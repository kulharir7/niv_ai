"""Test agent initialization"""
def test_agent():
    import frappe
    
    # Test imports
    from niv_ai.niv_core.llm.provider import LLMProvider, MCPTool, get_llm_provider
    from niv_ai.niv_core.tools.mcp_loader import load_mcp_tools
    from niv_ai.niv_core.knowledge.unified_discovery import get_discovery_for_agent
    from niv_ai.niv_core.agent import NivAgent
    
    results = {
        "imports": "OK",
        "tools_count": 0,
        "knowledge_length": 0,
        "agent_created": False
    }
    
    # Test tool loading
    try:
        tools = load_mcp_tools("Administrator")
        results["tools_count"] = len(tools)
        results["tools"] = [t.name for t in tools[:5]]  # First 5 tool names
    except Exception as e:
        results["tools_error"] = str(e)
    
    # Test knowledge
    try:
        knowledge = get_discovery_for_agent()
        results["knowledge_length"] = len(knowledge) if knowledge else 0
    except Exception as e:
        results["knowledge_error"] = str(e)
    
    # Test agent creation
    try:
        agent = NivAgent(user="Administrator")
        results["agent_created"] = True
    except Exception as e:
        results["agent_error"] = str(e)
    
    return results
