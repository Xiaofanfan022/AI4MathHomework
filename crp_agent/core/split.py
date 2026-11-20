"""数据集划分。

三类用途
--------
D (discovery)  用于拟合系数、提出候选
V (validation) 用于计算违反裕度与 p 值
T (test)       仅在最终报告时使用，用于估计被保留候选的真实有效率

划分按阶数分层，保证三个集合的阶数分布一致；
同一张图只会出现在一个集合中。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def split(df: pd.DataFrame, frac=(0.5, 0.25, 0.25), seed: int = 0,
          stratify_by: str = "n") -> dict[str, pd.DataFrame]:
    """按阶数分层随机划分为 D / V / T。"""
    assert abs(sum(frac) - 1.0) < 1e-9
    rng = np.random.default_rng(seed)

    parts = {"D": [], "V": [], "T": []}
    for _, grp in df.groupby(stratify_by):
        idx = rng.permutation(len(grp))
        n1 = int(round(len(grp) * frac[0]))
        n2 = int(round(len(grp) * (frac[0] + frac[1])))
        parts["D"].append(grp.iloc[idx[:n1]])
        parts["V"].append(grp.iloc[idx[n1:n2]])
        parts["T"].append(grp.iloc[idx[n2:]])

    return {k: pd.concat(v).reset_index(drop=True) for k, v in parts.items()}
