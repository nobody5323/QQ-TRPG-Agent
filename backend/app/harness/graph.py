"""LangGraph orchestration graph — Phase 2 full implementation.

Graph structure:
    [classify] → route_by_message_type
                    |
         ┌──────────┼──────────┬──────────────┬──────────┬──────────┐
         ▼          ▼          ▼              ▼          ▼          ▼
     player_     roleplay   npc_         rule_       kp_        chat
     action                 dialogue     question    command
         │          │          │              │          │          │
         ▼          ▼          ▼              ▼          ▼          ▼
      [rag]      [rag]      [rag]      [rule]     [cmd]     [chat_bot]
         │          │          │              │          │          │
         ▼          ▼          ▼              ▼          │          ▼
    [state]    [npc]     [npc]        [suggest]        │     [critic]
         │          │          │              │          │          │
         ▼          ▼          ▼              ▼          │          ▼
    [suggest]  [suggest]  [suggest]     [critic]       │     [output]
         │          │          │              │          │
         └──────────┴──────────┴──────────────┴──────────┘
                                         │
                                    [critic] → route_by_risk
                                         │
                                    [output] → END
"""

from typing import Literal

from langgraph.graph import StateGraph, END
# Checkpointer removed: AsyncSession in AgentState is not msgpack-serializable.

from app.harness.agent_state import AgentState, new_state


async def node_classify(state: AgentState) -> AgentState:
    """Classify message using ClassifierAgent."""
    from app.agents.classifier_agent import node_classify as _impl
    return await _impl(state)


async def node_rag_retrieve(state: AgentState) -> AgentState:
    """RAG retrieval with dice-aware strategy."""
    from app.agents.rag_agent import node_rag_retrieve as _impl
    return await _impl(state)


async def node_build_suggestion(state: AgentState) -> AgentState:
    """Build KP suggestion from classification + RAG + state."""
    content = state.get("content", "")
    sender = state.get("sender", "")
    msg_type = state.get("message_type", "chat")
    ctx = state.get("current_state", {}) or state.get("context", {})

    parts = []

    type_labels = {
        "player_action": "Player Action",
        "roleplay": "Roleplay",
        "npc_dialogue": "NPC Dialogue",
        "rule_question": "Rule Question",
        "chat": "Chat",
        "kp_command": "KP Command",
    }
    parts.append("[{}]".format(type_labels.get(msg_type, "Message")))
    parts.append("From: {}".format(sender))
    parts.append("Msg: {}".format(content[:200]))
    parts.append("")

    scene = ctx.get("active_scene")
    if scene:
        parts.append("Scene: {}".format(
            scene["name"] if isinstance(scene, dict) else scene
        ))
        if isinstance(scene, dict) and scene.get("summary"):
            parts.append("  {}".format(scene["summary"][:200]))

    npcs = ctx.get("active_npcs", [])
    if npcs:
        names = [n["name"] if isinstance(n, dict) else str(n) for n in npcs]
        parts.append("NPCs: {}".format(", ".join(names)))

    results = state.get("rag_results", [])
    if results:
        meta = state.get("rag_meta", {})
        lat = meta.get("latency_ms", "?")
        parts.append("")
        parts.append("Module ({}ms):".format(lat))
        for i, r in enumerate(results[:3], 1):
            text = r.get("text", "")[:200]
            title = r.get("title", "") or ""
            vis = r.get("visibility", "player_visible")
            tag = " [KP Only]" if vis == "kp_only" else ""
            prefix = "[{}]".format(title) if title else ""
            parts.append("{}. {}{}".format(i, prefix, tag))
            parts.append("   {}".format(text))

    undiscovered = ctx.get("undiscovered_clues", [])
    if undiscovered:
        names = [
            c["name"] if isinstance(c, dict) else str(c)
            for c in undiscovered[:5]
        ]
        parts.append("")
        parts.append("Undiscovered: {}".format(", ".join(names)))

    state["suggested_action"] = "\n".join(parts)
    state["kp_suggestion"] = state["suggested_action"]
    state["need_kp_notify"] = state.get("need_kp_suggestion", False)

    return state


async def node_npc_roleplay(state: AgentState) -> AgentState:
    """Generate NPC dialogue response."""
    from app.agents.npc_agent import node_npc_roleplay as _impl
    return await _impl(state)


async def node_rule_lookup(state: AgentState) -> AgentState:
    """Answer rule question or suggest dice check."""
    from app.agents.rule_agent import node_rule_lookup as _impl
    return await _impl(state)


async def node_state_track(state: AgentState) -> AgentState:
    """Track game state changes (after player_action)."""
    from app.agents.state_agent import node_state_track as _impl
    return await _impl(state)


async def node_kp_command(state: AgentState) -> AgentState:
    """KP command processing — handled by bot layer, minimal graph node."""
    content = state.get("content", "")
    state["suggested_action"] = "[KP Command: {}]".format(content[:50])
    state["need_kp_notify"] = False
    return state


async def node_chat_bot(state: AgentState) -> AgentState:
    """Persona-based casual chat response."""
    from app.agents.chat_agent import node_chat_bot as _impl
    return await _impl(state)


async def node_critic_check(state: AgentState) -> AgentState:
    """Safety check on all generated output."""
    from app.agents.critic_agent import node_critic_check as _impl
    return await _impl(state)


async def node_output(state: AgentState) -> AgentState:
    """Pack the final output dict for the API response."""
    existing = state.get("output", {})

    # ── Fallback: generate public_reply if none was set ──
    public_reply = state.get("public_reply", "")
    if not public_reply:
        content = state.get("content", "")
        msg_type = state.get("message_type", "chat")
        rag_results = state.get("rag_results", [])
        if rag_results:
            top = rag_results[0]
            title = top.get("title", "")
            text = (top.get("text") or "")[:300]
            score = top.get("score", 0)
            public_reply = f"[模组检索] {title} (相关度 {score:.0%})\n{text}"
        elif msg_type == "player_action":
            public_reply = f"收到行动: {content[:100]}"
        elif msg_type == "roleplay":
            public_reply = "（已记录角色扮演）"
        else:
            public_reply = f"收到: {content[:100]}"
        state["public_reply"] = public_reply

    # ── Also fallback kp_suggestion ──
    kp_suggestion = state.get("kp_suggestion", "")

    state["output"] = {
        "need_kp_notify": state.get("need_kp_notify", False),
        "kp_suggestion": kp_suggestion,
        "public_reply": state.get("public_reply", ""),
        "message_type": state.get("message_type", "chat"),
        "classification": {
            "message_type": state.get("message_type"),
            "confidence": state.get("confidence"),
            "need_rag": state.get("need_rag"),
            "need_kp_suggestion": state.get("need_kp_suggestion"),
            "need_state_update": state.get("need_state_update"),
            "reasoning": state.get("reasoning"),
        },
        "rag_meta": state.get("rag_meta", {}),
        "critic_result": state.get("critic_result", {}),
        "state_diff": state.get("state_diff", {}),
        "blocked": existing.get("blocked", False),
        "block_reason": existing.get("block_reason", ""),
    }
    return state


def route_by_message_type(state: AgentState) -> str:
    """After classify, route to the appropriate processing node."""
    msg_type = state.get("message_type", "chat")

    routes = {
        "player_action": "rag_retrieve",
        "roleplay": "rag_retrieve",
        "npc_dialogue": "rag_retrieve",
        "rule_question": "rule_lookup",
        "kp_command": "kp_command",
        "chat": "chat_bot",
    }

    return routes.get(msg_type, "chat_bot")


def route_after_rag(state: AgentState) -> str:
    """After RAG retrieval, decide next step."""
    msg_type = state.get("message_type", "chat")

    if msg_type in ("roleplay", "npc_dialogue"):
        return "npc_roleplay"
    if msg_type == "player_action":
        return "state_track"
    return "build_suggestion"


def route_after_npc(state: AgentState) -> str:
    """After NPC roleplay, either go to state track or suggestion."""
    msg_type = state.get("message_type", "chat")
    if msg_type == "npc_dialogue":
        return "state_track"
    return "build_suggestion"


def route_after_state(state: AgentState) -> str:
    """After state tracking, build suggestion."""
    return "build_suggestion"


def route_by_risk(state: AgentState) -> str:
    """After critic, decide whether to output or block."""
    risk = state.get("risk_level", "low")
    passed = state.get("critic_result", {}).get("passed", True)

    if not passed or risk == "high":
        state["output"] = {
            "need_kp_notify": False,
            "kp_suggestion": "",
            "public_reply": "",
            "message_type": state.get("message_type", "chat"),
            "blocked": True,
            "block_reason": "Critic rejected output (risk={})".format(risk),
        }
        return "output"

    return "output"


def build_graph() -> StateGraph:
    """Build and compile the full Phase 2 LangGraph orchestration graph."""
    workflow = StateGraph(AgentState)

    workflow.add_node("classify", node_classify)
    workflow.add_node("rag_retrieve", node_rag_retrieve)
    workflow.add_node("state_track", node_state_track)
    workflow.add_node("build_suggestion", node_build_suggestion)
    workflow.add_node("npc_roleplay", node_npc_roleplay)
    workflow.add_node("rule_lookup", node_rule_lookup)
    workflow.add_node("kp_command", node_kp_command)
    workflow.add_node("chat_bot", node_chat_bot)
    workflow.add_node("critic_check", node_critic_check)
    workflow.add_node("build_output", node_output)

    workflow.set_entry_point("classify")

    workflow.add_conditional_edges(
        "classify",
        route_by_message_type,
        {
            "rag_retrieve": "rag_retrieve",
            "rule_lookup": "rule_lookup",
            "kp_command": "kp_command",
            "chat_bot": "chat_bot",
        },
    )

    workflow.add_conditional_edges(
        "rag_retrieve",
        route_after_rag,
        {
            "npc_roleplay": "npc_roleplay",
            "state_track": "state_track",
            "build_suggestion": "build_suggestion",
        },
    )

    workflow.add_conditional_edges(
        "npc_roleplay",
        route_after_npc,
        {
            "state_track": "state_track",
            "build_suggestion": "build_suggestion",
        },
    )

    workflow.add_edge("state_track", "build_suggestion")

    workflow.add_edge("build_suggestion", "critic_check")
    workflow.add_edge("rule_lookup", "critic_check")
    workflow.add_edge("chat_bot", "critic_check")

    workflow.add_edge("kp_command", "build_output")

    workflow.add_conditional_edges(
        "critic_check",
        route_by_risk,
        {"output": "build_output"},
    )

    workflow.add_edge("build_output", END)

    # No checkpointer: AsyncSession in AgentState is not msgpack-serializable.
    # Each API call is independent — checkpointing across invocations isn't needed.
    graph = workflow.compile()
    return graph


_graph: StateGraph = None


def get_graph() -> StateGraph:
    """Get or lazily build the compiled graph (singleton)."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
