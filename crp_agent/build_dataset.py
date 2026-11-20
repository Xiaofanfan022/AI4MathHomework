"""阶段一：构建不变量数据集。

用法
----
    python -m crp_agent.build_dataset              # 完整构建（约 3 分钟）
    python -m crp_agent.build_dataset --quick      # 只到 n=7，用于快速调试

输出
----
    crp_agent/data/dataset_exhaustive.csv   n <= 8 的全部非同构图
    crp_agent/data/dataset_sampled.csv      n = 9..12 的采样图
    crp_agent/data/dataset_all.csv          两者合并，含 source 列
    crp_agent/data/dataset_meta.json        构建参数与统计
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from .config import (CACHE_DIR, DATA_DIR, EXHAUSTIVE_MAX_N, INVARIANTS,
                     SAMPLE_PER_N, SAMPLE_P, SAMPLED_N, SEED)
from .core.graphgen import (canon_key, enumerate_all_graphs, sample_random,
                            sample_structured)
from .core.invariants import compute_all


def _edges_to_str(edges) -> str:
    return ";".join(f"{u}-{v}" for u, v in edges)


def _row(n: int, edges, source: str, graph_id: str) -> dict:
    inv = compute_all(n, edges)
    row = {"graph_id": graph_id, "source": source}
    row.update({k: inv[k] for k in INVARIANTS})
    row["edges"] = _edges_to_str(edges)
    return row


def build_exhaustive(n_max: int, verbose: bool = True) -> pd.DataFrame:
    t0 = time.time()
    by_n = enumerate_all_graphs(n_max)

    rows = []
    for n in sorted(by_n):
        for idx, (_, edges) in enumerate(by_n[n]):
            rows.append(_row(n, edges, "exhaustive", f"e{n}_{idx:06d}"))
        if verbose:
            print(f"  n={n}: {len(by_n[n])} 张，累计 {len(rows)}，"
                  f"耗时 {time.time()-t0:.1f}s")

    df = pd.DataFrame(rows)
    return df.sort_values(["n", "m", "graph_id"]).reset_index(drop=True)


def build_sampled(n_list, per_n: int, seed: int, verbose: bool = True) -> pd.DataFrame:
    t0 = time.time()
    rnd = sample_random(n_list, per_n, SAMPLE_P, seed=seed)
    stc = sample_structured(n_list, seed=seed)

    seen: set[tuple] = set()
    uniq: list[tuple] = []
    for item in rnd + stc:
        key = (item[0], canon_key(*item))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)

    rows = []
    for idx, (n, edges) in enumerate(uniq):
        src = "sampled_struct" if idx >= len(rnd) else "sampled_random"
        rows.append(_row(n, edges, src, f"s{idx:06d}"))
        if verbose and idx and idx % 2000 == 0:
            print(f"  {idx}/{len(uniq)}，耗时 {time.time()-t0:.1f}s")

    df = pd.DataFrame(rows)
    if verbose:
        print(f"  采样共 {len(df)} 张，耗时 {time.time()-t0:.1f}s")
    return df.sort_values(["n", "m", "graph_id"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="只枚举到 n=7")
    ap.add_argument("--n-max", type=int, default=EXHAUSTIVE_MAX_N)
    ap.add_argument("--per-n", type=int, default=SAMPLE_PER_N)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--no-sampled", action="store_true")
    args = ap.parse_args()

    n_max = 7 if args.quick else args.n_max

    print("=" * 60)
    print("阶段一：构建不变量数据集")
    print("=" * 60)

    print(f"\n[1/3] 完全枚举 n <= {n_max}")
    df_ex = build_exhaustive(n_max)

    frames = [df_ex]
    if not args.no_sampled and not args.quick:
        print(f"\n[2/3] 采样 n = {list(SAMPLED_N)}")
        df_sa = build_sampled(list(SAMPLED_N), args.per_n, args.seed)
        df_sa.to_csv(DATA_DIR / "dataset_sampled.csv", index=False, encoding="utf-8-sig")
        frames.append(df_sa)
    else:
        print("\n[2/3] 跳过采样")

    print("\n[3/3] 写出文件")
    df_ex.to_csv(DATA_DIR / "dataset_exhaustive.csv", index=False, encoding="utf-8-sig")

    df_all = pd.concat(frames, ignore_index=True)
    df_all.to_csv(DATA_DIR / "dataset_all.csv", index=False, encoding="utf-8-sig")

    meta = {
        "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "invariants": INVARIANTS,
        "n_max_exhaustive": n_max,
        "sampled_n": [] if (args.quick or args.no_sampled) else list(SAMPLED_N),
        "sample_p": SAMPLE_P,
        "seed": args.seed,
        "counts": {
            "exhaustive": int(len(df_ex)),
            "all": int(len(df_all)),
        },
        "by_n": {int(k): int(v) for k, v in
                 df_all.groupby("n").size().items()},
    }
    with open(DATA_DIR / "dataset_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n完成：exhaustive {len(df_ex)} 张，all {len(df_all)} 张")
    print(f"输出目录：{DATA_DIR}")
    print("\n按阶数分布：")
    for k, v in sorted(meta["by_n"].items()):
        print(f"  n={k:2d}: {v:6d}")


if __name__ == "__main__":
    main()
