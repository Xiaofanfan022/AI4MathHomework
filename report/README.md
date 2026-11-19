# 报告工程说明

本目录是课程作业报告的 LaTeX 工程，输出 `main.pdf`。

## 目录结构

```
report/
├── main.tex              主文件：导言区、标题页、摘要、目录、正文装配
├── build.ps1             一键编译脚本（支持 -JobName 换输出名）
├── sections/
│   ├── 01-problem.tex    第 1 章：研究问题
│   ├── 02-background.tex 第 2 章：已有工作简述
│   ├── 03-method.tex     第 3 章：智能体设计（草稿）
│   ├── 04-evaluation.tex 第 4 章：如何判断做得好不好（草稿）
│   ├── 05-progress.tex   第 5 章：当前进度与后续计划
│   └── references.tex    参考文献
├── texmf/                手动补装的宏包（TEXMFHOME，不提交）
└── .texmf-var/           自建的 xelatex format（TEXMFVAR，不提交）
```

## 编译

```powershell
cd report
.\build.ps1
```

如果 `main.pdf` 正被阅读器打开，覆盖会失败并报
`xdvipdfmx:fatal: Unable to open "main.pdf"`。两种办法：

- 关掉阅读器后重跑；
- 或者换输出名：`.\build.ps1 -JobName main_v2`，再手动把 `main_v2.pdf` 改名。

或手动：

```powershell
cd report
$env:TEXMFHOME = "E:\AI4MathAgentHomework\report\texmf"
$env:TEXMFVAR  = "E:\AI4MathAgentHomework\report\.texmf-var"
xelatex -interaction=nonstopmode main.tex   # 跑两遍
```

## 环境说明（本机特有）

本机 TinyTeX 有两个问题，已绕过：

1. **`tlmgr` 失效**：报 `Cannot open HKCU for writing at .../TLWinGoo.pm line 586`，无法在线安装宏包。
   绕过方式：从阿里云 CTAN 镜像下载 tlnet 的 `.tar.xz` 直接解压到 `report/texmf`。
   脚本见仓库根目录的 `.tmp_texinstall.py`（未提交，可参考其逻辑）。

2. **format 版本不匹配**：系统 `xelatex.fmt` 是 2025-09 的，而 `texmf-dist` 里的
   `expl3.sty` 是 2026-01 的，编译时报 `Mismatched LaTeX support files detected`。
   绕过方式：`fmtutil-user --byfmt xelatex`，配合 `TEXMFVAR` 指向 `report/.texmf-var`，
   生成一份与当前宏包匹配的 format。`build.ps1` 会在缺失时自动执行。

换到其他机器（宏包齐全的 TeX Live 2025+）时，把 `build.ps1` 里的两个环境变量设置
删掉即可，不需要 `texmf/` 与 `.texmf-var/`。

## 写作约定

- 这是**课程报告**，不是学术论文。目标是让同学和老师看懂，不追求形式化程度。
- 数学符号只在必要处出现，能用自然语言说清就不用公式。
- 第 1 章（研究问题）与第 2 章（已有工作）已定稿；第 3–5 章是设计草稿，
  智能体实现后会大幅改写并补入实验数据。

## 当前进度

已完成五章与参考文献，共 15 页（正文 12 页）。尚无实验数据。
