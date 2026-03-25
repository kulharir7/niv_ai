/**
 * Niv AI Form Guide v4.0 — AI-Powered
 * 
 * Sends error message + form fields to AI → AI understands what happened →
 * AI tells which field(s) need attention → JS guides user there.
 * 
 * Fallback: If AI is slow or fails, uses basic regex parsing.
 * 
 * Flow:
 * 1. Error message appears (frappe.msgprint/throw)
 * 2. Collect current form's field list
 * 3. Send to AI API (fast model, ~1-2 sec)
 * 4. AI returns: which fields, what type, user-friendly message
 * 5. Scroll + highlight + show AI's message as tooltip
 */
(function() {
    "use strict";

    var HIGHLIGHT_COLOR = "#7c3aed";
    var HIGHLIGHT_MS = 6000;
    var TOOLTIP_MS = 10000;
    var DEBOUNCE_MS = 500;

    var _lastTrigger = 0;
    var _highlights = [];
    var _tooltips = [];
    var _hooked = false;
    var _pendingCall = null;

    // ─── CSS ───────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById("niv-fg4-css")) return;
        var s = document.createElement("style");
        s.id = "niv-fg4-css";
        s.textContent = [
            "@keyframes nivPulse{0%,100%{box-shadow:0 0 8px 2px " + HIGHLIGHT_COLOR + "55}50%{box-shadow:0 0 18px 6px " + HIGHLIGHT_COLOR + "88}}",
            ".niv-hl{animation:nivPulse 1.2s ease-in-out infinite;border-radius:6px;position:relative;z-index:1}",
            ".niv-hl input,.niv-hl select,.niv-hl .ql-editor,.niv-hl .link-field,.niv-hl .control-input,.niv-hl .control-input-wrapper{border-color:" + HIGHLIGHT_COLOR + " !important}",
            ".niv-tip{position:absolute;left:0;right:0;background:linear-gradient(135deg,#1e1b2e,#2d2640);color:#e2e0ea;padding:12px 16px 12px 14px;border-radius:10px;font-size:13px;line-height:1.6;z-index:1050;box-shadow:0 6px 24px rgba(124,58,237,.25);border:1px solid " + HIGHLIGHT_COLOR + "44;margin-top:6px;opacity:0;transform:translateY(-8px);transition:opacity .3s,transform .3s}",
            ".niv-tip.niv-show{opacity:1;transform:translateY(0)}",
            ".niv-tip-x{position:absolute;top:6px;right:10px;cursor:pointer;color:#9f9bb0;font-size:16px;line-height:1;border:none;background:none;padding:2px 4px}",
            ".niv-tip-x:hover{color:#fff}",
            ".niv-tip-badge{display:inline-block;background:" + HIGHLIGHT_COLOR + "33;color:#c4b5fd;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle}",
            ".niv-tip-reason{color:#a5a0b8;font-size:12px;margin-top:4px}"
        ].join("\n");
        document.head.appendChild(s);
    }

    // ─── Clear ─────────────────────────────────────────────────
    function clearAll() {
        var i;
        for (i = 0; i < _highlights.length; i++) _highlights[i].classList.remove("niv-hl");
        _highlights = [];
        for (i = 0; i < _tooltips.length; i++) {
            if (_tooltips[i].parentNode) _tooltips[i].parentNode.removeChild(_tooltips[i]);
        }
        _tooltips = [];
    }

    // ─── Collect Form Fields ───────────────────────────────────
    function getFormFields() {
        if (typeof cur_frm === "undefined" || !cur_frm) return [];
        var fields = [];

        for (var fname in cur_frm.fields_dict) {
            var f = cur_frm.fields_dict[fname];
            var df = f.df || {};
            if (!df.fieldname) continue;
            // Skip layout fields
            if (/Section Break|Column Break|Tab Break|HTML|Button/.test(df.fieldtype)) continue;

            var entry = {
                fieldname: df.fieldname,
                label: df.label || df.fieldname,
                fieldtype: df.fieldtype,
                reqd: df.reqd ? 1 : 0
            };

            // For Table fields, also include child table fields
            if (df.fieldtype === "Table" && f.grid) {
                entry.parent_table = null;
                fields.push(entry);

                // Add child table fields
                var gridMeta = f.grid.grid_rows && f.grid.grid_rows.length > 0
                    ? f.grid.grid_rows[0]
                    : null;
                var childFields = (f.grid.meta && f.grid.meta.fields) || [];
                for (var j = 0; j < childFields.length; j++) {
                    var cf = childFields[j];
                    if (/Section Break|Column Break|Tab Break|HTML|Button/.test(cf.fieldtype)) continue;
                    fields.push({
                        fieldname: cf.fieldname,
                        label: cf.label || cf.fieldname,
                        fieldtype: cf.fieldtype,
                        reqd: cf.reqd ? 1 : 0,
                        parent_table: df.fieldname
                    });
                }
            } else {
                fields.push(entry);
            }
        }
        return fields;
    }

    // ─── Call AI API ───────────────────────────────────────────
    function callAI(message, callback) {
        var formFields = getFormFields();
        var doctype = cur_frm ? cur_frm.doctype : "";

        // Cancel previous pending call
        if (_pendingCall) {
            try { _pendingCall.abort(); } catch(e) {}
        }

        _pendingCall = frappe.call({
            method: "niv_ai.niv_core.api.form_guide.parse_message",
            args: {
                message: message,
                doctype: doctype,
                fields_json: JSON.stringify(formFields)
            },
            async: true,
            callback: function(r) {
                _pendingCall = null;
                if (r && r.message) {
                    callback(r.message);
                }
            },
            error: function() {
                _pendingCall = null;
                // Silently fail — user already sees the original error
            }
        });
    }

    // ─── Find Field on Form ────────────────────────────────────
    function findField(fieldname, label, rowNum, tableName) {
        if (!cur_frm) return null;

        // Strategy 1: Find by exact fieldname
        if (fieldname && cur_frm.fields_dict[fieldname]) {
            var field = cur_frm.fields_dict[fieldname];
            if (field.$wrapper && field.$wrapper.length) {
                return { el: field.$wrapper[0], field: field };
            }
        }

        // Strategy 2: If it's a child table field, find in the table
        if (tableName && rowNum) {
            var tableField = cur_frm.fields_dict[tableName];
            if (tableField && tableField.grid) {
                var result = findInChildTable(tableField.grid, rowNum, fieldname, label);
                if (result) return result;
            }
        }

        // Strategy 3: Search all child tables if row specified
        if (rowNum) {
            for (var fname in cur_frm.fields_dict) {
                var f = cur_frm.fields_dict[fname];
                if ((f.df || {}).fieldtype === "Table" && f.grid) {
                    var res = findInChildTable(f.grid, rowNum, fieldname, label);
                    if (res) return res;
                }
            }
        }

        // Strategy 4: Search by label (fuzzy)
        if (label) {
            var searchLabel = label.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            for (var fn in cur_frm.fields_dict) {
                var fld = cur_frm.fields_dict[fn];
                var df = fld.df || {};
                var fLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
                if (fLabel === searchLabel || fLabel.indexOf(searchLabel) !== -1 || searchLabel.indexOf(fLabel) !== -1) {
                    if (fld.$wrapper && fld.$wrapper.length) {
                        return { el: fld.$wrapper[0], field: fld };
                    }
                }
            }
        }

        return null;
    }

    function findInChildTable(grid, rowNum, fieldname, label) {
        var rows = grid.grid_rows || [];
        var row = rows[rowNum - 1];
        if (!row) return null;

        // Open row
        try {
            if (row.open_form) row.open_form();
            else if (row.toggle_view) row.toggle_view(true);
        } catch(e) {}

        var searchName = (fieldname || "").toLowerCase();
        var searchLabel = (label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();

        // Search in columns
        var rowFields = row.columns || row.fields_dict || {};
        for (var fn in rowFields) {
            var rf = rowFields[fn];
            var rdf = rf.df || {};
            var rn = (rdf.fieldname || "").toLowerCase();
            var rl = (rdf.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();

            if ((searchName && rn === searchName) || (searchLabel && (rl === searchLabel || rl.indexOf(searchLabel) !== -1))) {
                var el = rf.$wrapper ? rf.$wrapper[0] : rf.wrapper;
                if (el) return { el: el, field: rf, row: rowNum };
            }
        }

        // Search in open form
        if (row.form && row.form.fields_dict) {
            for (var fn2 in row.form.fields_dict) {
                var rf2 = row.form.fields_dict[fn2];
                var rdf2 = rf2.df || {};
                var rn2 = (rdf2.fieldname || "").toLowerCase();
                var rl2 = (rdf2.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();

                if ((searchName && rn2 === searchName) || (searchLabel && (rl2 === searchLabel || rl2.indexOf(searchLabel) !== -1))) {
                    var el2 = rf2.$wrapper ? rf2.$wrapper[0] : rf2.wrapper;
                    if (el2) return { el: el2, field: rf2, row: rowNum };
                }
            }
        }

        return null;
    }

    // ─── UI Actions ────────────────────────────────────────────
    function highlight(el) {
        if (!el) return;
        el.classList.add("niv-hl");
        _highlights.push(el);
        setTimeout(function() { el.classList.remove("niv-hl"); }, HIGHLIGHT_MS);
    }

    function scrollTo(el) {
        if (!el) return;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(function() {
            var inp = el.querySelector("input:not([type=hidden]), select, textarea, .ql-editor");
            if (inp) try { inp.focus(); } catch(e) {}
        }, 500);
    }

    function showTip(el, mainText, reason, aiPowered) {
        if (!el) return;
        var old = el.querySelector(".niv-tip");
        if (old) old.remove();

        var tip = document.createElement("div");
        tip.className = "niv-tip";

        var html = escapeHtml(mainText);
        if (aiPowered) {
            html += '<span class="niv-tip-badge">✨ AI</span>';
        }
        if (reason) {
            html += '<div class="niv-tip-reason">' + escapeHtml(reason) + '</div>';
        }
        html += '<button class="niv-tip-x">&times;</button>';
        tip.innerHTML = html;

        var origPos = getComputedStyle(el).position;
        if (origPos === "static") el.style.position = "relative";

        el.appendChild(tip);
        _tooltips.push(tip);

        requestAnimationFrame(function() {
            requestAnimationFrame(function() { tip.classList.add("niv-show"); });
        });

        tip.querySelector(".niv-tip-x").addEventListener("click", function() {
            tip.classList.remove("niv-show");
            setTimeout(function() {
                if (tip.parentNode) tip.parentNode.removeChild(tip);
                if (origPos === "static" && el) el.style.position = "";
            }, 250);
        });

        setTimeout(function() {
            tip.classList.remove("niv-show");
            setTimeout(function() {
                if (tip.parentNode) tip.parentNode.removeChild(tip);
                if (origPos === "static" && el) el.style.position = "";
            }, 250);
        }, TOOLTIP_MS);
    }

    // ─── Apply AI Response ─────────────────────────────────────
    function applyGuidance(data) {
        if (!data) return;
        clearAll();

        // Permission — no field, show header message
        if (data.type === "permission") {
            var hdr = document.querySelector(".page-head, .form-message");
            if (hdr) {
                showTip(hdr, "🔒 " + (data.user_message || "You don't have permission."), null, data.ai_powered);
                hdr.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            return;
        }

        if (!data.fields || !data.fields.length) return;

        var scrolled = false;

        for (var i = 0; i < data.fields.length; i++) {
            var f = data.fields[i];
            var target = findField(f.fieldname, f.label, f.row, f.table);

            if (!target) {
                // Retry after delay (child table row might be opening)
                (function(fieldInfo, isFirst, guidance) {
                    setTimeout(function() {
                        var t = findField(fieldInfo.fieldname, fieldInfo.label, fieldInfo.row, fieldInfo.table);
                        if (t) {
                            highlight(t.el);
                            if (isFirst) {
                                scrollTo(t.el);
                                var mainMsg = guidance.user_message || (fieldInfo.label + " needs attention");
                                showTip(t.el, mainMsg, fieldInfo.reason, guidance.ai_powered);
                            }
                        }
                    }, 500);
                })(f, !scrolled, data);
                if (!scrolled) scrolled = true;
                continue;
            }

            highlight(target.el);

            if (!scrolled) {
                scrollTo(target.el);
                var mainMsg = data.user_message || (f.label + " needs attention");
                showTip(target.el, mainMsg, f.reason, data.ai_powered);
                scrolled = true;
            }
        }
    }

    // ─── Main Guide ────────────────────────────────────────────
    function guide(msg) {
        var now = Date.now();
        if (now - _lastTrigger < DEBOUNCE_MS) return;
        _lastTrigger = now;

        if (typeof cur_frm === "undefined" || !cur_frm) return;
        if (!msg) return;

        // Call AI to parse the message
        callAI(msg, function(result) {
            applyGuidance(result);
        });
    }

    // ─── Hook Frappe ───────────────────────────────────────────
    function hookFrappe() {
        if (_hooked) return;
        _hooked = true;

        // Hook frappe.msgprint
        var origMsgprint = frappe.msgprint;
        frappe.msgprint = function(msg, title) {
            var result = origMsgprint.apply(this, arguments);
            try {
                var text = "";
                if (typeof msg === "string") text = msg;
                else if (msg && typeof msg === "object") text = msg.message || msg.msg || msg.body || "";
                if (text) setTimeout(function() { guide(text); }, 200);
            } catch(e) {}
            return result;
        };

        // Hook frappe.throw
        var origThrow = frappe.throw;
        frappe.throw = function(msg) {
            try {
                var text = "";
                if (typeof msg === "string") text = msg;
                else if (msg && typeof msg === "object") text = msg.message || msg.msg || "";
                if (text) setTimeout(function() { guide(text); }, 200);
            } catch(e) {}
            return origThrow.apply(this, arguments);
        };

        // Hook show_alert for red/orange
        if (frappe.show_alert) {
            var origAlert = frappe.show_alert;
            frappe.show_alert = function(msg, seconds) {
                var result = origAlert.apply(this, arguments);
                try {
                    var text = "";
                    if (typeof msg === "string") text = msg;
                    else if (msg && typeof msg === "object") text = msg.message || msg.body || "";
                    if (text && msg && (msg.indicator === "red" || msg.indicator === "orange")) {
                        setTimeout(function() { guide(text); }, 200);
                    }
                } catch(e) {}
                return result;
            };
        }
    }

    function escapeHtml(s) {
        var d = document.createElement("div");
        d.textContent = s || "";
        return d.innerHTML;
    }

    // ─── Public API ────────────────────────────────────────────
    window.NivFormGuide = {
        guide: guide,
        test: function(msg) {
            msg = msg || 'Mandatory fields required in table <b>Items</b>, Row 1<br><br><ul><li>Delivery Date</li></ul>';
            console.log("[NivFormGuide] AI-powered test:", msg);
            guide(msg);
        },
        clear: clearAll,
        version: "4.0.0"
    };

    function init() {
        injectStyles();
        hookFrappe();
        console.log("[NivFormGuide] v4.0.0 AI-powered loaded");
    }

    if (typeof frappe !== "undefined" && frappe.ready) {
        frappe.ready(init);
    } else {
        document.addEventListener("DOMContentLoaded", function() { setTimeout(init, 1000); });
    }
})();
