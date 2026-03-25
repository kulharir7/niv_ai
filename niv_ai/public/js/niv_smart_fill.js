/**
 * Niv AI Smart Fill v1.0
 * Auto-suggest field values when user selects a Link field.
 * Shows a sleek suggestion bar — one click to apply all.
 * Zero AI cost — uses past data patterns.
 */
(function() {
    "use strict";

    var ENABLED_DOCTYPES = null; // Loaded on first use
    var _active_panel = null;
    var _debounce_timer = null;

    // ─── CSS ───────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById("niv-smart-fill-styles")) return;
        var style = document.createElement("style");
        style.id = "niv-smart-fill-styles";
        style.textContent = [
            ".niv-sf-panel {",
            "  background: linear-gradient(135deg, #1e1b2e 0%, #2d2640 100%);",
            "  border: 1px solid #7c3aed44;",
            "  border-radius: 10px;",
            "  padding: 12px 16px;",
            "  margin: 8px 0 12px 0;",
            "  box-shadow: 0 4px 20px rgba(124, 58, 237, 0.15);",
            "  opacity: 0;",
            "  transform: translateY(-8px);",
            "  transition: opacity 0.3s ease, transform 0.3s ease;",
            "}",
            ".niv-sf-panel.niv-sf-visible {",
            "  opacity: 1;",
            "  transform: translateY(0);",
            "}",
            ".niv-sf-header {",
            "  display: flex;",
            "  align-items: center;",
            "  justify-content: space-between;",
            "  margin-bottom: 8px;",
            "}",
            ".niv-sf-title {",
            "  color: #c4b5fd;",
            "  font-size: 12px;",
            "  font-weight: 600;",
            "  text-transform: uppercase;",
            "  letter-spacing: 0.5px;",
            "}",
            ".niv-sf-close {",
            "  background: none; border: none; color: #9f9bb0;",
            "  cursor: pointer; font-size: 18px; padding: 0 4px; line-height: 1;",
            "}",
            ".niv-sf-close:hover { color: #fff; }",
            ".niv-sf-items {",
            "  display: flex;",
            "  flex-wrap: wrap;",
            "  gap: 6px;",
            "  margin-bottom: 10px;",
            "}",
            ".niv-sf-item {",
            "  background: #7c3aed22;",
            "  border: 1px solid #7c3aed44;",
            "  border-radius: 6px;",
            "  padding: 6px 10px;",
            "  display: flex;",
            "  align-items: center;",
            "  gap: 6px;",
            "  cursor: pointer;",
            "  transition: all 0.2s ease;",
            "}",
            ".niv-sf-item:hover {",
            "  background: #7c3aed33;",
            "  border-color: #7c3aed88;",
            "}",
            ".niv-sf-item.niv-sf-applied {",
            "  background: #05966922;",
            "  border-color: #05966966;",
            "}",
            ".niv-sf-item-label {",
            "  color: #a5a0b8;",
            "  font-size: 11px;",
            "}",
            ".niv-sf-item-value {",
            "  color: #e2e0ea;",
            "  font-size: 12px;",
            "  font-weight: 500;",
            "}",
            ".niv-sf-item-confidence {",
            "  color: #7c3aed;",
            "  font-size: 10px;",
            "  font-weight: 600;",
            "}",
            ".niv-sf-item-check {",
            "  color: #10b981;",
            "  font-size: 14px;",
            "  display: none;",
            "}",
            ".niv-sf-item.niv-sf-applied .niv-sf-item-check { display: inline; }",
            ".niv-sf-actions {",
            "  display: flex;",
            "  gap: 8px;",
            "}",
            ".niv-sf-btn {",
            "  padding: 6px 14px;",
            "  border-radius: 6px;",
            "  font-size: 12px;",
            "  font-weight: 600;",
            "  cursor: pointer;",
            "  border: none;",
            "  transition: all 0.2s ease;",
            "}",
            ".niv-sf-btn-apply {",
            "  background: #7c3aed;",
            "  color: #fff;",
            "}",
            ".niv-sf-btn-apply:hover { background: #6d28d9; }",
            ".niv-sf-btn-dismiss {",
            "  background: transparent;",
            "  color: #9f9bb0;",
            "  border: 1px solid #9f9bb044;",
            "}",
            ".niv-sf-btn-dismiss:hover { color: #e2e0ea; border-color: #e2e0ea44; }",
        ].join("\n");
        document.head.appendChild(style);
    }

    // ─── Load Config ───────────────────────────────────────────
    function loadConfig(callback) {
        if (ENABLED_DOCTYPES !== null) {
            callback();
            return;
        }
        frappe.call({
            method: "niv_ai.niv_core.api.smart_fill.get_smart_fill_config",
            async: true,
            callback: function(r) {
                if (r && r.message) {
                    ENABLED_DOCTYPES = r.message.enabled_doctypes || [];
                } else {
                    ENABLED_DOCTYPES = [];
                }
                callback();
            },
            error: function() {
                ENABLED_DOCTYPES = [];
                callback();
            }
        });
    }

    // ─── Fetch Suggestions ─────────────────────────────────────
    function fetchSuggestions(doctype, triggerField, triggerValue) {
        if (!doctype || !triggerField || !triggerValue) return;

        // Collect currently filled values
        var existingValues = {};
        if (cur_frm) {
            var fields = cur_frm.fields_dict;
            for (var fname in fields) {
                var val = cur_frm.doc[fname];
                if (val) existingValues[fname] = val;
            }
        }

        frappe.call({
            method: "niv_ai.niv_core.api.smart_fill.get_suggestions",
            args: {
                doctype: doctype,
                trigger_field: triggerField,
                trigger_value: triggerValue,
                existing_values: JSON.stringify(existingValues),
            },
            async: true,
            callback: function(r) {
                if (r && r.message && r.message.suggestions && r.message.suggestions.length) {
                    showSuggestionPanel(r.message.suggestions, doctype);
                }
            },
            error: function() { /* Silent fail */ }
        });
    }

    // ─── Show Panel ────────────────────────────────────────────
    function showSuggestionPanel(suggestions, doctype) {
        removeSuggestionPanel();

        var panel = document.createElement("div");
        panel.className = "niv-sf-panel";
        panel.id = "niv-smart-fill-panel";

        // Header
        var header = document.createElement("div");
        header.className = "niv-sf-header";
        header.innerHTML =
            '<span class="niv-sf-title">✨ Smart Suggestions (based on ' +
            suggestions[0].based_on + ' past records)</span>' +
            '<button class="niv-sf-close" title="Dismiss">&times;</button>';
        panel.appendChild(header);

        header.querySelector(".niv-sf-close").addEventListener("click", function() {
            removeSuggestionPanel();
        });

        // Items
        var items = document.createElement("div");
        items.className = "niv-sf-items";

        for (var i = 0; i < suggestions.length; i++) {
            (function(sug) {
                var item = document.createElement("div");
                item.className = "niv-sf-item";
                item.setAttribute("data-fieldname", sug.fieldname);
                item.setAttribute("data-value", sug.value);
                item.innerHTML =
                    '<span class="niv-sf-item-check">✓</span>' +
                    '<div>' +
                    '<div class="niv-sf-item-label">' + escapeHtml(sug.label) + '</div>' +
                    '<div class="niv-sf-item-value">' + escapeHtml(sug.display_value || sug.value) + '</div>' +
                    '</div>' +
                    '<span class="niv-sf-item-confidence">' + sug.confidence + '%</span>';

                // Click individual item to toggle
                item.addEventListener("click", function() {
                    if (item.classList.contains("niv-sf-applied")) {
                        // Unapply
                        item.classList.remove("niv-sf-applied");
                        if (cur_frm) {
                            cur_frm.set_value(sug.fieldname, "");
                        }
                    } else {
                        // Apply
                        item.classList.add("niv-sf-applied");
                        if (cur_frm) {
                            cur_frm.set_value(sug.fieldname, sug.value);
                        }
                    }
                });

                items.appendChild(item);
            })(suggestions[i]);
        }
        panel.appendChild(items);

        // Action buttons
        var actions = document.createElement("div");
        actions.className = "niv-sf-actions";

        var applyAll = document.createElement("button");
        applyAll.className = "niv-sf-btn niv-sf-btn-apply";
        applyAll.textContent = "Apply All (" + suggestions.length + ")";
        applyAll.addEventListener("click", function() {
            if (!cur_frm) return;
            var allItems = panel.querySelectorAll(".niv-sf-item");
            for (var j = 0; j < allItems.length; j++) {
                var fn = allItems[j].getAttribute("data-fieldname");
                var fv = allItems[j].getAttribute("data-value");
                cur_frm.set_value(fn, fv);
                allItems[j].classList.add("niv-sf-applied");
            }
            // Flash green then dismiss
            applyAll.textContent = "✓ Applied!";
            applyAll.style.background = "#059669";
            setTimeout(function() {
                removeSuggestionPanel();
            }, 1500);
        });
        actions.appendChild(applyAll);

        var dismiss = document.createElement("button");
        dismiss.className = "niv-sf-btn niv-sf-btn-dismiss";
        dismiss.textContent = "Dismiss";
        dismiss.addEventListener("click", function() {
            removeSuggestionPanel();
        });
        actions.appendChild(dismiss);

        panel.appendChild(actions);

        // Insert after form-page header (before fields)
        var formLayout = document.querySelector(".form-layout");
        if (formLayout) {
            formLayout.insertBefore(panel, formLayout.firstChild);
        } else {
            // Fallback
            var formPage = document.querySelector(".form-page .page-body .layout-main-section");
            if (formPage) {
                formPage.insertBefore(panel, formPage.firstChild);
            }
        }

        _active_panel = panel;

        // Animate in
        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                panel.classList.add("niv-sf-visible");
            });
        });

        // Auto-dismiss after 30s
        setTimeout(function() {
            removeSuggestionPanel();
        }, 30000);
    }

    function removeSuggestionPanel() {
        if (_active_panel) {
            _active_panel.classList.remove("niv-sf-visible");
            var p = _active_panel;
            setTimeout(function() {
                if (p && p.parentNode) p.parentNode.removeChild(p);
            }, 300);
            _active_panel = null;
        }
        var existing = document.getElementById("niv-smart-fill-panel");
        if (existing && existing.parentNode) {
            existing.parentNode.removeChild(existing);
        }
    }

    // ─── Hook into Frappe Form ─────────────────────────────────
    function hookForms() {
        // Listen for field value changes on all forms
        $(document).on("change", ".frappe-control[data-fieldtype='Link'] input", function() {
            var $input = $(this);
            var value = $input.val();
            if (!value || !cur_frm) return;

            var $control = $input.closest(".frappe-control");
            var fieldname = $control.attr("data-fieldname");
            if (!fieldname) return;

            onFieldChange(cur_frm.doctype, fieldname, value);
        });

        // Also hook cur_frm.script_manager for programmatic changes
        if (typeof frappe.ui !== "undefined" && frappe.ui.form) {
            var origTrigger = frappe.ui.form.Form.prototype.script_manager
                ? frappe.ui.form.Form.prototype.trigger
                : null;

            // Use frappe form events
            $(document).on("form-load form-refresh", function() {
                if (!cur_frm) return;
                hookCurrentForm();
            });
        }
    }

    function hookCurrentForm() {
        if (!cur_frm || !cur_frm.doctype) return;

        // Check if this DocType is enabled
        loadConfig(function() {
            if (!ENABLED_DOCTYPES || ENABLED_DOCTYPES.indexOf(cur_frm.doctype) === -1) return;

            // Hook into Link field changes
            var fields = cur_frm.fields_dict;
            for (var fname in fields) {
                var df = fields[fname].df;
                if (df && df.fieldtype === "Link") {
                    (function(fieldname) {
                        cur_frm.fields_dict[fieldname].$input &&
                        cur_frm.fields_dict[fieldname].$input.on("change", function() {
                            var val = cur_frm.doc[fieldname];
                            if (val) {
                                onFieldChange(cur_frm.doctype, fieldname, val);
                            }
                        });
                    })(fname);
                }
            }
        });
    }

    function onFieldChange(doctype, fieldname, value) {
        // Debounce
        if (_debounce_timer) clearTimeout(_debounce_timer);
        _debounce_timer = setTimeout(function() {
            loadConfig(function() {
                if (ENABLED_DOCTYPES && ENABLED_DOCTYPES.indexOf(doctype) !== -1) {
                    fetchSuggestions(doctype, fieldname, value);
                }
            });
        }, 500);
    }

    // ─── Utilities ─────────────────────────────────────────────
    function escapeHtml(str) {
        if (!str) return "";
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ─── Public API ────────────────────────────────────────────
    window.NivSmartFill = {
        test: function(doctype, field, value) {
            doctype = doctype || (cur_frm ? cur_frm.doctype : "Sales Invoice");
            field = field || "customer";
            value = value || (cur_frm ? cur_frm.doc[field] : "");
            if (!value) {
                console.log("[NivSmartFill] No value to test. Pass value or fill the field first.");
                return;
            }
            console.log("[NivSmartFill] Testing:", doctype, field, value);
            fetchSuggestions(doctype, field, value);
        },
        dismiss: removeSuggestionPanel,
        version: "1.0.0",
    };

    // ─── Init ──────────────────────────────────────────────────
    function init() {
        injectStyles();
        hookForms();

        // Hook into frappe form events
        frappe.router && frappe.router.on && frappe.router.on("change", function() {
            setTimeout(function() {
                if (cur_frm) hookCurrentForm();
            }, 500);
        });

        // Also hook on page change
        $(document).on("page-change", function() {
            setTimeout(function() {
                if (cur_frm) hookCurrentForm();
            }, 500);
        });

        console.log("[NivSmartFill] v1.0.0 loaded ✓");
    }

    if (typeof frappe !== "undefined" && frappe.ready) {
        frappe.ready(init);
    } else {
        document.addEventListener("DOMContentLoaded", function() {
            setTimeout(init, 1000);
        });
    }
})();
