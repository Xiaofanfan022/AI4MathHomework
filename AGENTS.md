# 工作区约定

## ppt-master skill

已安装：`.dsh/skills/ppt-master` → 目录联接（junction）指向
`ppt-master/skills/ppt-master`（仓库 `https://atomgit.com/hugohe3/ppt-master`
的镜像克隆，版本 6.10.0）。更新时在 `ppt-master/` 里 `git pull` 即可，
skill 自动跟着更新。

### 运行 ppt-master 脚本必须用 PATH 前置的 python 垫片

系统 Python 3.13 看不到本目录的 `.deps`（里面是 cp312 的二进制轮子），
而且沙箱禁止写任何 site-packages。所以 **不要** 直接用 `python` / `python3`，
先用 `.pyshim/bin` 前置 PATH：

```powershell
$env:PATH = "E:\AI4MathAgentHomework\.pyshim\bin;$env:PATH"
python3 .dsh\skills\ppt-master\scripts\attribution_guard.py
```

`.pyshim/bin/python.cmd` 和 `python3.cmd` 会转发到 DSH 自带的 Python 3.12
运行时，并把 `PYTHONPATH` 指向 `.pyshim`，从而：

1. 把 `.deps`（190 个包，359 MB）加进 `sys.path`；
2. 修掉沙箱的临时目录权限问题（见下）。

等价写法：`.\.pyshim\pyppt.cmd <script.py> [args...]`。

### `.pyshim/sitecustomize.py` 在修什么

这个工作区的 Windows 沙箱令牌有两个权限毛病，会让 ppt-master（以及任何
pip / venv / tempfile 用户）失败：

- 用 `mode=0o700` 建的目录，令牌之后**写不进去也删不掉**；
- `tempfile.mkdtemp()` 硬编码 `os.mkdir(file, 0o700)`，所以 pip 的
  `pip-unpack` / `pip-build-tracker` / `pip-install` 全部变成只读，
  `ensurepip` 的 `_resetperms` 也直接 `PermissionError [WinError 5]`。

`sitecustomize.py` 把 `os.mkdir` 的受限 mode、`tempfile.mkdtemp` 和
`tempfile._resetperms` 统一改成 `0o777`，问题消失。只在 `PYTHONPATH`
包含 `.pyshim` 时生效。

已踩过的坑：`.pptx-build-*` 工作目录由
`scripts/svg_to_pptx/pptx_package/builder.py:5448` 用 `mkdir(mode=0o700)`
创建，补丁前会留下删不掉的残留目录。

### 目录约定

- `ppt-master/` — 上游仓库（不要在这里放项目产物）
- `.deps/` — ppt-master 的 Python 依赖（可重建，不必提交）
- `.pyshim/` — Python 垫片（应当提交）
- `projects/` — ppt-master 生成的项目工作区
