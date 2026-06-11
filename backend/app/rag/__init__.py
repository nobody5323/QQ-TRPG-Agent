"""ChronicleAgent RAG Module - state-aware retrieval for TRPG.

Architecture (differs from generic RAG):
1. State-Gated: queries enhanced with scene/NPC/clue state before embedding
2. Undiscovered Boost: unfound clues get higher retrieval priority
3. Dual-Visibility: each chunk tagged player_visible or kp_only
4. Hybrid + RRF: semantic vector search + keyword search via RRF fusion
5. Scene-Scoped: active scene context auto-injected into queries

Modules:
- document_parser.py  - PDF/MD/TXT parsing engine
- chunker.py          - semantic chunking (512 chars, 64 overlap)
- extractor.py        - structured extraction (NPCs, clues, scenes)
- embedding.py        - OpenAI Embedding API wrapper
- retriever.py        - hybrid search engine (vector + keyword + RRF + rerank)
- query_enhancer.py   - state-aware query enrichment
- keyword_search.py   - keyword matching on Qdrant payloads
"""

from app.rag.document_parser import ParserFactory, ParseResult, Section
from app.rag.chunker import Chunker, Chunk
from app.rag.extractor import extract_from_parse_result, extract_from_text, ExtractionResult
from app.rag.query_enhancer import query_enhancer, QueryEnhancer, QueryContext


def get_embedding_service():
    from app.rag.embedding import embedding_service
    return embedding_service


def get_retriever():
    from app.rag.retriever import retriever
    return retriever


def get_keyword_searcher():
    from app.rag.keyword_search import keyword_searcher
    return keyword_searcher


embedding_service = None
retriever = None
keyword_searcher = None


__all__ = [
    "ParserFactory", "ParseResult", "Section",
    "Chunker", "Chunk",
    "extract_from_parse_result", "extract_from_text", "ExtractionResult",
    "query_enhancer", "QueryEnhancer", "QueryContext",
    "get_embedding_service", "get_retriever", "get_keyword_searcher",
]
