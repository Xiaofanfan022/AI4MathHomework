"""统计筛选。

问题
----
同时检验 m 条候选时，即使每条候选都为真，
也会有若干条仅因偶然因素在数据上"恰好成立"。
需要把"在多少张图上成立"转换为统计意义上的可信程度，
并控制最终保留集合中无效命题的比例。

统计量
------
对候选 j，定义其在验证集 V 上的取等比例

    T_j = #{G in V : |右侧 - 左侧| <= tol} / |V|

T_j 越大，说明该不等式在未见过的图上不仅成立，而且频繁取等，
即它刻画的是一个真实的结构性等式，而非一条松垮的平凡界。

零分布
------
候选的内容是"形式 + 系数"。若形式与目标之间没有真实关联，
则把发现集 D 中的目标列随机置换后重新拟合，
再把得到的系数用在未经置换的 V 上，应当得到一个明显更差的 T。

注意拟合与评估必须分离：在 V 上重新拟合会让系数迁就 V，
使零分布与观测值不可比。因此置换只作用于 D，
V 始终保持原样。

p 值
----
    p_j = (1 + #{T~_b >= T_j}) / (B + 1)

方向说明：T 越大越好，故计数用 >=。若写成 <=，
p 值会随 T 增大而增大，BH 将优先保留最可疑的候选。

多重检验
--------
Benjamini-Hochberg 控制 FDR：
    k = max{ i : p_(i) <= i/m * q }
保留前 k 条。候选间存在正相关时改用 Benjamini-Yekutieli。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .forms import Form, Solution, solve_form

# 判定取等的相对容差
TIGHT_TOL = 1e-6


@dataclass
class TestedCandidate:
    solution: Solution
    tight_ratio: float
    p_value: float
    rank: int = 0
    retained: bool = False

    def to_dict(self) -> dict:
        d = self.solution.to_dict()
        d.update({
            "tight_ratio_V": round(self.tight_ratio, 6),
            "p_value": round(self.p_value, 6),
            "rank": self.rank,
            "retained": self.retained,
        })
        return d


# ---------------------------------------------------------------- 统计量
def slacks(df: pd.DataFrame, sol: Solution) -> np.ndarray:
    """不等式在每张图上的松弛量，>= 0 表示成立。"""
    A = np.column_stack([
        sg * df[name].to_numpy(dtype=float)
        for name, sg in zip(sol.form.predictors, sol.form.signs)
    ])
    pred = A @ np.array(list(sol.coefs.values())) + sol.intercept
    t = df[sol.form.target].to_numpy(dtype=float)
    return pred - t if sol.form.direction == "le" else t - pred


def tight_ratio(df: pd.DataFrame, sol: Solution) -> float:
    """取等比例。"""
    if len(df) == 0:
        return 0.0
    s = slacks(df, sol)
    scale = max(np.abs(df[sol.form.target].to_numpy(dtype=float)).max(), 1.0)
    return float(np.mean(np.abs(s) <= TIGHT_TOL * scale))


def min_slack(df: pd.DataFrame, sol: Solution) -> float:
    """最小松弛量，< 0 表示在 df 上存在反例。"""
    return float(slacks(df, sol).min())


# ---------------------------------------------------------------- 零分布
def null_tight_ratios(D: pd.DataFrame, V: pd.DataFrame, form: Form,
                      n_perm: int = 200, seed: int = 0) -> np.ndarray:
    """置换 D 的目标列后重新拟合，在 V 上计算取等比例。"""
    rng = np.random.default_rng(seed)
    out = np.full(n_perm, -1.0)

    t_orig = D[form.target].to_numpy(dtype=float)
    work = D.copy()

    for b in range(n_perm):
        work[form.target] = rng.permutation(t_orig)
        sol = solve_form(work, form)
        if sol is None or sol.trivial:
            continue
        out[b] = tight_ratio(V, sol)

    return out


def permutation_pvalues(D: pd.DataFrame, V: pd.DataFrame,
                        sols: list[Solution], n_perm: int = 200,
                        seed: int = 0,
                        verbose: bool = True) -> list[TestedCandidate]:
    """对每条候选计算取等比例与 p 值。

    同一形式共享零分布，按形式缓存。
    """
    cache: dict[str, np.ndarray] = {}
    out: list[TestedCandidate] = []

    for i, sol in enumerate(sols, 1):
        key = sol.form.key
        if key not in cache:
            cache[key] = null_tight_ratios(D, V, sol.form,
                                           n_perm=n_perm, seed=seed)
        null = cache[key]

        tr = tight_ratio(V, sol)
        p = (1 + int(np.sum(null >= tr))) / (len(null) + 1)
        out.append(TestedCandidate(sol, tr, float(p)))

        if verbose and i % 50 == 0:
            print(f"    {i}/{len(sols)}，已计算 {len(cache)} 个零分布")

    return out


# ---------------------------------------------------------------- 多重检验
def bh_filter(cands: list[TestedCandidate],
              q: float = 0.1) -> list[TestedCandidate]:
    """Benjamini-Hochberg。返回全部候选，但标记 retained。"""
    m = len(cands)
    if m == 0:
        return []

    order = sorted(range(m), key=lambda i: cands[i].p_value)
    k = 0
    for rank, idx in enumerate(order, 1):
        if cands[idx].p_value <= rank / m * q:
            k = rank

    for rank, idx in enumerate(order, 1):
        cands[idx].rank = rank
        cands[idx].retained = rank <= k

    return cands


def by_filter(cands: list[TestedCandidate],
              q: float = 0.1) -> list[TestedCandidate]:
    """Benjamini-Yekutieli：任意相关结构下控制 FDR，代价是更保守。"""
    m = len(cands)
    if m == 0:
        return []
    c_m = float(np.sum(1.0 / np.arange(1, m + 1)))

    order = sorted(range(m), key=lambda i: cands[i].p_value)
    k = 0
    for rank, idx in enumerate(order, 1):
        if cands[idx].p_value <= rank / (m * c_m) * q:
            k = rank

    for rank, idx in enumerate(order, 1):
        cands[idx].rank = rank
        cands[idx].retained = rank <= k

    return cands


def summarize(cands: list[TestedCandidate]) -> dict:
    m = len(cands)
    ret = [c for c in cands if c.retained]
    return {
        "n_candidates": m,
        "n_retained": len(ret),
        "retention_rate": round(len(ret) / m, 4) if m else 0.0,
        "min_p": round(min((c.p_value for c in cands), default=1.0), 6),
        "median_p": round(float(np.median([c.p_value for c in cands]))
                          if m else 1.0, 6),
    }
