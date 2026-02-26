"""Bulk Data Import from Excel for Niv AI.

User uploads Excel file in chat → AI reads it → validates → creates documents in Growth System.
Usage via run_python_code MCP tool:
    from niv_ai.niv_core.tools.bulk_import import preview_import, execute_import

Flow:
1. User uploads Excel in chat
2. AI calls preview_import() → shows validation results
3. User confirms → AI calls execute_import() → creates documents
"""
import frappe
import json
import os
import traceback
from typing import Optional


# Safety limits
MAX_IMPORT_ROWS = 200  # Max rows per import
MAX_PREVIEW_ROWS = 10  # Rows to show in preview
MAX_ERRORS_SHOW = 20   # Max errors to display


def preview_import(file_url: str, doctype: str, field_mapping: Optional[dict] = None) -> dict:
    """Preview what will be imported from Excel — validates without creating.
    
    Args:
        file_url: Frappe file URL (e.g., /files/loans.xlsx)
        doctype: Target DocType (e.g., 'Customer', 'Loan', 'Sales Order')
        field_mapping: Optional dict mapping Excel columns → DocType fields
                      e.g., {"Customer Name": "customer_name", "Phone": "phone"}
                      If None, auto-maps by matching column names to field labels/names
    
    Returns:
        dict with preview, errors, valid_count, etc.
    """
    # 1. Read Excel file
    try:
        df = _read_excel(file_url)
    except Exception as e:
        return {"status": "error", "message": f"Failed to read file: {str(e)}"}
    
    if df is None or len(df) == 0:
        return {"status": "error", "message": "File is empty or could not be parsed"}
    
    total_rows = len(df)
    if total_rows > MAX_IMPORT_ROWS:
        return {
            "status": "error",
            "message": f"Too many rows ({total_rows}). Maximum allowed: {MAX_IMPORT_ROWS}. Please split the file."
        }
    
    # 2. Validate DocType exists and user has permission
    if not frappe.db.exists("DocType", doctype):
        return {"status": "error", "message": f"DocType '{doctype}' does not exist"}
    
    if not frappe.has_permission(doctype, "create"):
        return {"status": "error", "message": f"You don't have permission to create {doctype}"}
    
    # 3. Auto-map or use provided mapping
    if field_mapping:
        mapping = field_mapping
    else:
        mapping = _auto_map_fields(df.columns.tolist(), doctype)
    
    unmapped = [col for col in df.columns if col not in mapping]
    
    # 4. Validate each row
    valid_rows = []
    errors = []
    
    meta = frappe.get_meta(doctype)
    required_fields = [f.fieldname for f in meta.fields if f.reqd and f.fieldname != "name"]
    link_fields = {f.fieldname: f.options for f in meta.fields if f.fieldtype == "Link"}
    select_fields = {f.fieldname: [o.strip() for o in (f.options or "").split("\n") if o.strip()] 
                     for f in meta.fields if f.fieldtype == "Select"}
    
    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row (1-indexed + header)
        row_errors = []
        row_data = {}
        
        for excel_col, frappe_field in mapping.items():
            value = row.get(excel_col)
            
            # Handle NaN/None
            if _is_empty(value):
                value = None
            else:
                value = _clean_value(value)
            
            row_data[frappe_field] = value
        
        # Check required fields
        for req_field in required_fields:
            if req_field in row_data and _is_empty(row_data.get(req_field)):
                field_label = meta.get_label(req_field) or req_field
                row_errors.append(f"'{field_label}' is required but empty")
            elif req_field not in row_data:
                # Required field not in mapping — check if it has a default
                field_meta = meta.get_field(req_field)
                if field_meta and not field_meta.default:
                    field_label = meta.get_label(req_field) or req_field
                    row_errors.append(f"Required field '{field_label}' not mapped from Excel")
        
        # Check Link fields exist
        for field, link_doctype in link_fields.items():
            if field in row_data and row_data[field]:
                if not frappe.db.exists(link_doctype, row_data[field]):
                    row_errors.append(f"'{row_data[field]}' not found in {link_doctype}")
        
        # Check Select field values
        for field, options in select_fields.items():
            if field in row_data and row_data[field] and options:
                if str(row_data[field]) not in options:
                    row_errors.append(f"Invalid value '{row_data[field]}' for {field}. Options: {', '.join(options[:5])}")
        
        if row_errors:
            errors.append({"row": row_num, "errors": row_errors})
        else:
            valid_rows.append(row_data)
    
    # 5. Build preview
    preview_data = valid_rows[:MAX_PREVIEW_ROWS]
    
    return {
        "status": "preview",
        "doctype": doctype,
        "file": os.path.basename(file_url),
        "total_rows": total_rows,
        "valid_count": len(valid_rows),
        "error_count": len(errors),
        "mapping": mapping,
        "unmapped_columns": unmapped,
        "errors": errors[:MAX_ERRORS_SHOW],
        "preview": preview_data,
        "message": _build_preview_message(doctype, total_rows, len(valid_rows), len(errors), errors),
        "note": "Call execute_import() to create the documents" if valid_rows else "Fix errors and retry"
    }


def execute_import(file_url: str, doctype: str, field_mapping: Optional[dict] = None, 
                   skip_errors: bool = False) -> dict:
    """Actually import data from Excel into Growth System.
    
    Args:
        file_url: Same file URL used in preview
        doctype: Target DocType
        field_mapping: Same mapping used in preview
        skip_errors: If True, skip invalid rows and import valid ones
    
    Returns:
        dict with created count, errors, created document names
    """
    # Re-validate
    preview = preview_import(file_url, doctype, field_mapping)
    
    if preview["status"] == "error":
        return preview
    
    if preview["error_count"] > 0 and not skip_errors:
        return {
            "status": "error",
            "message": f"{preview['error_count']} rows have errors. Fix them or set skip_errors=True to import only valid rows ({preview['valid_count']} rows).",
            "errors": preview["errors"]
        }
    
    if preview["valid_count"] == 0:
        return {"status": "error", "message": "No valid rows to import"}
    
    # Read Excel again and import valid rows
    try:
        df = _read_excel(file_url)
    except Exception as e:
        return {"status": "error", "message": f"Failed to read file: {str(e)}"}
    
    mapping = field_mapping or _auto_map_fields(df.columns.tolist(), doctype)
    meta = frappe.get_meta(doctype)
    required_fields = [f.fieldname for f in meta.fields if f.reqd and f.fieldname != "name"]
    link_fields = {f.fieldname: f.options for f in meta.fields if f.fieldtype == "Link"}
    
    created = []
    errors = []
    
    for idx, row in df.iterrows():
        row_num = idx + 2
        row_data = {}
        
        for excel_col, frappe_field in mapping.items():
            value = row.get(excel_col)
            if _is_empty(value):
                value = None
            else:
                value = _clean_value(value)
            row_data[frappe_field] = value
        
        # Skip if has errors and skip_errors is True
        has_error = False
        for req_field in required_fields:
            if req_field in row_data and _is_empty(row_data.get(req_field)):
                has_error = True
                break
        for field, link_dt in link_fields.items():
            if field in row_data and row_data[field] and not frappe.db.exists(link_dt, row_data[field]):
                has_error = True
                break
        
        if has_error and skip_errors:
            errors.append({"row": row_num, "status": "skipped"})
            continue
        elif has_error:
            errors.append({"row": row_num, "status": "error"})
            continue
        
        # Create document
        try:
            doc = frappe.get_doc({
                "doctype": doctype,
                **{k: v for k, v in row_data.items() if v is not None}
            })
            doc.flags.ignore_permissions = False
            doc.insert()
            created.append(doc.name)
        except Exception as e:
            errors.append({
                "row": row_num, 
                "status": "failed",
                "error": str(e)[:200]
            })
    
    if created:
        frappe.db.commit()
    
    return {
        "status": "success" if created else "error",
        "message": f"Created {len(created)}/{preview['total_rows']} {doctype} documents",
        "created_count": len(created),
        "created_names": created[:50],  # Show first 50
        "error_count": len(errors),
        "errors": errors[:MAX_ERRORS_SHOW],
        "doctype": doctype
    }


# ============================================================
# Helper Functions
# ============================================================

def _read_excel(file_url: str):
    """Read Excel/CSV file from Frappe file URL."""
    import pandas as pd
    
    file_path = _get_file_path(file_url)
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_url}")
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".csv":
        return pd.read_csv(file_path)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use .xlsx, .xls, or .csv")


def _get_file_path(file_url: str) -> Optional[str]:
    """Convert Frappe file URL to absolute path."""
    if not file_url:
        return None
    
    site_path = frappe.get_site_path()
    
    if file_url.startswith("/files/"):
        return os.path.join(site_path, "public", file_url.lstrip("/"))
    elif file_url.startswith("/private/files/"):
        return os.path.join(site_path, file_url.lstrip("/"))
    elif os.path.isabs(file_url):
        return file_url
    
    return None


def _auto_map_fields(excel_columns: list, doctype: str) -> dict:
    """Auto-map Excel column names to DocType field names/labels.
    
    Matches by:
    1. Exact field name match (case-insensitive)
    2. Exact label match (case-insensitive)
    3. Fuzzy match (column contains field name or vice versa)
    """
    meta = frappe.get_meta(doctype)
    mapping = {}
    
    # Build lookup: lowercase label/name → fieldname
    field_lookup = {}
    for f in meta.fields:
        if f.fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML"):
            continue
        field_lookup[f.fieldname.lower()] = f.fieldname
        if f.label:
            field_lookup[f.label.lower()] = f.fieldname
    
    for col in excel_columns:
        col_lower = str(col).lower().strip()
        
        # Exact match
        if col_lower in field_lookup:
            mapping[col] = field_lookup[col_lower]
            continue
        
        # Clean match (remove spaces, underscores, hyphens)
        col_clean = col_lower.replace(" ", "_").replace("-", "_")
        if col_clean in field_lookup:
            mapping[col] = field_lookup[col_clean]
            continue
        
        # Fuzzy: Excel col contains field name or field label contains col
        for key, fieldname in field_lookup.items():
            if col_lower in key or key in col_lower:
                if col not in mapping:  # Don't overwrite better matches
                    mapping[col] = fieldname
                break
    
    return mapping


def _is_empty(value) -> bool:
    """Check if value is empty/NaN."""
    if value is None:
        return True
    try:
        import pandas as pd
        if pd.isna(value):
            return True
    except (ImportError, TypeError, ValueError):
        pass
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _clean_value(value):
    """Clean a cell value for Frappe."""
    if isinstance(value, float):
        # Convert float that's actually int (e.g., 100.0 → 100)
        if value == int(value):
            return int(value)
        return value
    if isinstance(value, str):
        return value.strip()
    return value


def _build_preview_message(doctype, total, valid, errors, error_list):
    """Build a human-readable preview message."""
    lines = [f"📊 Found {total} rows in Excel"]
    
    if valid > 0:
        lines.append(f"✅ {valid} valid — ready to create as {doctype}")
    
    if errors > 0:
        lines.append(f"❌ {errors} rows with errors:")
        for err in error_list[:5]:
            err_msgs = "; ".join(err["errors"][:3])
            lines.append(f"   Row {err['row']}: {err_msgs}")
        if errors > 5:
            lines.append(f"   ... and {errors - 5} more errors")
    
    if valid > 0 and errors > 0:
        lines.append(f"\nOptions: Create {valid} valid rows (skip errors) or fix Excel and re-upload")
    elif valid > 0:
        lines.append(f"\nReady to import! Confirm to create {valid} {doctype} documents.")
    
    return "\n".join(lines)
