"""阶段二：形式搜索 + 系数求解 + 统计筛选（不调用大模型）。

这是智能体的"确定性骨架"：完整跑通 生成 → 筛选 两步，
先把不带 LLM 的基线做出来，后续再用它作消融对照。

用法
----
    python -m crp_agent.run_baseline                 # 默认配置
    python -m crp_agent.run_baseline --max-pred 2    # 只用到二元形式
    python -m crp_agent.run_baseline --quick         # 小规模，用于调试

输出
----
    crp_agent/runs/<timestamp>/
        config.json          本次运行的参数
        candidates.jsonl     每条候选一行
        retained.jsonl       经 BH 筛选后保留的候选
        summary.json         统计摘要
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, RUNS_DIR
from .core.forms import dedup, enumerate_forms, rank, search, solve_form
from .core.split import split
from .core.stats import (bh_filter, by_filter, min_slack,
                         permutation_pvalues, summarize)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", default=["chi"])
    ap.add_argument("--direction", default="le", choices=["le", "ge"])
    ap.add_argument("--max-pred", type=int, default=2)
    ap.add_argument("--min-tight", type=float, default=0.005,
                    help="取等比例下限，低于此值的形式直接丢弃")
    ap.add_argument("--top-k", type=int, default=120,
                    help="进入统计筛选的候选数")
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--q", type=float, default=0.1)
    ap.add_argument("--method", default="bh", choices=["bh", "by"])
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print("阶段二：形式搜索与统计筛选")
    print("=" * 66)

    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    if args.quick:
        df = df[df["n"] <= 7]
    parts = split(df, seed=20261120)
    D, V, T = parts["D"], parts["V"], parts["T"]
    print(f"\n数据划分：D={len(D)}  V={len(V)}  T={len(T)}")

    # ---------------- 生成
    forms = enumerate_forms(targets=args.targets, direction=args.direction,
                            max_predictors=args.max_pred)
    print(f"\n[1/4] 枚举形式：{len(forms)} 个")

    print(f"[2/4] 在 D 上求解系数（取等比例下限 {args.min_tight}）")
    t0 = time.time()
    sols = search(D, forms, min_tight_ratio=args.min_tight)
    print(f"  得到 {len(sols)} 条非平凡候选，耗时 {time.time()-t0:.1f}s")

    sols = dedup(rank(sols))
    print(f"  去重后 {len(sols)} 条，取前 {min(args.top_k, len(sols))} 条进入筛选")
    sols = sols[:args.top_k]

    # ---------------- 筛选
    print(f"[3/4] 置换检验（{args.n_perm} 次置换）")
    t0 = time.time()
    cands = permutation_pvalues(D, V, sols, n_perm=args.n_perm, seed=20261120)
    print(f"  耗时 {time.time()-t0:.1f}s")

    filt = bh_filter if args.method == "bh" else by_filter
    cands = filt(cands, q=args.q)
    summ = summarize(cands)
    print(f"  BH(q={args.q})：保留 {summ['n_retained']}/{summ['n_candidates']}"
          f"，最小 p={summ['min_p']}")

    # ---------------- 测试集复核
    print("[4/4] 在测试集 T 上复核保留的候选")
    rows = []
    for c in cands:
        r = c.to_dict()
        r["min_slack_T"] = round(min_slack(T, c.solution), 8)
        r["holds_on_T"] = bool(r["min_slack_T"] >= -1e-9)
        rows.append(r)

    retained = [r for r in rows if r["retained"]]
    still = [r for r in retained if r["holds_on_T"]]
    print(f"  保留的 {len(retained)} 条中，{len(still)} 条在 T 上仍成立")

    # ---------------- 落盘
    write_jsonl(out_dir / "candidates.jsonl", rows)
    write_jsonl(out_dir / "retained.jsonl", retained)

    config = {
        "stamp": stamp,
        "args": vars(args),
        "data": {"n_D": len(D), "n_V": len(V), "n_T": len(T),
                 "n_total": len(df)},
        "summary": {**summ,
                    "n_retained_holds_T": len(still),
                    "elapsed_total": round(time.time() - t0, 2)},
    }
    with open(out_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到 {out_dir}")
    print("\n保留的前 10 条：")
    for r in retained[:10]:
        flag = "T✓" if r["holds_on_T"] else "T✗"
        print(f"  [{flag}] p={r['p_value']:.4f}  {r['inequality']}")


if __name__ == "__main__":
    main()
