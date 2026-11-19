# 编译 basel.tex（需要 XeLaTeX + ctex 宏包）
#
# 本机 TinyTeX 的格式文件（format）比宏包旧，直接运行 xelatex 会报
#   "Mismatched LaTeX support files detected"
# 而 TinyTeX 默认的 texmf-var 目录在工作区之外、沙箱不可写。
# 因此这里把 TEXMFVAR 指向本文件夹内的 .texmf-var，并在首次编译前
# 用 fmtutil-user 重建一次格式文件。
#
# 用法：  powershell -ExecutionPolicy Bypass -File .\build.ps1
#         powershell -ExecutionPolicy Bypass -File .\build.ps1 -Clean

param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

if ($Clean) {
    Remove-Item -Force -ErrorAction SilentlyContinue `
        basel.aux, basel.log, basel.out, basel.toc, basel.pdf
    Write-Host '已清理编译产物。'
    return
}

# 让 TeX 使用本地的可变数据目录，避免写入 AppData
$env:TEXMFVAR    = Join-Path $here '.texmf-var'
$env:TEXMFCONFIG = $env:TEXMFVAR
New-Item -ItemType Directory -Force -Path $env:TEXMFVAR | Out-Null

# 首次运行时重建 xelatex 格式
if (-not (Test-Path (Join-Path $env:TEXMFVAR 'web2c\xetex\xelatex.fmt'))) {
    Write-Host '首次编译，正在重建 xelatex 格式文件……'
    & fmtutil-user --byfmt xelatex | Out-Null
}

# 跑两遍以解析目录与交叉引用
for ($i = 1; $i -le 2; $i++) {
    Write-Host "== xelatex 第 $i 遍 =="
    & xelatex -interaction=nonstopmode -halt-on-error basel.tex | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '编译失败，请查看 basel.log。'
        exit $LASTEXITCODE
    }
}

if (Test-Path basel.pdf) {
    $kb = [math]::Round((Get-Item basel.pdf).Length / 1KB, 1)
    Write-Host "完成：basel.pdf ($kb KB)"
} else {
    Write-Host '未生成 PDF，请查看 basel.log。'
    exit 1
}
