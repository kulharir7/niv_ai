"""
Niv AI Agent Factory — CORRECT Google ADK Implementation

CHANGES FROM OLD (WRONG) VERSION:
1. ❌ REMOVED: TransferToAgentTool — ADK handles via sub_agents
2. ✅ ADDED: description to ALL agents — required for routing
3. ✅ ADDED: output_key to ALL agents — required for state sharing
4. ✅ FIXED: Tool executor with proper Frappe context

Based on: https://google.github.io/adk-docs/agents/multi-agents/
"""

import json
import frappe
from typing import Dict, List, Any

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.lite_llm import LiteLlm

from niv_ai.niv_core.mcp_client import (
    get_all_mcp_tools_cached,
    call_tool_fast,
    find_tool_server,
)
from niv_ai.niv_core.utils import get_niv_settings


class NivAgentFactory:
    """
    Creates ADK agents with CORRECT patterns:
    - description for routing
    - output_key for state sharing
    - sub_agents for hierarchy (NO TransferToAgentTool!)
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
        
        Key fix: Proper Frappe context initialization in tool executor.
        """
        adk_tools = {}
        
        for tool_def in self.all_mcp_tools:
            func_def = tool_def.get("function", {})
            name = func_def.get("name", "")
            if not name:
                continue
            
            description = func_def.get("description", name)
            
            # Create closure with captured variables
            tool = FunctionTool(
                func=self._make_tool_executor(name, description)
            )
            adk_tools[name] = tool
        
        return adk_tools

    def _make_tool_executor(self, tool_name: str, tool_description: str):
        """
        Create tool executor function with proper Frappe context handling.
        
        FIX: Always re-init Frappe in ThreadPoolExecutor context.
        """
        site = self.site  # Capture at creation time
        
        def execute_tool(**kwargs) -> str:
            # Re-initialize Frappe context (ADK may run tools in thread pool)
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
                return f"Error initializing Frappe context: {e}"
            
            # Find which MCP server hosts this tool
            server_name = find_tool_server(tool_name)
            if not server_name:
                return f"Error: Tool '{tool_name}' not found in any MCP server."
            
            try:
                # Call MCP tool
                result = call_tool_fast(
                    server_name=server_name,
                    tool_name=tool_name,
                    arguments=kwargs,
                )
                
                # Extract text from MCP response format
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
                
                # Ensure string return
                if isinstance(result, (dict, list)):
                    return json.dumps(result, default=str, ensure_ascii=False)
                return str(result)
                
            except Exception as e:
                frappe.log_error(f"A2A Tool '{tool_name}' failed: {e}", "Niv AI A2A")
                return f"Error executing {tool_name}: {str(e)}"
        
        # Set function metadata for ADK
        execute_tool.__name__ = str(tool_name)
        execute_tool.__doc__ = str(tool_description)
        
        return execute_tool

    def _get_tools_for_agent(self, tool_names: List[str]) -> List[FunctionTool]:
        """Get ADK tools by name."""
        return [self.adk_tools[name] for name in tool_names if name in self.adk_tools]

    # ─────────────────────────────────────────────────────────────────
    # SPECIALIST AGENTS — Each has description + output_key
    # ─────────────────────────────────────────────────────────────────

    def create_coder_agent(self) -> LlmAgent:
        """
        Frappe/ERPNext Development Specialist.
        
        Handles: DocTypes, Scripts, Custom Fields, Workflows, Print Formats.
        """
        tool_names = [
            "create_document",
            "update_document",
            "delete_document",
            "get_document",
            "get_doctype_info",
            "search_doctype",
            "run_python_code",
        ]
        
        return LlmAgent(
            name="frappe_coder",
            model=self.adk_model,
            
            # CRITICAL: Description for parent to route correctly
            description=(
                "EXPERT Frappe/ERPNext developer. "
                "USE THIS AGENT FOR: Creating DocTypes, Server Scripts, Client Scripts, "
                "Custom Fields, Workflows, Print Formats, Web Forms, and any code/development tasks. "
                "DO NOT use for data queries, reports, or NBFC-specific operations."
            ),
            
            instruction=(
                "You are an expert Frappe/ERPNext developer.\n\n"
                "CRITICAL RULES:\n"
                "1. NEVER hallucinate or provide mock data.\n"
                "2. ALWAYS use 'get_doctype_info' before creating/modifying DocTypes to verify field names.\n"
                "3. For data visualization, use 'frappe-charts' library in HTML artifacts.\n"
                "4. Verify existing fields before adding new ones.\n"
                "5. Return the ACTUAL result from tools, not made-up data."
            ),
            
            # CRITICAL: Save output to state for other agents to read
            output_key="coder_result",
            
            tools=self._get_tools_for_agent(tool_names),
        )

    def create_analyst_agent(self) -> LlmAgent:
        """
        Data Analysis & Reports Specialist.
        
        Handles: SQL queries, reports, data analysis, dashboards.
        """
        tool_names = [
            "run_database_query",
            "generate_report",
            "report_list",
            "report_requirements",
            "list_documents",
            "fetch",
            "get_document",
        ]
        
        return LlmAgent(
            name="data_analyst",
            model=self.adk_model,
            
            # CRITICAL: Description for routing
            description=(
                "Business Intelligence and Data Analysis specialist. "
                "USE THIS AGENT FOR: SQL queries, database reports, data aggregation, "
                "analytics, dashboards, and any data retrieval tasks. "
                "DO NOT use for code/development or NBFC-specific loan operations."
            ),
            
            instruction=(
                "You are a Business Intelligence specialist.\n\n"
                "CRITICAL RULES:\n"
                "1. NEVER provide mock or example data. You MUST fetch REAL data.\n"
                "2. For financial queries, calculate true 'Due' = total_payment - paid_amount.\n"
                "3. If a table name is unknown, use 'run_database_query' with 'SHOW TABLES'.\n"
                "4. Always provide REAL numbers from the database.\n"
                "5. Use 'report_requirements' before 'generate_report' to know required filters."
            ),
            
            output_key="analyst_result",
            
            tools=self._get_tools_for_agent(tool_names),
        )

    def create_nbfc_agent(self) -> LlmAgent:
        """
        NBFC/Lending Operations Specialist.
        
        Handles: Loans, EMIs, Repayments, LOS/LMS, Growth System specific.
        """
        tool_names = [
            "run_database_query",
            "list_documents",
            "get_doctype_info",
            "get_document",
            "search_documents",
        ]
        
        # Try to load NBFC context from discovery cache
        nbfc_context = ""
        try:
            cache = frappe.cache().get_value("niv_system_discovery_map")
            if cache:
                data = json.loads(cache) if isinstance(cache, str) else cache
                nbfc_doctypes = data.get("nbfc_related", {}).get("relevant_doctypes", [])
                if nbfc_doctypes:
                    nbfc_context = f"\n\nKnown NBFC DocTypes: {', '.join(nbfc_doctypes[:15])}"
        except Exception:
            pass
        
        return LlmAgent(
            name="nbfc_specialist",
            model=self.adk_model,
            
            # CRITICAL: Description for routing
            description=(
                "NBFC (Non-Banking Financial Company) operations expert for Growth System. "
                "USE THIS AGENT FOR: Loan applications, EMI schedules, repayment tracking, "
                "borrower information, disbursements, LOS (Loan Origination), LMS (Loan Management), "
                "interest calculations, due loans, overdue recovery. "
                "DO NOT use for general development or non-NBFC reports."
            ),
            
            instruction=(
                "You are an expert in NBFC operations for Growth System.\n\n"
                f"{nbfc_context}\n\n"
                "CRITICAL RULES:\n"
                "1. ALWAYS provide REAL data. Never invent loan numbers or amounts.\n"
                "2. For 'Due Loans': Check 'Repayment Schedule' DocType.\n"
                "3. A loan entry is 'Due' if total_payment > 0 and status is NOT 'Cleared'.\n"
                "4. If due_amount is 0.0 but status is 'Presented'/'Bounced', payment is pending/failed.\n"
                "5. Use 'get_doctype_info' on 'Loan Type' to understand interest calculation rules."
            ),
            
            output_key="nbfc_result",
            
            tools=self._get_tools_for_agent(tool_names),
        )

    def create_discovery_agent(self) -> LlmAgent:
        """
        System Discovery & Introspection Specialist.
        
        Handles: System scanning, DocType discovery, workflow analysis.
        """
        tool_names = [
            "introspect_system",
            "get_doctype_info",
            "search_doctype",
            "list_documents",
        ]
        
        return LlmAgent(
            name="system_discovery",
            model=self.adk_model,
            
            # CRITICAL: Description for routing
            description=(
                "System Discovery and Introspection specialist. "
                "USE THIS AGENT FOR: Scanning the system, discovering custom DocTypes, "
                "analyzing workflows, understanding data structures, onboarding tasks, "
                "and learning about the ERPNext instance configuration. "
                "DO NOT use for development, reports, or NBFC operations."
            ),
            
            instruction=(
                "You are the System Discovery Specialist.\n\n"
                "Your job is to scan the Frappe instance and build a mental map of:\n"
                "- Custom DocTypes and their purposes\n"
                "- Active Workflows and their states\n"
                "- Data patterns and relationships\n\n"
                "Always provide a clear summary of what you find."
            ),
            
            output_key="discovery_result",
            
            tools=self._get_tools_for_agent(tool_names),
        )

    # ─────────────────────────────────────────────────────────────────
    # ORCHESTRATOR — Routes to specialists using sub_agents
    # ─────────────────────────────────────────────────────────────────

    def create_orchestrator(self) -> LlmAgent:
        """
        Main Orchestrator Agent.
        
        Routes requests to specialist agents using sub_agents.
        NO TransferToAgentTool — ADK handles transfers automatically!
        """
        # Create specialist agents
        coder = self.create_coder_agent()
        analyst = self.create_analyst_agent()
        nbfc = self.create_nbfc_agent()
        discovery = self.create_discovery_agent()
        
        # Orchestrator's own tools (lightweight discovery/search)
        orc_tool_names = [
            "universal_search",
            "list_documents",
            "get_doctype_info",
        ]
        
        return LlmAgent(
            name="niv_orchestrator",
            model=self.adk_model,
            
            # CRITICAL: Clear description
            description=(
                "Main coordinator that routes user requests to specialist agents. "
                "Handles general queries directly or delegates to specialists."
            ),
            
            instruction=(
                "You are Niv AI Orchestrator — the main coordinator.\n\n"
                "ROUTING RULES:\n"
                "- Coding/DocTypes/Scripts → transfer to 'frappe_coder'\n"
                "- SQL/Reports/Analytics → transfer to 'data_analyst'\n"
                "- Loans/EMI/NBFC/Growth System → transfer to 'nbfc_specialist'\n"
                "- System scanning/discovery → transfer to 'system_discovery'\n\n"
                "CRITICAL:\n"
                "1. NEVER provide mock data. Always use tools or transfer to specialists.\n"
                "2. If request is vague, use 'universal_search' first.\n"
                "3. For complex queries, transfer to the appropriate specialist.\n"
                "4. After specialist returns, summarize the result for the user.\n\n"
                "You can read results from specialists via state:\n"
                "- {coder_result} — frappe_coder's last output\n"
                "- {analyst_result} — data_analyst's last output\n"
                "- {nbfc_result} — nbfc_specialist's last output\n"
                "- {discovery_result} — system_discovery's last output"
            ),
            
            output_key="orchestrator_result",
            
            tools=self._get_tools_for_agent(orc_tool_names),
            
            # CRITICAL: This is how ADK knows about child agents!
            # NO TransferToAgentTool needed — ADK automatically enables transfers
            sub_agents=[coder, analyst, nbfc, discovery],
        )


# ─────────────────────────────────────────────────────────────────
# Factory function (convenience)
# ─────────────────────────────────────────────────────────────────

def get_orchestrator(
    conversation_id: str = None,
    provider_name: str = None,
    model_name: str = None,
) -> LlmAgent:
    """
    Get the main orchestrator agent.
    
    Usage:
        orchestrator = get_orchestrator(conversation_id="conv123")
    """
    factory = NivAgentFactory(
        conversation_id=conversation_id,
        provider_name=provider_name,
        model_name=model_name,
    )
    return factory.create_orchestrator()
