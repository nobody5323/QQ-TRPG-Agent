"""Qdrant 向量存储客户端

负责模组 chunk 的向量化存储和相似度检索。
"""

from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient as SyncQdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import settings


# 集合名称常量
COLLECTION_MODULE_CHUNKS = "module_chunks"
VECTOR_SIZE = settings.EMBEDDING_DIMENSION


class QdrantStore:
    """Qdrant 向量存储封装"""

    def __init__(self):
        self._client: Optional[SyncQdrantClient] = None

    @property
    def client(self) -> SyncQdrantClient:
        if self._client is None:
            self._client = SyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )
        return self._client

    def _ensure_collection(self):
        """确保集合存在（不存在则创建）"""
        collections = self.client.get_collections().collections
        names = [c.name for c in collections]

        if COLLECTION_MODULE_CHUNKS not in names:
            self.client.create_collection(
                collection_name=COLLECTION_MODULE_CHUNKS,
                vectors_config=qdrant_models.VectorParams(
                    size=VECTOR_SIZE,
                    distance=qdrant_models.Distance.COSINE,
                ),
                optimizers_config=qdrant_models.OptimizersConfigDiff(
                    indexing_threshold=10000,
                ),
            )
            # 创建 payload 索引
            self.client.create_payload_index(
                collection_name=COLLECTION_MODULE_CHUNKS,
                field_name="campaign_id",
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=COLLECTION_MODULE_CHUNKS,
                field_name="type",
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=COLLECTION_MODULE_CHUNKS,
                field_name="visibility",
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
            )

    def upsert_points(
        self,
        points: List[Dict[str, Any]],
    ):
        """批量写入向量点

        Args:
            points: [{id, vector, payload}] 列表
        """
        self._ensure_collection()

        qdrant_points = []
        for p in points:
            qdrant_points.append(
                qdrant_models.PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p.get("payload", {}),
                )
            )

        self.client.upsert(
            collection_name=COLLECTION_MODULE_CHUNKS,
            points=qdrant_points,
        )

    def search(
        self,
        vector: List[float],
        campaign_id: Optional[str] = None,
        top_k: int = 10,
        score_threshold: float = 0.0,
        filter_criteria: Optional[Dict] = None,
    ) -> List[Dict]:
        """向量相似度检索

        Args:
            vector: 查询向量
            campaign_id: 可选，限定跑团项目
            top_k: 返回数量
            score_threshold: 分数阈值
            filter_criteria: 额外过滤条件

        Returns:
            [{id, score, payload}]
        """
        self._ensure_collection()

        # 构建过滤条件
        must_filters = []
        if campaign_id:
            must_filters.append(
                qdrant_models.FieldCondition(
                    key="campaign_id",
                    match=qdrant_models.MatchValue(value=campaign_id),
                )
            )
        if filter_criteria:
            for key, value in filter_criteria.items():
                must_filters.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchValue(value=value),
                    )
                )

        query_filter = qdrant_models.Filter(must=must_filters) if must_filters else None

        results = self.client.search(
            collection_name=COLLECTION_MODULE_CHUNKS,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results
        ]

    def delete_by_campaign(self, campaign_id: str):
        """删除某个跑团项目下的所有向量"""
        self.client.delete(
            collection_name=COLLECTION_MODULE_CHUNKS,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="campaign_id",
                            match=qdrant_models.MatchValue(value=campaign_id),
                        )
                    ]
                )
            ),
        )

    def delete_point(self, point_id: str):
        """删除单个向量点"""
        self.client.delete(
            collection_name=COLLECTION_MODULE_CHUNKS,
            points_selector=qdrant_models.PointIdsList(
                points=[point_id],
            ),
        )


qdrant_store = QdrantStore()
