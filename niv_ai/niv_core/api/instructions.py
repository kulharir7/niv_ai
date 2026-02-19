import frappe
import json


@frappe.whitelist()
def get_instructions(user=None):
    """Get merged global + user custom instructions"""
    if not user:
        user = frappe.session.user

    instructions = []

    # Global instructions
    global_instructions = frappe.get_all(
        "Niv Custom Instruction",
        filters={"scope": "Global", "is_active": 1},
        fields=["instruction", "priority"],
        order_by="priority DESC",
    )
    instructions.extend(global_instructions)

    # Per-user instructions
    user_instructions = frappe.get_all(
        "Niv Custom Instruction",
        filters={"scope": "Per User", "user": user, "is_active": 1},
        fields=["instruction", "priority"],
        order_by="priority DESC",
    )
    instructions.extend(user_instructions)

    # Sort by priority descending
    instructions.sort(key=lambda x: x.get("priority", 0), reverse=True)

    return instructions


@frappe.whitelist()
def save_instruction(instruction, scope="Per User", priority=0):
    """Save a new custom instruction"""
    user = frappe.session.user

    if scope == "Global" and "System Manager" not in frappe.get_roles(user):
        frappe.throw("Only admins can set global instructions.")

    doc = frappe.get_doc({
        "doctype": "Niv Custom Instruction",
        "user": user if scope == "Per User" else None,
        "instruction": instruction,
        "scope": scope,
        "priority": int(priority),
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "name": doc.name}


@frappe.whitelist()
def delete_instruction(name):
    """Delete a custom instruction"""
    user = frappe.session.user
    doc = frappe.get_doc("Niv Custom Instruction", name)

    # Users can delete their own, admins can delete any
    if doc.user != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw("You can only delete your own instructions.")

    frappe.delete_doc("Niv Custom Instruction", name, ignore_permissions=True)
    frappe.db.commit()

    return {"success": True}


def get_instructions_for_prompt(user):
    """Get formatted instructions string for system prompt injection"""
    instructions = get_instructions(user)
    if not instructions:
        return ""

    parts = []
    for inst in instructions:
        if inst.get("instruction"):
            parts.append(inst["instruction"].strip())

    if not parts:
        return ""

    return "\n\nCustom Instructions:\n" + "\n".join(f"- {p}" for p in parts)
