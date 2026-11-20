"""智能体主循环。

一轮的流程
----------
1. 提出  模型给出若干候选形式（只给形式，不给系数）
2. 求解  线性规划确定系数，得到具体不等式
3. 反驳  在有限预算内搜索反例；找到即淘汰，并让模型解释原因
4. 筛选  对存活的候选做置换检验与 BH 校正
5. 记录  每一步写入轨迹

与"脚本"的区别在于第 1、3、4 步都需要模型判断，
且第 3 步的策略由模型选择。这些选择都写进轨迹，便于事后审计。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import DATA_DIR, RUNS_DIR
from ..core.counterexample import search_counterexample, tight_seed_graphs
from ..core.forms import Form, Solution, dedup, rank, solve_form
from ..core.informativeness import label
from ..core.split import split
from ..core.stats import (bh_filter, min_slack, permutation_pvalues,
                          summarize, tight_ratio)
from .llm import LLMClient
from .prompts import (SYSTEM_EXPLAIN, SYSTEM_NOVELTY, SYSTEM_PROPOSE,
                      SYSTEM_STRATEGY, explain_user_prompt,
                      novelty_user_prompt, propose_user_prompt,
                      strategy_user_prompt)
from .trace import Trace


def data_summary(df: pd.DataFrame, target: str = "chi") -> dict:
    """给模型的紧凑数据摘要。

    除目标不变量的相关系数外，还给出不变量两两之间的相关矩阵。只给
    "各量与 chi 的相关"会让模型几乎只把 chi 当目标，因为摘要里只有
    这一个被标为目标的量，其余量看起来都是"解释变量"。给出完整的相关
    结构后，模型才有可能对其他目标提出候选。
    """
    cols = [c for c in df.columns
            if c not in ("graph_id", "source", "edges")]
    full = df[cols].corr(method="spearman")
    corr = full[target].drop(target)

    # 相关最强的前若干对，帮助模型看到哪些量彼此接近共线
    pairs = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            pairs.append((a, b, float(full.loc[a, b])))
    pairs.sort(key=lambda t: -abs(t[2]))
    top_pairs = [{"a": a, "b": b, "rho": round(v, 3)}
                 for a, b, v in pairs[:8]]

    return {
        "n_graphs": len(df),
        "n_range": f"{int(df['n'].min())} 到 {int(df['n'].max())}",
        "target": target,
        "corr_with_target": {k: round(float(v), 3)
                             for k, v in corr.items()},
        "top_correlated_pairs": top_pairs,
        "ranges": {k: (int(df[k].min()), int(df[k].max()))
                   for k in cols if k != target},
    }


def _norm_sign(v) -> int:
    """把 1/-1、"+"/"-"、"plus"/"minus" 统一成 1/-1。"""
    if isinstance(v, (int, float)):
        return 1 if v > 0 else -1
    s = str(v).strip().lower()
    if s in ("+", "+1", "1", "plus", "pos", "positive"):
        return 1
    if s in ("-", "-1", "minus", "neg", "negative"):
        return -1
    raise ValueError(f"无法识别的符号：{v!r}")


def parse_forms(raw: dict, target_pool: list[str]) -> list[Form]:
    """把模型的 JSON 输出转成 Form，剔除不合法的。"""
    out: list[Form] = []
    for item in raw.get("forms", []):
        try:
            t = str(item["target"]).strip()
            d = str(item.get("direction", "le")).strip().lower()
            d = {"<=": "le", "≤": "le", "=<": "le",
                 ">=": "ge", "≥": "ge", "=>": "ge"}.get(d, d)
            preds = [str(p).strip() for p in item["predictors"]]
            signs = [_norm_sign(s) for s in item["signs"]]

            if t not in target_pool or d not in ("le", "ge"):
                continue
            if len(preds) != len(signs) or not 1 <= len(preds) <= 3:
                continue
            if t in preds or any(p not in target_pool for p in preds):
                continue
            if len(set(preds)) != len(preds):
                continue
            if any(s not in (1, -1) for s in signs):
                continue

            out.append(Form(t, tuple(preds), tuple(signs), d))
        except (KeyError, TypeError, ValueError):
            continue
    return out


class CRPResult:
    """单轮的结果容器。"""

    def __init__(self, rnd: int):
        self.round = rnd
        self.proposed: list[Form] = []
        self.solved: list[Solution] = []
        self.trivial: list[dict] = []
        self.refuted: list[dict] = []
        self.survived: list[Solution] = []
        self.tested: list = []
        self.retained: list = []

    def to_dict(self) -> dict:
        return {
            "round": self.round,
            "n_proposed": len(self.proposed),
            "n_solved": len(self.solved),
            "n_trivial": len(self.trivial),
            "n_refuted": len(self.refuted),
            "n_survived": len(self.survived),
            "n_retained": len(self.retained),
            "trivial": self.trivial,
            "refuted": self.refuted,
            "retained": [c.to_dict() for c in self.retained],
        }


def run_round(llm: LLMClient, trace: Trace, rnd: int,
              D: pd.DataFrame, V: pd.DataFrame,
              known: list[str], refuted_forms: list[str],
              *, budget: int = 1500, n_perm: int = 200,
              q: float = 0.1, verbose: bool = True,
              seen: set[str] | None = None,
              trivial_seen: list[str] | None = None) -> CRPResult:
    """执行一轮完整循环。

    seen 收集此前各轮已经处理过的不等式文本。不同形式在系数被压到零后
    可能塌缩成同一条不等式，若不剔除，后续轮次会重复反驳同一条候选。

    trivial_seen 收集被判为无信息量的恒真式。这类形式统计上必然通过
    检验，若不在提示中排除，模型会反复提出它们并占用筛选名额。
    """
    res = CRPResult(rnd)
    pool = ["n", "m", "Delta", "delta", "alpha", "omega", "chi", "nu", "rho"]
    seen = seen if seen is not None else set()
    trivial_seen = trivial_seen if trivial_seen is not None else []

    # ---------------- 1. 提出
    summary = data_summary(D)
    user = propose_user_prompt(summary, known, refuted_forms, rnd,
                               exhausted=sorted(seen),
                               trivial=trivial_seen)
    raw = llm.chat_json(SYSTEM_PROPOSE, user)

    res.proposed = parse_forms(raw, pool)
    trace.write("propose", llm_input=user[-1200:], llm_output=raw,
                n_forms=len(res.proposed),
                forms=[f.key for f in res.proposed])
    if verbose:
        print(f"  [提出] {len(res.proposed)} 条形式")

    # ---------------- 2. 求解
    n_collapsed = 0
    for f in res.proposed:
        sol = solve_form(D, f)
        if sol is None or sol.trivial:
            continue
        if sol.inequality_str() in seen:
            n_collapsed += 1
            continue
        res.solved.append(sol)
    res.solved = dedup(rank(res.solved))

    # ---------------- 2b. 剔除恒真式
    # 统计筛选只回答"是否超出偶然"，不回答"是否有内容"。由定义直接
    # 成立的形式必然通过检验，若留到筛选阶段会占用名额并误导对模型
    # 产出的评价，因此提前剔除并记入提示，避免下一轮重复提出。
    kept: list[Solution] = []
    for sol in res.solved:
        info = label(D, sol)
        if info["informative"]:
            kept.append(sol)
        else:
            res.trivial.append({"inequality": sol.inequality_str(),
                                "dominated_by": info["dominated_by"]})
            trivial_seen.append(sol.inequality_str())
            seen.add(sol.inequality_str())
    n_trivial = len(res.trivial)
    res.solved = kept

    trace.write("solve", n_solved=len(res.solved),
                n_repeat=n_collapsed, n_trivial=n_trivial,
                trivial=res.trivial,
                candidates=[s.to_dict() for s in res.solved])
    if verbose:
        msg = f"  [求解] {len(res.solved)} 条非平凡不等式"
        if n_collapsed:
            msg += f"（{n_collapsed} 条与前轮重复，已剔除）"
        if n_trivial:
            msg += f"（{n_trivial} 条恒真式，已剔除）"
        print(msg)

    # ---------------- 3. 反驳
    for sol in res.solved:
        hist = []
        found = False
        for attempt in range(2):
            raw_s = llm.chat_json(
                SYSTEM_STRATEGY,
                strategy_user_prompt(sol.inequality_str(), hist))
            strategy = raw_s.get("strategy", "structured")
            b = int(raw_s.get("budget", budget))
            b = max(100, min(b, budget))

            sr = search_counterexample(
                sol.signed_coefs(), sol.intercept, sol.form.direction,
                sol.form.target, strategy=strategy, budget=b, n_lo=3,
                n_hi=12, seed=1000 * rnd + attempt,
                tight_graphs=tight_seed_graphs(V, sol))

            hist.append({"strategy": strategy, "budget_used": sr.budget_used,
                         "found": sr.found})
            trace.write("refute", inequality=sol.inequality_str(),
                        strategy=strategy, budget=b,
                        budget_used=sr.budget_used, found=sr.found,
                        graph=sr.graph)

            if sr.found:
                from ..core.invariants import compute_all
                inv = compute_all(sr.graph["n"],
                                  [tuple(e) for e in sr.graph["edges"]])
                ce = {"n": sr.graph["n"], "edges": sr.graph["edges"],
                      "invariants": inv}

                raw_e = llm.chat_json(
                    SYSTEM_EXPLAIN,
                    explain_user_prompt(sol.inequality_str(), ce))
                trace.write("explain", inequality=sol.inequality_str(),
                            llm_output=raw_e)

                res.refuted.append({
                    "inequality": sol.inequality_str(),
                    "counterexample": ce,
                    "strategy": strategy,
                    "budget_used": sr.budget_used,
                    "explanation": raw_e,
                })
                refuted_forms.append(sol.inequality_str())
                seen.add(sol.inequality_str())
                found = True
                break

        seen.add(sol.inequality_str())
        if not found:
            res.survived.append(sol)

    if verbose:
        print(f"  [反驳] 推翻 {len(res.refuted)} 条，存活 {len(res.survived)} 条")

    # ---------------- 4. 筛选
    if res.survived:
        res.tested = permutation_pvalues(D, V, res.survived,
                                         n_perm=n_perm, seed=20261120,
                                         verbose=False)
        res.tested = bh_filter(res.tested, q=q)
        res.retained = [c for c in res.tested if c.retained]

        for c in res.retained:
            raw_n = llm.chat_json(
                SYSTEM_NOVELTY,
                novelty_user_prompt(c.solution.inequality_str(),
                                    c.tight_ratio, len(V)))
            # 统计筛选只回答"是否超出偶然"，不回答"是否有内容"。
            # 恒真式（如 omega <= chi）必然通过检验，需另打标签。
            info = label(D, c.solution)
            trace.write("novelty", inequality=c.solution.inequality_str(),
                        p_value=c.p_value, llm_output=raw_n,
                        informative=info["informative"],
                        dominated_by=info["dominated_by"])
            c.solution.novelty = raw_n          # 附加信息，仅用于展示
            c.solution.informative = info["informative"]

        trace.write("filter", q=q, n_perm=n_perm,
                    n_tested=len(res.tested),
                    n_retained=len(res.retained),
                    retained=[c.to_dict() for c in res.retained])
        if verbose:
            print(f"  [筛选] 保留 {len(res.retained)}/{len(res.tested)}")

    return res


def main(dry_run: bool = False, max_rounds: int = 3,
         n_perm: int = 200, budget: int = 1500) -> None:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / f"agent_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print("CRP-Agent 运行")
    print("=" * 66)

    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    parts = split(df, seed=20261120)
    D, V, T = parts["D"], parts["V"], parts["T"]
    print(f"\n数据划分：D={len(D)}  V={len(V)}  T={len(T)}")

    if dry_run:
        print("\n[演练模式] 不调用模型，仅检查数据结构")
        s = data_summary(D)
        print(json.dumps(s, ensure_ascii=False, indent=2)[:800])
        return

    llm = LLMClient()
    print(f"\n模型：{llm.cfg.model}  接口：{llm.cfg.base_url}")

    trace = Trace(run_dir)
    trace.write("start", model=llm.cfg.model,
                n_D=len(D), n_V=len(V), n_T=len(T),
                max_rounds=max_rounds)

    known = ["chi + alpha <= n + 1",
             "chi <= Delta + 1（Brooks 定理）",
             "alpha + omega <= n + 1"]
    refuted: list[str] = []
    all_retained: list[dict] = []
    rounds: list[dict] = []
    seen: set[str] = set()
    trivial_seen: list[str] = []

    for r in range(1, max_rounds + 1):
        print(f"\n--- 第 {r} 轮 ---")
        trace.round = r
        res = run_round(llm, trace, r, D, V, known, refuted,
                        budget=budget, n_perm=n_perm, seen=seen,
                        trivial_seen=trivial_seen)
        rounds.append(res.to_dict())
        all_retained.extend([c.to_dict() for c in res.retained])

    # ---------------- 测试集复核
    print("\n--- 测试集复核 ---")
    checked = []
    for item in all_retained:
        sol = None
        # 用轨迹里的形式重建
        f = Form(item["target"], tuple(item["predictors"]),
                 tuple(item["signs"]), item["direction"])
        sol = solve_form(D, f)
        if sol is None:
            continue
        ms = min_slack(T, sol)
        item["min_slack_T"] = round(ms, 8)
        item["holds_on_T"] = bool(ms >= -1e-9)
        checked.append(item)

    n_hold = sum(1 for c in checked if c["holds_on_T"])
    print(f"保留的 {len(checked)} 条中，{n_hold} 条在测试集上仍成立")

    out = {
        "stamp": stamp,
        "model": llm.cfg.model,
        "usage": llm.usage,
        "n_D": len(D), "n_V": len(V), "n_T": len(T),
        "rounds": rounds,
        "retained_all": checked,
        "n_retained": len(checked),
        "n_holds_on_T": n_hold,
    }
    with open(run_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到 {run_dir}")
    print(f"模型调用 {llm.usage['calls']} 次，"
          f"消耗 {llm.usage['prompt_tokens']} + "
          f"{llm.usage['completion_tokens']} tokens")
