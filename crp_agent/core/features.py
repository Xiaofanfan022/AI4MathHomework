"""派生特征。

为什么需要
----------
基础不变量只有九个，两点预测子的形式空间一共 2304 条，穷举一遍不到
半小时。让智能体跑一周，几小时就会饱和，剩下的时间都在重复已经检验
过的形式。要让它跑得久，必须先把可提的形式空间放大。

扩张方式的选择
--------------
乘积项是图论猜想里最常见的非线性结构（例如 χ ≤ ½(ω+Δ+1) 之外，
大量猜想涉及 α·Δ、n·Δ 这类量）。这里只加**乘积**，不加比值：
比值（如 m/n 即平均度的一半）通常是小数，而整份统计筛选建立在
"取等比例"上——浮点特征几乎不会精确取等，取等比例会塌到零附近，
置换检验随之失去分辨力。乘积保持整数性，取等仍然频繁出现。

由此带来的一个已知限制
----------------------
信息量判定依赖一张手工维护的基本事实表，表中只覆盖基础不变量。
因此使用派生特征的候选不会被判为"被支配"，即使它其实是某个显然
事实的改写。这一点在长跑统计里必须单独说明，不能把派生特征候选的
存活率与基础候选直接比较。
"""

from __future__ import annotations

import pandas as pd

# 派生特征：名称 -> 由哪些基础不变量相乘得到
DERIVED_SPEC: dict[str, tuple[str, ...]] = {
    "n2": ("n", "n"),
    "aD": ("alpha", "Delta"),
    "wD": ("omega", "Delta"),
    "cD": ("chi", "Delta"),
    "aO": ("alpha", "omega"),
    "nD": ("n", "Delta"),
}

DERIVED_CN = {
    "n2": "顶点数平方",
    "aD": "独立数×最大度",
    "wD": "团数×最大度",
    "cD": "色数×最大度",
    "aO": "独立数×团数",
    "nD": "顶点数×最大度",
}


def derived_names() -> list[str]:
    return list(DERIVED_SPEC)


def extend_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """在原表上增加派生特征列，返回新表（不修改入参）。

    所有派生列都是整数的乘积，因此仍然精确取等。
    """
    out = df.copy()
    for name, factors in DERIVED_SPEC.items():
        if name in out.columns:
            continue
        v = out[factors[0]].astype("int64")
        for f in factors[1:]:
            v = v * out[f].astype("int64")
        out[name] = v
    return out


def feature_pool(base: list[str], with_derived: bool = True) -> list[str]:
    """可参与形式的特征名列表。"""
    if not with_derived:
        return list(base)
    return list(base) + derived_names()


def augment_inv(inv: dict) -> dict:
    """给单张图的不变量字典补上派生特征。

    反例搜索在生成图之后只算基础不变量（`compute_all` 不认识派生名），
    而候选不等式可能以派生特征为预测子，故代入前必须补齐，
    否则 `violation` 会因缺少键而报 KeyError。
    """
    for name, factors in DERIVED_SPEC.items():
        if name in inv:
            continue
        v = 1
        for f in factors:
            v *= int(inv[f])
        inv[name] = v
    return inv


def is_derived(name: str) -> bool:
    return name in DERIVED_SPEC


def uses_derived(target: str, predictors) -> bool:
    return is_derived(target) or any(is_derived(p) for p in predictors)
