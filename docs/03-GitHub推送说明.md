# GitHub 推送说明

仓库地址：<https://github.com/Xiaofanfan022/AI4MathHomework>

## 一、本机推送会遇到的问题

本机的 `C:\WINDOWS\System32\drivers\etc\hosts` 里有 102 条 `127.0.0.1` 记录，
把 `github.com`、`api.github.com`、`raw.githubusercontent.com` 等域名全部指向
本机回环地址。文件头标记为 `# Steam++ Start`，是 Steam++（Watt Toolkit）
卸载后留下的残留，但程序本身已经不在了，所以这些域名全都不通。

表现是：

- 浏览器打不开 GitHub；
- `git push` 报 `Failed to connect to github.com port 443`；
- Python `requests` 报 `SSLCertVerificationError`。

**解决办法有两种，任选其一。**

### 办法 A：清理 hosts（推荐，一次解决）

1. 用管理员身份打开 PowerShell；
2. 先备份：`Copy-Item C:\WINDOWS\System32\drivers\etc\hosts D:\hosts.bak`；
3. 用记事本以管理员身份打开 hosts，删除 `# Steam++ Start` 到
   `# Steam++ End` 之间的全部内容（或删掉所有含 `github` 的行）；
4. 保存，然后 `ipconfig /flushdns`。

### 办法 B：不改 hosts，用本地转发代理

如果不能拿到管理员权限，可以让一个本地程序把连接直接送到 GitHub 的真实 IP，
绕开 hosts 的错误解析。原理是只做 TCP 转发、不碰 TLS，所以证书仍然是
GitHub 的真实证书，安全性不受影响。

代理脚本见本仓库外的 `.tmp_gh_proxy.py`（临时工具，未纳入版本库）。启动：

```powershell
python -u .tmp_gh_proxy.py 17893
```

然后所有 git 命令加两个参数：

```powershell
git -c http.sslBackend=openssl `
    -c http.proxy=http://127.0.0.1:17893 `
    push origin main
```

**两个必须加的配置项**：

- `http.sslBackend=openssl`：不加会报
  `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`。
  这是 Windows 凭据存储访问受限导致的，与网络无关。
- `http.proxy`：指向上面启动的本地代理端口。

**选 IP 的坑**：`20.205.243.168` 能完成 TLS 握手，但对 git 协议返回
**403 Forbidden**，看起来像是权限问题，其实是那个 IP 不可用。
`140.82.112.3`、`140.82.113.3`、`140.82.114.3`、`20.27.177.113`、
`4.237.22.38` 实测正常。

## 二、日常提交

```powershell
git add -A
git commit -m "说明这次改了什么"
git push
```

如果配置了办法 B 的代理，把 `http.proxy` 写进仓库配置就不用每次加：

```powershell
git config http.proxy http://127.0.0.1:17893
git config http.sslBackend openssl
```

## 三、安全约定

- `.env` 已在 `.gitignore` 中，**不会**进入版本库；仓库里只有
  `.env.example` 这个占位模板。
- 推送时不要把 Personal Access Token 写进 remote URL——那样会明文留在
  `.git/config` 里。用完后执行
  `git remote set-url origin https://github.com/Xiaofanfan022/AI4MathHomework.git`
  清理干净。
- Token 一旦在聊天、截图或代码里出现过，就应当作已泄露处理，去
  <https://github.com/settings/tokens> 吊销并重新生成。
