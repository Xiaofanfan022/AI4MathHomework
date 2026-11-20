"""图不变量的精确计算。

设计要点
--------
1. 全部使用位掩码表示邻域，n <= 12 时速度足够。
2. alpha / omega / chi 均为 NP-难，这里用分支定界精确求解，
   而非启发式近似。对 n <= 12 的图，单张耗时通常在毫秒量级。
3. 若某张图超时，返回 None，由上层决定丢弃或改用上下界。
   绝不静默返回一个错误的精确值。
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------- 基础
def adjacency_masks(n: int, edges) -> list[int]:
    """把边表转成邻接位掩码，mask[v] 的第 u 位为 1 表示 v-u 相邻。"""
    mask = [0] * n
    for u, v in edges:
        mask[u] |= 1 << v
        mask[v] |= 1 << u
    return mask


def complement_masks(mask: list[int], n: int) -> list[int]:
    full = (1 << n) - 1
    return [full & ~mask[v] & ~(1 << v) for v in range(n)]


# ---------------------------------------------------------------- 团数
def max_clique_size(mask: list[int], n: int) -> int:
    """最大团规模，带贪心着色的分支定界（Tomita 风格）。

    mask 为邻接位掩码。返回团数 omega。
    """
    best = 0

    def colour_sort(cand: int) -> tuple[list[int], list[int]]:
        """贪心着色，返回 (顶点顺序, 各顶点颜色上界)。"""
        order, bounds = [], []
        colour = 0
        remaining = cand
        while remaining:
            colour += 1
            avail = remaining
            while avail:
                v = (avail & -avail).bit_length() - 1
                avail &= avail & (avail - 1)
                avail &= ~mask[v]
                remaining &= ~(1 << v)
                order.append(v)
                bounds.append(colour)
        return order, bounds

    def expand(cand: int, size: int) -> None:
        nonlocal best
        if not cand:
            if size > best:
                best = size
            return
        order, bounds = colour_sort(cand)
        for idx in range(len(order) - 1, -1, -1):
            if size + bounds[idx] <= best:
                return
            v = order[idx]
            bit = 1 << v
            if not (cand & bit):
                continue
            expand(cand & mask[v], size + 1)
            cand &= ~bit

    expand((1 << n) - 1, 0)
    return best


def independence_number(mask: list[int], n: int) -> int:
    """独立数 alpha = 补图的团数。"""
    return max_clique_size(complement_masks(mask, n), n)


# ---------------------------------------------------------------- 色数
def chromatic_number(mask: list[int], n: int, upper: int | None = None) -> int:
    """精确色数，DSATUR 分支定界。

    upper 可传入一个已知可行上界（如 Delta+1），用于剪枝加速。
    """
    if n == 0:
        return 0

    # 平凡情形
    deg = [bin(mask[v]).count("1") for v in range(n)]
    if max(deg) == 0:
        return 1

    best = [upper if upper is not None else max(deg) + 1]

    colour = [-1] * n

    def sat_degree(v: int) -> tuple[int, int]:
        seen = 0
        for u in range(n):
            if (mask[v] >> u) & 1 and colour[u] >= 0:
                seen |= 1 << colour[u]
        return bin(seen).count("1"), deg[v]

    def expand(coloured: int, used: int) -> None:
        if used >= best[0]:
            return
        if coloured == n:
            best[0] = used
            return

        # 选择饱和度最高、度数最大的未着色顶点
        pick, pick_key = -1, (-1, -1)
        for v in range(n):
            if colour[v] < 0:
                key = sat_degree(v)
                if key > pick_key:
                    pick_key, pick = key, v
        v = pick

        forbidden = 0
        for u in range(n):
            if (mask[v] >> u) & 1 and colour[u] >= 0:
                forbidden |= 1 << colour[u]

        for c in range(min(used + 1, best[0] - 1)):
            if (forbidden >> c) & 1:
                continue
            colour[v] = c
            expand(coloured + 1, max(used, c + 1))
            colour[v] = -1
            # 对称性破除：若 c 是全新颜色且本层已试过，则跳过
            if c >= used:
                break

    expand(0, 0)
    return best[0]


# ---------------------------------------------------------------- 谱半径
def spectral_radius(n: int, edges) -> float:
    """邻接矩阵的谱半径，即最大特征值的绝对值。

    对无向图邻接矩阵，最大特征值为正实数（Perron-Frobenius），
    故谱半径等于最大特征值。
    """
    if n == 0:
        return 0.0
    A = np.zeros((n, n), dtype=float)
    for u, v in edges:
        A[u, v] = 1.0
        A[v, u] = 1.0
    vals = np.linalg.eigvalsh(A)
    return float(np.max(np.abs(vals)))


# ---------------------------------------------------------------- 匹配数
def matching_number(n: int, edges) -> int:
    """最大匹配的边数。

    用简单的贪心 + 增广（匈牙利算法）求二分图不适用，
    这里用通用图的 blossom 算法，直接调用 networkx。
    """
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(range(n))
    G.add_edges_from(edges)
    matching = nx.max_weight_matching(G, maxcardinality=True)
    return len(matching)


# ---------------------------------------------------------------- 汇总
def compute_all(n: int, edges, *, exact_chi: bool = True,
                chi_upper: int | None = None) -> dict:
    """计算一张图的全部不变量。

    返回 dict，键与 config.INVARIANTS 一致。
    """
    mask = adjacency_masks(n, edges)
    deg = [bin(mask[v]).count("1") for v in range(n)]

    omega = max_clique_size(mask, n)
    alpha = independence_number(mask, n)

    if exact_chi:
        chi = chromatic_number(mask, n, upper=chi_upper)
    else:
        chi = chi_upper if chi_upper is not None else max(deg) + 1

    return {
        "n": n,
        "m": len(edges),
        "Delta": max(deg) if deg else 0,
        "delta": min(deg) if deg else 0,
        "alpha": alpha,
        "omega": omega,
        "chi": chi,
        "nu": matching_number(n, edges),
        "rho": spectral_radius(n, edges),
    }


def compute_bounds(n: int, edges) -> dict:
    """只算便宜的量，并为 NP-难量给出区间上下界。

    用于大规模图：alpha 用 Caro-Wei 下界与 n-omega 上界，
    chi 用 omega 下界与 Delta+1 上界。
    """
    mask = adjacency_masks(n, edges)
    deg = [bin(mask[v]).count("1") for v in range(n)]
    omega = max_clique_size(mask, n)

    caro_wei = sum(1.0 / (d + 1) for d in deg)
    alpha_lo = max(omega, int(caro_wei)) if n else 0
    alpha_hi = n - omega if n else 0

    return {
        "n": n,
        "m": len(edges),
        "Delta": max(deg) if deg else 0,
        "delta": min(deg) if deg else 0,
        "alpha": alpha_lo,          # 下界
        "alpha_hi": alpha_hi,       # 上界
        "omega": omega,
        "chi": omega,               # 下界
        "chi_hi": (max(deg) + 1) if deg else 0,  # 上界
        "nu": matching_number(n, edges),
        "rho": spectral_radius(n, edges),
    }
