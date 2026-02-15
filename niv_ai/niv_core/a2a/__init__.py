"""
Niv AI A2A — Agent-to-Agent System

Correct implementation using Google ADK patterns:
- sub_agents for agent hierarchy (NOT TransferToAgentTool)
- output_key for state sharing between agents
- description for routing decisions
- Persistent session service (Redis-backed)

Usage:
    from niv_ai.niv_core.a2a import stream_a2a
    
    for event in stream_a2a(message="Create a Customer DocType", conversation_id="conv123"):
        print(event)
"""

from niv_ai.niv_core.a2a.agents import get_orchestrator, NivAgentFactory
from niv_ai.niv_core.a2a.runner import stream_a2a, run_a2a_sync
from niv_ai.niv_core.a2a.session import get_session_service, FrappeSessionService
from niv_ai.niv_core.a2a.config import AGENT_NAMES, STATE_KEYS, AGENT_TOOLS

__all__ = [
    # Agents
    "get_orchestrator",
    "NivAgentFactory",
    # Runner
    "stream_a2a",
    "run_a2a_sync",
    # Session
    "get_session_service",
    "FrappeSessionService",
    # Config
    "AGENT_NAMES",
    "STATE_KEYS",
    "AGENT_TOOLS",
]
