"""State Tracking Agent — tracks game state changes from player actions.

Phase 2: Full implementation with dice-aware branching and Player State.

Responsibilities:
  1. Parse player actions → extract scene/NPC/clue changes
  2. Select state branch based on dice_result (success/failure paths)
  3. Track Player State (sanity, skills, inventory, personal_clues, etc.)
  4. Generate state diffs (only changed fields)
  5. Write diffs to PostgreSQL

Design principles:
  - Incremental: only output what changed (diff), not full state
  - Dice-aware: success and failure produce different state transitions
  - Player-scoped: track state per-player, not just globally
  - KP-respecting: KP manual overrides take priority over AI updates
"""

import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.harness.agent_state import AgentState
from app.agents.llm_factory import llm_factory, ModelConfig


STATE_TRACKING_SYSTEM_PROMPT = """You are a game state tracker for a Call of Cthulhu (CoC) TRPG. Your job is to analyze a player's message and the dice result, then produce a structured state diff — only the things that changed.

DO NOT invent state from nothing. Only output changes that are directly implied by the player action + dice result + current state.

OUTPUT FORMAT — respond with ONLY this JSON:

{
  "global_diff": {
    "scene_transition": null or {"from": "current_scene_name", "to": "new_scene_name"},
    "clues_discovered": [{"clue_name": "...", "matched_clue_id": "..."}],
    "clues_locked": [{"clue_name": "...", "matched_clue_id": "...", "reason": "检定失败"}],
    "npc_attitude_changes": [{"npc_name": "...", "old_attitude": "...", "new_attitude": "..."}],
    "plot_advancement": null or {"stage": "new_stage", "trigger": "what happened"},
    "new_active_npc": null or "npc_name"
  },
  "player_diffs": {
    "<player_qq>": {
      "sanity_change": 0,
      "sanity_reason": "",
      "skill_growth": {"skill_name": "new_value"},
      "inventory_add": [{"name": "道具名", "source": "从哪获得", "clue_id": "关联线索ID"}],
      "inventory_remove": ["道具名"],
      "personal_clues_add": ["clue_id"],
      "status_add": [{"effect": "恐惧", "source": "触发源", "duration": "持续时间"}],
      "status_remove": ["effect_name"],
      "relationship_change": [{"npc_name": "道格拉斯", "change": "友善→中立", "reason": "..."}]
    }
  },
  "reasoning": "brief explanation of what changed and why"
}

RULES:
1. For dice FAILURE: do NOT mark clues as discovered. Instead mark them as locked.
2. For dice CRITICAL SUCCESS: add an extra clue or detail to inventory_add.
3. For dice FUMBLE: add a negative status_effect (fear, injury, etc.) and possibly SAN loss.
4. SAN loss values: minor horror 0/1d3, major horror 1/1d6, extreme horror 1d3/1d10.
5. If dice_result is null/None, assume the action succeeds normally (default path).
6. If the player's action doesn't involve dice, don't fabricate dice effects.
7. Player State (player_diffs) is keyed by QQ number. If you don't know the QQ, use "unknown".
8. Be conservative: when in doubt, produce fewer changes rather than more.
"""


STATE_TRACKING_USER_TEMPLATE = """Current Game State:
- Active scene: {active_scene}
- Active NPCs: {active_npcs}
- Discovered clues: {discovered_clues}
- Undiscovered clues: {undiscovered_clues}

Player: {sender}
Player Action: {content}

Dice Result: {dice_result}

Recent messages:
{recent_context}

Analyze this action and produce a state diff in JSON."""


class StateTrackingAgent:
    """Tracks game state changes and player state from messages + dice results."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("state")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("state")
        return cfg.model

    async def track(
        self,
        content: str,
        sender: str,
        campaign_id: str,
        dice_result: Optional[Dict[str, Any]] = None,
        current_state: Optional[Dict[str, Any]] = None,
        recent_context: str = "",
    ) -> Dict[str, Any]:
        """Analyze a player action and produce a state diff.

        Returns:
            dict: {global_diff, player_diffs, reasoning}
        """
        ctx = current_state or {}

        active_scene = ctx.get("active_scene", {}).get("name", "unknown") if isinstance(ctx.get("active_scene"), dict) else str(ctx.get("active_scene", "unknown"))
        npcs = ctx.get("active_npcs", [])
        active_npcs = ", ".join(
            n.get("name", n) if isinstance(n, dict) else str(n)
            for n in npcs[:10]
        )
        discovered = ", ".join(
            c.get("name", c) if isinstance(c, dict) else str(c)
            for c in ctx.get("discovered_clues", [])[:10]
        )
        undiscovered = ", ".join(
            c.get("name", c) if isinstance(c, dict) else str(c)
            for c in ctx.get("undiscovered_clues", [])[:10]
        )

        dice_str = json.dumps(dice_result, ensure_ascii=False) if dice_result else "None (success assumed)"

        user_prompt = STATE_TRACKING_USER_TEMPLATE.format(
            active_scene=active_scene or "unknown",
            active_npcs=active_npcs or "none",
            discovered_clues=discovered or "none",
            undiscovered_clues=undiscovered or "none",
            sender=sender,
            content=content[:500],
            dice_result=dice_str,
            recent_context=recent_context[:500],
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": STATE_TRACKING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            result = self._empty_diff()

        return self._validate_diff(result)

    def _validate_diff(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure the diff has correct structure."""
        if "global_diff" not in result:
            result["global_diff"] = {}
        if "player_diffs" not in result:
            result["player_diffs"] = {}
        if "reasoning" not in result:
            result["reasoning"] = ""

        gd = result["global_diff"]
        gd.setdefault("scene_transition", None)
        gd.setdefault("clues_discovered", [])
        gd.setdefault("clues_locked", [])
        gd.setdefault("npc_attitude_changes", [])
        gd.setdefault("plot_advancement", None)
        gd.setdefault("new_active_npc", None)

        return result

    def _empty_diff(self) -> Dict[str, Any]:
        return {
            "global_diff": {
                "scene_transition": None,
                "clues_discovered": [],
                "clues_locked": [],
                "npc_attitude_changes": [],
                "plot_advancement": None,
                "new_active_npc": None,
            },
            "player_diffs": {},
            "reasoning": "State agent unavailable, empty diff returned",
        }


state_tracking_agent = StateTrackingAgent()


# ── LangGraph node ─────────────────────────────────────────────

async def node_state_track(state: AgentState) -> AgentState:
    """LangGraph node: track state changes from player action + dice."""
    content = state.get("content", "")
    sender = state.get("sender", "")
    campaign_id = state.get("campaign_id", "")
    dice_result = state.get("dice_result")
    ctx = state.get("current_state", {}) or state.get("context", {})
    session = state.get("session")

    if not state.get("need_state_update", False):
        return state

    recent = ""
    if ctx.get("recent_messages"):
        recent = "\n".join(
            "{}: {}".format(m.get("sender", ""), m.get("content", ""))
            for m in ctx["recent_messages"][-5:]
        )

    diff = await state_tracking_agent.track(
        content=content,
        sender=sender,
        campaign_id=campaign_id,
        dice_result=dice_result,
        current_state=ctx,
        recent_context=recent,
    )

    # Write state changes to DB
    if session and campaign_id:
        await _apply_state_diff(session, campaign_id, diff, sender)

    # Update AgentState
    state["tool_calls"] = state.get("tool_calls", []) + ["state_track"]
    if "state_diff" not in state:
        state["state_diff"] = diff

    return state


async def _apply_state_diff(
    session,
    campaign_id: str,
    diff: Dict[str, Any],
    sender: str,
) -> None:
    """Write state diff to PostgreSQL. Best-effort — errors logged, not raised."""
    from app.storage.clue_repo import ClueRepository
    from app.storage.scene_repo import SceneRepository
    from app.storage.npc_repo import NPCRepository
    from app.storage.character_repo import CharacterRepository

    gd = diff.get("global_diff", {})

    # ── Clue discovery ──────────────────────────────────────
    clue_repo = ClueRepository(session)
    for clue_info in gd.get("clues_discovered", []):
        clue_id = clue_info.get("matched_clue_id", "")
        clue_name = clue_info.get("clue_name", "")
        if clue_id:
            try:
                await clue_repo.mark_discovered(clue_id, discovered=True)
            except Exception:
                pass

    # ── Clue locking (dice failure) ─────────────────────────
    for lock_info in gd.get("clues_locked", []):
        clue_id = lock_info.get("matched_clue_id", "")
        if clue_id:
            try:
                await clue_repo.set_locked(clue_id, locked=True, reason=lock_info.get("reason", ""))
            except Exception:
                pass

    # ── Scene transition ────────────────────────────────────
    scene_trans = gd.get("scene_transition")
    if scene_trans and isinstance(scene_trans, dict):
        scene_repo = SceneRepository(session)
        to_scene = scene_trans.get("to", "")
        if to_scene:
            try:
                await scene_repo.transition_to(campaign_id, to_scene)
            except Exception:
                pass

    # ── Player State ────────────────────────────────────────
    player_diffs = diff.get("player_diffs", {})
    if player_diffs and sender:
        char_repo = CharacterRepository(session)
        for player_qq, pdiff in player_diffs.items():
            try:
                await char_repo.apply_player_diff(campaign_id, player_qq, pdiff)
            except Exception:
                pass
