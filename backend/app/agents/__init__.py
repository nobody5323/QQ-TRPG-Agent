"""ChronicleAgent Agents module.

Phase 1: direct LLM calls (no LangGraph).
Phase 2: each agent becomes a LangGraph node.

Current agents:
- classifier_agent: Message type classification (LLM-based + keyword fallback)
- (Phase 2: rag_agent, state_agent, npc_agent, plot_agent, rule_agent,
   summary_agent, critic_agent)
"""

from app.agents.classifier_agent import classifier_agent, ClassifierAgent

__all__ = [
    "classifier_agent", "ClassifierAgent",
]
