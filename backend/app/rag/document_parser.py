"""
ChronicleAgent 文档解析引擎

支持格式：
- PDF（通过 pdftotext 提取）
- Markdown（结构化解析）
- TXT（纯文本）

统一输出 ParseResult，包含原始文本和分节结构。
"""

import re
import os
import subprocess
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class Section:
    """文档章节"""
    title: str
    level: int           # 标题层级（Markdown = # 个数，PDF/TXT = 0）
    content: str
    section_type: str = "text"  # text | scene | npc | clue | location


@dataclass
class ParseResult:
    """统一解析输出"""
    title: str
    sections: List[Section]
    raw_text: str
    format: str           # pdf | markdown | txt


class BaseParser:
    """解析器基类"""

    def parse(self, file_path: str) -> ParseResult:
        raise NotImplementedError


class PDFParser(BaseParser):
    """PDF 解析器（通过 pdftotext）"""

    def parse(self, file_path: str) -> ParseResult:
        # 提取文本
        result = subprocess.run(
            ["pdftotext", file_path, "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdftotext failed: {result.stderr}")

        raw_text = result.stdout.strip()

        # 取第一段作为标题
        title = ""
        lines = raw_text.split("\n")
        if lines:
            title = lines[0].strip()

        # 按空行分段，尝试识别章节标题
        sections = self._split_sections(raw_text)

        return ParseResult(
            title=title,
            sections=sections,
            raw_text=raw_text,
            format="pdf",
        )

    def _split_sections(self, text: str) -> List[Section]:
        """将 PDF 文本按章节拆分"""
        lines = text.split("\n")
        sections = []
        current_title = "开头"
        current_lines = []
        section_idx = 0

        # 章节标题识别模式
        heading_patterns = [
            re.compile(r"^[第第第第].*[章节幕部].*[（(]?[0-9一二三四五六七八九十]+[）)]?"),
            re.compile(r"^#{1,3}\s+\S"),  # Markdown 标题
            re.compile(r"^[A-Z][A-Z\s]{4,}$"),  # 全大写短句
            re.compile(r"^[一-鿿]{2,10}$"),  # 2-10 个中文（短标题）
        ]

        # 特定章节标识
        section_markers = [
            "背景信息", "玩家信息", "守秘人信息",
            "对 话", "地 穴", "写在最后",
            "道格拉斯·金博尔", "图书馆与历史", "金博尔宅",
            "询问朋友", "墓地看守", "监视",
        ]

        def is_heading(line: str) -> bool:
            stripped = line.strip()
            if not stripped:
                return False
            # 检查是否匹配标题模式
            for pattern in heading_patterns:
                if pattern.match(stripped):
                    return True
            # 检查是否是章节标记
            for marker in section_markers:
                if marker in stripped:
                    return True
            return False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                current_lines.append("")
                continue

            if is_heading(stripped):
                # 保存前一段
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append(Section(
                            title=current_title,
                            level=1,
                            content=content,
                            section_type=self._detect_type(current_title, content),
                        ))
                    current_lines = []
                current_title = stripped
                section_idx += 1

            current_lines.append(stripped)

        # 最后一段
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(Section(
                    title=current_title,
                    level=1,
                    content=content,
                    section_type=self._detect_type(current_title, content),
                ))

        return sections

    def _detect_type(self, title: str, content: str) -> str:
        """识别章节类型"""
        title_lower = title.lower()

        if any(kw in title for kw in ["背景", "情况", "缘起"]):
            return "scene"
        if any(kw in title for kw in ["NPC", "人物", "角色", "人设"]):
            return "npc"
        if any(kw in title for kw in ["线索", "关键", "发现"]):
            return "clue"
        if any(kw in title for kw in ["地点", "场景", "场所", "地穴"]):
            return "location"
        if any(kw in title for kw in ["对 话", "交谈", "台词"]):
            return "npc"
        if any(kw in title for kw in ["战斗", "数据", "属性", "属性"]):
            return "statblock"

        return "text"


class MarkdownParser(BaseParser):
    """Markdown 解析器"""

    def parse(self, file_path: str) -> ParseResult:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        lines = raw_text.split("\n")
        sections = []
        current_title = "开头"
        current_level = 0
        current_lines = []

        # 尝试从第一个 # 标题提取文档标题
        title = ""
        for line in lines:
            if line.startswith("# ") and not title:
                title = line.lstrip("# ").strip()
                break

        for line in lines:
            # 检测 Markdown 标题
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append(Section(
                            title=current_title,
                            level=current_level,
                            content=content,
                        ))
                    current_lines = []
                current_level = len(heading_match.group(1))
                current_title = heading_match.group(2).strip()
            else:
                current_lines.append(line)

        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(Section(
                    title=current_title,
                    level=current_level,
                    content=content,
                ))

        # 如果没有找到 # 标题，用文件名
        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]

        return ParseResult(
            title=title,
            sections=sections,
            raw_text=raw_text,
            format="markdown",
        )


class TxtParser(BaseParser):
    """TXT 解析器"""

    def parse(self, file_path: str) -> ParseResult:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # 尝试识别章节
        sections = []
        lines = raw_text.split("\n")
        current_title = "开头"
        current_lines = []

        # 尝试从第一行获取标题
        title = lines[0].strip() if lines else ""

        heading_pattern = re.compile(r"^[第第第第].*[章节]|^#{1,3}\s+\S|^[A-Z][A-Z\s]{4,}$")

        for line in lines:
            stripped = line.strip()
            if heading_pattern.match(stripped):
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append(Section(
                            title=current_title,
                            level=1,
                            content=content,
                        ))
                    current_lines = []
                current_title = stripped
            else:
                current_lines.append(stripped)

        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(Section(
                    title=current_title,
                    level=1,
                    content=content,
                ))

        return ParseResult(
            title=title,
            sections=sections,
            raw_text=raw_text,
            format="txt",
        )


class ParserFactory:
    """解析器工厂"""

    @staticmethod
    def get_parser(file_path: str) -> BaseParser:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return PDFParser()
        elif ext in (".md", ".markdown"):
            return MarkdownParser()
        elif ext == ".txt":
            return TxtParser()
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
