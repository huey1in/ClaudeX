# ClaudeX

![Version](https://img.shields.io/badge/Version-0.2.0-0A0A0A?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Requests](https://img.shields.io/badge/Requests-HTTP%20Client-20232A?style=flat-square)
![CLI](https://img.shields.io/badge/CLI-Tool-0A0A0A?style=flat-square&logo=gnubash&logoColor=white)
![JSON](https://img.shields.io/badge/Data-JSON-000000?style=flat-square&logo=json&logoColor=white)
![Environment](https://img.shields.io/badge/Config-.env-4B5563?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

ClaudeX 是一个用于批量注册 Claude 账号、保存会话状态并查询账号用量的 CLI 工具。

项目仓库：[huey1in/ClaudeX](https://github.com/huey1in/ClaudeX)

> 注意：本项目会请求 `claude.ai` 。请确认你的使用方式符合相关服务条款、当地法律法规要求。

## 功能

- 批量注册账号：生成域名邮箱、发送 Claude magic link、读取验证邮件、换取会话 Cookie。
- 并发执行注册：通过 `-j/--concurrent` 控制并发数量。
- 保存账号记录：默认写入 `accounts.json`。
- 批量检查账号：读取账号 Cookie，查询账号状态、套餐和模型限制。
- 支持代理：注册请求可通过 `PROXY` 配置代理。
- 请求头自动生成：每个账号拥有稳定的请求身份标识和浏览器资料。
- 可选 SEPA 工作流：使用 `register --sepa` 时，每个账号注册成功后立即处理订阅步骤。

## 版本检查

当前版本：`0.2.0`。检查本地和 GitHub `main` 分支的远端版本：

```bash
python main.py --version
```

命令会先输出本地版本，再输出远端版本。远端版本较新时，还会列出该版本在 `version.json` 中记录的更新内容。网络不可用或远端版本文件无效时，本地版本仍会正常显示。

## 项目结构

```text
.
├── main.py                 # CLI 入口
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例
├── accounts.json           # 账号记录文件，本地敏感文件
├── version.json            # 版本号与版本更新内容
├── core/                   # 共享基础能力
│   ├── config.py           # 环境变量、请求头生成和代理配置
│   ├── console.py          # 彩色终端日志
│   ├── session.py          # requests Session 工具
│   └── version.py          # 本地及 GitHub 远端版本检查
├── account/                # 账号数据与状态查询
│   ├── storage.py          # 账号文件读写与账号池
│   └── check.py            # 账号状态和用量检查
├── registration/           # 账号注册
│   ├── moemail.py          # MoeMail API 客户端
│   └── register.py         # 注册流程
├── billing/                # Claude 和 Stripe 订阅工作流
└── tests/                  # 自动化测试
```

## 环境要求

- Python 3.9+
- 可访问的 MoeMail 服务
- MoeMail API Key

安装依赖：

```bash
pip install -r requirements.txt
```

## 配置

复制示例环境变量：

```bash
cp .env.example .env
```

Windows PowerShell 可以使用：

```powershell
Copy-Item .env.example .env
```

至少需要配置：

```env
MOEMAIL_API_KEY=mk_your_api_key_here
MOEMAIL_BASE_URL=https://your-moemail-instance.example.com
```

常用配置项：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MOEMAIL_API_KEY` | 空 | MoeMail API Key |
| `MOEMAIL_BASE_URL` | 空 | MoeMail 服务地址 |
| `PROXY` | 空 | 注册请求使用的代理，例如 `socks5h://user:pass@host:port` |
| `REGISTER_COUNT` | `1` | 默认注册数量 |
| `REGISTER_CONCURRENT` | `1` | 默认并发数量 |
| `ACCOUNTS_FILE` | `accounts.json` | 账号记录文件路径 |

Claude 服务地址、请求身份标识和浏览器资料均由代码管理，不接受 `.env` 覆盖。

## 使用方法

### 注册账号

注册 1 个账号：

```bash
python main.py register
```

注册 10 个账号，并发 3 个任务：

```bash
python main.py register -n 10 -j 3
```

注册成功后立即处理每个账号的 SEPA Direct Debit 订阅步骤：

```bash
python main.py register -n 3 -j 3 --sepa
```

`--sepa` 不会打开或操作浏览器。每个账号注册成功后会立即在主线程中处理订阅；使用 `-j/--concurrent` 时，注册仍然并发执行，订阅按账号完成顺序串行处理：

- 仅当 Claude 返回 `checkout_flow=cassia` 或 `checkout_flow=custom` 时创建付款会话；`legacy` 组织会在发起 Checkout POST 前明确失败。
- 每次提交后先记录为 `pending`，随即查询一次异步状态，再继续处理后续成功注册的账号。SEPA 最终结果可能需要由 Claude Billing 或邮件稍后更新。

使用指定账号文件：

```bash
python main.py --accounts data/accounts.json register -n 5
```

注册成功后，账号记录会追加写入 `accounts.json`。

### 检查账号状态

检查默认账号文件：

```bash
python main.py check
```

检查指定账号文件：

```bash
python main.py --accounts data/accounts.json check
```

检查命令会输出每个账号的状态、套餐和部分模型限制。如果 Cookie 失效，会标记为过期或错误。

## 账号文件格式

`accounts.json` 是一个 JSON 数组，每条记录大致如下：

```json
[
  {
    "email": "example@domain.com",
    "uuid": "account_uuid",
    "email_address": "example@domain.com",
    "org_uuid": "organization_uuid",
    "org_name": "Organization Name",
    "cookies": {
      "sessionKey": "..."
    },
    "saved_at": "2026-07-10T10:00:00Z"
  }
]
```

该文件包含登录 Cookie，等同于账号会话凭据。请只保存在本机可信目录，不要上传到代码仓库或发送给他人。

## 工作流程

注册流程位于 `registration/register.py`：

1. 检查当前出口 IP。
2. 从 MoeMail 获取可用邮箱域名。
3. 创建临时邮箱。
4. 查询 Claude 登录方式。
5. 发送 magic link。
6. 轮询临时邮箱并提取 nonce。
7. 验证 magic link，保存账号信息和 Cookie。

检查流程位于 `account/check.py`：

1. 读取 `accounts.json`。
2. 用保存的 Cookie 创建会话。
3. 请求 Claude 账号和组织访问接口。
4. 输出账号状态、套餐和模型限制。

## 注意事项

- `.env` 和 `accounts.json` 都是敏感文件，已在 `.gitignore` 中排除时也不要手动提交。
- 并发注册可能触发目标服务的频率限制，建议从较小并发开始。
- `check` 命令当前使用直连请求，不读取 `PROXY`。
- Claude Web 接口可能随时间变化；如果出现非 JSON 响应、401、403、429 或接口字段缺失，需要根据实际响应更新代码。

## 开发

本项目没有额外构建步骤。常用命令：

```bash
python main.py --help
python main.py --version
python main.py register -n 1
python main.py check
python -m unittest discover -s tests -v
python -m ruff check main.py core account registration billing tests
```

建议在修改网络请求逻辑后，至少验证：

- `.env` 能正确加载。
- MoeMail 配置接口可用。
- 注册失败时不会破坏已有 `accounts.json`。
- `check` 能正确识别正常、过期和错误账号。

发布新版本时，同时更新 `version.json` 中的 `version` 和 `changes`，并同步修改 README 顶部的版本徽章及本节版本号。

## Contributing

欢迎提交 issue 和 pull request。参与贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，并确认不会提交 `.env`、`accounts.json`、Cookie、API Key 或代理凭据。

## License

本项目基于 [MIT License](LICENSE) 开源。
