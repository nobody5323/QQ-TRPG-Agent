"""Keyword search on Qdrant payloads - complements semantic vector search."""

import re
from typing import List, Dict, Optional


class KeywordSearcher:
    """Keyword-based retriever using Qdrant payload text matching.

    Strategy:
    1. Tokenize query (split + 2-gram for Chinese)
    2. Scroll all chunks for the campaign from Qdrant
    3. Count keyword hits in text/title/location fields
    4. Sort by hit count, return top-k
    """

    _SEP_PATTERN = re.compile(r'[，。！？、；：""''（）《》【】\s]+')
    _MIN_TERM_LEN = 2

    def search(
        self,
        query: str,
        campaign_id: str,
        top_k: int = 10,
        min_term_match: int = 1,
    ) -> List[Dict]:
        """Keyword search against Qdrant chunk payloads."""
        terms = self._tokenize(query)
        if not terms:
            return []

        all_chunks = self._scroll_campaign_chunks(campaign_id)
        if not all_chunks:
            return []

        scored = []
        for chunk in all_chunks:
            payload = chunk.get("payload", {}) or {}
            text = payload.get("text", "")
            title = payload.get("title", "")
            location = payload.get("location", "")

            title_hits = sum(1 for t in terms if t in title)
            text_hits = sum(1 for t in terms if t in text)
            location_hits = sum(1 for t in terms if t in location)
            total_hits = title_hits * 3 + text_hits + location_hits * 2

            if total_hits >= min_term_match:
                max_possible = len(terms) * 3
                normalized_score = min(total_hits / max(max_possible, 1), 1.0)
                scored.append({
                    "id": chunk.get("id"),
                    "score": round(normalized_score, 4),
                    "payload": payload,
                    "_hits": total_hits,
                    "_terms_matched": [t for t in terms if t in (text + title + location)],
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        """Simple Chinese tokenizer: split + 2-gram. Phase 2: jieba."""
        segments = self._SEP_PATTERN.split(text)
        terms = []
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            if len(seg) >= self._MIN_TERM_LEN:
                terms.append(seg)
            if len(seg) >= 4:
                for i in range(len(seg) - 1):
                    bigram = seg[i:i + 2]
                    if bigram not in terms:
                        terms.append(bigram)
        seen = set()
        unique_terms = []
        for t in terms:
            if t not in seen:
                seen.add(t)
                unique_terms.append(t)
        return unique_terms

    def _scroll_campaign_chunks(self, campaign_id: str) -> List[Dict]:
        """Scroll all chunks for a campaign from Qdrant."""
        from app.storage.qdrant import qdrant_store, COLLECTION_MODULE_CHUNKS
        from qdrant_client.http import models as qdrant_models

        qdrant_store._ensure_collection()
        all_points = []
        offset = None
        while True:
            points, offset = qdrant_store.client.scroll(
                collection_name=COLLECTION_MODULE_CHUNKS,
                scroll_filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="campaign_id",
                            match=qdrant_models.MatchValue(value=campaign_id),
                        )
                    ]
                ),
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend([
                {"id": p.id, "payload": p.payload}
                for p in points
            ])
            if offset is None:
                break
        return all_points


keyword_searcher = KeywordSearcher()
