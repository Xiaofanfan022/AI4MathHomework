"""阶段三的图：接入模型后的运行结果与消融实验。

产出
----
fig11_agent_funnel.png   一次完整运行中候选的逐轮去留
fig12_ablation.png       模型提议与随机提议的对比
fig13_trace_timeline.png 运行轨迹中各阶段的实际调用序列

数据来源
--------
fig11、fig13 读取 `runs/` 下最新的 agent 运行；
fig12 读取 `runs/` 下最新的 ablation 运行。
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..config import FIG_DIR, RUNS_DIR
from .style import ACCENT, ACCENT_LIGHT, GRAY, GREEN, ORANGE, save


def _latest(pattern: str) -> Path:
    hits = sorted(glob.glob(str(RUNS_DIR / pattern)))
    if not hits:
        raise FileNotFoundError(f"没有找到运行目录：{pattern}")
    return Path(hits[-1])


# ---------------------------------------------------------------- 图 11
def fig11_agent_funnel() -> None:
    run = _latest("agent_*/result.json").parent
    res = json.loads((run / "result.json").read_text(encoding="utf-8"))

    stages = ["提出", "非平凡", "反驳后", "筛选后"]
    per_round = []
    for r in res["rounds"]:
        per_round.append([r["n_proposed"], r["n_solved"],
                          r["n_survived"], r["n_retained"]])

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.6),
                             gridspec_kw={"width_ratios": [1.35, 1]})

    ax = axes[0]
    x = np.arange(len(stages))
    n_rounds = len(per_round)
    width = 0.8 / max(n_rounds, 1)
    cmap = plt.get_cmap("Blues")
    colors = [cmap(0.35 + 0.5 * i / max(n_rounds - 1, 1))
              for i in range(n_rounds)]
    for i, row in enumerate(per_round):
        ax.bar(x + (i - (n_rounds - 1) / 2) * width, row, width,
               label=f"第 {i + 1} 轮", color=colors[i], alpha=0.92)
    ax.set_xticks(x)
    ax.set_xticklabels(stages)
    ax.set_ylabel("候选条数")
    ax.legend(frameon=False, ncol=n_rounds, loc="lower center",
              bbox_to_anchor=(0.5, 1.0), fontsize=8)
    ax.set_ylim(0, max(max(r) for r in per_round) * 1.15)

    # 右图：累计
    ax = axes[1]
    totals = [sum(r[i] for r in per_round) for i in range(4)]
    ax.barh(range(4)[::-1], totals, color=[ACCENT, ACCENT_LIGHT,
                                           ORANGE, GREEN], height=0.6)
    ax.set_yticks(range(4)[::-1])
    ax.set_yticklabels(stages)
    for i, v in enumerate(totals):
        ax.text(v + 0.6, 3 - i, str(v), va="center", fontsize=9)
    ax.set_xlabel("五轮累计条数")
    ax.set_xlim(0, max(totals) * 1.25)

    fig.tight_layout()
    save(fig, FIG_DIR / "fig11_agent_funnel.png")


# ---------------------------------------------------------------- 图 12
def fig12_ablation() -> None:
    run = _latest("ablation_*/summary.json").parent
    d = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    means = d["means"]

    labels = ["非平凡候选", "通过反驳", "通过筛选", "测试集成立"]
    keys = ["n_solved", "n_survived", "n_retained", "n_holds_T"]
    llm = [means[k]["llm"] for k in keys]
    rnd = [means[k]["random"] for k in keys]

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    x = np.arange(len(labels))
    w = 0.34
    b1 = ax.bar(x - w / 2, llm, w, label="模型提议", color=ACCENT)
    b2 = ax.bar(x + w / 2, rnd, w, label="随机提议", color=GRAY, alpha=0.85)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.22,
                    f"{b.get_height():.1f}", ha="center", va="bottom",
                    fontsize=8.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(f"条数（{d['seeds']} 次运行均值）")
    ax.legend(frameon=False)
    ax.set_ylim(0, max(rnd) * 1.28)

    fig.tight_layout()
    save(fig, FIG_DIR / "fig12_ablation.png")


# ---------------------------------------------------------------- 图 13
def fig13_trace_timeline() -> None:
    """每轮八条提议的去向：重复 / 恒真 / 新且非平凡。

    这张图要说明的问题：智能体的产出并非均匀，从第 2 轮起大部分提议
    都是前轮已经处理过的形式，真正的新内容逐轮减少。这是提示词只给
    "已推翻清单"、不给"已检验清单"时的直接后果。
    """
    run = _latest("agent_*/trace.jsonl").parent
    recs = [json.loads(ln) for ln in
            (run / "trace.jsonl").read_text(encoding="utf-8").splitlines()
            if ln.strip()]

    by_round: dict[int, dict] = {}
    for r in recs:
        if r.get("stage") == "propose":
            by_round.setdefault(r["round"], {})["n_prop"] = r["n_forms"]
        elif r.get("stage") == "solve":
            d = by_round.setdefault(r["round"], {})
            d["n_repeat"] = r.get("n_repeat", 0)
            d["n_trivial"] = r.get("n_trivial", 0)
            d["n_new"] = r.get("n_solved", 0)

    rounds = sorted(by_round)
    n_prop = [by_round[r].get("n_prop", 0) for r in rounds]
    n_rep = [by_round[r].get("n_repeat", 0) for r in rounds]
    n_tri = [by_round[r].get("n_trivial", 0) for r in rounds]
    n_new = [by_round[r].get("n_new", 0) for r in rounds]
    # 线性规划不可行的形式既不重复也不恒真，单独成一类，
    # 否则堆叠柱的总高度会低于提议数，读者会以为漏算。
    n_bad = [n_prop[i] - n_new[i] - n_tri[i] - n_rep[i]
             for i in range(len(rounds))]

    fig, ax = plt.subplots(figsize=(7.4, 3.3))
    x = np.arange(len(rounds))
    ax.bar(x, n_new, 0.55, label="新且非平凡", color=ACCENT)
    ax.bar(x, n_tri, 0.55, bottom=n_new, label="恒真式", color=ORANGE)
    ax.bar(x, n_rep, 0.55, bottom=np.array(n_new) + np.array(n_tri),
           label="与前轮重复", color=GRAY, alpha=0.75)
    ax.bar(x, n_bad, 0.55,
           bottom=np.array(n_new) + np.array(n_tri) + np.array(n_rep),
           label="不可行", color="#D9D9D9", edgecolor="white", linewidth=0.5)

    for i in range(len(rounds)):
        ax.text(x[i], n_prop[i] + 0.2, f"{n_prop[i]}", ha="center",
                va="bottom", fontsize=8.5)

    ax.set_xticks(x)
    ax.set_xticklabels([f"第 {r} 轮" for r in rounds])
    ax.set_ylabel("提议条数")
    ax.set_ylim(0, max(n_prop) * 1.22)
    ax.legend(frameon=False, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, 1.16), fontsize=8.5)

    fig.tight_layout()
    save(fig, FIG_DIR / "fig13_trace_timeline.png")


def main() -> None:
    print("生成阶段三的图")
    fig11_agent_funnel()
    fig12_ablation()
    fig13_trace_timeline()


if __name__ == "__main__":
    main()
