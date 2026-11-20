"""绘图公共设置。"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

# 中文字体：按可用性依次尝试
_CJK_CANDIDATES = ["Microsoft YaHei", "SimHei", "Source Han Serif SC",
                   "SimSun", "FangSong"]

plt.rcParams.update({
    "font.sans-serif": _CJK_CANDIDATES + ["DejaVu Sans"],
    "font.family": "sans-serif",
    "axes.unicode_minus": False,
    "figure.dpi": 150,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 9,
})

# 配色：与报告正文的深蓝一致
ACCENT = "#14508C"
ACCENT_LIGHT = "#5B9BD5"
ORANGE = "#E07B39"
GREEN = "#3C8C5A"
GRAY = "#8C8C8C"


def save(fig, path) -> None:
    fig.savefig(path)
    plt.close(fig)
    print(f"  已保存 {path}")
