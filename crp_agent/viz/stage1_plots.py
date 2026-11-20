"""阶段一的可视化：数据集的整体面貌。

产出五张图，均可直接放入汇报幻灯片：

    fig01_invariant_dist.png    各不变量的分布（按阶数分层）
    fig02_reed_scatter.png      Reed 猜想的松弛量散点
    fig03_corr_heatmap.png      不变量之间的 Spearman 相关
    fig04_equality_ratio.png    已知结论的取等比例随阶数变化
    fig05_sample_graphs.png     若干典型图及其不变量

用法
----
    python -m crp_agent.viz.stage1_plots
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..config import DATA_DIR, FIG_DIR, INVARIANT_CN, INVARIANTS
from ..core.graphgen import to_nx
from .style import ACCENT, ACCENT_LIGHT, GRAY, GREEN, ORANGE, plt, save


def load() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "dataset_all.csv", encoding="utf-8-sig")


# ---------------------------------------------------------------- 图 1
def fig_distributions(df: pd.DataFrame) -> None:
    """每个不变量一张小图，按阶数着色的直方图。

    纵轴用组内比例而非绝对数量：n=8 有 12346 张图，
    绝对数量会完全压过其他阶数。
    """
    keys = ["alpha", "omega", "chi", "Delta", "nu"]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6))
    axes = axes.ravel()

    ns = sorted(df["n"].unique())
    cmap = plt.get_cmap("viridis")

    for ax, key in zip(axes, keys):
        lo = int(df[key].min())
        hi = int(df[key].max())
        bins = np.arange(lo - 0.5, hi + 1.5)
        for i, n in enumerate(ns):
            sub = df[df["n"] == n][key]
            if sub.empty:
                continue
            weights = np.ones(len(sub)) / len(sub)
            ax.hist(sub, bins=bins, weights=weights, histtype="step",
                    linewidth=1.3, color=cmap(i / max(len(ns) - 1, 1)),
                    label=f"n={n}")
        ax.set_title(INVARIANT_CN[key])
        ax.set_xlabel(key)
        ax.set_ylabel("组内比例")

    axes[-1].axis("off")
    handles, labels = axes[0].get_legend_handles_labels()
    axes[-1].legend(handles, labels, ncol=2, frameon=False, loc="center")
    fig.suptitle("各不变量在数据集中的分布（纵轴为同阶图内的比例）", y=0.99)
    fig.tight_layout()
    save(fig, FIG_DIR / "fig01_invariant_dist.png")


# ---------------------------------------------------------------- 图 2
def fig_reed_scatter(df: pd.DataFrame) -> None:
    """Reed 猜想的松弛量。

    横轴为 omega，纵轴为 chi，颜色表示 Delta。
    虚线为 Reed 上界 ceil((omega+Delta+1)/2) 的等值线不易画，
    改为画 chi 与上界之差对 omega 的散点，更直接。
    """
    d = df.copy()
    d["reed_rhs"] = d.apply(
        lambda r: math.ceil((r["omega"] + r["Delta"] + 1) / 2), axis=1)
    d["slack"] = d["reed_rhs"] - d["chi"]

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4))

    ax = axes[0]
    # 二维计数热图：整数格点上散点会严重重叠，改用计数
    from matplotlib.colors import LogNorm
    om_max = int(d["omega"].max())
    ch_max = int(d["chi"].max())
    grid = np.zeros((ch_max + 1, om_max + 1), dtype=int)
    for om, ch in zip(d["omega"], d["chi"]):
        grid[int(ch), int(om)] += 1
    masked = np.ma.masked_where(grid == 0, grid)
    im = ax.imshow(masked, origin="lower", cmap="Blues", norm=LogNorm(),
                   extent=(-0.5, om_max + 0.5, -0.5, ch_max + 0.5),
                   aspect="equal")
    lim = max(om_max, ch_max) + 1
    ax.plot([0, lim], [0, lim], color=ORANGE, lw=1.2, ls="--",
            label=r"$\chi=\omega$")
    ax.set_xlim(-0.5, lim - 0.5)
    ax.set_ylim(-0.5, lim - 0.5)
    ax.set_xlabel(r"团数 $\omega$")
    ax.set_ylabel(r"色数 $\chi$")
    ax.set_title("色数与团数的联合分布（对数色阶）")
    ax.legend(frameon=False, loc="upper left")
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.046, label="图数")

    ax = axes[1]
    counts = d["slack"].value_counts().sort_index()
    ax.bar(counts.index, counts.values, color=ACCENT, width=0.7)
    for x, y in zip(counts.index, counts.values):
        if y > len(d) * 0.02:
            ax.text(x, y, f"{y}", ha="center", va="bottom", fontsize=7)
    ax.set_xlabel("Reed 上界与色数之差")
    ax.set_ylabel("图数")
    ax.set_title(f"Reed 猜想的松弛量（0 处 {int((d['slack']==0).sum())} 张取等）")

    fig.tight_layout()
    save(fig, FIG_DIR / "fig02_reed_scatter.png")


# ---------------------------------------------------------------- 图 3
def fig_correlation(df: pd.DataFrame) -> None:
    cols = INVARIANTS
    corr = df[cols].corr(method="spearman")

    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels([INVARIANT_CN[c] for c in cols], rotation=45, ha="right")
    ax.set_yticklabels([INVARIANT_CN[c] for c in cols])
    for i in range(len(cols)):
        for j in range(len(cols)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=7, color="white" if abs(v) > 0.6 else "black")
    ax.set_title("不变量之间的 Spearman 相关系数")
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.046, label="相关系数")
    fig.tight_layout()
    save(fig, FIG_DIR / "fig03_corr_heatmap.png")


# ---------------------------------------------------------------- 图 4
def fig_equality_ratio(df: pd.DataFrame) -> None:
    """已知结论在各阶上的取等比例。

    取等意味着该结论在此阶上是紧的，也是"候选是否值得进一步研究"
    的一个天然指标。
    """
    d = df.copy()
    d["reed_rhs"] = d.apply(
        lambda r: math.ceil((r["omega"] + r["Delta"] + 1) / 2), axis=1)
    d["eq_chi_alpha"] = (d["chi"] + d["alpha"] == d["n"] + 1)
    d["eq_reed"] = (d["chi"] == d["reed_rhs"])
    d["eq_brooks"] = (d["chi"] == d["Delta"] + 1)

    g = d.groupby("n")[["eq_chi_alpha", "eq_reed", "eq_brooks"]].mean()

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for col, label, color, marker in [
        ("eq_chi_alpha", r"$\chi+\alpha=n+1$", ACCENT, "o"),
        ("eq_reed", "Reed 上界取等", ORANGE, "s"),
        ("eq_brooks", r"Brooks 界 $\chi=\Delta+1$", GREEN, "^"),
    ]:
        ax.plot(g.index, g[col] * 100, marker=marker, color=color,
                label=label, lw=1.6, ms=4.5)
    ax.set_xlabel("阶数 n")
    ax.set_ylabel("取等的图所占比例（%）")
    ax.set_title("已知结论的取等比例随阶数的变化")
    ax.set_xticks(sorted(d["n"].unique()))
    ax.legend(frameon=False)
    fig.tight_layout()
    save(fig, FIG_DIR / "fig04_equality_ratio.png")


# ---------------------------------------------------------------- 图 5
def fig_sample_graphs(df: pd.DataFrame) -> None:
    """展示若干典型图及其不变量。

    图直接由 networkx 构造后重标号，再调用 compute_all 求值，
    不依赖在 CSV 里按条件检索（检索条件容易选中同名但结构不同的图）。
    """
    import networkx as nx

    from ..core.invariants import compute_all

    specs = [
        ("完全图 $K_6$", nx.complete_graph(6)),
        ("空图 $\\overline{K_6}$", nx.empty_graph(6)),
        ("圈 $C_6$", nx.cycle_graph(6)),
        ("Petersen 图", nx.petersen_graph()),
        ("完全二部图 $K_{4,4}$", nx.complete_bipartite_graph(4, 4)),
        ("完全三部图 $K_{2,2,2}$", nx.complete_multipartite_graph(2, 2, 2)),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(11, 6.6))
    for ax, (title, G0) in zip(axes.ravel(), specs):
        G = nx.convert_node_labels_to_integers(G0, first_label=0)
        n = G.number_of_nodes()
        edges = sorted(tuple(sorted(e)) for e in G.edges())
        inv = compute_all(n, edges)

        pos = nx.circular_layout(G)
        nx.draw_networkx_edges(G, pos, ax=ax, edge_color=GRAY, width=0.9)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=ACCENT_LIGHT,
                               node_size=110, edgecolors=ACCENT, linewidths=0.8)
        ax.set_aspect("equal")
        ax.margins(0.16)
        ax.axis("off")
        ax.set_title(title, fontsize=9.5)
        info = (f"$n$={inv['n']}  $m$={inv['m']}  "
                f"$\\alpha$={inv['alpha']}  $\\omega$={inv['omega']}  "
                f"$\\chi$={inv['chi']}  $\\Delta$={inv['Delta']}")
        ax.text(0.5, -0.02, info, transform=ax.transAxes,
                ha="center", va="top", fontsize=8, color="#333333")

    fig.suptitle("数据集中的典型图及其不变量", y=0.99)
    fig.tight_layout()
    save(fig, FIG_DIR / "fig05_sample_graphs.png")


def _parse(s: str) -> list[tuple[int, int]]:
    if not isinstance(s, str) or not s:
        return []
    return [tuple(map(int, p.split("-"))) for p in s.split(";")]


def nx_layout(G, n: int):
    import networkx as nx
    if n <= 8:
        return nx.circular_layout(G)
    return nx.spring_layout(G, seed=0, k=0.9)


# ---------------------------------------------------------------- main
def main() -> None:
    print("=" * 60)
    print("阶段一可视化")
    print("=" * 60)
    df = load()
    print(f"读取 {len(df)} 条记录\n")

    print("[1/5] 不变量分布")
    fig_distributions(df)
    print("[2/5] Reed 猜想散点")
    fig_reed_scatter(df)
    print("[3/5] 相关性热图")
    fig_correlation(df)
    print("[4/5] 取等比例")
    fig_equality_ratio(df)
    print("[5/5] 典型图")
    fig_sample_graphs(df)

    print(f"\n全部图表已输出到 {FIG_DIR}")


if __name__ == "__main__":
    main()
