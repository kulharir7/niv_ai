app_name = "niv_ai"
app_title = "Niv AI"
app_publisher = "Ravindra Kulhari"
app_description = "Complete AI Chat Assistant for ERPNext"
app_email = "kulharir7@gmail.com"
app_license = "MIT"
app_version = "0.3.0"
# Works with Frappe/ERPNext v14 and v15
required_apps = ["frappe", "erpnext"]

# Includes in <head>
app_include_css = "/assets/niv_ai/css/niv_widget.css"
app_include_js = "/assets/niv_ai/js/niv_widget.js"

# Page modules
page_modules = {
    "niv-chat": "niv_ai.niv_ui.page.niv_chat",
    "niv-chat-shared": "niv_ai.niv_ui.page.niv_chat_shared",
    "niv-credits": "niv_ai.niv_ui.page.niv_credits",
    "niv-dashboard": "niv_ai.niv_ui.page.niv_dashboard",
}

# Fixtures — disabled, data is seeded via install.py instead
# fixtures = [
#     {"dt": "Niv Credit Plan"},
#     {"dt": "Niv System Prompt"},
#     {"dt": "Niv Tool", "filters": [["is_default", "=", 1]]},
# ]

# Installation
after_install = "niv_ai.install.after_install"
after_migrate = "niv_ai.install.after_migrate"

# Website route rules
website_route_rules = [
    {"from_route": "/niv-chat", "to_route": "niv-chat"},
    {"from_route": "/niv-chat-shared/<share_hash>", "to_route": "niv-chat-shared"},
    {"from_route": "/niv-credits", "to_route": "niv-credits"},
]

# Permissions
has_permission = {
    "Niv Conversation": "niv_ai.niv_core.doctype.niv_conversation.niv_conversation.has_permission",
    "Niv Message": "niv_ai.niv_core.doctype.niv_message.niv_message.has_permission",
}

# Document Events
doc_events = {
    "Niv Conversation": {
        "after_insert": "niv_ai.niv_core.doctype.niv_conversation.niv_conversation.after_insert",
    },
    "*": {
        "on_submit": "niv_ai.niv_core.api.automation.on_doc_event",
        "on_update": "niv_ai.niv_core.api.automation.on_doc_event",
        "on_cancel": "niv_ai.niv_core.api.automation.on_doc_event",
        "after_insert": "niv_ai.niv_core.api.automation.on_doc_event",
    },
}

# Whitelisted methods (auto-registered via @frappe.whitelist but listed for clarity)
# niv_ai.niv_billing.api.payment.get_plans
# niv_ai.niv_billing.api.payment.create_order
# niv_ai.niv_billing.api.payment.verify_payment
# niv_ai.niv_billing.api.payment.get_payment_history
# niv_ai.niv_billing.api.admin.get_usage_report

# Scheduled Tasks
scheduler_events = {
    "daily": [
        "niv_ai.niv_billing.api.billing.cleanup_expired_credits",
        "niv_ai.niv_core.api.scheduler.run_scheduled_reports",
        "niv_ai.niv_core.api.automation.run_daily_auto_actions",
    ],
    "weekly": [
        "niv_ai.niv_billing.api.billing.generate_usage_summary"
    ]
}
