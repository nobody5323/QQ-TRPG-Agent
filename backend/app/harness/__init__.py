"""ChronicleAgent Harness — message processing pipeline (Phase 2: LangGraph).

Pipeline:
  1. ContextManager — assembles campaign state (scene/NPC/clues/messages)
  2. Orchestrator — LangGraph-based dispatcher
  3. AgentState — shared state flowing through graph nodes
  4. Graph — compiled LangGraph StateGraph with 10 nodes
  5. TraceRecorder — records each message lifecycle to agent_traces table
  6. PermissionManager — filters output by visibility tier
"""

from app.harness.orchestrator import Orchestrator, process_message
from app.harness.context_manager import ContextManager, build_context, build_rag_context
from app.harness.trace_recorder import TraceRecorder
from app.harness.agent_state import AgentState, new_state
from app.harness.graph import get_graph, build_graph
from app.harness.permission_manager import PermissionManager, permission_manager

__all__ = [
    "Orchestrator", "process_message",
    "ContextManager", "build_context", "build_rag_context",
    "TraceRecorder",
    "AgentState", "new_state",
    "get_graph", "build_graph",
    "PermissionManager", "permission_manager",
]
