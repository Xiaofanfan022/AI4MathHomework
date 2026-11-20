"""生成中期汇报幻灯片。

设计约定
--------
16:9，白底，主色取报告中的深蓝 #14508C。
每页只讲一件事，标题为一句话结论而非名词短语。
正文字号不小于 16pt，保证投影可读。
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent
FIG = ROOT.parent.parent / "crp_agent" / "figures"
OUT = ROOT / "midterm.pptx"

ACCENT = RGBColor(0x14, 0x50, 0x8C)
ACCENT_LIGHT = RGBColor(0x5B, 0x9B, 0xD5)
ORANGE = RGBColor(0xE0, 0x7B, 0x39)
GREEN = RGBColor(0x3C, 0x8C, 0x5A)
INK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x6E, 0x6E, 0x6E)
LIGHT = RGBColor(0xF2, 0xF5, 0xF9)

FONT = "Microsoft YaHei"
MATH_FONT = "Cambria Math"
W, H = 13.333, 7.5


def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    return prs


def blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def textbox(slide, x, y, w, h, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.paragraphs[0].alignment = align
    return tf


def _segments(text: str):
    """把一段文字切成 (片段, 是否数学) 的序列。

    微软雅黑里的 χ 与拉丁字母 X 几乎同形，投影时容易被读成 X；≤ 与
    减号在雅黑里也偏细。希腊字母与数学符号单独用 Cambria Math 排，
    中文仍用雅黑，两段交替即可。
    """
    out: list[tuple[str, bool]] = []
    for ch in text:
        is_math = (
            "\u0370" <= ch <= "\u03ff"      # 希腊字母
            or ch in "≤≥≠≈∈⊆⊂∑√⌈⌉⌊⌋±×÷·−∞→←↔"
        )
        if out and out[-1][1] == is_math:
            out[-1] = (out[-1][0] + ch, is_math)
        else:
            out.append((ch, is_math))
    return out


def para(tf, text, size=18, color=INK, bold=False, space_after=6,
         first=False, line=1.25, align=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_after = Pt(space_after)
    p.line_spacing = line
    if align is not None:
        p.alignment = align
    for chunk, is_math in _segments(text):
        r = p.add_run()
        r.text = chunk
        r.font.size = Pt(size)
        r.font.color.rgb = color
        r.font.bold = bold
        r.font.name = MATH_FONT if is_math else FONT
        # 斜体是数学变量的惯例，也让 χ 不至于和拉丁字母 X 混淆。
        r.font.italic = is_math
    return p


def title(slide, text, sub=None):
    """页面标题：左侧一条竖线 + 一句话结论。"""
    bar = slide.shapes.add_shape(1, Inches(0.62), Inches(0.52),
                                 Inches(0.055), Inches(0.62))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False

    tf = textbox(slide, 0.85, 0.44, 11.6, 0.8)
    para(tf, text, size=27, color=INK, bold=True, first=True, space_after=0)

    if sub:
        tf2 = textbox(slide, 0.87, 1.18, 11.6, 0.45)
        para(tf2, sub, size=15, color=GRAY, first=True, space_after=0)


def footer(slide, page: int, note: str = ""):
    tf = textbox(slide, 0.62, 6.92, 9.0, 0.35)
    para(tf, note, size=11, color=GRAY, first=True, space_after=0)
    tf2 = textbox(slide, 12.0, 6.92, 0.8, 0.35, align=PP_ALIGN.RIGHT)
    para(tf2, str(page), size=11, color=GRAY, first=True, space_after=0)


def picture(slide, name, x, y, w=None, h=None):
    p = FIG / name
    if w is not None and h is None:
        return slide.shapes.add_picture(str(p), Inches(x), Inches(y),
                                        width=Inches(w))
    if h is not None and w is None:
        return slide.shapes.add_picture(str(p), Inches(x), Inches(y),
                                        height=Inches(h))
    return slide.shapes.add_picture(str(p), Inches(x), Inches(y),
                                    width=Inches(w), height=Inches(h))


def caption(slide, text, x, y, w):
    tf = textbox(slide, x, y, w, 0.3, align=PP_ALIGN.CENTER)
    para(tf, text, size=12, color=GRAY, first=True, space_after=0)


def box(slide, x, y, w, h, fill=LIGHT, line=None):
    shp = slide.shapes.add_shape(5, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(1.0)
    shp.shadow.inherit = False
    # python-pptx 的 shadow.inherit=False 只写一个空的 effectLst，
    # 但形状仍带着 <p:style>，其中的 effectRef 会让渲染器套用主题阴影。
    # 这里把 style 整个删掉，阴影才真正消失。
    el = shp._element
    ns = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    for node in el.findall(ns + "style"):
        el.remove(node)
    try:
        shp.adjustments[0] = 0.045
    except (IndexError, KeyError):
        pass
    return shp


# ------------------------------------------------------------------ 第 1 页
def slide_cover(prs: Presentation):
    s = blank(prs)

    band = s.shapes.add_shape(1, Inches(0), Inches(0), Inches(W), Inches(0.16))
    band.fill.solid()
    band.fill.fore_color.rgb = ACCENT
    band.line.fill.background()
    band.shadow.inherit = False

    tf = textbox(s, 1.1, 2.05, 11.2, 1.0)
    para(tf, "用智能体自动猜想图的不变量不等式", size=38, color=INK,
         bold=True, first=True, space_after=0)

    tf = textbox(s, 1.1, 3.05, 11.2, 0.6)
    para(tf, "CRP-Agent：提出、反驳与统计筛选的闭环", size=21,
         color=ACCENT, first=True, space_after=0)

    ln = s.shapes.add_shape(1, Inches(1.12), Inches(3.85), Inches(2.2),
                            Inches(0.035))
    ln.fill.solid()
    ln.fill.fore_color.rgb = ACCENT_LIGHT
    ln.line.fill.background()
    ln.shadow.inherit = False

    tf = textbox(s, 1.1, 4.12, 11.2, 1.4)
    para(tf, "人工智能与数学 · 课程作业", size=16, color=GRAY, first=True,
         space_after=4)
    para(tf, "中期汇报", size=16, color=GRAY, space_after=4)
    para(tf, "2026 年 11 月 25 日", size=16, color=GRAY, space_after=0)


# ------------------------------------------------------------------ 第 2 页
def slide_problem(prs: Presentation):
    s = blank(prs)
    title(s, "要研究的问题：让机器自己提出图的不等式")

    tf = textbox(s, 0.85, 1.72, 6.3, 4.6)
    para(tf, "给定一张图，计算九个常见不变量", size=18, first=True,
         space_after=8)
    para(tf, "顶点数 n、边数 m、最大度 Δ、最小度 δ、独立数 α、"
             "团数 ω、色数 χ、匹配数 ν、谱半径 ρ", size=15, color=GRAY,
         space_after=14)
    para(tf, "问：这些量之间有哪些恒成立的不等式？", size=18, space_after=8)
    para(tf, "例：χ + α ≤ n + 1", size=20, color=ACCENT, bold=True,
         space_after=4)
    para(tf, "一行即可证明，但当年并不显然", size=14, color=GRAY,
         space_after=14)
    para(tf, "对比：Reed 猜想 χ ≤ (ω+Δ+1)/2 的上取整", size=20, color=ORANGE,
         bold=True, space_after=4)
    para(tf, "1998 年提出，至今未解决", size=14, color=GRAY, space_after=0)

    box(s, 7.55, 1.72, 5.2, 4.1)
    tf = textbox(s, 7.85, 1.95, 4.6, 3.7)
    para(tf, "本课题不以求证某个猜想为目标", size=17, color=ACCENT,
         bold=True, first=True, space_after=10)
    para(tf, "目标是一个可运行的闭环系统：", size=15, space_after=6)
    para(tf, "① 自动提出候选形式", size=15, space_after=6)
    para(tf, "② 自动搜索反例", size=15, space_after=6)
    para(tf, "③ 统计筛选，控制假阳性", size=15, space_after=6)
    para(tf, "④ 全过程留下可审计的轨迹", size=15, space_after=12)
    para(tf, "能否重新发现已知结论，用来检验系统是否正确——"
             "这是正确性检验，不是成果。", size=14, color=GRAY,
         space_after=0)

    footer(s, 2)


# ------------------------------------------------------------------ 第 3 页
def slide_difficulty(prs: Presentation):
    s = blank(prs)
    title(s, "真正的困难不是想不出，而是想得太多",
          sub="四十年来的自动猜想程序都卡在同一处")

    items = [
        ("候选的数量超过人工消化的能力",
         "Graffiti 提出逾千条猜想，筛选靠人一条条看"),
        ("小样本上成立，不蕴含普遍成立",
         "在八阶以内的全部图上成立，可能在第 11 阶失效"),
        ("同时检验上百条，必然出现偶然成立",
         "不做多重检验校正，假阳性无法控制"),
    ]
    y = 1.86
    for i, (head, body) in enumerate(items, 1):
        num = s.shapes.add_shape(9, Inches(0.88), Inches(y + 0.06),
                                 Inches(0.46), Inches(0.46))
        num.fill.solid()
        num.fill.fore_color.rgb = ACCENT
        num.line.fill.background()
        num.shadow.inherit = False
        el = num._element
        ns = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
        for node in el.findall(ns + "style"):
            el.remove(node)
        ntf = num.text_frame
        ntf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = ntf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = str(i)
        r.font.size = Pt(17)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        r.font.name = FONT

        tf = textbox(s, 1.55, y, 5.6, 0.9)
        para(tf, head, size=18, bold=True, first=True, space_after=2)
        para(tf, body, size=14, color=GRAY, space_after=0)
        y += 1.42

    box(s, 7.55, 1.86, 5.2, 3.1, fill=RGBColor(0xFA, 0xF3, 0xEC))
    tf = textbox(s, 7.85, 2.08, 4.6, 2.7)
    para(tf, "一个实测的例子", size=16, color=ORANGE, bold=True, first=True,
         space_after=8)
    para(tf, "χ ≤ ω + 1", size=22, color=INK, bold=True, space_after=8)
    para(tf, "在 n ≤ 8 的全部 13598 张图上成立，", size=15, space_after=4)
    para(tf, "在 n = 9、10 的采样图上成立，", size=15, space_after=4)
    para(tf, "在 n = 11 上失效。", size=15, bold=True, space_after=10)
    para(tf, "反例是 Grötzsch 图：11 个顶点，不含三角形，"
             "却需要四种颜色。", size=14, color=GRAY, space_after=0)

    footer(s, 3)


# ------------------------------------------------------------------ 第 4 页
def slide_design(prs: Presentation):
    s = blank(prs)
    title(s, "系统结构：四步循环，数值计算全部交给程序")

    steps = [
        ("提出候选", "模型决定用哪些不变量、\n什么符号、哪个方向\n系数由线性规划求解"),
        ("搜索反例", "模型选择策略：随机、\n结构化、局部修改\n每次记录评估图数"),
        ("统计筛选", "置换检验给出 p 值\nBH 过程控制\n错误发现率"),
        ("记录与反思", "每步写入 JSONL 轨迹\n被推翻的形式与原因\n反馈给下一轮"),
    ]
    x = 0.72
    for i, (head, body) in enumerate(steps):
        box(s, x, 1.82, 2.86, 2.18)
        tf = textbox(s, x + 0.22, 1.96, 2.42, 1.98)
        para(tf, f"0{i + 1}", size=13, color=ACCENT_LIGHT, bold=True,
             first=True, space_after=2)
        para(tf, head, size=19, color=INK, bold=True, space_after=8)
        for line in body.split("\n"):
            para(tf, line, size=12.5, color=GRAY, space_after=2)
        if i < 3:
            atf = textbox(s, x + 2.86, 2.72, 0.34, 0.4)
            para(atf, "›", size=26, color=ACCENT_LIGHT, bold=True,
                 first=True, space_after=0)
        x += 3.2

    tf = textbox(s, 0.85, 4.34, 11.6, 0.4)
    para(tf, "模型负责的四件事（其余交给确定性程序）", size=17,
         color=ACCENT, bold=True, first=True, space_after=0)

    box(s, 0.72, 4.86, 11.9, 1.5)

    roles = [
        ("提出形式", "开放空间无法用规则穷举"),
        ("解释失败", "反例说明该往哪个方向改"),
        ("判断新颖性", "语义匹配，需查文献"),
        ("选择策略", "结构化族对某些形式快 20 倍"),
    ]
    x = 0.98
    for head, body in roles:
        tf = textbox(s, x, 5.10, 2.6, 1.05)
        para(tf, head, size=15, color=INK, bold=True, first=True,
             space_after=4)
        para(tf, body, size=12.5, color=GRAY, space_after=0)
        x += 2.95

    footer(s, 4, "系数、验证、计数全部由程序完成，模型不参与数值计算")


# ------------------------------------------------------------------ 第 5 页
def slide_data(prs: Presentation):
    s = blank(prs)
    title(s, "阶段一：27810 张图，九个不变量全部精确计算")

    stats = [("27810", "张图"), ("9", "个不变量"), ("0", "条已知结论被违反")]
    x = 0.72
    for big, small in stats:
        tf = textbox(s, x, 1.44, 3.2, 1.1)
        para(tf, big, size=40, color=ACCENT, bold=True, first=True,
             space_after=0)
        para(tf, small, size=14, color=GRAY, space_after=0)
        x += 3.45

    picture(s, "fig01_invariant_dist.png", 0.72, 2.86, w=6.3)
    caption(s, "各不变量在每一阶内部的分布比例", 0.72, 6.34, 6.3)

    box(s, 7.45, 2.86, 5.05, 3.4)
    tf = textbox(s, 7.72, 3.04, 4.52, 3.05)
    para(tf, "构造方式", size=15, color=ACCENT, bold=True, first=True,
         space_after=8)
    para(tf, "n ≤ 8：完全枚举并去重", size=13.5, space_after=3)
    para(tf, "各阶图数为 1、2、4、11、34、156、1044、12346", size=12,
         color=GRAY, space_after=10)
    para(tf, "n = 9–12：随机采样与结构化族", size=13.5, space_after=3)
    para(tf, "每阶约四千张，含完全多部图、"
             "Mycielski 扩张等特殊结构", size=12, color=GRAY,
         space_after=10)
    para(tf, "正确性校验", size=15, color=ACCENT, bold=True, space_after=8)
    para(tf, "χ+α≤n+1、Reed、Brooks 等四条已知结论，违反数均为 0",
         size=12, color=GRAY, space_after=0)

    footer(s, 5, "色数、独立数、团数均为 NP-难，全部用分支定界精确求解，不用启发式")


# ------------------------------------------------------------------ 第 6 页
def slide_baseline(prs: Presentation):
    s = blank(prs)
    title(s, "阶段二：线性规划能复现已知结论，搜索策略决定代价")

    picture(s, "fig06_lp_recovery.png", 0.72, 1.76, w=5.6)
    caption(s, "五条已知结论在数据上的取等比例", 0.72, 4.16, 5.6)

    picture(s, "fig09_boundary.png", 6.72, 1.76, w=6.0)
    caption(s, "χ ≤ ω+1 在每一阶上的最大超出量", 6.72, 4.06, 6.0)

    tf = textbox(s, 0.85, 4.52, 5.4, 1.9)
    para(tf, "线性规划的目标函数改了三次", size=15, color=ACCENT,
         bold=True, first=True, space_after=6)
    para(tf, "只最小化常数项，会偏好 χ ≤ n 这类弱形式；"
             "改最小化平均松弛后，系数才能被推到 1，"
             "Reed 型不等式才复现得出来。", size=12.5, color=GRAY,
         space_after=0)

    tf = textbox(s, 6.85, 4.42, 5.9, 2.1)
    para(tf, "三类反例搜索策略的实测", size=15, color=ACCENT, bold=True,
         first=True, space_after=6)
    para(tf, "结构化族全面不劣于随机图。对 χ ≤ ω+1，"
             "结构化族八次全部命中、中位预算 54；随机图仅命中一次、"
             "中位预算 1204。局部修改完全无效——反例离取等图太远。",
         size=12.5, color=GRAY, space_after=0)

    footer(s, 6, "Grötzsch 反例由结构化族在预算 45 内找到")


# ------------------------------------------------------------------ 第 7 页
def slide_agent(prs: Presentation):
    s = blank(prs)
    title(s, "阶段三：接入模型，五轮闭环跑通")

    stats = [("47", "次模型调用"), ("40", "条提议"), ("9", "条被推翻"),
             ("4", "条通过测试集")]
    x = 0.85
    for big, small in stats:
        tf = textbox(s, x, 1.62, 2.8, 1.0)
        para(tf, big, size=34, color=ACCENT, bold=True, first=True,
             space_after=0)
        para(tf, small, size=13, color=GRAY, space_after=0)
        x += 2.95

    picture(s, "fig11_agent_funnel.png", 0.72, 2.72, w=7.6)
    caption(s, "一次完整运行中候选的逐轮去留与累计", 0.72, 5.86, 7.6)

    box(s, 8.62, 2.72, 4.05, 3.2)
    tf = textbox(s, 8.85, 2.88, 3.6, 2.95)
    para(tf, "四条全部通过测试集", size=15, color=GREEN, bold=True,
         first=True, space_after=8)
    for line in ["α ≤ n − ν", "χ ≤ ρ + 1", "ρ ≥ ω − 1",
                 "α ≤ n − ω + 1"]:
        para(tf, line, size=14, space_after=4)
    para(tf, "前两条与第四条为已知结论，中间两条未查到出处——"
             "但查不到不等于新。", size=11.5, color=GRAY, space_after=0)

    footer(s, 7, "模型的四处职责：提出形式、解释失败、判断新颖性、选择搜索策略")


# ------------------------------------------------------------------ 第 8 页
def slide_ablation(prs: Presentation):
    s = blank(prs)
    title(s, "消融实验：一个与直觉相反的结果",
          sub="随机抽样一度全面超过模型提议")

    picture(s, "fig12_ablation.png", 0.72, 1.86, w=6.2)
    caption(s, "模型提议与随机提议在各指标上的对比", 0.72, 4.94, 6.2)

    tf = textbox(s, 7.25, 1.82, 5.5, 4.5)
    para(tf, "追查原因", size=16, color=ORANGE, bold=True, first=True,
         space_after=6)
    para(tf, "随机组保留的候选里，大量是 ω ≤ χ、δ ≤ Δ 这类"
             "由定义直接成立的恒真式。它们必然通过检验，却毫无信息量。",
         size=13, color=GRAY, space_after=12)

    para(tf, "处理办法", size=16, color=ACCENT, bold=True, space_after=6)
    para(tf, "用 32 条基本事实判断候选是否被处处支配，"
             "无信息量的剔除并反馈给模型。两组使用同一规则。",
         size=13, color=GRAY, space_after=12)

    para(tf, "统一口径后", size=16, color=ACCENT, bold=True, space_after=6)
    para(tf, "通过筛选 2.67 对 4.67，模型组仍略低。"
             "诚实的结论是：在当前的候选规模下，"
             "模型提议相对随机抽样没有表现出可测量的优势。",
         size=13, color=GRAY, space_after=0)

    footer(s, 8, "这个负面结论已如实写入报告，不作回避")


# ------------------------------------------------------------------ 第 9 页
def slide_takeaway(prs: Presentation):
    s = blank(prs)
    title(s, "目前得到的三个结论，以及下一步")

    tf = textbox(s, 0.85, 1.72, 5.6, 4.6)
    para(tf, "三个结论", size=17, color=ACCENT, bold=True, first=True,
         space_after=10)
    para(tf, "① 确定性骨架是对的", size=15, bold=True, space_after=3)
    para(tf, "四条已知结论零违反，线性规划能复现五条已知界，"
             "统计筛选能识别出过拟合候选。", size=12.5, color=GRAY,
         space_after=12)
    para(tf, "② 小阶成立不等于普遍成立", size=15, bold=True, space_after=3)
    para(tf, "χ ≤ ω+1 在 13598 张八阶图上成立，在第 11 阶失效。"
             "这条观察本身就是课题核心判断的实证。", size=12.5,
         color=GRAY, space_after=12)
    para(tf, "③ 模型的贡献尚未被证明", size=15, bold=True, space_after=3)
    para(tf, "剔除恒真式后，模型提议与随机抽样差距不可测量。"
             "问题可能出在提示词，也可能出在任务本身。", size=12.5,
         color=GRAY, space_after=0)

    box(s, 6.85, 1.72, 5.85, 3.62)
    tf = textbox(s, 7.1, 1.92, 5.35, 3.25)
    para(tf, "下一步（11/21 – 11/24）", size=17, color=ACCENT, bold=True,
         first=True, space_after=10)
    para(tf, "注入假命题，检验多重检验校正的筛除能力",
         size=13.5, space_after=6)
    para(tf, "改进提示词，让失败原因而不仅是失败形式进入下一轮",
         size=13.5, space_after=6)
    para(tf, "提高置换次数到 2000 以上，解决 BH 在当前规模下"
             "无法体现作用的问题", size=13.5, space_after=6)
    para(tf, "补充报告后两章，整理图表与轨迹样例", size=13.5,
         space_after=16)
    para(tf, "已纳入版本管理", size=15, color=GREEN, bold=True, space_after=4)
    para(tf, "代码、数据集、13 张图表与全部运行轨迹均已提交，"
             "共 12 次提交；汇报后推送至 GitHub", size=12.5, color=GRAY,
         space_after=0)

    footer(s, 9)


def main() -> None:
    prs = new_deck()
    slide_cover(prs)
    slide_problem(prs)
    slide_difficulty(prs)
    slide_design(prs)
    slide_data(prs)
    slide_baseline(prs)
    slide_agent(prs)
    slide_ablation(prs)
    slide_takeaway(prs)
    prs.save(OUT)
    print(f"已生成 {OUT}，共 {len(prs.slides.__iter__.__self__._sldIdLst)} 页")


if __name__ == "__main__":
    main()
