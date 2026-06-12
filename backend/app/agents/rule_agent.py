"""Rule Assistant Agent — answers rule questions and suggests dice checks.

COC 7th edition focused. Provides:
  1. Skill check difficulty suggestion
  2. Dice command format
  3. Success/failure effect descriptions
"""

import json
from typing import Dict, Any
from openai import AsyncOpenAI

from app.config import settings
from app.harness.agent_state import AgentState
from app.agents.llm_factory import llm_factory, ModelConfig


RULE_SYSTEM_PROMPT = """You are a Call of Cthulhu 7th Edition rules assistant. Help the Keeper by suggesting appropriate skill checks and interpreting rules.

Respond with ONLY this JSON:
{
  "suggested_check": "skill name in Chinese or English",
  "difficulty": "regular" | "hard" | "extreme",
  "target_value": <int, the skill value to roll against>,
  "dice_command": ".ra <skill> <target>",
  "success_effect": "What happens on success, under 100 chars.",
  "failure_effect": "What happens on failure, under 100 chars.",
  "rule_reference": "Which rule book section this relates to, if known.",
  "reasoning": "Brief explanation."
}

COC 7th Difficulty Levels:
- Regular: roll <= skill value
- Hard: roll <= skill/2
- Extreme: roll <= skill/5

Common COC skills:
侦查/Spot Hidden, 图书馆使用/Library Use, 聆听/Listen, 心理学/Psychology,
潜行/Stealth, 格斗/Fighting, 射击/Firearms, 急救/First Aid,
说服/Persuade, 魅惑/Charm, 恐吓/Intimidate, 话术/Fast Talk,
考古学/Archaeology, 历史/History, 神秘学/Occult, 博物学/Natural World,
机械维修/Mechanical Repair, 电气维修/Electrical Repair,
锁匠/Locksmith, 驾驶/Drive Auto, 追踪/Track

If the question doesn't involve a dice check, set suggested_check to empty string.
"""


class RuleAgent:
    """COC rules assistant for skill checks and rule interpretation."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("rule")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("rule")
        return cfg.model

    async def lookup(
        self,
        question: str,
        current_scene: str = "",
        context: str = "",
    ) -> Dict[str, Any]:
        """Look up rule or suggest a skill check."""
        user_prompt = f"Question: {question[:300]}\nScene: {current_scene}\nContext: {context[:300]}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": RULE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            result = self._fallback(question)

        return self._validate(result)

    def _validate(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result.setdefault("suggested_check", "")
        result.setdefault("difficulty", "regular")
        result.setdefault("target_value", 0)
        result.setdefault("dice_command", "")
        result.setdefault("success_effect", "")
        result.setdefault("failure_effect", "")
        result.setdefault("rule_reference", "")
        result.setdefault("reasoning", "")
        return result

    def _fallback(self, question: str) -> Dict[str, Any]:
        return {
            "suggested_check": "",
            "difficulty": "regular",
            "target_value": 0,
            "dice_command": "",
            "success_effect": "",
            "failure_effect": "",
            "rule_reference": "",
            "reasoning": "Rule agent unavailable.",
        }


rule_agent = RuleAgent()


# ── LangGraph nodes ────────────────────────────────────────────

async def node_rule_lookup(state: AgentState) -> AgentState:
    """LangGraph node: answer a rule question."""
    content = state.get("content", "")
    ctx = state.get("current_state", {}) or state.get("context", {})

    scene_name = ""
    if isinstance(ctx.get("active_scene"), dict):
        scene_name = ctx["active_scene"].get("name", "")

    context = ""
    if ctx.get("active_npcs"):
        context = "NPCs: " + ", ".join(
            n.get("name", "") for n in ctx["active_npcs"]
        )

    result = await rule_agent.lookup(
        question=content,
        current_scene=scene_name,
        context=context,
    )

    parts = ["[Rule Lookup]"]
    parts.append("Question: {}".format(content[:100]))
    if result["suggested_check"]:
        parts.append("Suggested: {} ({})".format(
            result["suggested_check"], result["difficulty"]
        ))
        parts.append("Dice: {}".format(result["dice_command"]))
        parts.append("Success: {}".format(result["success_effect"]))
        parts.append("Failure: {}".format(result["failure_effect"]))
    else:
        parts.append("No dice check needed.")
    if result["rule_reference"]:
        parts.append("Ref: {}".format(result["rule_reference"]))

    state["suggested_action"] = "\n".join(parts)
    state["kp_suggestion"] = state["suggested_action"]
    state["need_kp_notify"] = True

    return state
