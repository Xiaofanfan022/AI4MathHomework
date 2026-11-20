"""猜想的形式空间与系数求解。

一条候选猜想写成

        sum_j a_j * sigma_j * f_j(G) + b   <=   t(G)          (direction = "le")
        sum_j a_j * sigma_j * f_j(G) + b   >=   t(G)          (direction = "ge")

其中 t 是目标不变量，S = {f_j} 是参与的不变量集合，sigma_j ∈ {+1,-1}
是符号，a_j >= 0 与 b 由线性规划确定，不由大语言模型给出。

求解分两步
----------
LP-A（强度）：在全部约束成立的条件下，把界推到最紧。
    direction = "le" 时最小化 b，direction = "ge" 时最大化 b。
LP-B（贴合）：固定 b 为最优值，最小化总松弛量，
    使不等式在尽可能多的图上取等。

两步都是标准线性规划，用 scipy.optimize.linprog 求解。
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from ..config import INVARIANTS

# 数值容差：判定"取等"时使用相对容差
TOL = 1e-7

# 系数上界，防止无界解
COEF_MAX = 50.0


@dataclass(frozen=True)
class Form:
    """一个候选形式，尚未确定系数。"""

    target: str
    predictors: tuple[str, ...]
    signs: tuple[int, ...]
    direction: str = "le"      # "le": t <= ...; "ge": t >= ...

    def __post_init__(self):
        assert self.direction in ("le", "ge")
        assert len(self.predictors) == len(self.signs)

    @property
    def key(self) -> str:
        s = ",".join(f"{'+' if g > 0 else '-'}{p}" for p, g in
                     zip(self.predictors, self.signs))
        return f"{self.target} {self.direction} [{s}]"

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "predictors": list(self.predictors),
            "signs": list(self.signs),
            "direction": self.direction,
        }


@dataclass
class Solution:
    """LP 求出的具体不等式。"""

    form: Form
    coefs: dict[str, float]
    intercept: float
    n_tight: int
    n_total: int
    mean_slack: float
    trivial: bool
    status: str

    @property
    def tight_ratio(self) -> float:
        return self.n_tight / self.n_total if self.n_total else 0.0

    def inequality_str(self, digits: int = 3) -> str:
        """人类可读的不等式，目标在左侧。

        系数 a_j 恒为非负，符号由 signs 决定，这里显式写进表达式。
        """
        parts = []
        for (name, sg), a in zip(zip(self.form.predictors, self.form.signs),
                                 self.coefs.values()):
            if abs(a) < 1e-9:
                continue
            parts.append(f"{sg * a:.{digits}g}*{name}")
        rhs = " + ".join(parts) if parts else "0"
        if abs(self.intercept) > 1e-9:
            rhs += f" + {self.intercept:.{digits}g}"
        op = "<=" if self.form.direction == "le" else ">="
        return f"{self.form.target} {op} {rhs}"

    def to_dict(self) -> dict:
        return {
            "key": self.form.key,
            "target": self.form.target,
            "direction": self.form.direction,
            "predictors": list(self.form.predictors),
            "signs": list(self.form.signs),
            "coefs": {k: round(v, 10) for k, v in self.coefs.items()},
            "intercept": round(self.intercept, 10),
            "n_tight": self.n_tight,
            "n_total": self.n_total,
            "tight_ratio": round(self.tight_ratio, 6),
            "mean_slack": round(self.mean_slack, 8),
            "trivial": self.trivial,
            "inequality": self.inequality_str(),
        }


# ---------------------------------------------------------------- 形式枚举
def enumerate_forms(targets: Iterable[str] = ("chi",),
                    direction: str = "le",
                    max_predictors: int = 2,
                    exclude_np_hard: bool = False) -> list[Form]:
    """枚举形式：目标 × 预测子集 × 符号组合。

    预测子集的大小从 1 到 max_predictors，符号取全部 2^k 组合。
    """
    out: list[Form] = []
    for t in targets:
        pool = [v for v in INVARIANTS if v != t]
        if exclude_np_hard:
            from ..config import NP_HARD
            pool = [v for v in pool if v not in NP_HARD]
        for k in range(1, max_predictors + 1):
            for combo in itertools.combinations(pool, k):
                for signs in itertools.product([1, -1], repeat=k):
                    out.append(Form(t, tuple(combo), tuple(signs), direction))
    return out


# ---------------------------------------------------------------- LP
def _design_matrix(df: pd.DataFrame, form: Form) -> np.ndarray:
    """构造 A，第 i 行为该图在带符号预测子上的取值。"""
    cols = []
    for name, sg in zip(form.predictors, form.signs):
        cols.append(sg * df[name].to_numpy(dtype=float))
    return np.column_stack(cols)


def solve_form(df: pd.DataFrame, form: Form) -> Solution | None:
    """对单个形式求最优系数。

    归一化说明
    ----------
    目标不变量 t 在不等式左侧的系数固定为 1，因此整个不等式没有
    整体缩放的自由度，不存在"把系数放大、把常数项压小"的退化方向。
    只需把各系数限制在 [0, COEF_MAX] 并最小化平均松弛即可。

    早期版本曾把某个系数锚定为 1，这会排除 (0.5, 0.5) 这类比例，
    导致 Reed 猜想这样的形式无法被复现，故弃用。

    求解分两步
    ----------
    第一步最小化平均松弛量，使界尽可能紧；
    第二步在不劣化平均松弛的前提下收紧常数项，使数值更整齐。
    """
    A = _design_matrix(df, form)
    t = df[form.target].to_numpy(dtype=float)
    n, k = A.shape

    bounds = [(0.0, COEF_MAX)] * k + [(None, None)]

    # 可行性约束：le 时 A a + b >= t；ge 时 A a + b <= t
    if form.direction == "le":
        A_ub = np.hstack([-A, -np.ones((n, 1))])
        b_ub = -t
        c1 = np.concatenate([A.mean(axis=0), [1.0]])      # min mean(Aa+b-t)
    else:
        A_ub = np.hstack([A, np.ones((n, 1))])
        b_ub = t
        c1 = np.concatenate([-A.mean(axis=0), [-1.0]])    # min mean(t-Aa-b)

    res = linprog(c1, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not res.success:
        return None

    a = res.x[:k].copy()
    b = float(res.x[k])
    slack_star = float(c1 @ res.x)

    # 第二阶段：平均松弛不变，收紧常数项
    eq = c1.reshape(1, -1)
    c2 = np.zeros(k + 1)
    c2[k] = 1.0 if form.direction == "le" else -1.0

    res2 = linprog(c2, A_ub=A_ub, b_ub=b_ub, A_eq=eq, b_eq=[slack_star],
                   bounds=bounds, method="highs")
    if res2.success:
        a = res2.x[:k].copy()
        b = float(res2.x[k])

    pred = A @ a + b
    slack = pred - t if form.direction == "le" else t - pred

    scale = max(np.abs(t).max(), 1.0)
    tight = np.abs(slack) <= 1e-7 * scale

    coefs = {name: float(ai) for name, ai in zip(form.predictors, a)}
    trivial = bool(np.all(np.abs(a) < 1e-9))

    return Solution(
        form=form,
        coefs=coefs,
        intercept=b,
        n_tight=int(tight.sum()),
        n_total=n,
        mean_slack=float(slack.mean()),
        trivial=trivial,
        status="ok",
    )


# ---------------------------------------------------------------- 批量
def search(df: pd.DataFrame, forms: Sequence[Form],
           min_tight_ratio: float = 0.0,
           progress_every: int = 200) -> list[Solution]:
    """对一批形式求解，返回非平凡且满足取等比例下限的解。"""
    out: list[Solution] = []
    for i, f in enumerate(forms, 1):
        sol = solve_form(df, f)
        if sol is None or sol.trivial:
            continue
        if sol.tight_ratio < min_tight_ratio:
            continue
        out.append(sol)
        if progress_every and i % progress_every == 0:
            print(f"    {i}/{len(forms)}，已保留 {len(out)} 条")
    return out


def rank(sols: Sequence[Solution], by: str = "tight_ratio") -> list[Solution]:
    return sorted(sols, key=lambda s: (-getattr(s, by), s.mean_slack))


def dedup(sols: Sequence[Solution], digits: int = 6) -> list[Solution]:
    """按数值形式去重。

    不同的形式（如 chi <= a1*n - a2*alpha + b 与 chi <= -a1*alpha + b）
    在某个系数被 LP 压到 0 时会得到同一条不等式。
    这类重复必须剔除，否则多重检验的分母被虚增，
    BH 的阈值会被不必要地放宽。
    """
    seen: set[tuple] = set()
    out: list[Solution] = []
    for s in sols:
        # 只保留非零系数项，构成与形式无关的规范键
        items = []
        for (name, sg), a in zip(zip(s.form.predictors, s.form.signs),
                                 s.coefs.values()):
            if abs(a) < 10 ** (-digits):
                continue
            items.append((name, round(sg * a, digits)))
        key = (s.form.target, s.form.direction, tuple(sorted(items)),
               round(s.intercept, digits))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out
