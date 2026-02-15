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

UNIVERSAL RULES:
1. NEVER hallucinate or invent data. Always use tools to get REAL data.
2. If a tool fails, explain the error and suggest alternatives.
3. Be concise but thorough. Provide actionable answers.
4. For NBFC/Growth System queries, always verify data from the database.
5. When creating DocTypes/Scripts, always verify existing structure first.
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
                        return "\n".join(text_parts)
                
                if isinstance(result, (dict, list)):
                    return json.dumps(result, default=str, ensure_ascii=False)
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
                "RULES:\n"
                "1. ALWAYS use 'get_doctype_info' before creating/modifying DocTypes.\n"
                "2. Verify existing fields before adding new ones.\n"
                "3. For HTML/charts, use 'frappe-charts' library.\n"
                "4. Return ACTUAL tool results, never mock data.\n"
                "5. If a tool fails, explain why and suggest fixes."
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
                "RULES:\n"
                "1. NEVER provide mock data. ALWAYS fetch REAL data.\n"
                "2. For unknown tables, use 'SHOW TABLES' query first.\n"
                "3. Use 'report_requirements' before 'generate_report'.\n"
                "4. For financial data: Due = total_payment - paid_amount.\n"
                "5. Always provide real numbers with source context."
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
                "RULES:\n"
                "1. ALWAYS provide REAL data from database.\n"
                "2. Due Loans: Check 'Repayment Schedule' where status != 'Cleared'.\n"
                "3. If due_amount=0 but status='Presented'/'Bounced', payment pending/failed.\n"
                "4. Use 'get_doctype_info' on 'Loan Type' for interest rules.\n"
                "5. Never invent loan numbers or amounts."
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
            "introspect_system", "get_doctype_info", "search_doctype", "list_documents",
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
                "JOB: Scan the Frappe instance and build a map of:\n"
                "- Custom DocTypes and purposes\n"
                "- Active Workflows and states\n"
                "- Data patterns and relationships\n\n"
                "Always provide clear summaries of findings."
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
                "ROUTING RULES:\n"
                "• Coding/DocTypes/Scripts → transfer to 'frappe_coder'\n"
                "• SQL/Reports/Analytics → transfer to 'data_analyst'\n"
                "• Loans/EMI/NBFC → transfer to 'nbfc_specialist'\n"
                "• System scan/discovery → transfer to 'system_discovery'\n\n"
                "WORKFLOW:\n"
                "1. Analyze user request\n"
                "2. If simple, handle directly with your tools\n"
                "3. If complex/specialized, transfer to appropriate agent\n"
                "4. After specialist returns, summarize for user\n\n"
                "STATE ACCESS:\n"
                "- {coder_result} — frappe_coder output\n"
                "- {analyst_result} — data_analyst output\n"
                "- {nbfc_result} — nbfc_specialist output\n"
                "- {discovery_result} — system_discovery output\n\n"
                "NEVER provide mock data. Use tools or transfer."
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
