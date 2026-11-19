# 报告工程说明

本目录是课程作业报告的 LaTeX 工程，输出 `main.pdf`。

## 目录结构

```
report/
├── main.tex              主文件：导言区、标题页、摘要、目录、正文装配
├── build.ps1             一键编译脚本
├── sections/
│   ├── 01-problem.tex    第 1 节：研究问题的提出
│   ├── 02-background.tex 第 2 节：背景与相关工作
│   ├── 03-formulation.tex 第 3 节：问题的形式化
│   ├── 04-openness.tex   第 4 节：问题为何未解决
│   ├── 05-roadmap.tex    第 5 节：技术路线
│   └── references.tex    参考文献
├── texmf/                手动补装的宏包（TEXMFHOME，不提交）
└── .texmf-var/           自建的 xelatex format（TEXMFVAR，不提交）
```

## 编译

```powershell
cd report
.\build.ps1
```

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

## 当前进度

已完成第 1–5 节与参考文献（问题陈述、背景、形式化、困难分析、技术路线）。
尚未包含实验数据与结论，待智能体实现后补入第 6 节（实验）与第 7 节（讨论）。
