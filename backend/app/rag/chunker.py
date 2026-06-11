"""
ChronicleAgent 文档切分器

将解析后的文档按语义切分为 chunks，每个 chunk 携带元数据：
- type: text | scene | npc | clue | location | statblock
- title: 来源章节标题
- location: 关联地点
- visibility: player_visible | kp_only
- related_nodes: 关联的 NPC/线索/地点

切分策略（design.md 第 13.1 节）：
1. 按标题层级切分章节
2. 按 NPC/地点/线索/剧情节点语义切分
3. 每个 chunk 保留来源章节
4. 隐藏线索标记为 kp_only
5. 关键节点建立关系索引
"""

import hashlib
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """文档块"""
    chunk_id: str
    text: str
    type: str               # text | scene | npc | clue | location | statblock
    title: str
    location: str = ""
    visibility: str = "player_visible"  # player_visible | kp_only
    related_nodes: List[str] = field(default_factory=list)
    section_ref: str = ""   # 来源章节引用


class Chunker:
    """文档切分器"""

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

        # 隐藏线索关键词（标记为 kp_only）
        self.hidden_markers = [
            "隐藏", "秘密", "暗格", "未触发", "隐藏线索",
            "kp_only", "secret", "hidden",
            "守秘人信息", "守秘人",
        ]

    def chunk(self, sections: List, title: str) -> List[Chunk]:
        """将解析后的章节列表切分为 Chunk 列表

        Args:
            sections: Section 列表（来自 ParseResult.sections）
            title: 文档标题

        Returns:
            Chunk 列表
        """
        chunks: List[Chunk] = []

        for section in sections:
            chunked = self._chunk_section(section, title)
            chunks.extend(chunked)

        return chunks

    def _chunk_section(self, section, doc_title: str) -> List[Chunk]:
        """将单个章节切分为 chunks"""
        content = section.content.strip()
        if not content:
            return []

        # 判断可见性
        visibility = self._detect_visibility(section.title, content)

        # 识别关联实体
        related = self._extract_related_entities(content)

        # 如果内容较短，直接作为一个 chunk
        if len(content) <= self.chunk_size:
            chunk_id = self._make_chunk_id(doc_title, section.title)
            return [Chunk(
                chunk_id=chunk_id,
                text=content,
                type=section.section_type if hasattr(section, 'section_type') else "text",
                title=section.title,
                location=self._detect_location(section.title, content),
                visibility=visibility,
                related_nodes=related,
                section_ref=section.title,
            )]

        # 长内容需要切分
        return self._split_long_section(section, content, doc_title, visibility, related)

    def _split_long_section(
        self, section, content: str, doc_title: str,
        visibility: str, related: List[str],
    ) -> List[Chunk]:
        """将长章节按段落或固定大小切分"""
        paragraphs = re.split(r"\n\s*\n", content)
        chunks = []
        current_chunks = []
        current_size = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_size + len(para) > self.chunk_size and current_chunks:
                # 合并当前积累的段落
                combined = "\n\n".join(current_chunks)
                chunk_id = self._make_chunk_id(doc_title, section.title, len(chunks))
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    text=combined,
                    type=section.section_type,
                    title=section.title,
                    location=self._detect_location(section.title, combined),
                    visibility=visibility,
                    related_nodes=related,
                    section_ref=section.title,
                ))
                current_chunks = []
                current_size = 0

            current_chunks.append(para)
            current_size += len(para)

        # 最后一段
        if current_chunks:
            combined = "\n\n".join(current_chunks)
            chunk_id = self._make_chunk_id(doc_title, section.title, len(chunks))
            chunks.append(Chunk(
                chunk_id=chunk_id,
                text=combined,
                type=section.section_type,
                title=section.title,
                location=self._detect_location(section.title, combined),
                visibility=visibility,
                related_nodes=related,
                section_ref=section.title,
            ))

        return chunks

    def _detect_visibility(self, title: str, content: str) -> str:
        """检测内容是否应标记为 KP only"""
        combined = title + "\n" + content
        for marker in self.hidden_markers:
            if marker in combined:
                return "kp_only"
        return "player_visible"

    def _detect_location(self, title: str, content: str) -> str:
        """从内容中提取地点信息"""
        # 常见地点模式
        location_patterns = [
            (r"(?:在|位于|来到)(.{2,10}(?:宅|公墓|墓地|地穴|书房|图书馆|街道|酒吧|教堂|医院))", 1),
            (r"(.{2,10}(?:宅|公墓|墓地|地穴|书房|图书馆|街道|酒吧))", 1),
        ]

        for pattern, group in location_patterns:
            match = re.search(pattern, content[:200])  # 只搜索开头 200 字
            if match:
                return match.group(group).strip()

        return ""

    def _extract_related_entities(self, content: str) -> List[str]:
        """从内容中提取关联的 NPC/线索/地名"""
        related = []

        # 常见 NPC 名模式
        npc_patterns = [
            r"(道格拉斯·金博尔|金博尔|道格拉斯)",
            r"(托马斯·金博尔|托马斯)",
            r"(梅洛迪亚斯·杰弗逊|杰弗逊)",
            r"(莱拉·奥戴尔|奥戴尔)",
            r"(希尔达·沃德|沃德)",
        ]
        for pattern in npc_patterns:
            if re.search(pattern, content):
                npc_name = re.search(pattern, content).group(1)
                if npc_name not in related:
                    related.append(npc_name)

        # 线索关键词
        clue_keywords = ["线索", "关键", "发现", "日记", "报道", "脚印", "石板"]
        for kw in clue_keywords:
            if kw in content:
                if kw not in related:
                    related.append(kw)

        return related

    def _make_chunk_id(self, doc_title: str, section_title: str, index: int = 0) -> str:
        """生成唯一 chunk ID"""
        raw = f"{doc_title}/{section_title}/{index}"
        return f"chunk_{hashlib.md5(raw.encode()).hexdigest()[:12]}"
