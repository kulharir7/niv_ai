"""
Niv AI A2A Agents — Correct Google ADK Implementation

Key Patterns:
1. Every agent has `description` — used by parent for routing
2. Every agent has `output_key` — saves response to session state
3. Parent uses `sub_agents` — ADK automatically enables transfers
4. NO TransferToAgentTool — that's wrong!
"""

from niv_ai.niv_core.a2a.agents.factory import NivAgentFactory, get_orchestrator

__all__ = ["NivAgentFactory", "get_orchestrator"]
