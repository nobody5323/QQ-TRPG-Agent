"""Chat Bot Agent — persona-based casual chat in group or private.

Phase 2 Step 11.5: The chat bot is a configurable persona that responds when
@mentioned in group chat (or any message in private chat). It must never
reveal module secrets (critic check enforced).

Bot persona config is stored in Campaign.bot_persona JSONB:
  {
    "name": "小管家",
    "personality": "温和有礼，略带幽默",
    "role_description": "团内小助手",
    "speaking_style": "简短，爱用省略号...",
    "constraints": ["不透露模组线索", "不替KP做决定"]
  }

Design rules:
  - @mention only in group (no autoplay)
  - 30-second cooldown between replies in same group
  - Critic check before output (reuse Step 13)
  - Max 200 chars per reply
  - Never reveals kp_only content
"""

import json
import time
from typing import Dict, Any, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.harness.agent_state import AgentState
from app.agents.llm_factory import llm_factory, ModelConfig


CHAT_BOT_SYSTEM_PROMPT = """You are a chat bot character in a Call of Cthulhu TRPG group chat. You have a defined personality and must stay in character.

YOUR PERSONA:
Name: {name}
Personality: {personality}
Role: {role_description}
Speaking style: {speaking_style}

RULES:
1. Stay in character at all times.
2. Keep replies under 150 characters.
3. NEVER reveal module secrets, hidden clues, or plot twists.
4. NEVER make game decisions for the Keeper.
5. NEVER reveal information your character wouldn't know.
6. If asked about game secrets, deflect with in-character ignorance.
7. Match the speaking style defined above.
8. If the message is just casual chat, respond naturally in character.
9. If addressed by your name, acknowledge it.

CURRENT CONTEXT:
Scene: {scene_name}
(This is the ONLY in-game context you have. Do not reference anything beyond this.)

RECENT CHAT:
{recent_context}

Reply as {name} in JSON:
{{"reply": "your in-character response", "risk": "low" | "medium", "reasoning": "brief"}}"""


# Simple in-memory cooldown tracker: {group_id: last_reply_timestamp}
_cooldowns: Dict[str, float] = {}
COOLDOWN_SECONDS = 30


class ChatAgent:
    """Persona-based casual chat responder."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("chat")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("chat")
        return cfg.model

    def check_cooldown(self, group_id: str) -> bool:
        """Check if bot can reply in this group. Returns True if OK to reply."""
        now = time.time()
        last = _cooldowns.get(group_id, 0)
        if now - last < COOLDOWN_SECONDS:
            return False
        _cooldowns[group_id] = now
        return True

    async def chat(
        self,
        message: str,
        persona: Dict[str, Any],
        scene_name: str = "",
        recent_context: str = "",
        is_group: bool = True,
        group_id: str = "",
    ) -> Dict[str, Any]:
        """Generate a persona-based chat reply.

        Args:
            message: The user's message content.
            persona: Bot persona config dict.
            scene_name: Current scene name (for context).
            recent_context: Recent chat messages.
            is_group: Whether this is a group chat (enforces cooldown).
            group_id: Group ID for cooldown tracking.

        Returns:
            dict: {reply, risk, reasoning}
        """
        # Cooldown check
        if is_group and group_id:
            if not self.check_cooldown(group_id):
                return {"reply": None, "risk": "low", "reasoning": "cooldown"}

        # If no persona configured, don't reply
        if not persona or not persona.get("name"):
            return {"reply": None, "risk": "low", "reasoning": "no persona configured"}

        system = CHAT_BOT_SYSTEM_PROMPT.format(
            name=persona.get("name", "助手"),
            personality=persona.get("personality", "友好"),
            role_description=persona.get("role_description", "助手"),
            speaking_style=persona.get("speaking_style", "简洁"),
            scene_name=scene_name or "未知",
            recent_context=recent_context[:800],
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": message[:300]},
                ],
                temperature=0.8,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            return {"reply": None, "risk": "low", "reasoning": "chat agent error"}

        return self._validate(result, persona)

    def _validate(self, result: Dict[str, Any], persona: Dict[str, Any]) -> Dict[str, Any]:
        reply = result.get("reply", "")
        risk = result.get("risk", "low")

        # Truncate long replies
        if isinstance(reply, str) and len(reply) > 200:
            reply = reply[:197] + "..."

        # Check against constraints
        constraints = persona.get("constraints", [])
        if reply and constraints:
            # Simple keyword check on constraints
            for constraint in constraints:
                if constraint in reply:
                    reply = None
                    risk = "high"
                    break

        return {
            "reply": reply,
            "risk": risk,
            "reasoning": result.get("reasoning", ""),
        }


chat_agent = ChatAgent()


# ── LangGraph node ─────────────────────────────────────────────

async def node_chat_bot(state: AgentState) -> AgentState:
    """LangGraph node: persona-based casual chat response.

    This is reached when classifier determines message_type == "chat"
    and the campaign has bot_persona configured.
    """
    content = state.get("content", "")
    sender = state.get("sender", "")
    session = state.get("session")
    ctx = state.get("current_state", {}) or state.get("context", {})

    # Get bot persona from campaign
    persona = None
    if session:
        from app.storage.campaign_repo import CampaignRepository
        campaign_id = state.get("campaign_id", "")
        if campaign_id:
            try:
                repo = CampaignRepository(session)
                campaign = await repo.get(campaign_id)
                if campaign and campaign.bot_persona:
                    persona = campaign.bot_persona
            except Exception:
                pass

    if not persona:
        state["output"] = {
            "need_kp_notify": False,
            "kp_suggestion": "",
            "message_type": "chat",
            "classification": {"message_type": "chat"},
        }
        return state

    scene_name = ""
    if isinstance(ctx.get("active_scene"), dict):
        scene_name = ctx["active_scene"].get("name", "")

    recent = ""
    if ctx.get("recent_messages"):
        recent = "\n".join(
            "{}: {}".format(m.get("sender", ""), m.get("content", ""))
            for m in ctx["recent_messages"][-5:]
        )

    result = await chat_agent.chat(
        message=content,
        persona=persona,
        scene_name=scene_name,
        recent_context=recent,
    )

    reply = result.get("reply")
    risk = result.get("risk", "low")

    state["public_reply"] = reply or ""
    state["risk_level"] = risk if risk == "high" else "low"

    # Package output
    state["output"] = {
        "need_kp_notify": False,
        "message_type": "chat",
        "public_reply": reply,
        "chat_risk": risk,
    }
    state["message_type"] = "chat"
    state["need_kp_notify"] = False

    return state
