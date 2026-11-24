"""长跑结果分析。

用户自己跑完一周之后，用这个脚本把整个运行目录读成一份可读的报告：
账本汇总、逐轮走势、被保留候选的清单与复验、失败模式统计。

设计原则
--------
1. **只读**。不修改运行目录里的任何文件，分析可以反复做。
2. **容忍残缺**。长跑可能被中途杀掉，state.json 与 ledger.jsonl 可能
   不同步，轨迹里可能有半行 JSON。所有读取都做了容错。
3. **复验保留候选**。账本里记录的"测试集成立"是当时的判断，这里
   重新在完整数据上算一遍最小松弛，避免因中途改代码而产生假记录。

用法
----
    python -m crp_agent.analyze_longrun                       # 取最新一次
    python -m crp_agent.analyze_longrun --run-dir runs/longrun_xxx
    python -m crp_agent.analyze_longrun --out report.md
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, INVARIANTS, RUNS_DIR
from .core.features import extend_dataset


# ---------------------------------------------------------------- 读账本
def read_ledger(run_dir: Path) -> list[dict]:
    path = run_dir / "ledger.jsonl"
    if not path.exists():
        return []
    out = []
    # utf-8-sig：某些编辑器写出的账本带 BOM，会让首行解析失败
    with open(path, encoding="utf-8-sig") as f:
        for ln in f:
            if not ln.strip():
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue          # 进程被杀时最后一行可能是半截
    return out


def read_state(run_dir: Path) -> dict:
    path = run_dir / "state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _fmt(v) -> str:
    """账本里可能缺字段，缺失显示为短横而不是 None。"""
    return "-" if v is None else str(v)


# ---------------------------------------------------------------- 复验
def recheck(inequality_rows: list[dict], df: pd.DataFrame,
            with_derived: bool) -> list[dict]:
    """在完整数据上重新计算每条保留候选的最小松弛与取等比例。

    账本里的数字来自当时的验证集与测试集，中途若改过划分或代码，
    那些数字就不再可信。这里用账本里存下来的 form 与系数重算。
    """
    if with_derived and "n2" not in df.columns:
        df = extend_dataset(df)

    out = []
    for r in inequality_rows:
        preds = r.get("predictors") or []
        signs = r.get("signs") or [1] * len(preds)
        coefs = r.get("coefs") or {}
        target = r.get("target")
        direction = r.get("direction")
        intercept = float(r.get("intercept") or 0.0)

        missing = [p for p in preds if p not in df.columns]
        if not preds or target not in df.columns or missing:
            out.append({**r, "recheck": "跳过（列缺失）"})
            continue

        # coefs 存的是非负幅值，符号在 signs 里。漏乘符号会把
        # 「n - nu」算成「n + nu」，复验结果完全失真。
        lhs = sum(float(sg) * coefs.get(p, 0.0)
                  * df[p].to_numpy(dtype=float)
                  for p, sg in zip(preds, signs)) + intercept
        t = df[target].to_numpy(dtype=float)
        slack = lhs - t if direction == "le" else t - lhs

        scale = max(abs(t).max(), 1.0)
        out.append({
            **r,
            "recheck_min_slack": round(float(slack.min()), 6),
            "recheck_tight_ratio": round(
                float((abs(slack) <= 1e-6 * scale).mean()), 6),
            "recheck_violations": int((slack < -1e-9).sum()),
        })
    return out


# ---------------------------------------------------------------- 报告
def build_report(run_dir: Path, df: pd.DataFrame) -> str:
    state = read_state(run_dir)
    rows = read_ledger(run_dir)

    rounds = [r for r in rows if r.get("kind") == "round"]
    retained = [r for r in rows if r.get("kind") == "retained"]
    refuted = [r for r in rows if r.get("kind") == "refuted"]
    errors = [r for r in rows if r.get("kind") == "error"]
    escalates = [r for r in rows if r.get("kind") == "escalate"]

    # 旧版账本的 retained 记录只存了四个字段，无法复验；state.json 里
    # 的 retained_all 一直是全字段，优先用它补全。
    if retained and not retained[0].get("predictors"):
        full = state.get("retained_all") or []
        if len(full) == len(retained):
            # retained_all 没有 round 字段，但两者写入顺序一致，按序对齐
            retained = [{**r, **d} for r, d in zip(retained, full)]
        elif full:
            by_ineq = {d.get("inequality"): d for d in full}
            retained = [{**r, **by_ineq.get(r.get("inequality"), {})}
                        for r in retained]

    with_derived = bool(state.get("stage_level", 0) >= 1)

    L = []
    L.append(f"# 长跑分析：{run_dir.name}")
    L.append("")
    L.append("## 一、总体")
    L.append("")
    # state.json 可能损坏或缺失，轮数以账本里实际完成的轮次为准
    L.append(f"- 轮数：{max(int(state.get('round') or 0), len(rounds))}")
    L.append(f"- 起止：{state.get('started_at', '?')} → "
             f"{state.get('updated_at', '?')}")
    L.append(f"- 结束原因：{state.get('finished_reason') or '（仍在运行）'}")
    L.append(f"- 模型调用：{state.get('calls', 0)} 次，"
             f"{state.get('prompt_tokens', 0)} + "
             f"{state.get('completion_tokens', 0)} 词元")
    L.append(f"- 评估图数：{state.get('graphs_evaluated', 0)}")
    L.append(f"- 已提互异形式：{len(state.get('seen_keys', []))}")
    L.append(f"- 形式空间档位：第 {state.get('stage_level', 0)} 档")
    if escalates:
        for e in escalates:
            L.append(f"  - 第 {e.get('round')} 轮升到 {e.get('label')}，"
                     f"空间 {e.get('space')} 条（{e.get('reason')}）")
    L.append("")

    if errors:
        L.append(f"## 二、异常（{len(errors)} 次）")
        L.append("")
        c = Counter(e.get("error", "")[:80] for e in errors)
        for msg, k in c.most_common(8):
            L.append(f"- {k} 次：`{msg}`")
        L.append("")

    L.append("## 三、逐轮走势")
    L.append("")
    L.append("| 轮 | 提出 | 非平凡 | 恒真 | 推翻 | 保留 | 新形式 | 重复 | 词元 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rounds:
        L.append(f"| {r.get('round')} | {r.get('n_proposed')} | "
                 f"{r.get('n_solved')} | {r.get('n_trivial')} | "
                 f"{r.get('n_refuted')} | {r.get('n_retained')} | "
                 f"{_fmt(r.get('n_new_keys'))} | {r.get('n_key_repeat')} | "
                 f"{r.get('tokens')} |")
    L.append("")
    if any(r.get("n_new_keys") is None for r in rounds):
        L.append("> 新形式一列的 `-` 来自加入该字段之前的旧账本，"
                 "缺失不等于零，判读时不参与计算。")
        L.append("")

    if rounds:
        n = len(rounds)
        L.append("### 转化率")
        L.append("")
        tot = lambda k: sum(int(r.get(k) or 0) for r in rounds)  # noqa: E731
        prop = tot("n_proposed") or 1
        L.append(f"- 提出 → 非平凡：{tot('n_solved')} / {prop} "
                 f"= {tot('n_solved') / prop:.1%}")
        L.append(f"- 提出 → 恒真式剔除：{tot('n_trivial')} / {prop} "
                 f"= {tot('n_trivial') / prop:.1%}")
        L.append(f"- 提出 → 被推翻：{tot('n_refuted')} / {prop} "
                 f"= {tot('n_refuted') / prop:.1%}")
        L.append(f"- 提出 → 保留：{tot('n_retained')} / {prop} "
                 f"= {tot('n_retained') / prop:.1%}")
        # 旧账本没有 n_new_keys，缺失不能当 0 拉低平均
        fresh = [r for r in rounds if r.get("n_new_keys") is not None]
        if fresh:
            L.append(f"- 平均每轮新增互异形式："
                     f"{sum(int(r['n_new_keys']) for r in fresh) / len(fresh):.2f} 个"
                     f"（基于 {len(fresh)} 轮）")
        else:
            L.append("- 平均每轮新增互异形式：无法计算（账本缺少该字段）")
        L.append(f"- 平均每轮词元：{tot('tokens') / n:.0f}")
        L.append("")

    L.append("## 四、被保留的候选")
    L.append("")
    if not retained:
        L.append("（无）")
        L.append("")
    else:
        checked = recheck(retained, df, with_derived)
        L.append(f"共 {len(checked)} 条。下表在完整数据集上复验过，"
                 f"`违反` 为 0 表示在全部 {len(df)} 张图上都成立。")
        L.append("")
        L.append("| 不等式 | 取等比例 | p 值 | 测试集 | 复验违反 | 复验取等 |")
        L.append("|---|---|---|---|---|---|")
        for c in checked:
            L.append(f"| `{c.get('inequality')}` | "
                     f"{c.get('tight_ratio_V')} | {c.get('p_value')} | "
                     f"{'成立' if c.get('holds_on_T') else '失败'} | "
                     f"{c.get('recheck_violations', '-')} | "
                     f"{c.get('recheck_tight_ratio', '-')} |")
        L.append("")

        # 重复出现的候选：长期运行时同一条被反复"重新发现"是重要信号
        cnt = Counter(c.get("inequality") for c in checked)
        dup = [(q, k) for q, k in cnt.items() if k > 1]
        if dup:
            L.append("### 被重复发现的候选")
            L.append("")
            L.append("长期运行时同一条不等式被多次保留。次数越多，"
                     "说明提示词越难把它排除在候选之外。")
            L.append("")
            for q, k in sorted(dup, key=lambda x: -x[1])[:10]:
                L.append(f"- {k} 次：`{q}`")
            L.append("")

    L.append("## 五、被推翻的候选")
    L.append("")
    if not refuted:
        L.append("（无）")
        L.append("")
    else:
        L.append(f"共 {len(refuted)} 条。按反例阶数分布：")
        L.append("")
        c = Counter(r.get("cex_n") for r in refuted)
        for n_val, k in sorted(c.items(), key=lambda x: (x[0] is None, x[0])):
            L.append(f"- n = {n_val}：{k} 条")
        L.append("")
        L.append("最近 20 条：")
        L.append("")
        for r in refuted[-20:]:
            L.append(f"- 第 {r.get('round')} 轮：`{r.get('inequality')}`"
                     f"（反例 {r.get('cex_n')} 个顶点）")
        L.append("")

    L.append("## 六、判读")
    L.append("")
    L.extend(_verdict(state, rounds, retained, refuted, escalates))
    L.append("")
    return "\n".join(L)


def _verdict(state: dict, rounds: list[dict], retained: list[dict],
             refuted: list[dict], escalates: list[dict]) -> list[str]:
    """把数字翻译成几句话，避免只给表格不给结论。"""
    out = []
    if not rounds:
        return ["账本里没有完成的轮次，无法判读。"
                "（若进程被中途杀掉，请检查 ledger.jsonl 是否完整。）"]

    n = len(rounds)
    fresh = [r for r in rounds if r.get("n_new_keys") is not None]
    prop = sum(int(r.get("n_proposed") or 0) for r in rounds) or 1
    ret_rate = sum(int(r.get("n_retained") or 0) for r in rounds) / prop

    if not fresh:
        out.append("- 账本缺少「每轮新增互异形式」，无法判断形式空间"
                   "是否接近饱和。下一版运行会记录该字段。")
    else:
        new_per_round = sum(int(r["n_new_keys"]) for r in fresh) / len(fresh)
        if new_per_round >= 4:
            out.append(f"- 新增速度仍然健康（每轮 {new_per_round:.1f} 个互异形式），"
                       f"说明形式空间还没被提完，继续跑仍有新内容。")
        elif new_per_round >= 2:
            out.append(f"- 新增速度开始下降（每轮 {new_per_round:.1f} 个），"
                       f"若还没有触发扩张，下一档应当尽快放开。")
        else:
            out.append(f"- 新增速度已很低（每轮 {new_per_round:.1f} 个），"
                       f"继续在当前离线上的边际收益有限。")

    if ret_rate > 0.15:
        out.append(f"- 保留率 {ret_rate:.1%} 偏高，需要抽查是否存在"
                   f"检查器漏判的恒真式。")
    else:
        out.append(f"- 保留率 {ret_rate:.1%}，与短跑的 10% 量级相当，"
                   f"没有出现筛选失效的迹象。")

    if not escalates and state.get("stage_level", 0) == 0:
        out.append("- 全程停留在基础档，乘积项与三点形式都未启用。"
                   "若跑满一周，这部分空间是浪费的。")

    if len(retained) > 0 and len(refuted) == 0:
        out.append("- 有保留但没有推翻，这不正常："
                   "说明反例搜索或提示词有一环没在工作。")
    return out


# ---------------------------------------------------------------- CLI
def _latest() -> Path | None:
    dirs = sorted(glob.glob(str(RUNS_DIR / "longrun_*")))
    return Path(dirs[-1]) if dirs else None


def main() -> None:
    ap = argparse.ArgumentParser(description="分析长跑结果")
    ap.add_argument("--run-dir", type=str, default="")
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--print", action="store_true",
                    help="同时打印到终端")
    args = ap.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else _latest()
    if run_dir is None or not run_dir.exists():
        print(f"找不到运行目录：{run_dir}")
        return

    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    text = build_report(run_dir, df)

    out = Path(args.out) if args.out else run_dir / "analysis.md"
    out.write_text(text, encoding="utf-8")
    print(f"已写入 {out}（{len(text)} 字符）")
    if args.print:
        print()
        print(text)


if __name__ == "__main__":
    main()
