# Google ADK — Session & State Management

Source: https://google.github.io/adk-docs/sessions/

## Session Object

```python
session = await session_service.create_session(
    app_name="my_app",
    user_id="user123",
    state={"initial_key": "value"}
)

print(session.id)              # Unique session ID
print(session.app_name)        # Application name
print(session.user_id)         # User identifier
print(session.state)           # Current state dict
print(session.events)          # Conversation history
print(session.last_update_time) # Last activity
```

## SessionService Types

### 1. InMemorySessionService (Testing Only!)
```python
from google.adk.sessions import InMemorySessionService
session_service = InMemorySessionService()
# ⚠️ Data LOST on restart!
```

### 2. DatabaseSessionService (Production)
```python
from google.adk.sessions import DatabaseSessionService
db_url = "sqlite+aiosqlite:///./my_agent_data.db"
session_service = DatabaseSessionService(db_url=db_url)
# ✅ Data persists!
```

### 3. VertexAiSessionService (Google Cloud)
```python
from google.adk.sessions import VertexAiSessionService
session_service = VertexAiSessionService(project=PROJECT_ID, location=LOCATION)
```

---

## State Management

### State Prefixes (Scope)

| Prefix | Scope | Persistence |
|--------|-------|-------------|
| (none) | Current session | Session lifetime |
| `user:` | User across sessions | Persistent |
| `app:` | App-wide (all users) | Persistent |
| `temp:` | Current invocation only | Discarded after |

```python
session.state['task_status'] = 'active'           # Session state
session.state['user:preferred_language'] = 'fr'   # User state
session.state['app:global_discount'] = 'SAVE10'   # App state
session.state['temp:raw_api_response'] = {...}    # Temporary (discarded)
```

### Accessing State in Instructions

```python
agent = LlmAgent(
    instruction="Write a story about {topic}."  # Reads state['topic']
)
```

### Updating State

**Method 1: output_key (Easiest)**
```python
agent = LlmAgent(
    name="Greeter",
    output_key="last_greeting"  # Saves response to state['last_greeting']
)
```

**Method 2: EventActions.state_delta**
```python
state_changes = {
    "task_status": "active",
    "user:login_count": 1,
}
actions = EventActions(state_delta=state_changes)
event = Event(author="system", actions=actions)
await session_service.append_event(session, event)
```

**Method 3: Context (In Tools/Callbacks)**
```python
def my_tool(context: ToolContext):
    context.state["user_action_count"] = 1  # Auto-tracked!
```

### ⚠️ WARNING: Never Do This!
```python
# ❌ WRONG - Bypasses event tracking
session = await session_service.get_session(...)
session.state['key'] = 'value'  # NOT SAVED!
```

---

## Key Takeaways

1. **InMemorySessionService = Testing only** — Use DatabaseSessionService for production
2. **Use `output_key`** — Easiest way to save agent output
3. **Use state prefixes** — `user:`, `app:`, `temp:` for proper scoping
4. **Use `{var}` in instruction** — To inject state values
5. **Never modify session.state directly** — Use context or EventActions
