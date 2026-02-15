# Google ADK — Multi-Agent Systems

Source: https://google.github.io/adk-docs/agents/multi-agents/

## Key Concepts

### 1. Agent Hierarchy (sub_agents)
```python
# Define individual agents
greeter = LlmAgent(name="Greeter", model="gemini-2.0-flash")
task_doer = BaseAgent(name="TaskExecutor")

# Create parent agent with sub_agents
coordinator = LlmAgent(
    name="Coordinator",
    model="gemini-2.0-flash",
    description="I coordinate greetings and tasks.",
    sub_agents=[greeter, task_doer]  # ← This enables AutoFlow transfers!
)
```

### 2. Workflow Agents

**SequentialAgent** — Run agents in order:
```python
step1 = LlmAgent(name="Step1_Fetch", output_key="data")  # Saves to state['data']
step2 = LlmAgent(name="Step2_Process", instruction="Process data from {data}.")

pipeline = SequentialAgent(name="MyPipeline", sub_agents=[step1, step2])
```

**ParallelAgent** — Run agents concurrently:
```python
fetch_weather = LlmAgent(name="WeatherFetcher", output_key="weather")
fetch_news = LlmAgent(name="NewsFetcher", output_key="news")

gatherer = ParallelAgent(name="InfoGatherer", sub_agents=[fetch_weather, fetch_news])
```

**LoopAgent** — Repeat until condition:
```python
poller = LoopAgent(
    name="StatusPoller",
    max_iterations=10,
    sub_agents=[process_step, checker]
)
```

### 3. Communication Mechanisms

**a) Shared Session State**
```python
agent_A = LlmAgent(name="AgentA", output_key="capital_city")  # Saves to state
agent_B = LlmAgent(instruction="Tell me about {capital_city}.")  # Reads from state
```

**b) LLM-Driven Delegation (Agent Transfer)**
```python
booking_agent = LlmAgent(name="Booker", description="Handles flight and hotel bookings.")
info_agent = LlmAgent(name="Info", description="Provides general information.")

coordinator = LlmAgent(
    name="Coordinator",
    instruction="Delegate booking tasks to Booker and info requests to Info.",
    sub_agents=[booking_agent, info_agent]
)
# LLM generates: transfer_to_agent(agent_name='Booker')
# ADK framework routes execution automatically!
```

**c) AgentTool (Explicit Invocation)**
```python
from google.adk.tools import agent_tool

image_tool = agent_tool.AgentTool(agent=image_agent)
artist_agent = LlmAgent(tools=[image_tool])  # Uses agent as a tool
```

### 4. Coordinator Pattern
```python
billing_agent = LlmAgent(name="Billing", description="Handles billing inquiries.")
support_agent = LlmAgent(name="Support", description="Handles technical support.")

coordinator = LlmAgent(
    name="HelpDeskCoordinator",
    instruction="Route: Billing for payment, Support for technical.",
    sub_agents=[billing_agent, support_agent]
)
```

## Key Takeaways

1. **Use `sub_agents`** — NOT TransferToAgentTool manually
2. **Use `output_key`** — To save agent output to state
3. **Use `description`** — So LLM knows when to route
4. **Use `{state_key}`** — In instruction to read from state
