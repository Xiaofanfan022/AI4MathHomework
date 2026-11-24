# 中期汇报材料

2026 年 11 月 25 日，5 分钟。

```
presentation/
  build_slides.py   生成脚本（九页，16:9）
  midterm.pptx      幻灯片
  讲稿.md           逐页讲稿，按 300 秒排
```

## 重新生成

```powershell
$py = "C:\Users\ASUS\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py presentation\build_slides.py
```

系统自带的 python 没有 python-pptx，必须用上面这个解释器。

## 时间分配

| 页 | 内容 | 秒 |
|---|---|---|
| 1 | 封面 | 8 |
| 2 | 研究问题 | 58 |
| 3 | 技术路线 | 38 |
| 4 | 阶段一：数据 | 32 |
| 5 | 阶段二：基线与搜索 | 35 |
| 6 | 阶段三：接入模型 | 45 |
| 7 | 一个更重要的发现 | 32 |
| 8 | 消融 | 24 |
| 9 | 后续工作 | 28 |

合计 300 秒。若现场超时，优先压缩第 4、8 页——这两页的内容报告里都有，
口头带过即可。

## 排版上的两个坑

**形状带主题阴影。** `shape.shadow.inherit = False` 只写一个空的
`effectLst`，形状仍然带着 `<p:style>`，其中的 `effectRef` 会让渲染器
套用主题阴影。必须把 `style` 节点整个删掉，见 `_strip_style`。

**χ 与拉丁字母 X 几乎同形。** 微软雅黑里的希腊字母与 `≤ ≥` 等符号
又细又小。`_segments()` 逐字符切段，希腊字母与数学符号用 Cambria Math
并设斜体，中文仍用雅黑。调用处不必关心，`para()` 内部已处理。

## 数字来源

- 数据集 27810 张、九不变量精确：`crp_agent/data/dataset_all.csv`
- 四条已知结论零违反：`python -m crp_agent.validate_dataset`
- 五条已知界被复现：`crp_agent/figures/fig06_lp_recovery.png`
- 三类策略对比：`crp_agent/runs/refute_table.json`
- 智能体 26 次调用、40 条提议、3 条保留：
  `crp_agent/runs/agent_20261121_141452/result.json`
- 穷举上界 34 条：`crp_agent/runs/ceiling_20261121_141400/summary.json`
- 注入难例检出率：`crp_agent/runs/inject_20261121_145649/summary.json`
- 消融 2.33 对 1.33：`crp_agent/runs/ablation_20261121_141449/summary.json`
