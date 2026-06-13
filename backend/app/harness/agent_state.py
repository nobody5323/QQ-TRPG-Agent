"""AgentState — the shared state object flowing through LangGraph nodes.

Every LangGraph node receives this state, reads what it needs,
and returns an updated copy (immutable dict semantics).

This is the single source of truth for a single message-processing
invocation.  All eight Phase-2 Agents operate on subsets of this state.
"""

from typing import TypedDict, Optional, List, Dict, Any
try:
    from typing import NotRequired  # Python 3.11+
except ImportError:
    from typing_extensions import NotRequired  # Python 3.10


class AgentState(TypedDict, total=False):
    """State flowing through the message-processing LangGraph.

    Fields are grouped by which agent / stage owns them.  Because this
    is a TypedDict with `total=False`, every field is optional —
    nodes only populate the fields they're responsible for.
    """

    # Input (set by graph entry point)
    campaign_id: str
    sender: str
    content: str
    message: str
    session: Any

    # Classifier output
    message_type: str
    confidence: float
    need_rag: bool
    need_kp_suggestion: bool
    need_state_update: bool
    reasoning: str

    # RAG retrieval output
    rag_results: List[Dict[str, Any]]
    rag_meta: Dict[str, Any]

    # Campaign context
    current_state: Dict[str, Any]
    context: Dict[str, Any]

    # Dice result (parsed from dice-robot)
    dice_result: Optional[Dict[str, Any]]

    # Player state
    player_states: Dict[str, Dict[str, Any]]

    # Suggestion / Action
    suggested_action: str
    kp_suggestion: str
    public_reply: str

    # Critic output
    critic_result: Dict[str, Any]
    risk_level: str

    # Output
    output: Dict[str, Any]
    need_kp_notify: bool
    error: Optional[str]

    # Trace
    trace_id: str
    node_timings: Dict[str, float]
    tool_calls: List[str]
    token_count: int


def new_state(
    campaign_id: str = "",
    sender: str = "",
    content: str = "",
    **kwargs,
) -> AgentState:
    """Create a minimal AgentState with sane defaults."""
    s: AgentState = {
        "campaign_id": campaign_id,
        "sender": sender,
        "content": content,
        "message": content,
        "message_type": "chat",
        "confidence": 0.0,
        "need_rag": False,
        "need_kp_suggestion": False,
        "need_state_update": False,
        "reasoning": "",
        "rag_results": [],
        "rag_meta": {},
        "current_state": {},
        "context": {},
        "dice_result": None,
        "player_states": {},
        "suggested_action": "",
        "kp_suggestion": "",
        "public_reply": "",
        "critic_result": {},
        "risk_level": "low",
        "output": {},
        "need_kp_notify": False,
        "error": None,
        "trace_id": "",
        "node_timings": {},
        "tool_calls": [],
        "token_count": 0,
    }
    s.update(kwargs)
    return s
