/**
 * Niv AI Form Guide v3.0
 * 
 * Reads ANY message and guides user to the exact field.
 * Message-first: parse message → find field → scroll + highlight + tooltip
 * 
 * Handles:
 * - "Mandatory fields required in table Items, Row 1 • Delivery Date"
 * - "Mandatory fields required in Sales Invoice • Customer • Date"
 * - "Customer is required" / "Please enter Customer"
 * - "Could not find ABC" / Link errors
 * - "No permission" / Permission errors
 * - Any message with a field name in it
 * 
 * Pure client-side JS — zero API calls, zero cost.
 * Safe: original frappe functions run first, we add guidance after.
 */
(function() {
    "use strict";

    var HIGHLIGHT_COLOR = "#7c3aed";
    var HIGHLIGHT_MS = 6000;
    var TOOLTIP_MS = 8000;
    var DEBOUNCE_MS = 300;

    var _lastTrigger = 0;
    var _highlights = [];
    var _tooltips = [];
    var _hooked = false;

    // ─── CSS ───────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById("niv-fg3-css")) return;
        var s = document.createElement("style");
        s.id = "niv-fg3-css";
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

    // ─── PARSE MESSAGE ─────────────────────────────────────────
    // This is the CORE. Reads the full message and extracts:
    // - field names (label)
    // - row number (for child table fields)
    // - error type (mandatory/validation/link/permission)
    //
    // Frappe message formats:
    // 1. "Mandatory fields required in table <b>Items</b>, Row 1<br>...<ul><li>Delivery Date</li></ul>"
    // 2. "Mandatory fields required in <b>Sales Invoice</b><br>...<ul><li>Customer</li><li>Date</li></ul>"
    // 3. "Customer is required"
    // 4. "Could not find XYZ"
    // 5. "No permission to Submit Sales Invoice"

    function parseMessage(msg) {
        if (!msg || typeof msg !== "string") return null;
        var raw = msg;

        // ── Step 1: Check for child table mandatory ──
        // Format: "Mandatory fields required in table <b>TableName</b>, Row N"
        // Followed by <li> items with field names
        var tableMatch = raw.match(/(?:mandatory\s+fields?\s+required\s+in\s+table)\s+(?:<[^>]*>)?\s*([^<,]+?)(?:<[^>]*>)?\s*,?\s*Row\s*#?\s*(\d+)/i);
        if (tableMatch) {
            var tableName = tableMatch[1].trim();
            var rowNum = parseInt(tableMatch[2]);
            var fieldNames = extractLiItems(raw);
            
            if (fieldNames.length > 0) {
                var fields = [];
                for (var i = 0; i < fieldNames.length; i++) {
                    fields.push({ label: fieldNames[i], row: rowNum, table: tableName });
                }
                return { fields: fields, type: "mandatory", row: rowNum, table: tableName };
            }
            // If no <li> items, the table name itself might be what we need to highlight
            return { fields: [{ label: tableName, row: rowNum, table: tableName }], type: "mandatory", row: rowNum, table: tableName };
        }

        // ── Step 2: Check for regular mandatory with <li> list ──
        // Format: "Mandatory fields required in <b>DocType</b><br>...<ul><li>Field1</li><li>Field2</li></ul>"
        var mandatoryMatch = raw.match(/mandatory\s+fields?\s+required/i);
        if (mandatoryMatch) {
            var fieldNames2 = extractLiItems(raw);
            // Also check for bullet character (•) which frappe sometimes uses
            if (fieldNames2.length === 0) {
                fieldNames2 = extractBulletItems(raw);
            }
            if (fieldNames2.length > 0) {
                var fields2 = [];
                for (var j = 0; j < fieldNames2.length; j++) {
                    fields2.push({ label: fieldNames2[j], row: null, table: null });
                }
                return { fields: fields2, type: "mandatory", row: null, table: null };
            }
        }

        // ── From here, strip HTML for simpler patterns ──
        var clean = raw.replace(/<[^>]*>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();

        // ── Step 3: "Mandatory: Field1, Field2" ──
        var m = clean.match(/(?:mandatory|required)\s*[:：]\s*(.+)/i);
        if (m) return { fields: splitFields(m[1]), type: "mandatory" };

        // ── Step 4: "Row #N: Field is required" ──
        m = clean.match(/Row\s*#?\s*(\d+)\s*[:]\s*(?:mandatory\s*[:：]\s*)?(.+?)(?:\s+is\s+required|\s+is\s+mandatory|\s*$)/i);
        if (m) return { fields: [{ label: m[2].trim(), row: parseInt(m[1]) }], type: "mandatory", row: parseInt(m[1]) };

        // ── Step 5: "FieldName is required / cannot be empty / is mandatory" ──
        m = clean.match(/^(.+?)\s+(?:is\s+required|cannot\s+be\s+empty|is\s+mandatory|must\s+not\s+be\s+empty)/i);
        if (m && m[1].length < 60) return { fields: [{ label: m[1].trim(), row: null }], type: "mandatory" };

        // ── Step 6: "Value missing for: Field" ──
        m = clean.match(/value\s+missing\s+for\s*[:：]\s*(.+)/i);
        if (m) return { fields: splitFields(m[1]), type: "mandatory" };

        // ── Step 7: "Please enter/set/select FieldName" ──
        m = clean.match(/please\s+(?:enter|set|select|fill|provide|specify)\s+(.+?)(?:\s+first|\s+before|\s+in\s+row|\s*[.]|$)/i);
        if (m && m[1].length < 60) return { fields: [{ label: m[1].trim(), row: null }], type: "mandatory" };

        // ── Step 8: "Could not find ..." (link validation) ──
        m = clean.match(/could\s+not\s+find\s+(.+)/i);
        if (m) return { fields: splitFields(m[1]), type: "link_error" };

        // ── Step 9: "Cannot link cancelled document: ..." ──
        m = clean.match(/cannot\s+link\s+cancelled\s+document\s*[:：]\s*(.+)/i);
        if (m) return { fields: splitFields(m[1]), type: "link_error" };

        // ── Step 10: "FieldName must be / should be ..." ──
        m = clean.match(/^(.+?)\s+(?:must|should|needs?\s+to)\s+be\s+/i);
        if (m && m[1].length < 50) return { fields: [{ label: m[1].trim(), row: null }], type: "validation" };

        // ── Step 11: "Invalid / Wrong FieldName" ──
        m = clean.match(/(?:invalid|wrong|incorrect)\s+(.+?)(?:\s+format|\s+value|\s+in\s+row|$)/i);
        if (m && m[1].length < 60) return { fields: [{ label: m[1].trim(), row: null }], type: "validation" };

        // ── Step 12: Negative value ──
        if (/negative\s+value/i.test(clean)) {
            m = clean.match(/(?:for|of|in)\s+(.+?)(?:\s+in\s+row|\s*$)/i);
            if (m) return { fields: [{ label: m[1].trim(), row: null }], type: "validation" };
        }

        // ── Step 13: Permission ──
        if (/not\s+permitted|permission\s+denied|access\s+denied|no\s+permission/i.test(clean)) {
            return { fields: [], type: "permission" };
        }

        // ── Step 14: Last resort — scan message for known field names on current form ──
        if (typeof cur_frm !== "undefined" && cur_frm) {
            var found = scanForFieldNames(clean);
            if (found.length) return { fields: found, type: "general" };
        }

        return null;
    }

    // Extract text from <li> tags
    function extractLiItems(html) {
        var items = [];
        var re = /<li[^>]*>([\s\S]*?)<\/li>/gi;
        var match;
        while ((match = re.exec(html)) !== null) {
            var text = match[1].replace(/<[^>]*>/g, "").trim();
            if (text) items.push(text);
        }
        return items;
    }

    // Extract text after bullet character (•)
    function extractBulletItems(html) {
        var clean = html.replace(/<[^>]*>/g, " ");
        var items = [];
        var parts = clean.split(/[•·]/);
        for (var i = 1; i < parts.length; i++) { // Start from 1, skip text before first bullet
            var text = parts[i].trim();
            if (text && text.length < 80) items.push(text);
        }
        return items;
    }

    function splitFields(str) {
        var parts = str.split(/[,،;]+/);
        var result = [];
        for (var i = 0; i < parts.length; i++) {
            var t = parts[i].trim();
            if (t && t.length < 80) result.push({ label: t, row: null });
        }
        return result;
    }

    // Scan message for any field label on current form
    function scanForFieldNames(text) {
        if (!cur_frm) return [];
        var textLower = text.toLowerCase();
        var found = [];
        for (var fname in cur_frm.fields_dict) {
            var df = cur_frm.fields_dict[fname].df;
            if (!df || !df.label) continue;
            if (/Section Break|Column Break|Tab Break|HTML|Button/.test(df.fieldtype)) continue;
            var label = df.label.toLowerCase();
            if (label.length < 3) continue;
            if (textLower.indexOf(label) !== -1) {
                found.push({ label: df.label, row: null });
            }
        }
        return found;
    }

    // ─── FIND FIELD ON FORM ────────────────────────────────────

    function findField(info) {
        if (!cur_frm || !info || !info.label) return null;
        var label = info.label;
        var rowNum = info.row || null;
        var tableName = info.table || null;
        var searchLabel = label.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
        if (!searchLabel) return null;

        // If we know the table name and row, search directly in that child table
        if (tableName && rowNum) {
            var tableField = findTableByLabel(tableName);
            if (tableField && tableField.grid) {
                var childResult = findInChildTable(tableField.grid, rowNum, searchLabel);
                if (childResult) return childResult;
            }
        }

        // Search all form fields
        var fname, field, df, fLabel, fName;

        // Pass 1: exact match
        for (fname in cur_frm.fields_dict) {
            field = cur_frm.fields_dict[fname];
            df = field.df || {};
            fLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            fName = (df.fieldname || "").toLowerCase();

            if (fLabel === searchLabel || fName === searchLabel) {
                if (rowNum && df.fieldtype === "Table" && field.grid) {
                    return findInChildTable(field.grid, rowNum, searchLabel);
                }
                if (field.$wrapper && field.$wrapper.length) {
                    return { el: field.$wrapper[0], field: field, df: df };
                }
            }
        }

        // Pass 2: partial match
        for (fname in cur_frm.fields_dict) {
            field = cur_frm.fields_dict[fname];
            df = field.df || {};
            fLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            fName = (df.fieldname || "").toLowerCase();
            if (!fLabel && !fName) continue;

            if ((fLabel && (fLabel.indexOf(searchLabel) !== -1 || searchLabel.indexOf(fLabel) !== -1)) ||
                (fName && (fName.indexOf(searchLabel) !== -1 || searchLabel.indexOf(fName) !== -1))) {
                if (rowNum && df.fieldtype === "Table" && field.grid) {
                    return findInChildTable(field.grid, rowNum, searchLabel);
                }
                if (field.$wrapper && field.$wrapper.length) {
                    return { el: field.$wrapper[0], field: field, df: df };
                }
            }
        }

        // Pass 3: if row specified, try ALL child tables
        if (rowNum) {
            for (fname in cur_frm.fields_dict) {
                field = cur_frm.fields_dict[fname];
                if ((field.df || {}).fieldtype === "Table" && field.grid) {
                    var res = findInChildTable(field.grid, rowNum, searchLabel);
                    if (res) return res;
                }
            }
        }

        return null;
    }

    // Find a Table field by its label (e.g., "Items")
    function findTableByLabel(tableName) {
        if (!cur_frm) return null;
        var searchName = tableName.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
        for (var fname in cur_frm.fields_dict) {
            var field = cur_frm.fields_dict[fname];
            var df = field.df || {};
            if (df.fieldtype !== "Table") continue;
            var fLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            var fName = (df.fieldname || "").toLowerCase();
            if (fLabel === searchName || fName === searchName ||
                fLabel.indexOf(searchName) !== -1 || searchName.indexOf(fLabel) !== -1) {
                return field;
            }
        }
        return null;
    }

    function findInChildTable(grid, rowNum, searchLabel) {
        var rows = grid.grid_rows || [];
        var row = rows[rowNum - 1]; // 1-indexed
        if (!row) return null;

        // Open row form if collapsed
        try {
            if (row.open_form) {
                row.open_form();
            } else if (row.toggle_view) {
                row.toggle_view(true);
            }
        } catch(e) {}

        // Wait a tick for DOM to render, then search
        var rowFields = row.columns || row.fields_dict || {};
        var fn, rf, rdf, rl, rn, el;
        for (fn in rowFields) {
            rf = rowFields[fn];
            rdf = rf.df || {};
            rl = (rdf.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            rn = (rdf.fieldname || "").toLowerCase();
            if (rl === searchLabel || rn === searchLabel ||
                (rl && (rl.indexOf(searchLabel) !== -1 || searchLabel.indexOf(rl) !== -1)) ||
                (rn && (rn.indexOf(searchLabel) !== -1 || searchLabel.indexOf(rn) !== -1))) {
                el = rf.$wrapper ? rf.$wrapper[0] : rf.wrapper;
                if (el) return { el: el, field: rf, df: rdf, row: rowNum };
            }
        }

        // Also try searching in the open form (edit area)
        if (row.form && row.form.fields_dict) {
            for (fn in row.form.fields_dict) {
                rf = row.form.fields_dict[fn];
                rdf = rf.df || {};
                rl = (rdf.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
                rn = (rdf.fieldname || "").toLowerCase();
                if (rl === searchLabel || rn === searchLabel ||
                    (rl && (rl.indexOf(searchLabel) !== -1 || searchLabel.indexOf(rl) !== -1))) {
                    el = rf.$wrapper ? rf.$wrapper[0] : rf.wrapper;
                    if (el) return { el: el, field: rf, df: rdf, row: rowNum };
                }
            }
        }

        return null;
    }

    // ─── Highlight + Scroll + Tooltip ──────────────────────────
    function highlight(el) {
        if (!el) return;
        el.classList.add("niv-hl");
        _highlights.push(el);
        setTimeout(function() {
            el.classList.remove("niv-hl");
        }, HIGHLIGHT_MS);
    }

    function scrollTo(el) {
        if (!el) return;
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(function() {
            var inp = el.querySelector("input:not([type=hidden]), select, textarea, .ql-editor, [contenteditable]");
            if (inp) try { inp.focus(); } catch(e) {}
        }, 500);
    }

    function showTip(el, text) {
        if (!el) return;
        var old = el.querySelector(".niv-tip");
        if (old) old.remove();

        var tip = document.createElement("div");
        tip.className = "niv-tip";
        tip.innerHTML = escapeHtml(text) + '<button class="niv-tip-x">&times;</button>';

        var origPos = getComputedStyle(el).position;
        if (origPos === "static") el.style.position = "relative";

        el.appendChild(tip);
        _tooltips.push(tip);

        requestAnimationFrame(function() {
            requestAnimationFrame(function() { tip.classList.add("niv-show"); });
        });

        tip.querySelector(".niv-tip-x").addEventListener("click", function() {
            removeTip(tip, el, origPos);
        });

        setTimeout(function() { removeTip(tip, el, origPos); }, TOOLTIP_MS);
    }

    function removeTip(tip, el, origPos) {
        tip.classList.remove("niv-show");
        setTimeout(function() {
            if (tip.parentNode) tip.parentNode.removeChild(tip);
            if (origPos === "static" && el) el.style.position = "";
        }, 250);
    }

    // ─── Build human-readable tooltip ──────────────────────────
    function buildTip(fieldLabel, type, rowNum) {
        var prefix = "";
        if (type === "mandatory") prefix = "📝 ";
        else if (type === "validation") prefix = "⚠️ ";
        else if (type === "link_error") prefix = "🔗 ";
        else if (type === "permission") prefix = "🔒 ";
        else prefix = "💡 ";

        var msg = prefix + fieldLabel;
        if (type === "mandatory") {
            msg += " is required.";
        } else if (type === "link_error") {
            msg += " — invalid or not found. Please check this value.";
        } else if (type === "validation") {
            msg += " — please check this value.";
        } else if (type === "permission") {
            msg = prefix + "You don't have permission. Contact your administrator.";
        } else {
            msg += " needs your attention.";
        }

        if (rowNum) {
            msg += " (Row " + rowNum + ")";
        }

        return msg;
    }

    // ─── MAIN GUIDE ────────────────────────────────────────────
    function guide(msg) {
        var now = Date.now();
        if (now - _lastTrigger < DEBOUNCE_MS) return;
        _lastTrigger = now;

        if (typeof cur_frm === "undefined" || !cur_frm) return;

        var parsed = parseMessage(msg);
        if (!parsed) return;
        if (!parsed.fields.length && parsed.type !== "permission") return;

        clearAll();

        // Permission — show near header
        if (parsed.type === "permission") {
            var hdr = document.querySelector(".page-head, .form-message, .page-header");
            if (hdr) {
                showTip(hdr, buildTip("", "permission", null));
                hdr.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            return;
        }

        var scrolled = false;

        for (var i = 0; i < parsed.fields.length; i++) {
            var info = parsed.fields[i];
            if (!info.label) continue;

            // For child table fields, add small delay for row to open
            var target = findField(info);

            if (!target) {
                // Retry after short delay (row might still be opening)
                (function(fieldInfo, isFirst) {
                    setTimeout(function() {
                        var t = findField(fieldInfo);
                        if (t) {
                            highlight(t.el);
                            if (isFirst) {
                                scrollTo(t.el);
                                showTip(t.el, buildTip(fieldInfo.label, parsed.type, fieldInfo.row));
                            }
                        }
                    }, 400);
                })(info, !scrolled);
                if (!scrolled) scrolled = true;
                continue;
            }

            highlight(target.el);

            if (!scrolled) {
                scrollTo(target.el);
                showTip(target.el, buildTip(info.label, parsed.type, info.row));
                scrolled = true;
            }
        }
    }

    // ─── HOOK FRAPPE ───────────────────────────────────────────
    function hookFrappe() {
        if (_hooked) return;
        _hooked = true;

        // Hook frappe.msgprint — SAFE, original runs first
        var origMsgprint = frappe.msgprint;
        frappe.msgprint = function(msg, title) {
            var result = origMsgprint.apply(this, arguments);
            try {
                var text = "";
                if (typeof msg === "string") text = msg;
                else if (msg && typeof msg === "object") text = msg.message || msg.msg || msg.body || "";
                if (text) setTimeout(function() { guide(text); }, 150);
            } catch(e) {}
            return result;
        };

        // Hook frappe.throw — SAFE
        var origThrow = frappe.throw;
        frappe.throw = function(msg) {
            try {
                var text = "";
                if (typeof msg === "string") text = msg;
                else if (msg && typeof msg === "object") text = msg.message || msg.msg || "";
                if (text) setTimeout(function() { guide(text); }, 150);
            } catch(e) {}
            return origThrow.apply(this, arguments);
        };

        // Hook frappe.show_alert — only on red/orange
        if (frappe.show_alert) {
            var origAlert = frappe.show_alert;
            frappe.show_alert = function(msg, seconds) {
                var result = origAlert.apply(this, arguments);
                try {
                    var text = "";
                    if (typeof msg === "string") text = msg;
                    else if (msg && typeof msg === "object") text = msg.message || msg.body || "";
                    if (text && msg && (msg.indicator === "red" || msg.indicator === "orange")) {
                        setTimeout(function() { guide(text); }, 150);
                    }
                } catch(e) {}
                return result;
            };
        }

        // Watch .has-error class
        var observer = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                if (mutations[i].attributeName !== "class") continue;
                var el = mutations[i].target;
                if (!el.classList || !el.classList.contains("has-error")) continue;
                var wrapper = el.closest(".frappe-control");
                if (!wrapper) continue;
                var labelEl = wrapper.querySelector(".control-label, label");
                if (!labelEl) continue;
                var lbl = labelEl.textContent.trim();
                if (lbl) {
                    (function(l) {
                        setTimeout(function() { guide("Mandatory: " + l); }, 200);
                    })(lbl);
                }
            }
        });
        observer.observe(document.getElementById("body") || document.body, {
            attributes: true, attributeFilter: ["class"], subtree: true
        });
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
            console.log("[NivFormGuide] Testing:", msg);
            guide(msg);
        },
        parse: function(msg) {
            var r = parseMessage(msg);
            console.log("[NivFormGuide] Parsed:", JSON.stringify(r, null, 2));
            return r;
        },
        clear: clearAll,
        version: "3.0.0"
    };

    function init() {
        injectStyles();
        hookFrappe();
        console.log("[NivFormGuide] v3.0.0 loaded");
    }

    if (typeof frappe !== "undefined" && frappe.ready) {
        frappe.ready(init);
    } else {
        document.addEventListener("DOMContentLoaded", function() { setTimeout(init, 1000); });
    }
})();
