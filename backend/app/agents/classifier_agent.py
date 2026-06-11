"""Message Classifier Agent (Phase 1: direct LLM call, no LangGraph).

Classifies TRPG group chat messages into types:
- player_action: player investigating, searching, interacting (triggers RAG + suggestion)
- roleplay: player speaking as their character (triggers RAG + NPC suggestion)
- chat: off-topic conversation (ignored by system)
- rule_question: rules or dice question (triggers rule lookup)
- kp_command: KP speaking (already handled separately via private message)

Phase 2 upgrades:
- Add few-shot examples from history
- Replace with LangGraph node
- Add confidence-based fallback to keyword rules
"""

import json
from typing import Dict, Any
from openai import AsyncOpenAI

from app.config import settings


CLASSIFIER_SYSTEM_PROMPT = """You are a TRPG (Tabletop Role-Playing Game) message classifier for a Keeper (GM) assistant system. Your job is to classify player chat messages.

Classify each message into exactly ONE category:

1. player_action: The player is taking an in-game action — investigating, searching, examining, moving, talking to an NPC, using an item. These messages describe what the player character DOES. Examples: "I search the bookshelf", "I examine the painting", "I talk to the old man", "I open the drawer", "我想调查书房", "我检查画像背后".

2. roleplay: The player is speaking in character (IC dialogue), using first-person storytelling, or describing their character's emotions/reactions. These are NOT direct actions but narrative embellishment. Examples: "I tremble at the sight", "This place gives me the creeps", "我颤抖着说：你是谁？", "这地方真叫人不安".

3. chat: Off-topic conversation, OOC (out of character) chat, greeting, jokes, or anything unrelated to the game. These should be ignored by the system. Examples: "lol", "今天吃啥", "etc.", "give me a minute".

4. rule_question: The player is asking about game rules, character stats, dice mechanics, or skill checks. Examples: "How do I roll for investigation?", "What's my SAN?", "这个技能怎么投？", "我的HP是多少".

5. kp_command: The Keeper speaking in the group (not private). These start with / or are clearly Keeper rulings. Examples: "/roll 1d100", "Make a SAN check".

Respond with ONLY valid JSON:
{"message_type": "player_action", "confidence": 0.95, "need_rag": true, "need_kp_suggestion": true, "need_state_update": true, "reasoning": "brief explanation"}"""


CLASSIFIER_USER_TEMPLATE = """Message: {message}

Recent context (last messages in this campaign):
{recent_context}

Current scene: {active_scene}
Present NPCs: {npc_names}
"""


class ClassifierAgent:
    """LLM-based message classifier using direct OpenAI call."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        self.model = settings.OPENAI_MODEL
        self.system_prompt = CLASSIFIER_SYSTEM_PROMPT

    async def classify(
        self,
        message: str,
        recent_context: str = "",
        active_scene: str = "unknown",
        npc_names: str = "none",
    ) -> Dict[str, Any]:
        """Classify a single message.

        Returns:
            dict: {message_type, confidence, need_rag, need_kp_suggestion,
                   need_state_update, reasoning}
        """
        # Build user prompt
        user_prompt = CLASSIFIER_USER_TEMPLATE.format(
            message=message[:500],
            recent_context=recent_context[:1000],
            active_scene=active_scene or "unknown",
            npc_names=npc_names or "none",
        )

        # Call LLM
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            text = response.choices[0].message.content or "{}"
            result = json.loads(text)

        except Exception as e:
            # Fallback: keyword-based classification on LLM failure
            result = self._keyword_fallback(message)

        # Validate result
        valid_types = {"player_action", "roleplay", "chat", "rule_question", "kp_command"}
        msg_type = result.get("message_type", "chat")
        if msg_type not in valid_types:
            msg_type = "chat"

        # Ensure all fields exist
        return {
            "message_type": msg_type,
            "confidence": result.get("confidence", 0.5),
            "need_rag": result.get("need_rag", msg_type in ("player_action", "roleplay", "rule_question")),
            "need_kp_suggestion": result.get("need_kp_suggestion", msg_type in ("player_action", "roleplay")),
            "need_state_update": result.get("need_state_update", msg_type == "player_action"),
            "reasoning": result.get("reasoning", ""),
        }

    def _keyword_fallback(self, message: str) -> Dict[str, Any]:
        """Keyword-based fallback if LLM is unavailable."""
        player_action_kw = ["调查", "搜索", "检查", "查看", "询问", "我想", "我要",
                           "使用", "走", "去", "打开", "翻", "找", "talk", "search",
                           "examine", "look", "investigate", "open", "use"]
        rule_kw = [".r", "。r", "骰", "roll", "规则", "规则书", "HP", "SAN", "技能",
                   "检定", "投骰", "判定"]

        msg_lower = message.lower()
        for kw in rule_kw:
            if kw in msg_lower or kw in message:
                return {
                    "message_type": "rule_question",
                    "confidence": 0.7,
                    "need_rag": True,
                    "need_kp_suggestion": True,
                    "need_state_update": False,
                    "reasoning": "keyword matched rule_question: " + kw,
                }
        for kw in player_action_kw:
            if kw in message:
                return {
                    "message_type": "player_action",
                    "confidence": 0.7,
                    "need_rag": True,
                    "need_kp_suggestion": True,
                    "need_state_update": True,
                    "reasoning": "keyword matched player_action: " + kw,
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
