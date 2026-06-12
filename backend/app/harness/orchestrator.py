"""Orchestrator — central message processing pipeline.

Phase 2: LangGraph orchestration.

The Orchestrator wraps a compiled LangGraph StateGraph.  Each message
flows through the graph nodes (classify → rag → suggestion → critic →
output), with conditional routing based on message type and risk level.

Usage:
    orch = Orchestrator(session)
    result = await orch.process(campaign_id, sender, content)
"""

import uuid
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.message_repo import MessageRepository
from app.harness.trace_recorder import TraceRecorder
from app.harness.agent_state import AgentState, new_state
from app.harness.graph import get_graph


class Orchestrator:
    """Message processing orchestrator — LangGraph-based (Phase 2)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.msg_repo = MessageRepository(session)
        self.trace_recorder = TraceRecorder(session)
        self._graph = get_graph()

    async def process(
        self,
        campaign_id: str,
        sender: str,
        content: str,
        *,
        dice_result: Dict[str, Any] = None,
        thread_id: str = None,
    ) -> Dict[str, Any]:
        """Process a single message through the LangGraph pipeline.

        Args:
            campaign_id: Campaign this message belongs to.
            sender: Sender display name (or QQ number).
            content: Raw message text.
            dice_result: Optional parsed dice result from dice-robot.
            thread_id: Optional LangGraph thread ID for checkpointing.
                       Defaults to a new UUID per invocation.

        Returns:
            dict with need_kp_notify, kp_suggestion, message_type, etc.
        """
        # Save message to DB
        if campaign_id:
            await self.msg_repo.create(
                campaign_id=campaign_id,
                sender=sender,
                content=content,
                msg_type="group",
                role="player",
            )

        # Start trace
        tid = thread_id or str(uuid.uuid4())
        trace_id = await self.trace_recorder.start(
            campaign_id=campaign_id,
            agent_name="orchestrator",
            input_data={
                "sender": sender,
                "content": content[:500],
                "campaign_id": campaign_id,
            },
        )

        # Build initial state
        initial: AgentState = new_state(
            campaign_id=campaign_id,
            sender=sender,
            content=content,
            session=self.session,
            dice_result=dice_result,
            trace_id=trace_id,
            thread_id=tid,
        )

        # Run the graph
        try:
            config = {"configurable": {"thread_id": tid}}
            result_state = await self._graph.ainvoke(initial, config)
        except Exception as e:
            # Graph failed — record error trace and return safe default
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

        # Extract output
        output = result_state.get("output", {})

        # Finish trace
        retrieved = {}
        if result_state.get("rag_results"):
            retrieved = {
                "fusion_method": result_state.get("rag_meta", {}).get("fusion_method"),
                "top_sources": [
                    {
                        "title": r.get("title", ""),
                        "text": (r.get("text", "") or "")[:200],
                        "score": r.get("score", 0),
                        "visibility": r.get("visibility", "player_visible"),
                    }
                    for r in result_state.get("rag_results", [])[:5]
                ],
            }

        await self.trace_recorder.finish(
            trace_id=trace_id,
            output_data={
                "message_type": result_state.get("message_type", "chat"),
                "need_kp_notify": output.get("need_kp_notify", False),
                "kp_suggestion": result_state.get("kp_suggestion", "")[:500],
                "classification": output.get("classification", {}),
            },
            retrieved_context=retrieved if retrieved else None,
            tool_calls=result_state.get("tool_calls"),
            token_count=result_state.get("token_count", 0),
        )

        return {
            "need_kp_notify": output.get("need_kp_notify", False),
            "kp_suggestion": result_state.get("kp_suggestion", ""),
            "message_type": result_state.get("message_type", "chat"),
            "classification": output.get("classification", {"message_type": result_state.get("message_type", "chat")}),
        }

    @property
    def graph(self):
        """Access the underlying LangGraph for debugging / visualization."""
        return self._graph


# Convenience function

async def process_message(
    session: AsyncSession,
    campaign_id: str,
    sender: str,
    content: str,
    **kwargs,
) -> Dict[str, Any]:
    """Process a message through the LangGraph orchestrator in one call."""
    orch = Orchestrator(session)
    return await orch.process(campaign_id, sender, content, **kwargs)
