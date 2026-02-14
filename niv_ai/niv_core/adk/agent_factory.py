"""
Niv AI Agent Factory — Powered by Google ADK.
Creates specialized agents and handles A2A delegation.
"""
import json
import frappe
from typing import List, Dict, Any
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool, TransferToAgentTool
from google.adk.models.lite_llm import LiteLlm
from niv_ai.niv_core.mcp_client import get_all_mcp_tools_cached, call_tool_fast, find_tool_server
from niv_ai.niv_core.utils import get_niv_settings

from niv_ai.niv_core.adk.discovery import DiscoveryEngine

class NivAgentFactory:
    def __init__(self, conversation_id: str = None, provider_name: str = None, model_name: str = None):
        self.conversation_id = conversation_id
        self.provider_name = provider_name
        self.model_name = model_name
        
        # Initialize ADK Model (LiteLLM adapter for multi-provider support)
        # ADK LiteLlm uses litellm internally. We prefix with provider if needed.
        full_model = model_name
        if provider_name and "/" not in model_name:
            full_model = f"{provider_name}/{model_name}"
            
        self.adk_model = LiteLlm(model_name=full_model)
        
        self.all_mcp_tools = get_all_mcp_tools_cached()
        self.adk_tools = self._convert_mcp_to_adk()

    def _convert_mcp_to_adk(self) -> Dict[str, FunctionTool]:
        """Convert all MCP tools to ADK FunctionTools."""
        adk_tools = {}
        for tool_def in self.all_mcp_tools:
            func_def = tool_def.get("function", {})
            name = func_def.get("name", "")
            if not name: continue

            description = func_def.get("description", "")
            
            def make_executor(t_name, t_doc):
                def tool_func(**kwargs):
                    server_name = find_tool_server(t_name)
                    if not server_name:
                        return f"Error: Tool {t_name} not found."
                    try:
                        result = call_tool_fast(
                            server_name=server_name,
                            tool_name=t_name,
                            arguments=kwargs
                        )
                        if isinstance(result, dict) and "content" in result:
                            return "\n".join([c.get("text", str(c)) for c in result["content"]])
                        return str(result)
                    except Exception as e:
                        return f"Error executing {t_name}: {str(e)}"
                
                tool_func.__name__ = str(t_name)
                tool_func.__doc__ = str(t_doc)
                return tool_func

            tool = FunctionTool(func=make_executor(name, description))
            adk_tools[name] = tool
        return adk_tools

    def create_coder_agent(self):
        """Specialized for DocTypes, Scripts, and UI."""
        coder_tool_names = [
            "create_document", "update_document", "delete_document", 
            "get_document", "get_doctype_info", "search_doctype", "run_python_code"
        ]
        tools = [self.adk_tools[name] for name in coder_tool_names if name in self.adk_tools]
        
        return LlmAgent(
            name="frappe_coder",
            model=self.adk_model,
            instruction=(
                "You are an expert Frappe/ERPNext developer. "
                "Your job is to create DocTypes, write Server Scripts, and build UI components. "
                "For data visualization, you can create 'Artifacts' using HTML/JS and the 'frappe-charts' library. "
                "The library is already available globally as 'frappe.Chart'. "
                "Always follow Frappe coding standards. Use get_doctype_info before modifying anything."
            ),
            tools=tools
        )

    def create_data_agent(self):
        """Specialized for Reports and Queries."""
        data_tool_names = [
            "run_database_query", "analyze_business_data", "generate_report", 
            "report_list", "list_documents", "fetch"
        ]
        tools = [self.adk_tools[name] for name in data_tool_names if name in self.adk_tools]

        return LlmAgent(
            name="data_analyst",
            model=self.adk_model,
            instruction=(
                "You are a Business Intelligence specialist for ERPNext. "
                "You analyze data, run SQL queries safely, and generate reports. "
                "Always verify table names using run_database_query (DESC commands) if unsure."
            ),
            tools=tools
        )

    def create_discovery_agent(self):
        """Specialized for System Scan and Onboarding."""
        return LlmAgent(
            name="system_discovery",
            model=self.adk_model,
            instruction=(
                "You are the System Discovery Specialist. "
                "Your job is to scan the Frappe instance and build a mental map of custom DocTypes, "
                "Workflows, and Data patterns. Always provide a clear summary of what you find."
            ),
            tools=[self.adk_tools[n] for n in ["introspect_system", "get_doctype_info"] if n in self.adk_tools]
        )

    def create_nbfc_agent(self):
        """Specialized for NBFC operations (LOS, LMS, Growth System)."""
        # Load NBFC context from discovery cache
        nbfc_ctx = {}
        try:
            cache = frappe.cache().get_value("niv_system_discovery_map")
            if cache:
                nbfc_ctx = json.loads(cache).get("nbfc_related", {})
        except Exception:
            pass

        nbfc_dt = ", ".join(nbfc_ctx.get("relevant_doctypes", ["Loan", "Borrower", "EMI"]))
        
        return LlmAgent(
            name="nbfc_specialist",
            model=self.adk_model,
            instruction=(
                "You are an expert in NBFC (Non-Banking Financial Company) operations for Growth System. "
                "You understand LOS (Loan Origination), LMS (Loan Management), and Co-Lending. "
                f"Relevant DocTypes you should know: {nbfc_dt}. "
                "Always check for specific interest calculation rules or repayment schedules before answering."
            ),
            tools=[self.adk_tools[n] for n in ["run_database_query", "list_documents", "get_doctype_info"] if n in self.adk_tools]
        )

    def create_orchestrator(self):
        """Main agent that delegates to specialists."""
        coder = self.create_coder_agent()
        data = self.create_data_agent()
        discovery = self.create_discovery_agent()
        nbfc = self.create_nbfc_agent()

        # Orchestrator tools
        universal_search = self.adk_tools.get("universal_search")
        tools = [universal_search] if universal_search else []
        
        # Transfers
        transfer_tool = TransferToAgentTool(agent_names=[coder.name, data.name, discovery.name, nbfc.name])

        return LlmAgent(
            name="niv_orchestrator",
            model=self.adk_model,
            instruction=(
                "You are Niv Orchestrator, the central brain of Niv AI. "
                "Your job is to understand the user's intent and delegate to specialized agents. "
                "If the user wants to build something, transfer to 'frappe_coder'. "
                "If the user wants data analysis or reports, transfer to 'data_analyst'. "
                "If the user is asking about system capabilities or 'Discovery', transfer to 'system_discovery'. "
                "If the user asks about Loans, Borrowers, Interest, or NBFC logic, transfer to 'nbfc_specialist'. "
                "Use 'universal_search' to find context before delegating."
            ),
            tools=tools + [transfer_tool],
            sub_agents=[coder, data, discovery, nbfc]
        )

def get_orchestrator(conversation_id: str = None, provider_name: str = None, model_name: str = None):
    settings = get_niv_settings()
    provider_name = provider_name or settings.default_provider
    model_name = model_name or settings.default_model
    
    factory = NivAgentFactory(conversation_id, provider_name, model_name)
    return factory.create_orchestrator()
