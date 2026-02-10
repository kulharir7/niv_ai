import frappe


def search_documents(query, doctype=None, limit=20):
    """Full-text search across documents"""
    limit = min(int(limit), 100)

    if doctype:
        frappe.has_permission(doctype, "read", throw=True)
        meta = frappe.get_meta(doctype)

        # Build search conditions
        search_fields = ["name"]
        for f in meta.get_search_fields():
            search_fields.append(f)
        if meta.title_field and meta.title_field not in search_fields:
            search_fields.append(meta.title_field)

        or_filters = {}
        for sf in search_fields[:5]:
            or_filters[sf] = ["like", f"%{query}%"]

        fields = ["name"]
        if meta.title_field:
            fields.append(meta.title_field)
        for f in ["status", "creation", "modified"]:
            if meta.has_field(f):
                fields.append(f)

        results = frappe.get_list(
            doctype,
            or_filters=or_filters,
            fields=fields,
            limit_page_length=limit,
        )
        return {"doctype": doctype, "query": query, "count": len(results), "results": results}

    # Global search
    return global_search(query, limit)


def search_doctype(query):
    """Find DocType by name or description"""
    results = frappe.get_list(
        "DocType",
        filters=[
            ["name", "like", f"%{query}%"],
            ["istable", "=", 0],
            ["issingle", "=", 0],
        ],
        fields=["name", "module", "description"],
        limit_page_length=20,
        order_by="name ASC",
    )

    # Also search by module
    module_results = frappe.get_list(
        "DocType",
        filters=[
            ["module", "like", f"%{query}%"],
            ["istable", "=", 0],
            ["issingle", "=", 0],
        ],
        fields=["name", "module", "description"],
        limit_page_length=20,
        order_by="name ASC",
    )

    # Merge and deduplicate
    seen = set()
    all_results = []
    for r in results + module_results:
        if r.name not in seen:
            seen.add(r.name)
            all_results.append(r)

    return {"query": query, "count": len(all_results), "doctypes": all_results}


def search_link(doctype, query, filters=None, limit=10):
    """Link field search"""
    frappe.has_permission(doctype, "read", throw=True)

    meta = frappe.get_meta(doctype)
    search_fields = ["name"]
    for f in meta.get_search_fields():
        search_fields.append(f)
    if meta.title_field:
        search_fields.append(meta.title_field)

    or_filters = {}
    for sf in search_fields[:5]:
        or_filters[sf] = ["like", f"%{query}%"]

    results = frappe.get_list(
        doctype,
        filters=filters,
        or_filters=or_filters,
        fields=list(set(search_fields[:5])),
        limit_page_length=min(int(limit), 50),
    )

    return {"doctype": doctype, "query": query, "results": results}


def global_search(query, limit=20):
    """Global search across all DocTypes"""
    from frappe.utils.global_search import search as frappe_global_search

    limit = min(int(limit), 100)
    results = frappe_global_search(query, start=0, limit=limit)

    formatted = []
    for r in results:
        formatted.append({
            "doctype": r.get("doctype"),
            "name": r.get("name"),
            "content": r.get("content", "")[:200],
        })

    return {"query": query, "count": len(formatted), "results": formatted}
