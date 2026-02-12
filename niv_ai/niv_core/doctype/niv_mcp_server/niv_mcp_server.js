frappe.ui.form.on("Niv MCP Server", {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Test Connection"), function() {
                frappe.show_alert({message: "Testing connection...", indicator: "blue"});
                frm.call("test_connection").then(r => {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: `Connected! ${r.message.tools_count} tools discovered.`,
                            indicator: "green"
                        });
                        frm.reload_doc();
                    } else {
                        frappe.show_alert({
                            message: `Failed: ${(r.message && r.message.error) || "Unknown error"}`,
                            indicator: "red"
                        });
                        frm.reload_doc();
                    }
                });
            }, __("Actions"));
        }
    }
});
