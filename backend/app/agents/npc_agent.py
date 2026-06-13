"""NPC Roleplay Agent — generates NPC dialogue with public/KP split.

Inputs:
  - NPC name + personality profile
  - Player's question/message
  - Current game state (scene, discovered clues)
  - Dice result (may affect NPC attitude)
  - Recent dialogue history

Outputs:
  - public_line: Player-visible in-character dialogue
  - kp_note: Hidden notes for KP about NPC's true intentions
  - risk: Risk level (low/medium/high)
  - relationship_change: Any attitude shift triggered by this exchange

Constraints:
  - Never reveal hidden secrets in public_line
  - Maintain NPC personality consistency
  - Respect NPC's current knowledge state (don't reveal things NPC doesn't know)
  - Dice failure may make NPC less cooperative
"""

import json
from typing import Dict, Any, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.harness.agent_state import AgentState
from app.agents.llm_factory import llm_factory, ModelConfig


NPC_SYSTEM_PROMPT = """You are an NPC dialogue generator for a Call of Cthulhu (CoC) TRPG Keeper assistant. You play the role of an NPC and generate authentic in-character responses.

OUTPUT FORMAT — respond with ONLY this JSON:
{
  "public_line": "The NPC's spoken dialogue, in Chinese or English, matching the NPC's personality. Keep under 150 chars.",
  "kp_note": "For the Keeper's eyes only — what the NPC is REALLY thinking, any hidden meaning, or secret agenda.",
  "risk": "low" | "medium" | "high",
  "relationship_change": null or {"npc": "NPC_name", "change": "neutral→friendly", "reason": "..."},
  "reasoning": "Brief explanation of dialogue choices"
}

IMPORTANT RULES:
1. NEVER reveal hidden secrets, clues, or plot twists in public_line. These go in kp_note only.
2. Match the NPC's established personality. A gruff old keeper won't suddenly become chatty.
3. If the NPC doesn't know something, have them say so — don't invent knowledge.
4. If dice_result is failure/fumble, the NPC should be less helpful, evasive, or suspicious.
5. If the player is being hostile or suspicious, the NPC should react accordingly.
6. public_line should be natural spoken dialogue, not narration.
7. kp_note is the Keeper's backstage view — use it for secrets, hidden agendas, and reminders.
8. Risk assessment: low=casual chat, medium=player probing for secrets, high=player directly asking about a hidden clue."""


NPC_USER_TEMPLATE = """NPC: {npc_name}
Personality: {personality}
Secret (KP only): {secret}
Current relationship with party: {relationship}

Player: {player_name}
Player says: {content}

Current scene: {scene_name}
Discovered clues: {discovered_clues}

Dice result: {dice_result}
Recent dialogue:
{recent_dialogue}

Generate the NPC's response as JSON."""


class NPCAgent:
    """Generates NPC dialogue with dual visibility (public + KP notes)."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("npc")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("npc")
        return cfg.model

    async def generate(
        self,
        npc_name: str,
        personality: str,
        secret: str,
        content: str,
        player_name: str = "调查员",
        scene_name: str = "unknown",
        discovered_clues: str = "",
        dice_result: Optional[Dict[str, Any]] = None,
        recent_dialogue: str = "",
        relationship: str = "中立",
    ) -> Dict[str, Any]:
        """Generate NPC dialogue response.

        Returns:
            dict with public_line, kp_note, risk, relationship_change, reasoning
        """
        dice_str = json.dumps(dice_result, ensure_ascii=False) if dice_result else "无骰子结果"

        user_prompt = NPC_USER_TEMPLATE.format(
            npc_name=npc_name,
            personality=personality[:300],
            secret=secret[:300],
            relationship=relationship,
            player_name=player_name,
            content=content[:300],
            scene_name=scene_name,
            discovered_clues=discovered_clues[:300],
            dice_result=dice_str,
            recent_dialogue=recent_dialogue[:500],
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": NPC_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            result = self._fallback(npc_name, content)

        return self._validate(result, npc_name)

    def _validate(self, result: Dict[str, Any], npc_name: str) -> Dict[str, Any]:
        result.setdefault("public_line", "……")
        result.setdefault("kp_note", "")
        result.setdefault("risk", "low")
        result.setdefault("relationship_change", None)
        result.setdefault("reasoning", "")

        # Cap public_line length
        if len(result["public_line"]) > 200:
            result["public_line"] = result["public_line"][:197] + "..."

        # Validate risk
        if result["risk"] not in ("low", "medium", "high"):
            result["risk"] = "low"

        return result

    def _fallback(self, npc_name: str, content: str) -> Dict[str, Any]:
        return {
            "public_line": "……（{}若有所思地看着你）".format(npc_name),
            "kp_note": "NPC agent unavailable, returned fallback response.",
            "risk": "low",
            "relationship_change": None,
            "reasoning": "fallback",
        }


npc_agent = NPCAgent()


# ── LangGraph node ─────────────────────────────────────────────

async def node_npc_roleplay(state: AgentState) -> AgentState:
    """LangGraph node: generate NPC dialogue response."""
    content = state.get("content", "")
    sender = state.get("sender", "")
    ctx = state.get("current_state", {}) or state.get("context", {})
    dice = state.get("dice_result")

    # Find the NPC being addressed
    active_npcs = ctx.get("active_npcs", [])
    if not active_npcs:
        state["suggested_action"] = "[NPC Agent — no active NPCs in scene]"
        return state

    # Try to identify which NPC is being addressed from the message
    target_npc = active_npcs[0]  # Default to first active NPC
    for npc in active_npcs:
        name = npc.get("name", "")
        if name and name in content:
            target_npc = npc
            break

    npc_name = target_npc.get("name", "NPC")
    personality = target_npc.get("personality", "")
    secret = target_npc.get("secret", "")

    # Build dialogue history
    recent = ctx.get("recent_messages", [])
    dialogue_history = "\n".join(
        "{}: {}".format(m.get("sender", ""), m.get("content", ""))
        for m in recent[-5:]
    )

    discovered = ", ".join(
        c.get("name", c) if isinstance(c, dict) else str(c)
        for c in ctx.get("discovered_clues", [])[:5]
    )

    scene_name = ctx.get("active_scene", {}).get("name", "unknown") if isinstance(ctx.get("active_scene"), dict) else "unknown"

    result = await npc_agent.generate(
        npc_name=npc_name,
        personality=personality,
        secret=secret,
        content=content,
        player_name=sender,
        scene_name=scene_name,
        discovered_clues=discovered,
        dice_result=dice,
        recent_dialogue=dialogue_history,
    )

    # Store results
    suggestion_parts = [
        "[NPC Dialogue: {}]".format(npc_name),
        "Player: {}".format(content[:100]),
        "",
        "Public: {}".format(result["public_line"]),
        "",
        "KP Note: {}".format(result["kp_note"]),
        "Risk: {}".format(result["risk"]),
    ]
    if result.get("relationship_change"):
        rc = result["relationship_change"]
        suggestion_parts.append(
            "Relationship: {} → {}".format(
                rc.get("npc", npc_name), rc.get("change", "")
            )
        )

    state["suggested_action"] = "\n".join(suggestion_parts)
    state["kp_suggestion"] = state["suggested_action"]
    state["public_reply"] = result["public_line"]
    state["need_kp_notify"] = result["risk"] in ("medium", "high")

    return state
