"""
RAG Auto-Indexer — indexes DocType schemas, workflows, and ERPNext knowledge
into the FAISS vectorstore for context-aware AI responses.

Usage:
    bench --site <site> execute niv_ai.niv_core.langchain.rag_indexer.index_all
    bench --site <site> execute niv_ai.niv_core.langchain.rag_indexer.index_doctypes
    bench --site <site> execute niv_ai.niv_core.langchain.rag_indexer.index_erpnext_knowledge
    bench --site <site> execute niv_ai.niv_core.langchain.rag_indexer.get_index_stats
"""
import frappe
import json
from typing import List, Dict


def index_all(force=False):
    """Index everything: DocTypes + ERPNext knowledge + workflows.
    
    Args:
        force: If True, delete existing index and rebuild from scratch.
    """
    if force:
        from .rag import delete_by_source, _reset_vectorstore
        for source in ["doctype_schema", "erpnext_knowledge", "workflow", "naming_series"]:
            delete_by_source(source)
        _reset_vectorstore()
        print("[RAG Indexer] Cleared existing index")

    stats = {}
    stats["doctypes"] = index_doctypes()
    stats["knowledge"] = index_erpnext_knowledge()
    stats["workflows"] = index_workflows()
    stats["naming"] = index_naming_series()

    total = sum(stats.values())
    print(f"\n[RAG Indexer] === COMPLETE === Total: {total} chunks indexed")
    for key, count in stats.items():
        print(f"  {key}: {count} chunks")

    return stats


def index_doctypes(modules=None, skip_custom=False):
    """Index all DocType schemas into RAG.
    
    Each DocType becomes 1-2 chunks containing:
    - DocType name, module, description
    - All fields with type, required, options
    - Common field combinations for create/update
    
    Args:
        modules: List of modules to index (None = all)
        skip_custom: Skip custom DocTypes
    """
    from .rag import add_documents, delete_by_source

    # Clear existing doctype schemas
    delete_by_source("doctype_schema")

    filters = {"istable": 0}  # Skip child tables as standalone
    if modules:
        filters["module"] = ["in", modules]
    if skip_custom:
        filters["custom"] = 0

    doctypes = frappe.get_all(
        "DocType",
        filters=filters,
        fields=["name", "module", "description", "issingle", "istable", "is_submittable"],
        order_by="module asc, name asc",
    )

    texts = []
    metadatas = []
    skipped = 0

    for dt in doctypes:
        try:
            schema_text = _build_doctype_schema(dt)
            if not schema_text:
                skipped += 1
                continue

            texts.append(schema_text)
            metadatas.append({
                "source": "doctype_schema",
                "title": f"DocType: {dt.name}",
                "doctype": dt.name,
                "module": dt.module,
            })

            # For complex DocTypes with many fields, add a separate "create guide"
            create_guide = _build_create_guide(dt)
            if create_guide:
                texts.append(create_guide)
                metadatas.append({
                    "source": "doctype_schema",
                    "title": f"How to create {dt.name}",
                    "doctype": dt.name,
                    "module": dt.module,
                })
        except Exception as e:
            print(f"  [SKIP] {dt.name}: {e}")
            skipped += 1

    if texts:
        count = add_documents(texts, metadatas, batch_size=30)
        print(f"[RAG Indexer] DocTypes: {count} chunks indexed ({len(doctypes)} DocTypes, {skipped} skipped)")
        return count

    print("[RAG Indexer] DocTypes: No schemas to index")
    return 0


def _build_doctype_schema(dt_info: dict) -> str:
    """Build a rich text description of a DocType for RAG indexing."""
    name = dt_info["name"]

    try:
        meta = frappe.get_meta(name)
    except Exception:
        return ""

    fields = meta.fields or []
    if not fields:
        return ""

    parts = [f"DocType: {name}"]
    parts.append(f"Module: {dt_info.get('module', 'Unknown')}")

    if dt_info.get("description"):
        parts.append(f"Description: {dt_info['description']}")

    doc_flags = []
    if dt_info.get("issingle"):
        doc_flags.append("Single (settings)")
    if dt_info.get("is_submittable"):
        doc_flags.append("Submittable (draft → submitted → cancelled)")
    if dt_info.get("istable"):
        doc_flags.append("Child Table")
    if doc_flags:
        parts.append(f"Type: {', '.join(doc_flags)}")

    # Required fields
    required = []
    for f in fields:
        if f.reqd and f.fieldtype not in ("Section Break", "Column Break", "Tab Break"):
            req_info = f"{f.fieldname} ({f.fieldtype}"
            if f.options:
                req_info += f", options: {f.options}"
            req_info += ")"
            required.append(req_info)

    if required:
        parts.append(f"Required fields: {', '.join(required)}")

    # All data fields (skip layout fields)
    layout_types = {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Fold"}
    data_fields = [f for f in fields if f.fieldtype not in layout_types]

    if len(data_fields) <= 30:
        parts.append("Fields:")
        for f in data_fields:
            line = f"  - {f.fieldname}: {f.fieldtype}"
            if f.options:
                line += f" ({f.options})"
            if f.reqd:
                line += " [REQUIRED]"
            if f.default:
                line += f" [default: {f.default}]"
            parts.append(line)
    else:
        # Too many fields — summarize
        parts.append(f"Total fields: {len(data_fields)}")
        parts.append("Key fields:")
        # Show required + first 15 important ones
        shown = set()
        for f in data_fields:
            if f.reqd and f.fieldname not in shown:
                line = f"  - {f.fieldname}: {f.fieldtype}"
                if f.options:
                    line += f" ({f.options})"
                line += " [REQUIRED]"
                parts.append(line)
                shown.add(f.fieldname)

        for f in data_fields:
            if f.fieldname not in shown and len(shown) < 20:
                line = f"  - {f.fieldname}: {f.fieldtype}"
                if f.options:
                    line += f" ({f.options})"
                parts.append(line)
                shown.add(f.fieldname)

        remaining = len(data_fields) - len(shown)
        if remaining > 0:
            parts.append(f"  ... and {remaining} more fields")

    # Child tables
    child_tables = [f for f in fields if f.fieldtype == "Table"]
    if child_tables:
        parts.append("Child Tables:")
        for ct in child_tables:
            parts.append(f"  - {ct.fieldname}: {ct.options}")
            # Get child table required fields
            try:
                child_meta = frappe.get_meta(ct.options)
                child_required = [
                    cf.fieldname for cf in (child_meta.fields or [])
                    if cf.reqd and cf.fieldtype not in layout_types
                ]
                if child_required:
                    parts.append(f"    Required: {', '.join(child_required)}")
            except Exception:
                pass

    return "\n".join(parts)


def _build_create_guide(dt_info: dict) -> str:
    """Build a 'how to create' guide for common DocTypes."""
    name = dt_info["name"]

    try:
        meta = frappe.get_meta(name)
    except Exception:
        return ""

    # Only for DocTypes with child tables or 5+ required fields
    fields = meta.fields or []
    layout_types = {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Fold"}
    required = [f for f in fields if f.reqd and f.fieldtype not in layout_types]
    child_tables = [f for f in fields if f.fieldtype == "Table"]

    if len(required) < 3 and not child_tables:
        return ""

    parts = [f"How to create a {name}:"]
    parts.append(f"Use the create_document tool with doctype='{name}'")
    parts.append("Required values:")

    for f in required:
        hint = ""
        if f.fieldtype == "Link":
            hint = f" (must be valid {f.options} name)"
        elif f.fieldtype == "Date":
            hint = " (format: YYYY-MM-DD)"
        elif f.fieldtype == "Select" and f.options:
            opts = f.options.split("\n")[:5]
            hint = f" (options: {', '.join(opts)})"
        parts.append(f"  - {f.fieldname}: {f.fieldtype}{hint}")

    if child_tables:
        parts.append("Child table items (pass as list of dicts):")
        for ct in child_tables:
            parts.append(f"  {ct.fieldname} (type: {ct.options}):")
            try:
                child_meta = frappe.get_meta(ct.options)
                for cf in (child_meta.fields or []):
                    if cf.reqd and cf.fieldtype not in layout_types:
                        parts.append(f"    - {cf.fieldname}: {cf.fieldtype} [REQUIRED]")
            except Exception:
                pass

    if dt_info.get("is_submittable"):
        parts.append("Note: Creates as Draft. Use submit_document to submit after review.")

    # Example JSON structure
    example = {"doctype": name}
    for f in required[:5]:
        if f.fieldtype == "Link":
            example[f.fieldname] = f"<valid {f.options}>"
        elif f.fieldtype == "Date":
            example[f.fieldname] = "2026-01-01"
        elif f.fieldtype in ("Currency", "Float", "Int"):
            example[f.fieldname] = 0
        else:
            example[f.fieldname] = f"<{f.fieldname}>"

    if child_tables:
        ct = child_tables[0]
        try:
            child_meta = frappe.get_meta(ct.options)
            child_example = {}
            for cf in (child_meta.fields or []):
                if cf.reqd and cf.fieldtype not in layout_types:
                    child_example[cf.fieldname] = f"<{cf.fieldname}>"
            if child_example:
                example[ct.fieldname] = [child_example]
        except Exception:
            pass

    parts.append(f"Example: {json.dumps(example, indent=2)}")

    return "\n".join(parts)


def index_erpnext_knowledge():
    """Index general ERPNext knowledge — common workflows, tips, concepts."""
    from .rag import add_documents, delete_by_source

    delete_by_source("erpnext_knowledge")

    knowledge = [
        {
            "title": "ERPNext Document Lifecycle",
            "content": (
                "ERPNext documents follow a lifecycle: Draft → Saved → Submitted → Cancelled → Amended.\n"
                "Draft: Initial state, can be freely edited.\n"
                "Submitted: Finalized, creates GL entries/stock ledger. Cannot be edited directly.\n"
                "Cancelled: Reverses all ledger entries. Creates 'Amended From' link.\n"
                "Amended: Creates a new version from cancelled document.\n"
                "Tools: create_document (draft), submit_document (submit), update_document (amend).\n"
                "Submittable DocTypes: Sales Order, Purchase Order, Sales Invoice, Purchase Invoice, "
                "Journal Entry, Stock Entry, Delivery Note, Purchase Receipt, Payment Entry."
            ),
        },
        {
            "title": "ERPNext Selling Workflow",
            "content": (
                "Standard selling flow in ERPNext:\n"
                "1. Lead → Opportunity → Quotation → Sales Order → Delivery Note → Sales Invoice → Payment Entry\n"
                "Key relationships:\n"
                "- Sales Order: customer (Link to Customer), items (child table Sales Order Item with item_code, qty, rate)\n"
                "- Delivery Note: Created from Sales Order (Get Items From > Sales Order)\n"
                "- Sales Invoice: Created from Sales Order or Delivery Note\n"
                "- Payment Entry: Created from Sales Invoice (Make > Payment)\n"
                "Common fields: company, customer, transaction_date, delivery_date, items table"
            ),
        },
        {
            "title": "ERPNext Buying Workflow",
            "content": (
                "Standard buying flow in ERPNext:\n"
                "1. Material Request → Supplier Quotation → Purchase Order → Purchase Receipt → Purchase Invoice → Payment Entry\n"
                "Key relationships:\n"
                "- Purchase Order: supplier (Link to Supplier), items (child table Purchase Order Item with item_code, qty, rate)\n"
                "- Purchase Receipt: Created from Purchase Order\n"
                "- Purchase Invoice: Created from PO or Purchase Receipt\n"
                "Common fields: company, supplier, transaction_date, schedule_date, items table"
            ),
        },
        {
            "title": "ERPNext Stock/Inventory",
            "content": (
                "Stock management in ERPNext:\n"
                "- Item: Master for all products/services. item_code is the primary key.\n"
                "- Warehouse: Stock location. Default warehouse in Stock Settings.\n"
                "- Stock Entry: Transfer, receipt, manufacture. Types: Material Receipt, Material Transfer, Manufacture.\n"
                "- Stock Reconciliation: Adjust opening stock or fix discrepancies.\n"
                "- Bin: Real-time stock balance per item per warehouse.\n"
                "To check stock: list_documents with doctype='Bin', filters by item_code and warehouse.\n"
                "To move stock: create Stock Entry with items table (item_code, qty, s_warehouse, t_warehouse)."
            ),
        },
        {
            "title": "ERPNext Accounting Basics",
            "content": (
                "Accounting in ERPNext:\n"
                "- Chart of Accounts: Tree structure. Account types: Asset, Liability, Income, Expense, Equity.\n"
                "- Journal Entry: Manual accounting entry. Debit and Credit rows must balance.\n"
                "- Payment Entry: Receive/pay against invoices. payment_type: Receive/Pay/Internal Transfer.\n"
                "- GL Entry: Auto-generated from invoices, payments. Read-only.\n"
                "- Fiscal Year: Financial year period. Must exist for transaction dates.\n"
                "Common queries: Account balance (GL Entry), Outstanding invoices (Sales/Purchase Invoice with outstanding_amount > 0)"
            ),
        },
        {
            "title": "ERPNext HR Module",
            "content": (
                "HR management in ERPNext:\n"
                "- Employee: Master record. employee_name, company, department, designation required.\n"
                "- Leave Application: employee, leave_type, from_date, to_date required.\n"
                "- Attendance: employee, attendance_date, status (Present/Absent/Half Day/Work From Home).\n"
                "- Salary Structure: Links to Salary Component. Assign via Salary Structure Assignment.\n"
                "- Payroll Entry: Generate salary slips for a period. company, payroll_frequency required.\n"
                "Common queries: Employee count by department, Leave balance, Attendance summary."
            ),
        },
        {
            "title": "ERPNext Common Patterns",
            "content": (
                "Useful patterns for querying ERPNext data:\n"
                "1. Count documents: list_documents with doctype, limit=0, then check total\n"
                "2. Filter by date range: filters={'date_field': ['between', ['2025-01-01', '2025-12-31']]}\n"
                "3. Filter by status: filters={'status': 'Draft'} or {'docstatus': 0} (0=draft, 1=submitted, 2=cancelled)\n"
                "4. Search by name pattern: filters={'name': ['like', '%keyword%']}\n"
                "5. Get document details: use get_document tool with doctype and name\n"
                "6. Aggregate data: use run_python_code or run_database_query for SUM/COUNT/GROUP BY\n"
                "7. Check permissions: list_documents respects user permissions automatically\n"
                "8. Fields parameter: pass fields=['name', 'field1', 'field2'] to get specific columns only"
            ),
        },
    ]

    texts = [k["content"] for k in knowledge]
    metadatas = [{"source": "erpnext_knowledge", "title": k["title"]} for k in knowledge]

    count = add_documents(texts, metadatas)
    print(f"[RAG Indexer] ERPNext Knowledge: {count} chunks indexed")
    return count


def index_workflows():
    """Index active Workflow definitions."""
    from .rag import add_documents, delete_by_source

    delete_by_source("workflow")

    workflows = frappe.get_all(
        "Workflow",
        filters={"is_active": 1},
        fields=["name", "document_type", "workflow_name"],
    )

    if not workflows:
        print("[RAG Indexer] Workflows: None active")
        return 0

    texts = []
    metadatas = []

    for wf in workflows:
        try:
            wf_doc = frappe.get_doc("Workflow", wf.name)
            parts = [f"Workflow: {wf.workflow_name or wf.name}"]
            parts.append(f"Applies to: {wf.document_type}")

            states = []
            for s in (wf_doc.states or []):
                state_info = f"  - {s.state}"
                if s.doc_status is not None:
                    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
                    state_info += f" (docstatus: {status_map.get(s.doc_status, s.doc_status)})"
                if s.allow_edit:
                    state_info += f" [editable by: {s.allow_edit}]"
                states.append(state_info)

            if states:
                parts.append("States:")
                parts.extend(states)

            transitions = []
            for t in (wf_doc.transitions or []):
                transitions.append(
                    f"  - {t.state} → {t.next_state} (action: {t.action}, allowed: {t.allowed})"
                )

            if transitions:
                parts.append("Transitions:")
                parts.extend(transitions)

            texts.append("\n".join(parts))
            metadatas.append({
                "source": "workflow",
                "title": f"Workflow: {wf.workflow_name or wf.name}",
                "doctype": wf.document_type,
            })
        except Exception as e:
            print(f"  [SKIP] Workflow {wf.name}: {e}")

    if texts:
        count = add_documents(texts, metadatas)
        print(f"[RAG Indexer] Workflows: {count} chunks indexed")
        return count

    return 0


def index_naming_series():
    """Index naming series patterns for document creation."""
    from .rag import add_documents, delete_by_source

    delete_by_source("naming_series")

    # Get DocTypes with naming series
    doctypes_with_naming = frappe.get_all(
        "DocType",
        filters={"autoname": ["like", "%naming_series%"]},
        fields=["name", "autoname"],
    )

    if not doctypes_with_naming:
        print("[RAG Indexer] Naming Series: None found")
        return 0

    texts = []
    metadatas = []

    for dt in doctypes_with_naming:
        try:
            meta = frappe.get_meta(dt.name)
            ns_field = meta.get_field("naming_series")
            if ns_field and ns_field.options:
                options = [o.strip() for o in ns_field.options.split("\n") if o.strip()]
                text = (
                    f"Naming Series for {dt.name}:\n"
                    f"Available patterns: {', '.join(options)}\n"
                    f"Default: {options[0] if options else 'None'}\n"
                    f"When creating a {dt.name}, the naming_series field determines the ID format."
                )
                texts.append(text)
                metadatas.append({
                    "source": "naming_series",
                    "title": f"Naming: {dt.name}",
                    "doctype": dt.name,
                })
        except Exception:
            pass

    if texts:
        count = add_documents(texts, metadatas)
        print(f"[RAG Indexer] Naming Series: {count} chunks indexed")
        return count

    return 0


def get_index_stats():
    """Get stats about what's currently indexed."""
    try:
        from .rag import _get_vectorstore
        store = _get_vectorstore()
        all_docs = store.docstore._dict

        stats = {"total": 0, "by_source": {}}
        for _doc_id, doc in all_docs.items():
            source = doc.metadata.get("source", "unknown")
            if source == "init":
                continue
            stats["total"] += 1
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

        print(f"\n[RAG Index Stats]")
        print(f"  Total chunks: {stats['total']}")
        for source, count in sorted(stats["by_source"].items()):
            print(f"  {source}: {count}")

        return stats
    except Exception as e:
        print(f"[RAG Index Stats] Error: {e}")
        return {"total": 0, "error": str(e)}
