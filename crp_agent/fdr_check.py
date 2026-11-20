"""筛选环节的对照实验：不做多重检验校正会怎样。

思路
----
判断一条候选是否"无效"需要标准答案。真实数据上没有标准答案，
因此本实验换一个角度：构造一份**安慰剂数据**。

具体做法是把目标列（色数）在整份数据上随机置换。置换之后，
色数与其余八个不变量之间不再有任何关联，任何在这份数据上
"成立"的候选都必然是假发现。于是：

    安慰剂数据上保留的条数 = 假发现的条数

在同一批候选上分别用三种判定方式保留：

    (a) 不校正：p <= 0.05 即保留
    (b) BH 校正：q = 0.1
    (c) BH 校正：q = 0.2

比较三者保留的条数，即可看出校正环节的作用。

另一个副产品
------------
置换次数 B 决定了 p 值能取到的最小值 1/(B+1)。
BH 要求存在 i 使 p_(i) <= i/m * q，故 B 次置换下
只有当候选数 m <= (B+1)q 时才有可能保留任何候选。
B=200、q=0.1 时这一上限是 20。基线运行的 m=17 恰好落在边界内，
若候选再多一些，BH 将一条也保留不了。这一点在结果中一并报告。

用法
----
    python -m crp_agent.fdr_check                 # 3 组种子
    python -m crp_agent.fdr_check --seeds 1 --n-perm 200
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from .config import DATA_DIR, RUNS_DIR
from .core.forms import dedup, enumerate_forms, rank, search
from .core.split import split
from .core.stats import bh_filter, permutation_pvalues

TARGET = "chi"


def _retained_counts(cands, thresholds=(0.05,)) -> dict:
    """不校正时各阈值下保留的条数。"""
    return {f"uncorrected_{a:g}": sum(1 for c in cands if c.p_value <= a)
            for a in thresholds}


def run_placebo(df: pd.DataFrame, seed: int, n_perm: int,
                max_pred: int = 2, top_k: int = 80,
                min_tight: float = 0.0) -> dict:
    """在目标列被置换的数据上跑一遍完整流程。"""
    rng = np.random.default_rng(seed)
    fake = df.copy()
    fake[TARGET] = rng.permutation(fake[TARGET].to_numpy())

    parts = split(fake, seed=20261120)
    D, V = parts["D"], parts["V"]

    forms = enumerate_forms(targets=[TARGET], direction="le",
                            max_predictors=max_pred)
    sols = search(D, forms, min_tight_ratio=min_tight)
    sols = dedup(rank(sols))[:top_k]
    if not sols:
        return {"seed": seed, "n_solved": 0, "n_tested": 0,
                "uncorrected_0.05": 0, "bh_q0.1": 0, "bh_q0.2": 0}

    cands = permutation_pvalues(D, V, sols, n_perm=n_perm,
                               seed=seed, verbose=False)
    out = {"seed": seed, "n_solved": len(sols), "n_tested": len(cands)}
    out.update(_retained_counts(cands))

    for q, key in ((0.1, "bh_q0.1"), (0.2, "bh_q0.2")):
        marked = bh_filter([c for c in cands], q=q)
        out[key] = sum(1 for c in marked if c.retained)
    return out


def real_counts(n_perm: int = 200, max_pred: int = 2, top_k: int = 80,
                min_tight: float = 0.0002) -> dict:
    """在真实数据上做同样的计数，供对照。"""
    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    parts = split(df, seed=20261120)
    D, V = parts["D"], parts["V"]

    forms = enumerate_forms(targets=[TARGET], direction="le",
                            max_predictors=max_pred)
    sols = search(D, forms, min_tight_ratio=min_tight)
    sols = dedup(rank(sols))[:top_k]

    cands = permutation_pvalues(D, V, sols, n_perm=n_perm,
                                seed=20261120, verbose=False)
    out = {"n_solved": len(sols), "n_tested": len(cands)}
    out.update(_retained_counts(cands))
    for q, key in ((0.1, "bh_q0.1"), (0.2, "bh_q0.2")):
        marked = bh_filter([c for c in cands], q=q)
        out[key] = sum(1 for c in marked if c.retained)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--max-pred", type=int, default=2)
    ap.add_argument("--top-k", type=int, default=80)
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / f"fdr_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print("筛选环节的对照实验：安慰剂数据上的假发现")
    print("=" * 66)
    print(f"置换次数 B={args.n_perm}，p 值下限 1/(B+1)={1/(args.n_perm+1):.4f}")
    print(f"BH(q) 能保留候选的前提：候选数 m <= (B+1)q = "
          f"{(args.n_perm + 1) * 0.1:.1f}（q=0.1）")

    records = []
    for s in range(args.seeds):
        print(f"\n[安慰剂 {s + 1}/{args.seeds}] 置换目标列，种子 {s}")
        r = run_placebo(df=_load(), seed=s, n_perm=args.n_perm,
                        max_pred=args.max_pred, top_k=args.top_k)
        print(f"  求解 {r['n_solved']} 条，进入筛选 {r['n_tested']} 条"
              f"；不校正保留 {r['uncorrected_0.05']} 条"
              f"，BH(q=0.1) 保留 {r['bh_q0.1']} 条")
        records.append(r)

    print("\n[真实数据] 同一流程，供对照")
    real = real_counts(n_perm=args.n_perm, max_pred=args.max_pred,
                       top_k=args.top_k)
    print(f"  求解 {real['n_solved']} 条，进入筛选 {real['n_tested']} 条"
          f"；不校正保留 {real['uncorrected_0.05']} 条"
          f"，BH(q=0.1) 保留 {real['bh_q0.1']} 条")

    def mean(key: str) -> float:
        vals = [r[key] for r in records if key in r]
        return float(np.mean(vals)) if vals else 0.0

    summary = {
        "stamp": stamp,
        "n_perm": args.n_perm,
        "p_floor": round(1 / (args.n_perm + 1), 6),
        "bh_m_limit_q0.1": round((args.n_perm + 1) * 0.1, 1),
        "placebo": {
            "n_seeds": args.seeds,
            "mean_n_solved": round(mean("n_solved"), 2),
            "mean_n_tested": round(mean("n_tested"), 2),
            "mean_uncorrected": round(mean("uncorrected_0.05"), 2),
            "mean_bh_q0.1": round(mean("bh_q0.1"), 2),
            "mean_bh_q0.2": round(mean("bh_q0.2"), 2),
            "records": records,
        },
        "real": real,
    }

    print("\n" + "=" * 66)
    print("汇总")
    print("=" * 66)
    print(f"{'':16s}{'安慰剂（均值）':>14s}{'真实数据':>12s}")
    print(f"{'进入筛选的候选':16s}{summary['placebo']['mean_n_tested']:>14.2f}"
          f"{real['n_tested']:>12d}")
    print(f"{'不校正 p<=0.05':16s}{summary['placebo']['mean_uncorrected']:>14.2f}"
          f"{real['uncorrected_0.05']:>12d}")
    print(f"{'BH q=0.1':16s}{summary['placebo']['mean_bh_q0.1']:>14.2f}"
          f"{real['bh_q0.1']:>12d}")
    print(f"{'BH q=0.2':16s}{summary['placebo']['mean_bh_q0.2']:>14.2f}"
          f"{real['bh_q0.2']:>12d}")

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到 {out_dir}")


def _load() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")


if __name__ == "__main__":
    main()
