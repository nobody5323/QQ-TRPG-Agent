"""Critic Agent — safety check on all Agent outputs before delivery.

Phase 2 Step 13: Checks every agent output for:
  1. Hidden clue leaks — does output contain visibility=kp_only info?
  2. Premature ending reveals — does output spoil the resolution?
  3. NPC knowledge violations — does NPC say things they shouldn't know?
  4. Historical contradictions — does output contradict established facts?
  5. Player agency reduction — does output make decisions for players?
  6. Known-information conflicts — does output conflict with discovered facts?

Output: CriticResult {passed, check_results[], risk_level, fix_suggestion}
"""

import json
from typing import Dict, Any, List
from openai import AsyncOpenAI

from app.config import settings
from app.harness.agent_state import AgentState
from app.agents.llm_factory import llm_factory, ModelConfig


CRITIC_SYSTEM_PROMPT = """You are a safety and quality assurance checker for a TRPG Keeper assistant. Your job is to review system-generated content before it reaches players or the Keeper.

CHECK THESE 6 CRITERIA. For each, respond with pass/fail and a brief note.

1. SPOILER_LEAK: Does the content reveal hidden clues or kp_only information to players?
2. ENDING_SPOIL: Does the content prematurely reveal the story resolution?
3. NPC_KNOWLEDGE: Does the content have an NPC saying something they shouldn't know?
4. HISTORY_CONFLICT: Does the content contradict previously established facts?
5. PLAYER_AGENCY: Does the content make decisions that should be the players' choice?
6. FACT_CONFLICT: Does the content contradict information the players have already discovered?

Respond with ONLY this JSON:
{
  "passed": true or false,
  "risk_level": "low" | "medium" | "high",
  "checks": [
    {"check": "SPOILER_LEAK", "passed": true/false, "note": ""},
    {"check": "ENDING_SPOIL", "passed": true/false, "note": ""},
    {"check": "NPC_KNOWLEDGE", "passed": true/false, "note": ""},
    {"check": "HISTORY_CONFLICT", "passed": true/false, "note": ""},
    {"check": "PLAYER_AGENCY", "passed": true/false, "note": ""},
    {"check": "FACT_CONFLICT", "passed": true/false, "note": ""}
  ],
  "fix_suggestion": "If not passed, what should be changed? Keep under 150 chars. Null if passed.",
  "reasoning": "Overall assessment, 1-2 sentences."
}

IMPORTANT:
- risk_level "high" means the content MUST be blocked — it would ruin the game.
- risk_level "medium" means the content should be shown to KP only, not players.
- risk_level "low" means it's safe to show.
- Be strict about SPOILER_LEAK — that's the #1 concern.
- For NPC_KNOWLEDGE: an NPC should only know what their character would reasonably know.
- If unsure, err on the side of caution (mark as not passed)."""


CRITIC_USER_TEMPLATE = """Content to review:
Message type: {message_type}
Target audience: {target_audience}

Content:
{content}

Known facts (what players have discovered):
{known_facts}

Hidden information (what players should NOT know yet):
{hidden_info}

NPC profiles (what each NPC knows):
{npc_profiles}

{extra_context}

Review this content and return the JSON check result."""


class CriticAgent:
    """Safety checker for all agent-generated content."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("critic")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("critic")
        return cfg.model

    async def check(
        self,
        content: str,
        message_type: str = "chat",
        target_audience: str = "player",
        known_facts: str = "",
        hidden_info: str = "",
        npc_profiles: str = "",
        extra_context: str = "",
    ) -> Dict[str, Any]:
        """Check content for safety issues.

        Args:
            content: The text to check (public_reply, kp_suggestion, etc.)
            message_type: Type of the original message.
            target_audience: "player" or "kp" — affects strictness.
            known_facts: What players have already discovered.
            hidden_info: What should remain hidden.
            npc_profiles: NPC personality/secret/knowledge summaries.
            extra_context: Additional context to consider.

        Returns:
            CriticResult dict.
        """
        # For KP-only content, relaxed check — KP should see everything
        if target_audience == "kp":
            return {
                "passed": True,
                "risk_level": "low",
                "checks": [],
                "fix_suggestion": None,
                "reasoning": "KP-only content — full access granted.",
            }

        # Empty content passes automatically
        if not content or not content.strip():
            return {
                "passed": True,
                "risk_level": "low",
                "checks": [],
                "fix_suggestion": None,
                "reasoning": "Empty content, nothing to check.",
            }

        user_prompt = CRITIC_USER_TEMPLATE.format(
            message_type=message_type,
            target_audience=target_audience,
            content=content[:1000],
            known_facts=known_facts[:500],
            hidden_info=hidden_info[:500],
            npc_profiles=npc_profiles[:500],
            extra_context=extra_context[:300],
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            # On failure, err on the side of caution
            return {
                "passed": False,
                "risk_level": "high",
                "checks": [],
                "fix_suggestion": "Critic agent unavailable — content blocked for safety.",
                "reasoning": "Critic error, blocking content.",
            }

        return self._validate(result)

    def _validate(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result.setdefault("passed", False)
        result.setdefault("risk_level", "high")
        result.setdefault("checks", [])
        result.setdefault("fix_suggestion", None)
        result.setdefault("reasoning", "")

        # If any high-severity check fails, override to not passed
        for check in result.get("checks", []):
            if check.get("check") in ("SPOILER_LEAK", "ENDING_SPOIL") and not check.get("passed", True):
                result["passed"] = False
                result["risk_level"] = "high"

        return result


critic_agent = CriticAgent()


# ── Helper: build critic context from AgentState ───────────────

def _build_critic_context(state: AgentState) -> Dict[str, str]:
    """Extract critic inputs from AgentState."""
    ctx = state.get("current_state", {}) or state.get("context", {})

    # Known facts: discovered clues
    discovered = ctx.get("discovered_clues", [])
    known_facts = "\n".join(
        "- {}: {}".format(
            c.get("name", c) if isinstance(c, dict) else str(c),
            c.get("location", "") if isinstance(c, dict) else "",
        )
        for c in discovered[:10]
    )

    # Hidden info: undiscovered clues
    undiscovered = ctx.get("undiscovered_clues", [])
    hidden_info = "\n".join(
        "- {} (trigger: {})".format(
            c.get("name", c) if isinstance(c, dict) else str(c),
            c.get("trigger_condition", "") if isinstance(c, dict) else "",
        )
        for c in undiscovered[:10]
    )

    # NPC profiles
    npcs = ctx.get("active_npcs", [])
    npc_profiles = "\n".join(
        "- {}: {} (secret: {})".format(
            n.get("name", n) if isinstance(n, dict) else str(n),
            n.get("personality", "") if isinstance(n, dict) else "",
            n.get("secret", "") if isinstance(n, dict) else "",
        )
        for n in npcs[:10]
    )

    # RAG results as extra context
    rag_results = state.get("rag_results", [])
    rag_context = ""
    kp_only_chunks = [r for r in rag_results if r.get("visibility") == "kp_only"]
    if kp_only_chunks:
        rag_context = "KP-ONLY content referenced:\n" + "\n".join(
            "- {}".format(r.get("title", r.get("text", "")[:100]))
            for r in kp_only_chunks[:5]
        )

    return {
        "known_facts": known_facts or "无已知信息",
        "hidden_info": hidden_info or "无隐藏信息",
        "npc_profiles": npc_profiles or "无NPC信息",
        "extra_context": rag_context,
    }


# ── LangGraph node ─────────────────────────────────────────────

async def node_critic_check(state: AgentState) -> AgentState:
    """LangGraph node: check all generated output for safety."""
    cctx = _build_critic_context(state)

    content_to_check = state.get("public_reply") or state.get("kp_suggestion") or state.get("suggested_action", "")
    message_type = state.get("message_type", "chat")

    result = await critic_agent.check(
        content=content_to_check,
        message_type=message_type,
        target_audience="player",
        known_facts=cctx["known_facts"],
        hidden_info=cctx["hidden_info"],
        npc_profiles=cctx["npc_profiles"],
        extra_context=cctx["extra_context"],
    )

    state["critic_result"] = result
    state["risk_level"] = result.get("risk_level", "low")

    # If critic rejects and there's a public_reply, clear it
    if not result.get("passed", True) and state.get("public_reply"):
        if result["risk_level"] == "high":
            state["public_reply"] = ""  # Block player-visible output
            state["need_kp_notify"] = True
            state["kp_suggestion"] = (
                state.get("kp_suggestion", "") +
                "\n[Critic blocked output: {}]".format(
                    result.get("reasoning", "safety concern")
                )
            )

    return state
