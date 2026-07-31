# Personal Assistant Agent

基于 [Pydantic AI](https://ai.pydantic.dev/) + Harness 构建的交互式命令行 AI 助手，集成了联网搜索、文件操作、Shell 执行、GitHub MCP、长期记忆（向量检索）、以及待办 / 笔记 / 提醒等个人效率功能。

## 功能特性

- **多能力 Agent**：联网搜索（WebSearch）、文件读写（FileSystem）、执行系统命令（Shell）
- **MCP 外部工具**：通过 `mcp_config.json` 挂载 GitHub 搜索等外部工具集
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
├── personal.py           # 待办 / 笔记 / 提醒 纯函数与迁移读取（parse_time / format_time 等）
├── personal_mysql.py     # 待办 / 笔记 / 提醒 数据层（唯一后端：MySQL，自动建库建表 + 存量迁移）
├── storage.py            # 存储工厂：create_personal_manager / create_session_store（仅 MySQL，失败报错）
├── memory.py             # 外部记忆系统（ChromaDB 向量检索）
├── history.py            # 历史会话存储（唯一后端：MySQL，自动建库建表 + 存量迁移，/history /load 支持）
├── gaia_eval/            # GAIA 基准评测
│   ├── run.py            # 评测 CLI 入口
│   └── gaia_eval.py      # 数据集加载与评测逻辑
├── mcp_config.json       # MCP 外部工具配置
├── requirements.txt      # Python 依赖
├── .env                  # 环境变量（已 gitignore，勿提交）
└── .agent_personal/      # 旧版待办/笔记/提醒数据（仅首次启动迁移到 MySQL 时读取，不再写入）
└── .agent_history/       # 旧版历史会话数据（仅首次启动迁移到 MySQL 时读取，不再写入）
```

## 隐私与安全

- 所有数据仅存本地：向量记忆在 `.agent_memory/`，待办/笔记/提醒与历史会话全部存本地 MySQL（`.agent_personal/`、`.agent_history/` 仅保留旧数据供一次性迁移），不上云
- 敏感信息（手机号 / 密码 / 银行卡 / 身份证）自动过滤，不写入记忆
- `.env` 含 API Key，已被 `.gitignore` 排除，请勿提交到公开仓库

## 许可证

私有项目，仅供个人使用。
