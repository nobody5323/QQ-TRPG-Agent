"""ChronicleAgent hybrid retrieval engine.

Why not GraphRAG:
1. TRPG modules are small (20-50 pages) - graph construction is overkill
2. Game state changes every few minutes - static graphs can't reflect dynamic plot
3. GraphRAG has no visibility concept - can't distinguish KP Only / Player Visible
4. Latency target <500ms - GraphRAG community detection takes minutes

Our pipeline:
  query -> QueryEnhancer (inject scene/NPC/clue context)
  -> parallel: [semantic vector search || keyword search]
  -> RRF fusion (Reciprocal Rank Fusion)
  -> rerank (scene +0.3, NPC +0.25, hidden +0.15)
  -> top-K

Five key differentiators from generic RAG:
1. State-Gated: check scene/NPC/clue state before retrieval
2. Undiscovered Boost: priority for unfound clues
3. Dual-Visibility: kp_only chunks auto-boosted for KP view
4. Scene-Scoped: active scene context injected into query
5. Hybrid + RRF: semantic + keyword fusion, no single-signal dependency
"""

import time
from typing import List, Dict, Any, Optional

from app.config import settings
from app.storage.qdrant import qdrant_store
from app.rag.query_enhancer import QueryContext, query_enhancer
from app.rag.keyword_search import keyword_searcher
from app.rag.embedding import embedding_service


class Retriever:
    """ChronicleAgent hybrid retriever with state-aware enhancement and RRF fusion."""

    RRF_K = 60

    def __init__(self):
        self.top_k = settings.RAG_TOP_K
        self.score_threshold = settings.RAG_SCORE_THRESHOLD

    async def search(
        self,
        query: str,
        campaign_id: Optional[str] = None,
        scene_context: Optional[str] = None,
        active_npcs: Optional[List[str]] = None,
        undiscovered_clue_names: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        enable_enhancement: bool = True,
        enable_keyword: bool = True,
    ) -> Dict[str, Any]:
        """Execute full hybrid retrieval pipeline.

        Returns dict with keys: results (list), meta (dict).
        """
        t_start = time.time()
        k = top_k or self.top_k

        # Step 1: Query enhancement - inject state context
        enhanced_query = query
        if enable_enhancement:
            ctx = QueryContext(
                query=query,
                active_scene=scene_context,
                active_npcs=active_npcs or [],
                undiscovered_clues=undiscovered_clue_names or [],
            )
            enhanced_query = query_enhancer.enhance(query, ctx, strategy="expansion")

        # Step 2: Parallel retrieval
        vector_results = []
        keyword_results = []

        query_vector = await embedding_service.embed_text(enhanced_query)
        vector_results = qdrant_store.search(
            vector=query_vector,
            campaign_id=campaign_id,
            top_k=k * 2,
            score_threshold=self.score_threshold,
        )

        if enable_keyword and campaign_id:
            keyword_results = keyword_searcher.search(
                query=query,
                campaign_id=campaign_id,
                top_k=k * 2,
            )

        # Step 3: RRF fusion
        fusion_method = "vector_only"
        if vector_results and keyword_results:
            merged = self._rrf_fusion(vector_results, keyword_results)
            fusion_method = "rrf"
        elif vector_results:
            merged = vector_results
        elif keyword_results:
            merged = keyword_results
            fusion_method = "keyword_only"
        else:
            latency_ms = round((time.time() - t_start) * 1000, 1)
            return {"results": [], "meta": {
                "query_original": query, "query_enhanced": enhanced_query,
                "vector_count": 0, "keyword_count": 0,
                "fusion_method": "none", "latency_ms": latency_ms,
                "within_target": latency_ms < 500,
            }}

        # Step 4: State-aware reranking
        reranked = self._rerank(
            results=merged,
            scene_context=scene_context,
            active_npcs=active_npcs,
        )

        final_results = reranked[:k]
        latency_ms = round((time.time() - t_start) * 1000, 1)

        return {
            "results": final_results,
            "meta": {
                "query_original": query,
                "query_enhanced": enhanced_query if enable_enhancement else query,
                "vector_count": len(vector_results),
                "keyword_count": len(keyword_results),
                "merged_count": len(merged),
                "fusion_method": fusion_method,
                "latency_ms": latency_ms,
                "within_target": latency_ms < 500,
            },
        }

    def _rrf_fusion(
        self, vector_results: List[Dict], keyword_results: List[Dict]
    ) -> List[Dict]:
        """Reciprocal Rank Fusion - no score normalization needed."""
        rrf_scores: Dict[str, float] = {}
        payload_map: Dict[str, Dict] = {}
        k = self.RRF_K

        for rank, item in enumerate(vector_results):
            cid = str(item["id"])
            rrf_scores[cid] = 1.0 / (k + rank + 1)
            payload_map[cid] = item.get("payload", {}) or {}

        for rank, item in enumerate(keyword_results):
            cid = str(item["id"])
            kw_score = 1.0 / (k + rank + 1)
            rrf_scores[cid] = rrf_scores.get(cid, 0) + kw_score
            if cid not in payload_map:
                payload_map[cid] = item.get("payload", {}) or {}

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        return [
            {"id": cid, "score": round(rrf_scores[cid], 4), "payload": payload_map.get(cid, {})}
            for cid in sorted_ids
        ]

    def _rerank(
        self,
        results: List[Dict],
        scene_context: Optional[str] = None,
        active_npcs: Optional[List[str]] = None,
    ) -> List[Dict]:
        """State-aware reranking with boosts per design.md Section 13.3."""
        scored = []
        for item in results:
            base_score = item.get("score", 0)
            payload = item.get("payload", {}) or {}
            boost = 0.0

            if scene_context and payload:
                text = payload.get("text", "")
                title = payload.get("title", "")
                location = payload.get("location", "")
                scene_term = scene_context.split(" (")[0] if " (" in scene_context else scene_context
                if scene_term in title or scene_term in location or scene_term in text[:200]:
                    boost += 0.3

            if active_npcs and payload:
                text = payload.get("text", "")
                related = payload.get("related_nodes", []) or []
                for npc in active_npcs:
                    if npc in related or npc in text[:300]:
                        boost += 0.25
                        break

            if payload.get("visibility") == "kp_only":
                boost += 0.15

            item["rerank_score"] = round(base_score + boost, 4)
            item["_boost_detail"] = {
                "base": round(base_score, 4),
                "scene_boost": 0.3 if (scene_context and payload.get("title") and (
                    scene_context.split(" (")[0] if " (" in scene_context else scene_context
                ) in payload["title"]) else 0,
                "npc_boost": 0.25 if active_npcs else 0,
                "hidden_boost": 0.15 if payload.get("visibility") == "kp_only" else 0,
            }
            scored.append(item)

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored

    async def search_simple(
        self,
        query_vector: List[float],
        campaign_id: Optional[str] = None,
        scene_context: Optional[str] = None,
        active_npcs: Optional[List[str]] = None,
        top_k: Optional[int] = None,
    ) -> List[Dict]:
        """Backward-compatible simple search (vector only + rerank)."""
        k = top_k or self.top_k
        results = qdrant_store.search(
            vector=query_vector,
            campaign_id=campaign_id,
            top_k=k * 2,
            score_threshold=self.score_threshold,
        )
        if not results:
            return []
        return self._rerank(results=results, scene_context=scene_context, active_npcs=active_npcs)[:k]


retriever = Retriever()
