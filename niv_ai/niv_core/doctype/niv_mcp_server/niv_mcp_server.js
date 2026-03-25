frappe.ui.form.on("Niv MCP Server", {
    refresh: function(frm) {
        // Test Connection button
        frm.add_custom_button(__("Test Connection"), function() {
            frappe.show_alert({message: __("Testing connection..."), indicator: "blue"});
            frappe.call({
                method: "niv_ai.niv_core.doctype.niv_mcp_server.niv_mcp_server.test_connection",
                args: { server_name: frm.doc.server_name },
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: "green"
                        });
                        frm.reload_doc();
                    } else {
                        frappe.msgprint({
                            title: __("Connection Failed"),
                            message: r.message ? r.message.message : "Unknown error",
                            indicator: "red"
                        });
                    }
                },
                error: function(e) {
                    frappe.msgprint({
                        title: __("Error"),
                        message: __("Could not test connection"),
                        indicator: "red"
                    });
                }
            });
        }, __("Actions"));
    }
});
