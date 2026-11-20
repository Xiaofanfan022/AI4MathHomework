"""阶段二可视化。

产出
----
fig06_lp_recovery.png        LP 能否重新发现已知结论
fig07_refute_curve.png       反例搜索：策略与预算的效果
fig08_pvalue_hist.png        p 值分布与 BH 保留结果
fig09_tight_vs_holdout.png   取等比例与测试集表现
fig10_form_space.png         形式复杂度与过拟合

数据来源
--------
图 6、7、10 现场计算；图 8、9 读取最近一次运行的结果文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..config import DATA_DIR, FIG_DIR, RUNS_DIR
from ..core.counterexample import search_counterexample
from ..core.forms import Form, dedup, enumerate_forms, search, solve_form
from ..core.split import split
from ..core.stats import min_slack, tight_ratio
from .style import ACCENT, ACCENT_LIGHT, GRAY, GREEN, ORANGE, save


# ---------------------------------------------------------------- 图 6
def fig_lp_recovery(df: pd.DataFrame, out: Path) -> None:
    """已知结论在数据上的取等比例。

    取等比例衡量一条结论"有多紧"。取等比例高说明它在
    大量图上恰好触到边界，因而是一个值得被自动发现的候选。
    """
    D = df[df["n"] <= 8]

    cases = [
        (r"$\chi \leq n-\alpha+1$", Form("chi", ("alpha", "n"), (-1, 1))),
        (r"$\chi \leq \Delta+1$（Brooks）", Form("chi", ("Delta",), (1,))),
        (r"$\chi \leq \omega+1$", Form("chi", ("omega",), (1,))),
        (r"$\alpha \leq n-\omega+1$", Form("alpha", ("omega", "n"), (-1, 1))),
        (r"$\chi \leq (\omega+\Delta+1)/2$", Form("chi", ("omega", "Delta"), (1, 1))),
    ]

    labels, ratios = [], []
    for name, f in cases:
        s = solve_form(D, f)
        labels.append(name)
        ratios.append(s.tight_ratio if s else 0.0)

    fig, ax = plt.subplots(figsize=(8.0, 3.4))
    y = np.arange(len(labels))
    ax.barh(y, ratios, color=ACCENT, height=0.62)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlabel("取等比例（$n \\leq 8$ 的全部 13598 张图）")
    ax.set_xlim(0, max(ratios) * 1.3)
    for yi, r in zip(y, ratios):
        ax.text(r + max(ratios) * 0.025, yi, f"{r*100:.1f}%",
                va="center", fontsize=9, color=GRAY)
    ax.grid(axis="x", alpha=0.3)
    ax.set_title("已知结论在数据上的紧度")
    save(fig, out)


# ---------------------------------------------------------------- 图 7
def fig_refute_curve(out: Path) -> None:
    """三种策略找到反例所需的代价。

    横轴是对数尺度的"评估图数"，越靠左越省算力。
    圆点表示 10 次试验的中位数；若某策略在 2000 张图内从未成功，
    在该行右侧标注"未找到"。
    """
    candidates = [
        (r"$\chi \leq \omega+1$", {"omega": 1.0}, 1.0),
        (r"$\chi \leq \Delta$", {"Delta": 1.0}, 0.0),
        (r"$\alpha+\omega \leq n$", {"omega": -1.0, "n": 1.0}, 0.0),
    ]
    strategies = ["random", "structured", "local"]
    colors = {"random": GRAY, "structured": ACCENT, "local": ORANGE}
    names = {"random": "随机图", "structured": "结构化族", "local": "局部修改"}
    budget = 2000
    trials = 10

    fig, ax = plt.subplots(figsize=(8.6, 4.4))

    yticks, ylabels = [], []
    for i, (title, coefs, b) in enumerate(candidates):
        for j, strat in enumerate(strategies):
            y = i * 4 + j
            used = []
            for t in range(trials):
                r = search_counterexample(
                    coefs, b, "le", "chi", strategy=strat,
                    budget=budget, n_lo=3, n_hi=12, seed=7919 * t + 13)
                if r.found:
                    used.append(r.budget_used)

            if used:
                med = float(np.median(used))
                ax.scatter(med, y, s=95, color=colors[strat],
                           zorder=3, edgecolor="white", linewidth=1.2)
                ax.text(med * 1.18, y, f"{int(med)}", va="center",
                        fontsize=8, color=GRAY)
            else:
                ax.text(budget * 1.18, y, "未找到", va="center",
                        fontsize=8, color=ORANGE)

            yticks.append(y)
            ylabels.append(names[strat])

        # 候选标题放在该组上方
        ax.text(0.015, i * 4 - 0.85, title,
                transform=ax.get_yaxis_transform(),
                ha="left", va="center", fontsize=10)

    ax.set_yticks(yticks, ylabels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlim(0.8, budget * 3.5)
    ax.set_ylim(len(candidates) * 4 - 0.3, -1.4)
    ax.set_xlabel("找到反例时已评估的图数（中位数，对数尺度）")
    ax.grid(axis="x", alpha=0.3)
    ax.set_title("反例搜索：策略决定代价")
    save(fig, out)


# ---------------------------------------------------------------- 图 8
def fig_pvalue(out: Path) -> None:
    """最近一次基线的 p 值分布与保留情况。"""
    runs = sorted(RUNS_DIR.glob("2026*"))
    path = None
    for r in reversed(runs):
        p = r / "candidates.jsonl"
        if p.exists():
            path = p
            break
    if path is None:
        print("  跳过 fig08：没有找到运行结果")
        return

    rows = [json.loads(ln) for ln in open(path, encoding="utf-8")]
    ps = np.array([r["p_value"] for r in rows])
    kept = np.array([r["retained"] for r in rows])
    m = len(ps)

    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.6))

    ax = axes[0]
    bins = np.linspace(0, 1, 21)
    ax.hist([ps[~kept], ps[kept]], bins=bins, stacked=True,
            color=[GRAY, ACCENT], label=["未保留", "保留"],
            edgecolor="white", linewidth=0.6)
    ax.set_xlabel("p 值")
    ax.set_ylabel("候选数")
    ax.legend(frameon=False)
    ax.set_title(f"p 值分布（{m} 条候选）")

    # BH 阈值曲线
    ax = axes[1]
    order = np.argsort(ps)
    ranks = np.arange(1, m + 1)
    ax.plot(ranks, np.sort(ps), "o", color=ACCENT, markersize=5,
            label="排序后的 p 值")
    ax.plot(ranks, ranks / m * 0.1, "--", color=ORANGE,
            label=r"BH 阈值 $iq/m$（$q=0.1$）")
    ax.set_xlabel("秩 $i$")
    ax.set_ylabel("p 值")
    ax.legend(frameon=False)
    ax.set_title("BH 过程")
    ax.grid(alpha=0.3)

    fig.tight_layout()
    save(fig, out)


# ---------------------------------------------------------------- 图 9
def fig_boundary(df: pd.DataFrame, out: Path) -> None:
    """小阶成立不等于普遍成立。

    左：在每一阶上，chi - omega - 1 的最大值。
        前若干阶恒为 -1 或 0，说明 chi <= omega+1 在那些阶上成立；
        某一阶起出现正值，该阶即出现反例。
    右：反例本身（Grötzsch 图），无三角形但色数为 4。
    """
    d = df.copy()
    d["gap"] = d["chi"] - d["omega"] - 1
    g = d.groupby("n")["gap"].max()

    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.9),
                             gridspec_kw={"width_ratios": [1.35, 1]})

    # ---- 左：逐阶最大超出量
    ax = axes[0]
    ns = g.index.to_numpy()
    vals = g.to_numpy()

    ax.fill_between(ns, -2, 0, color=ACCENT, alpha=0.07)
    ax.plot(ns, vals, "-", color=ACCENT, linewidth=1.3, zorder=2)
    ax.scatter(ns, vals, s=48, zorder=3,
               color=[ORANGE if v > 0 else ACCENT for v in vals],
               edgecolor="white", linewidth=1.2)

    for n, v in zip(ns, vals):
        if v > 0:
            ax.annotate(f"首次出现反例 $n={n}$", xy=(n, v),
                        xytext=(n - 5.6, v + 0.28),
                        fontsize=8.5, color=ORANGE, va="center",
                        arrowprops=dict(arrowstyle="->", color=ORANGE,
                                        linewidth=1))

    ax.axhline(0, color=GRAY, linewidth=1)
    ax.set_xlabel("图的阶数 $n$")
    ax.set_ylabel(r"$\max(\chi-\omega-1)$")
    ax.set_ylim(-1.55, max(vals) + 0.62)
    ax.set_xlim(0.4, ns.max() + 0.6)
    ax.set_xticks(ns)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title(r"$\chi \leq \omega+1$ 在每一阶上的最大超出量")

    # ---- 右：反例
    ax = axes[1]
    import networkx as nx
    G = nx.Graph()
    G.add_nodes_from(range(11))
    G.add_edges_from([
        (0, 1), (0, 4), (0, 6), (0, 9), (1, 2), (1, 5), (1, 7),
        (2, 3), (2, 6), (2, 8), (3, 4), (3, 7), (3, 9), (4, 5), (4, 8),
        (5, 10), (6, 10), (7, 10), (8, 10), (9, 10)])
    pos = nx.spring_layout(G, seed=4)
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color=GRAY, width=1.2)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=ACCENT,
                           node_size=230, edgecolors="white", linewidths=1.2)
    nx.draw_networkx_labels(G, pos, ax=ax, font_color="white",
                            font_size=7)
    ax.set_axis_off()
    ax.set_title("Grötzsch 图：$\\omega=2$，$\\chi=4$")

    fig.tight_layout()
    save(fig, out)


# ---------------------------------------------------------------- 图 10
def fig_form_funnel(D: pd.DataFrame, V: pd.DataFrame, T: pd.DataFrame,
               out: Path, cache: Path) -> None:
    """候选的逐级淘汰。

    这条漏斗是整篇报告的中心图：形式空间很大，
    但真正能通过全部检验的极少，且每一级淘汰的原因不同。
    """
    import json as _json

    if cache.exists():
        counts = _json.loads(cache.read_text(encoding="utf-8"))
    else:
        forms = enumerate_forms(targets=["chi"], max_predictors=2)
        sols = [s for s in search(D, forms, min_tight_ratio=0.0002,
                                  progress_every=0) if not s.trivial]
        n_nontrivial = len(sols)
        sols = dedup(sols)
        n_dedup = len(sols)

        from ..core.stats import bh_filter, permutation_pvalues
        cands = permutation_pvalues(D, V, sols, n_perm=200, seed=20261120,
                                    verbose=False)
        cands = bh_filter(cands, q=0.1)
        n_retained = sum(1 for c in cands if c.retained)
        n_hold = sum(1 for c in cands
                     if c.retained and min_slack(T, c.solution) >= -1e-9)

        counts = {
            "枚举的形式": len(forms),
            "求得非平凡解": n_nontrivial,
            "去重后": n_dedup,
            "通过置换检验": n_retained,
            "测试集上成立": n_hold,
        }
        cache.write_text(_json.dumps(counts, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    labels = list(counts.keys())
    vals = [counts[k] for k in labels]

    fig, ax = plt.subplots(figsize=(8.4, 4.0))
    y = np.arange(len(labels))
    colors = [ACCENT_LIGHT, ACCENT_LIGHT, ACCENT, ACCENT, GREEN]
    ax.barh(y, vals, color=colors, height=0.62)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlim(0.8, max(vals) * 2.2)

    for yi, v in zip(y, vals):
        ax.text(v * 1.12, yi, str(v), va="center", fontsize=9.5, color=GRAY)

    # 每一级的淘汰数
    for i in range(1, len(vals)):
        drop = vals[i - 1] - vals[i]
        ax.text(max(vals) * 1.55, i - 0.5, f"−{drop}", va="center",
                fontsize=8.5, color=ORANGE)

    ax.set_xlabel("候选数（对数尺度）")
    ax.grid(axis="x", alpha=0.3)
    ax.set_title("候选的逐级淘汰")
    save(fig, out)


# ---------------------------------------------------------------- 入口
def main() -> None:
    df = pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")
    parts = split(df, seed=20261120)
    D, V, T = parts["D"], parts["V"], parts["T"]

    print("生成阶段二图表…")
    fig_lp_recovery(df, FIG_DIR / "fig06_lp_recovery.png")
    print("  fig06 完成")
    fig_refute_curve(FIG_DIR / "fig07_refute_curve.png")
    print("  fig07 完成")
    fig_pvalue(FIG_DIR / "fig08_pvalue_hist.png")
    print("  fig08 完成")
    fig_boundary(df, FIG_DIR / "fig09_boundary.png")
    print("  fig09 完成")
    fig_form_funnel(D, V, T, FIG_DIR / "fig10_funnel.png",
                    FIG_DIR / ".funnel_cache.json")
    print("  fig10 完成")


if __name__ == "__main__":
    main()
