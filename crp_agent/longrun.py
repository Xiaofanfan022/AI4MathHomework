"""可长期运行的智能体。

与 `agent.loop` 的区别
----------------------
`agent.loop` 跑固定轮数就退出，状态在内存里。这里把状态落到磁盘，
进程被杀、断电、机器重启之后都能从上次结束的地方继续。设计目标是
"写好后交给用户自己跑一周，回来再看结果"，因此优先保证的是
**不丢数据、不空转、不失控**，而不是单轮的速度。

四个工程件
----------
1. 断点续跑  每轮结束原子写一次 `state.json`；启动时若存在则恢复。
2. 去重账本  已提形式、已推翻、恒真式、已通过四张表，跨轮次持久化。
3. 预算上限  按小时限词元、按天限评估图数；超限则降档或休眠。
4. 自动日报  每日把新增候选与推翻记录汇总成 markdown，供人工抽检。

安全边界
--------
- 单实例锁：`longrun.lock` 存在且进程存活时拒绝启动第二个实例，
  避免两个进程同时写同一个 state.json。
- 单轮异常不终止进程：记录后休眠重试，连续失败达到阈值才退出。
- 所有上限都在 `Limits` 里显式写出，不依赖外部配置。

用法
----
    python -m crp_agent.longrun --hours 24
    python -m crp_agent.longrun --hours 168 --with-derived   # 跑一周
    python -m crp_agent.longrun --mock --hours 0.02          # 离线自检
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from .agent.loop import run_round
from .agent.trace import Trace
from .config import DATA_DIR, INVARIANTS, RUNS_DIR
from .core.features import derived_names, extend_dataset, feature_pool
from .core.split import split

STATE_NAME = "state.json"
LOCK_NAME = "longrun.lock"
LEDGER_NAME = "ledger.jsonl"
DAILY_DIR = "daily"


# ---------------------------------------------------------------- 预算
@dataclass
class Limits:
    """所有硬上限。刻意写得保守，宁少跑也不失控。"""

    max_hours: float = 24.0
    max_rounds: int = 500
    # 每小时词元上限，防止模型接口异常时烧掉整月额度
    tokens_per_hour: int = 400000
    # 每天最多评估多少张图（反例搜索的总评估量）
    graphs_per_day: int = 400000
    # 连续失败多少轮后退出
    max_consecutive_failures: int = 5
    # 每轮之间的休眠秒数，避免把接口打满
    sleep_between_rounds: float = 5.0
    # 超限后的休眠秒数
    sleep_on_limit: float = 600.0


@dataclass
class RoundPlan:
    """本轮的实际参数，会随预算压力降档。"""

    n_forms: int = 8
    budget: int = 1500
    n_perm: int = 200
    max_pred: int = 2


def plan_for(pressure: float) -> RoundPlan:
    """按预算压力决定本轮档位。

    pressure 是本小时已用词元占上限的比例。0.5 以下全速，
    0.5–0.8 减半，0.8 以上降到最低档。
    """
    if pressure < 0.5:
        return RoundPlan(8, 1500, 200)
    if pressure < 0.8:
        return RoundPlan(5, 800, 150)
    return RoundPlan(3, 400, 100)


# 形式空间扩张的三个阶段。基础空间 2304 条提完之后，若不再扩张，
# 后面几天只会重复已检验过的形式。
#
# 判据有两条，任一满足即升级：
#   (1) 已提互异键占当前档空间的比例达到 STAGE_FRACTIONS；
#   (2) 最近 STALE_WINDOW 轮平均每轮新增互异键少于 STALE_MIN_NEW 个。
# 只看 (1) 不够：实测每轮提出的 8 条里常有一半重复或塌缩，按 60% 的
# 阈值要跑几百轮才触发，而那几百轮的后半段已经在空转。加上 (2) 之后，
# 一旦新增速度掉下来就扩张，不必等比例凑满。
STAGE_FRACTIONS = (0.35, 0.35)
STALE_WINDOW = 6
STALE_MIN_NEW = 2.0


@dataclass
class Stage:
    """形式空间的当前档位。"""

    level: int = 0          # 0 基础两点 / 1 派生两点 / 2 派生三点
    label: str = "基础"

    @property
    def with_derived(self) -> bool:
        return self.level >= 1

    @property
    def max_pred(self) -> int:
        return 3 if self.level >= 2 else 2

    @classmethod
    def for_level(cls, level: int) -> "Stage":
        level = max(0, min(level, 2))
        return cls(level, ("基础", "乘积项", "三点预测子")[level])


# ---------------------------------------------------------------- 状态
@dataclass
class State:
    round: int = 0
    started_at: str = ""
    updated_at: str = ""
    seen: list[str] = field(default_factory=list)
    seen_keys: list[str] = field(default_factory=list)
    trivial_seen: list[str] = field(default_factory=list)
    lessons: list[dict] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    collapses_seen: list[dict] = field(default_factory=list)
    refuted_forms: list[str] = field(default_factory=list)
    retained_all: list[dict] = field(default_factory=list)
    # 用量
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    graphs_evaluated: int = 0
    # 按小时的用量窗口：[[hour_epoch, tokens], ...]
    hourly: list[list] = field(default_factory=list)
    # 按天的图数窗口：{"2026-11-24": 12345}
    daily_graphs: dict = field(default_factory=dict)
    consecutive_failures: int = 0
    stage_level: int = 0
    finished_reason: str = ""

    # ---- 序列化
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: Path) -> None:
        """原子写：先写临时文件再替换，避免断电留下半个 JSON。"""
        self.updated_at = _now()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        os.replace(tmp, path)

    # ---- 用量窗口
    def tokens_in_last_hour(self) -> int:
        cutoff = time.time() - 3600
        return sum(t for h, t in self.hourly if h >= cutoff)

    def graphs_today(self) -> int:
        return int(self.daily_graphs.get(_today(), 0))

    def add_tokens(self, t: int) -> None:
        self.hourly.append([time.time(), t])
        # 只保留最近两小时的窗口，避免无限增长
        cutoff = time.time() - 7200
        self.hourly = [x for x in self.hourly if x[0] >= cutoff]

    def add_graphs(self, g: int) -> None:
        d = _today()
        self.daily_graphs[d] = int(self.daily_graphs.get(d, 0)) + g
        self.graphs_evaluated += g


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 锁
class Lock:
    """单实例锁。

    只检查文件里记录的 pid 是否仍然存活，不用平台相关的文件锁——
    在 Windows 与 Linux 上行为一致，代价是 pid 复用时会误判。
    """

    def __init__(self, path: Path):
        self.path = path

    def acquire(self) -> bool:
        if self.path.exists():
            try:
                pid = int(self.path.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                pid = -1
            if pid > 0 and _pid_alive(pid):
                return False
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        return True

    def release(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    except Exception:                                   # noqa: BLE001
        return True
    return True


# ---------------------------------------------------------------- 账本
def append_ledger(path: Path, rec: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def daily_report(state: State, run_dir: Path) -> Path:
    """把账本里今天发生的事汇总成一页 markdown。"""
    d = _today()
    path = run_dir / DAILY_DIR / f"{d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    recs = []
    ledger = run_dir / LEDGER_NAME
    if ledger.exists():
        with open(ledger, encoding="utf-8") as f:
            for ln in f:
                if not ln.strip():
                    continue
                try:
                    r = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if str(r.get("ts", "")).startswith(d):
                    recs.append(r)

    lines = [f"# {d} 长跑日报", ""]
    lines.append(f"- 累计轮数：{state.round}")
    lines.append(f"- 累计调用：{state.calls} 次，"
                 f"{state.prompt_tokens} + {state.completion_tokens} 词元")
    lines.append(f"- 累计评估图数：{state.graphs_evaluated}")
    lines.append(f"- 已提形式：{len(state.seen_keys)} 个互异键")
    lines.append(f"- 已推翻：{len(state.refuted_forms)} 条")
    lines.append(f"- 恒真式：{len(state.trivial_seen)} 条")
    lines.append(f"- 已通过：{len(state.passed)} 条")
    lines.append("")

    rounds = [r for r in recs if r.get("kind") == "round"]
    if rounds:
        lines.append("## 今日各轮")
        lines.append("")
        lines.append("| 轮 | 提出 | 非平凡 | 恒真 | 推翻 | 保留 | 词元 |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in rounds:
            lines.append(f"| {r.get('round')} | {r.get('n_proposed')} | "
                         f"{r.get('n_solved')} | {r.get('n_trivial')} | "
                         f"{r.get('n_refuted')} | {r.get('n_retained')} | "
                         f"{r.get('tokens')} |")
        lines.append("")

    new_ret = [r for r in recs if r.get("kind") == "retained"]
    if new_ret:
        lines.append("## 今日新通过筛选的候选")
        lines.append("")
        for r in new_ret:
            lines.append(f"- `{r['inequality']}`　"
                         f"取等比例 {r.get('tight_ratio_V')}，"
                         f"p = {r.get('p_value')}，"
                         f"测试集{'成立' if r.get('holds_on_T') else '失败'}")
        lines.append("")

    new_ref = [r for r in recs if r.get("kind") == "refuted"]
    if new_ref:
        lines.append("## 今日被推翻的候选")
        lines.append("")
        for r in new_ref[:40]:
            lines.append(f"- `{r['inequality']}`　"
                         f"反例 {r.get('cex_n')} 个顶点")
        if len(new_ref) > 40:
            lines.append(f"- …… 另有 {len(new_ref) - 40} 条，见 ledger.jsonl")
        lines.append("")

    if not rounds and not new_ret and not new_ref:
        lines.append("今日无新增记录。")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 主循环
class LongRun:
    def __init__(self, run_dir: Path, limits: Limits,
                 with_derived: bool = False, use_mock: bool = False,
                 n_perm: int = 200, budget: int = 1500,
                 q: float = 0.1, auto_escalate: bool = True):
        self.run_dir = run_dir
        self.limits = limits
        self.auto_escalate = auto_escalate
        self.q = q
        self.base_perm = n_perm
        self.base_budget = budget

        self.state_path = run_dir / STATE_NAME
        self.ledger_path = run_dir / LEDGER_NAME
        self.state = State.load(self.state_path)
        if not self.state.started_at:
            self.state.started_at = _now()
        if with_derived:
            self.state.stage_level = max(self.state.stage_level, 1)

        # ---- 数据
        df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
        if self.state.stage_level >= 1:
            df = extend_dataset(df)
        parts = split(df, seed=20261120)
        self.D, self.V, self.T = parts["D"], parts["V"], parts["T"]

        self.target_pool = list(INVARIANTS)
        self.pred_pool = feature_pool(INVARIANTS,
                                      self.state.stage_level >= 1)

        # ---- 模型
        if use_mock:
            from .agent.mock import MockLLM
            self.llm = MockLLM(self.pred_pool, seed=0, n_forms=6)
        else:
            from .agent.llm import LLMClient
            self.llm = LLMClient()

        self.trace = Trace(run_dir)
        self.trace.round = self.state.round

        # 用量基线：模型客户端每次启动都从零计数，而 state 里保存的是
        # 累计值。续跑时若不记住基线，累计用量会被覆盖成"本次进程的用量"，
        # 预算判断随之失真。
        self._base_calls = self.state.calls
        self._base_prompt = self.state.prompt_tokens
        self._base_completion = self.state.completion_tokens

        self.known = ["chi + alpha <= n + 1",
                      "chi <= Delta + 1（Brooks 定理）",
                      "alpha + omega <= n + 1"]

    # ---- 会话内可变的集合（从 state 恢复）
    def _restore_sets(self):
        s = self.state
        return (set(s.seen), set(s.seen_keys), list(s.trivial_seen),
                list(s.lessons), list(s.passed), list(s.collapses_seen))

    def _persist_sets(self, seen, seen_keys, trivial_seen, lessons,
                      passed, collapses_seen):
        s = self.state
        s.seen = sorted(seen)
        s.seen_keys = sorted(seen_keys)
        s.trivial_seen = trivial_seen[-400:]
        s.lessons = lessons[-60:]
        s.passed = passed[-200:]
        s.collapses_seen = collapses_seen[-200:]

    def _exhausted(self) -> bool:
        """形式空间是否已经被提完。"""
        return len(self.state.seen_keys) >= self.form_space_size()

    def _escalate(self) -> bool:
        """检查是否应当放开下一档形式空间。

        两条判据任一满足即升级：空间占用比例，或近期新增速度。
        只看比例不够——实测每轮提出的 8 条里常有一半重复或塌缩，
        按比例要跑几百轮才触发，而那几百轮的后半段已经在空转。
        """
        if not self.auto_escalate or self.state.stage_level >= 2:
            return False

        used = len(self.state.seen_keys)
        space = self.form_space_size()
        by_fraction = space > 0 and used / space >= STAGE_FRACTIONS[0]
        by_stale = self._stale()

        if not (by_fraction or by_stale):
            return False

        self.state.stage_level += 1
        st = Stage.for_level(self.state.stage_level)
        if st.with_derived and "n2" not in self.D.columns:
            self.D = extend_dataset(self.D)
            self.V = extend_dataset(self.V)
            self.T = extend_dataset(self.T)
        self.pred_pool = feature_pool(INVARIANTS, st.with_derived)
        append_ledger(self.ledger_path, {
            "kind": "escalate", "ts": _now(), "round": self.state.round,
            "level": self.state.stage_level, "label": st.label,
            "space": self.form_space_size(st.max_pred),
            "reason": ("占用比例" if by_fraction else "新增速度下降"),
            "used": used,
        })
        print(f"[扩张] 形式空间升到第 {st.level} 档（{st.label}），"
              f"共约 {self.form_space_size(st.max_pred)} 条"
              f"（{'占用比例' if by_fraction else '新增速度下降'}）")
        return True

    def _stale(self) -> bool:
        """最近若干轮的新增互异形式是否已经很少。

        只统计最近 STALE_WINDOW 轮的 round 记录，用 seen_keys 的增量
        近似"新增"。少于 4 轮样本时不判断，避免开局误触发。
        """
        rows = self._recent_rounds(STALE_WINDOW)
        if len(rows) < 4:
            return False
        new_total = sum(int(r.get("n_new_keys") or 0) for r in rows)
        return new_total / len(rows) < STALE_MIN_NEW

    def _recent_rounds(self, k: int) -> list[dict]:
        rows: list[dict] = []
        if not self.ledger_path.exists():
            return rows
        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                for ln in f:
                    if not ln.strip():
                        continue
                    try:
                        r = json.loads(ln)
                    except json.JSONDecodeError:
                        continue
                    if r.get("kind") == "round":
                        rows.append(r)
        except OSError:
            return []
        return rows[-k:]

    def form_space_size(self, max_pred: int | None = None) -> int:
        """当前设置下的形式空间大小。

        目标数 × 两个方向 × 每个目标的（预测子子集 × 符号组合）总数。
        预测子可以含派生特征，目标只能是基础不变量。
        """
        from math import comb

        if max_pred is None:
            max_pred = Stage.for_level(self.state.stage_level).max_pred
        n_feat = len(self.pred_pool)
        n_tgt = len(self.target_pool)
        per = 0
        for k in range(1, max_pred + 1):
            per += comb(n_feat - 1, k) * (2 ** k)
        return n_tgt * 2 * per

    # ---- 单轮
    def run_one_round(self) -> dict:
        s = self.state
        s.round += 1
        self.trace.round = s.round

        pressure = s.tokens_in_last_hour() / max(self.limits.tokens_per_hour, 1)
        plan = plan_for(pressure)
        st = Stage.for_level(s.stage_level)
        plan.max_pred = st.max_pred
        budget = min(plan.budget, self.base_budget)
        n_perm = min(plan.n_perm, self.base_perm)

        tok_before = (self.llm.prompt_tokens + self.llm.completion_tokens)
        (seen, seen_keys, trivial_seen, lessons, passed,
         collapses_seen) = self._restore_sets()
        keys_before = len(seen_keys)

        res = run_round(
            self.llm, self.trace, s.round, self.D, self.V,
            self.known, s.refuted_forms,
            budget=budget, n_perm=n_perm, q=self.q, verbose=True,
            seen=seen, seen_keys=seen_keys, trivial_seen=trivial_seen,
            lessons=lessons, passed=passed,
            collapses_seen=collapses_seen,
            pred_pool=self.pred_pool,
            max_forms=plan.n_forms,
            max_pred=st.max_pred,
        )

        collapses_seen.extend(res.collapses)
        self._persist_sets(seen, seen_keys, trivial_seen, lessons, passed,
                           collapses_seen)

        # 本轮评估的图数：由 run_round 累加，避免每轮回读整个轨迹文件
        graphs = res.graphs_used

        tok_after = (self.llm.prompt_tokens + self.llm.completion_tokens)
        used = tok_after - tok_before
        # 累计值 = 续跑前的基线 + 本进程用量
        s.calls = self._base_calls + self.llm.calls
        s.prompt_tokens = self._base_prompt + self.llm.prompt_tokens
        s.completion_tokens = (self._base_completion
                               + self.llm.completion_tokens)
        s.add_tokens(used)
        s.add_graphs(graphs)

        rec = {
            "kind": "round",
            "ts": _now(),
            "round": s.round,
            "n_proposed": len(res.proposed),
            "n_solved": len(res.solved),
            "n_trivial": len(res.trivial),
            "n_refuted": len(res.refuted),
            "n_survived": len(res.survived),
            "n_retained": len(res.retained),
            "n_key_repeat": res.n_key_repeat,
            "n_new_keys": len(seen_keys) - keys_before,
            "tokens": used,
            "graphs": graphs,
            "plan": asdict(plan),
        }
        append_ledger(self.ledger_path, rec)

        for c in res.retained:
            d = c.to_dict()
            d["holds_on_T"] = bool(
                _holds_on(self.T, c.solution))
            s.retained_all.append(d)
            # 写全字段：分析脚本要拿 predictors/coefs/target/direction
            # 在完整数据集上复验，只存不等式文本无法重算。
            append_ledger(self.ledger_path, {
                "kind": "retained", "ts": _now(), "round": s.round, **d,
            })

        for r in res.refuted:
            append_ledger(self.ledger_path, {
                "kind": "refuted", "ts": _now(), "round": s.round,
                "inequality": r.get("inequality"),
                "cex_n": (r.get("counterexample") or {}).get("n"),
            })

        s.save(self.state_path)
        daily_report(s, self.run_dir)
        return rec

    def loop(self) -> None:
        lim = self.limits
        t0 = time.time()
        print("=" * 66)
        print("CRP-Agent 长跑")
        print("=" * 66)
        print(f"运行目录 {self.run_dir}")
        print(f"恢复自第 {self.state.round} 轮" if self.state.round
              else "全新开始")
        print(f"数据 D={len(self.D)} V={len(self.V)} T={len(self.T)}")
        print(f"形式空间约 {self.form_space_size()} 条"
              f"（预测子 {len(self.pred_pool)} 个，"
              f"第 {self.state.stage_level} 档 "
              f"{Stage.for_level(self.state.stage_level).label}）")

        while True:
            if (time.time() - t0) / 3600 >= lim.max_hours:
                self.state.finished_reason = "达到时间上限"
                break
            if self.state.round >= lim.max_rounds:
                self.state.finished_reason = "达到轮数上限"
                break

            if self.state.tokens_in_last_hour() >= lim.tokens_per_hour:
                print(f"[预算] 本小时词元已达上限，休眠 "
                      f"{lim.sleep_on_limit:.0f} 秒")
                time.sleep(lim.sleep_on_limit)
                continue
            if self.state.graphs_today() >= lim.graphs_per_day:
                print("[预算] 今日评估图数已达上限，休眠到下一个整点")
                time.sleep(min(lim.sleep_on_limit, 3600))
                continue
            if self._escalate():
                pass
            if self._exhausted():
                self.state.finished_reason = "形式空间已提完"
                break

            try:
                rec = self.run_one_round()
                self.state.consecutive_failures = 0
                print(f"[第 {rec['round']} 轮] 提出 {rec['n_proposed']}，"
                      f"非平凡 {rec['n_solved']}，推翻 {rec['n_refuted']}，"
                      f"保留 {rec['n_retained']}，"
                      f"词元 {rec['tokens']}")
            except KeyboardInterrupt:
                self.state.finished_reason = "人工中断"
                break
            except Exception as e:                      # noqa: BLE001
                self.state.consecutive_failures += 1
                msg = f"{type(e).__name__}: {e}"
                print(f"[失败 {self.state.consecutive_failures}] {msg}")
                append_ledger(self.ledger_path, {
                    "kind": "error", "ts": _now(),
                    "round": self.state.round,
                    "error": msg,
                    "traceback": traceback.format_exc()[-2000:],
                })
                self.state.save(self.state_path)
                if self.state.consecutive_failures >= \
                        lim.max_consecutive_failures:
                    self.state.finished_reason = "连续失败过多"
                    break
                time.sleep(min(60 * self.state.consecutive_failures, 600))
                continue

            time.sleep(lim.sleep_between_rounds)

        self.state.save(self.state_path)
        daily_report(self.state, self.run_dir)
        print(f"\n结束：{self.state.finished_reason}")
        print(f"共 {self.state.round} 轮，调用 {self.state.calls} 次，"
              f"{self.state.prompt_tokens} + "
              f"{self.state.completion_tokens} 词元")
        print(f"已提形式 {len(self.state.seen_keys)} 个互异键，"
              f"推翻 {len(self.state.refuted_forms)} 条，"
              f"保留 {len(self.state.retained_all)} 条")


def _holds_on(T: pd.DataFrame, sol) -> bool:
    from .core.stats import min_slack
    try:
        return bool(min_slack(T, sol) >= -1e-9)
    except (KeyError, ValueError):
        return False


# ---------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description="CRP-Agent 长跑")
    ap.add_argument("--hours", type=float, default=24.0,
                    help="最多运行多少小时；跑一周用 168")
    ap.add_argument("--max-rounds", type=int, default=500)
    ap.add_argument("--with-derived", action="store_true",
                    help="直接以乘积项档位起步（默认从基础档开始，自动升级）")
    ap.add_argument("--no-escalate", action="store_true",
                    help="禁止自动扩张形式空间，用于对照实验")
    ap.add_argument("--mock", action="store_true",
                    help="用离线假模型，只验证工程件")
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--budget", type=int, default=1500)
    ap.add_argument("--q", type=float, default=0.1)
    ap.add_argument("--run-dir", type=str, default="",
                    help="指定运行目录，便于续跑")
    args = ap.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        run_dir = RUNS_DIR / f"longrun_{time.strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    lock = Lock(run_dir / LOCK_NAME)
    if not lock.acquire():
        print(f"另一个实例正在使用 {run_dir}，退出。")
        return

    try:
        LongRun(run_dir, Limits(max_hours=args.hours,
                                max_rounds=args.max_rounds),
                with_derived=args.with_derived, use_mock=args.mock,
                n_perm=args.n_perm, budget=args.budget, q=args.q,
                auto_escalate=not args.no_escalate).loop()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
