# 中期汇报材料

2026 年 11 月 25 日，5 分钟，10 页。

```
presentation/
  midterm.pptx      幻灯片（含逐页演讲备注）
  讲稿.md           逐页讲稿，按 300 秒排
```

## 怎么改

这一版由 ppt-master 生成，源文件是 `projects/midterm_20261124/svg_output/` 下的
十张 SVG（`01_cover.svg` … `10_next.svg`），设计规格在同目录的
`design_spec.md` 与 `spec_lock.md`。

改稿流程（顺序不能颠倒）：

```powershell
$env:PATH = "E:\AI4MathAgentHomework\.pyshim\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"
$S = ".dsh\skills\ppt-master\scripts"

# 1. 改 svg_output/*.svg
# 2. 展开图标、扁平化文本
python3 (Join-Path $S "finalize_svg.py") "projects\midterm_20261124"
# 3. 质量门禁（必须带 --json，否则全通过也返回 1）
python3 (Join-Path $S "svg_quality_checker.py") "projects\midterm_20261124" --canonical-authoring --stage final --json
# 4. 导出
python3 (Join-Path $S "svg_to_pptx.py") "projects\midterm_20261124"
```

导出会检查门禁报告是否为 `passed` 且未过期；改过 SVG 不重跑第 3 步会报
`found stale`。

## 时间分配

| 页 | 内容 | 秒 |
|---|---|---|
| 1 | 封面 | 8 |
| 2 | 问题：从九个不变量里猜不等式 | 45 |
| 3 | 生成容易，筛选难 | 28 |
| 4 | 提出—反驳—筛选的闭环 | 36 |
| 5 | 地基：27 810 张图 | 26 |
| 6 | 不接模型也能复现已知结论 | 34 |
| 7 | 40 条提议，3 条活到最后 | 38 |
| 8 | 找不到反例可能什么也没说明 | 34 |
| 9 | 一个差点得出错误结论的消融 | 26 |
| 10 | 接下来可以往哪走 | 25 |

合计 300 秒。若现场超时，优先压缩第 5、9 页——这两页的内容报告里都有，
口头带过即可。

## 排版上踩过的三个坑

**导出器按第一行内容宽度决定文本框宽度。** 一个 `<text>` 里用 `<tspan dy>`
堆多行时，后面比第一行长的行会被 LibreOffice 自动折行并溢出。所以多行
文本要**每行一个独立 `<text>` + 独立 `<g>`**，bounds 上下各留 32–34px。

**同级顶层组重叠 > 1px 即门禁失败。** 分隔线不能单独成组，要放进相邻组的
bounds 内，或让相邻组边界让开。

**雅黑里的 χ 与拉丁字母 X 几乎同形。** 含希腊字母或数学符号的 `<text>` 要
显式写 `font-family="Cambria Math, Arial, SimHei, sans-serif"`，否则渲染出来
看不出是希腊字母。

## 数字来源

- 数据集 27 810 张、九不变量精确：`crp_agent/data/dataset_all.csv`
- 四条已知结论零违反：`python -m crp_agent.validate_dataset`
- 五条已知界被复现、三策略对比：
  `crp_agent/runs/ceiling_20261121_141400/summary.json`
- 智能体 26 次调用、40 条提议、推翻 5、保留 3：
  `crp_agent/runs/agent_20261121_141452/trace.jsonl`
- 穷举上界 34 条、其中 32 条在测试集成立：
  `crp_agent/runs/ceiling_20261121_141400/summary.json`
- 注入难例检出率：`crp_agent/runs/inject_20261121_145649/summary.json`
- 消融 2.33 对 1.33：`crp_agent/runs/ablation_20261121_141449/summary.json`
