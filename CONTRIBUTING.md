# Contributing

感谢你考虑为 ClaudeX 做贡献。这个项目涉及账号会话、Cookie、API Key 和网络请求行为，提交前请特别注意不要泄露任何敏感信息。

## 开始之前

1. Fork 本仓库并创建新分支。
2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 从 `.env.example` 创建本地配置：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

## 分支命名

建议使用下面的格式：

- `feat/short-description`
- `fix/short-description`
- `docs/short-description`
- `refactor/short-description`

## 提交要求

- 保持改动范围清晰，避免把无关格式化和功能改动混在一起。
- 不要提交 `.env`、`accounts.json`、`accounts*.json`、抓包文件、日志或任何 Cookie/API Key。
- 修改网络请求逻辑时，请说明变更原因和兼容性影响。
- 修改 CLI 参数或配置项时，请同步更新 `README.md` 和 `.env.example`。
- 如果修复 bug，请尽量描述复现步骤和修复后的验证方式。

## Pull Request

提交 PR 时建议包含：

- 改动摘要。
- 测试或手动验证结果。
- 是否影响现有配置项、账号文件格式或命令行参数。
- 相关 issue 链接，如果有。

## 代码风格

- Python 代码保持简单直接，优先沿用现有模块结构。
- 新增函数应有清晰命名，复杂流程可添加简短注释。
- 对外部接口响应的解析要保守处理，避免字段缺失导致整个流程崩溃。
- 并发写文件时继续使用现有锁机制，避免破坏 `accounts.json`。

## 安全注意事项

- 不要在 issue、PR、截图或日志里粘贴真实邮箱、会话 Cookie、API Key、代理凭据或完整响应体。
- 示例数据请使用占位符，例如 `example@domain.com`、`sessionKey`、`mk_your_api_key_here`。
- 如果发现敏感信息已经提交，请立即移除并轮换对应凭据。

## License

通过提交贡献，你同意你的贡献将按照本项目的 MIT License 授权。
