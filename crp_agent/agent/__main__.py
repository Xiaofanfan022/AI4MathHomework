"""CRP-Agent 命令行入口。

用法
----
    python -m crp_agent.agent.loop --dry-run          # 只检查数据，不调用模型
    python -m crp_agent.agent.loop --rounds 3         # 运行三轮
"""

from __future__ import annotations

import argparse

from .loop import main


def cli() -> None:
    ap = argparse.ArgumentParser(description="CRP-Agent")
    ap.add_argument("--dry-run", action="store_true",
                    help="不调用模型，仅检查数据与轨迹目录")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--budget", type=int, default=1500)
    args = ap.parse_args()

    main(dry_run=args.dry_run, max_rounds=args.rounds,
         n_perm=args.n_perm, budget=args.budget)


if __name__ == "__main__":
    cli()
