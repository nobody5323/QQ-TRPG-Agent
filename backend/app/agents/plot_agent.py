"""Plot Deviation Agent — detects player drift from main storyline.

Phase 2: Dice-aware deviation scoring.

Deviation Score = weighted sum of 6 factors (0-1):
  1. Semantic similarity of recent messages vs main plot (weight 0.3)
  2. Key clue triggers: time since last clue triggered (weight 0.25)
     — DISTINGUISHES: failed dice attempts vs not trying
  3. Player action vs current scene relevance (weight 0.15)
  4. NPC interaction relevance (weight 0.1)
  5. Scene dwell time (weight 0.1)
  6. Recent dice success rate (weight 0.1) — NEW

Dice-aware classification:
  - High action coverage + low success rate → Dice-blocked (not deviation)
  - Low action coverage + high success rate → True deviation
  - Low action coverage + low success rate → Needs KP intervention

Response levels:
  - low (score < 0.3): No intervention
  - medium (0.3-0.6): Gentle nudge suggestion
  - high (> 0.6): Strong intervention recommended
"""

import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.harness.agent_state import AgentState
from app.agents.llm_factory import llm_factory, ModelConfig


PLOT_DEVIATION_PROMPT = """You are a plot deviation detector for a Call of Cthulhu TRPG. Analyze whether the players are drifting away from the main storyline.

Respond with ONLY this JSON:
{
  "deviation_score": <float 0.0-1.0>,
  "deviation_type": "true_deviation" | "dice_blocked" | "mixed" | "on_track",
  "factors": {
    "semantic_drift": <float 0-1>,
    "clue_stagnation": <float 0-1>,
    "scene_relevance": <float 0-1>,
    "npc_relevance": <float 0-1>,
    "dwell_time": <float 0-1>,
    "dice_block_rate": <float 0-1>
  },
  "level": "low" | "medium" | "high",
  "suggestion": "A brief suggestion for the Keeper in Chinese or English, under 100 chars.",
  "suggestion_type": "gentle_nudge" | "dice_adjustment" | "alternative_clue" | "direct_push" | "none",
  "reasoning": "Detailed analysis, 1-2 sentences."
}

Scoring guidelines:
- deviation_score 0-0.3: Players are following the plot naturally
- deviation_score 0.3-0.6: Some drift detected, consider a gentle nudge
- deviation_score 0.6+: Significant deviation, intervention needed

For dice_blocked type: the suggestion should focus on lowering difficulty or providing alternative clues, NOT on pushing players back to the main story path.

For true_deviation: suggest a narrative nudge to guide players back.
"""


PLOT_USER_TEMPLATE = """Campaign: {campaign_name}
Active scene: {scene_name}
Main plot stage: {plot_stage}

Discovered clues: {discovered}
Undiscovered critical clues: {undiscovered}

Recent messages (last {msg_count}):
{recent_messages}

Recent dice results (last 10 rolls):
{dice_summary}

Dice stats: {attempts} attempts, {successes} successes, success rate: {success_rate:.0%}

Analyze deviation."""


class PlotAgent:
    """Dice-aware plot deviation detector."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("plot")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("plot")
        return cfg.model

    async def analyze(
        self,
        campaign_name: str = "",
        scene_name: str = "",
        plot_stage: str = "",
        discovered: str = "",
        undiscovered: str = "",
        recent_messages: str = "",
        dice_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Analyze plot deviation.

        Args:
            dice_results: List of recent parsed DiceResult dicts.

        Returns:
            dict with deviation_score, deviation_type, level, suggestion, etc.
        """
        dice = dice_results or []
        attempts = len(dice)
        successes = sum(1 for d in dice if d.get("outcome", "") in (
            "critical_success", "extreme_success", "hard_success", "normal_success"
        ))
        success_rate = successes / max(attempts, 1)

        dice_summary = "\n".join(
            "{}: rolled {} vs {} → {}".format(
                d.get("check_type", "?"),
                d.get("rolled", "?"),
                d.get("target", "?"),
                d.get("outcome", "?"),
            )
            for d in dice[-10:]
        ) if dice else "No recent dice rolls."

        user_prompt = PLOT_USER_TEMPLATE.format(
            campaign_name=campaign_name or "unknown",
            scene_name=scene_name or "unknown",
            plot_stage=plot_stage or "unknown",
            discovered=discovered[:300],
            undiscovered=undiscovered[:300],
            msg_count=min(len(recent_messages.split("\n")), 15),
            recent_messages=recent_messages[:1000],
            dice_summary=dice_summary,
            attempts=attempts,
            successes=successes,
            success_rate=success_rate,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": PLOT_DEVIATION_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            result = self._fallback()

        return self._validate(result)

    def _validate(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result.setdefault("deviation_score", 0.0)
        result.setdefault("deviation_type", "on_track")
        result.setdefault("level", "low")
        result.setdefault("suggestion", "")
        result.setdefault("suggestion_type", "none")
        result.setdefault("reasoning", "")

        score = result["deviation_score"]
        if score < 0.3:
            result["level"] = "low"
        elif score < 0.6:
            result["level"] = "medium"
        else:
            result["level"] = "high"

        return result

    def _fallback(self) -> Dict[str, Any]:
        return {
            "deviation_score": 0.0,
            "deviation_type": "on_track",
            "factors": {
                "semantic_drift": 0.0, "clue_stagnation": 0.0,
                "scene_relevance": 0.0, "npc_relevance": 0.0,
                "dwell_time": 0.0, "dice_block_rate": 0.0,
            },
            "level": "low",
            "suggestion": "",
            "suggestion_type": "none",
            "reasoning": "Plot agent unavailable, defaulting to on_track.",
        }


plot_agent = PlotAgent()
