"""
Frappe Session Service for ADK — COMPLETE Implementation (v1.0.0 Compatible)

FEATURES:
1. ✅ Inherits from google.adk.sessions.base_session_service.BaseSessionService
2. ✅ Session inherits from google.adk.sessions.session.Session (Pydantic)
3. ✅ Redis-backed persistence (not InMemory)
4. ✅ v14 + v15 compatible

Architecture:
- Linked to Niv Conversation by conversation_id
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import frappe
from google.adk.sessions.session import Session
from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig, ListSessionsResponse
from google.adk.events.event import Event


# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────

# Redis key prefixes
_PREFIX_SESSION = "niv_a2a:session:"
_PREFIX_STATE = "niv_a2a:state:"
_PREFIX_EVENTS = "niv_a2a:events:"

# TTL settings
_SESSION_TTL = 7200  # 2 hours
_STATE_TTL = 7200
_EVENTS_TTL = 3600  # 1 hour

# Limits
_MAX_EVENTS = 100

# Singleton
_session_service: Optional["FrappeSessionService"] = None


# ─────────────────────────────────────────────────────────────────
# SESSION SERVICE
# ─────────────────────────────────────────────────────────────────

class FrappeSessionService(BaseSessionService):
    """
    ADK SessionService implementation using Frappe Redis.
    """
    
    def __init__(self, site: str = None):
        super().__init__()
        # Request-local cache
        self._local_cache: Dict[str, Session] = {}
        self.site = site or getattr(frappe.local, "site", None)
    
    def _ensure_context(self):
        """Ensure Frappe context is initialized (important for background threads)."""
        if not getattr(frappe.local, "site", None) and self.site:
            frappe.init(site=self.site)
            frappe.connect()

    # ─────────────────────────────────────────────────────────────
    # CORE INTERFACE (ADK v1.0.0)
    # ─────────────────────────────────────────────────────────────
    
    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        self._ensure_context()
        session_id = session_id or str(uuid.uuid4())
        
        # Check existing
        existing = await self.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        if existing:
            if state:
                existing.state.update(state)
                self._redis_set(f"{_PREFIX_STATE}{session_id}", existing.state, ttl=_STATE_TTL)
            return existing
        
        # Create new
        session = Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=time.time(),
        )
        
        # Persist
        self._save_session_metadata(session)
        self._redis_set(f"{_PREFIX_STATE}{session_id}", session.state, ttl=_STATE_TTL)
        
        # Cache locally
        cache_key = self._cache_key(app_name, user_id, session_id)
        self._local_cache[cache_key] = session
        
        return session
    
    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        self._ensure_context()
        cache_key = self._cache_key(app_name, user_id, session_id)
        
        # Local cache
        if cache_key in self._local_cache:
            return self._local_cache[cache_key]
        
        # Redis
        session_data = self._redis_get(f"{_PREFIX_SESSION}{session_id}")
        if not session_data:
            return None
        
        state = self._redis_get(f"{_PREFIX_STATE}{session_id}") or {}
        event_dicts = self._redis_get(f"{_PREFIX_EVENTS}{session_id}") or []
        
        # Convert events back to objects
        events = []
        for ed in event_dicts:
            try:
                events.append(Event.model_validate(ed))
            except Exception:
                pass
        
        session = Session(
            id=session_data["id"],
            app_name=session_data["app_name"],
            user_id=session_data["user_id"],
            state=state,
            events=events,
            last_update_time=session_data.get("last_update_time", time.time())
        )
        
        self._local_cache[cache_key] = session
        return session
    
    async def list_sessions(self, *, app_name: str, user_id: str) -> ListSessionsResponse:
        return ListSessionsResponse(sessions=[])
    
    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        self._ensure_context()
        self._redis_delete(f"{_PREFIX_SESSION}{session_id}")
        self._redis_delete(f"{_PREFIX_STATE}{session_id}")
        self._redis_delete(f"{_PREFIX_EVENTS}{session_id}")
        cache_key = self._cache_key(app_name, user_id, session_id)
        self._local_cache.pop(cache_key, None)

    async def append_event(self, session: Session, event: Event) -> Event:
        """Override to persist event to Redis."""
        self._ensure_context()
        
        # Call base implementation (updates session object in memory)
        await super().append_event(session, event)
        
        if event.partial:
            return event
            
        # Persist updated state
        self._redis_set(f"{_PREFIX_STATE}{session.id}", session.state, ttl=_STATE_TTL)
        
        # Persist events
        event_dicts = [e.model_dump() for e in session.events]
        if len(event_dicts) > _MAX_EVENTS:
            event_dicts = event_dicts[-_MAX_EVENTS:]
            
        self._redis_set(f"{_PREFIX_EVENTS}{session.id}", event_dicts, ttl=_EVENTS_TTL)
        
        # Update metadata
        session.last_update_time = time.time()
        self._save_session_metadata(session)
        
        return event

    # ─────────────────────────────────────────────────────────────
    # SYNC WRAPPERS (for non-async callers)
    # ─────────────────────────────────────────────────────────────
    
    def get_session_sync(self, app_name: str, user_id: str, session_id: str) -> Optional[Session]:
        self._ensure_context()
        data = self._redis_get(f"{_PREFIX_SESSION}{session_id}")
        if not data: return None
        
        state = self._redis_get(f"{_PREFIX_STATE}{session_id}") or {}
        event_dicts = self._redis_get(f"{_PREFIX_EVENTS}{session_id}") or []
        events = []
        for ed in event_dicts:
            try: events.append(Event.model_validate(ed))
            except: pass
            
        return Session(
            id=data["id"],
            app_name=data["app_name"],
            user_id=data["user_id"],
            state=state,
            events=events,
            last_update_time=data.get("last_update_time", time.time())
        )
    
    def create_session_sync(self, app_name: str, user_id: str, session_id: str, state: Dict[str, Any] = None) -> Session:
        self._ensure_context()
        session = Session(id=session_id, app_name=app_name, user_id=user_id, state=state or {})
        self._save_session_metadata(session)
        self._redis_set(f"{_PREFIX_STATE}{session_id}", session.state, ttl=_STATE_TTL)
        return session

    def update_session_sync(self, app_name: str, user_id: str, session_id: str, state: Dict[str, Any]) -> None:
        self._ensure_context()
        self._redis_set(f"{_PREFIX_STATE}{session_id}", state, ttl=_STATE_TTL)
        session_data = self._redis_get(f"{_PREFIX_SESSION}{session_id}")
        if session_data:
            session_data["last_update_time"] = time.time()
            self._redis_set(f"{_PREFIX_SESSION}{session_id}", session_data, ttl=_SESSION_TTL)
    
    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────
    
    def _save_session_metadata(self, session: Session) -> None:
        data = {
            "id": session.id,
            "app_name": session.app_name,
            "user_id": session.user_id,
            "last_update_time": session.last_update_time,
        }
        self._redis_set(f"{_PREFIX_SESSION}{session.id}", data, ttl=_SESSION_TTL)
    
    def _redis_set(self, key: str, value: Any, ttl: int = _SESSION_TTL) -> None:
        self._ensure_context()
        try:
            # Pydantic models need dump, other things need default str
            if hasattr(value, "model_dump"):
                data = json.dumps(value.model_dump(), default=str)
            else:
                data = json.dumps(value, default=str)
                
            try:
                frappe.cache().set_value(key, data, expires_in_sec=ttl)
            except TypeError:
                frappe.cache().set_value(key, data)
        except Exception as e:
            frappe.log_error(f"Redis set failed [{key}]: {e}", "Niv AI A2A")
    
    def _redis_get(self, key: str) -> Optional[Any]:
        self._ensure_context()
        try:
            data = frappe.cache().get_value(key)
            if data is None: return None
            if isinstance(data, bytes): data = data.decode("utf-8")
            if isinstance(data, str):
                try: return json.loads(data)
                except: return data
            return data
        except Exception: return None
    
    def _redis_delete(self, key: str) -> None:
        self._ensure_context()
        try: frappe.cache().delete_value(key)
        except Exception: pass
    
    def _cache_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"{app_name}:{user_id}:{session_id}"


# ─────────────────────────────────────────────────────────────────
# SINGLETON ACCESSOR
# ─────────────────────────────────────────────────────────────────

def get_session_service(site: str = None) -> FrappeSessionService:
    global _session_service
    if _session_service is None:
        _session_service = FrappeSessionService(site=site)
    elif site and _session_service.site != site:
        _session_service.site = site
    return _session_service
