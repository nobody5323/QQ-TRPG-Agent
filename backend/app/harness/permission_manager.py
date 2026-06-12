"""Permission Manager — filters output by visibility level.

Phase 2 Step 13.2: Ensures kp_only content never reaches players.
Three visibility tiers:
  - player_visible: Safe for group chat and player-facing output
  - kp_only: Only shown in KP private chat or web console
  - prohibited: Never output (hard-blocked by Critic)
"""

from typing import Dict, Any, List

# Visibility tag constants
PLAYER_VISIBLE = "player_visible"
KP_ONLY = "kp_only"
PROHIBITED = "prohibited"


class PermissionManager:
    """Filters and routes content based on visibility tags."""

    @staticmethod
    def filter_rag_results(
        rag_results: List[Dict[str, Any]],
        audience: str = "player",
    ) -> List[Dict[str, Any]]:
        """Filter RAG results by audience visibility.

        Args:
            rag_results: List of RAG result dicts with 'visibility' field.
            audience: "player" or "kp".

        Returns:
            Filtered list — kp_only results removed for player audience.
        """
        if audience == "kp":
            return rag_results

        return [
            r for r in rag_results
            if r.get("visibility", PLAYER_VISIBLE) != KP_ONLY
        ]

    @staticmethod
    def filter_output(
        output: Dict[str, Any],
        audience: str = "player",
    ) -> Dict[str, Any]:
        """Filter the final output dict for a specific audience.

        For player audience:
          - Remove kp_suggestion
          - Remove any kp_only fields
          - Only include public_reply and basic classification

        For KP audience:
          - Return everything
        """
        if audience == "kp":
            return output

        # Player-safe output
        safe = {
            "message_type": output.get("message_type", "chat"),
            "public_reply": output.get("public_reply", ""),
            "classification": output.get("classification", {}),
        }

        # Include need_kp_notify so the bot knows to notify KP separately
        safe["need_kp_notify"] = output.get("need_kp_notify", False)

        return safe

    @staticmethod
    def tag_content(
        rag_results: List[Dict[str, Any]],
        kp_only_ids: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """Tag RAG results with correct visibility.

        If a result's chunk_id is in kp_only_ids, mark it as kp_only.
        """
        kp_ids = set(kp_only_ids or [])
        for r in rag_results:
            if r.get("chunk_id") in kp_ids:
                r["visibility"] = KP_ONLY
            elif not r.get("visibility"):
                r["visibility"] = PLAYER_VISIBLE
        return rag_results

    @staticmethod
    def check_spoiler_risk(
        text: str,
        hidden_clue_names: List[str],
    ) -> Dict[str, Any]:
        """Simple keyword check: does text contain any hidden clue names?

        This is a fast pre-check before the LLM-based Critic.
        """
        found = []
        for name in hidden_clue_names:
            if name and len(name) > 2 and name in text:
                found.append(name)

        if found:
            return {
                "risk": "high",
                "matched_clues": found,
                "reason": "Text contains hidden clue names: {}".format(", ".join(found)),
            }

        return {"risk": "low", "matched_clues": [], "reason": ""}


permission_manager = PermissionManager()
