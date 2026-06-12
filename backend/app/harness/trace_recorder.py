"""Trace Recorder — records each message processing lifecycle.

Writes to the agent_traces table:
- Input message
- Classification result
- Retrieved context (top RAG chunks)
- Generated output/suggestion
- Tool calls
- Latency and token count

Phase 2 will add Critic result recording.
"""

import time
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.trace_repo import TraceRepository


class TraceRecorder:
    """Records message processing traces to agent_traces table.

    Usage:
        recorder = TraceRecorder(session)
        trace_id = await recorder.start(campaign_id, agent_name, input_data)
        # ... do work ...
        await recorder.finish(trace_id, output_data, retrieved_context, latency_ms)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TraceRepository(session)
        # In-memory map of trace_id -> start_time (for latency calculation)
        self._starts: Dict[str, float] = {}

    async def start(
        self,
        campaign_id: str,
        agent_name: str,
        input_data: Dict[str, Any],
    ) -> str:
        """Record the start of a trace. Returns trace ID."""
        trace = await self.repo.create(
            campaign_id=campaign_id,
            agent_name=agent_name,
            input_data=input_data,
            output_data={},
            retrieved_context={},
            tool_calls=[],
            critic_result={},
            latency_ms=0,
            token_count=0,
        )
        self._starts[trace.id] = time.time()
        return trace.id

    async def finish(
        self,
        trace_id: str,
        output_data: Dict[str, Any],
        retrieved_context: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[str]] = None,
        token_count: int = 0,
    ) -> None:
        """Complete a trace with output and timing."""
        elapsed = time.time() - self._starts.pop(trace_id, time.time())
        latency_ms = int(elapsed * 1000)

        await self.repo.update(
            trace_id,
            output_data=output_data,
            retrieved_context=retrieved_context or {},
            tool_calls=tool_calls or [],
            latency_ms=latency_ms,
            token_count=token_count,
        )

    async def record(
        self,
        campaign_id: str,
        agent_name: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        retrieved_context: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[str]] = None,
        token_count: int = 0,
        latency_ms: Optional[int] = None,
    ) -> str:
        """One-shot record: create a complete trace in a single call.

        Use this when you don't need the start/finish split pattern.
        """
        trace = await self.repo.create(
            campaign_id=campaign_id,
            agent_name=agent_name,
            input_data=input_data,
            output_data=output_data,
            retrieved_context=retrieved_context or {},
            tool_calls=tool_calls or [],
            critic_result={},
            latency_ms=latency_ms or 0,
            token_count=token_count,
        )
        return trace.id


def record_decorator(agent_name: str):
    """Decorator that wraps an async function with trace recording.

    Usage:
        @record_decorator("classifier")
        async def my_func(session, input_data):
            ...
            return output_data
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        async def wrapper(session: AsyncSession, *args, **kwargs):
            recorder = TraceRecorder(session)
            # Build input data from args
            input_data = {"args": str(args[:2]), "kwargs": {k: str(v)[:200] for k, v in kwargs.items()}}
            trace_id = await recorder.start(
                campaign_id=kwargs.get("campaign_id", ""),
                agent_name=agent_name,
                input_data=input_data,
            )
            try:
                result = await func(session, *args, **kwargs)
                await recorder.finish(
                    trace_id=trace_id,
                    output_data={"result": str(result)[:500]},
                )
                return result
            except Exception as e:
                await recorder.finish(
                    trace_id=trace_id,
                    output_data={"error": str(e)[:500]},
                )
                raise
        return wrapper
    return decorator
