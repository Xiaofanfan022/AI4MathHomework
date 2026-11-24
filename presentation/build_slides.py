"""生成中期汇报幻灯片（5 分钟版）。

设计约定
--------
16:9，白底，主色沿用报告中的深蓝 #14508C。
每页标题是一句话结论，不是名词短语。
五分钟只讲一条主线：问题 -> 路线 -> 三级结果 -> 一个反转 -> 下一步。
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
FIG = ROOT.parent / "crp_agent" / "figures"
OUT = ROOT / "midterm.pptx"

ACCENT = RGBColor(0x14, 0x50, 0x8C)
ACCENT_LIGHT = RGBColor(0x5B, 0x9B, 0xD5)
ORANGE = RGBColor(0xE0, 0x7B, 0x39)
GREEN = RGBColor(0x3C, 0x8C, 0x5A)
INK = RGBColor(0x1A, 0x1A, 0x1A)
GRAY = RGBColor(0x6E, 0x6E, 0x6E)
LIGHT = RGBColor(0xF2, 0xF5, 0xF9)
WARM = RGBColor(0xFA, 0xF3, 0xEC)

FONT = "Microsoft YaHei"
MATH_FONT = "Cambria Math"
W, H = 13.333, 7.5

MATH_CHARS = "≤≥≠≈∈⊆⊂∑√⌈⌉⌊⌋±×÷·−∞→←↔"


# ------------------------------------------------------------------ 基础
def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    return prs


def blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _strip_style(shp):
    """删掉 <p:style>，否则渲染器会套用主题阴影。"""
    el = shp._element
    ns = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    for node in el.findall(ns + "style"):
        el.remove(node)


def textbox(slide, x, y, w, h, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.paragraphs[0].alignment = align
    return tf


def _segments(text: str):
    """把文字切成（片段, 是否数学）序列。

    雅黑里的 χ 与拉丁字母 X 几乎同形，≤ 也偏细。希腊字母与数学符号
    单独用 Cambria Math 并设斜体，中文仍用雅黑。
    """
    out: list[tuple[str, bool]] = []
    for ch in text:
        is_math = ("\u0370" <= ch <= "\u03ff") or ch in MATH_CHARS
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
        r.font.italic = is_math
    return p


def title(slide, text, sub=None):
    bar = slide.shapes.add_shape(1, Inches(0.62), Inches(0.50),
                                 Inches(0.055), Inches(0.60))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    _strip_style(bar)

    tf = textbox(slide, 0.85, 0.42, 11.7, 0.75)
    para(tf, text, size=26, color=INK, bold=True, first=True, space_after=0)

    if sub:
        tf2 = textbox(slide, 0.87, 1.14, 11.7, 0.4)
        para(tf2, sub, size=14, color=GRAY, first=True, space_after=0)


def footer(slide, page: int, note: str = ""):
    if note:
        tf = textbox(slide, 0.62, 6.94, 10.6, 0.34)
        para(tf, note, size=11, color=GRAY, first=True, space_after=0)
    tf2 = textbox(slide, 12.1, 6.94, 0.7, 0.34, align=PP_ALIGN.RIGHT)
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
    para(tf, text, size=11.5, color=GRAY, first=True, space_after=0)


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
    _strip_style(shp)
    try:
        shp.adjustments[0] = 0.045
    except (IndexError, KeyError):
        pass
    return shp


def badge(slide, x, y, d, text, fill=ACCENT, size=16):
    shp = slide.shapes.add_shape(9, Inches(x), Inches(y), Inches(d), Inches(d))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    _strip_style(shp)
    tf = shp.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    r.font.name = FONT
    return shp


def arrow(slide, x, y, size=24):
    tf = textbox(slide, x, y, 0.36, 0.5)
    para(tf, "›", size=size, color=ACCENT_LIGHT, bold=True, first=True,
         space_after=0)


def bignum(slide, x, y, w, big, small, color=ACCENT):
    tf = textbox(slide, x, y, w, 1.05)
    para(tf, big, size=34, color=color, bold=True, first=True, space_after=0)
    para(tf, small, size=12.5, color=GRAY, space_after=0)


# ------------------------------------------------------------------ 第 1 页
def slide_cover(prs):
    s = blank(prs)

    band = s.shapes.add_shape(1, Inches(0), Inches(0), Inches(W), Inches(0.16))
    band.fill.solid()
    band.fill.fore_color.rgb = ACCENT
    band.line.fill.background()
    _strip_style(band)

    tf = textbox(s, 1.1, 2.00, 11.2, 1.0)
    para(tf, "用智能体自动猜想图的不变量不等式", size=38, color=INK,
         bold=True, first=True, space_after=0)

    tf = textbox(s, 1.1, 3.00, 11.2, 0.6)
    para(tf, "CRP-Agent：提出、反驳与筛选的闭环", size=21, color=ACCENT,
         first=True, space_after=0)

    ln = s.shapes.add_shape(1, Inches(1.12), Inches(3.80), Inches(2.2),
                            Inches(0.035))
    ln.fill.solid()
    ln.fill.fore_color.rgb = ACCENT_LIGHT
    ln.line.fill.background()
    _strip_style(ln)

    tf = textbox(s, 1.1, 4.08, 11.2, 1.2)
    para(tf, "人工智能与数学 · 课程作业 · 中期汇报", size=16, color=GRAY,
         first=True, space_after=4)
    para(tf, "2026 年 11 月 25 日", size=16, color=GRAY, space_after=0)


# ------------------------------------------------------------------ 第 2 页
def slide_problem(prs):
    s = blank(prs)
    title(s, "要研究的问题：让机器自己提出图的不等式")

    tf = textbox(s, 0.85, 1.70, 6.5, 4.7)
    para(tf, "给定一张图，可以算出九个常见的不变量", size=17, first=True,
         space_after=6)
    para(tf, "n 顶点数、m 边数、Δ 最大度、δ 最小度、α 独立数、"
             "ω 团数、χ 色数、ν 匹配数、ρ 谱半径", size=14, color=GRAY,
         space_after=16)
    para(tf, "问：这些量之间有哪些恒成立的不等式？", size=17, space_after=10)
    para(tf, "χ + α ≤ n + 1", size=21, color=ACCENT, bold=True, space_after=2)
    para(tf, "一行即可证明，但发现它并不显然", size=13, color=GRAY,
         space_after=14)
    para(tf, "Reed 猜想：χ ≤ (ω+Δ+1)/2 的上取整", size=21, color=ORANGE,
         bold=True, space_after=2)
    para(tf, "1998 年提出，至今未解决", size=13, color=GRAY, space_after=0)

    box(s, 7.72, 1.70, 5.05, 3.55, fill=WARM)
    tf = textbox(s, 8.00, 1.92, 4.55, 3.15)
    para(tf, "难点不在生成，而在筛选", size=17, color=ORANGE, bold=True,
         first=True, space_after=10)
    para(tf, "候选的数量超过人工消化的能力", size=13.5, space_after=2)
    para(tf, "Graffiti 提了逾千条，靠人一条条看", size=12, color=GRAY,
         space_after=9)
    para(tf, "小样本上成立，不蕴含普遍成立", size=13.5, space_after=2)
    para(tf, "八阶以内全成立，可能第 11 阶失效", size=12, color=GRAY,
         space_after=9)
    para(tf, "同时检验上百条，必然有偶然成立", size=13.5, space_after=2)
    para(tf, "不做多重检验校正，假阳性失控", size=12, color=GRAY,
         space_after=0)

    box(s, 0.85, 5.52, 11.92, 0.98, fill=LIGHT)
    tf = textbox(s, 1.08, 5.66, 11.45, 0.72)
    para(tf, "一个实测：χ ≤ ω + 1 在 n ≤ 8 的全部 13598 张图上成立，"
             "在 n = 11 上失效。", size=14.5, first=True, space_after=3)
    para(tf, "反例是 Grötzsch 图——11 个顶点，不含三角形，却需要四种颜色。",
         size=12.5, color=GRAY, space_after=0)

    footer(s, 2)


# ------------------------------------------------------------------ 第 3 页
def slide_route(prs):
    s = blank(prs)
    title(s, "技术路线：四步闭环，数值计算全部交给程序")

    steps = [
        ("提出候选", "模型决定用哪些不变量、\n什么符号、哪个方向", True),
        ("求解系数", "线性规划在数据上定系数\n不可行即淘汰", False),
        ("搜索反例", "模型选策略，程序执行\n随机／结构化／局部", True),
        ("统计筛选", "置换检验给 p 值\nBH 控制错误发现率", False),
        ("记录与反馈", "每步写入 JSONL 轨迹\n失败原因回灌下一轮", False),
    ]
    x = 0.60
    for i, (head, body, is_model) in enumerate(steps):
        box(s, x, 1.86, 2.24, 2.30,
            fill=WARM if is_model else LIGHT,
            line=ORANGE if is_model else None)
        tf = textbox(s, x + 0.16, 1.98, 1.92, 2.08)
        para(tf, f"0{i + 1}", size=12, color=ACCENT_LIGHT, bold=True,
             first=True, space_after=2)
        para(tf, head, size=15, color=INK, bold=True, space_after=6)
        for line in body.split("\n"):
            para(tf, line, size=10.5, color=GRAY, space_after=2)
        if i < 4:
            arrow(s, x + 2.24, 2.74, size=20)
        x += 2.55

    tf = textbox(s, 0.85, 4.42, 11.6, 0.4)
    para(tf, "模型只做四件事，其余一律由确定性代码完成", size=16,
         color=ACCENT, bold=True, first=True, space_after=0)

    roles = [
        ("提出形式", "开放空间无法用规则穷举"),
        ("解释失败", "反例指出该往哪个方向改"),
        ("判断新颖性", "语义匹配，需查文献"),
        ("选择策略", "结构化族对某些形式快 20 倍"),
    ]
    x = 0.72
    for head, body in roles:
        box(s, x, 4.90, 2.92, 0.92)
        tf = textbox(s, x + 0.18, 5.02, 2.58, 0.72)
        para(tf, head, size=13.5, color=INK, bold=True, first=True,
             space_after=2)
        para(tf, body, size=11, color=GRAY, space_after=0)
        x += 3.10

    tf = textbox(s, 0.85, 6.02, 11.6, 0.5)
    para(tf, "参数：DeepSeek-V4.1-Flash，温度 0.6，5 轮，每轮 8 条，"
             "搜索预算 1500 张图/条，置换 200 次，q = 0.1", size=11.5,
         color=GRAY, first=True, space_after=0)

    footer(s, 3, "橙色为模型决策，蓝色为程序计算")


# ------------------------------------------------------------------ 第 4 页
def slide_stage1(prs):
    s = blank(prs)
    title(s, "阶段一：27810 张图，九个不变量全部精确计算")

    bignum(s, 0.72, 1.52, 2.6, "27810", "张图")
    bignum(s, 3.32, 1.52, 2.6, "9", "个不变量，无一是估计值")
    bignum(s, 5.92, 1.52, 2.9, "0", "条已知结论被违反", color=GREEN)

    picture(s, "fig01_invariant_dist.png", 0.72, 2.72, w=6.30)
    caption(s, "各不变量在每一阶内部的分布比例", 0.72, 6.16, 6.30)

    box(s, 7.52, 2.72, 5.25, 3.48)
    tf = textbox(s, 7.78, 2.90, 4.72, 3.14)
    para(tf, "构造方式", size=14, color=ACCENT, bold=True, first=True,
         space_after=7)
    para(tf, "n ≤ 8：完全枚举并去重", size=12.5, space_after=2)
    para(tf, "各阶图数 1、2、4、11、34、156、1044、12346，"
             "与 OEIS 一致", size=11, color=GRAY, space_after=9)
    para(tf, "n = 9–12：采样加结构化族", size=12.5, space_after=2)
    para(tf, "完全多部图、Mycielski 扩张、Kneser 图、"
             "多档正则图", size=11, color=GRAY, space_after=9)
    para(tf, "正确性校验", size=14, color=ACCENT, bold=True, space_after=7)
    para(tf, "χ+α≤n+1、Reed、Brooks、α+ω≤n+1 四条，"
             "违反数全为 0", size=11, color=GRAY, space_after=0)

    footer(s, 4, "色数、独立数、团数都是 NP-难，全部用分支定界精确求解，不用启发式")


# ------------------------------------------------------------------ 第 5 页
def slide_stage2(prs):
    s = blank(prs)
    title(s, "阶段二：线性规划能复现已知界，搜索策略决定代价")

    picture(s, "fig06_lp_recovery.png", 0.62, 1.62, w=5.20)
    caption(s, "五条已知结论被自动复现", 0.62, 3.86, 5.20)

    picture(s, "fig07_refute_curve.png", 6.15, 1.58, w=6.30)
    caption(s, "三类策略命中反例所需的中位预算（越靠左越省）",
            6.15, 5.10, 6.30)

    tf = textbox(s, 0.72, 4.22, 5.15, 2.30)
    para(tf, "目标函数改了三次才复现出来", size=14, color=ACCENT, bold=True,
         first=True, space_after=6)
    para(tf, "只最小化常数项，会偏好 χ ≤ n 这类弱形式；"
             "改为最小化平均松弛后，系数才能被推到 1。",
         size=11.5, color=GRAY, space_after=0)

    tf = textbox(s, 0.72, 5.54, 5.15, 1.20)
    para(tf, "三类策略各有有效区间", size=14, color=ACCENT, bold=True,
         first=True, space_after=6)
    para(tf, "χ ≤ ω+1 只有结构化族找得到（中位 50 张图），"
             "随机图八次全落空。", size=11.5, color=GRAY, space_after=0)

    footer(s, 5, "Grötzsch 反例由结构化族在预算 45 内找到")


# ------------------------------------------------------------------ 第 6 页
def slide_stage3(prs):
    s = blank(prs)
    title(s, "阶段三：五轮闭环，产出三条在测试集上成立的不等式")

    bignum(s, 0.72, 1.46, 2.3, "26", "次模型调用")
    bignum(s, 3.02, 1.46, 2.3, "40", "条提议")
    bignum(s, 5.32, 1.46, 2.3, "5", "条被推翻")
    bignum(s, 7.62, 1.46, 2.3, "3", "条通过测试集", color=GREEN)

    picture(s, "fig11_agent_funnel.png", 0.62, 2.56, w=6.45)
    caption(s, "五轮中候选的逐轮去留", 0.62, 5.14, 6.45)

    box(s, 7.42, 2.56, 5.35, 3.40)
    tf = textbox(s, 7.68, 2.74, 4.82, 3.08)
    para(tf, "保留下来的三条", size=14, color=GREEN, bold=True, first=True,
         space_after=9)
    for line, note in [("α ≤ n − ν", "取等比例 0.32"),
                       ("α ≤ n − ω + 1", "0.018"),
                       ("χ ≤ ρ + 1", "0.005")]:
        p = para(tf, line, size=17, color=INK, bold=True, space_after=1)
        para(tf, note, size=11, color=GRAY, space_after=8)
    para(tf, "事后核对：三条都是已知结论。", size=12.5, color=ORANGE,
         bold=True, space_after=4)
    para(tf, "第三条即 Wilf 1967 定理 χ ≤ 1 + λmax。"
             "系统独立地重新发现了它。", size=11, color=GRAY,
         space_after=0)

    footer(s, 6, "三条 p 值均为 0.005，即 200 次置换中零分布从未达到观测值")


# ------------------------------------------------------------------ 第 7 页
def slide_finding(prs):
    s = blank(prs)
    title(s, "一个比结果更重要的发现：反例搜索在难例上近乎失效")

    picture(s, "fig14_injection.png", 0.62, 1.78, w=6.95)
    caption(s, "三十条已知为假的命题上的检出率", 0.62, 4.42, 6.95)

    tf = textbox(s, 7.90, 1.72, 4.90, 4.6)
    para(tf, "怎么测的", size=14, color=ACCENT, bold=True, first=True,
         space_after=6)
    para(tf, "从数据里筛出“整份数据集上至多 5 张反例、"
             "且反例阶数 ≥ 9”的假命题，共 30 条。",
         size=11.5, color=GRAY, space_after=12)

    para(tf, "结果", size=14, color=ORANGE, bold=True, space_after=6)
    para(tf, "预算扩大 60 倍，检出率只从 0.27 升到 0.30。",
         size=11.5, color=GRAY, space_after=4)
    para(tf, "只有 1 张反例的 18 条命题，检出率 0.02。",
         size=11.5, color=GRAY, space_after=12)

    para(tf, "所以", size=14, color=ACCENT, bold=True, space_after=6)
    para(tf, "“没找到反例”在难例上几乎不提供信息。"
             "瓶颈不在算力，在搜索分布的支撑集。",
         size=11.5, color=GRAY, space_after=0)

    footer(s, 7, "这条结论已改写报告中对整条流水线的解读：两道关卡的信息量并不相同")


# ------------------------------------------------------------------ 第 8 页
def slide_ablation(prs):
    s = blank(prs)
    title(s, "消融：模型的贡献还没有被证明")

    picture(s, "fig12_ablation.png", 0.62, 1.74, w=5.95)
    caption(s, "模型提议与随机提议的四项指标", 0.62, 4.62, 5.95)

    tf = textbox(s, 6.95, 1.72, 5.80, 4.5)
    para(tf, "第一次跑，随机组四项全赢", size=14, color=ORANGE,
         bold=True, first=True, space_after=6)
    para(tf, "查保留清单才发现，随机组抽到大量 ω ≤ χ、δ ≤ Δ "
             "这类由定义直接成立的恒真式。", size=11.5, color=GRAY,
         space_after=12)

    para(tf, "补上 35 条基本事实，两组用同一剔除规则", size=14,
         color=ACCENT, bold=True, space_after=6)
    para(tf, "结论随之翻转：通过筛选 2.33 对 1.33，"
             "模型组反超，但三组种子只胜两次。", size=11.5, color=GRAY,
         space_after=12)

    para(tf, "如实报告", size=14, color=ACCENT, bold=True, space_after=6)
    para(tf, "样本不足以支撑“模型优于随机”，报告中不作此声称。"
             "两次翻转的真正价值是暴露了检查器的漏洞。",
         size=11.5, color=GRAY, space_after=0)

    footer(s, 8, "“什么算有信息量”本身是实验的一部分，它随检查器的改进而移动")


# ------------------------------------------------------------------ 第 9 页
def slide_next(prs):
    s = blank(prs)
    title(s, "下一步：让智能体自己跑一周，但瓶颈不在时间",
          sub="可行性判断与设计要点")

    tf = textbox(s, 0.72, 1.66, 6.05, 4.9)
    para(tf, "可行，需要四个工程件", size=14, color=GREEN, bold=True,
         first=True, space_after=8)
    for head, body in [
        ("断点续跑", "每轮落盘，进程被杀后从上次状态继续"),
        ("去重账本", "已提形式、已推翻、恒真式三张表，跨轮次持久化"),
        ("预算上限", "按小时限词元、按天限评估图数，超限自动降档"),
        ("自动日报", "每日汇总新增候选与推翻记录，供人工抽检"),
    ]:
        para(tf, f"· {head}　{body}", size=11.5, color=GRAY, space_after=7)

    box(s, 7.05, 1.66, 5.72, 2.62, fill=WARM)
    tf = textbox(s, 7.32, 1.86, 5.18, 2.26)
    para(tf, "但真正的瓶颈不是时间", size=14, color=ORANGE, bold=True,
         first=True, space_after=7)
    para(tf, "形式空间共 2304 条，穷举上界只有 34 条能通过全部关卡；"
             "智能体五轮已提出 25 条互异形式。",
         size=11.5, color=GRAY, space_after=5)
    para(tf, "照现在的设定跑一周，几小时内就会饱和，剩下的时间在重复。",
         size=11.5, color=GRAY, space_after=0)

    tf = textbox(s, 7.05, 4.48, 5.72, 2.1)
    para(tf, "所以长期运行必须同时扩张空间", size=14, color=ACCENT,
         bold=True, first=True, space_after=7)
    for line in ["预测子 2 个 → 3 个",
                 "加入乘积项与比值项",
                 "图上到 n = 13–15，用上下界代替精确值"]:
        para(tf, f"· {line}", size=11.5, color=GRAY, space_after=4)

    footer(s, 9, "汇报后推送 GitHub；代码、数据集、14 张图表与全部轨迹均已提交")


def main() -> None:
    prs = new_deck()
    slide_cover(prs)
    slide_problem(prs)
    slide_route(prs)
    slide_stage1(prs)
    slide_stage2(prs)
    slide_stage3(prs)
    slide_finding(prs)
    slide_ablation(prs)
    slide_next(prs)
    prs.save(OUT)
    print(f"已生成 {OUT}，共 {len(prs.slides._sldIdLst)} 页")


if __name__ == "__main__":
    main()
