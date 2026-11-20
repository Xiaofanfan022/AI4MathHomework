"""图的枚举与采样。

两类来源
--------
1. 完全枚举：n <= 8 的全部非同构简单图。
   用逐点扩张 + 同构去重（canonical augmentation 的简化版）。
   规模：|G_6|=156, |G_7|=1044, |G_8|=12346。
2. 随机采样：n = 9..12，按不同边概率生成，覆盖稠密与稀疏区域。
   另加若干结构化族（完全多部图、正则图、Mycielski 扩张），
   因为这些结构最容易成为反例的来源。

所有图统一表示为 (n, edges)，edges 为 [(u,v), ...]，u < v。
"""

from __future__ import annotations

import itertools
import random
import warnings
from typing import Iterable, Iterator

import networkx as nx

# networkx 3.5 起 WL 哈希的实现有变动，会针对无属性的图发出提示；
# 本项目只用它做分桶键，不影响正确性。
warnings.filterwarnings("ignore", message=".*hashes produced for graphs.*")


# ---------------------------------------------------------------- 工具
def to_nx(n: int, edges) -> nx.Graph:
    G = nx.Graph()
    G.add_nodes_from(range(n))
    G.add_edges_from(edges)
    return G


def canon_key(n: int, edges) -> str:
    """用于去重的规范键：WL 哈希 + 边数 + 度序列。

    不保证完全区分同构类，但配合后续精确同构检验足够用。
    仅作为分桶键，不作为最终判据。
    """
    G = to_nx(n, edges)
    h = nx.weisfeiler_lehman_graph_hash(G, iterations=3)
    deg = tuple(sorted(d for _, d in G.degree()))
    return f"{n}|{G.number_of_edges()}|{h}|{deg}"


# ---------------------------------------------------------------- 完全枚举
def enumerate_all_graphs(n_max: int = 8) -> dict[int, list[tuple]]:
    """返回 {n: [(n, edges), ...]}，每个 n 下为全部非同构简单图。

    以 graph_atlas 的 7 阶图为种子（含全部 n <= 7），再逐点扩张到 8 阶。
    """
    by_n: dict[int, list[tuple]] = {k: [] for k in range(1, n_max + 1)}

    for G in nx.graph_atlas_g():
        k = G.number_of_nodes()
        if 1 <= k <= min(n_max, 7):
            by_n[k].append((k, sorted(tuple(sorted(e)) for e in G.edges())))

    # 逐阶扩张
    for k in range(1, n_max):
        nxt = by_n.get(k + 1)
        if nxt is None:
            continue
        seen: dict[str, list[tuple]] = {}
        for (_, edges) in by_n[k]:
            base = set(edges)
            for neigh_bits in range(1 << k):
                new_edges = list(base)
                for v in range(k):
                    if (neigh_bits >> v) & 1:
                        new_edges.append((v, k))
                new_edges.sort()
                key = canon_key(k + 1, new_edges)
                bucket = seen.setdefault(key, [])
                # 桶内精确同构检验
                cand = to_nx(k + 1, new_edges)
                dup = False
                for existing in bucket:
                    if nx.is_isomorphic(cand, to_nx(k + 1, existing)):
                        dup = True
                        break
                if not dup:
                    bucket.append(tuple(new_edges))

        reps = [e for b in seen.values() for e in b]
        by_n[k + 1] = [(k + 1, e) for e in reps]
        print(f"  n={k+1}: {len(reps)} graphs")

    return by_n


# ---------------------------------------------------------------- 随机采样
def sample_random(n_list: Iterable[int], per_n: int,
                  p_list: Iterable[float], seed: int = 0) -> list[tuple]:
    rng = random.Random(seed)
    out: list[tuple] = []
    for n in n_list:
        for p in p_list:
            for _ in range(per_n // len(list(p_list))):
                G = nx.gnp_random_graph(n, p, seed=rng.randrange(1 << 30))
                out.append((n, sorted(tuple(sorted(e)) for e in G.edges())))
    return out


def sample_structured(n_list: Iterable[int], seed: int = 0) -> list[tuple]:
    """结构化族：完全多部图、正则图、轮图、Mycielski 扩张、Kneser 图。

    这些结构常是极端例子所在，作为随机采样的补充。
    """
    rng = random.Random(seed)
    out: list[tuple] = []
    allowed = set(n_list)

    def add(G: nx.Graph):
        n = G.number_of_nodes()
        if n in allowed:
            # 统一重标号为 0..n-1：hypercube_graph 等生成器的顶点是元组，
            # 直接取边会得到 ((0,0),(0,1)) 这类非整数端点。
            G = nx.convert_node_labels_to_integers(G, first_label=0)
            out.append((n, sorted(tuple(sorted(e)) for e in G.edges())))

    # 完全多部图 K_{a1,...,ak}
    def partitions(total: int, max_parts: int = 4):
        def rec(rem, parts):
            if rem == 0:
                if len(parts) >= 2:
                    yield tuple(parts)
                return
            if len(parts) >= max_parts:
                return
            lo = parts[-1] if parts else 1
            for x in range(lo, rem + 1):
                yield from rec(rem - x, parts + [x])
        yield from rec(total, [])

    for n in range(4, 13):
        for part in partitions(n):
            G = nx.complete_multipartite_graph(*part)
            add(G)

    # 循环图与轮图
    for n in range(5, 14):
        add(nx.cycle_graph(n))
        add(nx.wheel_graph(n))

    # 完全图、完全二部图、Petersen、超立方体
    for k in range(4, 11):
        add(nx.complete_graph(k))
    for a in range(2, 6):
        for b in range(a, 7):
            if a + b <= 13:
                add(nx.complete_bipartite_graph(a, b))
    add(nx.petersen_graph())
    for d in range(2, 5):
        add(nx.hypercube_graph(d))

    # Mycielski 扩张（保持团数不变而色数增加，是反例的经典来源）
    G = nx.cycle_graph(5)
    for _ in range(3):
        G = nx.mycielskian(G)
        add(G)

    # 随机正则图
    for n in range(6, 13):
        for d in range(2, min(6, n - 1)):
            if (n * d) % 2:
                continue
            try:
                G = nx.random_regular_graph(d, n, seed=rng.randrange(1 << 30))
                add(G)
            except nx.NetworkXError:
                pass

    return out


# ---------------------------------------------------------------- 汇总
def build_dataset(n_max_exhaustive: int = 8,
                  sampled_n: Iterable[int] = (9, 10, 11, 12),
                  per_n: int = 4000,
                  seed: int = 0) -> dict:
    """返回 {"exhaustive": {...}, "sampled": [...]}，均已去重。"""
    print("[枚举] 完全枚举 n <= %d ..." % n_max_exhaustive)
    exh = enumerate_all_graphs(n_max_exhaustive)

    print("[采样] 随机图与结构化图 ...")
    rnd = sample_random(sampled_n, per_n, [0.2, 0.35, 0.5, 0.65, 0.8], seed=seed)
    stc = sample_structured(sampled_n, seed=seed)

    # 去重
    seen = set()
    uniq = []
    for item in rnd + stc:
        key = canon_key(*item)
        sig = (item[0], key)
        if sig in seen:
            continue
        seen.add(sig)
        uniq.append(item)
    print(f"  采样去重后 {len(uniq)} 张")

    return {"exhaustive": exh, "sampled": uniq}
