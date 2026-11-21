"""注入假命题：反例搜索在"反例稀少且阶数较大"条件下的检出率。

问题
----
真实候选的真伪无从判定，因此无法直接测量"反例搜索有多可靠"。
这里改用**已知为假**的命题：真值由数据集直接给出，
于是可以精确统计搜索是否找到了反例。

三次失败的设计（记下来避免重犯）
------------------------------
1. 把已知成立的界整体收紧 1、2、3。结果每条假命题在 27810 张图上
   有数百至上万个反例，三类策略在预算 50 时检出率即达 100%
   （`runs/inject_20261121_143227`）。这测的是"能否发现一条明显错误的
   命题"，而真实困难在于"命题只在极罕见的图上失效"。
2. 想按目标反例个数 $k$ 精确设定常数项。但九个不变量都取整数值，
   松弛量大量并列，阈值跳一格就从 1 个反例变成上万个
   （`runs/inject_20261121_143300` 里 $k=1$ 实际得到 23585 个）。
3. 改用"收紧到最小正松弛量处"，得到的仍是成百上千个反例
   （`runs/inject_20261121_143336`），因为多数形式在很多图上取等。

本模块的做法
------------
不再人为构造，改为**从数据中筛出天然的难例**：
在完整形式空间上逐条求解，保留那些在整个数据集上
**只有不超过 5 张图不成立、且这些图的阶数都不小于 9** 的形式。
这类形式正是真实场景中的困难情形——它在绝大多数图上成立，
只在少数大阶图上失效。

于是实验有了明确的问题：给定这样的命题，
三类搜索策略在多大预算内能找到那张反例图？

输出
----
runs/inject_<stamp>/summary.json
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import numpy as np
import pandas as pd

from .config import INVARIANTS, RUNS_DIR
from .core.counterexample import search_counterexample, tight_seed_graphs
from .core.forms import Form, _design_matrix, enumerate_forms, solve_form
from .core.split import split

# 难例的筛选条件
MAX_VIOL = 5        # 在整个数据集上最多这么多张图不成立
MIN_N = 9           # 且这些图的阶数不小于此值
MAX_FORMS = 30      # 最多取这么多条形式，控制运行时间
BUDGETS = [50, 100, 200, 400, 800, 1500, 3000]
STRATEGIES = ["random", "structured", "local"]


def find_hard_forms(df: pd.DataFrame, D: pd.DataFrame,
                    verbose: bool = True) -> list[dict]:
    """在完整形式空间中筛出"反例稀少且阶数大"的形式。"""
    out: list[dict] = []
    for f in enumerate_forms(targets=INVARIANTS, direction="le",
                             max_predictors=2):
        sol = solve_form(D, f)
        if sol is None:
            continue
        A = _design_matrix(df, f)
        # 注意：_design_matrix 已按 signs 带符号，故用不带符号的系数幅值
        a = np.array([sol.coefs[k] for k in f.predictors])
        slack = A @ a + sol.intercept - df[f.target].to_numpy(dtype=float)
        mask = slack < -1e-9
        k = int(mask.sum())
        if k == 0 or k > MAX_VIOL:
            continue
        n_min = int(df.loc[mask, "n"].min())
        if n_min < MIN_N:
            continue
        out.append({
            "id": f.key,
            "form_key": f.key,
            "target": f.target,
            "direction": f.direction,
            "predictors": list(f.predictors),
            "signs": list(f.signs),
            "coefs": {kk: float(v) for kk, v in sol.coefs.items()},
            "intercept": float(sol.intercept),
            "n_counterexamples": k,
            "min_n": n_min,
            "max_n": int(df.loc[mask, "n"].max()),
            "inequality": sol.inequality_str(),
        })
        if len(out) >= MAX_FORMS:
            break
    if verbose:
        print(f"[1] 筛出难例形式 {len(out)} 条"
              f"（反例 ≤ {MAX_VIOL} 张、阶数 ≥ {MIN_N}）")
        for it in out[:12]:
            print(f"    {it['id']:<26} 反例 {it['n_counterexamples']} 张"
                  f"  阶数 {it['min_n']}-{it['max_n']}"
                  f"  {it['inequality']}")
        if len(out) > 12:
            print(f"    …… 其余 {len(out) - 12} 条略")
    return out


def run(budgets=BUDGETS, strategies=STRATEGIES, n_rep: int = 3,
        seed: int = 0, verbose: bool = True) -> dict:
    """对每条难例形式、每种策略、每个预算各跑 n_rep 次，统计检出率。"""
    t0 = time.time()
    df = pd.read_csv(RUNS_DIR.parent / "data" / "dataset_all.csv")
    sp = split(df, seed=20261120)
    D, V = sp["D"], sp["V"]

    forms = find_hard_forms(df, D, verbose=verbose)
    if not forms:
        raise RuntimeError("没有找到符合条件的难例形式")

    records: list[dict] = []
    total = len(forms) * len(strategies) * len(budgets)
    done = 0
    for it in forms:
        # search_counterexample 的 coefs 必须带符号：
        # 它内部按 sum(c * inv) 计算，不另看 form.signs。
        signed = {k: s * c for k, s, c in
                  zip(it["coefs"].keys(), it["signs"], it["coefs"].values())}
        # 取等图种子：用同一形式重新求解，得到与验证集可比的常数项
        f = Form(it["target"], tuple(it["predictors"]), tuple(it["signs"]),
                 it["direction"])
        sol = solve_form(D, f)
        seeds = tight_seed_graphs(V, sol) if sol is not None else []

        for st in strategies:
            for budget in budgets:
                hits = 0
                used_sum = 0
                found_ns: list[int] = []
                for rep in range(n_rep):
                    r = search_counterexample(
                        signed, it["intercept"], it["direction"], it["target"],
                        strategy=st, budget=budget,
                        seed=seed + rep, tight_graphs=seeds)
                    used_sum += r.budget_used
                    if r.found:
                        hits += 1
                        found_ns.append(int(r.graph["n"]))
                done += 1
                records.append({
                    "id": it["id"], "strategy": st, "budget": budget,
                    "n_rep": n_rep, "hits": hits, "rate": hits / n_rep,
                    "mean_used": used_sum / n_rep,
                    "found_n": found_ns,
                    "k": it["n_counterexamples"],
                    "min_n_truth": it["min_n"],
                })
                if verbose and done % 30 == 0:
                    print(f"    {done}/{total}")

    # 汇总一：策略 × 预算
    table: dict[str, dict[int, float]] = {}
    for st in strategies:
        table[st] = {}
        for budget in budgets:
            rows = [r for r in records
                    if r["strategy"] == st and r["budget"] == budget]
            table[st][budget] = float(np.mean([r["rate"] for r in rows]))

    # 汇总二：按反例张数分档
    by_k: dict[int, dict] = {}
    for it in forms:
        rows = [r for r in records if r["id"] == it["id"]]
        by_k.setdefault(it["n_counterexamples"], {"rates": [], "props": []})
        by_k[it["n_counterexamples"]]["rates"].extend(r["rate"] for r in rows)
        by_k[it["n_counterexamples"]]["props"].append(it["id"])
    by_k = {k: {"rate": float(np.mean(v["rates"])), "n_props": len(v["props"])}
            for k, v in sorted(by_k.items())}

    out = {
        "stamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "budgets": list(budgets),
        "strategies": list(strategies),
        "n_rep": n_rep,
        "seed": seed,
        "max_viol": MAX_VIOL,
        "min_n": MIN_N,
        "n_forms": len(forms),
        "forms": forms,
        "rate_table": table,
        "rate_by_k": by_k,
        "elapsed": round(time.time() - t0, 1),
        "records": records,
    }

    d = RUNS_DIR / f"inject_{out['stamp']}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    if verbose:
        print(f"\n[2] 检出率（{n_rep} 次重复的均值），按策略 × 预算")
        print("    " + "预算".ljust(8) + "".join(s.ljust(12) for s in strategies))
        for budget in budgets:
            row = str(budget).ljust(10)
            for st in strategies:
                row += f"{table[st][budget]:.2f}".ljust(12)
            print("    " + row)

        print(f"\n[3] 检出率，按反例张数分档")
        for k, v in by_k.items():
            print(f"    反例 {k} 张（{v['n_props']} 条形式）"
                  f"  平均检出率 {v['rate']:.2f}")
        print(f"\n[4] 耗时 {out['elapsed']} 秒，结果写入 {d}")
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="注入假命题检验")
    ap.add_argument("--n-rep", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run(n_rep=args.n_rep, seed=args.seed)


if __name__ == "__main__":
    main()
