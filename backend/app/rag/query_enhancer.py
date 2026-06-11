"""Query enhancer - injects TRPG state context into queries before embedding."""

from typing import List, Optional, Dict
from dataclasses import dataclass


@dataclass
class QueryContext:
    query: str = ""
    active_scene: Optional[str] = None
    active_npcs: List[str] = None
    undiscovered_clues: List[str] = None
    recent_events: List[str] = None

    def __post_init__(self):
        if self.active_npcs is None:
            self.active_npcs = []
        if self.undiscovered_clues is None:
            self.undiscovered_clues = []
        if self.recent_events is None:
            self.recent_events = []


class QueryEnhancer:
    """Enriches queries with current TRPG state context.

    Three strategies:
    - expansion: repeat state keywords to boost vector weight
    - prefix: prepend natural-language state summary
    - hybrid: expansion for embedding, prefix saved for reranker

    Boost weights (higher = more emphasis in vector search):
    - Scene keywords: 3x repeat
    - NPC keywords: 2x repeat
    - Undiscovered clues: 4x repeat (KP's biggest pain point)
    """

    SCENE_BOOST_TERMS = 3
    NPC_BOOST_TERMS = 2
    CLUE_BOOST_TERMS = 4

    def enhance(self, query: str, context: QueryContext, strategy: str = "expansion") -> str:
        if strategy == "prefix":
            return self._prefix_enhance(query, context)
        elif strategy == "hybrid":
            return self._hybrid_enhance(query, context)
        else:
            return self._expansion_enhance(query, context)

    def _expansion_enhance(self, query: str, ctx: QueryContext) -> str:
        parts = [query]
        if ctx.active_scene:
            parts.append((ctx.active_scene + " ") * self.SCENE_BOOST_TERMS)
        for npc in ctx.active_npcs[:3]:
            parts.append((npc + " ") * self.NPC_BOOST_TERMS)
        for clue in ctx.undiscovered_clues[:5]:
            parts.append((clue + " ") * self.CLUE_BOOST_TERMS)
        return " ".join(parts)

    def _prefix_enhance(self, query: str, ctx: QueryContext) -> str:
        prefix_parts = []
        if ctx.active_scene:
            prefix_parts.append(f"Current scene: {ctx.active_scene}. ")
        if ctx.active_npcs:
            npc_list = ", ".join(ctx.active_npcs[:5])
            prefix_parts.append(f"Present NPCs: {npc_list}. ")
        if ctx.undiscovered_clues:
            clue_list = ", ".join(ctx.undiscovered_clues[:5])
            prefix_parts.append(f"Undiscovered clues: {clue_list}. ")
        if ctx.recent_events:
            events = "; ".join(ctx.recent_events[:3])
            prefix_parts.append(f"Recent events: {events}. ")
        if prefix_parts:
            return "".join(prefix_parts) + " Query: " + query
        return query

    def _hybrid_enhance(self, query: str, ctx: QueryContext) -> str:
        return self._expansion_enhance(query, ctx)

    def build_context(
        self,
        active_scene_name: Optional[str] = None,
        active_scene_summary: Optional[str] = None,
        npc_names: Optional[List[str]] = None,
        undiscovered_clue_names: Optional[List[str]] = None,
        recent_event_texts: Optional[List[str]] = None,
    ) -> QueryContext:
        scene_desc = None
        if active_scene_name:
            if active_scene_summary:
                scene_desc = active_scene_name + " (" + active_scene_summary[:80] + ")"
            else:
                scene_desc = active_scene_name
        return QueryContext(
            query="",
            active_scene=scene_desc,
            active_npcs=npc_names or [],
            undiscovered_clues=undiscovered_clue_names or [],
            recent_events=recent_event_texts or [],
        )


query_enhancer = QueryEnhancer()
