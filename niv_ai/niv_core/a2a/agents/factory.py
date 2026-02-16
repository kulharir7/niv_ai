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
from google.adk.tools.tool_context import ToolContext
from google.adk.models.lite_llm import LiteLlm
from google.genai.types import GenerateContentConfig


class MCPFunctionTool(FunctionTool):
    """
    Custom FunctionTool that properly handles MCP tool arguments.
    
    ADK's FunctionTool filters arguments to match function signature,
    which breaks **kwargs. This subclass passes all arguments directly.
    """
    
    async def run_async(self, *, args: dict, tool_context: ToolContext):
        """Override to pass all args without filtering."""
        # Call our function directly with all args
        return await self._invoke_callable(self.func, args)

from niv_ai.niv_core.mcp_client import (
    get_all_mcp_tools_cached,
    call_tool_fast,
    find_tool_server,
)
from niv_ai.niv_core.utils import get_niv_settings


# ─────────────────────────────────────────────────────────────────
# GLOBAL INSTRUCTION — Minimal, fast context
# ─────────────────────────────────────────────────────────────────

GLOBAL_INSTRUCTION = f"""You are Niv AI for Frappe/ERPNext. Date: {date.today()}
RULE: Use tools for ALL data. Never invent data. If tool fails, say so."""


# ─────────────────────────────────────────────────────────────────
# CALLBACKS — State initialization & Tool result storage
# ─────────────────────────────────────────────────────────────────

def store_tool_result_in_state(
    tool,
    args: Dict[str, Any],
    tool_context,
    tool_response: Any,
) -> Optional[Dict]:
    """
    After-tool callback: Store tool results in session state.
    
    This is CRITICAL for A2A — allows agents to share data via state.
    
    Pattern from official ADK samples:
    - data-science/sub_agents/bigquery/agent.py
    - travel-concierge/sub_agents/planning/agent.py
    """
    try:
        tool_name = getattr(tool, "name", str(tool))
        
        # Store result in state with tool name as key
        result_key = f"tool_result_{tool_name}"
        
        # Convert response to string if needed
        if isinstance(tool_response, dict):
            result_str = json.dumps(tool_response, default=str, ensure_ascii=False)
        else:
            result_str = str(tool_response)
        
        # Truncate if too long (avoid state bloat)
        if len(result_str) > 5000:
            result_str = result_str[:5000] + "... (truncated)"
        
        tool_context.state[result_key] = result_str
        
        # Also store last tool result for easy access
        tool_context.state["last_tool_result"] = result_str
        tool_context.state["last_tool_name"] = tool_name
        
    except Exception as e:
        # Don't fail the tool call, just log
        try:
            frappe.log_error(f"store_tool_result_in_state error: {e}", "Niv AI A2A")
        except:
            pass
    
    # Return None to not modify the tool response
    return None


def init_agent_state(callback_context: CallbackContext) -> None:
    """
    Initialize state before agent runs. FAST version - minimal loading.
    """
    state = callback_context.state
    
    # Initialize result placeholders
    for key in ["coder_result", "analyst_result", "nbfc_result", "discovery_result", 
                "critique_result", "planner_result", "orchestrator_result"]:
        if key not in state:
            state[key] = ""
    
    # Skip heavy loading - agents can use tools to discover
    if "system_doctypes" not in state:
        state["system_doctypes"] = "Use tools to query DocTypes."
    
    if "nbfc_context" not in state:
        state["nbfc_context"] = {}
    
    if "user_memory" not in state:
        state["user_memory"] = ""
    
    if "dev_reference" not in state:
        state["dev_reference"] = ""


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
        
        # Add Native Memory Tool
        self.adk_tools["save_to_user_memory"] = FunctionTool(
            func=self._make_memory_tool()
        )

        # Add Native Planning Tools
        self.adk_tools["create_task_plan"] = FunctionTool(func=self._make_create_plan_tool())
        self.adk_tools["update_task_plan"] = FunctionTool(func=self._make_update_plan_tool())
        self.adk_tools["get_task_plan"] = FunctionTool(func=self._make_get_plan_tool())
        
        # Add Visualizer Tool
        self.adk_tools["visualize_system_map"] = FunctionTool(func=self._make_visualize_graph_tool())
        
        # Add Auditor Tool
        self.adk_tools["run_nbfc_audit"] = FunctionTool(func=self._make_auditor_tool())

    def _make_auditor_tool(self):
        """Tool to run NBFC business audits."""
        def run_nbfc_audit() -> str:
            try:
                from niv_ai.niv_core.knowledge.auditor_service import run_daily_audit
                return run_daily_audit()
            except Exception as e:
                return f"Error running audit: {e}"
        run_nbfc_audit.__name__ = "run_nbfc_audit"
        run_nbfc_audit.__doc__ = "Scans the system for overdue loans, interest mismatches, and data anomalies."
        return run_nbfc_audit

    def _make_visualize_graph_tool(self):
        """Tool to create a visual artifact of the knowledge graph."""
        def visualize_system_map() -> str:
            try:
                from niv_ai.niv_core.knowledge.system_map import get_graph_elements
                elements = get_graph_elements()
                
                # Full self-contained HTML Document (Optimized for speed)
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.26.0/cytoscape.min.js"></script>
    <style>
        body {{ margin: 0; padding: 0; background: #0f172a; overflow: hidden; font-family: sans-serif; }}
        #cy {{ width: 100vw; height: 100vh; display: block; }}
        #loading {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #8b5cf6; font-size: 14px; z-index: 10; font-weight: bold; }}
    </style>
</head>
<body>
    <div id="loading">🧠 Neural Map Loading...</div>
    <div id="cy"></div>
    <script>
        window.onload = function() {{
            try {{
                var elements = {json.dumps(elements)};
                if (!elements || elements.length === 0) {{
                    document.getElementById('loading').innerText = "No data found to map.";
                    return;
                }}

                var cy = cytoscape({{
                    container: document.getElementById('cy'),
                    elements: elements,
                    style: [
                        {{
                            selector: 'node',
                            style: {{
                                'background-color': '#7c3aed',
                                'label': 'data(label)',
                                'color': '#fff',
                                'text-valign': 'center',
                                'font-size': '10px',
                                'width': '90px',
                                'height': '30px',
                                'shape': 'round-rectangle',
                                'text-wrap': 'wrap',
                                'text-max-width': '80px'
                            }}
                        }},
                        {{
                            selector: 'edge',
                            style: {{
                                'width': 1,
                                'line-color': '#4f46e5',
                                'target-arrow-color': '#4f46e5',
                                'target-arrow-shape': 'triangle',
                                'curve-style': 'haystack',
                                'opacity': 0.6
                            }}
                        }}
                    ],
                    layout: {{
                        name: 'grid',
                        padding: 50
                    }}
                }});
                document.getElementById('loading').style.display = 'none';
            }} catch (err) {{
                document.getElementById('loading').innerText = "Error: " + err.message;
            }}
        }};
    </script>
</body>
</html>"""
                
                from niv_ai.niv_core.api.artifacts import create_artifact
                artifact_id = create_artifact(
                    title="System Knowledge Map",
                    artifact_type="Dashboard",
                    artifact_content=html_content,
                    preview_html=html_content
                )
                
                return f"SUCCESS: Interactive Graph created (ID: {artifact_id}). View in Artifacts panel."
            except Exception as e:
                return f"ERROR: {e}"
        
        visualize_system_map.__name__ = "visualize_system_map"
        visualize_system_map.__doc__ = "Creates an interactive visual map of the system DocTypes and their relationships."
        return visualize_system_map

    def _make_create_plan_tool(self):
        def create_task_plan(title: str, steps: list) -> str:
            try:
                from niv_ai.niv_core.knowledge.planner_service import PlannerService
                user = frappe.session.user
                plan_id = PlannerService.create_plan(user, title, steps)
                return f"Plan created successfully. ID: {plan_id}"
            except Exception as e:
                return f"Error creating plan: {e}"
        create_task_plan.__name__ = "create_task_plan"
        return create_task_plan

    def _make_update_plan_tool(self):
        def update_task_plan(plan_id: str, step_num: int, status: str, result: str = "") -> str:
            try:
                from niv_ai.niv_core.knowledge.planner_service import PlannerService
                PlannerService.update_step(plan_id, step_num, status, result)
                return f"Step {step_num} updated to {status}."
            except Exception as e:
                return f"Error updating plan: {e}"
        update_task_plan.__name__ = "update_task_plan"
        return update_task_plan

    def _make_get_plan_tool(self):
        def get_task_plan(plan_id: str) -> str:
            try:
                from niv_ai.niv_core.knowledge.planner_service import PlannerService
                return PlannerService.get_plan_status(plan_id)
            except Exception as e:
                return f"Error getting plan: {e}"
        get_task_plan.__name__ = "get_task_plan"
        return get_task_plan

    def _make_memory_tool(self):
        """Native tool to save something to user's long-term memory."""
        def save_to_user_memory(key: str, value: str, category: str) -> str:
            try:
                from niv_ai.niv_core.knowledge.memory_service import MemoryService
                user = frappe.session.user
                doc_name = MemoryService.save_memory(user, key, value, category)
                return f"Successfully saved to memory: {key} = {value}"
            except Exception as e:
                return f"Error saving to memory: {e}"
        
        save_to_user_memory.__name__ = "save_to_user_memory"
        save_to_user_memory.__doc__ = "Saves a user preference, habit, or fact to long-term memory. Categories: Preference, Habit, Fact, Context."
        return save_to_user_memory

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
        
        Uses MCPFunctionTool which bypasses ADK's argument filtering.
        """
        adk_tools = {}
        
        for tool_def in self.all_mcp_tools:
            func_def = tool_def.get("function", {})
            name = func_def.get("name", "")
            if not name:
                continue
            
            description = func_def.get("description", name)
            
            # Create tool with our custom MCPFunctionTool
            tool = MCPFunctionTool(
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
        
        async def execute_tool(arguments: dict) -> str:
            """Execute MCP tool."""
            # Log for debugging
            frappe.log_error(f"ADK Tool Call: {tool_name}\nArgs: {arguments}", "Niv AI Debug")
            
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
                    arguments=arguments,
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
                        
                        # Guard: Mark empty results clearly with user-friendly message
                        if not final_text.strip() or final_text.strip() in ("[]", "{}", "null", "None"):
                            friendly_msg = self._get_empty_result_message(tool_name, arguments)
                            return f"No data found. {friendly_msg}"
                        return final_text
                
                if isinstance(result, (dict, list)):
                    json_str = json.dumps(result, default=str, ensure_ascii=False)
                    # Guard: Mark empty results clearly with user-friendly message
                    if json_str in ("[]", "{}", "null"):
                        friendly_msg = self._get_empty_result_message(tool_name, arguments)
                        return f"No records found. {friendly_msg}"
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

    def _get_empty_result_message(self, tool_name: str, arguments: dict) -> str:
        """Generate user-friendly message for empty results."""
        # Extract context from arguments
        doctype = arguments.get("doctype", arguments.get("doc_type", ""))
        filters = arguments.get("filters", arguments.get("filter", ""))
        query = arguments.get("query", "")
        name = arguments.get("name", arguments.get("document_name", ""))
        
        if tool_name == "list_documents":
            if doctype:
                return f"No {doctype} records exist yet, or filters don't match any records."
            return "No documents found matching your criteria."
        
        if tool_name == "get_document":
            if doctype and name:
                return f"{doctype} '{name}' does not exist."
            return "The requested document was not found."
        
        if tool_name == "run_database_query":
            return "The query returned no results. Check table name and filters."
        
        if tool_name == "search_documents" or tool_name == "search_doctype":
            return "No matching records found. Try different search terms."
        
        if "report" in tool_name.lower():
            return "Report generated no data for the given parameters."
        
        return "The operation completed but returned no data."

    def _get_tools(self, tool_names: List[str]) -> List[FunctionTool]:
        """Get ADK tools by name."""
        return [self.adk_tools[n] for n in tool_names if n in self.adk_tools]

    # ─────────────────────────────────────────────────────────────
    # SPECIALIST AGENTS
    # ─────────────────────────────────────────────────────────────

    def create_coder_agent(self) -> LlmAgent:
        """
        Frappe/ERPNext Development Specialist.
        """
        tool_names = [
            "create_document", "update_document", "delete_document",
            "get_document", "get_doctype_info", "search_doctype", "run_python_code",
        ]
        
        return LlmAgent(
            name="frappe_coder",
            model=self.adk_model,
            
            description=(
                "Frappe developer: DocTypes, Scripts, Fields, Workflows. "
                "Use for: create/modify code, add fields, server scripts."
            ),
            
            instruction=(
                "Frappe developer. Run tools IMMEDIATELY.\n\n"
                "TOOL SELECTION:\n"
                "- Check DocType → get_doctype_info(doctype='X')\n"
                "- Get record → get_document(doctype='X', name='ID')\n"
                "- Create → create_document(doctype='X', data={...})\n"
                "- Update → update_document(doctype='X', name='ID', data={...})\n"
                "- Run code → run_python_code(code='...')\n\n"
                "DO: Check what exists first, then modify.\n"
                "DON'T: Assume fields exist. Verify with tool."
            ),
            
            output_key="coder_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=CREATIVE_CONFIG,
            after_tool_callback=store_tool_result_in_state,
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
                "Data queries: counts, lists, reports, SQL. "
                "Use for: 'show customers', 'how many X', 'list all Y', reports."
            ),
            
            instruction=(
                "Data analyst. Run tools IMMEDIATELY.\n\n"
                "TOOL SELECTION (pick ONE):\n"
                "- List records → list_documents(doctype='X', limit=10)\n"
                "- Get one record → get_document(doctype='X', name='ID')\n"
                "- Count/SQL → run_database_query(query='SELECT...')\n"
                "- Reports → generate_report()\n\n"
                "TABLE NAMES: DocType 'Customer' = table `tabCustomer`\n\n"
                "DO: Run tool first, then answer with result.\n"
                "DON'T: Explain what you'll do. Just do it."
            ),
            
            output_key="analyst_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=FACTUAL_CONFIG,
            after_tool_callback=store_tool_result_in_state,
            tools=self._get_tools(tool_names),
        )

    def create_nbfc_agent(self) -> LlmAgent:
        """
        NBFC/Lending Operations Specialist for Growth System.
        """
        tool_names = [
            "run_nbfc_audit", "run_database_query", "list_documents", "get_doctype_info",
            "get_document", "search_documents",
        ]
        
        return LlmAgent(
            name="nbfc_specialist",
            model=self.adk_model,
            
            description=(
                "NBFC/Loans: EMI, borrowers, repayments, due loans. "
                "Use for: loan queries, overdue, disbursements."
            ),
            
            instruction=(
                "NBFC specialist. Run tools IMMEDIATELY.\n\n"
                "COMMON QUERIES:\n"
                "- List loans → list_documents(doctype='Loan')\n"
                "- Due loans → run_database_query('SELECT * FROM `tabRepayment Schedule` WHERE status!=\"Cleared\"')\n"
                "- Borrower info → get_document(doctype='Customer', name='X')\n\n"
                "All loan IDs/amounts MUST come from tool results."
            ),
            
            output_key="nbfc_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=FACTUAL_CONFIG,
            after_tool_callback=store_tool_result_in_state,
            tools=self._get_tools(tool_names),
        )

    def create_discovery_agent(self) -> LlmAgent:
        """
        System Discovery & Introspection Specialist.
        """
        tool_names = [
            "get_system_knowledge_graph", "visualize_system_map", "introspect_system", "get_doctype_info", "search_doctype", "list_documents",
        ]
        
        return LlmAgent(
            name="system_discovery",
            model=self.adk_model,
            
            description=(
                "System scan: DocTypes, relationships, workflows. "
                "Use for: 'what DocTypes exist', 'system structure', 'scan system'."
            ),
            
            instruction=(
                "System scanner. Run tools IMMEDIATELY.\n\n"
                "TOOLS:\n"
                "- Full map → get_system_knowledge_graph()\n"
                "- Visual → visualize_system_map()\n"
                "- DocType info → get_doctype_info(doctype='X')\n\n"
                "Report actual DocTypes and relationships found."
            ),
            
            output_key="discovery_result",
            disallow_transfer_to_parent=True,
            disallow_transfer_to_peers=True,
            generate_content_config=FACTUAL_CONFIG,
            after_tool_callback=store_tool_result_in_state,
            tools=self._get_tools(tool_names),
        )

    def create_critique_agent(self) -> LlmAgent:
        """
        Quality Control & Self-Reflection Specialist.
        """
        return LlmAgent(
            name="niv_critique",
            model=self.adk_model,
            
            description="Verify accuracy. Check for mock/fake data.",
            
            instruction=(
                "Verify accuracy. Check if data came from tools.\n"
                "Reply: PASSED or FAILED: [reason]"
            ),
            
            output_key="critique_result",
            generate_content_config=ROUTING_CONFIG,
        )

    def create_planner_agent(self) -> LlmAgent:
        """
        Task Planning & Decomposition Specialist.
        """
        return LlmAgent(
            name="niv_planner",
            model=self.adk_model,
            
            description="Complex projects: break into steps. Multi-step tasks.",
            
            instruction=(
                "Break complex tasks into 3-7 steps.\n"
                "Use create_task_plan() to save plan.\n"
                "Assign steps to: frappe_coder, data_analyst, nbfc_specialist."
            ),
            
            output_key="planner_result",
            generate_content_config=FACTUAL_CONFIG,
            after_tool_callback=store_tool_result_in_state,
            tools=[self.adk_tools["create_task_plan"]]
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
        critique = self.create_critique_agent()
        planner = self.create_planner_agent()
        
        # Orchestrator's own tools (lightweight)
        orc_tool_names = ["universal_search", "list_documents", "get_doctype_info", "save_to_user_memory", "update_task_plan", "get_task_plan"]
        
        return LlmAgent(
            name="niv_orchestrator",
            model=self.adk_model,
            
            description="Routes requests to specialists.",
            
            # COMMON CONTEXT for all agents
            global_instruction=GLOBAL_INSTRUCTION,
            
            instruction=(
                "Route user requests to specialists. Be FAST.\n\n"
                "ROUTING (pick ONE immediately):\n"
                "- Data/list/count/show/report → data_analyst\n"
                "- Code/DocType/Script/Field → frappe_coder\n"
                "- Loan/EMI/NBFC/Borrower → nbfc_specialist\n"
                "- System scan/DocTypes map → system_discovery\n\n"
                "SIMPLE QUERIES: Handle directly with your tools.\n"
                "COMPLEX QUERIES: Route to specialist.\n\n"
                "After specialist returns, format their result for user."
            ),
            
            output_key="orchestrator_result",
            before_agent_callback=init_agent_state,
            generate_content_config=ROUTING_CONFIG,
            after_tool_callback=store_tool_result_in_state,
            tools=self._get_tools(orc_tool_names),
            sub_agents=[coder, analyst, nbfc, discovery, critique, planner],
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
