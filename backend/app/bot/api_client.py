"""Bot API 客户端 — 通过 HTTP 调用 FastAPI 后端"""

import httpx
from typing import Optional, Dict, Any

from app.bot.config import bot_settings


class BotAPIClient:
    """封装对 FastAPI 后端的 HTTP 调用"""

    def __init__(self):
        self.base_url = bot_settings.api_base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._client

    async def handle_message(
        self, campaign_id: str, sender: str, content: str
    ) -> Dict[str, Any]:
        """将群消息发给 FastAPI 处理"""
        resp = await self.client.post(
            "/api/messages/handle",
            json={
                "campaign_id": campaign_id,
                "sender": sender,
                "content": content,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def rag_query(
        self, campaign_id: str, query: str, top_k: int = 5
    ) -> Dict[str, Any]:
        """RAG 检索"""
        resp = await self.client.post(
            "/api/rag/query",
            json={
                "campaign_id": campaign_id,
                "query": query,
                "top_k": top_k,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_campaign_state(self, campaign_id: str) -> Dict[str, Any]:
        """获取剧情状态"""
        resp = await self.client.get(f"/api/campaigns/{campaign_id}/state")
        resp.raise_for_status()
        return resp.json()

    async def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """获取跑团项目信息"""
        resp = await self.client.get(f"/api/campaigns/{campaign_id}")
        resp.raise_for_status()
        return resp.json()

    async def list_campaigns(self) -> Dict[str, Any]:
        """获取所有跑团项目"""
        resp = await self.client.get("/api/campaigns")
        resp.raise_for_status()
        return resp.json()

    async def generate_summary(self, campaign_id: str) -> Dict[str, Any]:
        """生成团录"""
        resp = await self.client.post(
            "/api/summaries/generate",
            json={"campaign_id": campaign_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def kp_command(self, campaign_id: str, command: str, args: str = "") -> Dict[str, Any]:
        """KP 指令处理"""
        resp = await self.client.post(
            "/api/messages/kp-command",
            json={
                "campaign_id": campaign_id,
                "command": command,
                "args": args,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


api_client = BotAPIClient()
