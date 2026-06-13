# ChronicleAgent 部署文档

> 2 核 4G 云服务器推荐配置

## 环境要求

| 项目 | 要求 | 说明 |
|------|------|------|
| 服务器 | 2 核 4G | 本文档以此配置为准 |
| 系统盘 | 40GB+ | Docker 镜像 + 数据卷约占用 15-20GB |
| 操作系统 | Ubuntu 22.04 / Debian 12 | 推荐 |
| Docker | 24+ | 含 Docker Compose |
| 域名（可选） | - | 如需 HTTPS 需要域名 |

## 快速部署

### 1. 安装 Docker

```bash
# Ubuntu 22.04
curl -fsSL https://get.docker.com | bash -s docker
sudo usermod -aG docker $USER
# 登出重新登录使组生效
```

### 2. 克隆代码

```bash
git clone https://github.com/nobody5323/QQ-TRPG-Agent.git
cd QQ-TRPG-Agent
```

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env  # 修改以下必填项
```

必填项：
- `OPENAI_API_KEY` — LLM API 密钥
- `DB_PASSWORD` — 数据库密码（建议改为强密码）
- `SECRET_KEY` — 随机字符串

### 4. 启动服务

```bash
# 首次启动（构建镜像 + 启动所有服务）
docker compose up -d

# 查看启动日志
docker compose logs -f

# 检查健康状态
curl http://localhost:8000/health
```

预期返回：
```json
{
  "status": "ok",
  "version": "0.1.0",
  "db": "connected",
  "redis": "connected"
}
```

### 5. 配置 QQ Bot（Phase 1 中完成）

详见 `docs/qq-bot-setup.md`。

## 服务架构

```text
                          公网
                            │
            ┌───────────────┼───────────────┐
            │               │               │
       HTTP:8000         QQ 协议        WebSocket
       (后端 API)      (NapCatQQ)      (前端, Phase 3)
            │               │               │
            ▼               ▼               ▼
        ┌──────┐       ┌────────┐      ┌────────┐
        │backend│◄─────│  bot   │      │frontend│
        └──┬───┘       └────────┘      └────────┘
           │
     ┌─────┼─────┬──────────────┐
     ▼     ▼     ▼              ▼
  postgres qdrant redis    (LLM API)
```

## 内存分配（2C4G 峰值约 3.2GB）

| 服务 | 内存 | 说明 |
|------|------|------|
| PostgreSQL | ~700MB | shared_buffers=512MB + 其他 |
| Qdrant | ~300-500MB | 取决于向量数量 |
| Redis | ~150MB | maxmemory=256MB |
| Backend (Python) | ~300-500MB | FastAPI + Agent 逻辑 |
| Bot | ~500-800MB | NapCatQQ 含 Chromium |
| OS + Docker | ~500MB | 系统进程和容器层 |
| **合计** | **~2.5-3.2GB** | 留有 800MB+ 余量 |

## 日常运维

### 查看状态

```bash
# 所有服务状态
docker compose ps

# 实时日志
docker compose logs -f backend

# 各服务资源占用
docker stats
```

### 重启服务

```bash
# 重启全部
docker compose restart

# 重启单个服务
docker compose restart backend
```

### 更新代码

```bash
git pull
docker compose build backend bot
docker compose up -d
```

### 备份数据

```bash
# PostgreSQL 备份
docker compose exec -T postgres pg_dump -U chronicle chronicle > backup_$(date +%Y%m%d).sql

# Qdrant 备份（直接备份数据卷目录）
tar czf qdrant_backup_$(date +%Y%m%d).tar.gz /var/lib/docker/volumes/qq-trpg-agent_qdrant_storage/
```

### 日志清理（防止 40GB 系统盘占满）

```bash
# Docker 日志清理
sudo journalctl --vacuum-time=7d
docker system prune -f

# 或在 docker-compose.yml 中已配置 max-size=10m, max-file=3
```

## 安全注意事项

1. **不要暴露 PostgreSQL/Qdrant/Redis 端口到公网**
   - 已在 docker-compose.yml 中配置为 `127.0.0.1:PORT:PORT`
   - 确保云服务器安全组只开放 `8000`（和将来前端的 `3000` 或 `443`）

2. **修改默认密码**
   - `DB_PASSWORD` 不要用 `chronicle_secret`
   - `SECRET_KEY` 必须修改

3. **如果需要 HTTPS**
   - 建议前置 Nginx 反代 + Let's Encrypt（certbot）
   - 参考 `docs/nginx-ssl.md`

## 常见问题

**Q: `docker compose up -d` 后服务启动失败？**
A: 查看日志 `docker compose logs <service-name>`，最常见原因是 OpenAI API Key 未配置。

**Q: 40GB 磁盘不够用？**
A: 定期运行 `docker system prune -f` 清理无用镜像和缓存。PostgreSQL 日志默认会增长，已在配置中限制。

**Q: 如何切换 LLM 模型？**
A: 修改 `.env` 中的 `LLM_PROVIDER` 和对应 API Key，然后 `docker compose restart backend`。

**Q: 如何从 pgvector 切换到 Qdrant？**
A: 修改 `.env` 中 `VECTOR_STORE=qdrant`，重启后端。数据不会自动迁移，需要重新上传模组。
