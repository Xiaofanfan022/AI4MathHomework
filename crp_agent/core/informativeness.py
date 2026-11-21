"""候选不等式的信息量判定。

为什么需要
----------
统计筛选只回答"这条不等式是否超出偶然"，不回答"它是否有内容"。
`omega <= chi`、`n >= chi`、`delta <= Delta` 这类由定义直接给出的
关系在任何图集上都成立，因此必然通过置换检验与 BH 校正，却没有任何
信息量。若只以"保留条数"衡量智能体的产出，随机抽样反而会胜出——
它更容易撞上这些恒真式。

判定方式
--------
维护一组基本事实（定义、简单计数、已被证明的经典结论）。若某条基本
事实在数据上处处不比候选松弛，则候选被该基本事实支配，判为无信息量。

"处处不比候选松弛"是比"逻辑蕴含"更弱的条件：它只在给定图集上成立，
因此判定的结果是"在数据上被支配"，而非"逻辑上被蕴含"。这一点在报告
中必须说明。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .forms import Solution


# ---------------------------------------------------------------- 基本事实
def _f(name: str, target: str, direction: str, fn) -> dict:
    return {"name": name, "target": target, "direction": direction, "fn": fn}


def _slack_le(lhs: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    return rhs - lhs


def _slack_ge(lhs: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    return lhs - rhs


def base_facts() -> list[dict]:
    """返回基本事实表。

    每条事实给出 slack 函数，slack >= 0 表示该图满足此事实。
    """
    c = lambda df, k: df[k].to_numpy(dtype=float)  # noqa: E731
    facts = []

    def add(name, target, direction, lhs_fn, rhs_fn):
        facts.append(_f(name, target, direction,
                        lambda df, l=lhs_fn, r=rhs_fn, d=direction:
                        (_slack_le if d == "le" else _slack_ge)(l(df), r(df))))

    # 目标 chi
    # 注意方向：direction 为 "ge" 时不等式形如 target >= expr，
    # slack = target - expr，故 lhs 必须是 target 本身。
    add("chi >= omega（定义）", "chi", "ge", lambda df: c(df, "chi"),
        lambda df: c(df, "omega"))
    add("chi <= n（色数不超过顶点数）", "chi", "le", lambda df: c(df, "chi"),
        lambda df: c(df, "n"))
    add("chi <= Delta + 1（贪心着色）", "chi", "le", lambda df: c(df, "chi"),
        lambda df: c(df, "Delta") + 1)
    add("chi >= 1（非空图）", "chi", "ge", lambda df: c(df, "chi"),
        lambda df: np.ones(len(df)))
    add("chi <= m + 1（边数界）", "chi", "le", lambda df: c(df, "chi"),
        lambda df: c(df, "m") + 1)

    # 目标 omega
    add("omega <= chi（定义）", "omega", "le", lambda df: c(df, "omega"),
        lambda df: c(df, "chi"))
    add("omega <= Delta + 1", "omega", "le", lambda df: c(df, "omega"),
        lambda df: c(df, "Delta") + 1)
    add("omega <= n", "omega", "le", lambda df: c(df, "omega"),
        lambda df: c(df, "n"))
    add("omega >= 1（非空图）", "omega", "ge", lambda df: c(df, "omega"),
        lambda df: np.ones(len(df)))

    # 目标 alpha
    add("alpha <= n", "alpha", "le", lambda df: c(df, "alpha"),
        lambda df: c(df, "n"))
    add("alpha <= n - delta（最大独立集）", "alpha", "le",
        lambda df: c(df, "alpha"), lambda df: c(df, "n") - c(df, "delta"))
    add("alpha >= 1（非空图）", "alpha", "ge", lambda df: c(df, "alpha"),
        lambda df: np.ones(len(df)))

    # 目标 Delta
    add("Delta <= n - 1", "Delta", "le", lambda df: c(df, "Delta"),
        lambda df: c(df, "n") - 1)
    add("Delta >= delta（定义）", "Delta", "ge", lambda df: c(df, "Delta"),
        lambda df: c(df, "delta"))
    add("Delta <= m（最大度不超过边数）", "Delta", "le",
        lambda df: c(df, "Delta"), lambda df: c(df, "m"))
    # rho <= Delta 与 Delta >= rho 是同一事实的两种写法，两条都要列出，
    # 否则只有一半的等价写法能被识别为无信息量。
    add("Delta >= rho（谱半径不超过最大度）", "Delta", "ge",
        lambda df: c(df, "Delta"), lambda df: c(df, "rho"))

    # 目标 delta
    add("delta <= Delta（定义）", "delta", "le", lambda df: c(df, "delta"),
        lambda df: c(df, "Delta"))
    add("delta <= n - 1", "delta", "le", lambda df: c(df, "delta"),
        lambda df: c(df, "n") - 1)
    add("delta <= 2m/n（平均度）", "delta", "le", lambda df: c(df, "delta"),
        lambda df: 2 * c(df, "m") / np.maximum(c(df, "n"), 1))
    add("delta <= rho（谱半径不小于最小度）", "delta", "le",
        lambda df: c(df, "delta"), lambda df: c(df, "rho"))

    # 目标 m
    add("m <= n(n-1)/2（简单图）", "m", "le", lambda df: c(df, "m"),
        lambda df: c(df, "n") * (c(df, "n") - 1) / 2)
    add("m >= Delta（最大度不超过边数）", "m", "ge", lambda df: c(df, "m"),
        lambda df: c(df, "Delta"))
    add("m >= nu（匹配数不超过边数）", "m", "ge", lambda df: c(df, "m"),
        lambda df: c(df, "nu"))

    # 目标 nu
    add("nu <= n/2", "nu", "le", lambda df: c(df, "nu"),
        lambda df: c(df, "n") / 2)
    add("nu <= m", "nu", "le", lambda df: c(df, "nu"), lambda df: c(df, "m"))
    add("nu >= 0（平凡下界）", "nu", "ge", lambda df: c(df, "nu"),
        lambda df: np.zeros(len(df)))

    # 目标 rho
    add("rho <= Delta", "rho", "le", lambda df: c(df, "rho"),
        lambda df: c(df, "Delta"))
    add("rho <= n - 1", "rho", "le", lambda df: c(df, "rho"),
        lambda df: c(df, "n") - 1)
    add("rho >= 2m/n（平均度）", "rho", "ge", lambda df: c(df, "rho"),
        lambda df: 2 * c(df, "m") / np.maximum(c(df, "n"), 1))

    # 目标 n
    add("n >= chi", "n", "ge", lambda df: c(df, "n"),
        lambda df: c(df, "chi"))
    add("n >= alpha", "n", "ge", lambda df: c(df, "n"),
        lambda df: c(df, "alpha"))
    add("n >= rho + 1", "n", "ge", lambda df: c(df, "n"),
        lambda df: c(df, "rho") + 1)
    # 同一不等式的另一种写法，目标与方向都不同。dominated_by 只在
    # (target, direction) 相同的条件下比较，故这些对称写法必须显式列出，
    # 否则 "n >= 2*nu" 会被当成有信息量的候选——它其实是 "nu <= n/2" 的
    # 移项，取等比例高达 0.5854，正是靠这一条才在形式上界中排到第一。
    add("n >= Delta + 1（最大度）", "n", "ge", lambda df: c(df, "n"),
        lambda df: c(df, "Delta") + 1)
    add("n >= 2*nu（匹配数）", "n", "ge", lambda df: c(df, "n"),
        lambda df: 2 * c(df, "nu"))
    add("n >= alpha + delta（独立集）", "n", "ge", lambda df: c(df, "n"),
        lambda df: c(df, "alpha") + c(df, "delta"))

    return facts


def candidate_slack(df: pd.DataFrame, sol: Solution) -> np.ndarray:
    """候选不等式在各图上的松弛量，>= 0 表示成立。

    注意：`_design_matrix` 已按 form.signs 给列带上符号，因此这里必须
    乘未带符号的 `sol.coefs`。若乘 `signed_coefs`，符号会被应用两次，
    负号项变成正号，松弛量随之出错。
    """
    from .forms import _design_matrix

    A = _design_matrix(df, sol.form)
    a = np.array([sol.coefs[p] for p in sol.form.predictors])
    lhs = A @ a + sol.intercept
    t = df[sol.form.target].to_numpy(dtype=float)
    if sol.form.direction == "le":
        return lhs - t
    return t - lhs


def dominated_by(df: pd.DataFrame, sol: Solution,
                 tol: float = 1e-9) -> str | None:
    """若候选被某条基本事实支配，返回该事实名；否则返回 None。"""
    sl = candidate_slack(df, sol)
    best = None
    for fact in base_facts():
        if fact["target"] != sol.form.target:
            continue
        if fact["direction"] != sol.form.direction:
            continue
        sb = fact["fn"](df)
        # 基本事实处处不比候选松弛 => 候选是它的推论
        if np.all(sb <= sl + tol):
            return fact["name"]
        if best is None:
            best = fact["name"]
    return None


def label(df: pd.DataFrame, sol: Solution) -> dict:
    """给候选打标签：有信息量 / 被支配。"""
    d = dominated_by(df, sol)
    return {"informative": d is None, "dominated_by": d}
