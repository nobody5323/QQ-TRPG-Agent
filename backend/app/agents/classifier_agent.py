"""Message Classifier Agent (Phase 2: few-shot upgrade with LangGraph node).

Classifies TRPG group chat messages into 6 types with few-shot examples
and confidence calibration. Also serves as the node_classify LangGraph node.

Categories:
  player_action — in-game investigation, movement, object interaction
  roleplay — in-character dialogue or narrative description
  npc_dialogue — player speaking TO an NPC
  rule_question — rules, dice, stat, or skill check questions
  kp_command — KP-facing commands starting with /
  chat — off-topic conversation, OOC chatter, jokes
"""

import json
from typing import Dict, Any
from openai import AsyncOpenAI

from app.config import settings
from app.harness.agent_state import AgentState
from app.agents.llm_factory import llm_factory, ModelConfig


CLASSIFIER_SYSTEM_PROMPT = """You are a TRPG (Tabletop Role-Playing Game) message classifier for a Keeper (GM) assistant system. Your job is to classify messages from players in a Call of Cthulhu group chat.

Classify each message into exactly ONE of these categories:

1. player_action — The player describes their character taking an in-game action: investigating, searching, examining, picking up, moving between rooms, using items, etc. These describe what the character DOES physically.
   Examples:
   "I search the desk drawer carefully" → player_action
   "I use the magnifying glass on the stain" → player_action

2. roleplay — The player speaks in character (IC dialogue) or narrates their character's internal state, emotions, or reactions. These are NOT direct mechanical actions but narrative/story content.
   Examples:
   "This place... something terrible happened here" → roleplay
   "My hands won't stop shaking" → roleplay

3. npc_dialogue — The player directly speaks TO a named NPC in character. The key difference from roleplay is that this is addressed TO someone specific who can respond.
   Examples:
   "Old man, when did you last see him?" → npc_dialogue
   "Lady Meredith, do you recognize this badge?" → npc_dialogue

4. rule_question — The player asks about game rules, skill values, dice mechanics, or character stats.
   Examples:
   "What is my Spot Hidden skill?" → rule_question
   "How does a SAN check work?" → rule_question
   ".r 1d100" (dice roll) → rule_question

5. kp_command — A command directed at the system, starting with / (slash). These are meta-game instructions, not in-game content.
   Examples: "/upload", "/help", "/search clue diary"

6. chat — Off-topic conversation, OOC (out of character) banter, greetings, jokes, technical discussion, or anything not related to the game world.
   Examples: "lol that dice roll was cursed", "take a break for dinner"

IMPORTANT RULES:
- If a message contains BOTH action description AND dialogue, classify as npc_dialogue if the dialogue is addressed to an NPC, otherwise roleplay.
- Messages that start with / are always kp_command.
- If uncertain between roleplay and chat, prefer roleplay.
- Dice rolls (.r, .ra, .rc, etc.) from dice bots should be classified as rule_question.

Respond with ONLY this JSON structure:
{
  "message_type": "<one of the 6 types>",
  "confidence": <float 0.0 to 1.0>,
  "need_rag": <bool>,
  "need_kp_suggestion": <bool>,
  "need_state_update": <bool>,
  "reasoning": "<brief explanation, 1 sentence>"
}"""


CLASSIFIER_USER_TEMPLATE = """Message to classify: {message}

Recent context (last messages in this campaign):
{recent_context}

Current scene: {active_scene}
Present NPCs: {npc_names}

Classify the message above and return JSON."""


class ClassifierAgent:
    """LLM-based message classifier with few-shot system prompt."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("classifier")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("classifier")
        return cfg.model

    async def classify(
        self,
        message: str,
        recent_context: str = "",
        active_scene: str = "unknown",
        npc_names: str = "none",
    ) -> Dict[str, Any]:
        """Classify a single message."""
        user_prompt = CLASSIFIER_USER_TEMPLATE.format(
            message=message[:500],
            recent_context=recent_context[:1000],
            active_scene=active_scene or "unknown",
            npc_names=npc_names or "none",
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            result = self._keyword_fallback(message)

        return self._validate(result, message)

    def _validate(self, result: Dict[str, Any], message: str = "") -> Dict[str, Any]:
        """Validate and fill missing fields."""
        valid_types = {
            "player_action", "roleplay", "npc_dialogue",
            "rule_question", "kp_command", "chat",
        }
        msg_type = result.get("message_type", "chat")
        if msg_type not in valid_types:
            msg_type = "chat"

        need_rag_types = {"player_action", "roleplay", "npc_dialogue", "rule_question"}
        need_sug_types = {"player_action", "npc_dialogue"}
        need_state_types = {"player_action"}

        return {
            "message_type": msg_type,
            "confidence": min(max(result.get("confidence", 0.5), 0.0), 1.0),
            "need_rag": result.get("need_rag", msg_type in need_rag_types),
            "need_kp_suggestion": result.get("need_kp_suggestion", msg_type in need_sug_types),
            "need_state_update": result.get("need_state_update", msg_type in need_state_types),
            "reasoning": result.get("reasoning", ""),
        }

    def _keyword_fallback(self, message: str) -> Dict[str, Any]:
        """Keyword-based fallback if LLM is unavailable."""
        if any(p in message for p in (".r", ".ra", ".rc", ".st")):
            return {
                "message_type": "rule_question",
                "confidence": 0.8,
                "need_rag": False,
                "need_kp_suggestion": False,
                "need_state_update": False,
                "reasoning": "dice pattern detected",
            }

        import re
        npc_address = re.search(
            r'(管家|神父|警长|医生|夫人|先生|小姐|老板|店主|女士)[,;: ]',
            message
        )
        if npc_address:
            return {
                "message_type": "npc_dialogue",
                "confidence": 0.75,
                "need_rag": True,
                "need_kp_suggestion": True,
                "need_state_update": False,
                "reasoning": "NPC address pattern: " + npc_address.group(1),
            }

        action_kw = [
            "search", "examine", "look", "investigate", "open", "use",
            "pick", "grab", "check", "inspect", "read", "enter", "leave",
        ]
        for kw in action_kw:
            if kw in message.lower():
                return {
                    "message_type": "player_action",
                    "confidence": 0.7,
                    "need_rag": True,
                    "need_kp_suggestion": True,
                    "need_state_update": True,
                    "reasoning": "action keyword: " + kw,
                }

        rp_kw = ["feel", "afraid", "scared", "strange", "weird", "creepy"]
        if any(kw in message.lower() for kw in rp_kw):
            return {
                "message_type": "roleplay",
                "confidence": 0.6,
                "need_rag": True,
                "need_kp_suggestion": False,
                "need_state_update": False,
                "reasoning": "roleplay signal keyword",
            }

        return {
            "message_type": "chat",
            "confidence": 0.5,
            "need_rag": False,
            "need_kp_suggestion": False,
            "need_state_update": False,
            "reasoning": "no keywords matched, default to chat",
        }


classifier_agent = ClassifierAgent()


async def node_classify(state: AgentState) -> AgentState:
    """LangGraph node: classify the incoming message."""
    from app.harness.context_manager import build_context

    campaign_id = state.get("campaign_id", "")
    content = state.get("content", "")
    sender = state.get("sender", "")
    from app.harness.session_context import get_session
    session = get_session()

    if campaign_id and session:
        ctx = await build_context(session, campaign_id)
        state["current_state"] = ctx
        state["context"] = ctx

        recent = "\n".join(
            "{}: {}".format(m["sender"], m["content"])
            for m in ctx.get("recent_messages", [])[-5:]
        )
        active_scene = ctx["active_scene"]["name"] if ctx.get("active_scene") else None
        npc_names = ", ".join(n["name"] for n in ctx.get("active_npcs", []))

        result = await classifier_agent.classify(
            message=content,
            recent_context=recent,
            active_scene=active_scene or "unknown",
            npc_names=npc_names or "none",
        )
    else:
        result = classifier_agent._keyword_fallback(content)

    state["message_type"] = result["message_type"]
    state["confidence"] = result["confidence"]
    state["need_rag"] = result["need_rag"]
    state["need_kp_suggestion"] = result["need_kp_suggestion"]
    state["need_state_update"] = result["need_state_update"]
    state["reasoning"] = result.get("reasoning", "")

    return state
