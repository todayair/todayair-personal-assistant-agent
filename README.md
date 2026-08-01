# Personal Assistant Agent

基于 [Pydantic AI](https://ai.pydantic.dev/) + Harness 构建的交互式命令行 AI 助手，集成了联网搜索、文件操作、Shell 执行、GitHub / 国内邮箱 MCP、长期记忆（向量检索）、以及待办 / 笔记 / 提醒等个人效率功能。

## 功能特性

- **多能力 Agent**：联网搜索（WebSearch）、文件读写（FileSystem）、执行系统命令（Shell）
- **MCP 外部工具**：通过 `mcp_config.json` 挂载 GitHub 搜索等外部工具集
- **国内邮箱（可选）**：QQ / 163 / 126 / Outlook 收发与管理（IMAP/SMTP + 授权码，国内直连，可搜索 / 阅读 / 发送 / 回复 / 移动 / 删除）
- **长期记忆系统**：ChromaDB 向量数据库 + 语义检索，跨对话记住用户偏好与信息
- **待办 / 笔记 / 提醒**：LLM 可直接用自然语言操作，数据统一存储到 MySQL（首次启动自动建库建表，初始化失败即报错终止）
- **后台提醒**：提醒到点自动在终端弹出通知，无需打断对话
- **历史会话**：每轮对话自动保存，支持按关键词查找历史记录，并可从任一会话恢复上下文继续对话（统一存 MySQL `agent_history` 库）
- **上下文自动压缩**：TieredCompaction 分层策略（清旧工具结果 → LLM 摘要），长对话不爆上下文
- **Prompt Caching**：DeepSeek 前缀缓存自动生效，节省 token
- **隐私保护**：手机号 / 密码 / 银行卡 / 身份证等敏感信息自动跳过，不写入记忆

## 技术栈

| 组件 | 用途 |
|------|------|
| Python 3.10+ | 运行环境 |
| pydantic-ai ≥ 2.20 | Agent 框架（工具、能力、MCP） |
| pydantic-ai-harness ≥ 0.14 | FileSystem / Shell / 上下文压缩 |
| ChromaDB + sentence-transformers | 向量记忆存储与语义检索 |
| python-dotenv | 环境变量加载 |
| fastmcp ≥ 3.4 | 进程内 FastMCP 服务（国内邮箱） |
| imap_tools ≥ 1.7 | 国内邮箱 IMAP 收信（QQ / 163 / 126 / Outlook） |
| PyMySQL | MySQL 存储驱动（个人数据 + 历史会话，唯一存储后端） |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`（或参考下表手动创建），填入你的 Key：

```bash
# .env 最小配置
LLM_MODEL=deepseek:deepseek-v4-flash
DEEPSEEK_API_KEY=sk-xxxx
SYSTEM_PROMPT=你是一个友好的 AI 助手，可以用多种工具帮助用户解决问题。
```

### 3. 启动对话

```bash
python agent.py
```

首次启动会自动下载嵌入模型（`intfloat/multilingual-e5-small`，约 235MB），请耐心等待。

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_MODEL` | ✅ | - | 模型标识，如 `deepseek:deepseek-v4-flash` |
| `DEEPSEEK_API_KEY` | ✅ | - | DeepSeek API Key |
| `SYSTEM_PROMPT` | ✅ | - | 系统提示词 |
| `SUMMARY_MODEL` | 否 | 同主模型 | 上下文压缩摘要用模型（可设更便宜的模型省成本） |
| `SUMMARY_TARGET_TOKENS` | 否 | `100000` | 压缩目标 token 上限 |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | 否 | - | GitHub MCP 工具的 Personal Access Token |
| `EMAIL_PROVIDER` | 否 | `qq` | 国内邮箱服务商：`qq` / `163` / `126` / `outlook` / `custom` |
| `EMAIL_ADDRESS` | 否 | - | 国内邮箱地址（与授权码一起填写后启用邮箱工具） |
| `EMAIL_PASSWORD` | 否 | - | 邮箱授权码（网页端开启 IMAP/SMTP 后生成，不是登录密码） |
| `EMAIL_USERNAME` | 否 | 同地址 | IMAP/SMTP 登录用户名（一般无需设置） |
| `EMAIL_IMAP_HOST` / `EMAIL_IMAP_PORT` | 否 | 按预设 | 自定义 IMAP 服务器（`custom` 时必填） |
| `EMAIL_IMAP_MODE` | 否 | 按端口 | IMAP 连接模式：`ssl` / `starttls` / `plain`（默认 993=ssl，其他=starttls） |
| `EMAIL_SMTP_HOST` / `EMAIL_SMTP_PORT` | 否 | 按预设 | 自定义 SMTP 服务器（`custom` 时必填） |
| `EMAIL_SMTP_STARTTLS` | 否 | 按预设 | `true` 用 STARTTLS（587 端口），`false` 用 SSL（465 端口） |
| `EMAIL_ATTACHMENT_DIR` | 否 | `.agent_email_attachments` | 邮件附件下载保存目录 |
| `MEMORY_ENABLED` | 否 | `true` | 是否启用外部记忆 |
| `MEMORY_TOP_K` | 否 | `3` | 每次对话注入的记忆条数 |
| `MEMORY_MIN_SIMILARITY` | 否 | `0.4` | 记忆注入相似度阈值，低于则丢弃 |
| `MEMORY_DIR` | 否 | `.agent_memory` | 向量库存储目录 |
| `MEMORY_COLLECTION` | 否 | `agent_memory` | 向量库 collection 名 |
| `MYSQL_ENABLED` | ✅ | `true` | 启用 MySQL 存储（必填） |
| `MYSQL_HOST` | ✅ | `127.0.0.1` | MySQL 地址（必填） |
| `MYSQL_PORT` | 否 | `3306` | MySQL 端口 |
| `MYSQL_USER` | 否 | `root` | MySQL 用户 |
| `MYSQL_PASSWORD` | ✅ | - | MySQL 密码（必填） |
| `MYSQL_DATABASE` | 否 | - | 显式指定库名；未设置时个人数据用 `agent_personal` 库、历史会话用 `agent_history` 库 |

> 说明：`.env` 中所有变量均可用 `${VAR}` 占位符在 `mcp_config.json` 中引用。

## CLI 命令

| 命令 | 功能 |
|------|------|
| `/help` | 查看全部指令与已注册能力（`/tools` 为兼容别名） |
| `/memory` | 查看记忆状态与隐私规则 |
| `/forget` | 清空所有长期记忆 |
| `/todos` | 查看待办列表 |
| `/notes` | 查看笔记列表 |
| `/reminders` | 查看提醒列表 |
| `/history [关键词]` | 查看历史会话（支持按标题/内容关键词搜索） |
| `/load <会话ID>` | 加载历史会话并继续对话 |
| `/new` | 开始一个新会话 |
| `/clear` | 清空当前对话历史并开始新会话 |
| `/exit` | 退出程序（`exit` / `quit` 亦可） |
| `Ctrl+C` | 仅用于复制文本（先选中）；不会退出程序，退出请用 `/exit` |

## 待办 / 笔记 / 提醒

三种个人效率数据统一存储到 MySQL 的 `agent_personal` 库，历史会话存储到 `agent_history` 库；首次启动自动建库建表，并把旧版 `.agent_personal/` 与 `.agent_history/` 目录下的存量数据一次性迁移进库（仅迁移）。MySQL 初始化失败直接报错终止启动。数据重启不丢失，并注册为 10 个 LLM 工具，可直接用自然语言操作：

```
"提醒我 30 分钟后喝水"    → add_reminder(text, when)
"记一下：周三交报告"      → add_todo(text)
"帮我记个笔记：会议纪要..." → add_note(title, content)
```

**提醒时间格式**（自然语言解析）：

| 格式 | 示例 |
|------|------|
| 相对时间 | `30秒后` `5分钟后` `2小时后` `3天后` |
| 明后天 | `明天 9:00` `大后天 8:30` |
| 具体日期 | `2026-07-31 15:00` |
| 裸时间 | `15:00`（已过则自动顺延到明天） |

提醒到点后由后台任务自动在终端打印通知，无需手动查看。

## 记忆系统

- 基于 ChromaDB 向量库，语义检索相似记忆注入对话上下文
- **价值分层**：只存偏好 / 个人信息 / 任务等高价值内容，寒暄、天气、短回答自动跳过
- **相似度过滤**：低于 `MEMORY_MIN_SIMILARITY` 的记忆不注入
- **冲突处理**：注入模板标注"与本次对话矛盾时以本次为准"
- **隐私保护**：手机号 / 密码 / 银行卡 / 身份证正则匹配，命中即跳过

## MCP 工具配置

`mcp_config.json` 声明外部 MCP 服务器，支持 `${VAR}` 环境变量占位符：

```json
{
  "mcpServers": {
    "github": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}",
        "ghcr.io/github/github-mcp-server:1.7.0",
        "stdio",
        "--toolsets=default"
      ]
    }
  }
}
```

> GitHub MCP 服务器需要本机安装 Docker。

## 国内邮箱（QQ / 163 / 126 / Outlook）

通过 IMAP/SMTP + 授权码直连国内邮箱服务器，支持**收发邮件**及搜索 / 阅读 / 回复 / 移动 / 删除，全程国内网络直连，不依赖任何境外服务。

### 1. 开启 IMAP/SMTP 并获取授权码（一次性）

| 邮箱 | 网页端操作 | 服务器（预设，无需填写） |
|------|-----------|--------------------------|
| QQ 邮箱 | 设置 → 账号 → 开启 IMAP/SMTP 服务 → 生成授权码 | imap.qq.com:993 / smtp.qq.com:465 |
| 163 邮箱 | 设置 → POP3/SMTP/IMAP → 开启 IMAP/SMTP → 生成授权码 | imap.163.com:993 / smtp.163.com:465 |
| 126 邮箱 | 同上 | imap.126.com:993 / smtp.126.com:465 |
| Outlook | 设置 → 邮件 → 同步邮件 → 开启 IMAP，使用普通密码或应用密码 | imap-mail.outlook.com:993 / smtp-mail.outlook.com:587 |

> 授权码**不是登录密码**，是网页端开启服务后单独生成的；QQ / 163 / 126 必须用授权码登录。163 邮箱需要额外发送 IMAP ID 命令，本项目已自动处理。

### 2. 配置 .env

```bash
EMAIL_PROVIDER=qq        # qq | 163 | 126 | outlook | custom
EMAIL_ADDRESS=你的邮箱@qq.com
EMAIL_PASSWORD=你的授权码
# EMAIL_USERNAME=        # 一般无需设置，默认同邮箱地址
# EMAIL_ATTACHMENT_DIR=.agent_email_attachments
```

其他服务商把 `EMAIL_PROVIDER` 换成 `163` / `126` / `outlook` 即可；企业邮箱或自建邮箱可设 `EMAIL_PROVIDER=custom` 并填写 `EMAIL_IMAP_HOST` / `EMAIL_IMAP_PORT` / `EMAIL_SMTP_HOST` / `EMAIL_SMTP_PORT`。

### 3. 使用

- 重启 `python agent.py`，执行 `/tools` 应能看到 `mail_*` 前缀的工具；Web 控制台「状态」页也会显示「邮箱」能力。
- 可用工具（8 个）：`mail_list_folders`、`mail_search_emails`、`mail_read_email`、`mail_send_email`、`mail_reply_email`、`mail_mark_read`、`mail_move_email`、`mail_delete_email`。
- 邮件正文过长会自动截断防止撑爆上下文；带附件的邮件会先把附件保存到 `EMAIL_ATTACHMENT_DIR`（默认 `.agent_email_attachments/`）再返回本地路径，可直接用文件系统工具打开。

> 提示：授权码只保存在本机 `.env`，IMAP/SMTP 直连邮箱官方服务器，不经过任何第三方服务；删除邮件默认先进回收站，永久删除不可恢复。

## Web 界面与日志

Web 界面由两部分组成：Python 后端 `web_api.py`（FastAPI）与 Next.js 前端
`personal-assistant-agent-web-console/`。启动脚本统一放在 `scripts/`：

| 命令 | 作用 |
|------|------|
| `scripts/start-api.ps1` | 后台启动 Web API（端口 8000） |
| `scripts/start-web.ps1` | 后台启动前端（端口 3000） |
| `scripts/start-all.ps1` | 一并启动后端 + 前端 |
| `scripts/stop-all.ps1` | 停止以上脚本启动的服务（按 PID 记录） |

**日志统一写入 `logs/` 目录**（已 gitignore，不提交）：

| 文件 | 来源 |
|------|------|
| `logs/web-api.log` | Web API（自动轮转：单文件 5MB，保留 3 份历史） |
| `logs/next-dev.log` | Next.js 前端开发服务器 |
| `logs/archive/` | 历史旧日志归档，确认无用后可删除 |

手动运行也一样：`python web_api.py` 会自动把日志写入 `logs/web-api.log`；
前端 `pnpm dev` 直接跑时输出在终端，用 `scripts/start-web.ps1` 启动则写入 `logs/next-dev.log`。

## GAIA 基准评测

内置 [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA) 基准评测脚本，评估 Agent 综合能力：

```bash
# 完整评测
python -m gaia_eval.run --gaia

# 仅 Level 1
python -m gaia_eval.run --gaia --gaia-levels 1

# 只跑 10 题尝鲜
python -m gaia_eval.run --gaia --gaia-max 10

# 跳过附件题
python -m gaia_eval.run --gaia --gaia-no-attach

# 先预览题数与 API 消耗，不实际调用
python -m gaia_eval.run --gaia --dry-run
```

评测结果自动保存为报告文件，支持通过 `--gaia-levels` / `--gaia-max` / `--gaia-no-attach` 组合筛选题目。

## 项目结构

```
.
├── agent.py              # 主程序：对话循环、工具注册、后台提醒、CLI
├── email_tools.py        # 国内邮箱工具集（FastMCP 进程内服务，IMAP/SMTP + 授权码）
├── personal.py           # 待办 / 笔记 / 提醒 纯函数与迁移读取（parse_time / format_time 等）
├── personal_mysql.py     # 待办 / 笔记 / 提醒 数据层（唯一后端：MySQL，自动建库建表 + 存量迁移）
├── storage.py            # 存储工厂：create_personal_manager / create_session_store（仅 MySQL，失败报错）
├── memory.py             # 外部记忆系统（ChromaDB 向量检索）
├── history.py            # 历史会话存储（唯一后端：MySQL，自动建库建表 + 存量迁移，/history /load 支持）
├── web_api.py            # Web API 后端（FastAPI，SSE 对话 / 待办 / 笔记 / 提醒 / 历史 / 状态）
├── scripts/              # 启动 / 停止脚本（start-api / start-web / start-all / stop-all）
├── logs/                 # 运行日志（web-api.log、next-dev.log、archive/ 历史归档）
├── personal-assistant-agent-web-console/  # Next.js Web 控制台前端（独立工程）
├── gaia_eval/            # GAIA 基准评测
│   ├── run.py            # 评测 CLI 入口
│   └── gaia_eval.py      # 数据集加载与评测逻辑
├── mcp_config.json       # MCP 外部工具配置（GitHub；国内邮箱为代码直连，见上文）
├── requirements.txt      # Python 依赖
├── .env                  # 环境变量（已 gitignore，勿提交）
└── .agent_personal/      # 旧版待办/笔记/提醒数据（仅首次启动迁移到 MySQL 时读取，不再写入）
└── .agent_history/       # 旧版历史会话数据（仅首次启动迁移到 MySQL 时读取，不再写入）
```

## 隐私与安全

- 所有数据仅存本地：向量记忆在 `.agent_memory/`，待办/笔记/提醒与历史会话全部存本地 MySQL（`.agent_personal/`、`.agent_history/` 仅保留旧数据供一次性迁移），不上云
- 敏感信息（手机号 / 密码 / 银行卡 / 身份证）自动过滤，不写入记忆
- `.env` 含 API Key，已被 `.gitignore` 排除，请勿提交到公开仓库
- 国内邮箱通过 IMAP/SMTP 直连邮箱服务器（QQ / 163 / 126 / Outlook），授权码只保存在本机 `.env`，不经过任何第三方服务；附件默认下载到 `.agent_email_attachments/`

## 许可证

私有项目，仅供个人使用。
