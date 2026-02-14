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
        provider = frappe.get_doc("Niv AI Provider", provider_name)
        api_key = provider.get_password("api_key")
        
        from google.adk.models.lite_llm import LiteLlm
        
        # Determine provider type for LiteLLM
        # For custom OpenAI compatible (like ollama-cloud), use 'openai/' prefix
        model_id = model_name
        if "openai" not in provider_name.lower() and "anthropic" not in provider_name.lower() and "google" not in provider_name.lower():
            if not model_id.startswith("openai/"):
                model_id = f"openai/{model_id}"
        
        self.adk_model = LiteLlm(
            model=model_id,
            api_key=api_key,
            api_base=provider.base_url
        )
        
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
                "CRITICAL: Never hallucinate or provide mock data. If you need to know about a DocType, use 'get_doctype_info'. "
                "Your job is to create DocTypes, write Server Scripts, and build UI components. "
                "For data visualization, use 'frappe-charts' library in HTML artifacts. "
                "Always verify existing fields before adding new ones."
            ),
            tools=tools
        )

    def create_data_agent(self):
        """Specialized for Reports and Queries."""
        data_tool_names = [
            "run_database_query", "analyze_business_data", "generate_report", 
            "report_list", "list_documents", "fetch", "get_document"
        ]
        tools = [self.adk_tools[name] for name in data_tool_names if name in self.adk_tools]

        return LlmAgent(
            name="data_analyst",
            model=self.adk_model,
            instruction=(
                "You are a Business Intelligence specialist. "
                "CRITICAL: Never provide mock or example data. You MUST use 'run_database_query' or 'list_documents' to fetch real data from the system. "
                "If a table name is unknown, use 'run_database_query' with 'SHOW TABLES' or 'DESC'. "
                "Always provide real numbers from the database."
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
                "You are an expert in NBFC operations for Growth System. "
                f"Relevant DocTypes: {nbfc_dt}. "
                "CRITICAL: Do not invent loan numbers or amounts. Use 'list_documents' or 'run_database_query' to find real borrower records. "
                "Always check interest calculation rules using 'get_doctype_info' on 'Loan Type' or similar."
            ),
            tools=[self.adk_tools[n] for n in ["run_database_query", "list_documents", "get_doctype_info", "get_document"] if n in self.adk_tools]
        )

    def create_orchestrator(self):
        """Main agent that delegates to specialists."""
        coder = self.create_coder_agent()
        data = self.create_data_agent()
        discovery = self.create_discovery_agent()
        nbfc = self.create_nbfc_agent()

        # Orchestrator tools: allow basic discovery and reading
        orc_tool_names = ["universal_search", "list_documents", "get_doctype_info"]
        tools = [self.adk_tools[n] for n in orc_tool_names if n in self.adk_tools]
        
        # Transfers
        transfer_tool = TransferToAgentTool(agent_names=[coder.name, data.name, discovery.name, nbfc.name])

        return LlmAgent(
            name="niv_orchestrator",
            model=self.adk_model,
            instruction=(
                "You are Niv Orchestrator. "
                "CRITICAL: Never provide mock data. If the user asks for data, you MUST either use your tools or transfer to a specialist. "
                "- For Coding/DocTypes: transfer to 'frappe_coder'. "
                "- For complex SQL/Reports: transfer to 'data_analyst'. "
                "- For NBFC/Loan specific queries: transfer to 'nbfc_specialist'. "
                "- For System logic/Workflows: transfer to 'system_discovery'. "
                "Always use 'universal_search' if the request is vague."
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
