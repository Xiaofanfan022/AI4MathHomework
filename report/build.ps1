# 编译报告（Windows / PowerShell）
#
# 用法：在 report 目录下执行
#     .\build.ps1
#
# 说明：
#   本机 TinyTeX 的 tlmgr 因无法写 HKCU 注册表而失效，缺失宏包被手动解压到
#   report\texmf（TEXMFHOME）。系统自带的 xelatex.fmt 与 texmf-dist 中的
#   expl3.sty 版本不匹配，故用 fmtutil-user 在 report\.texmf-var（TEXMFVAR）
#   下重建了一份 format。这两个环境变量必须在编译前设置，否则报
#   "Mismatched LaTeX support files detected"。

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$env:TEXMFHOME = Join-Path $here "texmf"
$env:TEXMFVAR  = Join-Path $here ".texmf-var"

if (-not (Test-Path (Join-Path $env:TEXMFVAR "web2c\xetex\xelatex.fmt"))) {
    Write-Host "未找到自建 format，正在生成..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $env:TEXMFVAR | Out-Null
    fmtutil-user --byfmt xelatex | Out-Null
}

Push-Location $here
try {
    # 跑两遍：第一遍生成 .aux/.toc，第二遍解析交叉引用与目录
    foreach ($pass in 1..2) {
        Write-Host "=== xelatex pass $pass ===" -ForegroundColor Cyan
        xelatex -interaction=nonstopmode -halt-on-error main.tex | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "编译失败，详见 main.log" -ForegroundColor Red
            Get-Content main.log -Tail 40
            exit 1
        }
    }
    Write-Host "`n生成 main.pdf" -ForegroundColor Green
    Get-Item main.pdf | Select-Object Name, Length, LastWriteTime
}
finally {
    Pop-Location
}
