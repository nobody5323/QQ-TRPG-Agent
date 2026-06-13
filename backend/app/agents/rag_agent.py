"""RAG Agent — wraps the Step 4 retriever as a LangGraph agent node.

Phase 2: Dice-aware retrieval strategy.

When dice_result is present:
  - SUCCESS: Normal retrieval, normal clue weighting
  - FAILURE: Deprioritize locked clues, boost alternative paths
  - FUMBLE: Additional recall of negative consequences, remedy content

Also injects Player State into query enhancement:
  - Already-held clues → deprioritize (player already has them)
  - Player skills → boost matching content (e.g. high Investigation → boost investigation clues)
"""

from typing import Dict, Any
from app.harness.agent_state import AgentState


async def node_rag_retrieve(state: AgentState) -> AgentState:
    """LangGraph node: run RAG retrieval with dice-aware strategy."""
    from app.harness.context_manager import build_rag_context
    from app.rag.retriever import retriever

    campaign_id = state.get("campaign_id", "")
    content = state.get("content", "")
    from app.harness.session_context import get_session
    session = get_session()

    if not campaign_id or not session:
        state["rag_results"] = []
        state["rag_meta"] = {}
        return state

    rag_ctx = await build_rag_context(session, campaign_id)
    state["tool_calls"] = state.get("tool_calls", []) + ["rag_search"]

    # ── Dice-aware query modification ──────────────────────
    query = content
    dice = state.get("dice_result")
    if dice:
        outcome = dice.get("outcome", "unknown")
        if outcome in ("failure", "fumble"):
            # Add alternative-path keywords to query
            query += " 替代方案 绕路 其他方法"
        if dice.get("check_type"):
            # Boost the check type in the query
            query += " " + dice["check_type"]

    # ── Player State injection ─────────────────────────────
    player_states = state.get("player_states", {})
    inventory_items = []
    player_skills = {}
    if player_states:
        # Extract items and skills from all players
        for qq, ps in player_states.items():
            inv = ps.get("inventory", [])
            for item in inv:
                name = item.get("name", item) if isinstance(item, dict) else item
                inventory_items.append(name)
            skills = ps.get("skills", {})
            player_skills.update(skills)

    # Add player context to query
    if inventory_items:
        query += " (player has: " + ", ".join(inventory_items[:5]) + ")"
    # Boost top skills
    top_skills = sorted(player_skills.items(), key=lambda x: x[1], reverse=True)[:3]
    if top_skills:
        query += " (skills: " + ", ".join(
            "{}={}".format(k, v) for k, v in top_skills
        ) + ")"

    # ── Run retrieval ──────────────────────────────────────
    search_result = await retriever.search(
        query=query,
        campaign_id=campaign_id,
        scene_context=rag_ctx.get("scene_name"),
        active_npcs=rag_ctx.get("npc_names"),
        undiscovered_clue_names=rag_ctx.get("undiscovered_clue_names"),
        top_k=5,
    )

    meta = search_result.get("meta", {})
    results = search_result.get("results", [])

    # ── Post-process with dice awareness ───────────────────
    processed = []
    for r in results[:5]:
        payload = r.get("payload", {})
        visibility = payload.get("visibility", "player_visible")
        score = r.get("rerank_score", r.get("score", 0))

        # Dice failure: deprioritize locked clues
        if dice and dice.get("outcome") in ("failure", "fumble"):
            if payload.get("type") == "clue" and visibility == "kp_only":
                score *= 0.3  # Significant deprioritization

        processed.append({
            "text": (payload.get("text", "") or "")[:300],
            "title": payload.get("title", ""),
            "score": score,
            "visibility": visibility,
            "chunk_id": payload.get("chunk_id", ""),
            "type": payload.get("type", "text"),
        })

    state["rag_results"] = processed
    state["rag_meta"] = {
        "fusion_method": meta.get("fusion_method", "unknown"),
        "vector_count": meta.get("vector_count", 0),
        "keyword_count": meta.get("keyword_count", 0),
        "latency_ms": meta.get("latency_ms", 0),
        "player_items_injected": len(inventory_items),
        "player_skills_injected": len(top_skills),
    }

    return state
