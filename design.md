# ChronicleAgent Design Document

> 面向 QQ TRPG 跑团场景的多 Agent KP 辅助系统  
> A Multi-Agent Copilot for TRPG Keepers in QQ Groups

---

## 1. 项目背景

TRPG 跑团过程中，KP / DM 通常需要同时处理多个复杂任务：

- 阅读和记忆大量模组内容；
- 维护当前剧情进度；
- 记录玩家行动、线索发现和 NPC 态度变化；
- 根据玩家行为临场生成描述、台词和判定建议；
- 防止过早剧透关键线索；
- 在玩家偏离主线时提供自然的剧情引导；
- 跑团结束后整理团录和下次开团提醒。

传统跑团主要依赖 KP 人工维护信息，容易出现以下问题：

1. 模组信息量大，KP 容易忘记关键线索；
2. 玩家发言较多时，剧情状态难以及时同步；
3. 团录整理耗时，容易遗漏重要事件；
4. NPC 设定和隐藏信息容易前后不一致；
5. 玩家跑偏时，KP 需要临场构造合理引导。

ChronicleAgent 的目标是构建一个面向 QQ 跑团场景的 AI KP Copilot。它不会替代 KP，而是在后台监听群聊、检索模组知识、维护剧情状态，并通过私聊或 Web 控制台为 KP 提供辅助建议。

---

## 2. 项目定位

ChronicleAgent 是一个面向 QQ 群跑团场景的多 Agent 辅助系统。

核心定位：

> 让 AI 成为 KP 的副驾驶，而不是取代 KP。

系统通过 QQ Bot 接入跑团群，持续监听玩家发言，并结合模组文档、角色卡、历史团录和当前剧情状态，为 KP 提供以下能力：

- 模组知识检索；
- 剧情状态追踪；
- 主线偏离检测；
- NPC 台词与行为建议；
- 防剧透输出；
- 规则与骰点辅助；
- 自动团录总结；
- Web 可视化控制台。

---

## 3. 核心用户与应用场景

### 3.1 核心用户

| 用户 | 需求 |
|---|---|
| KP / DM | 管理剧情、NPC、线索、判定和团录 |
| 玩家 | 获得流畅的跑团体验 |
| 模组作者 | 测试模组节奏和线索设计 |
| TRPG 社群 | 降低开团门槛，提高团录整理效率 |

### 3.2 典型应用场景

#### 场景一：模组线索提醒

玩家在 QQ 群中发言：

```text
我想调查书房里的那幅画像。
```

系统检索模组后，私聊 KP：

```text
检测到玩家正在调查“书房画像”。

相关模组内容：
- 画像后方藏有伯爵旧信；
- 需要通过调查 / 侦查检定发现；
- 该线索是进入地下室剧情的关键入口。

建议描述：
“你注意到画像边框附近有细微磨损，似乎曾被人反复移动过。”

隐藏提示：
如果玩家检定成功，可以让其发现画像后的暗格。
```

#### 场景二：主线偏离检测

玩家连续讨论无关 NPC，长时间没有推进剧情。

系统私聊 KP：

```text
当前偏离程度：中等

原因：
1. 玩家连续 12 轮讨论无关商人；
2. 当前主线目标应为调查庄园二楼；
3. 关键线索“伯爵旧信”尚未触发。

建议：
- 温和推进：让老管家提醒二楼传来异响；
- 强推进：触发画像掉落事件；
- 自由探索：继续当前互动，但提示该 NPC 无更多有效信息。
```

#### 场景三：NPC 台词生成

玩家询问 NPC：

```text
你是不是知道地下室发生过什么？
```

系统根据 NPC 人设生成建议：

```text
NPC：老管家
人设：谨慎、沉默、对伯爵家族有愧疚感，不会主动透露地下室秘密。

建议台词：
“地下室？那地方已经很多年没人去了……先生，我劝您别再追问。”

KP 隐藏提示：
老管家知道地下室入口在书房画像后，但当前不应直接透露。
如果玩家成功说服或威胁，可以透露“画像”相关线索。
```

#### 场景四：自动团录总结

跑团结束后，KP 输入：

```text
/总结本次团录
```

系统生成：

```markdown
# 第 3 次跑团记录

## 本次主要进展
玩家进入废弃庄园二楼，调查书房画像，并发现画像边框存在移动痕迹。

## 已获得线索
- 沾血的钥匙
- 破损的家族画像
- 老管家对地下室表现出明显回避

## 未触发线索
- 伯爵旧信
- 地下室入口

## 下次 KP 提醒
建议从“画像后的暗格”继续推进，可安排老管家在门外偷听。
```

---

## 4. 系统目标

### 4.1 功能目标

ChronicleAgent 需要实现：

1. QQ 群聊消息监听；
2. KP 私聊指令交互；
3. 模组文档上传与解析；
4. 基于 RAG 的模组知识检索；
5. 当前剧情状态维护；
6. 玩家行为与主线偏离检测；
7. NPC 台词和行为建议生成；
8. 防剧透输出机制；
9. 自动团录总结；
10. Web 控制台展示剧情状态和 Agent 执行过程。

### 4.2 非功能目标

| 目标 | 说明 |
|---|---|
| 可扩展性 | 支持不同规则系统，如 CoC、DND、无限流等 |
| 可观测性 | 记录每次 Agent 检索、推理、建议和状态更新 |
| 安全性 | 区分玩家可见内容和 KP 私密内容，防止剧透 |
| 可维护性 | Agent 模块职责清晰，方便替换模型和工具 |
| 低成本 | 使用动态上下文选择降低 token 消耗 |
| 易部署 | 使用 Docker Compose 一键启动 |

---

## 5. 技术选型

### 5.1 后端技术

| 模块 | 技术选型 | 说明 |
|---|---|---|
| API 服务 | FastAPI | 提供 Bot、前端和 Agent 调用接口 |
| Agent 编排 | LangGraph | 实现有状态、多分支、多 Agent 流程 |
| QQ Bot | NoneBot2 + OneBot v11 | 接入 QQ 群消息 |
| QQ 协议端 | NapCatQQ / Lagrange.OneBot | 提供 OneBot 适配 |
| 文档解析 | PyMuPDF / MarkItDown / Unstructured | 解析 PDF、Markdown、TXT |
| 向量数据库 | Qdrant | 存储模组、团录和角色记忆向量 |
| 关系数据库 | PostgreSQL | 存储 campaign、scene、npc、trace 等结构化数据 |
| 缓存 | Redis | 缓存短期上下文和任务状态 |
| LLM 接入 | OpenAI / DeepSeek / Qwen / Claude | 支持多模型切换 |
| 观测 | Langfuse / OpenTelemetry | 记录 Agent 调用链路 |
| 部署 | Docker Compose | 方便本地与服务器部署 |

### 5.2 前端技术

| 模块 | 技术选型 | 说明 |
|---|---|---|
| Web 框架 | Next.js / React | 控制台页面 |
| UI 组件 | shadcn/ui | 快速构建现代化界面 |
| 状态管理 | Zustand | 管理前端状态 |
| 图谱展示 | React Flow | 展示 NPC、线索、地点关系 |
| 图表展示 | ECharts / Recharts | 展示建议评分、偏离程度 |
| 代码 / JSON 查看 | Monaco Editor | 查看 Agent Trace 和结构化状态 |

---

## 6. 总体架构

```text
QQ Group
  ↓
NapCatQQ / OneBot
  ↓
NoneBot2
  ↓
FastAPI Agent Service
  ↓
LangGraph Orchestrator
  ├── Message Classifier Agent
  ├── Module RAG Agent
  ├── State Tracking Agent
  ├── Plot Deviation Agent
  ├── NPC Roleplay Agent
  ├── Rule Assistant Agent
  ├── Summary Agent
  └── Critic Agent
  ↓
Tools
  ├── Dice Roller
  ├── Module Search
  ├── Rule Search
  ├── Character Memory
  ├── Scene Graph
  └── Markdown Export
  ↓
PostgreSQL + Qdrant + Redis
  ↓
Next.js Dashboard
```

---

## 7. 多 Agent 设计

### 7.1 Message Classifier Agent

职责：

- 判断群聊消息类型；
- 区分玩家行动、角色扮演、闲聊、规则问题、KP 指令；
- 判断是否需要触发其他 Agent。

输入：

```json
{
  "sender": "玩家A",
  "message": "我想调查书房里的画像",
  "recent_context": ["玩家进入书房", "老管家站在门外"]
}
```

输出：

```json
{
  "message_type": "player_action",
  "need_rag": true,
  "need_state_update": true,
  "need_kp_suggestion": true
}
```

### 7.2 Module RAG Agent

职责：

- 检索模组中与当前玩家行为相关的内容；
- 返回相关 NPC、地点、线索、剧情节点；
- 支持多跳检索，例如从地点检索到隐藏线索，再检索到后续剧情。

检索优先级：

1. 当前场景相关内容；
2. 当前 NPC 相关内容；
3. 当前玩家行动相关线索；
4. 未触发的关键剧情节点；
5. 历史团录中的相关事件。

### 7.3 State Tracking Agent

职责：

- 维护当前剧情状态；
- 更新场景、NPC、线索、玩家目标和物品状态；
- 将自然语言群聊转成结构化状态。

状态示例：

```json
{
  "current_scene": "废弃庄园二楼书房",
  "active_npcs": ["老管家"],
  "discovered_clues": ["破损的家族画像"],
  "undiscovered_clues": ["伯爵旧信", "地下室入口"],
  "plot_stage": "第二幕：调查庄园",
  "player_goals": {
    "玩家A": "寻找失踪妹妹",
    "玩家B": "调查庄园诅咒"
  }
}
```

### 7.4 Plot Deviation Agent

职责：

- 判断玩家当前行为是否偏离主线；
- 计算偏离程度；
- 为 KP 提供自然引导建议。

偏离分数设计：

```text
Deviation Score =
0.35 * 当前对话与主线目标相似度不足
+ 0.25 * 关键线索长时间未触发
+ 0.20 * 玩家行动与当前场景无关
+ 0.10 * NPC 行为偏离设定
+ 0.10 * 当前场景停留过久
```

输出：

```json
{
  "deviation_level": "medium",
  "reason": [
    "玩家连续多轮讨论无关 NPC",
    "关键线索“伯爵旧信”尚未触发"
  ],
  "suggestions": [
    "让老管家提醒二楼传来异响",
    "触发画像轻微晃动",
    "提示当前商人无更多有效信息"
  ]
}
```

### 7.5 NPC Roleplay Agent

职责：

- 根据 NPC 人设、当前剧情、隐藏信息生成台词；
- 区分玩家可见台词和 KP 隐藏提示；
- 保持 NPC 前后一致。

输入：

```json
{
  "npc": "老管家",
  "player_question": "你是不是知道地下室发生过什么？",
  "npc_profile": {
    "personality": "谨慎、沉默、有愧疚感",
    "secret": "知道地下室入口在书房画像后"
  }
}
```

输出：

```json
{
  "public_line": "地下室？那地方已经很多年没人去了……先生，我劝您别再追问。",
  "kp_note": "老管家知道画像后的暗格，但当前不应直接透露。",
  "risk": "low"
}
```

### 7.6 Rule Assistant Agent

职责：

- 查询规则；
- 根据玩家行动建议判定类型；
- 自动生成骰点指令；
- 解释判定结果。

示例：

```json
{
  "action": "调查画像",
  "suggested_check": "侦查 / 调查",
  "difficulty": "普通",
  "dice_command": ".r 1d100",
  "success_effect": "发现画像边框磨损",
  "failure_effect": "只能发现画像年代久远"
}
```

### 7.7 Summary Agent

职责：

- 整理本次团录；
- 提取关键事件、线索、NPC 态度、玩家状态；
- 生成 Markdown 团录；
- 生成下次 KP 提醒。

### 7.8 Critic Agent

职责：

- 检查系统输出是否剧透；
- 检查 NPC 台词是否违背设定；
- 检查建议是否与模组矛盾；
- 检查是否过度干预玩家自由。

检查项：

```text
1. 是否泄露隐藏线索？
2. 是否提前暴露结局？
3. 是否让 NPC 说出不该知道的信息？
4. 是否与历史团录矛盾？
5. 是否破坏玩家选择自由？
```

---

## 8. Harness 设计

ChronicleAgent 内部包含一个 TRPG Agent Harness，用于统一管理 Agent 的输入、上下文、工具、权限、输出和评测。

```text
TRPG Agent Harness
├── Input Manager
│   ├── 群聊消息
│   ├── KP 指令
│   ├── 模组文档
│   └── 角色卡
├── Context Manager
│   ├── RAG 检索
│   ├── 当前剧情状态
│   ├── 历史团录
│   └── 角色长期记忆
├── Tool Manager
│   ├── Dice Roller
│   ├── Module Search
│   ├── Rule Search
│   └── Markdown Export
├── Permission Manager
│   ├── 玩家可见内容
│   ├── KP 私密内容
│   └── 禁止输出内容
├── Output Verifier
│   ├── 防剧透检查
│   ├── 一致性检查
│   └── 幻觉检查
└── Trace Recorder
    ├── Agent 输入
    ├── 检索结果
    ├── 推理输出
    └── 最终建议
```

---

## 9. 数据库设计

### 9.1 campaigns

存储跑团项目。

```sql
CREATE TABLE campaigns (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    system_type VARCHAR(64),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.2 modules

存储模组原文和解析结果。

```sql
CREATE TABLE modules (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id),
    title VARCHAR(255),
    raw_text TEXT,
    parsed_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.3 characters

存储玩家角色信息。

```sql
CREATE TABLE characters (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id),
    player_name VARCHAR(255),
    character_name VARCHAR(255),
    profile JSONB,
    status JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.4 npcs

存储 NPC 设定。

```sql
CREATE TABLE npcs (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id),
    name VARCHAR(255),
    personality TEXT,
    secret TEXT,
    relationship_state JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.5 scenes

存储剧情场景状态。

```sql
CREATE TABLE scenes (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id),
    name VARCHAR(255),
    summary TEXT,
    active_npcs JSONB,
    discovered_clues JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.6 clues

存储线索。

```sql
CREATE TABLE clues (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id),
    name VARCHAR(255),
    location VARCHAR(255),
    trigger_condition TEXT,
    discovered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.7 messages

存储群聊消息。

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id),
    sender VARCHAR(255),
    content TEXT,
    role VARCHAR(64),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.8 agent_traces

存储 Agent 执行记录。

```sql
CREATE TABLE agent_traces (
    id UUID PRIMARY KEY,
    campaign_id UUID REFERENCES campaigns(id),
    agent_name VARCHAR(255),
    input JSONB,
    output JSONB,
    retrieved_context JSONB,
    tool_calls JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 10. API 设计

### 10.1 上传模组

```http
POST /api/modules/upload
```

请求：

```json
{
  "campaign_id": "uuid",
  "file": "module.pdf"
}
```

返回：

```json
{
  "module_id": "uuid",
  "status": "parsed",
  "chunks": 128
}
```

### 10.2 查询模组

```http
POST /api/rag/query
```

请求：

```json
{
  "campaign_id": "uuid",
  "query": "书房画像有什么线索？"
}
```

返回：

```json
{
  "answer": "画像后藏有伯爵旧信，需要调查检定发现。",
  "sources": [
    {
      "chunk_id": "chunk_001",
      "text": "画像背后藏有一封伯爵旧信……"
    }
  ]
}
```

### 10.3 处理群聊消息

```http
POST /api/messages/handle
```

请求：

```json
{
  "campaign_id": "uuid",
  "sender": "玩家A",
  "content": "我想调查书房里的画像"
}
```

返回：

```json
{
  "need_kp_notify": true,
  "kp_suggestion": "建议让玩家进行调查检定……"
}
```

### 10.4 获取当前剧情状态

```http
GET /api/campaigns/{campaign_id}/state
```

返回：

```json
{
  "current_scene": "废弃庄园二楼书房",
  "plot_stage": "第二幕：调查庄园",
  "discovered_clues": ["破损的家族画像"],
  "active_npcs": ["老管家"]
}
```

### 10.5 生成团录

```http
POST /api/summaries/generate
```

请求：

```json
{
  "campaign_id": "uuid",
  "message_range": "latest_session"
}
```

返回：

```json
{
  "markdown": "# 第 3 次跑团记录\n\n## 本次主要进展..."
}
```

---

## 11. 前端页面设计

### 11.1 模组知识库页面

功能：

- 上传模组；
- 查看解析结果；
- 查看 NPC、地点、线索、剧情节点；
- 手动编辑结构化信息。

### 11.2 当前剧情状态页面

功能：

- 查看当前场景；
- 查看活跃 NPC；
- 查看已发现 / 未发现线索；
- 查看玩家目标；
- 手动修正状态。

### 11.3 Agent 建议时间线页面

功能：

- 展示每次 Agent 触发原因；
- 展示检索到的模组内容；
- 展示给 KP 的建议；
- 展示 Critic Agent 的风险检查结果。

### 11.4 团录总结页面

功能：

- 自动生成团录；
- 支持 Markdown 编辑；
- 支持导出 Markdown / PDF；
- 支持生成下次开团提醒。

### 11.5 剧情图谱页面

功能：

- 展示 NPC、地点、线索和主线节点的关系；
- 标记已触发线索；
- 标记未触发关键节点；
- 展示玩家当前位置和剧情进度。

---

## 12. 核心流程设计

### 12.1 群聊监听流程

```text
QQ 群消息
  ↓
NoneBot2 接收
  ↓
Message Classifier Agent 判断消息类型
  ↓
如果是玩家行动：
    调用 Module RAG Agent
    调用 State Tracking Agent
    调用 Plot Deviation Agent
    调用 Critic Agent
  ↓
如果需要提醒：
    私聊 KP
  ↓
写入 agent_traces
```

### 12.2 模组上传流程

```text
KP 上传 PDF / Markdown / TXT
  ↓
文档解析
  ↓
文本切分
  ↓
结构化抽取 NPC / 地点 / 线索 / 剧情节点
  ↓
写入 PostgreSQL
  ↓
生成 Embedding
  ↓
写入 Qdrant
```

### 12.3 团录总结流程

```text
选择消息范围
  ↓
读取群聊记录
  ↓
提取关键事件
  ↓
更新线索和 NPC 状态
  ↓
生成 Markdown 团录
  ↓
Critic Agent 检查遗漏和矛盾
  ↓
保存到数据库
```

---

## 13. RAG 设计

### 13.1 文档切分策略

模组文档不适合简单按固定长度切分，需要结合结构：

1. 按标题层级切分章节；
2. 按 NPC、地点、线索、剧情节点进行语义切分；
3. 每个 chunk 保留来源章节；
4. 隐藏线索标记为 KP-only；
5. 关键节点建立关系索引。

chunk 示例：

```json
{
  "chunk_id": "chunk_001",
  "type": "clue",
  "title": "伯爵旧信",
  "location": "书房画像后",
  "visibility": "kp_only",
  "text": "画像后藏有伯爵旧信，是进入地下室剧情的关键线索。",
  "related_nodes": ["地下室入口", "老管家", "第二幕"]
}
```

### 13.2 检索策略

使用混合检索：

```text
最终召回结果 =
语义向量检索
+ 关键词检索
+ 当前场景过滤
+ NPC / 地点关系扩展
+ 未触发关键线索加权
```

### 13.3 重排序策略

优先级：

1. 当前场景相关；
2. 当前 NPC 相关；
3. 与玩家行动高度相似；
4. 未触发关键线索；
5. 与当前主线节点相关。

---

## 14. 防剧透机制

系统输出分为两类：

### 14.1 玩家可见内容

可以出现在 QQ 群中：

```text
你注意到画像边框附近有一些细微磨损。
```

### 14.2 KP 私密内容

只能私聊 KP 或显示在控制台：

```text
画像背后藏有伯爵旧信，是进入地下室剧情的关键线索。
```

### 14.3 输出检查规则

Critic Agent 需要检查：

```text
1. 玩家可见内容是否包含隐藏线索？
2. 是否直接暴露 NPC 秘密？
3. 是否提前透露结局？
4. 是否破坏玩家探索过程？
5. 是否与当前已发现信息冲突？
```

---

## 15. 评测指标

### 15.1 系统效果指标

| 指标 | 说明 |
|---|---|
| Clue Recall | 相关线索召回率 |
| State Accuracy | 剧情状态更新准确率 |
| Spoiler Safety | 防剧透成功率 |
| Suggestion Relevance | KP 建议相关性 |
| Summary Completeness | 团录完整度 |
| Latency | 单次建议生成延迟 |
| Cost | 单次建议 token 成本 |

### 15.2 人工评分指标

KP 可以对每条建议评分：

| 分数 | 含义 |
|---|---|
| 1 | 完全无用 |
| 2 | 有少量参考价值 |
| 3 | 基本可用 |
| 4 | 很有帮助 |
| 5 | 可以直接采用 |

### 15.3 自动评测任务

构造模拟跑团数据：

```text
任务 1：玩家调查关键地点，系统是否召回正确线索？
任务 2：玩家长时间偏离主线，系统是否给出合理提醒？
任务 3：NPC 被询问秘密，系统是否避免剧透？
任务 4：跑团结束后，系统是否完整总结获得线索？
任务 5：玩家行为改变场景状态，系统是否正确更新状态？
```

---

## 16. 项目目录结构

```text
chronicle-agent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── modules.py
│   │   │   ├── messages.py
│   │   │   ├── campaigns.py
│   │   │   └── summaries.py
│   │   ├── agents/
│   │   │   ├── classifier_agent.py
│   │   │   ├── rag_agent.py
│   │   │   ├── state_agent.py
│   │   │   ├── plot_agent.py
│   │   │   ├── npc_agent.py
│   │   │   ├── rule_agent.py
│   │   │   ├── summary_agent.py
│   │   │   └── critic_agent.py
│   │   ├── harness/
│   │   │   ├── orchestrator.py
│   │   │   ├── context_manager.py
│   │   │   ├── permission_manager.py
│   │   │   ├── tool_manager.py
│   │   │   └── trace_recorder.py
│   │   ├── rag/
│   │   │   ├── document_parser.py
│   │   │   ├── chunker.py
│   │   │   ├── retriever.py
│   │   │   └── reranker.py
│   │   ├── bot/
│   │   │   ├── nonebot_adapter.py
│   │   │   └── commands.py
│   │   ├── tools/
│   │   │   ├── dice.py
│   │   │   ├── rule_search.py
│   │   │   ├── module_search.py
│   │   │   └── markdown_export.py
│   │   ├── storage/
│   │   │   ├── postgres.py
│   │   │   ├── qdrant.py
│   │   │   └── redis.py
│   │   └── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── ModuleManager.tsx
│   │   │   ├── StatePanel.tsx
│   │   │   ├── AgentTimeline.tsx
│   │   │   ├── StoryGraph.tsx
│   │   │   └── SummaryEditor.tsx
│   │   └── lib/
│   └── package.json
├── docker-compose.yml
├── docs/
│   ├── design.md
│   ├── api.md
│   └── deployment.md
├── examples/
│   ├── demo_module.md
│   ├── demo_messages.jsonl
│   └── demo_character_cards/
└── README.md
```

---

## 17. MVP 开发计划

### Phase 1：基础可运行版本

目标：实现 QQ Bot + 模组检索 + KP 私聊建议。

任务：

- 搭建 FastAPI 后端；
- 接入 NoneBot2；
- 支持上传 Markdown / TXT 模组；
- 实现简单 RAG 检索；
- 实现 `/查线索`、`/当前状态` 指令；
- 支持 KP 私聊建议。

### Phase 2：多 Agent 协作版本

目标：实现剧情状态追踪和 NPC 建议。

任务：

- 使用 LangGraph 编排 Agent；
- 实现 Message Classifier Agent；
- 实现 State Tracking Agent；
- 实现 NPC Roleplay Agent；
- 实现 Critic Agent；
- 保存 Agent Trace。

### Phase 3：Web 控制台版本

目标：实现可视化展示。

任务：

- 模组管理页面；
- 当前剧情状态页面；
- Agent 建议时间线；
- 团录总结页面；
- 剧情图谱页面。

### Phase 4：增强版本

目标：提升简历竞争力。

任务：

- 主线偏离检测；
- 防剧透评分；
- 多模型切换；
- 建议人工评分；
- 自动生成 Benchmark；
- 支持 Markdown / PDF 团录导出。

---

## 18. 简历亮点

可以在简历中这样描述：

```text
ChronicleAgent：面向 QQ TRPG 跑团的多 Agent KP 辅助系统
- 基于 NoneBot2、FastAPI、LangGraph、Qdrant 和 PostgreSQL 构建 QQ 群跑团辅助 Agent，支持模组文档解析、剧情状态追踪、NPC 台词生成、主线偏离检测与自动团录总结。
- 设计 Context Agent、State Agent、Plot Agent、NPC Agent、Rule Agent、Critic Agent 等多 Agent 协作流程，实现从群聊消息监听、模组检索、状态更新到 KP 私聊建议的闭环辅助。
- 构建基于 RAG 的模组知识库，支持对 NPC、地点、线索、剧情节点进行结构化抽取与多跳检索，提高复杂模组场景下的信息召回能力。
- 实现防剧透输出机制，将玩家可见描述与 KP 私密提示分离，并通过 Critic Agent 检查 NPC 设定冲突、隐藏线索泄露和剧情一致性问题。
- 设计剧情偏离检测算法，根据玩家发言、当前场景、关键线索触发情况和主线节点相似度，为 KP 提供回归主线、自由探索或强制推进等多策略建议。
- 实现 Agent Trace 与 Web 控制台，展示检索内容、推理过程、剧情状态变化、团录摘要和建议评分，提升系统可观测性与可调试性。
```

---

## 19. 风险与解决方案

| 风险 | 解决方案 |
|---|---|
| QQ Bot 接入不稳定 | 抽象 Bot Adapter，支持 OneBot、WebSocket、模拟消息输入 |
| 模组 PDF 解析质量差 | 优先支持 Markdown / TXT，PDF 作为增强功能 |
| Agent 容易剧透 | 引入 Visibility 字段和 Critic Agent |
| 成本过高 | 使用动态上下文选择、缓存、低价模型 |
| 状态更新不准确 | 支持 KP 手动修正状态 |
| 多 Agent 流程复杂 | MVP 先做 3 个 Agent，再逐步扩展 |
| 跑团规则差异大 | 规则系统插件化，先支持通用判定 |

---

## 20. 后续扩展方向

1. 支持 CoC / DND 规则插件；
2. 支持地图和战斗轮次管理；
3. 支持角色卡自动读取；
4. 支持语音跑团记录转写；
5. 支持模组作者测试工具；
6. 支持剧情图谱自动生成；
7. 支持 MCP 工具接入；
8. 支持多模型效果对比；
9. 支持本地模型离线部署；
10. 支持 Discord / KOOK / Telegram 等平台。

---

## 21. 总结

ChronicleAgent 的核心价值不是让 AI 取代 KP，而是通过多 Agent、RAG、长期记忆、剧情状态追踪和防剧透机制，为 KP 提供一个可控、可解释、可回放的 AI 辅助系统。

它具备明确应用场景、完整工程链路和较强技术深度，适合作为 Agent 方向的简历项目。

最终项目关键词：

```text
Multi-Agent
RAG
Long-term Memory
QQ Bot
TRPG
Human-in-the-loop
Agent Harness
Spoiler Safety
Story State Tracking
Agent Observability
```
