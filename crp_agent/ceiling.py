"""形式上界分析：智能体离"穷举能拿到的最好结果"有多远。

动机
----
智能体五轮共提出约 40 条形式，保留 4 条。但这不能说明它做得好还是不好，
因为不知道**同一形式空间里究竟有多少条能通过全部检验**。如果穷举也只剩
四五条，那智能体已经接近上限；如果穷举能留下几十条，那智能体漏掉了很多。

做法
----
对完整形式空间（目标 × 预测子组合 × 符号，max_predictors=2）逐条求解，
施加与智能体完全相同的四道关卡：

    1. 非平凡     线性规划不把全部系数压成 0
    2. 有信息量   不被 base_facts 中任一基本事实处处支配
    3. 无反例     在验证集 V 上成立（智能体用搜索，这里直接查 V）
    4. 通过筛选   置换检验 p 值，BH 校正

第 3 关是两者的差别所在：智能体只能用有限预算搜索反例，这里可以直接
在 V 上判定。因此本实验给出的是**上界**，智能体不可能超过它。

用法
----
    python -m crp_agent.ceiling                 # 默认 max_predictors=2
    python -m crp_agent.ceiling --max-pred 3 --n-perm 1000
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from .config import DATA_DIR, RUNS_DIR
from .core.forms import dedup, enumerate_forms, rank, solve_form
from .core.informativeness import label
from .core.split import split
from .core.stats import bh_filter, min_slack, permutation_pvalues


def run(max_pred: int = 2, n_perm: int = 200, q: float = 0.1,
        verbose: bool = True) -> dict:
    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    parts = split(df, seed=20261120)
    D, V, T = parts["D"], parts["V"], parts["T"]

    forms = enumerate_forms(targets=["n", "m", "Delta", "delta", "alpha",
                                     "omega", "chi", "nu", "rho"],
                            direction="le", max_predictors=max_pred)
    forms += enumerate_forms(targets=["n", "m", "Delta", "delta", "alpha",
                                      "omega", "chi", "nu", "rho"],
                             direction="ge", max_predictors=max_pred)
    if verbose:
        print(f"形式空间：{len(forms)} 条（max_predictors={max_pred}，双向）")

    # ---- 第 1 关：非平凡
    t0 = time.time()
    sols = []
    for i, f in enumerate(forms, 1):
        s = solve_form(D, f)
        if s is not None and not s.trivial:
            sols.append(s)
        if verbose and i % 500 == 0:
            print(f"  求解 {i}/{len(forms)}，非平凡 {len(sols)}")
    n_nontrivial = len(sols)
    if verbose:
        print(f"[1] 非平凡：{n_nontrivial}（{time.time() - t0:.1f}s）")

    # 不同形式可能拟出同一条不等式，去重后再统计
    sols = dedup(rank(sols))
    n_unique = len(sols)
    if verbose:
        print(f"    去重后：{n_unique}")

    # ---- 第 2 关：有信息量
    sols = [s for s in sols if label(D, s)["informative"]]
    n_informative = len(sols)
    if verbose:
        print(f"[2] 有信息量：{n_informative}")

    # ---- 第 3 关：在 V 上无反例（智能体此处靠搜索，这里是上界）
    sols = [s for s in sols if min_slack(V, s) >= -1e-9]
    n_no_ce = len(sols)
    if verbose:
        print(f"[3] V 上无反例：{n_no_ce}")

    # ---- 第 4 关：置换检验 + BH
    # 同时记录"不校正"与"BH 校正"两种判定，用于比较校正环节的作用。
    # 不校正的阈值取 0.05，这是最常见的做法。
    cands = permutation_pvalues(D, V, sols, n_perm=n_perm,
                                seed=20261120, verbose=False)
    bh_filter(cands, q=q)

    def _rows(selected):
        out = []
        for c in selected:
            ms = min_slack(T, c.solution)
            out.append({
                "inequality": c.solution.inequality_str(),
                "form_key": c.solution.form.key,
                "target": c.solution.form.target,
                "direction": c.solution.form.direction,
                "tight_ratio_V": round(c.tight_ratio, 6),
                "p_value": round(c.p_value, 6),
                "min_slack_T": round(ms, 8),
                "holds_on_T": bool(ms >= -1e-9),
            })
        out.sort(key=lambda r: -r["tight_ratio_V"])
        return out

    rows_bh = _rows([c for c in cands if c.retained])
    rows_unc = _rows([c for c in cands if c.p_value <= 0.05])

    if verbose:
        print(f"[4] 不校正(p<=0.05) 保留 {len(rows_unc)} 条，"
              f"其中测试集失败 {sum(1 for r in rows_unc if not r['holds_on_T'])} 条")
        print(f"    BH(q={q}) 保留 {len(rows_bh)} 条，"
              f"其中测试集失败 {sum(1 for r in rows_bh if not r['holds_on_T'])} 条")

    rows = rows_bh
    n_hold = sum(1 for r in rows if r["holds_on_T"])
    out = {
        "max_predictors": max_pred,
        "n_perm": n_perm,
        "q": q,
        "n_forms": len(forms),
        "n_nontrivial": n_nontrivial,
        "n_unique": n_unique,
        "n_informative": n_informative,
        "n_no_counterexample_on_V": n_no_ce,
        "n_retained": len(rows_bh),
        "n_holds_on_T": n_hold,
        "retained": rows_bh,
        "uncorrected": {
            "threshold": 0.05,
            "n_retained": len(rows_unc),
            "n_holds_on_T": sum(1 for r in rows_unc if r["holds_on_T"]),
            "retained": rows_unc,
        },
    }

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / f"ceiling_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    if verbose:
        print(f"\n结果已保存到 {out_dir}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pred", type=int, default=2)
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--q", type=float, default=0.1)
    args = ap.parse_args()

    print("=" * 66)
    print("形式上界分析")
    print("=" * 66)
    out = run(max_pred=args.max_pred, n_perm=args.n_perm, q=args.q)

    print("\n" + "=" * 66)
    print("汇总")
    print("=" * 66)
    print(f"{'形式总数':22s}{out['n_forms']:>8d}")
    print(f"{'非平凡':22s}{out['n_nontrivial']:>8d}")
    print(f"{'去重后':22s}{out['n_unique']:>8d}")
    print(f"{'有信息量':22s}{out['n_informative']:>8d}")
    print(f"{'V 上无反例':22s}{out['n_no_counterexample_on_V']:>8d}")
    print(f"{'不校正 p<=0.05':22s}{out['uncorrected']['n_retained']:>8d}"
          f"   （测试集失败 {out['uncorrected']['n_retained'] - out['uncorrected']['n_holds_on_T']} 条）")
    print(f"{'BH 校正后':22s}{out['n_retained']:>8d}"
          f"   （测试集失败 {out['n_retained'] - out['n_holds_on_T']} 条）")

    print(f"\nBH 校正保留的 {len(out['retained'])} 条，按取等比例排序：")
    for r in out["retained"][:40]:
        flag = "✓" if r["holds_on_T"] else "✗"
        print(f"  {flag} {r['inequality']:48s} "
              f"tight={r['tight_ratio_V']:.4f} p={r['p_value']:.4f}")

    missed = [r for r in out["uncorrected"]["retained"]
              if r["inequality"] not in {x["inequality"] for x in out["retained"]}]
    if missed:
        print(f"\n仅通过不校正、被 BH 淘汰的 {len(missed)} 条中，"
              f"测试集失败的：")
        for r in missed:
            if not r["holds_on_T"]:
                print(f"  ✗ {r['inequality']:48s} "
                      f"tight={r['tight_ratio_V']:.4f} p={r['p_value']:.4f}")


if __name__ == "__main__":
    main()
