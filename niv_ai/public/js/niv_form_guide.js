/**
 * Niv AI Form Guide v2.0
 * 
 * Reads ANY message (mandatory, validation, permission, link error, custom)
 * and intelligently guides the user to the right field.
 * 
 * Message-first approach: parse the message text → find field(s) → scroll + highlight + tooltip
 * 
 * Pure client-side JS — zero API calls, zero AI cost, instant.
 * Safe: original frappe.msgprint/throw run first, we only add guidance after.
 */
(function() {
    "use strict";

    // ─── Config ────────────────────────────────────────────────
    var HIGHLIGHT_COLOR = "#7c3aed";
    var HIGHLIGHT_MS = 6000;
    var TOOLTIP_MS = 8000;
    var DEBOUNCE_MS = 300;

    // ─── State ─────────────────────────────────────────────────
    var _lastTrigger = 0;
    var _highlights = [];
    var _tooltips = [];
    var _hooked = false;

    // ─── CSS ───────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById("niv-fg2-css")) return;
        var s = document.createElement("style");
        s.id = "niv-fg2-css";
        s.textContent = [
            "@keyframes nivPulse{0%,100%{box-shadow:0 0 8px 2px " + HIGHLIGHT_COLOR + "55}50%{box-shadow:0 0 18px 6px " + HIGHLIGHT_COLOR + "88}}",
            ".niv-hl{animation:nivPulse 1.2s ease-in-out infinite;border-radius:6px;position:relative;z-index:1}",
            ".niv-hl input,.niv-hl select,.niv-hl .ql-editor,.niv-hl .link-field,.niv-hl .control-input,.niv-hl .control-input-wrapper{border-color:" + HIGHLIGHT_COLOR + " !important}",
            ".niv-tip{position:absolute;left:0;right:0;background:#1e1b2e;color:#e2e0ea;padding:10px 14px 10px 12px;border-radius:8px;font-size:13px;line-height:1.5;z-index:1050;box-shadow:0 4px 20px rgba(124,58,237,.2);border:1px solid " + HIGHLIGHT_COLOR + "44;margin-top:4px;opacity:0;transform:translateY(-6px);transition:opacity .25s,transform .25s}",
            ".niv-tip.niv-show{opacity:1;transform:translateY(0)}",
            ".niv-tip-x{position:absolute;top:4px;right:8px;cursor:pointer;color:#9f9bb0;font-size:16px;line-height:1;border:none;background:none;padding:2px 4px}",
            ".niv-tip-x:hover{color:#fff}"
        ].join("\n");
        document.head.appendChild(s);
    }

    // ─── Clear Previous ────────────────────────────────────────
    function clearAll() {
        var i;
        for (i = 0; i < _highlights.length; i++) {
            _highlights[i].classList.remove("niv-hl");
        }
        _highlights = [];
        for (i = 0; i < _tooltips.length; i++) {
            if (_tooltips[i].parentNode) _tooltips[i].parentNode.removeChild(_tooltips[i]);
        }
        _tooltips = [];
    }

    // ─── Parse Message — Extract Field Names ───────────────────
    // This is the CORE — reads any message and finds field names in it.

    function extractFieldNames(msg) {
        if (!msg || typeof msg !== "string") return { fields: [], type: "unknown", raw: "" };

        // Strip HTML but remember list items (they are field names in mandatory errors)
        var raw = msg;

        // 1. Frappe mandatory format: "Mandatory fields required in DocType<br><br><ul><li>Field1</li><li>Field2</li></ul>"
        var liMatches = msg.match(/<li[^>]*>(.*?)<\/li>/gi);
        if (liMatches && liMatches.length > 0) {
            var fields = [];
            for (var i = 0; i < liMatches.length; i++) {
                var text = liMatches[i].replace(/<[^>]*>/g, "").trim();
                if (text) {
                    // Handle "Row #3: FieldName" inside <li>
                    var rowMatch = text.match(/^Row\s*#?\s*(\d+)\s*[:]\s*(.+)/i);
                    if (rowMatch) {
                        fields.push({ label: rowMatch[2].trim(), row: parseInt(rowMatch[1]) });
                    } else {
                        fields.push({ label: text, row: null });
                    }
                }
            }
            if (fields.length > 0) {
                return { fields: fields, type: "mandatory", raw: raw };
            }
        }

        // Now strip all HTML for remaining patterns
        var clean = msg.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
        if (!clean) return { fields: [], type: "unknown", raw: raw };

        var m, result;

        // 2. "Mandatory: Field1, Field2" (simple format)
        m = clean.match(/(?:mandatory|required)\s*[:：]\s*(.+)/i);
        if (m) {
            return {
                fields: splitFieldNames(m[1]),
                type: "mandatory",
                raw: clean
            };
        }

        // 3. "Row #N: Field is required" or "Row #N: Mandatory: Field"
        m = clean.match(/Row\s*#?\s*(\d+)\s*[:]\s*(?:mandatory\s*[:：]\s*)?(.+?)(?:\s+is\s+required|\s+is\s+mandatory)?$/i);
        if (m) {
            return {
                fields: [{ label: m[2].trim(), row: parseInt(m[1]) }],
                type: "mandatory",
                raw: clean
            };
        }

        // 4. "FieldName is required" / "FieldName cannot be empty" / "FieldName is mandatory"
        m = clean.match(/^(.+?)\s+(?:is\s+required|cannot\s+be\s+empty|is\s+mandatory|must\s+be\s+filled|must\s+not\s+be\s+empty)/i);
        if (m) {
            return {
                fields: [{ label: m[1].trim(), row: null }],
                type: "mandatory",
                raw: clean
            };
        }

        // 5. "Value missing for: FieldName"
        m = clean.match(/value\s+missing\s+for\s*[:：]\s*(.+)/i);
        if (m) {
            return {
                fields: splitFieldNames(m[1]),
                type: "mandatory",
                raw: clean
            };
        }

        // 6. "Could not find FieldLabel" (link validation error)
        m = clean.match(/could\s+not\s+find\s+(.+)/i);
        if (m) {
            return {
                fields: splitFieldNames(m[1]),
                type: "link_error",
                raw: clean
            };
        }

        // 7. "Cannot link cancelled document: FieldLabel"
        m = clean.match(/cannot\s+link\s+cancelled\s+document\s*[:：]\s*(.+)/i);
        if (m) {
            return {
                fields: splitFieldNames(m[1]),
                type: "link_error",
                raw: clean
            };
        }

        // 8. Negative value — "Negative Value" title with field in message
        if (/negative\s+value/i.test(clean)) {
            // Try to find field name — usually in format "Value cannot be negative for FieldName"
            m = clean.match(/(?:for|of|in)\s+(.+?)(?:\s+in\s+row|\s*$)/i);
            if (m) {
                return {
                    fields: [{ label: m[1].trim(), row: null }],
                    type: "validation",
                    raw: clean
                };
            }
        }

        // 9. "Invalid FieldName" / "Wrong FieldName" / "Incorrect FieldName"
        m = clean.match(/(?:invalid|wrong|incorrect)\s+(.+?)(?:\s+format|\s+value|\s+in\s+row|$)/i);
        if (m && m[1].length < 60) {
            return {
                fields: [{ label: m[1].trim(), row: null }],
                type: "validation",
                raw: clean
            };
        }

        // 10. "Please enter FieldName" / "Please set FieldName" / "Please select FieldName"
        m = clean.match(/please\s+(?:enter|set|select|fill|provide|specify)\s+(.+?)(?:\s+first|\s+before|\s+in\s+row|\s*[.]|$)/i);
        if (m && m[1].length < 60) {
            return {
                fields: [{ label: m[1].trim(), row: null }],
                type: "mandatory",
                raw: clean
            };
        }

        // 11. "FieldName must be ..." (validation)
        m = clean.match(/^(.+?)\s+must\s+be\s+/i);
        if (m && m[1].length < 50) {
            return {
                fields: [{ label: m[1].trim(), row: null }],
                type: "validation",
                raw: clean
            };
        }

        // 12. "FieldName should be ..." / "FieldName needs to be ..."
        m = clean.match(/^(.+?)\s+(?:should|needs?\s+to)\s+be\s+/i);
        if (m && m[1].length < 50) {
            return {
                fields: [{ label: m[1].trim(), row: null }],
                type: "validation",
                raw: clean
            };
        }

        // 13. Permission messages
        if (/not\s+permitted|permission\s+denied|access\s+denied|no\s+permission/i.test(clean)) {
            return { fields: [], type: "permission", raw: clean };
        }

        // 14. Generic — try to find any field name mentioned in the message
        // Last resort: scan message for known field labels on current form
        if (typeof cur_frm !== "undefined" && cur_frm) {
            var foundFields = findFieldNamesInText(clean);
            if (foundFields.length > 0) {
                return {
                    fields: foundFields,
                    type: "general",
                    raw: clean
                };
            }
        }

        return { fields: [], type: "unknown", raw: clean };
    }

    function splitFieldNames(str) {
        var parts = str.split(/[,،;]+/);
        var result = [];
        for (var i = 0; i < parts.length; i++) {
            var t = parts[i].trim();
            if (t) result.push({ label: t, row: null });
        }
        return result;
    }

    // Scan message text for any field label that exists on the current form
    function findFieldNamesInText(text) {
        if (!cur_frm || !text) return [];
        var textLower = text.toLowerCase();
        var found = [];
        var fields = cur_frm.fields_dict;
        for (var fname in fields) {
            var df = fields[fname].df;
            if (!df || !df.label) continue;
            // Skip layout fields
            if (df.fieldtype === "Section Break" || df.fieldtype === "Column Break" ||
                df.fieldtype === "Tab Break" || df.fieldtype === "HTML") continue;
            var label = df.label.toLowerCase();
            if (label.length < 3) continue; // Skip very short labels to avoid false matches
            if (textLower.indexOf(label) !== -1) {
                found.push({ label: df.label, row: null });
            }
        }
        return found;
    }

    // ─── Find Field on Form ────────────────────────────────────
    function findField(label, rowNum) {
        if (!cur_frm || !label) return null;
        var searchLabel = label.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
        if (!searchLabel) return null;

        var fname, field, df, fLabel, fName;

        // First pass: exact match on label or fieldname
        for (fname in cur_frm.fields_dict) {
            field = cur_frm.fields_dict[fname];
            df = field.df || {};
            fLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            fName = (df.fieldname || "").toLowerCase();

            if (fLabel === searchLabel || fName === searchLabel) {
                if (rowNum && df.fieldtype === "Table" && field.grid) {
                    return findInChildTable(field.grid, rowNum, label);
                }
                if (field.$wrapper && field.$wrapper.length) {
                    return { el: field.$wrapper[0], field: field, df: df };
                }
            }
        }

        // Second pass: partial match (contains)
        for (fname in cur_frm.fields_dict) {
            field = cur_frm.fields_dict[fname];
            df = field.df || {};
            fLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            fName = (df.fieldname || "").toLowerCase();

            if (!fLabel && !fName) continue;
            if (fLabel.indexOf(searchLabel) !== -1 || searchLabel.indexOf(fLabel) !== -1 ||
                fName.indexOf(searchLabel) !== -1 || searchLabel.indexOf(fName) !== -1) {
                if (rowNum && df.fieldtype === "Table" && field.grid) {
                    return findInChildTable(field.grid, rowNum, label);
                }
                if (field.$wrapper && field.$wrapper.length) {
                    return { el: field.$wrapper[0], field: field, df: df };
                }
            }
        }

        // If rowNum specified, search all child tables
        if (rowNum) {
            for (fname in cur_frm.fields_dict) {
                field = cur_frm.fields_dict[fname];
                if ((field.df || {}).fieldtype === "Table" && field.grid) {
                    var found = findInChildTable(field.grid, rowNum, label);
                    if (found) return found;
                }
            }
        }
        return null;
    }

    function findInChildTable(grid, rowNum, label) {
        var searchLabel = label.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
        var rows = grid.grid_rows || [];
        var row = rows[rowNum - 1]; // 1-indexed
        if (!row) return null;

        // Open row if collapsed
        try { row.toggle_view(true); } catch(e) {}

        var rowFields = row.columns || row.fields_dict || {};
        var fn, rf, rdf, rl, rn, el;
        for (fn in rowFields) {
            rf = rowFields[fn];
            rdf = rf.df || {};
            rl = (rdf.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            rn = (rdf.fieldname || "").toLowerCase();
            if (rl === searchLabel || rn === searchLabel ||
                rl.indexOf(searchLabel) !== -1 || searchLabel.indexOf(rl) !== -1) {
                el = rf.$wrapper ? rf.$wrapper[0] : rf.wrapper;
                if (el) return { el: el, field: rf, df: rdf, row: rowNum };
            }
        }
        return null;
    }

    // ─── Highlight + Scroll + Tooltip ──────────────────────────
    function highlight(target) {
        if (!target || !target.el) return;
        target.el.classList.add("niv-hl");
        _highlights.push(target.el);
        setTimeout(function() {
            target.el.classList.remove("niv-hl");
            _highlights = _highlights.filter(function(e) { return e !== target.el; });
        }, HIGHLIGHT_MS);
    }

    function scrollTo(target) {
        if (!target || !target.el) return;
        target.el.scrollIntoView({ behavior: "smooth", block: "center" });
        // Focus input after scroll
        setTimeout(function() {
            var inp = target.el.querySelector("input:not([type=hidden]), select, textarea, .ql-editor, [contenteditable]");
            if (inp) try { inp.focus(); } catch(e) {}
        }, 400);
    }

    function showTip(target, text) {
        if (!target || !target.el) return;
        var el = target.el;

        // Remove existing
        var old = el.querySelector(".niv-tip");
        if (old) old.remove();

        var tip = document.createElement("div");
        tip.className = "niv-tip";
        tip.innerHTML = escapeHtml(text) + '<button class="niv-tip-x" title="Close">&times;</button>';

        var origPos = getComputedStyle(el).position;
        if (origPos === "static") el.style.position = "relative";

        el.appendChild(tip);
        _tooltips.push(tip);

        // Animate in
        requestAnimationFrame(function() {
            requestAnimationFrame(function() { tip.classList.add("niv-show"); });
        });

        // Close button
        tip.querySelector(".niv-tip-x").addEventListener("click", function() {
            removeTip(tip, el, origPos);
        });

        // Auto-dismiss
        setTimeout(function() { removeTip(tip, el, origPos); }, TOOLTIP_MS);
    }

    function removeTip(tip, el, origPos) {
        tip.classList.remove("niv-show");
        setTimeout(function() {
            if (tip.parentNode) tip.parentNode.removeChild(tip);
            if (origPos === "static" && el) el.style.position = "";
            _tooltips = _tooltips.filter(function(t) { return t !== tip; });
        }, 250);
    }

    // ─── Build Tooltip Message ─────────────────────────────────
    function buildTipMessage(fieldLabel, type, rawMessage) {
        var icon = { mandatory: "📝", validation: "⚠️", link_error: "🔗", permission: "🔒", general: "💡" };
        var prefix = icon[type] || "💡";

        if (type === "mandatory") {
            return prefix + " " + fieldLabel + " is required. Please fill this field.";
        }
        if (type === "link_error") {
            return prefix + " " + fieldLabel + " has an invalid link. Please check the value.";
        }
        if (type === "validation") {
            return prefix + " Please check " + fieldLabel + ". " + (rawMessage.length < 120 ? rawMessage : "");
        }
        if (type === "permission") {
            return prefix + " You don't have permission. Contact your administrator.";
        }
        // General — show the raw message
        return prefix + " " + (rawMessage.length < 150 ? rawMessage : fieldLabel + " needs attention.");
    }

    // ─── Main Guide Function ───────────────────────────────────
    function guide(msg) {
        // Debounce
        var now = Date.now();
        if (now - _lastTrigger < DEBOUNCE_MS) return;
        _lastTrigger = now;

        if (typeof cur_frm === "undefined" || !cur_frm) return;

        var parsed = extractFieldNames(msg);
        if (!parsed.fields.length && parsed.type !== "permission") return;

        clearAll();

        // Permission — no specific field, show near header
        if (parsed.type === "permission") {
            var header = document.querySelector(".form-page .page-head, .page-header, .form-message");
            if (header) {
                showTip({ el: header }, buildTipMessage("", "permission", parsed.raw));
                header.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            return;
        }

        var scrolled = false;
        for (var i = 0; i < parsed.fields.length; i++) {
            var info = parsed.fields[i];
            if (!info.label) continue;

            var target = findField(info.label, info.row);
            if (!target) continue;

            highlight(target);

            // First field gets scroll + tooltip
            if (!scrolled) {
                scrollTo(target);
                var tipMsg = buildTipMessage(info.label, parsed.type, parsed.raw);
                showTip(target, tipMsg);
                scrolled = true;
            }
        }
    }

    // ─── Hook Frappe Functions ──────────────────────────────────
    // SAFE: original functions run FIRST, then we add guidance.

    function hookFrappe() {
        if (_hooked) return;
        _hooked = true;

        // 1. Hook frappe.msgprint
        var origMsgprint = frappe.msgprint;
        frappe.msgprint = function(msg, title) {
            var result = origMsgprint.apply(this, arguments);
            try {
                var text = "";
                if (typeof msg === "string") {
                    text = msg;
                } else if (msg && typeof msg === "object") {
                    text = msg.message || msg.msg || msg.body || "";
                    // Also check title for context
                    if (!text && msg.title) text = msg.title;
                }
                if (text) setTimeout(function() { guide(text); }, 150);
            } catch(e) { /* Never break original flow */ }
            return result;
        };

        // 2. Hook frappe.throw
        var origThrow = frappe.throw;
        frappe.throw = function(msg) {
            try {
                var text = "";
                if (typeof msg === "string") {
                    text = msg;
                } else if (msg && typeof msg === "object") {
                    text = msg.message || msg.msg || "";
                }
                if (text) setTimeout(function() { guide(text); }, 150);
            } catch(e) { /* Never break original flow */ }
            return origThrow.apply(this, arguments);
        };

        // 3. Hook frappe.show_alert (lighter messages)
        if (frappe.show_alert) {
            var origAlert = frappe.show_alert;
            frappe.show_alert = function(msg, seconds) {
                var result = origAlert.apply(this, arguments);
                try {
                    var text = "";
                    if (typeof msg === "string") {
                        text = msg;
                    } else if (msg && typeof msg === "object") {
                        text = msg.message || msg.body || "";
                    }
                    // Only guide on red/orange alerts (errors/warnings)
                    if (text && msg && (msg.indicator === "red" || msg.indicator === "orange")) {
                        setTimeout(function() { guide(text); }, 150);
                    }
                } catch(e) {}
                return result;
            };
        }

        // 4. Watch for .has-error class additions
        var observer = new MutationObserver(function(mutations) {
            for (var m = 0; m < mutations.length; m++) {
                if (mutations[m].type !== "attributes" || mutations[m].attributeName !== "class") continue;
                var el = mutations[m].target;
                if (!el.classList || !el.classList.contains("has-error")) continue;
                var wrapper = el.closest(".frappe-control");
                if (!wrapper) continue;
                var labelEl = wrapper.querySelector(".control-label, label");
                if (!labelEl) continue;
                var label = labelEl.textContent.trim();
                if (label) {
                    (function(l) {
                        setTimeout(function() { guide("Mandatory: " + l); }, 200);
                    })(label);
                }
            }
        });

        var body = document.getElementById("body") || document.body;
        observer.observe(body, { attributes: true, attributeFilter: ["class"], subtree: true });
    }

    // ─── Utility ───────────────────────────────────────────────
    function escapeHtml(str) {
        var d = document.createElement("div");
        d.textContent = str || "";
        return d.innerHTML;
    }

    // ─── Public API ────────────────────────────────────────────
    window.NivFormGuide = {
        guide: guide,
        test: function(msg) {
            msg = msg || 'Mandatory fields required in Sales Invoice<br><br><ul><li>Customer</li><li>Posting Date</li></ul>';
            console.log("[NivFormGuide] Testing:", msg);
            guide(msg);
        },
        parse: function(msg) {
            console.log("[NivFormGuide] Parse result:", extractFieldNames(msg));
        },
        clear: clearAll,
        version: "2.0.0"
    };

    // ─── Init ──────────────────────────────────────────────────
    function init() {
        injectStyles();
        hookFrappe();
        console.log("[NivFormGuide] v2.0.0 loaded");
    }

    if (typeof frappe !== "undefined" && frappe.ready) {
        frappe.ready(init);
    } else {
        document.addEventListener("DOMContentLoaded", function() {
            setTimeout(init, 1000);
        });
    }
})();
