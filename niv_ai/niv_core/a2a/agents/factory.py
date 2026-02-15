"""
Niv AI Agent Factory — COMPLETE Google ADK Implementation

Based on official ADK samples:
- https://github.com/google/adk-samples/tree/main/python/agents/travel-concierge
- https://github.com/google/adk-samples/tree/main/python/agents/data-science

FEATURES IMPLEMENTED:
1. ✅ sub_agents for hierarchy (NOT TransferToAgentTool)
2. ✅ description for routing decisions
3. ✅ output_key for state sharing
4. ✅ disallow_transfer_to_parent — specialist stays focused
5. ✅ disallow_transfer_to_peers — no sibling confusion
6. ✅ global_instruction — common context
7. ✅ generate_content_config — temperature control
8. ✅ before_agent_callback — state initialization
9. ✅ Proper Frappe context in tool executor
"""

import json
from datetime import date
from typing import Dict, List, Any, Optional

import frappe
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import FunctionTool
from google.adk.models.lite_llm import LiteLlm
from google.genai.types import GenerateContentConfig

from niv_ai.niv_core.mcp_client import (
    get_all_mcp_tools_cached,
    call_tool_fast,
    find_tool_server,
)
from niv_ai.niv_core.utils import get_niv_settings


# ─────────────────────────────────────────────────────────────────
# GLOBAL INSTRUCTION — Common context for all agents
# ─────────────────────────────────────────────────────────────────

GLOBAL_INSTRUCTION = f"""
You are part of Niv AI — an intelligent assistant for Frappe/ERPNext systems.
Today's date: {date.today()}

🚨 CRITICAL — REAL DATA ONLY 🚨

ABSOLUTE RULES (ZERO TOLERANCE):
1. NEVER invent, assume, or hallucinate ANY data — not even as examples.
2. ALWAYS use MCP tools to fetch REAL data from the database.
3. If a tool fails → say "Tool failed: [error]" — DO NOT make up alternative data.
4. If no data exists → say "No records found" — DO NOT create mock records.
5. Numbers, names, dates, amounts — ALL must come from tool results.
6. NEVER say "for example" or "let's assume" with fake data.
7. If you don't have real data, ASK the user or run a tool.

WORKFLOW:
1. User asks question → Run appropriate tool
2. Tool returns data → Use ONLY that data in response
3. Tool fails/empty → Report failure honestly, suggest next steps
4. NEVER fill gaps with imagination

For NBFC/Growth System: Every loan number, amount, date, borrower name MUST be real.
"""


# ─────────────────────────────────────────────────────────────────
# CALLBACKS — State initialization
# ─────────────────────────────────────────────────────────────────

def init_agent_state(callback_context: CallbackContext) -> None:
    """
    Initialize state before agent runs.
    
    Called via before_agent_callback — ensures state is ready.
    From: data-science sample pattern.
    """
    state = callback_context.state
    
    # Initialize result placeholders if not present
    if "coder_result" not in state:
        state["coder_result"] = ""
    if "analyst_result" not in state:
        state["analyst_result"] = ""
    if "nbfc_result" not in state:
        state["nbfc_result"] = ""
    if "discovery_result" not in state:
        state["discovery_result"] = ""
    if "orchestrator_result" not in state:
        state["orchestrator_result"] = ""
    
    # Load NBFC context if available
    if "nbfc_context" not in state:
        try:
            cache = frappe.cache().get_value("niv_system_discovery_map")
            if cache:
                data = json.loads(cache) if isinstance(cache, str) else cache
                state["nbfc_context"] = data.get("nbfc_related", {})
        except Exception:
            state["nbfc_context"] = {}


# ─────────────────────────────────────────────────────────────────
# GENERATE CONTENT CONFIG — Temperature control
# ─────────────────────────────────────────────────────────────────

# Low temperature for consistent, factual responses
FACTUAL_CONFIG = GenerateContentConfig(temperature=0.1, top_p=0.8)

# Medium temperature for creative tasks (code generation)
CREATIVE_CONFIG = GenerateContentConfig(temperature=0.3, top_p=0.9)

# Very low for strict routing decisions
ROUTING_CONFIG = GenerateContentConfig(temperature=0.05, top_p=0.5)


# ─────────────────────────────────────────────────────────────────
# AGENT FACTORY
# ─────────────────────────────────────────────────────────────────

class NivAgentFactory:
    """
    Creates ADK agents with COMPLETE official patterns.
    
    Every specialist agent has:
    - description — for parent routing
    - output_key — for state sharing
    - disallow_transfer_to_parent — stay focused
    - disallow_transfer_to_peers — no sibling confusion
    - generate_content_config — temperature control
    """

    def __init__(
        self,
        conversation_id: str = None,
        provider_name: str = None,
        model_name: str = None,
    ):
        self.conversation_id = conversation_id
        self.provider_name = provider_name
        self.model_name = model_name
        
        # Store site name for tool execution context
        self.site = getattr(frappe.local, "site", None) or frappe.local.site
        
        # Initialize ADK model via LiteLLM (multi-provider support)
        self.adk_model = self._init_model(provider_name, model_name)
        
        # Load and convert MCP tools to ADK format
        self.all_mcp_tools = get_all_mcp_tools_cached()
        self.adk_tools = self._convert_mcp_to_adk()
        
        # Add Native Knowledge Graph Tool
        self.adk_tools["get_system_knowledge_graph"] = FunctionTool(
            func=self._make_knowledge_graph_tool()
        )

    def _make_knowledge_graph_tool(self):
        """Native tool to fetch the pre-built knowledge graph."""
        def get_system_knowledge_graph() -> str:
            try:
                cache = frappe.cache().get_value("niv_system_knowledge_graph")
                if not cache:
                    from niv_ai.niv_core.knowledge.system_map import update_knowledge_graph
                    cache = json.dumps(update_knowledge_graph())
                return cache
            except Exception as e:
                return f"Error fetching graph: {e}"
        
        get_system_knowledge_graph.__name__ = "get_system_knowledge_graph"
        get_system_knowledge_graph.__doc__ = "Returns a JSON map of all DocTypes and their relationships (Links/Tables)."
        return get_system_knowledge_graph

    def _init_model(self, provider_name: str, model_name: str) -> LiteLlm:
        """Initialize ADK model with LiteLLM adapter."""
        settings = get_niv_settings()
        provider_name = provider_name or settings.default_provider
        model_name = model_name or settings.default_model
        
        provider = frappe.get_doc("Niv AI Provider", provider_name)
        api_key = provider.get_password("api_key")
        
        # Determine provider type for LiteLLM
        # For custom OpenAI compatible (like ollama-cloud), use 'openai/' prefix
        model_id = model_name
        provider_lower = provider_name.lower()
        if not any(p in provider_lower for p in ("openai", "anthropic", "google", "gemini")):
            if not model_id.startswith("openai/"):
                model_id = f"openai/{model_id}"
        
        return LiteLlm(
            model=model_id,
            api_key=api_key,
            api_base=provider.base_url,
        )

    def _convert_mcp_to_adk(self) -> Dict[str, FunctionTool]:
        """
        Convert MCP tools to ADK FunctionTools.
        
        Proper Frappe context initialization in tool executor.
        """
        adk_tools = {}
        
        for tool_def in self.all_mcp_tools:
            func_def = tool_def.get("function", {})
            name = func_def.get("name", "")
            if not name:
                continue
            
            description = func_def.get("description", name)
            
            tool = FunctionTool(
                func=self._make_tool_executor(name, description)
            )
            adk_tools[name] = tool
        
        return adk_tools

    def _make_tool_executor(self, tool_name: str, tool_description: str):
        """
        Create tool executor with proper Frappe context handling.
        
        CRITICAL: ADK runs tools in ThreadPoolExecutor.
        Must re-init Frappe context in each tool call.
        """
        site = self.site  # Capture at creation time
        
        def execute_tool(**kwargs) -> str:
            # Re-initialize Frappe context (ADK runs in thread pool)
            try:
                if not getattr(frappe.local, "site", None):
                    frappe.init(site=site)
                    frappe.connect()
                else:
                    # Verify DB connection is alive
                    try:
                        frappe.db.sql("SELECT 1")
                    except Exception:
                        frappe.db.connect()
            except Exception as e:
                return json.dumps({
                    "error": f"Frappe context init failed: {e}",
                    "recovery_hint": "Try again or use a different tool."
                })
            
            # Find MCP server
            server_name = find_tool_server(tool_name)
            if not server_name:
                return json.dumps({
                    "error": f"Tool '{tool_name}' not found in any MCP server.",
                    "recovery_hint": "Check tool name spelling or use 'introspect_system' to list available tools."
                })
            
            try:
                result = call_tool_fast(
                    server_name=server_name,
                    tool_name=tool_name,
                    arguments=kwargs,
                )
                
                # Extract text from MCP response
                if isinstance(result, dict) and "content" in result:
                    contents = result["content"]
                    if isinstance(contents, list):
                        text_parts = []
                        for c in contents:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text_parts.append(c.get("text", ""))
                            elif isinstance(c, dict):
                                text_parts.append(json.dumps(c, default=str))
                            else:
                                text_parts.append(str(c))
                        final_text = "\n".join(text_parts)
                        
                        # Guard: Mark empty results clearly
                        if not final_text.strip() or final_text.strip() in ("[]", "{}", "null", "None"):
                            return json.dumps({
                                "result": "EMPTY",
                                "message": f"Tool '{tool_name}' returned no data.",
                                "instruction": "Report 'No data found' to user. DO NOT invent data."
                            })
                        return final_text
                
                if isinstance(result, (dict, list)):
                    json_str = json.dumps(result, default=str, ensure_ascii=False)
                    # Guard: Mark empty results clearly
                    if json_str in ("[]", "{}", "null"):
                        return json.dumps({
                            "result": "EMPTY",
                            "message": f"Tool '{tool_name}' returned empty result.",
                            "instruction": "Report 'No records found' to user. DO NOT invent data."
                        })
                    return json_str
                return str(result)
                
            except Exception as e:
                frappe.log_error(f"A2A Tool '{tool_name}' failed: {e}", "Niv AI A2A")
                return json.dumps({
                    "error": f"Tool '{tool_name}' failed: {str(e)}",
                    "recovery_hint": self._get_recovery_hint(tool_name, str(e))
                })
        
        execute_tool.__name__ = str(tool_name)
        execute_tool.__doc__ = str(tool_description)
        return execute_tool

    def _get_recovery_hint(self, tool_name: str, error: str) -> str:
        """Generate recovery hints for common errors."""
        err = error.lower()
        
        if "permission" in err:
            return "User may not have access. Try 'run_database_query' with SELECT."
        if "not found" in err:
            return "Record/DocType not found. Use 'search_documents' or 'list_documents' first."
        if "timeout" in err:
            return "Query too slow. Reduce limit or use simpler filters."
        if "required" in err or "mandatory" in err:
            return "Missing required fields. Use 'get_doctype_info' to see required fields."
        
        return "Try a different approach or break into smaller steps."

    def _get_tools(self, tool_names: List[str]) -> List[FunctionTool]:
        """Get ADK tools by name."""
        return [self.adk_tools[n] for n in tool_names if n in self.adk_tools]

    # ─────────────────────────────────────────────────────────────
    # SPECIALIST AGENTS
    # ─────────────────────────────────────────────────────────────

    def create_coder_agent(self) -> LlmAgent:
        """
        Frappe/ERPNext Development Specialist.
        
        From travel-concierge pattern: sub-agent with full control flags.
        """
        tool_names = [
            "create_document", "update_document", "delete_document",
            "get_document", "get_doctype_info", "search_doctype", "run_python_code",
        ]
        
        return LlmAgent(
            name="frappe_coder",
            model=self.adk_model,
            
            # ROUTING: Parent reads this to decide transfer
            description=(
                "EXPERT Frappe/ERPNext developer. "
                "Handles: DocType creation, Server Scripts, Client Scripts, "
                "Custom Fields, Workflows, Print Formats, Web Forms. "
                "DO NOT use for data queries or NBFC operations."
            ),
            
            instruction=(
                "You are an expert Frappe/ERPNext developer.\n\n"
                "🚨 REAL DATA ONLY:\n"
                "1. Before creating ANYTHING → run 'get_doctype_info' to see what exists.\n"
                "2. Before modifying → run 'get_document' to fetch current state.\n"
                "3. Tool results are your ONLY source of truth.\n"
                "4. If tool says 'DocType not found' → it doesn't exist. Period.\n"
                "5. NEVER describe hypothetical fields — only actual fields from tool.\n\n"
                "WORKFLOW:\n"
                "- Create DocType? First: get_doctype_info → see structure.\n"
                "- Add field? First: get_document → see existing fields.\n"
                "- Modify? First: fetch current → then update."
            ),
            
            # STATE: Save output for orchestrator to read
            output_key="coder_result",
            
            # CONTROL: Stay focused, don't transfer back mid-task
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            
            # TEMPERATURE: Slightly creative for code generation
            generate_content_config=CREATIVE_CONFIG,
            
            tools=self._get_tools(tool_names),
        )

    def create_analyst_agent(self) -> LlmAgent:
        """
        Data Analysis & Reports Specialist.
        """
        tool_names = [
            "run_database_query", "generate_report", "report_list",
            "report_requirements", "list_documents", "fetch", "get_document",
        ]
        
        return LlmAgent(
            name="data_analyst",
            model=self.adk_model,
            
            description=(
                "Business Intelligence and Data Analysis specialist. "
                "Handles: SQL queries, reports, data aggregation, analytics, dashboards. "
                "DO NOT use for development or NBFC-specific loan operations."
            ),
            
            instruction=(
                "You are a Business Intelligence specialist.\n\n"
                "🚨 REAL DATA ONLY — ZERO MOCK DATA:\n"
                "1. EVERY number you mention MUST come from a tool result.\n"
                "2. If asked for counts/totals → run SQL query first.\n"
                "3. If asked for reports → run report tool first.\n"
                "4. NEVER say 'approximately' or 'around X' without real data.\n"
                "5. If tool fails → say 'Query failed' — don't invent numbers.\n\n"
                "WORKFLOW:\n"
                "- Unknown tables? Run: SELECT table_name FROM information_schema.tables\n"
                "- Need count? Run: SELECT COUNT(*) FROM tabXXX\n"
                "- Always show the query you ran and its result."
            ),
            
            output_key="analyst_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=FACTUAL_CONFIG,
            
            tools=self._get_tools(tool_names),
        )

    def create_nbfc_agent(self) -> LlmAgent:
        """
        NBFC/Lending Operations Specialist for Growth System.
        """
        tool_names = [
            "run_database_query", "list_documents", "get_doctype_info",
            "get_document", "search_documents",
        ]
        
        return LlmAgent(
            name="nbfc_specialist",
            model=self.adk_model,
            
            description=(
                "NBFC operations expert for Growth System. "
                "Handles: Loan applications, EMI schedules, repayment tracking, "
                "borrower info, disbursements, LOS, LMS, interest calculations, "
                "due loans, overdue recovery. "
                "DO NOT use for general development or non-NBFC queries."
            ),
            
            instruction=(
                "You are an NBFC operations expert for Growth System.\n\n"
                "NBFC CONTEXT (from state):\n"
                "- Known DocTypes: {nbfc_context}\n\n"
                "🚨 REAL DATA ONLY — STRICT MODE:\n"
                "1. Loan numbers, borrower names, amounts → MUST be from tool results.\n"
                "2. Before answering ANY loan question → run list_documents or run_database_query.\n"
                "3. Due Loans: SELECT * FROM `tabRepayment Schedule` WHERE status != 'Cleared'\n"
                "4. NEVER say 'Loan XYZ-001' unless that exact ID came from database.\n"
                "5. If no loan data found → say 'No loans found' — don't make up loans.\n"
                "6. EMI amounts, interest rates → MUST be queried, not assumed.\n\n"
                "EXAMPLE BAD (NEVER DO):\n"
                "'Customer ABC has 5 loans...' ← WHERE DID THIS COME FROM?\n\n"
                "EXAMPLE GOOD:\n"
                "'Running query... Found 3 loans: [actual IDs from result]'"
            ),
            
            output_key="nbfc_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=FACTUAL_CONFIG,
            
            tools=self._get_tools(tool_names),
        )

    def create_discovery_agent(self) -> LlmAgent:
        """
        System Discovery & Introspection Specialist.
        """
        tool_names = [
            "get_system_knowledge_graph", "introspect_system", "get_doctype_info", "search_doctype", "list_documents",
        ]
        
        return LlmAgent(
            name="system_discovery",
            model=self.adk_model,
            
            description=(
                "System Discovery specialist. "
                "Handles: System scanning, DocType discovery, workflow analysis, "
                "data structure understanding, onboarding. "
                "DO NOT use for development, reports, or NBFC operations."
            ),
            
            instruction=(
                "You are the System Discovery Specialist.\n\n"
                "🚨 REAL DATA ONLY:\n"
                "1. Run 'get_system_knowledge_graph' FIRST to see the full relationship map.\n"
                "2. Use 'introspect_system' for a high-level overview if the graph is too large.\n"
                "3. DocType names and relationships → MUST come from the graph or tool results.\n"
                "4. NEVER guess connections — if the graph shows a Link, mention it.\n\n"
                "JOB: Scan Frappe instance and report ACTUAL findings using the Knowledge Graph:\n"
                "- Map of Custom DocTypes and their modules\n"
                "- Link relationships (e.g. Loan links to Customer)\n"
                "- Active Workflows and their states\n\n"
                "Your goal is to be the 'brain' that understands how everything is connected."
            ),
            
            output_key="discovery_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=FACTUAL_CONFIG,
            
            tools=self._get_tools(tool_names),
        )

    # ─────────────────────────────────────────────────────────────
    # ORCHESTRATOR
    # ─────────────────────────────────────────────────────────────

    def create_orchestrator(self) -> LlmAgent:
        """
        Main Orchestrator — routes to specialists.
        
        Uses sub_agents (NOT TransferToAgentTool).
        ADK automatically enables transfers based on descriptions.
        """
        # Create all specialists
        coder = self.create_coder_agent()
        analyst = self.create_analyst_agent()
        nbfc = self.create_nbfc_agent()
        discovery = self.create_discovery_agent()
        
        # Orchestrator's own tools (lightweight)
        orc_tool_names = ["universal_search", "list_documents", "get_doctype_info"]
        
        return LlmAgent(
            name="niv_orchestrator",
            model=self.adk_model,
            
            description=(
                "Main coordinator that routes requests to specialist agents."
            ),
            
            # COMMON CONTEXT for all agents
            global_instruction=GLOBAL_INSTRUCTION,
            
            instruction=(
                "You are Niv AI Orchestrator.\n\n"
                "🚨 REAL DATA POLICY:\n"
                "EVERY response with data MUST come from tool execution.\n"
                "If you don't know → run a tool or transfer to specialist.\n"
                "NEVER guess, assume, or provide example data.\n\n"
                "ROUTING RULES:\n"
                "• Coding/DocTypes/Scripts → transfer to 'frappe_coder'\n"
                "• SQL/Reports/Analytics → transfer to 'data_analyst'\n"
                "• Loans/EMI/NBFC → transfer to 'nbfc_specialist'\n"
                "• System scan/discovery → transfer to 'system_discovery'\n\n"
                "WORKFLOW:\n"
                "1. User asks for data → Run tool OR transfer to specialist\n"
                "2. Get tool result → Use ONLY that result in response\n"
                "3. Tool failed? → Say 'Tool failed' — don't make up data\n"
                "4. Specialist returned? → Use their {output_key} result\n\n"
                "STATE ACCESS:\n"
                "- {coder_result} — frappe_coder output\n"
                "- {analyst_result} — data_analyst output\n"
                "- {nbfc_result} — nbfc_specialist output\n"
                "- {discovery_result} — system_discovery output"
            ),
            
            output_key="orchestrator_result",
            
            # STATE INIT
            before_agent_callback=init_agent_state,
            
            # ROUTING TEMPERATURE: Very low for consistent decisions
            generate_content_config=ROUTING_CONFIG,
            
            tools=self._get_tools(orc_tool_names),
            
            # HIERARCHY: ADK enables transfers automatically
            sub_agents=[coder, analyst, nbfc, discovery],
        )


# ─────────────────────────────────────────────────────────────────
# FACTORY FUNCTION
# ─────────────────────────────────────────────────────────────────

def get_orchestrator(
    conversation_id: str = None,
    provider_name: str = None,
    model_name: str = None,
) -> LlmAgent:
    """
    Get the main orchestrator agent.
    
    Usage:
        from niv_ai.niv_core.a2a import get_orchestrator
        
        orchestrator = get_orchestrator(conversation_id="conv123")
        # Use with ADK Runner
    """
    factory = NivAgentFactory(
        conversation_id=conversation_id,
        provider_name=provider_name,
        model_name=model_name,
    )
    return factory.create_orchestrator()
