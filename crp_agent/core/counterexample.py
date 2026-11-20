"""反例搜索。

给定一条候选不等式，在有限预算内搜索使其不成立的图。

四类策略
--------
random      随机图，边概率在若干档位上扫过
structured  结构化族（完全多部图、Mycielski 扩张、Kneser、正则图等）
local       对已知取等的图作局部修改（加边、删边、加点）
exhaustive  小规模完全枚举

每类策略都记录"搜索了多少张图"，因为
"搜了 30 张没找到"与"搜了 30 万张没找到"提供的证据强度不同。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from ..config import INVARIANTS
from .invariants import compute_all


@dataclass
class SearchResult:
    found: bool
    graph: dict | None = None          # {"n":.., "edges":[[u,v],..]}
    budget_used: int = 0               # 实际评估的图数
    budget_total: int = 0
    strategy: str = ""
    elapsed: float = 0.0
    best_slack: float = -np.inf        # 最大违反量（未找到时为负）
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "graph": self.graph,
            "budget_used": self.budget_used,
            "budget_total": self.budget_total,
            "strategy": self.strategy,
            "elapsed": round(self.elapsed, 3),
            "best_slack": (round(self.best_slack, 6)
                           if np.isfinite(self.best_slack) else None),
        }


# ---------------------------------------------------------------- 评估
def violation(coefs: dict, intercept: float, direction: str,
              inv: dict) -> float:
    """返回违反量：> 0 表示该图是不等式的一个反例。

    不等式写成 sum coefs_j * inv_j + intercept >= target（le 方向），
    因此违反量 = 右侧 - 左侧。
    """
    target = inv["_target"]
    rhs = sum(c * inv[k] for k, c in coefs.items()) + intercept
    v = target - rhs
    return v if direction == "le" else -v


def _check(n: int, edges, coefs: dict, intercept: float, direction: str,
           target: str) -> float:
    inv = compute_all(n, edges)
    inv["_target"] = inv[target]
    return violation(coefs, intercept, direction, inv)


# ---------------------------------------------------------------- 策略
def _random_graphs(n_lo: int, n_hi: int, count: int, rng: random.Random):
    for _ in range(count):
        n = rng.randint(n_lo, n_hi)
        p = rng.choice([0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        G = nx.gnp_random_graph(n, p, seed=rng.randrange(1 << 30))
        yield n, sorted(tuple(sorted(e)) for e in G.edges())


def _structured_graphs(n_lo: int, n_hi: int, count: int, rng: random.Random):
    """结构化族：优先覆盖可能产生反例的极端结构。"""
    pool: list[nx.Graph] = []

    for k in range(n_lo, n_hi + 1):
        pool.append(nx.cycle_graph(k))
        pool.append(nx.wheel_graph(k))
        pool.append(nx.path_graph(k))
        pool.append(nx.complete_graph(k))
        pool.append(nx.empty_graph(k))

    # 完全多部图
    for a in range(2, 6):
        for b in range(a, 7):
            if a + b <= n_hi:
                pool.append(nx.complete_bipartite_graph(a, b))
    for a in range(2, 4):
        for b in range(a, 4):
            for c in range(b, 4):
                if a + b + c <= n_hi:
                    pool.append(nx.complete_multipartite_graph(a, b, c))

    # Mycielski 扩张：保持团数为 2 而色数逐次加一
    G = nx.cycle_graph(5)
    for _ in range(3):
        G = nx.mycielskian(G)
        if G.number_of_nodes() <= n_hi:
            pool.append(G)

    # 正则图与随机正则图
    for k in range(n_lo, n_hi + 1):
        for d in range(2, min(6, k - 1)):
            if (k * d) % 2:
                continue
            try:
                pool.append(nx.random_regular_graph(
                    d, k, seed=rng.randrange(1 << 30)))
            except nx.NetworkXError:
                pass

    rng.shuffle(pool)
    for G in pool[:count]:
        G = nx.convert_node_labels_to_integers(G, first_label=0)
        yield G.number_of_nodes(), sorted(tuple(sorted(e)) for e in G.edges())


def tight_seed_graphs(df, sol, k: int = 60, tol: float = 1e-6):
    """从验证集中取出使该不等式取等的图，作为局部搜索的起点。

    局部搜索的思路是"反例应当与取等图相距不远"，因此种子必须来自
    取等图而非随机图。若一条不等式在验证集上没有取等图，局部搜索
    就没有起点，此时返回空列表。
    """
    import numpy as np

    from .forms import _design_matrix

    A = _design_matrix(df, sol.form)
    a = np.array([sol.signed_coefs()[p] for p in sol.form.predictors])
    vals = A @ a + sol.intercept - df[sol.form.target].to_numpy(dtype=float)
    if sol.form.direction == "le":
        slack = vals
    else:
        slack = -vals

    idx = np.where(np.abs(slack) <= tol)[0]
    if len(idx) == 0:
        return []
    if len(idx) > k:
        idx = np.random.default_rng(0).choice(idx, size=k, replace=False)

    out = []
    for i in idx:
        row = df.iloc[int(i)]
        n = int(row["n"])
        raw = str(row["edges"])
        edges = []
        if raw and raw != "nan":
            for part in raw.split(";"):
                u, v = part.split("-")
                edges.append((int(u), int(v)))
        out.append((n, sorted(edges)))
    return out


def _local_graphs(seed_graphs, count: int, rng: random.Random):
    """对取等的图作局部修改：加一条边、删一条边、或加一个点。"""
    seeds = list(seed_graphs)
    if not seeds:
        return
    for _ in range(count):
        n, edges = rng.choice(seeds)
        es = set(edges)
        op = rng.choice(["add", "del", "addv"])

        if op == "add":
            non = [(u, v) for u in range(n) for v in range(u + 1, n)
                   if (u, v) not in es]
            if not non:
                continue
            es.add(rng.choice(non))
        elif op == "del" and es:
            es.discard(rng.choice(sorted(es)))
        else:
            k = n
            for v in range(k):
                if rng.random() < 0.4:
                    es.add((v, k))
            n = k + 1

        yield n, sorted(es)


# ---------------------------------------------------------------- 主入口
def search_counterexample(coefs: dict, intercept: float, direction: str,
                          target: str, strategy: str = "structured",
                          budget: int = 2000, n_lo: int = 3, n_hi: int = 12,
                          seed: int = 0,
                          tight_graphs=None) -> SearchResult:
    """在预算内搜索反例。"""
    t0 = time.time()
    rng = random.Random(seed)

    if strategy == "random":
        gen = _random_graphs(n_lo, n_hi, budget, rng)
    elif strategy == "local":
        gen = _local_graphs(tight_graphs or [], budget, rng)
    else:
        gen = _structured_graphs(n_lo, n_hi, budget, rng)

    best = -np.inf
    used = 0
    for n, edges in gen:
        used += 1
        v = _check(n, edges, coefs, intercept, direction, target)
        if v > best:
            best = v
        if v > 1e-9:
            return SearchResult(
                found=True,
                graph={"n": n, "edges": [list(e) for e in edges]},
                budget_used=used, budget_total=budget,
                strategy=strategy,
                elapsed=time.time() - t0,
                best_slack=float(v),
            )
        if used >= budget:
            break

    return SearchResult(
        found=False,
        budget_used=used, budget_total=budget,
        strategy=strategy,
        elapsed=time.time() - t0,
        best_slack=float(best),
    )
