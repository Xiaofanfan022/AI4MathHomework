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

SYSTEM_PROPOSE = """\
你是一位图论研究者，正在参与一个自动猜想系统。

你的任务：根据给定的数据摘要，提出若干值得检验的图不变量不等式形式。

规则：
- 每条形式必须写成 "目标 <= 线性组合" 或 "目标 >= 线性组合"。
- 线性组合只能使用给出的不变量，每个量带 +1 或 -1 的符号。
- 系数不由你给出，系统会用线性规划求解，你只决定"用哪些量、什么方向"。
- 最多使用 3 个预测子。超过 3 个的形式在有限数据上几乎必然过拟合。
- 不要提出平凡形式：例如只用 n 作预测子去界 n 本身，或只用一个量界它自己。
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
                        tried: list[str], n_round: int) -> str:
    """构造"提出形式"的用户消息。"""
    lines = [
        f"这是第 {n_round} 轮。",
        "",
        "## 不变量对照表",
        INVARIANT_GLOSSARY,
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

    lines += ["", "## 已确认成立的结论（不要重复提出）"]
    lines += [f"  - {s}" for s in known] or ["  （暂无）"]

    if tried:
        lines += ["", "## 已尝试且被推翻的形式（不要重复）"]
        lines += [f"  - {s}" for s in tried[-12:]]

    lines += ["", "请提出 4 到 8 条候选形式。"]
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
