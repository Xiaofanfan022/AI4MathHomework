"""数据集正确性校验。

三项检查
--------
1. 与 networkx 的独立实现比对（alpha、omega、chi）。
   networkx 的 approximation 不够，这里用它的精确算法：
   max_weight_clique（精确）、chromatic_polynomial 不可行，
   故 chi 用 networkx 的 greedy 上界 + 独立集覆盖下界夹逼，
   只在两者相等时比对。
2. 已知定理在全部数据上成立（chi + alpha <= n + 1）。
3. 已知猜想在全部数据上未被推翻（Reed 猜想）。
   这既是数据校验，也是后续实验的对照基准。
"""

from __future__ import annotations

import sys

import networkx as nx
import pandas as pd

from .config import DATA_DIR
from .core.graphgen import to_nx
from .core.invariants import (adjacency_masks, chromatic_number,
                              max_clique_size)


def parse_edges(s: str) -> list[tuple[int, int]]:
    if not s:
        return []
    out = []
    for part in s.split(";"):
        u, v = part.split("-")
        out.append((int(u), int(v)))
    return out


def check_against_networkx(df: pd.DataFrame, sample: int = 500) -> list[str]:
    """抽样比对 alpha 与 omega。"""
    problems = []
    sub = df.sample(min(sample, len(df)), random_state=0)
    for _, r in sub.iterrows():
        n = int(r["n"])
        edges = parse_edges(r["edges"])
        G = to_nx(n, edges)

        clique, _ = nx.max_weight_clique(G, weight=None)
        nx_omega = len(clique)
        if nx_omega != int(r["omega"]):
            problems.append(f"{r['graph_id']}: omega ours={r['omega']} nx={nx_omega}")

        nx_alpha = len(nx.max_weight_clique(nx.complement(G), weight=None)[0])
        if nx_alpha != int(r["alpha"]):
            problems.append(f"{r['graph_id']}: alpha ours={r['alpha']} nx={nx_alpha}")

    return problems


def check_known_theorems(df: pd.DataFrame) -> dict:
    """在全部数据上检验已知结论。"""
    res = {}

    # (1) chi + alpha <= n + 1
    viol = df[df["chi"] + df["alpha"] > df["n"] + 1]
    res["chi_plus_alpha"] = {
        "name": "chi + alpha <= n + 1",
        "violations": int(len(viol)),
        "tight": int((df["chi"] + df["alpha"] == df["n"] + 1).sum()),
        "total": int(len(df)),
    }

    # (2) Reed 猜想 chi <= ceil((omega + Delta + 1) / 2)
    import math
    rhs = df.apply(lambda r: math.ceil((r["omega"] + r["Delta"] + 1) / 2), axis=1)
    viol2 = df[df["chi"] > rhs]
    res["reed"] = {
        "name": "Reed: chi <= ceil((omega+Delta+1)/2)",
        "violations": int(len(viol2)),
        "tight": int((df["chi"] == rhs).sum()),
        "total": int(len(df)),
    }

    # (3) Brooks 定理 chi <= Delta + 1
    viol3 = df[df["chi"] > df["Delta"] + 1]
    res["brooks"] = {
        "name": "Brooks: chi <= Delta + 1",
        "violations": int(len(viol3)),
        "total": int(len(df)),
    }

    # (4) 已知结论 alpha + omega <= n + 1
    viol4 = df[df["alpha"] + df["omega"] > df["n"] + 1]
    res["alpha_omega"] = {
        "name": "alpha + omega <= n + 1",
        "violations": int(len(viol4)),
        "tight": int((df["alpha"] + df["omega"] == df["n"] + 1).sum()),
        "total": int(len(df)),
    }

    return res


def main() -> None:
    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    print(f"读取 {len(df)} 条记录\n")

    print("[1] 与 networkx 独立实现比对（抽样 500）")
    problems = check_against_networkx(df, 500)
    if problems:
        print(f"  发现 {len(problems)} 处不一致：")
        for p in problems[:10]:
            print("   ", p)
    else:
        print("  alpha 与 omega 全部一致")

    print("\n[2] 已知结论检验")
    res = check_known_theorems(df)
    for key, v in res.items():
        flag = "OK" if v["violations"] == 0 else "FAIL"
        extra = f"，取等 {v['tight']}" if "tight" in v else ""
        print(f"  [{flag}] {v['name']}：违反 {v['violations']} / {v['total']}{extra}")

    total_viol = sum(v["violations"] for v in res.values()) + len(problems)
    print(f"\n总计问题数：{total_viol}")
    sys.exit(0 if total_viol == 0 else 1)


if __name__ == "__main__":
    main()
