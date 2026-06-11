"""Embedding 服务 — 调用 LLM API 生成向量"""

from typing import List, Optional
from openai import AsyncOpenAI

from app.config import settings


class EmbeddingService:
    """文本向量化服务"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION

    async def embed_text(self, text: str) -> List[float]:
        """生成单条文本的向量"""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimension,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量生成向量"""
        if not texts:
            return []
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimension,
        )
        # 按输入顺序排序
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]


embedding_service = EmbeddingService()
