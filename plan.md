# ChronicleAgent 实施步骤分布计划

> 基于 design.md 的 Phase 1-4 细化，包含每个步骤的技术要点、依赖关系、优先级和交付标准。
> 总阶段：4 | 总步骤：24 | 标注 ⚡ 为 MVP 关键路径

---

## Phase 1：基础可运行版本（Step 1-7）

> 目标：实现 QQ Bot 接入 + 模组检索 + KP 私聊建议的闭环。
> 关键路径：Step 1 → 2 → 3 → 4 → 5 → 6 → 7
> ⚡ 此阶段完成后即可进行首次实机跑团测试。

---

### Step 1：项目脚手架与基础设施搭建

**优先级**：P0（必须先做） | **预估工时**：1-2 天 | **依赖**：无

**任务清单**：

1.1 创建项目目录结构（遵循 design.md 第 16 节的目录树）
- backend/app/api/、agents/、harness/、rag/、bot/、tools/、storage/
- frontend/（留空，Phase 3 实现）
- docs/、examples/

1.2 Docker Compose 基础设施
- 编写 docker-compose.yml，包含：
  - PostgreSQL 15 + pgvector（端口 5432，挂载持久化卷）
  - Qdrant（最新版，端口 6333，挂载持久化卷）
  - Redis 7 Alpine（端口 6379）
  - API 服务（backend，端口 8000）
  - Bot 独立进程（NoneBot2 + NapCatQQ）
  - 前端（frontend，Phase 3 启用）
- 编写各服务的 .env.example 配置文件

1.3 服务器选型说明
> 当前服务器：2 核 4G 云服务器（已适配完整方案）

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_CONFIG: "shared_buffers=512MB,effective_cache_size=1GB"
  qdrant:    # ✅ 启用
  redis:     # ✅ 启用
  backend:   # FastAPI
  bot:       # NapCatQQ (含 Chromium，约 500-800MB)
```

> 内存峰值约 2.5-3.2GB，留有 800MB+ 余量。
      # 使用静态导出模式（SSG），不跑 Node.js 运行时
```

**方案 B：4 核 4G（推荐）**
```yaml
services:
  postgres: # 完整配置
  qdrant:   # 启用
  redis:    # 启用
  backend:
  bot:
    # 可使用 NapCatQQ
  frontend:
    # 完整 SSR 模式
```

> 详细资源分析见 docs/deployment.md 的服务器选型章节。

1.3 FastAPI 应用骨架
- 创建 backend/app/main.py（FastAPI 应用入口）
- 配置 CORS、生命周期管理（数据库连接池启停）
- 创建 backend/app/__init__.py 和各模块 __init__.py
- 健康检查端点 `GET /health`，返回数据库连接状态

1.4 Python 依赖管理
- 创建 backend/requirements.txt 或 pyproject.toml
- 核心依赖：fastapi, uvicorn, sqlalchemy, asyncpg, psycopg2-binary
- 向量相关：qdrant-client
- 缓存：redis, aioredis
- LLM：openai, anthropic
- Agent：langgraph, langchain-core
- 文档：pymupdf, markitdown
- Bot：nonebot2, nonebot-adapter-onebot
- 观测：langfuse, opentelemetry-api
- 其他：python-multipart, pydantic, sqlalchemy-utils

**交付检查**：
- [ ] `docker compose up` 后 PostgreSQL / Qdrant / Redis 均正常启动
- [ ] `GET /health` 返回 `{"status": "ok", "db": "connected", "qdrant": "connected"}`
- [ ] 项目目录结构与 design.md 一致

---

### Step 2：数据库表结构与数据层

**优先级**：P0 | **预估工时**：1-2 天 | **依赖**：Step 1

**任务清单**：

2.1 SQLAlchemy ORM 模型（遵循 design.md 第 9 节）
- backend/app/storage/models.py，包含 8 个模型：
  - `Campaign` → campaigns 表
  - `Module` → modules 表
  - `Character` → characters 表
  - `NPC` → npcs 表
  - `Scene` → scenes 表
  - `Clue` → clues 表
  - `Message` → messages 表
  - `AgentTrace` → agent_traces 表
- 所有模型使用 UUID 主键
- 建立外键关联关系（campaign_id 指向 Campaign）
- 使用 JSONB 类型存储 JSON 字段（profile, status, relationship_state 等）

2.2 Alembic 数据库迁移
- 初始化 Alembic
- 自动生成初始迁移脚本
- 编写 migrate.sh / migrate.bat 快捷脚本

2.3 数据库会话管理
- backend/app/storage/__init__.py
- 异步会话工厂（AsyncSession）
- get_db 依赖注入函数
- 连接池配置（pool_size=10, max_overflow=20）

2.4 Qdrant 集合管理
- backend/app/storage/qdrant.py
- 集合创建（向量维度 1536，对应 text-embedding-3-small）
-  payload 索引（campaign_id, type, visibility）
- CRUD 操作封装（upsert, search, delete, scroll）

2.5 Redis 缓存层
- backend/app/storage/redis.py
- 连接池管理
- 缓存装饰器
- 短期上下文 TTL 配置（默认 30 分钟）

2.6 Repository 模式
- campaign_repo.py, module_repo.py, message_repo.py, scene_repo.py, npc_repo.py, clue_repo.py, trace_repo.py
- 每个 Repository 封装对应模型的 CRUD + 业务查询

**交付检查**：
- [ ] Alembic migrate 执行成功，PostgreSQL 中 8 张表均创建
- [ ] Qdrant 集合创建成功，可写入和检索向量
- [ ] Redis 连接正常，set/get 测试通过
- [ ] Repository 的 CRUD 单元测试通过

---

### Step 3：模组文档上传与解析

**优先级**：P0 | **预估工时**：2-3 天 | **依赖**：Step 2

**任务清单**：

3.1 文件上传 API
- `POST /api/modules/upload`
- 接收 multipart/form-data（campaign_id + file）
- 文件大小限制（当前 50MB）
- 支持格式：.md / .txt（Phase 1 优先）、.pdf（Phase 2 增强）

3.2 文档解析引擎
- backend/app/rag/document_parser.py
- 通用接口 `BaseParser` + 各格式实现（MarkdownParser, TxtParser, PDFParser）
- 输出统一结构：`ParseResult(title, sections[], raw_text)`

3.3 文档切分（Chunking）
- backend/app/rag/chunker.py
- **分层切分策略**（design.md 第 13.1 节）：
  1. 按 Markdown 标题层级切分章节
  2. 语义识别 NPC / 地点 / 线索 / 剧情节点并单独成块
  3. 保留跨块引用关系
  4. 每个 chunk 携带元数据：type、title、location、visibility、related_nodes
- 回退策略：固定大小切分（chunk_size=512, overlap=64）
- chunk 输出 JSON 格式与 design.md 第 13.1 节一致

3.4 结构化信息抽取
- 使用 LLM 从文档中抽取：
  - NPC 列表（name, personality, secret）
  - 地点列表（name, description）
  - 线索列表（name, location, trigger_condition, hidden）
  - 剧情节点列表（name, stage, description, prerequisites）
- 写入 PostgreSQL 对应表

3.5 向量化存储
- 为每个 chunk 生成 Embedding（OpenAI text-embedding-3-small）
- 写入 Qdrant 集合
- payload 包含：chunk_id, campaign_id, type, title, visibility, location, related_nodes

3.6 API 端点
- `POST /api/modules/upload`（上传 + 全流程解析）
- `GET /api/modules/{module_id}`（查看解析结果）
- `GET /api/modules/{module_id}/chunks`（查看切分结果）
- `GET /api/campaigns/{id}/npcs`、`/clues`、`/scenes`（查看抽取的结构化数据）

**交付检查**：
- [ ] 上传 .md 文件后成功解析为结构化章节
- [ ] 上传 .txt 文件后成功解析（回退策略）
- [ ] 解析后 PostgreSQL 中 NPC / Clue / Scene 数据正确写入
- [ ] Qdrant 中对应 chunk 写入成功，向量检索可召回

---

### Step 4：RAG 检索服务

**优先级**：P0 | **预估工时**：1-2 天 | **依赖**：Step 3

**任务清单**：

4.1 检索器实现
- backend/app/rag/retriever.py
- **混合检索**（design.md 第 13.2 节）：
  1. 语义向量检索（Qdrant search，top_k=10）
  2. 关键词检索（Qdrant payload filter + 全文）
  3. 当前场景过滤（filter by campaign_id + scene）
  4. 未触发线索加权（boost 分数）
- 检索结果合并去重

4.2 重排序器
- backend/app/rag/reranker.py
- 重排序优先级（design.md 第 13.3 节）：
  1. 当前场景相关（+0.3）
  2. 当前 NPC 相关（+0.25）
  3. 与玩家行动语义相似度高（+0.2）
  4. 未触发关键线索（+0.15）
  5. 与当前主线节点相关（+0.1）
- 支持两种模式：快速（基于分数加权）/ 精确（LLM 重排）

4.3 检索 API
- `POST /api/rag/query`
- 请求：campaign_id, query, scene_context?, top_k
- 返回：answer + sources[]（chunk_id, text, score, visibility）

4.4 查询增强
- 自动加入当前场景和活跃 NPC 信息到查询上下文
- 支持多轮对话中的查询重写

**交付检查**：
- [x] 语义检索 + 关键词检索结果正确合并（RRF 融合已验证）
- [x] 重排序后场景相关结果排在前面（Boost: scene +0.3, NPC +0.25, hidden +0.15）
- [x] `POST /api/rag/query` 返回增强检索结果（含状态上下文注入）
- [x] `POST /api/rag/debug` 调试端点可查看检索内部过程
- [x] `GET /api/rag/state/{campaign_id}` 可查看影响检索的剧情状态
- [ ] 检索平均延迟 < 500ms（需 docker compose 启动后实测）

**Step 4 与通用 RAG 的核心差异（设计说明）**：
1. **State-Gated**：查询前自动注入当前场景/NPC/线索状态（QueryEnhancer）
2. **Undiscovered Boost**：未发现线索关键词 4x 重复权重 → 嵌入向量自动偏向
3. **Dual-Visibility**：kp_only chunk 自动 +0.15 boost（给 KP 看时），player_visible 可安全输出
4. **Hybrid + RRF**：语义向量 + 关键词并行检索 → Reciprocal Rank Fusion 去重排序
5. **Scene-Scoped**：场景名匹配 chunk title/location → +0.3 场景 boost

---

### Step 5：QQ Bot 接入

**优先级**：P0 | **预估工时**：2-3 天 | **依赖**：Step 1

**任务清单**：

5.1 NoneBot2 项目初始化
- 创建 backend/app/bot/ 模块
- 配置 NoneBot2（nb-cli 或手动配置）
- 配置 OneBot v11 适配器
- 配置 NapCatQQ/Lagrange.OneBot 连接信息（environment.yml / bot_config.yml）

5.2 Bot 启动集成
- 将 NoneBot2 作为 FastAPI 的子应用或独立进程运行
- 方案 A（推荐）：独立进程，通过 HTTP/WebSocket 与 FastAPI 通信
- 方案 B：使用 nonebot2 的 ASGI 模式挂载到 FastAPI
- 实现消息转发：Bot → FastAPI Agent Service 的统一入口

5.3 群聊消息监听
- 监听 `group_message` 事件
- **群聊铁律：必须 @Bot 才响应（闲聊和指令均适用）**
- 提取字段：group_id, user_id, raw_message, at_segments
- 检查 `at` 消息段中是否包含 Bot QQ → 不包含则静默忽略
- 通过后调用 FastAPI 的 `POST /api/messages/handle` 进行消息处理
- 非阻塞处理：Bot 接收后异步发送到处理队列，快速回复群聊

5.4 KP 指令系统
- backend/app/bot/commands.py
- 私聊指令（KP 私聊 Bot）：
  - `/绑定团 <campaign_id>` → 持久化绑定到 PostgreSQL（campaigns.kp_qq）
  - `/解绑团` → 解除 KP 绑定
  - `/查线索 <关键词>` → 调用 RAG 检索
  - `/当前状态` → 返回当前剧情状态
  - `/建议` → 获取当前建议
  - `/总结` → 生成团录
- 群聊绑定：
  - `/群绑定 <群号> <campaign_id>` → 绑定群到跑团项目

5.5 KP 私聊通知
- 群消息 → FastAPI 处理 → 查 campaigns.kp_qq 获取 KP QQ → Bot 私聊发送
- 支持多个 KP 共用一个 Bot，每个 KP 绑定不同的团
- 消息格式：建议标题 + 模组内容（摘要） + 操作建议
- 区分玩家可见内容 / KP 私密内容

**交付检查**：
- [x] Bot 独立进程可通过 `python -m app.bot` 启动 NoneBot2
- [x] Bot 通过 HTTP 调用 FastAPI 消息处理 API
- [x] KP 私聊 `/绑定团`、`/查线索`、`/当前状态`、`/帮助` 指令就绪
- [x] `/绑定团` 持久化到 PostgreSQL（campaigns.kp_qq 字段）
- [x] KP QQ 无需环境变量配置，用户私聊绑定后存入数据库
- [x] 群聊消息 → 分类 → RAG 检索 → KP 建议全链路
- [x] 非阻塞处理：群聊响应和 KP 私聊分离
- [ ] 需 NapCatQQ 扫码登录后才能实际验证（`docker compose up napcat`）
- [ ] 消息处理延迟 < 3s（需实机测试）

---

### Step 6：Orchestrator 消息处理主流程

**优先级**：P0 | **预估工时**：2-3 天 | **依赖**：Step 4, Step 5

**任务清单**：

6.1 Harness 核心框架
- backend/app/harness/orchestrator.py
- 消息处理主循环：
  1. Bot 接收消息 → 2. 消息入队 → 3. 分类 → 4. 检索 → 5. 生成建议 → 6. 安全检查 → 7. 输出

6.2 Message Classifier 初步实现
- 基于 LLM 调用（非 LangGraph，Phase 2 再引入编排）
- 判断消息类型：player_action / roleplay / chat / rule_question / kp_command
- 输出：是否需要 RAG、是否需要 KP 提醒

6.3 建议生成流程（简单版）
- 输入：消息内容 + RAG 检索结果 + 当前状态
- LLM 调用生成建议
- 建议格式：描述 + KP 提示
- 基础防剧透（prompt 层面控制，不要泄露隐藏信息给玩家可见部分）

6.4 Trace 记录
- backend/app/harness/trace_recorder.py
- 记录每次消息处理的完整过程：
  - 输入消息
  - 分类结果
  - 检索结果（top 3 chunk）
  - 生成的建议
  - 耗时、token 消耗
- 写入 agent_traces 表

6.5 Context Manager 初步
- backend/app/harness/context_manager.py
- 组装消息处理上下文：
  - 当前场景状态
  - 最近 N 条消息（N 可配置，默认 20）
  - 活跃 NPC 列表
  - 已发现 / 未发现线索

**交付检查**：
- [x] Orchestrator 消息处理主循环：保存 → 上下文 → 分类 → 检索 → 建议 → Trace
- [x] Context Manager 组装完整上下文（场景/NPC/线索/最近消息）
- [x] LLM 消息分类替代硬编码关键词（classifier_agent，含关键词兜底）
- [x] Trace 记录正确写入 agent_traces 表
- [x] Trace Recorder 支持 start/finish 和 one-shot 两种模式
- [x] 异常兜底：LLM 或 RAG 失败时返回安全默认值
- [ ] 单次消息处理总延迟 < 5s（需实机测试）

---

### Step 7：MVP 整合测试与部署

**优先级**：P0 | **预估工时**：1 天 | **依赖**：Step 6

**任务清单**：

7.1 端到端测试
- 构造示例模组（examples/demo_module.md）
- 构造示例消息序列（examples/demo_messages.jsonl）
- 编写测试脚本，验证完整流程

7.2 Docker Compose 完善
- 完善服务编排，确保一键启动
- 编写 .env 示例文件
- 编写启动脚本（start.sh / start.bat）

7.3 部署文档
- docs/deployment.md
- 环境要求
- 配置说明（QQ Bot 配置、API Key 配置）
- 启动步骤

7.4 Phase 1 交付演示
- 上传示例模组
- 发送模拟群消息
- KP 收到私聊建议

**交付检查**：
- [x] 构造示例模组 examples/demo_module.md（CoC 模组"迷雾庄园"）
- [x] 构造示例消息序列 examples/demo_messages.jsonl（20 条模拟消息）
- [x] 测试脚本 test_step7_mvp.py 覆盖 12 项测试（关键词分类、查询增强、分词、RRF 融合、重排序、结构验证等）
- [x] 12/12 项目结构验证通过，48 个 .py 语法全部通过
- [ ] `docker compose up` 一键启动所有服务（需实机测试）
- [ ] 上传模组 → 解析 → 检索 → Bot 私聊全链路可用（需 Docker 环境）

---

## Phase 2：多 Agent 协作版本（Step 8-13）

> 目标：引入 LangGraph 编排和 8 个 Agent，实现结构化状态追踪、NPC 角色扮演和 Critic 检查。
> ⚡ 此阶段是项目的核心技术亮点，完成后 Agent 架构具备可观测性和可扩展性。

---

### Step 8：LangGraph 编排框架搭建

**优先级**：P1 | **预估工时**：1-2 天 | **依赖**：Step 7（可并行开始）

**任务清单**：

8.1 LangGraph 图结构设计
- backend/app/harness/orchestrator.py（重构）
- 定义 Graph 节点（状态节点 + Agent 节点）
- 定义边（条件分支）
- 消息处理主图的节点链路：
  `classify → [rag + state_lookup] → (concurrent) → generate_suggestion → critic_check → output`

8.2 State Schema 定义
- 定义 `AgentState` TypedDict：
  - message: 原始消息
  - sender: 发送者
  - message_type: 分类结果
  - rag_results: 检索结果列表
  - current_state: 当前剧情状态
  - suggested_action: Agent 建议
  - critic_result: 安全检查结果
  - output: 最终输出

8.3 路由与条件分支
- `route_by_message_type`：根据分类结果路由到不同处理路径
- `route_by_risk_level`：根据 Critic 结果决定是否允许输出
- 各路径：
  - 玩家行动 → 完整链路
  - 角色扮演 → NPC Agent
  - 规则问题 → Rule Agent
  - KP 指令 → 指令处理
  - 闲聊 → 跳过（不处理）

8.4 Agent 节点接口
- 统一的 Agent 节点签名：`(state: AgentState) -> AgentState`
- 每个 Agent 节点只更新自己负责的状态片段
- LLM 调用抽象层，支持多模型切换

**交付检查**：
- [ ] LangGraph 图构建成功，可视化可查看节点和边
- [ ] 消息处理走通 LangGraph 编排
- [ ] 不同消息类型路由到不同路径
- [ ] Graph 的 State 在节点间正确传递

---

### Step 9：Message Classifier Agent

**优先级**：P1 | **预估工时**：0.5 天 | **依赖**：Step 8

**任务清单**：

9.1 Agent 实现
- backend/app/agents/classifier_agent.py
- 输入：消息内容 + 最近 5 条上下文
- LLM Prompt 设计（few-shot 示例）
- 分类类别（design.md 第 7.1 节）：
  - player_action：玩家行动（调查、移动、交互）
  - roleplay：角色扮演对话
  - chat：玩家间闲聊
  - rule_question：规则相关问题
  - kp_command：KP 指令（以 / 开头）
  - npc_dialogue：玩家与 NPC 对话

9.2 输出结构化
```python
class ClassifierResult(BaseModel):
    message_type: str
    confidence: float
    need_rag: bool
    need_state_update: bool
    need_kp_suggestion: bool
    reasoning: str
```

9.3 单元测试
- 测试各类消息类型的分类准确性
- 边界情况：混合消息、简短消息、含骰点指令

**交付检查**：
- [ ] 各种消息类型分类准确（验证集 > 85%）
- [ ] 置信度低于 0.4 时返回 `uncertain` 并走默认路径
- [ ] 延迟 < 500ms

---

### Step 10：State Tracking Agent + RAG Agent + 骰子解析

**优先级**：P1 | **预估工时**：2-3 天 | **依赖**：Step 8, Step 4

**任务清单**：

10.0 骰子结果解析器
- backend/app/bot/dice_parser.py
- 静默读取群聊中骰娘发出的结果，不自己掷骰
- 常见骰娘格式正则匹配：`.r 1d100 = 75`、`检定/侦查 70/45 失败`、`1D100=32/60 成功` 等
- 提取结构化字段：check_type（检定类型）、target（目标值）、rolled（掷出值）、outcome（critical_success / success / failure / fumble）
- 输出 `DiceResult` 对象，作为 `AgentState.dice_result` 字段注入 LangGraph
- 注意：暗骰（KP 私聊骰娘的结果）不在群聊中出现，此类情况 dice_result 为 None，走默认分支

10.1 State Tracking Agent（骰子感知版）
- backend/app/agents/state_agent.py
- 职责（design.md 第 7.3 节 + 骰子分支）：
  1. 解析玩家行动，提取场景变化
  2. **根据骰子结果选择状态分支**（成功 → 线索已获取 / 失败 → 行动被锁定或触发替代事件 / 大成功 → 额外信息 / 大失败 → 负面后果）
  3. 更新 NPC 态度
  4. 标记已发现线索
  5. 更新玩家目标进度
  6. 更新剧情阶段
- 实现方式：
  - 读取当前状态 + 玩家消息 + dice_result
  - LLM 推理状态变更，骰子结果作为分支选择条件
  - 生成状态 diff（只更新变化部分）
  - 写入 PostgreSQL（scenes, clues, npcs 表）
- 状态模型变更：从单线状态快照改为**可能性树**
  - 同一玩家行动根据骰子结果对应多个合法后继状态
  - 分支被实际走入后，修剪其余可能性
  - 失败分支记录"锁定原因"（如"侦查检定失败，线索 X 无法通过此路径获取"），供 RAG Agent 后续检索替代路径

10.1.5 玩家状态追踪（Player State）
- **为什么需要**：CoC 跑团中 KP 最容易记混的是**按玩家切分**的状态——谁掉过多少理智值、谁身上带着哪个线索道具、谁习得了什么技能。现有 State Tracking 只追踪全局状态（场景、全体线索），不追踪玩家维度。这是当前 plan 的最大缺口。
- 数据模型（利用现有 characters 表 + 新增字段）：
  - `sanity`（int）：当前理智值，每次掉 SAN 自动更新
  - `skills`（JSONB）：技能字典，如 `{"侦查": 70, "图书馆使用": 45}`，检定成功后可选自动标记技能成长
  - `inventory`（JSONB）：随身物品列表，如 `[{"name": "旧日记", "source": "书房抽屉", "clue_id": "xxx"}]`
  - `personal_clues`（JSONB）：该玩家独有发现的线索 ID 列表（区别于全局线索池）
  - `status_effects`（JSONB）：临时状态，如 `[{"effect": "恐惧", "source": "目睹食尸鬼", "duration": "3轮"}]`
  - `relationships`（JSONB）：与 NPC 的关系状态，如 `{"道格拉斯": "友善", "梅洛迪亚斯": "不信任"}`
- 实现方式：
  - AgentState 新增 `player_states: dict[str, PlayerSnapshot]` 字段（key 为 player_qq）
  - State Tracking Agent 处理每条消息时，不仅更新全局状态 diff，也输出 `player_diffs: dict[str, dict]`（按玩家切分的变更）
  - PlayerSnapshot 从数据库 characters 表读取，每次变更写回
  - 骰子结果联动：大失败导致 SAN 下降自动写回 player_state；大成功获得额外线索自动追加到 inventory
- Player State 在 RAG 检索中的用途：
  - 查询增强时注入当前玩家持有的线索（避免重复推荐已获得的线索）
  - 查询增强时注入玩家技能值（如玩家侦查 70，相关线索给予更高权重）
- API 端点：
  - `GET /api/campaigns/{id}/players` — 查看所有玩家状态概览
  - `GET /api/campaigns/{id}/players/{player_qq}` — 查看单个玩家完整状态
  - `PATCH /api/campaigns/{id}/players/{player_qq}` — KP 手动修正玩家状态

10.2 状态更新策略
- 增量更新：LLM 只输出 `changes` diff
- 骰子驱动的分治：success 和 failure 两条 diff 路径预先定义，实际执行时选其一
- 冲突处理：如果 KP 手动修正过状态，以 KP 为准
- 回滚支持：每次状态变更记录版本号

10.3 RAG Agent 封装（成功率感知版）
- backend/app/agents/rag_agent.py
- 封装 Step 4 的检索服务为 Agent 节点
- 自动注入当前状态上下文（场景、NPC、线索）增强检索
- **骰子结果影响检索策略**：
  - 成功时：正常检索，当前线索权重正常
  - 失败时：对已锁定线索降权，对替代线索、关联信息、绕路方向加权
  - 大失败时：额外召回负面事件、补救措施相关内容
- 支持多轮检索：一次检索后根据结果决定是否补充检索

10.4 状态查询 API
- `GET /api/campaigns/{id}/state`（design.md 第 10.4 节）
- 返回完整状态 JSON（含骰子锁定标记）
- `GET /api/campaigns/{id}/state/locks` — 查看当前被骰子锁定的线索和行动

**交付检查**：
- [ ] 骰娘消息 `.r 1d100 = 75` 正确解析为 DiceResult(outcome=success, rolled=75)
- [ ] 同一行动（调查书房）在成功/失败两种骰子结果下，状态走向不同分支
- [ ] 骰子失败后，线索标记为 locked=True，RAG 检索自动偏好转替代路径
- [ ] 暗骰（dice_result=None）时走默认成功分支，不报错
- [ ] 玩家目睹食尸鬼 → 全局状态更新"食尸鬼已暴露" + 该玩家 player_state 理智值正确下降
- [ ] 大成功获得额外线索 → 自动追加到对应玩家的 inventory
- [ ] KP 手动修正玩家理智值后，后续自动更新不覆盖 KP 修正
- [ ] 状态 diff 正确，不修改未变化字段
- [ ] RAG Agent 检索结果注入当前状态 + 骰子分支正确

---

### Step 11：NPC Roleplay Agent

**优先级**：P1 | **预估工时**：1-2 天 | **依赖**：Step 8, Step 10

**任务清单**：

11.1 NPC Agent 实现
- backend/app/agents/npc_agent.py
- 职责（design.md 第 7.5 节）：
  1. 根据 NPC 人设生成台词
  2. 区分玩家可见台词和 KP 隐藏提示
  3. 保持 NPC 前后一致性
- 输入：
  - NPC 名称 + 人设 profile（从数据库读取）
  - 玩家问题
  - 当前剧情状态
  - 对话历史（最近 10 轮）
  - NPC 当前关系状态

11.2 NPC 人设管理
- 从模组解析结果加载 NPC profile
- 支持 KP 手动补充或修正 NPC 设定
- 维护 NPC 关系状态（友善 / 中立 / 敌视 / 恐惧）

11.3 输出
```python
class NPCSuggestion(BaseModel):
    public_line: str  # 玩家可见台词
    kp_note: str  # KP 隐藏提示
    risk: str  # low / medium / high
    relationship_change: str | None  # 关系变化
```

11.4 一致性保护
- 检查 NPC 记忆：是否已经说过某句话
- 检查设定冲突：不能说出不该知道的信息
- 检查态度一致性：不能无故转变

**交付检查**：
- [ ] 老管家面对 "地下室发生过什么" 的输出不直接透露秘密
- [ ] NPC 态度在连续对话中保持合理一致
- [ ] public_line 不含隐藏信息（通过 Critic 检查）

---

### Step 11.5：陪聊 Bot 模块

**优先级**：P1 | **预估工时**：1 天 | **依赖**：Step 8, Step 13（共用 Critic）

**任务清单**：

11.5.1 Bot 角色配置
- 数据模型（利用现有 campaigns 表 + 新增 JSONB 字段或独立表）：
  ```python
  bot_persona = {
      "name": "小管家",                    # Bot 的群内称呼
      "personality": "温和有礼，略带幽默",  # 性格描述
      "role_description": "团内小助手",     # 角色定位
      "speaking_style": "简短，爱用省略号", # 说话风格
      "constraints": [                      # 硬约束
          "不透露模组线索",
          "不替 KP 做剧情决定",
          "不透露未发现的秘密"
      ]
  }
  ```
- 存储位置：campaigns 表新增 `bot_persona JSONB DEFAULT NULL` 字段，NULL 表示未启用陪聊
- 配置指令：`/Bot设定 name=<名称> personality=<性格> role=<定位>`（仅拥有者可用）
- 重置指令：`/Bot解除` — 清空 bot_persona，关闭陪聊

11.5.2 闲聊 vs 指令区分（群聊必须 @）
- **群聊铁律：所有 Bot 互动（闲聊 + 指令）都必须在消息中 @Bot 才触发。私聊不受此限制。**
- 指令识别：以 `/` 开头的消息判定为指令，走指令路由
- 非指令消息：含 @Bot + 不含 `/`前缀 → 触发陪聊
- 骰娘消息：即使 @Bot 也不触发陪聊（dice_parser 先行过滤）
- Bot 名字匹配：从 bot_persona.name 读取，支持模糊匹配

11.5.3 对话生成
- backend/app/agents/chat_agent.py
- 输入：
  - bot_persona（角色设定）
  - 当前场景的公开描述（visibility=player_visible 的 chunk）
  - 最近 10 条群聊上下文（仅 public 消息）
  - 当前玩家的 bot_persona 中定义的角色信息
- **严格防剧透**：
  - 生成的回复**不包含** visibility=kp_only 的任何内容
  - 生成后必须经过 Critic Agent 检查（复用 Step 13）
  - 如果 Critic 判定 risk_level=high，丢弃回复并保持沉默
- 输出：自然语言回复（不超过 200 字，匹配 speaking_style）
- 私聊场景：KP 私聊 Bot 的非指令消息也触发陪聊，但 KP 可以看到更深入的内容（critic 检查放宽到 kp_only）

11.5.4 上下文管理
- 群聊中 Bot 保持对话连续性：记录最近 5 轮 Bot 发言 + 被 @ 的上下文
- 冷却机制：30 秒内同一群只回复 1 次，避免刷屏
- 如果 Bot 被连续 @ 但无人回应，逐步降低回复频率

**交付检查**：
- [ ] KP 执行 `/Bot设定 name=小书虫 personality=博学但啰嗦 role=图书馆助手` → 配置保存成功
- [ ] 群内 @Bot "小书虫，今天天气怎么样" → Bot 以博学但啰嗦的风格回复，不含模组内容
- [ ] 群内发言不含 `/` 前缀且未 @Bot → 不触发陪聊
- [ ] Critic 检查发现生成内容含隐藏线索 → 丢弃回复，不输出
- [ ] `/Bot解除` 后 Bot 停止陪聊回复
- [ ] 30 秒冷却机制生效，不连续刷屏

---

### Step 12：Plot Deviation Agent + Rule Assistant Agent + 分支创作

**优先级**：P1 | **预估工时**：1-2 天 | **依赖**：Step 10

**任务清单**：

12.1 Plot Deviation Agent（骰子感知版）
- backend/app/agents/plot_agent.py
- **偏离分数计算**（design.md 第 7.4 节 + 骰子因子）：
  - deviation_score = weighted sum of 6 factors（新增骰子因子）
  - 各因子权重可配置（默认从设计文档）
  - 分数范围 0-1
- **新增：行动覆盖率 vs 成功率解耦**（从 Step 10 的 dice_result 读取）：
  - 行动覆盖率高 + 成功率低 → 骰子阻挡型（不是偏离，是运气不好）
  - 行动覆盖率低 + 成功率高 → 玩家兴趣偏离型（真正的偏离）
  - 行动覆盖率低 + 成功率低 → 既缺乏尝试又被骰子阻挡（最需要 KP 介入）
- 骰子阻挡型不走"回归主线"提示，改为"降低难度建议 / 替代线索 / 暗骰放水选项"

12.2 偏离检测输入
- 最新 N 条消息的语义与主线目标的相似度
- 关键线索未触发时间（**区分"未尝试"与"尝试但骰子失败"**）
- 玩家行动与当前场景相关性
- NPC 行为偏差
- 当前场景停留轮数
- **骰子成功率统计**（新增）：最近 K 次检定的成功率，用于判断偏离类型

12.3 引导建议生成
- 三级偏离策略（design.md 场景二）：
  - low：无需干预
  - medium：温和推进建议（NPC 提示）
  - high：强制推进策略 + 回主线建议

12.4 Rule Assistant Agent
- backend/app/agents/rule_agent.py
- 职责（design.md 第 7.6 节）：
  1. 根据玩家行动建议判定类型
  2. 生成骰点指令
  3. 解释判定结果
- Phase 2 实现通用规则支持（COC 优先）
- 输出：suggested_check, difficulty, dice_command, success_effect, failure_effect

12.5 分支剧情创作（KP 主动开新线）
- backend/app/agents/branch_writer.py
- **为什么需要**：偏离检测是"防守"（玩家跑偏了报警），这个是"进攻"（KP 决定不按模组走，AI 帮着写新内容）。KP 在跑团中经常需要临场发挥——玩家做了模组没覆盖的选择、KP 想加入原创支线、或者骰子的连续大成功/大失败把剧情推到了模组未定义的方向。这个 Agent 利用已解析的模组数据（NPC 人设、世界观设定、已有线索和场景）作为地基，生成与之自洽的新内容。
- 触发方式：
  - KP 私聊指令：`/新分支 <描述>` — KP 描述当前局面和意图，Agent 生成新分支方案
- 输入（提供给 LLM 的上下文）：
  - 当前场景和全局剧情状态（从 Step 10 State Tracking 读取）
  - 活跃 NPC 的完整人设（name, personality, secret, relationships）
  - 已发现和未发现的线索清单
  - 玩家当前持有的道具和线索（从 Player State 读取）
  - 模组世界观摘要（从已解析的模组 chunks 中提取）
  - KP 的自由文本描述（新分支的意图和方向）
- 输出（BranchProposal）：
  ```python
  class BranchProposal(BaseModel):
      title: str                          # 新分支名称
      premise: str                        # 前提概要（为什么走到这条分支）
      new_scenes: list[dict]              # 新场景：name, description, location, connected_npcs
      new_clues: list[dict]               # 新线索：name, description, location, trigger, hidden
      affected_npcs: list[dict]           # 受影响的 NPC：name, new_attitude, new_secret（可选）
      possible_outcomes: list[dict]       # 可能的结局走向：description, conditions, connection_to_main（是否可回归主线）
      consistency_check: str              # 自检：与已有模组的自洽性说明
      suggested_dice_events: list[dict]   # 建议的骰点事件：场景, 检定类型, 难度, 成功/失败后果
  ```
- 关键约束（Prompt 层面）：
  - 必须与已有 NPC 人设自洽（不会让友善 NPC 无缘无故背叛）
  - 必须与模组世界观自洽（不会在 1920s 美国小镇突然出现太空飞船）
  - 生成的线索必须可骰子化（每个关键节点有对应的检定建议）
  - 必须提供"回归主线"的路径（除非 KP 明确说这是永久分叉）
  - 新内容是建议而非强制——KP 可以全部采用、部分采用或完全拒绝
- 与 Player State 联动：
  - 新生成的线索自动绑定到当前场景
  - 新分支创建后，Player State 的 personal_clues 和 inventory 可容纳新内容
  - 如果 KP 采纳新分支，自动写入 scenes / clues / npcs 表（标记 source="kp_branch" 以区别于模组原始数据）
- API 端点：
  - `POST /api/campaigns/{id}/branches/generate` — 请求生成新分支（参数：kp_description, include_main_return 等）
  - `POST /api/campaigns/{id}/branches/{branch_id}/adopt` — KP 确认采纳某分支，写入数据库
  - `GET /api/campaigns/{id}/branches` — 查看历史分支方案列表
- Bot 指令：
  - `/新分支 <描述>` — KP 私聊 Bot，描述当前局面，Bot 调用 branch_writer 生成方案并私聊回复
  - `/采纳分支 <branch_id>` — KP 确认采纳，写库

**交付检查**：
- [ ] 玩家连续讨论无关 NPC → 偏离检测提醒正确（行动覆盖率低）
- [ ] 关键线索长时间未触发 but 玩家已多次尝试检定失败 → 识别为骰子阻挡型，不报偏离，提示降难度
- [ ] 偏离建议合理（不破坏玩家体验）
- [ ] Rule Agent 能给出正确判定建议
- [ ] KP 输入"/新分支 玩家决定跟踪墓地看守回家而不是进入地穴" → 生成包含新场景、新线索、与 NPC 梅洛迪亚斯相关的自洽分支
- [ ] 生成的新分支不与已有 NPC 人设矛盾（Critic 可验证）
- [ ] KP 采纳分支后，新场景/线索正确写入数据库（source=kp_branch）
- [ ] 新分支提供至少一条回归主线的路径

---

### Step 13：Critic Agent + Agent Trace 完善

**优先级**：P1 | **预估工时**：1-2 天 | **依赖**：Step 9, 10, 11, 12

**任务清单**：

13.1 Critic Agent 实现
- backend/app/agents/critic_agent.py
- 检查项（design.md 第 7.8 节）：
  1. 是否泄露隐藏线索？（检查 output 中是否包含 visibility=kp_only 的信息）
  2. 是否提前暴露结局？
  3. 是否让 NPC 说出不该知道的信息？
  4. 是否与历史团录矛盾？
  5. 是否破坏玩家选择自由？
  6. 是否与当前已知信息冲突？
- 输出：
```python
class CriticResult(BaseModel):
    passed: bool
    check_results: list[CheckItem]
    risk_level: str  # low / medium / high
    fix_suggestion: str | None  # 如果未通过，建议修正
```

13.2 防剧透机制增强
- backend/app/harness/permission_manager.py
- 输出过滤规则（design.md 第 14 节）：
  - 玩家可见内容：自动过滤 visibility=kp_only 的信息
  - KP 私密内容：标记为 kp_only，仅私聊或控制台显示
  - 禁止输出内容：硬屏蔽

13.3 Trace Recorder 完善
- backend/app/harness/trace_recorder.py（增强）
- 记录每个 Agent 节点的：
  - 输入/输出
  - 调用的工具和结果
  - 延迟和 token 消耗
  - Critic 检查结果
- 支持 Trace 回放（用于调试和评测）

13.4 Permission Manager
- backend/app/harness/permission_manager.py
- 权限层级：player_visible / kp_only / prohibited
- 输出过滤函数：根据目标渠道过滤内容
- 安全检查集成：Critic Agent 输出 → Permission Manager 过滤 → 最终输出

**交付检查**：
- [ ] 包含隐藏线索的输出被 Critic 拦截（risk_level=high）
- [ ] 玩家可见消息中不包含 kp_only 内容
- [ ] Trace 记录完整，可通过 API 查询 Agent 调用链
- [ ] 端到端测试：完整 Agent 链路 → Critic 检查 → 过滤 → 输出

---

## Phase 3：Web 控制台版本（Step 14-18）

> 目标：为 KP 提供可视化控制台。
> 可以从前端开始，也可以并行进行。

---

### Step 14：前端项目搭建

**优先级**：P2 | **预估工时**：1 天 | **依赖**：Phase 2 API（可并行）

**任务清单**：

14.1 Next.js 项目初始化
- frontend/ 目录下 `npx create-next-app`
- TypeScript + App Router
- 配置 Tailwind CSS

14.2 UI 组件库集成
- 安装 shadcn/ui 组件
- 初始化按钮、卡片、表格、对话框、抽屉等基础组件
- 安装 Zustand（状态管理）
- 安装 React Flow（图谱展示）
- 安装 Recharts / ECharts（图表展示）

14.3 API 客户端
- frontend/src/lib/api.ts
- 封装所有 FastAPI 接口调用
- 请求/响应类型定义
- 错误处理和 loading 状态

14.4 布局与导航
- 侧边栏导航
- 路由配置：
  - `/campaigns` - 跑团项目列表
  - `/campaigns/{id}/modules` - 模组管理
  - `/campaigns/{id}/state` - 剧情状态
  - `/campaigns/{id}/timeline` - Agent 时间线
  - `/campaigns/{id}/summary` - 团录总结
  - `/campaigns/{id}/graph` - 剧情图谱

**交付检查**：
- [ ] Next.js 项目启动成功
- [ ] API 客户端可正确调用后端接口
- [ ] 路由导航正常

---

### Step 15：模组管理页面

**优先级**：P2 | **预估工时**：1-2 天 | **依赖**：Step 14

**任务清单**：

15.1 模组上传
- 拖拽上传区域
- 上传进度显示
- 格式校验提示

15.2 模组列表
- 显示所有已上传模组
- 模组标题、解析状态、块数、上传时间
- 删除和重新解析操作

15.3 解析结果预览
- 章节树状浏览（按文档结构折叠/展开）
- NPC / 地点 / 线索 / 剧情节点分页展示
- 手动编辑结构化信息（编辑 NPC 人设、修正线索条件）

**组件**：frontend/src/components/ModuleManager.tsx

**交付检查**：
- [ ] 可上传 .md / .txt 文件
- [ ] 上传后自动显示解析进度
- [ ] 可查看和编辑抽取的 NPC / 线索 / 地点信息

---

### Step 16：剧情状态页面

**优先级**：P2 | **预估工时**：1-2 天 | **依赖**：Step 14

**任务清单**：

16.1 当前场景展示
- 场景名称、描述
- 场景内 NPC 列表（带状态标记）
- 场景内线索列表（已发现 / 未发现）

16.2 剧情进度展示
- 当前剧情阶段
- 已完成的主要事件
- 未完成的剧情节点

16.3 玩家状态
- 各玩家角色名称、当前目标、状态

16.4 手动状态修正
- 场景切换按钮
- 线索标记（发现/未发现）
- NPC 状态编辑
- 修改后自动记录版本

**组件**：frontend/src/components/StatePanel.tsx

**交付检查**：
- [ ] 状态页面展示与数据库状态一致
- [ ] 手动修正后数据正确更新到数据库
- [ ] 玩家目标列表正确

---

### Step 17：Agent 时间线 + 团录总结页面

**优先级**：P2 | **预估工时**：2 天 | **依赖**：Step 14, Step 13

**任务清单**：

17.1 Agent 时间线页面
- 展示每次 Agent 处理记录（按时间倒序）
- 每条记录展示：
  - 触发消息
  - 消息类型分类结果
  - 检索到的模组内容（折叠）
  - 生成的建议
  - Critic 检查结果（通过/风险等级）
  - 最终输出
  - 耗时和 token 消耗
- 过滤：按消息类型、Agent 名称、风险等级

17.2 Summary Agent 实现
- backend/app/agents/summary_agent.py
- 职责（design.md 第 7.7 节）：
  1. 读取指定范围的消息
  2. 提取关键事件
  3. 汇总已获得 / 未获得线索
  4. 生成下次 KP 提醒
- `POST /api/summaries/generate`

17.3 团录总结页面
- 可选的日期/轮次范围选择
- 生成按钮
- 团录 Markdown 预览
- 在线编辑
- 导出为 Markdown / PDF（Phase 4 支持 PDF）

**组件**：frontend/src/components/AgentTimeline.tsx, SummaryEditor.tsx

**交付检查**：
- [ ] 时间线可查看每次 Agent 处理的完整记录
- [ ] 团录生成结果准确完整
- [ ] 团录可编辑和导出

---

### Step 18：剧情图谱页面

**优先级**：P3 | **预估工时**：2 天 | **依赖**：Step 14, Step 16

**任务清单**：

18.1 图谱数据接口
- `GET /api/campaigns/{id}/graph`
- 返回节点和边：
  - 节点：NPC、地点、线索、剧情节点
  - 边：关联关系（位于、涉及、触发、指向）
  - 节点状态：已触发/未触发

18.2 React Flow 图谱展示
- 节点颜色标记：绿色（已触发）/ 灰色（未触发）/ 红色（关键未触发）
- 交互：拖拽、缩放、点击查看详情
- 连线标注关系类型

18.3 图谱交互
- 点击节点显示详情卡片
- 标记玩家当前位置
- 高亮关键路径

**组件**：frontend/src/components/StoryGraph.tsx

**交付检查**：
- [ ] NPC / 地点 / 线索关系正确展示
- [ ] 已触发线索与未触发线索颜色区分明确
- [ ] 图谱交互流畅

---

## Phase 4：增强版本（Step 19-24）

> 目标：提升简历竞争力，增加高级功能和评测体系。

---

### Step 19：主线偏离检测增强

**优先级**：P2 | **预估工时**：1 天 | **依赖**：Step 12

**任务清单**：

19.1 偏离分数算法优化
- 从固定权重升级为动态权重
- 根据剧情阶段动态调整各因子重要性
- 引入时间衰减：线索未触发越久权重越高

19.2 多策略建议
- 为每个偏离级别提供 3 种策略：
  - 温和（NPC 提示）
  - 中等（环境变化）
  - 强力（直接事件推动）
- KP 可选择采用哪种策略

19.3 偏离趋势图
- Web 控制台展示偏离分数随时间变化
- 标记关键干预点
- 展示 KP 采取的策略和效果

**交付检查**：
- [ ] 偏离分数在不同剧情阶段表现合理
- [ ] 三种策略建议均可用
- [ ] 趋势图正常展示

---

### Step 20：防剧透评测与评分

**优先级**：P2 | **预估工时**：1-2 天 | **依赖**：Step 13

**任务清单**：

20.1 防剧透自动评测
- 构造剧透测试用例集（10-20 个）
- 基准测试脚本：批量运行并统计防剧透成功率
- 报告生成

20.2 KP 建议评分系统
- Web 控制台每个建议增加评分按钮（1-5 星）
- KP 可附带评分备注
- 评分数据用于：
  - 统计各 Agent 的有效性
  - 分析低分原因
  - 优化 Prompt

20.3 评分展示面板
- 平均分趋势
- 各 Agent 得分分布
- 低分建议的聚类分析

**交付检查**：
- [ ] 防剧透测试用例全部通过或明确记录失败
- [ ] 评分数据可正常记录和查询
- [ ] 评分面板展示正确

---

### Step 21：多模型切换支持

**优先级**：P3 | **预估工时**：1 天 | **依赖**：Step 8

**任务清单**：

21.1 LLM 抽象层
- backend/app/agents/llm_factory.py
- 统一接口：`generate(prompt, model_config) -> str`
- 支持的模型：OpenAI GPT-4o / GPT-4o-mini, DeepSeek V3 / R1, Qwen, Claude Sonnet / Haiku
- 模型配置：从环境变量读取 API Key、Base URL

21.2 模型选择策略
- 按 Agent 配置不同模型（轻量任务用低成本模型，推理任务用强模型）
- 兜底策略：模型调用失败时自动切换到备选模型
- 成本追踪：记录每次调用的模型、tokens、费用

21.3 控制台模型配置
- Web 控制台可查看当前各 Agent 使用的模型
- 支持运行时切换模型（为特定 Agent 选择不同模型）

**交付检查**：
- [ ] 至少支持 3 家 API 的正常调用
- [ ] 模型切换不影响业务逻辑
- [ ] 成本追踪数据正确

---

### Step 22：Benchmark 与自动评测

**优先级**：P3 | **预估工时**：2 天 | **依赖**：Step 20

**任务清单**：

22.1 模拟跑题数据构造
- examples/benchmark/ 目录
- 5 个评测任务（design.md 第 15.3 节）：
  1. 线索召回测试：玩家调查关键地点 → 是否召回正确线索
  2. 偏离检测测试：玩家长时间偏离 → 是否给出合理提醒
  3. 防剧透测试：询问 NPC 秘密 → 是否避免剧透
  4. 团录完整度测试：跑团结束后 → 是否完整总结
  5. 状态更新测试：玩家改变场景 → 是否正确更新

22.2 评测框架
- backend/benchmark/runner.py
- 批量执行评测任务
- 自动评分（通过 LLM as Judge 或规则匹配）
- 生成评测报告

22.3 评测报告展示
- Web 控制台展示评测结果
- 各指标雷达图
- 历史对比（每次代码变更后的分数变化）

22.4 回归测试
- CI 集成
- 每次变更后自动运行基准评测
- 分数下降时报警

**交付检查**：
- [ ] 5 个评测任务均可执行
- [ ] 评测报告内容完整
- [ ] 评测结果可追踪历史变化

---

### Step 23：多格式团录导出 + 提醒功能

**优先级**：P3 | **预估工时**：1 天 | **依赖**：Step 17

**任务清单**：

23.1 PDF 团录导出
- 使用 WeasyPrint / ReportLab 生成 PDF
- 排版：标题、章节、表格
- 中文支持

23.2 下次开团提醒
- 团录最后自动生成 "下次 KP 提醒" 部分
- 包括：关键事件回顾、待触发线索、建议推进方向
- 支持下次开团前 Bot 发送提醒

23.3 团录历史管理
- 查看历次团录列表
- 版本对比（同一团的多版本差异）

**交付检查**：
- [ ] PDF 导出格式正确、中文正常显示
- [ ] 开团提醒可正常发送
- [ ] 团录历史列表可正常查看

---

### Step 24：文档完善 + 简历包装

**优先级**：P3 | **预估工时**：1 天 | **依赖**：全部 Step

**任务清单**：

24.1 完善项目 README
- 项目简介
- 架构图
- 快速启动指南
- 功能特性列表
- 技术栈

24.2 API 文档
- docs/api.md
- 所有 API 接口说明
- 请求/响应示例

24.3 简历要点整理
- 基于 design.md 第 18 节
- 每个技术亮点的量化指标（如：防剧透成功率 100%，检索延迟 < 500ms）
- 包装技术深度（多 Agent 编排、RAG 混合检索、防剧透机制）

**交付检查**：
- [ ] README 内容完整、格式规范
- [ ] API 文档涵盖所有接口
- [ ] 简历要点可提取为 3-5 个 bullet point

---

## 步骤依赖总图

```
Phase 1:
  Step 1 (脚手架) ──→ Step 2 (数据库) ──→ Step 3 (模组解析) ──→ Step 4 (RAG)
                                          Step 5 (Bot) ──→ Step 6 (Orchestrator) ──→ Step 7 (整合测试)
                                              ↗
Phase 1 完成 ───────────────────────────────────

Phase 2:
  Step 8 (LangGraph) ──→ Step 9 (Classifier)
                      ──→ Step 10 (State + RAG + 骰子 + Player)
                      ──→ Step 11 (NPC Agent) ──→ Step 13 (Critic + Trace)
                      │                          ↗
                      ├──→ Step 11.5 (陪聊 Bot) ─┘
                      │
                      ──→ Step 12 (Plot + Rule + 分支) ──→ Step 13 ↗
Phase 2 完成 ───────────────────────────────────

Phase 3:
  Step 14 (前端框架) ──→ Step 15 (模组页面)
                      ──→ Step 16 (状态页面)
                      ──→ Step 17 (时间线 + 团录) ──→ Step 18 (图谱)

Phase 4:
  Step 19 (偏离增强)  Step 20 (防剧透评测)  Step 21 (多模型)  Step 22 (Benchmark)
  Step 23 (团录导出)  Step 24 (文档包装)
```

## 优先级与工时汇总

| 步骤 | 名称 | 优先级 | 预估工时 |
|------|------|--------|----------|
| Step 1 | 项目脚手架 | P0 ⚡ | 1-2 天 |
| Step 2 | 数据库层 | P0 ⚡ | 1-2 天 |
| Step 3 | 模组解析 | P0 ⚡ | 2-3 天 |
| Step 4 | RAG 检索 | P0 ⚡ | 1-2 天 |
| Step 5 | QQ Bot 接入 | P0 ⚡ | 2-3 天 |
| Step 6 | Orchestrator 主流程 | P0 ⚡ | 2-3 天 |
| Step 7 | MVP 整合测试 | P0 ⚡ | 1 天 |
| Step 8 | LangGraph 编排 | P1 | 1-2 天 |
| Step 9 | Classifier Agent | P1 | 0.5 天 |
| Step 10 | State + RAG Agent | P1 | 2-3 天 |
| Step 11 | NPC Agent | P1 | 1-2 天 |
| Step 11.5 | 陪聊 Bot 模块 | P1 | 1 天 |
| Step 12 | Plot + Rule + 分支创作 Agent | P1 | 1-2 天 |
| Step 13 | Critic + Trace | P1 | 1-2 天 |
| Step 14 | 前端项目搭建 | P2 | 1 天 |
| Step 15 | 模组管理页面 | P2 | 1-2 天 |
| Step 16 | 剧情状态页面 | P2 | 1-2 天 |
| Step 17 | 时间线 + 团录页面 | P2 | 2 天 |
| Step 18 | 剧情图谱页面 | P3 | 2 天 |
| Step 19 | 偏离检测增强 | P2 | 1 天 |
| Step 20 | 防剧透评测 | P2 | 1-2 天 |
| Step 21 | 多模型切换 | P3 | 1 天 |
| Step 22 | Benchmark | P3 | 2 天 |
| Step 23 | 团录导出 | P3 | 1 天 |
| Step 24 | 文档完善 | P3 | 1 天 |
| **总计** | | | **31-43 天** |
| **Phase 1 ⚡** | | | **10-16 天** |

> 注：工时估算基于单人全职开发。

---

## 关键设计决策记录

1. **Phase 1 消息处理走 LLM 直接调用，Phase 2 再引入 LangGraph**
   - 原因：MVP 快速验证核心链路，避免早期编排复杂度
   - 切换时机：Step 8 重构 orchestrator

2. **独立进程运行 NoneBot2，通过 HTTP 与 FastAPI 通信**
   - 原因：Bot 进程重启不影响 API 服务，职责分离

3. **模组格式优先支持 Markdown/TXT，PDF 作为增强**
   - 原因：PDF 解析质量不可控，MVP 阶段先保证核心体验

4. **防剧透采用「Prompt 约束 + Critic Agent 检查 + 输出过滤」三层机制**
   - 原因：单层可能失效，多层确保安全性

5. **检索优先使用语义向量检索，关键词检索作为补充**
   - 原因：模组内容以自然语言为主，语义检索更匹配
