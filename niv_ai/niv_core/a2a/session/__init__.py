"""
Niv AI A2A Session Service — MariaDB Persistence

Key Features:
- Sessions persist across requests (unlike InMemorySessionService)
- State shared between agents via session.state
- Uses existing Niv Conversation DocType + Redis cache
"""

from niv_ai.niv_core.a2a.session.frappe_session import (
    FrappeSessionService,
    get_session_service,
)

__all__ = ["FrappeSessionService", "get_session_service"]
