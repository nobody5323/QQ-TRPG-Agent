"""Orchestrator — central message processing pipeline.

Message flow:
  1. Save message to DB
  2. Build campaign context (ContextManager)
  3. Classify message (ClassifierAgent)
  4. If needed: RAG retrieval
  5. Build suggestion
  6. Record trace (TraceRecorder)
  7. Return result

Phase 1: direct function calls (no LangGraph).
Phase 2: replaced with LangGraph orchestration graph.
"""

from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.message_repo import MessageRepository
from app.harness.context_manager import ContextManager, build_rag_context
from app.harness.trace_recorder import TraceRecorder
from app.agents.classifier_agent import classifier_agent
from app.rag.retriever import retriever


class Orchestrator:
    """Message processing orchestrator."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.msg_repo = MessageRepository(session)
        self.context_mgr = ContextManager(session)
        self.trace_recorder = TraceRecorder(session)

    async def process(
        self,
        campaign_id: str,
        sender: str,
        content: str,
    ) -> Dict[str, Any]:
        """Process a single message through the full pipeline.

        Args:
            campaign_id: Campaign this message belongs to
            sender: Sender display name
            content: Message text

        Returns:
            dict with:
            - need_kp_notify: whether to notify KP
            - kp_suggestion: suggestion text for KP
            - message_type: classified type
            - classification: full classification result
        """
        trace_id = await self.trace_recorder.start(
            campaign_id=campaign_id,
            agent_name="orchestrator",
            input_data={
                "sender": sender,
                "content": content[:500],
                "campaign_id": campaign_id,
            },
        )

        try:
            # 1. Save message to DB
            if campaign_id:
                await self.msg_repo.create(
                    campaign_id=campaign_id,
                    sender=sender,
                    content=content,
                    msg_type="group",
                    role="player",
                )

            # 2. Build context
            context = await self.context_mgr.build(campaign_id)

            # 3. Classify message
            recent_text = "\n".join(
                "{}: {}".format(m["sender"], m["content"])
                for m in context["recent_messages"][-5:]
            )
            active_scene_name = (
                context["active_scene"]["name"]
                if context["active_scene"] else None
            )
            npc_names = ", ".join(n["name"] for n in context["active_npcs"])

            classification = await classifier_agent.classify(
                message=content,
                recent_context=recent_text,
                active_scene=active_scene_name or "unknown",
                npc_names=npc_names or "none",
            )

            msg_type = classification["message_type"]
            need_rag = classification["need_rag"]
            need_suggestion = classification["need_kp_suggestion"]
            need_state_update = classification["need_state_update"]

            # 4. RAG retrieval (if needed)
            kp_suggestion = ""
            retrieved = {}
            tool_calls = []
            search_result = {"results": [], "meta": {}}

            if need_rag and campaign_id:
                rag_ctx = await build_rag_context(self.session, campaign_id)
                tool_calls.append("rag_search")

                search_result = await retriever.search(
                    query=content,
                    campaign_id=campaign_id,
                    scene_context=rag_ctx.get("scene_name"),
                    active_npcs=rag_ctx.get("npc_names"),
                    undiscovered_clue_names=rag_ctx.get("undiscovered_clue_names"),
                    top_k=5,
                )

                meta = search_result.get("meta", {})
                results = search_result.get("results", [])

                retrieved = {
                    "fusion_method": meta.get("fusion_method", "unknown"),
                    "vector_count": meta.get("vector_count", 0),
                    "keyword_count": meta.get("keyword_count", 0),
                    "latency_ms": meta.get("latency_ms", 0),
                    "top_sources": [
                        {
                            "title": r.get("payload", {}).get("title", ""),
                            "text": (r.get("payload", {}).get("text", "") or "")[:200],
                            "score": r.get("rerank_score", r.get("score", 0)),
                            "visibility": r.get("payload", {}).get("visibility", "player_visible"),
                        }
                        for r in results[:5]
                    ],
                }

            # 5. Build suggestion
            if need_suggestion and campaign_id:
                kp_suggestion = self._build_suggestion(
                    sender=sender,
                    content=content,
                    msg_type=msg_type,
                    context=context,
                    results=search_result.get("results", []),
                    meta=search_result.get("meta", {}),
                )

            # 6. Record trace
            output_data = {
                "message_type": msg_type,
                "need_kp_notify": need_suggestion,
                "kp_suggestion": kp_suggestion[:500] if kp_suggestion else "",
                "classification": classification,
            }

            await self.trace_recorder.finish(
                trace_id=trace_id,
                output_data=output_data,
                retrieved_context=retrieved if need_rag else None,
                tool_calls=tool_calls if tool_calls else None,
            )

            return {
                "need_kp_notify": need_suggestion,
                "kp_suggestion": kp_suggestion,
                "message_type": msg_type,
                "classification": classification,
            }

        except Exception as e:
            await self.trace_recorder.finish(
                trace_id=trace_id,
                output_data={"error": str(e)[:500]},
            )
            return {
                "need_kp_notify": False,
                "kp_suggestion": "",
                "message_type": "chat",
                "classification": {"message_type": "chat"},
            }

    def _build_suggestion(
        self,
        sender: str,
        content: str,
        msg_type: str,
        context: Dict[str, Any],
        results: list,
        meta: dict,
    ) -> str:
        """Build a KP suggestion from classification + RAG results."""
        parts = []

        type_labels = {
            "player_action": "Player Action Detected",
            "roleplay": "Roleplay",
            "rule_question": "Rule Question",
            "chat": "Chat",
            "kp_command": "KP Command",
        }
        parts.append("[{}]".format(type_labels.get(msg_type, "Message")))
        parts.append("From: {}".format(sender))
        parts.append("Msg: {}".format(content))
        parts.append("")

        scene = context.get("active_scene")
        if scene:
            parts.append("Scene: {}".format(scene["name"]))
            if scene.get("summary"):
                parts.append("  {}".format(scene["summary"][:200]))

        npcs = context.get("active_npcs", [])
        if npcs:
            names = [n["name"] for n in npcs]
            parts.append("NPCs: {}".format(", ".join(names)))

        if results:
            lat = meta.get("latency_ms", "?")
            parts.append("")
            parts.append("Module ({}ms):".format(lat))
            for i, r in enumerate(results[:3], 1):
                payload = r.get("payload", {}) or {}
                text = (payload.get("text", "") or "")[:200]
                title = payload.get("title", "") or ""
                vis = payload.get("visibility", "player_visible")
                tag = " [KP Only]" if vis == "kp_only" else ""
                prefix = "[{}]".format(title) if title else ""
                parts.append("{}. {}{}".format(i, prefix, tag))
                parts.append("   {}".format(text))

        if context.get("undiscovered_clues"):
            names = [c["name"] for c in context["undiscovered_clues"][:5]]
            parts.append("")
            parts.append("Undiscovered: {}".format(", ".join(names)))

        return "\n".join(parts)


async def process_message(
    session: AsyncSession,
    campaign_id: str,
    sender: str,
    content: str,
) -> Dict[str, Any]:
    """Process a message through orchestrator in one call."""
    orch = Orchestrator(session)
    return await orch.process(campaign_id, sender, content)
