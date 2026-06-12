"""Branch Writer Agent — generates new story branches from KP input.

Phase 2 Step 12.5: When the KP decides to deviate from the module, this agent
generates a new branch proposal using existing module data (NPC personalities,
world lore, existing clues) as the foundation.

KP-triggered only — never auto-suggests new branches.
Command: /新分支 <description> (KP private chat to bot)
"""

import json
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.agents.llm_factory import llm_factory, ModelConfig


BRANCH_WRITER_PROMPT = """You are a story branch writer for a Call of Cthulhu TRPG. The Keeper needs a new story branch because the players have gone in an unexpected direction or the Keeper wants to add original content.

Using the provided context (NPCs, scenes, clues, world setting), generate a self-consistent new story branch.

Respond with ONLY this JSON:
{
  "title": "Branch name, under 30 chars",
  "premise": "Why this branch exists — what happened to trigger it. Under 150 chars.",
  "new_scenes": [
    {
      "name": "Scene name",
      "description": "What's in this scene. Under 200 chars.",
      "location": "Where it takes place",
      "connected_npcs": ["NPC name"]
    }
  ],
  "new_clues": [
    {
      "name": "Clue name",
      "description": "What the clue reveals",
      "location": "Where to find it",
      "trigger": "What action reveals it",
      "hidden": true
    }
  ],
  "affected_npcs": [
    {
      "name": "NPC name",
      "new_attitude": "changed attitude if any",
      "new_secret": "new secret if any, or keep original"
    }
  ],
  "possible_outcomes": [
    {
      "description": "How this branch could end",
      "conditions": "What needs to happen",
      "connection_to_main": "How it reconnects to the main plot, or 'permanent_fork'"
    }
  ],
  "consistency_check": "Self-check: does this contradict any existing NPC or world facts?",
  "suggested_dice_events": [
    {
      "scene": "Which scene",
      "check_type": "Skill to roll",
      "difficulty": "regular" | "hard" | "extreme",
      "success": "What happens on success",
      "failure": "What happens on failure"
    }
  ]
}

CRITICAL CONSTRAINTS:
1. All NPCs must stay in character — no sudden personality changes without cause.
2. World setting must be consistent: 1920s Cthulhu Mythos, no anachronisms.
3. Every branch MUST provide at least one path back to the main story, unless the KP explicitly said otherwise.
4. Generated clues must be dice-able: every key discovery should have a skill check.
5. This is a SUGGESTION — the KP may adopt, modify, or reject freely."""


BRANCH_USER_TEMPLATE = """KP's description of the situation:
{kp_description}

Current game state:
- Active scene: {scene_name}
- Active NPCs: {active_npcs}
- Discovered clues: {discovered_clues}
- Undiscovered clues: {undiscovered_clues}

World setting context:
{world_context}

Player states:
{player_states}

Generate a self-consistent branch proposal."""


class BranchWriter:
    """Generates new story branch proposals from KP input + existing module data."""

    def __init__(self, model_config: ModelConfig = None):
        self._config = model_config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg = self._config or llm_factory.get_config_for_agent("branch")
            self._client = AsyncOpenAI(
                api_key=cfg.api_key,
                base_url=cfg.base_url,
            )
        return self._client

    @property
    def model(self):
        cfg = self._config or llm_factory.get_config_for_agent("branch")
        return cfg.model

    async def generate(
        self,
        kp_description: str,
        scene_name: str = "",
        active_npcs: str = "",
        discovered_clues: str = "",
        undiscovered_clues: str = "",
        world_context: str = "",
        player_states: str = "",
    ) -> Dict[str, Any]:
        """Generate a new branch proposal.

        Args:
            kp_description: The KP's free-text description of the situation.
            world_context: Extracted world lore from module chunks.
            player_states: Current player inventory, clues, status effects.

        Returns:
            BranchProposal dict.
        """
        user_prompt = BRANCH_USER_TEMPLATE.format(
            kp_description=kp_description[:500],
            scene_name=scene_name or "unknown",
            active_npcs=active_npcs[:500],
            discovered_clues=discovered_clues[:300],
            undiscovered_clues=undiscovered_clues[:300],
            world_context=world_context[:800],
            player_states=player_states[:500],
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": BRANCH_WRITER_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            result = json.loads(text)
        except Exception:
            result = self._fallback(kp_description)

        return self._validate(result)

    def _validate(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result.setdefault("title", "未命名分支")
        result.setdefault("premise", "")
        result.setdefault("new_scenes", [])
        result.setdefault("new_clues", [])
        result.setdefault("affected_npcs", [])
        result.setdefault("possible_outcomes", [])
        result.setdefault("consistency_check", "")
        result.setdefault("suggested_dice_events", [])

        # Ensure at least one outcome reconnects to main plot
        has_return = any(
            o.get("connection_to_main", "") != "permanent_fork"
            for o in result["possible_outcomes"]
        )
        if not has_return and result["possible_outcomes"]:
            result["possible_outcomes"].append({
                "description": "回归主线",
                "conditions": "KP决定推进主线剧情",
                "connection_to_main": "direct_return",
            })

        return result

    def _fallback(self, kp_description: str) -> Dict[str, Any]:
        return {
            "title": "新分支",
            "premise": kp_description[:100],
            "new_scenes": [],
            "new_clues": [],
            "affected_npcs": [],
            "possible_outcomes": [{
                "description": "回归主线",
                "conditions": "KP决定推进",
                "connection_to_main": "direct_return",
            }],
            "consistency_check": "Branch writer unavailable — KP should verify manually.",
            "suggested_dice_events": [],
        }


branch_writer = BranchWriter()
