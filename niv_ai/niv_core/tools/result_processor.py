"""
Tool Result Post-Processor for Niv AI.

Problem: MCP tools return raw JSON that can be 50KB+, flooding the LLM context window.
Solution: Intelligently summarize/truncate results while preserving essential information.

Usage: Called by langchain/tools.py in _make_mcp_executor() after getting tool result.
"""
import json
from typing import Optional


# Maximum characters to allow in a tool result before summarization kicks in
MAX_RESULT_CHARS = 4000

# Tools whose results should never be truncated (schema/metadata tools)
_NO_TRUNCATE_TOOLS = {
    "get_doctype_info", "search_doctype", "report_requirements",
    "report_list", "search_link"
}

# Read-only tools whose results can be cached
READ_ONLY_TOOLS = {
    "get_doctype_info", "search_doctype", "report_list",
    "report_requirements", "search_link"
}


def post_process_result(tool_name: str, result_text: str) -> str:
    """Post-process a tool result to reduce token usage.
    
    Strategy:
    1. Small results (< MAX_RESULT_CHARS) → pass through unchanged
    2. JSON list results → keep first N records + summary
    3. Large text → truncate with indicator
    4. Schema tools → never truncate
    
    Args:
        tool_name: Name of the tool that produced this result
        result_text: Raw result string from MCP tool
        
    Returns:
        Processed result string (may be shorter than input)
    """
    if not result_text:
        return result_text
    
    # Small results → pass through
    if len(result_text) <= MAX_RESULT_CHARS:
        return result_text
    
    # Schema/metadata tools → don't truncate (they're reference data)
    if tool_name in _NO_TRUNCATE_TOOLS:
        # Still apply a generous limit
        if len(result_text) > 8000:
            return result_text[:8000] + "\n\n[... truncated. Use specific filters for smaller results.]"
        return result_text
    
    # Try to parse as JSON for intelligent summarization
    try:
        data = json.loads(result_text)
        return _summarize_json_result(tool_name, data)
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Plain text → hard truncate with indicator
    return _truncate_text(result_text)


def _summarize_json_result(tool_name: str, data) -> str:
    """Summarize a JSON tool result intelligently."""
    
    # Case 1: Dict with "data" list (list_documents pattern)
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return _summarize_list_result(tool_name, data)
    
    # Case 2: Dict with "result" that contains data
    if isinstance(data, dict) and "result" in data:
        result_val = data["result"]
        if isinstance(result_val, dict) and "data" in result_val and isinstance(result_val["data"], list):
            return _summarize_list_result(tool_name, result_val)
        if isinstance(result_val, list):
            return _summarize_list_result(tool_name, {"data": result_val})
    
    # Case 3: Plain list
    if isinstance(data, list):
        return _summarize_list_result(tool_name, {"data": data})
    
    # Case 4: Dict with large string values
    if isinstance(data, dict):
        return _summarize_dict_result(data)
    
    # Fallback: convert back to JSON string and truncate
    text = json.dumps(data, default=str, ensure_ascii=False)
    return _truncate_text(text)


def _summarize_list_result(tool_name: str, data: dict) -> str:
    """Summarize a list-type result (most common for list_documents)."""
    records = data.get("data", [])
    total_count = data.get("total_count", len(records))
    message = data.get("message", "")
    
    if not records:
        return json.dumps({"data": [], "total_count": 0, "message": message or "No records found"}, 
                         default=str, ensure_ascii=False)
    
    # Determine how many records to keep
    # For small lists, keep all; for large lists, keep first 10
    max_records = 10 if len(records) > 10 else len(records)
    
    summary = {
        "total_records_in_database": total_count,
        "records_returned": len(records),
        "showing_first": max_records,
        "data": records[:max_records],
    }
    
    if message:
        summary["message"] = message
    
    if len(records) > max_records:
        summary["note"] = (
            f"Showing {max_records} of {len(records)} returned records "
            f"({total_count} total in database). "
            "Add more specific filters or use get_document for details on a specific record."
        )
    
    result = json.dumps(summary, default=str, ensure_ascii=False)
    
    # If still too large after keeping 10 records, reduce further
    if len(result) > MAX_RESULT_CHARS and max_records > 5:
        summary["data"] = records[:5]
        summary["showing_first"] = 5
        summary["note"] = (
            f"Showing 5 of {len(records)} returned records "
            f"({total_count} total in database). "
            "Results were large — add more specific filters or ask about specific records."
        )
        result = json.dumps(summary, default=str, ensure_ascii=False)
    
    # Last resort: truncate individual records
    if len(result) > MAX_RESULT_CHARS:
        # Keep only key fields from each record
        slim_records = []
        for record in records[:5]:
            if isinstance(record, dict):
                # Keep name + up to 5 most important fields
                slim = {}
                priority_fields = ["name", "status", "title", "subject", "customer_name", 
                                  "applicant_name", "loan_amount", "amount", "total", 
                                  "posting_date", "creation"]
                for f in priority_fields:
                    if f in record:
                        slim[f] = record[f]
                # Add remaining fields up to limit
                for k, v in record.items():
                    if k not in slim and len(slim) < 8:
                        val = str(v)
                        slim[k] = val[:200] if len(val) > 200 else v
                slim_records.append(slim)
            else:
                slim_records.append(record)
        
        summary["data"] = slim_records
        result = json.dumps(summary, default=str, ensure_ascii=False)
    
    return result


def _summarize_dict_result(data: dict) -> str:
    """Summarize a dict result by truncating large values."""
    slim = {}
    for key, value in data.items():
        if isinstance(value, str) and len(value) > 500:
            slim[key] = value[:500] + "...[truncated]"
        elif isinstance(value, list) and len(value) > 10:
            slim[key] = value[:10]
            slim[f"_{key}_note"] = f"Showing 10 of {len(value)} items"
        elif isinstance(value, dict):
            # Recursively handle nested dicts
            val_str = json.dumps(value, default=str)
            if len(val_str) > 1000:
                slim[key] = json.loads(val_str[:1000] + "}")  # Attempt to keep valid JSON
            else:
                slim[key] = value
        else:
            slim[key] = value
    
    return json.dumps(slim, default=str, ensure_ascii=False)


def _truncate_text(text: str) -> str:
    """Truncate plain text with indicator."""
    if len(text) <= MAX_RESULT_CHARS:
        return text
    
    truncated = text[:MAX_RESULT_CHARS]
    remaining = len(text) - MAX_RESULT_CHARS
    return f"{truncated}\n\n[... {remaining} characters truncated. Ask for specific details if needed.]"


def add_next_steps(tool_name: str, result_text: str) -> str:
    """Append contextual next-step hints to tool results.
    
    Guides the LLM on what to do after getting this result.
    """
    hints = {
        "list_documents": (
            "\n\n💡 Next steps: Use get_document(doctype, name) to see full details "
            "of a specific record. Use run_database_query for aggregations (SUM, COUNT, AVG)."
        ),
        "get_doctype_info": (
            "\n\n💡 Now you know the fields. Use list_documents with correct field names, "
            "or create_document with all required fields."
        ),
        "report_requirements": (
            "\n\n💡 Now call generate_report with the required filters listed above."
        ),
        "search_doctype": (
            "\n\n💡 Now use list_documents or get_document with the correct DocType name."
        ),
        "report_list": (
            "\n\n💡 To generate a report, first call report_requirements(report_name) to get required filters, "
            "then call generate_report(report_name, filters)."
        ),
    }
    
    hint = hints.get(tool_name)
    if hint and len(result_text) < MAX_RESULT_CHARS:  # Don't add hints to already large results
        return result_text + hint
    return result_text
