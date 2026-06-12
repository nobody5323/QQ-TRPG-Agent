"""ChronicleAgent Agents module (Phase 2: LangGraph nodes).

Each agent is a LangGraph node with signature (state: AgentState) -> AgentState.

Agents (Steps 9-13):
  - classifier_agent: Message type classification (LLM few-shot + keyword fallback)
  - llm_factory: Multi-model LLM abstraction layer
  - state_agent: Game state tracking with dice-aware branching + Player State
  - rag_agent: RAG retrieval as agent node with dice-aware strategy
  - npc_agent: NPC roleplay dialogue generation
  - chat_agent: Persona-based casual chat responder
  - plot_agent: Plot deviation detection
  - rule_agent: COC rules lookup and dice check suggestion
  - branch_writer: KP-triggered story branch generation
  - critic_agent: Safety check on all agent outputs
"""

from app.agents.classifier_agent import ClassifierAgent, classifier_agent
from app.agents.llm_factory import LLMFactory, ModelConfig, llm_factory
from app.agents.state_agent import StateTrackingAgent, state_tracking_agent
from app.agents.npc_agent import NPCAgent, npc_agent
from app.agents.chat_agent import ChatAgent, chat_agent
from app.agents.plot_agent import PlotAgent, plot_agent
from app.agents.rule_agent import RuleAgent, rule_agent
from app.agents.branch_writer import BranchWriter, branch_writer
from app.agents.critic_agent import CriticAgent, critic_agent

__all__ = [
    "ClassifierAgent", "classifier_agent",
    "LLMFactory", "ModelConfig", "llm_factory",
    "StateTrackingAgent", "state_tracking_agent",
    "NPCAgent", "npc_agent",
    "ChatAgent", "chat_agent",
    "PlotAgent", "plot_agent",
    "RuleAgent", "rule_agent",
    "BranchWriter", "branch_writer",
    "CriticAgent", "critic_agent",
]
