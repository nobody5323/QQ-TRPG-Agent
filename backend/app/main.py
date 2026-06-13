"""ChronicleAgent — FastAPI 应用入口"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.storage.database import engine, create_tables
from app.storage.redis import redis_client
from app.api import modules, messages, campaigns, summaries, rag

# --- API 路由不急于全部实现，先挂载 health ---
# from app.api import routers...


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：创建数据库表、连接 Redis
    await create_tables()
    await redis_client.initialize()
    yield
    # 关闭时：清理连接
    await engine.dispose()
    await redis_client.close()


app = FastAPI(
    title="ChronicleAgent",
    description="面向 QQ TRPG 跑团场景的多 Agent KP 辅助系统",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置（开发阶段允许前端 localhost 访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 健康检查 ──────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """服务健康状态"""
    from app.storage.database import check_db_connection
    db_ok = await check_db_connection()
    redis_ok = await redis_client.ping()
    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "version": "0.1.0",
        "db": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
    }


# ── 路由注册（Phase 1 逐模块挂载） ─────────────────────
app.include_router(modules.router, prefix="/api/modules", tags=["modules"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])
app.include_router(summaries.router, prefix="/api/summaries", tags=["summaries"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
