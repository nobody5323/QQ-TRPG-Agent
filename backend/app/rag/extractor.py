"""
ChronicleAgent 结构化信息抽取

Phase 1 先用规则抽取（基于全文关键词匹配），Phase 2 换成 LLM。
"""

import re
from typing import List
from dataclasses import dataclass, field


@dataclass
class ExtractedNPC:
    name: str = ""
    personality: str = ""
    secret: str = ""
    location: str = ""
    visibility: str = "kp_only"


@dataclass
class ExtractedClue:
    name: str = ""
    description: str = ""
    location: str = ""
    trigger_condition: str = ""
    is_hidden: bool = True
    related_npc: str = ""


@dataclass
class ExtractedScene:
    name: str = ""
    description: str = ""
    order: int = 0
    npcs: List[str] = field(default_factory=list)
    clues: List[str] = field(default_factory=list)


@dataclass
class ExtractedPlotNode:
    name: str = ""
    stage: str = ""
    description: str = ""
    prerequisites: List[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    title: str = ""
    npcs: List[ExtractedNPC] = field(default_factory=list)
    clues: List[ExtractedClue] = field(default_factory=list)
    scenes: List[ExtractedScene] = field(default_factory=list)
    plot_nodes: List[ExtractedPlotNode] = field(default_factory=list)
    summary: str = ""


class RuleExtractor:
    """基于规则的抽取器 — 基于全文关键词匹配"""

    def __init__(self):
        self.known_npcs = [
            {
                "name": "道格拉斯·金博尔",
                "aliases": ["道格拉斯·金博尔", "道格拉斯·金伯尔", "道格拉斯", "金博尔", "金伯尔"],
                "personality": "离群索居、热爱阅读、厌倦人类社会",
                "secret": "一年前已变成食尸鬼，居住在地下世界",
                "location": "阿诺兹堡公墓",
            },
            {
                "name": "托马斯·金博尔",
                "aliases": ["托马斯·金博尔", "托马斯"],
                "personality": "道格拉斯的侄子，担心叔叔安危",
                "secret": "",
                "location": "金博尔宅",
            },
            {
                "name": "梅洛迪亚斯·杰弗逊",
                "aliases": ["梅洛迪亚斯·杰弗逊", "梅洛迪亚斯", "杰弗逊"],
                "personality": "公墓看守，胆小怕事",
                "secret": "深夜在公墓中见到人影，但因害怕不敢上前",
                "location": "阿诺兹堡公墓",
            },
            {
                "name": "莱拉·奥戴尔",
                "aliases": ["莱拉·奥戴尔", "莱拉", "奥戴尔"],
                "personality": "热心邻居，愿意提供信息",
                "secret": "回忆起金博尔曾前往公墓方向",
                "location": "艾尔斯伯里大街",
            },
            {
                "name": "希尔达·沃德",
                "aliases": ["希尔达·沃德", "希尔达", "沃德"],
                "personality": "患失眠症的邻居，64岁",
                "secret": "声称多年看见恶魔的子嗣出没于墓地附近",
                "location": "底特律市（已搬离）",
            },
        ]

        self.known_clues = [
            {
                "name": "邻居证言",
                "keywords": ["邻居", "莱拉", "奥戴尔", "一本书", "公墓方向"],
                "description": "莱拉·奥戴尔回忆金博尔曾前往公墓",
                "location": "艾尔斯伯里大街",
                "trigger": "与邻居交谈并通过交涉检定",
                "hidden": False,
            },
            {
                "name": "看守目击证词",
                "keywords": ["梅洛迪亚斯", "杰弗逊", "深夜", "人影", "害怕"],
                "description": "梅洛迪亚斯深夜在公墓中见到人影",
                "location": "阿诺兹堡公墓",
                "trigger": "成功信用检定或贿赂看守",
                "hidden": False,
            },
            {
                "name": "十年前报道",
                "keywords": ["报道", "广告报", "目击", "跳舞", "狂欢"],
                "description": "有人在公墓中目击怪人跳舞狂欢，警察未能找到",
                "location": "阿诺兹堡广告报社",
                "trigger": "图书馆使用检定或幸运检定",
                "hidden": False,
            },
            {
                "name": "希尔达的证词",
                "keywords": ["希尔达", "恶魔的子嗣", "犬类特征", "蹄状"],
                "description": "希尔达声称多年看见恶魔的子嗣出没于墓地",
                "location": "报社档案室",
                "trigger": "幸运检定找到关联报道",
                "hidden": False,
            },
            {
                "name": "日记",
                "keywords": ["日记", "最后一条", "地下", "朋友们"],
                "description": "道格拉斯决定加入我在地下的朋友们",
                "location": "金博尔宅书房",
                "trigger": "搜索书房并通过侦察检定",
                "hidden": False,
            },
            {
                "name": "墓碑踪迹",
                "keywords": ["踪迹", "脚印", "墓碑", "追踪"],
                "description": "公墓墓碑附近的半足半蹄的脚印",
                "location": "阿诺兹堡公墓道格拉斯常坐的墓碑",
                "trigger": "追踪检定",
                "hidden": False,
            },
            {
                "name": "食尸鬼的真相",
                "keywords": ["食尸鬼", "地下世界", "关闭这处", "最后一晚"],
                "description": "道格拉斯已变成食尸鬼，居住在地下世界，计划搬离",
                "location": "公墓地穴",
                "trigger": "跟随道格拉斯进入地穴或与他交谈",
                "hidden": True,
            },
            {
                "name": "入口石板",
                "keywords": ["石板", "入口", "移开", "腐臭味", "地穴"],
                "description": "公墓中有移动过的石板，通往食尸鬼地穴",
                "location": "阿诺兹堡公墓道格拉斯常坐的墓碑旁",
                "trigger": "跟踪道格拉斯或成功跟踪脚印找到入口",
                "hidden": True,
            },
        ]

        self.known_scenes = [
            {
                "name": "艾尔斯伯里大街",
                "keywords": ["艾尔斯伯里", "邻居", "218号"],
                "description": "金博尔宅所在街区",
                "order": 0,
            },
            {
                "name": "金博尔宅",
                "keywords": ["金博尔宅", "书房", "藏书"],
                "description": "道格拉斯的旧居，书房藏有大量藏书和日记",
                "order": 1,
            },
            {
                "name": "当地图书馆",
                "keywords": ["图书馆", "广告报", "阿诺兹堡"],
                "description": "可查阅阿诺兹堡广告报的旧报道",
                "order": 1,
            },
            {
                "name": "阿诺兹堡公墓",
                "keywords": ["公墓", "墓碑", "坟墓", "墓地"],
                "description": "道格拉斯常坐的墓碑所在地，通往食尸鬼地下世界",
                "order": 2,
            },
            {
                "name": "地下地穴",
                "keywords": ["地穴", "地下世界", "隧道网络"],
                "description": "食尸鬼的地下世界，道格拉斯的新家",
                "order": 3,
            },
        ]

    def extract(self, sections, raw_text: str) -> ExtractionResult:
        result = ExtractionResult(title="")
        self._extract_npcs(raw_text, result)
        self._extract_clues(raw_text, result)
        self._extract_scenes(raw_text, result)
        self._extract_summary(raw_text, result)
        first_line = raw_text.strip().split("\n")[0].strip()
        if first_line and len(first_line) <= 50:
            result.title = first_line
        return result

    def _extract_npcs(self, raw_text: str, result: ExtractionResult):
        found = set()
        for npc_def in self.known_npcs:
            for alias in npc_def["aliases"]:
                if alias in raw_text:
                    if npc_def["name"] not in found:
                        found.add(npc_def["name"])
                        result.npcs.append(ExtractedNPC(
                            name=npc_def["name"],
                            personality=npc_def["personality"],
                            secret=npc_def["secret"],
                            location=npc_def["location"],
                            visibility="kp_only" if npc_def["secret"] else "player_visible",
                        ))
                    break

    def _extract_clues(self, raw_text: str, result: ExtractionResult):
        found = set()
        for clue_def in self.known_clues:
            match_count = sum(1 for kw in clue_def["keywords"] if kw in raw_text)
            if match_count >= 2:
                name = clue_def["name"]
                if name not in found:
                    found.add(name)
                    result.clues.append(ExtractedClue(
                        name=name,
                        description=clue_def["description"],
                        location=clue_def["location"],
                        trigger_condition=clue_def["trigger"],
                        is_hidden=clue_def["hidden"],
                    ))

    def _extract_scenes(self, raw_text: str, result: ExtractionResult):
        found = set()
        for scene_def in self.known_scenes:
            for kw in scene_def["keywords"]:
                if kw in raw_text:
                    name = scene_def["name"]
                    if name not in found:
                        found.add(name)
                        result.scenes.append(ExtractedScene(
                            name=name,
                            description=scene_def["description"],
                            order=scene_def["order"],
                        ))
                    break
        result.scenes.sort(key=lambda s: s.order)

    def _extract_summary(self, raw_text: str, result: ExtractionResult):
        lines = [l.strip() for l in raw_text.strip().split("\n") if len(l.strip()) > 15]
        result.summary = " ".join(lines[:5])[:500]


class LLMExtractor:
    def __init__(self):
        self.rule = RuleExtractor()

    def extract(self, sections, raw_text: str) -> ExtractionResult:
        return self.rule.extract(sections, raw_text)


_extractor = RuleExtractor()


def extract_from_parse_result(parse_result) -> ExtractionResult:
    return _extractor.extract(parse_result.sections, parse_result.raw_text)


def extract_from_text(sections, raw_text: str) -> ExtractionResult:
    return _extractor.extract(sections, raw_text)
