frappe.ui.form.on("Niv AI Provider", {
    refresh(frm) {
        // Show OAuth login button based on auth type
        if (frm.doc.auth_type === "Setup Token") {
            frm.add_custom_button(__("Login with Claude"), function () {
                niv_oauth_login(frm);
            }, __("OAuth"));
        } else if (frm.doc.auth_type === "ChatGPT Login") {
            frm.add_custom_button(__("Login with ChatGPT"), function () {
                niv_oauth_login(frm);
            }, __("OAuth"));
        }

        // Update status display
        if (frm.doc.oauth_status && frm.doc.auth_type !== "API Key") {
            frm.dashboard.set_headline(frm.doc.oauth_status);
        }
    },

    auth_type(frm) {
        // Auto-set fields based on auth type
        if (frm.doc.auth_type === "Setup Token") {
            frm.set_value("base_url", "https://api.anthropic.com/v1");
            frm.set_value("provider_type", "anthropic");
        } else if (frm.doc.auth_type === "ChatGPT Login") {
            frm.set_value("base_url", "https://api.openai.com/v1");
            frm.set_value("provider_type", "openai_compatible");
        }
    }
});

function niv_oauth_login(frm) {
    if (!frm.doc.name || frm.is_new()) {
        frappe.msgprint(__("Please save the provider first, then click Login with Claude."));
        return;
    }

    frappe.call({
        method: "niv_ai.niv_core.api.oauth.get_auth_url",
        args: { provider_name: frm.doc.name },
        callback(r) {
            if (!r.message || !r.message.url) {
                frappe.msgprint(__("Failed to generate auth URL."));
                return;
            }

            // Open Claude login in new tab
            window.open(r.message.url, "_blank");

            const isChatGPT = frm.doc.auth_type === "ChatGPT Login";
            const providerLabel = isChatGPT ? "ChatGPT" : "Claude";
            const codeHint = isChatGPT 
                ? "Paste the full redirect URL or authorization code" 
                : "Code format: <code>abc123#state456</code>";

            // Show dialog to paste the code
            const d = new frappe.ui.Dialog({
                title: __("Paste Authorization Code"),
                fields: [
                    {
                        fieldtype: "HTML",
                        options: `
                            <div style="margin-bottom: 15px; line-height: 1.6">
                                <p><b>Step 1:</b> A new tab opened with ${providerLabel} login page.</p>
                                <p><b>Step 2:</b> Log in with your ${providerLabel} account.</p>
                                <p><b>Step 3:</b> After login, you'll see an authorization code.</p>
                                <p><b>Step 4:</b> Copy the code and paste it below.</p>
                                <p style="color: var(--text-muted); font-size: 12px">
                                    ${codeHint}
                                </p>
                            </div>
                        `
                    },
                    {
                        fieldname: "auth_code",
                        fieldtype: "Small Text",
                        label: __("Authorization Code"),
                        reqd: 1,
                        description: "Paste the full code from Claude (including the # part)"
                    }
                ],
                primary_action_label: __("Connect"),
                primary_action(values) {
                    if (!values.auth_code) return;

                    d.disable_primary_action();
                    d.set_title(__("Connecting..."));

                    frappe.call({
                        method: "niv_ai.niv_core.api.oauth.exchange_code",
                        args: {
                            provider_name: frm.doc.name,
                            auth_code: values.auth_code.trim()
                        },
                        callback(r) {
                            if (r.message && r.message.success) {
                                d.hide();
                                frappe.show_alert({
                                    message: __("Successfully connected to Claude!"),
                                    indicator: "green"
                                });
                                frm.reload_doc();
                            }
                        },
                        error() {
                            d.enable_primary_action();
                            d.set_title(__("Paste Authorization Code"));
                        }
                    });
                }
            });
            d.show();
        }
    });
}
