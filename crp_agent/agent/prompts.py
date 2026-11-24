"""提示词。

四处调用大语言模型，各有独立提示：
1. 提出形式   propose_forms
2. 解释失败   explain_failure
3. 判定新颖性 judge_novelty
4. 选择策略   choose_strategy

约定：提示只提供数据摘要，不提供原始数据表。
模型不接触系数，只决定"用哪些量、什么符号"。
"""

from __future__ import annotations

INVARIANT_GLOSSARY = """\
n     顶点数
m     边数
Delta 最大度（各顶点度数中的最大值）
delta 最小度
alpha 独立数（两两不相邻的顶点集的最大规模）
omega 团数（两两相邻的顶点集的最大规模）
chi   色数（使相邻顶点异色所需的最少颜色数）
nu    匹配数（两两不共端点的边的最大条数）
rho   谱半径（邻接矩阵最大特征值的绝对值）
"""

# 派生特征只在长跑的后半段开放。它们让形式空间从 2304 条扩到 7056 条，
# 但可读性下降：像 "chi <= 0.3*aD" 这样的不等式很难一眼看出含义。
# 因此策略是先让模型在基础空间里提完，再放开乘积项。
DERIVED_GLOSSARY = """\
以下派生特征由基础不变量相乘得到，可以当作预测子使用：
n2     n 的平方（顶点数 × 顶点数）
aD     alpha × Delta（独立数 × 最大度）
wD     omega × Delta（团数 × 最大度）
cD     chi × Delta（色数 × 最大度）
aO     alpha × omega（独立数 × 团数）
nD     n × Delta（顶点数 × 最大度）

注意：目标不变量仍然只能是上面九个基础量，派生特征只能出现在右侧。
"""

SYSTEM_PROPOSE = """\
你是一位图论研究者，正在参与一个自动猜想系统。

你的任务：根据给定的数据摘要，提出若干值得检验的图不变量不等式形式。

规则：
- 每条形式必须写成 "目标 <= 线性组合" 或 "目标 >= 线性组合"。
- 线性组合只能使用给出的不变量，每个量带 +1 或 -1 的符号。
- 系数不由你给出，系统会用线性规划求解，你只决定"用哪些量、什么方向"。
- 预测子个数有上限，具体数目见用户消息末尾。预测子越多，在有限数据上
  越容易过拟合，也越容易被线性规划压成零。
- 目标不变量可以是九个量中的任意一个，不要全部集中在 chi 上。
  在八条形式里，至少三条的目标不应是 chi。
- 不要提出平凡形式：例如只用 n 作预测子去界 n 本身，或只用一个量界它自己，
  也不要提 "alpha <= n"、"chi <= Delta + 1"、"omega <= chi" 这类由定义
  或最粗的计数就立即成立的界。
- 优先考虑你判断在图论中有结构性意义的组合，而不是随机拼凑。

输出格式：严格的 JSON，形如
{"forms": [{"target": "chi", "direction": "le",
            "predictors": ["omega", "Delta"], "signs": [1, 1],
            "reason": "一句话说明为什么值得试"}]}
不要输出任何其他文字。
"""

SYSTEM_EXPLAIN = """\
你是一位图论研究者。系统中有一条候选不等式被反例推翻了。

你的任务：根据反例的结构特征，归纳这条候选失败的原因，
并指出下一轮应当避免的方向。

要求：
- 只依据给出的数据作判断，不要臆造未见过的定理。
- 说明要具体：是形式本身不成立，还是数据范围不足以支撑。
- 输出严格的 JSON：
{"reason": "失败原因", "lesson": "下一轮应避免什么",
 "suggested_fix": "可以尝试的修正方向或空字符串"}
"""

SYSTEM_NOVELTY = """\
你是一位图论研究者。系统中产生了一条在数据上成立的候选不等式。

你的任务：判断它与已知结论的关系。

要求：
- 若它是某个经典结论的等价改写，指出是哪一个。
- 若你不确定，明确说"不确定"，不要编造文献。
- 判断依据只能是你的知识，系统没有联网检索。
- 输出严格的 JSON：
{"verdict": "known|equivalent|unknown",
 "matched": "对应的已知结论名或空字符串",
 "comment": "一句话说明"}
"""

SYSTEM_STRATEGY = """\
你是一位图论研究者。系统中有一条候选不等式，需要用有限算力搜索反例。

可选的搜索策略：
- random      随机图，覆盖各种边密度
- structured  结构化图族（完全多部图、Mycielski 扩张、正则图等）
- local       对已知取等的图作局部修改

你的任务：根据候选的形式与上一轮的搜索记录，选择本轮应重点使用的策略，
并给出理由。

要求：
- 若上一轮某策略已用尽预算仍未找到反例，考虑换策略而非重复。
- 若候选涉及色数、团数，结构化族通常更有希望。
- 输出严格的 JSON：
{"strategy": "random|structured|local", "budget": 整数,
 "reason": "一句话说明"}
"""


def propose_user_prompt(summary: dict, known: list[str],
                        tried: list[str], n_round: int,
                        exhausted: list[str] | None = None,
                        trivial: list[str] | None = None,
                        lessons: list[dict] | None = None,
                        passed: list[str] | None = None,
                        collapses: list[dict] | None = None,
                        max_forms: int = 8,
                        derived: list[str] | None = None,
                        max_pred: int = 3) -> str:
    """构造"提出形式"的用户消息。

    known     已经确认成立的结论（不要重复提出）
    tried     已被反例推翻的形式
    exhausted 此前各轮已经处理过、无论存活的全部形式。只给 tried
              会让模型反复提出同一批"未被推翻"的形式，导致后续轮次
              没有新内容可评估。
    trivial   被判为无信息量的形式（由定义直接给出的恒真式）。
              这些形式统计上必然通过检验，但没有内容，须单独列出，
              否则模型会不断提出同一批恒真式。
    lessons   上一轮被推翻的候选及其失败原因。早期版本只回传被推翻的
              形式文本，模型看不到自己上一轮归纳出的失败原因，等于每轮
              从零开始重新采样，跨轮没有积累。这里把反例的数值特征与
              模型自己的教训一并回传，模型才可能提出有针对性的修正。
    passed    已通过统计检验的候选。它们尚未被证明，但可以作为进一步
              收紧或组合的起点。
    collapses 上一轮"提了多个预测子、但线性规划把其中某些系数压成 0"
              的形式。这类形式与已检验过的某条不等式重合而被剔除，
              但模型看不到这一点，于是反复提出"多加一个量"的变体。
    """
    lines = [
        f"这是第 {n_round} 轮。",
        "",
        "## 不变量对照表",
        INVARIANT_GLOSSARY,
    ]
    if derived:
        lines += [DERIVED_GLOSSARY]
    lines += [
        "## 数据摘要",
        f"图的数量：{summary['n_graphs']}",
        f"阶数范围：{summary['n_range']}",
        "",
        "各不变量与目标 chi 的 Spearman 相关系数：",
    ]
    for k, v in summary["corr_with_target"].items():
        lines.append(f"  {k:6s} {v:+.3f}")

    lines += ["", "各不变量的取值范围："]
    for k, (lo, hi) in summary["ranges"].items():
        lines.append(f"  {k:6s} [{lo}, {hi}]")

    pairs = summary.get("top_correlated_pairs") or []
    if pairs:
        lines += ["", "相关性最强的若干不变量对（Spearman）："]
        for p in pairs:
            lines.append(f"  {p['a']:6s} ~ {p['b']:6s} {p['rho']:+.3f}")
        lines += ["",
                  "注意：上表只是相关结构，不代表因果关系。目标不变量不必"
                  "是 chi，你可以对任何一个不变量提出上界或下界。"]

    lines += ["", "## 已确认成立的结论（不要重复提出）"]
    lines += [f"  - {s}" for s in known] or ["  （暂无）"]

    if tried:
        lines += ["", "## 已尝试且被反例推翻的形式（不要重复）"]
        lines += [f"  - {s}" for s in tried[-12:]]

    if lessons:
        lines += ["", "## 上一轮失败的复盘（重要）"]
        lines += ["以下候选被反例推翻。反例的数值说明这条形式为什么不可能"
                  "成立，请据此调整方向，而不是换个符号重提同一条。"]
        for L in lessons[-6:]:
            lines.append("")
            lines.append(f"  * 候选：{L['inequality']}")
            if L.get("counterexample"):
                ce = L["counterexample"]
                inv = ce.get("invariants", {})
                keys = ("n", "m", "Delta", "alpha", "omega", "chi", "nu")
                vals = ", ".join(f"{k}={inv[k]}" for k in keys if k in inv)
                lines.append(f"    反例：{ce['n']} 个顶点，"
                             f"{len(ce.get('edges', []))} 条边；{vals}")
            if L.get("reason"):
                lines.append(f"    失败原因：{L['reason']}")
            if L.get("lesson"):
                lines.append(f"    教训：{L['lesson']}")
            if L.get("suggested_fix"):
                lines.append(f"    建议方向：{L['suggested_fix']}")
        lines += ["",
                  "注意：如果某条候选的失败原因是\"该不变量对目标没有约束力\"，"
                  "那么只改变符号或系数不会有用，应当更换预测子。"
                  "如果失败原因是\"常数项吸收了差异\"，应当考虑引入另一个"
                  "能区分反例与其余图的不变量。"]

    if collapses:
        lines += ["", "## 上一轮被系数压成零的形式（重要）"]
        lines += ["你上一轮提出的下列形式，在求解时有一个或几个预测子的系数"
                  "被压到 0，结果退化成了另一条已经检验过的不等式，因此被"
                  "剔除。这说明那些量对目标没有额外约束力。请换用别的量，"
                  "而不是继续在同一组量上加项。"]
        for c in collapses[-8:]:
            lines.append(f"  - {c['target']} {c['direction']} "
                         f"{c['proposed']}：{', '.join(c['zero_coef'])} "
                         f"的系数为 0，退化为 {c['collapsed_to']}")

    if passed:
        lines += ["", "## 已通过统计检验的候选（可作为收紧的起点）"]
        lines += [f"  - {s}" for s in passed[-8:]]
        lines += ["",
                  "这些候选尚未被证明，但在验证集上通过了置换检验。"
                  "你可以尝试对它们收紧：例如加入一个新的预测子，"
                  "或换一个方向提出对偶形式。"]

    if trivial:
        lines += ["", "## 以下形式由定义直接成立，没有信息量（不要再提）"]
        lines += [f"  - {s}" for s in trivial[-12:]]
        lines += ["",
                  "这些形式在任何图上都成立，检验它们不会产生新知识。"
                  "请提出需要实质论证才能成立的组合。"]

    if exhausted:
        lines += ["", "## 此前各轮已经提出过的形式（不要重复，请换方向）"]
        lines += [f"  - {s}" for s in exhausted[-24:]]
        lines += ["",
                  "上面按「目标 方向 [带符号的预测子]」列出，与你在 JSON 里"
                  "写的 target / direction / predictors / signs 一一对应。"
                  "这些形式已经处理过，请提出与它们不同的组合。"]

    lines += ["", f"请提出 {max(1, max_forms - 2)} 到 {max_forms} 条候选形式。"
                  f"每条最多 {max_pred} 个预测子。"]
    return "\n".join(lines)


def explain_user_prompt(inequality: str, counterexample: dict) -> str:
    n = counterexample["n"]
    m = len(counterexample["edges"])
    inv = counterexample.get("invariants", {})
    inv_str = ", ".join(f"{k}={v}" for k, v in inv.items()
                        if not k.startswith("_"))
    return (
        f"候选不等式：{inequality}\n\n"
        f"反例：{n} 个顶点，{m} 条边。\n"
        f"该图的不变量：{inv_str}\n\n"
        f"请分析这条候选为何不成立。"
    )


def novelty_user_prompt(inequality: str, tight_ratio: float,
                        n_graphs: int) -> str:
    return (
        f"候选不等式：{inequality}\n"
        f"在 {n_graphs} 张图上成立，其中 {tight_ratio*100:.1f}% 取等。\n\n"
        f"请判断它与已知结论的关系。"
    )


def strategy_user_prompt(inequality: str, history: list[dict]) -> str:
    lines = [f"候选不等式：{inequality}", "", "上一轮的搜索记录："]
    if not history:
        lines.append("  （这是第一次搜索）")
    for h in history[-6:]:
        lines.append(f"  - 策略 {h['strategy']}，预算 {h['budget_used']}，"
                     f"结果 {'找到反例' if h['found'] else '未找到'}")
    lines += ["", "请选择本轮的搜索策略与预算。"]
    return "\n".join(lines)
