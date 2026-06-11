"""ChronicleAgent Harness — message processing pipeline.

Pipeline:
  1. ContextManager — assembles campaign state (scene/NPC/clues/messages)
  2. Orchestrator — central dispatcher: classify -> retrieve -> suggest -> trace
  3. TraceRecorder — records each message lifecycle to agent_traces table

Phase 1: direct function calls (no LangGraph).
Phase 2: replaced with LangGraph orchestration graph.
"""

from app.harness.orchestrator import Orchestrator, process_message
from app.harness.context_manager import ContextManager, build_context, build_rag_context
from app.harness.trace_recorder import TraceRecorder

__all__ = [
    "Orchestrator", "process_message",
    "ContextManager", "build_context", "build_rag_context",
    "TraceRecorder",
]
