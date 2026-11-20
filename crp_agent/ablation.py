"""消融实验：模型提议 vs 随机提议。

问题
----
智能体里的"提出候选形式"一步由大语言模型完成。必须回答：
若把模型换成从同一形式空间中均匀随机抽样，结果会差多少？
若两者无差别，则模型在这一步没有贡献，应当如实报告。

设计
----
两个实验组共用全部其他环节（线性规划求解、反例搜索、置换检验、BH 校正），
唯一差别是候选形式的来源：

    模型组  由大语言模型依据数据摘要提出
    随机组  从同一形式空间（目标 × 预测子集 × 符号组合）中均匀抽样

为控制预算公平，两组每轮提出的形式数相同，反例搜索的预算也相同。
每组重复若干次（不同随机种子），比较四个指标的均值：

    非平凡候选数    线性规划求解后未被判为平凡的形式数
    通过反驳数      反例搜索未能推翻的候选数
    通过筛选数      置换检验 + BH 校正后保留的候选数
    测试集成立数    在从未参与拟合与筛选的测试集上仍然成立的候选数

用法
----
    python -m crp_agent.ablation --seeds 3 --rounds 4
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, INVARIANTS, RUNS_DIR
from .core.counterexample import search_counterexample
from .core.forms import (Form, dedup, enumerate_forms, rank, solve_form)
from .core.informativeness import label
from .core.split import split
from .core.stats import (bh_filter, min_slack, permutation_pvalues,
                         summarize)
from .agent.llm import LLMClient
from .agent.loop import data_summary, parse_forms
from .agent.prompts import SYSTEM_PROPOSE, propose_user_prompt


def _sample_random_forms(rng: random.Random, k: int,
                         space: list[Form]) -> list[Form]:
    """从形式空间中无放回地抽 k 个。"""
    k = min(k, len(space))
    return rng.sample(space, k)


def _evaluate(forms: list[Form], D: pd.DataFrame, V: pd.DataFrame,
              T: pd.DataFrame, *, budget: int, n_perm: int, q: float,
              seed: int) -> dict:
    """对一批形式跑完整的求解—反驳—筛选流程。

    恒真式（由定义直接成立的界）在求解后立即剔除，与智能体的实际
    流程一致；否则两组都会被恒真式灌水，比较失去意义。
    """
    sols = []
    for f in forms:
        s = solve_form(D, f)
        if s is None or s.trivial:
            continue
        sols.append(s)
    sols = dedup(rank(sols))
    sols = [s for s in sols if label(D, s)["informative"]]
    n_solved = len(sols)

    survived = []
    for i, s in enumerate(sols):
        sr = search_counterexample(
            s.signed_coefs(), s.intercept, s.form.direction, s.form.target,
            strategy="structured", budget=budget, n_lo=3, n_hi=12,
            seed=seed * 1000 + i)
        if not sr.found:
            survived.append(s)

    n_survived = len(survived)
    n_retained = n_hold = 0
    kept_names: list[str] = []
    if survived:
        tested = permutation_pvalues(D, V, survived, n_perm=n_perm,
                                     seed=seed, verbose=False)
        tested = bh_filter(tested, q=q)
        kept = [c for c in tested if c.retained]
        n_retained = len(kept)
        n_hold = sum(1 for c in kept if min_slack(T, c.solution) >= -1e-9)
        kept_names = [c.solution.inequality_str() for c in kept]

    return {
        "n_forms": len(forms),
        "n_solved": n_solved,
        "n_survived": n_survived,
        "n_retained": n_retained,
        "n_holds_T": n_hold,
        "retained": kept_names,
    }


def run(seeds: int = 3, rounds: int = 4, budget: int = 1500,
        n_perm: int = 200, q: float = 0.1) -> None:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / f"ablation_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    parts = split(df, seed=20261120)
    D, V, T = parts["D"], parts["V"], parts["T"]

    space = enumerate_forms(targets=INVARIANTS, direction="le",
                            max_predictors=2)
    space += enumerate_forms(targets=INVARIANTS, direction="ge",
                             max_predictors=2)
    print(f"形式空间大小：{len(space)}")

    llm = LLMClient()
    print(f"模型：{llm.cfg.model}")
    summary = data_summary(D)
    known = ["chi + alpha <= n + 1",
             "chi <= Delta + 1（Brooks 定理）",
             "alpha + omega <= n + 1"]

    records = []
    for seed in range(1, seeds + 1):
        print(f"\n===== 种子 {seed} =====")

        # ---- 模型组：每轮独立提问，累积全部提议
        llm_forms: list[Form] = []
        for r in range(1, rounds + 1):
            user = propose_user_prompt(summary, known,
                                       [f.key for f in llm_forms], r)
            raw = llm.chat_json(SYSTEM_PROPOSE, user)
            got = parse_forms(raw, list(INVARIANTS))
            llm_forms.extend(got)
            print(f"  模型 第{r}轮：{len(got)} 条")
        print(f"  模型组共 {len(llm_forms)} 条，开始评估")
        a = _evaluate(llm_forms, D, V, T, budget=budget, n_perm=n_perm,
                      q=q, seed=seed)
        print(f"  模型组：{a['n_solved']} 求解 / {a['n_survived']} 存活"
              f" / {a['n_retained']} 保留 / {a['n_holds_T']} 测试集成立")

        # ---- 随机组：同一数量，均匀抽样
        rng = random.Random(10007 * seed)
        rnd_forms = _sample_random_forms(rng, len(llm_forms), space)
        print(f"  随机组共 {len(rnd_forms)} 条，开始评估")
        b = _evaluate(rnd_forms, D, V, T, budget=budget, n_perm=n_perm,
                      q=q, seed=seed)
        print(f"  随机组：{b['n_solved']} 求解 / {b['n_survived']} 存活"
              f" / {b['n_retained']} 保留 / {b['n_holds_T']} 测试集成立")

        records.append({"seed": seed, "llm": a, "random": b})

    # ---------------- 汇总
    def mean(key: str, arm: str) -> float:
        return sum(r[arm][key] for r in records) / len(records)

    summary_out = {
        "stamp": stamp,
        "model": llm.cfg.model,
        "seeds": seeds, "rounds": rounds, "budget": budget,
        "n_perm": n_perm, "q": q,
        "form_space": len(space),
        "usage": llm.usage,
        "means": {
            key: {"llm": round(mean(key, "llm"), 3),
                  "random": round(mean(key, "random"), 3)}
            for key in ("n_forms", "n_solved", "n_survived",
                        "n_retained", "n_holds_T")
        },
        "records": records,
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary_out, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("汇总（各指标均值）")
    print("=" * 60)
    print(f"{'指标':<14}{'模型组':>10}{'随机组':>10}")
    for k, lbl in [("n_solved", "非平凡候选"), ("n_survived", "通过反驳"),
                   ("n_retained", "通过筛选"),
                   ("n_holds_T", "测试集成立")]:
        v = summary_out["means"][k]
        print(f"{lbl:<14}{v['llm']:>10.2f}{v['random']:>10.2f}")
    print(f"\n结果已保存到 {out_dir}")


def cli() -> None:
    ap = argparse.ArgumentParser(description="消融实验")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--budget", type=int, default=1500)
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--q", type=float, default=0.1)
    a = ap.parse_args()
    run(seeds=a.seeds, rounds=a.rounds, budget=a.budget,
        n_perm=a.n_perm, q=a.q)


if __name__ == "__main__":
    cli()
