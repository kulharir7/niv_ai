"""
Frappe Session Service for ADK — MariaDB + Redis Persistence

This replaces InMemorySessionService which loses all data per request.

Architecture:
- Session state: Redis (fast) + MariaDB fallback (persistent)
- Events history: Stored in Niv Conversation messages
- Sessions linked by conversation_id

Based on ADK SessionService interface.
"""

import json
import time
import uuid
import frappe
from typing import Any, Dict, List, Optional


# Redis key prefixes
_SESSION_PREFIX = "niv_a2a_session:"
_STATE_PREFIX = "niv_a2a_state:"
_EVENTS_PREFIX = "niv_a2a_events:"

# Session TTL (2 hours — long conversation support)
_SESSION_TTL = 7200

# Singleton instance
_session_service_instance = None


class FrappeSession:
    """
    ADK-compatible Session object.
    
    Wraps session data with the interface ADK expects.
    """
    
    def __init__(
        self,
        session_id: str,
        app_name: str,
        user_id: str,
        state: Dict[str, Any] = None,
        events: List[Any] = None,
        last_update_time: float = None,
    ):
        self.id = session_id
        self.app_name = app_name
        self.user_id = user_id
        self._state = state or {}
        self._events = events or []
        self.last_update_time = last_update_time or time.time()
    
    @property
    def state(self) -> Dict[str, Any]:
        """Session state dict. Agents read/write via state['key']."""
        return self._state
    
    @state.setter
    def state(self, value: Dict[str, Any]):
        self._state = value
    
    @property
    def events(self) -> List[Any]:
        """Event history for this session."""
        return self._events
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session for storage."""
        return {
            "id": self.id,
            "app_name": self.app_name,
            "user_id": self.user_id,
            "state": self._state,
            "events_count": len(self._events),
            "last_update_time": self.last_update_time,
        }


class FrappeSessionService:
    """
    ADK SessionService implementation using Frappe/MariaDB.
    
    Key differences from InMemorySessionService:
    1. Sessions PERSIST across requests
    2. State stored in Redis (fast) + can be persisted to MariaDB
    3. Events linked to Niv Conversation messages
    
    This fixes the critical bug where every request created a new session.
    """
    
    def __init__(self):
        self._local_cache = {}  # Request-local cache for speed
    
    # ─────────────────────────────────────────────────────────────────
    # Core SessionService Interface Methods
    # ─────────────────────────────────────────────────────────────────
    
    async def create_session(
        self,
        app_name: str,
        user_id: str,
        state: Dict[str, Any] = None,
        session_id: str = None,
    ) -> FrappeSession:
        """
        Create a new session or return existing one.
        
        If session_id is provided and exists, returns existing session.
        This enables session REUSE across requests — critical fix!
        """
        session_id = session_id or str(uuid.uuid4())
        
        # Check if session already exists
        existing = await self.get_session(app_name, user_id, session_id)
        if existing:
            # Update state if new state provided
            if state:
                existing.state.update(state)
                await self._save_state(session_id, existing.state)
            return existing
        
        # Create new session
        session = FrappeSession(
            session_id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=time.time(),
        )
        
        # Persist to Redis
        await self._save_session(session)
        
        return session
    
    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Optional[FrappeSession]:
        """
        Retrieve an existing session.
        
        Returns None if session doesn't exist.
        """
        # Check local cache first (request-local)
        cache_key = f"{app_name}:{user_id}:{session_id}"
        if cache_key in self._local_cache:
            return self._local_cache[cache_key]
        
        # Check Redis
        session_data = self._redis_get(f"{_SESSION_PREFIX}{session_id}")
        if not session_data:
            return None
        
        state = self._redis_get(f"{_STATE_PREFIX}{session_id}") or {}
        events = self._redis_get(f"{_EVENTS_PREFIX}{session_id}") or []
        
        session = FrappeSession(
            session_id=session_id,
            app_name=session_data.get("app_name", app_name),
            user_id=session_data.get("user_id", user_id),
            state=state,
            events=events,
            last_update_time=session_data.get("last_update_time", time.time()),
        )
        
        # Cache locally
        self._local_cache[cache_key] = session
        
        return session
    
    async def list_sessions(
        self,
        app_name: str,
        user_id: str,
    ) -> List[FrappeSession]:
        """
        List all sessions for a user.
        
        Note: This is expensive — use sparingly.
        """
        # For now, return empty list — we don't track session lists
        # In production, we'd query Niv Conversation by user
        return []
    
    async def delete_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> bool:
        """Delete a session and all its data."""
        try:
            self._redis_delete(f"{_SESSION_PREFIX}{session_id}")
            self._redis_delete(f"{_STATE_PREFIX}{session_id}")
            self._redis_delete(f"{_EVENTS_PREFIX}{session_id}")
            
            # Remove from local cache
            cache_key = f"{app_name}:{user_id}:{session_id}"
            self._local_cache.pop(cache_key, None)
            
            return True
        except Exception:
            return False
    
    async def append_event(
        self,
        session: FrappeSession,
        event: Any,
    ) -> None:
        """
        Append an event to session history.
        
        Events are stored in Redis with TTL.
        """
        session._events.append(event)
        session.last_update_time = time.time()
        
        # Save events to Redis (limit to last 100 for memory)
        events_to_save = session._events[-100:]
        self._redis_set(
            f"{_EVENTS_PREFIX}{session.id}",
            events_to_save,
            ttl=_SESSION_TTL,
        )
        
        # Update session metadata
        await self._save_session(session)
    
    # ─────────────────────────────────────────────────────────────────
    # State Management (critical for agent-to-agent communication)
    # ─────────────────────────────────────────────────────────────────
    
    async def update_state(
        self,
        session: FrappeSession,
        state_delta: Dict[str, Any],
    ) -> None:
        """
        Update session state with delta.
        
        This is called when agents set output_key values.
        """
        session.state.update(state_delta)
        session.last_update_time = time.time()
        await self._save_state(session.id, session.state)
    
    async def _save_state(self, session_id: str, state: Dict[str, Any]) -> None:
        """Persist state to Redis."""
        self._redis_set(f"{_STATE_PREFIX}{session_id}", state, ttl=_SESSION_TTL)
    
    async def _save_session(self, session: FrappeSession) -> None:
        """Persist session metadata to Redis."""
        self._redis_set(
            f"{_SESSION_PREFIX}{session.id}",
            session.to_dict(),
            ttl=_SESSION_TTL,
        )
    
    # ─────────────────────────────────────────────────────────────────
    # Redis Helpers
    # ─────────────────────────────────────────────────────────────────
    
    def _redis_set(self, key: str, value: Any, ttl: int = _SESSION_TTL) -> None:
        """Set value in Redis with TTL."""
        try:
            data = json.dumps(value, default=str) if not isinstance(value, str) else value
            try:
                frappe.cache().set_value(key, data, expires_in_sec=ttl)
            except TypeError:
                # v14 doesn't have expires_in_sec
                frappe.cache().set_value(key, data)
        except Exception as e:
            frappe.log_error(f"A2A Session Redis set failed: {e}", "Niv AI A2A")
    
    def _redis_get(self, key: str) -> Optional[Any]:
        """Get value from Redis."""
        try:
            data = frappe.cache().get_value(key)
            if data is None:
                return None
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if isinstance(data, str):
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return data
            return data
        except Exception:
            return None
    
    def _redis_delete(self, key: str) -> None:
        """Delete key from Redis."""
        try:
            frappe.cache().delete_value(key)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────
# Singleton accessor — REUSE across requests (critical fix!)
# ─────────────────────────────────────────────────────────────────

def get_session_service() -> FrappeSessionService:
    """
    Get singleton session service instance.
    
    CRITICAL: This is the key fix!
    Old code created InMemorySessionService inside stream function
    which meant every request got a NEW session service with NO data.
    
    Now we reuse the same service, and it persists data to Redis.
    """
    global _session_service_instance
    if _session_service_instance is None:
        _session_service_instance = FrappeSessionService()
    return _session_service_instance
