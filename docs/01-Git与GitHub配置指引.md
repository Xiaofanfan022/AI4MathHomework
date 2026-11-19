# Git 与 GitHub 配置指引

> 你的情况：**有 GitHub 账号，本机没装 Git**。
> 下面从安装一路走到第一次推送，照着做即可。

---

## 第 1 步：安装 Git

我已经用 winget 在后台帮你装了。装完后**必须新开一个终端**（当前终端读不到新的 PATH），然后验证：

```powershell
git --version
```

如果提示找不到命令，说明 PATH 没刷新，**重启一下这个应用**即可。

如果自动安装失败，手动下载：<https://git-scm.com/download/win>
安装时一路默认即可，只有一处建议改：**默认分支名**选 `main`。

---

## 第 2 步：配置身份（只需一次）

```powershell
git config --global user.name "你的名字"
git config --global user.email "你的GitHub注册邮箱"
```

> 邮箱要和 GitHub 账号绑定的一致，否则提交记录不会算到你头上。

建议再设两项，避免中文文件名变成乱码：

```powershell
git config --global core.quotepath false
git config --global init.defaultBranch main
```

---

## 第 3 步：选一种认证方式

### 方式 A：HTTPS + Personal Access Token（推荐，最省事）

GitHub 从 2021 年起**不再接受账号密码**，必须用 Token。

1. 打开 <https://github.com/settings/tokens> → **Generate new token (classic)**
2. Note 随便填（如 `AI4Math-homework`），Expiration 选 90 天
3. 勾选 **`repo`** 这一整个大类（作业只需要这个）
4. 生成后**立刻复制**，页面关掉就再也看不到了
5. 之后 `git push` 提示输入密码时，**粘贴这个 Token**（不是账号密码）

> Token 等同密码，不要写进代码、不要发给别人。Windows 的 Git 凭据管理器会帮你记住，只需输入一次。

### 方式 B：SSH Key（一劳永逸，但多几步）

```powershell
ssh-keygen -t ed25519 -C "你的GitHub注册邮箱"
# 一路回车（密码可留空）

# 查看公钥并复制全部内容
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

然后打开 <https://github.com/settings/keys> → **New SSH key** → 粘贴 → 保存。

验证：

```powershell
ssh -T git@github.com
# 看到 "Hi 你的用户名! You've successfully authenticated" 就成功了
```

---

## 第 4 步：在 GitHub 上建仓库

1. 打开 <https://github.com/new>
2. Repository name：`AI4Math-Agent`（或你喜欢的名字）
3. 可见性：**Public**（作业要求"个人自建 GitHub 账号"，公开便于老师查看）
4. **不要**勾选 "Add a README file"、".gitignore"、"license" —— 我们本地已经有了，勾了会导致首次推送冲突
5. 点 **Create repository**

---

## 第 5 步：本地初始化并首次推送

在项目根目录 `E:\AI4MathAgentHomework` 下执行：

```powershell
# 1. 初始化仓库
git init

# 2. 确认 .env 被正确忽略（这一步很重要，别跳过）
git status

# 3. 添加所有文件
git add .

# 4. 再检查一次：暂存区里绝对不能出现 .env
git status
```

> ⚠️ **关键检查点**：第 4 步的输出里**不应该有 `.env`**。
> 如果看到了 `.env`，立刻执行 `git rm --cached .env` 再继续。
> 一旦带密钥的提交被推上 GitHub，即使之后删除，历史记录里依然能翻出来。

```powershell
# 5. 首次提交
git commit -m "初始化：ReAct 智能体基础版本与周计划"

# 6. 关联远程仓库（把 YOURNAME 换成你的 GitHub 用户名）
git remote add origin https://github.com/YOURNAME/AI4Math-Agent.git

# 7. 推送
git push -u origin main
```

如果第 7 步报错 `src refspec main does not match any`，说明默认分支叫 `master`，改用：

```powershell
git branch -M main
git push -u origin main
```

---

## 第 6 步：日常提交节奏

这一周建议至少留下 **5 次有意义的提交**，让老师能看到迭代过程：

```powershell
git add .
git commit -m "feat: 接入 function calling，替换正则解析"
git push
```

提交信息用「类型: 说明」的格式，类型用这几个就够：

| 类型 | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `exp` | 实验（跑了一组对比、加了一个指标） |
| `docs` | 文档、报告 |
| `refactor` | 重构，不改行为 |

---

## 常见问题

**Q: `git push` 卡住或超时？**
国内访问 GitHub 有时不稳定。多试几次；或临时用代理：
```powershell
git config --global http.proxy http://127.0.0.1:你的代理端口
```

**Q: 不小心提交了 `.env` 怎么办？**
如果**还没推送**：
```powershell
git rm --cached .env
git commit --amend --no-edit
```
如果**已经推送了**：立刻去平台**吊销那个 Key**（这是唯一可靠的补救），然后再清理历史。

**Q: 中文文件名显示成 `\344\275\240`？**
执行 `git config --global core.quotepath false`。

**Q: 想忽略某个已经提交的文件？**
`.gitignore` 只对未跟踪文件生效。已跟踪的要先 `git rm --cached <文件>`。
