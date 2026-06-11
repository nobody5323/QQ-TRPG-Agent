"""ChronicleAgent document chunker."""

import uuid
import re
from typing import List
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_id: str
    text: str
    type: str = "text"
    title: str = ""
    location: str = ""
    visibility: str = "player_visible"
    related_nodes: List[str] = field(default_factory=list)
    section_ref: str = ""


class Chunker:
    """Document chunker. Generates UUID chunk IDs for Qdrant 1.18+ compatibility."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.hidden_markers = [
            "隐藏", "秘密", "暗格", "未触发", "隐藏线索",
            "kp_only", "secret", "hidden",
            "守秘人信息", "守秘人",
        ]

    def chunk(self, sections: List, title: str) -> List[Chunk]:
        chunks = []
        for section in sections:
            chunks.extend(self._chunk_section(section, title))
        return chunks

    def _chunk_section(self, section, doc_title: str) -> List[Chunk]:
        content = section.content.strip()
        if not content:
            return []

        visibility = self._detect_visibility(section.title, content)
        related = self._extract_related_entities(content)
        section_type = section.section_type if hasattr(section, 'section_type') else "text"

        if len(content) <= self.chunk_size:
            return [Chunk(
                chunk_id=self._make_chunk_id(),
                text=content,
                type=section_type,
                title=section.title,
                location=self._detect_location(section.title, content),
                visibility=visibility,
                related_nodes=related,
                section_ref=section.title,
            )]

        return self._split_long_section(content, section_type, section, visibility, related)

    def _split_long_section(self, content, section_type, section, visibility, related):
        paragraphs = re.split(r"\n\s*\n", content)
        chunks = []
        current_chunks = []
        current_size = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if current_size + len(para) > self.chunk_size and current_chunks:
                combined = "\n\n".join(current_chunks)
                chunks.append(Chunk(
                    chunk_id=self._make_chunk_id(),
                    text=combined, type=section_type,
                    title=section.title,
                    location=self._detect_location(section.title, combined),
                    visibility=visibility, related_nodes=related,
                    section_ref=section.title,
                ))
                current_chunks = []
                current_size = 0
            current_chunks.append(para)
            current_size += len(para)

        if current_chunks:
            combined = "\n\n".join(current_chunks)
            chunks.append(Chunk(
                chunk_id=self._make_chunk_id(),
                text=combined, type=section_type,
                title=section.title,
                location=self._detect_location(section.title, combined),
                visibility=visibility, related_nodes=related,
                section_ref=section.title,
            ))
        return chunks

    def _detect_visibility(self, title: str, content: str) -> str:
        for marker in self.hidden_markers:
            if marker in (title + "\n" + content):
                return "kp_only"
        return "player_visible"

    def _detect_location(self, title: str, content: str) -> str:
        patterns = [
            (r"(?:在|位于|来到)(.{2,10}(?:宅|公墓|墓地|地穴|书房|图书馆|街道|酒吧|教堂|医院))", 1),
            (r"(.{2,10}(?:宅|公墓|墓地|地穴|书房|图书馆|街道|酒吧))", 1),
        ]
        for pat, g in patterns:
            m = re.search(pat, content[:200])
            if m:
                return m.group(g).strip()
        return ""

    def _extract_related_entities(self, content: str) -> List[str]:
        related = []
        npc_pats = [
            r"(道格拉斯·金博尔|金博尔|道格拉斯)",
            r"(托马斯·金博尔|托马斯)",
            r"(梅洛迪亚斯·杰弗逊|杰弗逊)",
            r"(莱拉·奥戴尔|奥戴尔)",
            r"(希尔达·沃德|沃德)",
        ]
        for pat in npc_pats:
            m = re.search(pat, content)
            if m and m.group(1) not in related:
                related.append(m.group(1))
        for kw in ["线索", "关键", "发现", "日记", "报道", "脚印", "石板"]:
            if kw in content and kw not in related:
                related.append(kw)
        return related

    def _make_chunk_id(self) -> str:
        """UUID v4 — Qdrant 1.18+ requires UUID or integer point IDs."""
        return str(uuid.uuid4())
