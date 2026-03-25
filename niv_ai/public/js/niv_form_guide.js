/**
 * Niv AI Form Guide v5.0 — Smart Hybrid
 * 
 * INSTANT (0ms): Reads message + scans form fields → guides to matching field
 * BACKGROUND (2-5s): Sends to AI → if AI gives better answer, updates tooltip
 * 
 * Smart matching: No hardcoded patterns. Dynamically matches form field
 * labels/names against words in the error message.
 */
(function() {
    "use strict";

    var HIGHLIGHT_COLOR = "#7c3aed";
    var HIGHLIGHT_MS = 8000;
    var TOOLTIP_MS = 12000;
    var DEBOUNCE_MS = 400;

    var _lastTrigger = 0;
    var _highlights = [];
    var _tooltips = [];
    var _hooked = false;
    var _activeTooltipEl = null;
    var _activeTooltipData = null;

    // ─── CSS ───────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById("niv-fg5-css")) return;
        var s = document.createElement("style");
        s.id = "niv-fg5-css";
        s.textContent = [
            "@keyframes nivPulse{0%,100%{box-shadow:0 0 8px 2px " + HIGHLIGHT_COLOR + "55}50%{box-shadow:0 0 18px 6px " + HIGHLIGHT_COLOR + "88}}",
            ".niv-hl{animation:nivPulse 1.2s ease-in-out infinite;border-radius:6px;position:relative;z-index:1}",
            ".niv-hl input,.niv-hl select,.niv-hl .ql-editor,.niv-hl .link-field,.niv-hl .control-input,.niv-hl .control-input-wrapper{border-color:" + HIGHLIGHT_COLOR + " !important}",
            ".niv-tip{position:absolute;left:0;right:0;background:linear-gradient(135deg,#1e1b2e,#2d2640);color:#e2e0ea;padding:12px 16px;border-radius:10px;font-size:13px;line-height:1.6;z-index:1050;box-shadow:0 6px 24px rgba(124,58,237,.25);border:1px solid " + HIGHLIGHT_COLOR + "44;margin-top:6px;opacity:0;transform:translateY(-8px);transition:opacity .3s,transform .3s}",
            ".niv-tip.niv-show{opacity:1;transform:translateY(0)}",
            ".niv-tip-x{position:absolute;top:6px;right:10px;cursor:pointer;color:#9f9bb0;font-size:16px;line-height:1;border:none;background:none;padding:2px 4px}",
            ".niv-tip-x:hover{color:#fff}",
            ".niv-tip-badge{display:inline-block;background:" + HIGHLIGHT_COLOR + "33;color:#c4b5fd;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle}",
            ".niv-tip-msg{margin-top:0}",
            ".niv-tip-updating{opacity:0.7;transition:opacity 0.3s}"
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
        _activeTooltipEl = null;
        _activeTooltipData = null;
    }

    // ═══════════════════════════════════════════════════════════
    // PHASE 1: INSTANT SMART MATCHING (0ms)
    // No hardcoded patterns. Reads message, finds field names dynamically.
    // ═══════════════════════════════════════════════════════════

    function instantParse(msg) {
        if (!msg || typeof msg !== "string") return null;
        if (typeof cur_frm === "undefined" || !cur_frm) return null;

        // Step 1: Extract clean text + any <li> items from HTML
        var liItems = [];
        var re = /<li[^>]*>([\s\S]*?)<\/li>/gi;
        var match;
        while ((match = re.exec(msg)) !== null) {
            var t = match[1].replace(/<[^>]*>/g, "").trim();
            if (t) liItems.push(t);
        }

        // Strip HTML
        var clean = msg.replace(/<[^>]*>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
        if (!clean) return null;

        // Step 2: Detect error type from keywords
        var type = "general";
        if (/mandatory|required|missing|must\s+not\s+be\s+empty|cannot\s+be\s+empty/i.test(clean)) type = "mandatory";
        else if (/not\s+permitted|permission\s+denied|access\s+denied|no\s+permission/i.test(clean)) type = "permission";
        else if (/could\s+not\s+find|invalid\s+link|cancelled\s+document/i.test(clean)) type = "link_error";
        else if (/invalid|wrong|incorrect|negative|must\s+be|should\s+be|cannot|error/i.test(clean)) type = "validation";

        // Permission — no field to find
        if (type === "permission") {
            return { fields: [], type: "permission", message: clean };
        }

        // Step 3: Detect row number
        var rowNum = null;
        var rowMatch = clean.match(/Row\s*#?\s*(\d+)/i);
        if (rowMatch) rowNum = parseInt(rowMatch[1]);

        // Step 4: Detect table name
        var tableName = null;
        var tableMatch = clean.match(/(?:in\s+table|table)\s+([A-Za-z][A-Za-z0-9 _-]+?)(?:\s*,|\s+Row|\s*$)/i);
        if (tableMatch) tableName = tableMatch[1].trim();

        // Step 5: Find fields — use <li> items first, then scan message for field labels
        var foundFields = [];

        // 5a: If <li> items exist, those ARE the field names (Frappe standard)
        if (liItems.length > 0) {
            for (var i = 0; i < liItems.length; i++) {
                var fieldMatch = matchFieldOnForm(liItems[i], rowNum, tableName);
                if (fieldMatch) {
                    foundFields.push(fieldMatch);
                } else {
                    // Still add it even if not found on form (might be child table)
                    foundFields.push({
                        label: liItems[i],
                        fieldname: null,
                        row: rowNum,
                        table: tableName
                    });
                }
            }
        }

        // 5b: If no <li> items, scan the full message for field labels
        if (foundFields.length === 0) {
            foundFields = scanMessageForFields(clean, rowNum, tableName);
        }

        if (foundFields.length === 0) return null;

        return {
            fields: foundFields,
            type: type,
            message: clean,
            row: rowNum,
            table: tableName
        };
    }

    // Match a single field name against the current form
    function matchFieldOnForm(text, rowNum, tableName) {
        if (!cur_frm || !text) return null;
        var searchText = text.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
        if (!searchText || searchText.length < 2) return null;

        // Search main form fields
        for (var fname in cur_frm.fields_dict) {
            var field = cur_frm.fields_dict[fname];
            var df = field.df || {};
            var fLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            var fName = (df.fieldname || "").toLowerCase();

            if (fLabel === searchText || fName === searchText) {
                return {
                    label: df.label || text,
                    fieldname: df.fieldname,
                    row: (df.fieldtype === "Table") ? null : rowNum,
                    table: tableName
                };
            }
        }

        // Search child table fields (all tables)
        for (var fn2 in cur_frm.fields_dict) {
            var f2 = cur_frm.fields_dict[fn2];
            if ((f2.df || {}).fieldtype !== "Table" || !f2.grid) continue;
            var childMeta = (f2.grid.meta && f2.grid.meta.fields) || [];
            for (var c = 0; c < childMeta.length; c++) {
                var cf = childMeta[c];
                var cfLabel = (cf.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
                var cfName = (cf.fieldname || "").toLowerCase();
                if (cfLabel === searchText || cfName === searchText) {
                    return {
                        label: cf.label || text,
                        fieldname: cf.fieldname,
                        row: rowNum,
                        table: (f2.df || {}).fieldname || tableName
                    };
                }
            }
        }

        return null;
    }

    // Scan full message text for any field label on current form
    function scanMessageForFields(text, rowNum, tableName) {
        if (!cur_frm) return [];
        var textLower = text.toLowerCase();
        var found = [];
        var usedLabels = {};

        // Check all form fields
        for (var fname in cur_frm.fields_dict) {
            var df = cur_frm.fields_dict[fname].df || {};
            if (!df.label) continue;
            if (/Section Break|Column Break|Tab Break|HTML|Button|Table/.test(df.fieldtype)) continue;

            var label = df.label.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            if (label.length < 3) continue;
            if (usedLabels[label]) continue;

            if (textLower.indexOf(label) !== -1) {
                found.push({ label: df.label, fieldname: df.fieldname, row: null, table: null });
                usedLabels[label] = true;
            }
        }

        // Check child table fields too
        for (var fn2 in cur_frm.fields_dict) {
            var f2 = cur_frm.fields_dict[fn2];
            if ((f2.df || {}).fieldtype !== "Table" || !f2.grid) continue;
            var childMeta = (f2.grid.meta && f2.grid.meta.fields) || [];
            for (var c = 0; c < childMeta.length; c++) {
                var cf = childMeta[c];
                if (!cf.label) continue;
                var cfLabel = cf.label.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
                if (cfLabel.length < 3 || usedLabels[cfLabel]) continue;

                if (textLower.indexOf(cfLabel) !== -1) {
                    found.push({
                        label: cf.label,
                        fieldname: cf.fieldname,
                        row: rowNum,
                        table: (f2.df || {}).fieldname || tableName
                    });
                    usedLabels[cfLabel] = true;
                }
            }
        }

        return found;
    }

    // ═══════════════════════════════════════════════════════════
    // PHASE 2: AI ENHANCEMENT (background, 2-5s)
    // ═══════════════════════════════════════════════════════════

    function callAI(message, callback) {
        var formFields = getFormFieldsList();
        var doctype = cur_frm ? cur_frm.doctype : "";

        frappe.call({
            method: "niv_ai.niv_core.api.form_guide.parse_message",
            args: {
                message: message,
                doctype: doctype,
                fields_json: JSON.stringify(formFields)
            },
            async: true,
            callback: function(r) {
                if (r && r.message && r.message.ai_powered) {
                    callback(r.message);
                }
            },
            error: function() { /* Silent — instant guide already shown */ }
        });
    }

    function getFormFieldsList() {
        if (!cur_frm) return [];
        var fields = [];
        for (var fname in cur_frm.fields_dict) {
            var f = cur_frm.fields_dict[fname];
            var df = f.df || {};
            if (!df.fieldname) continue;
            if (/Section Break|Column Break|Tab Break|HTML|Button/.test(df.fieldtype)) continue;

            fields.push({
                fieldname: df.fieldname,
                label: df.label || df.fieldname,
                fieldtype: df.fieldtype,
                reqd: df.reqd ? 1 : 0
            });

            // Child table fields
            if (df.fieldtype === "Table" && f.grid) {
                var childMeta = (f.grid.meta && f.grid.meta.fields) || [];
                for (var j = 0; j < childMeta.length; j++) {
                    var cf = childMeta[j];
                    if (/Section Break|Column Break|Tab Break|HTML|Button/.test(cf.fieldtype)) continue;
                    fields.push({
                        fieldname: cf.fieldname,
                        label: cf.label || cf.fieldname,
                        fieldtype: cf.fieldtype,
                        reqd: cf.reqd ? 1 : 0,
                        parent_table: df.fieldname
                    });
                }
            }
        }
        return fields;
    }

    // ═══════════════════════════════════════════════════════════
    // FIND FIELD ON FORM + UI
    // ═══════════════════════════════════════════════════════════

    function findFieldElement(info) {
        if (!cur_frm || !info) return null;

        var fieldname = info.fieldname;
        var label = info.label;
        var rowNum = info.row;
        var tableName = info.table;

        // 1. Child table field
        if (tableName && rowNum) {
            var tableField = cur_frm.fields_dict[tableName];
            if (tableField && tableField.grid) {
                var r = findInChild(tableField.grid, rowNum, fieldname, label);
                if (r) return r;
            }
            // Try all tables
            for (var fn in cur_frm.fields_dict) {
                var ff = cur_frm.fields_dict[fn];
                if ((ff.df || {}).fieldtype === "Table" && ff.grid) {
                    var r2 = findInChild(ff.grid, rowNum, fieldname, label);
                    if (r2) return r2;
                }
            }
        }

        // 2. By fieldname
        if (fieldname && cur_frm.fields_dict[fieldname]) {
            var fld = cur_frm.fields_dict[fieldname];
            if (fld.$wrapper && fld.$wrapper.length) return fld.$wrapper[0];
        }

        // 3. By label (fuzzy)
        if (label) {
            var sl = label.toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
            for (var fn3 in cur_frm.fields_dict) {
                var df3 = cur_frm.fields_dict[fn3].df || {};
                var fl3 = (df3.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();
                if (fl3 === sl || (fl3 && sl && (fl3.indexOf(sl) !== -1 || sl.indexOf(fl3) !== -1))) {
                    var w = cur_frm.fields_dict[fn3].$wrapper;
                    if (w && w.length) return w[0];
                }
            }
        }

        // 4. If row but no table, try all child tables
        if (rowNum && !tableName) {
            for (var fn4 in cur_frm.fields_dict) {
                var ff4 = cur_frm.fields_dict[fn4];
                if ((ff4.df || {}).fieldtype === "Table" && ff4.grid) {
                    var r4 = findInChild(ff4.grid, rowNum, fieldname, label);
                    if (r4) return r4;
                }
            }
        }

        return null;
    }

    function findInChild(grid, rowNum, fieldname, label) {
        var rows = grid.grid_rows || [];
        var row = rows[rowNum - 1];
        if (!row) return null;

        // Open row
        try {
            if (row.open_form) row.open_form();
            else if (row.toggle_view) row.toggle_view(true);
        } catch(e) {}

        var sn = (fieldname || "").toLowerCase();
        var sl = (label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();

        // Search columns + fields_dict
        var sources = [row.columns || {}, row.fields_dict || {}];
        if (row.form && row.form.fields_dict) sources.push(row.form.fields_dict);

        for (var s = 0; s < sources.length; s++) {
            for (var fn in sources[s]) {
                var rf = sources[s][fn];
                var rdf = rf.df || {};
                var rn = (rdf.fieldname || "").toLowerCase();
                var rl = (rdf.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();

                if ((sn && rn === sn) || (sl && (rl === sl || rl.indexOf(sl) !== -1 || sl.indexOf(rl) !== -1))) {
                    var el = rf.$wrapper ? rf.$wrapper[0] : rf.wrapper;
                    if (el) return el;
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

    function showTip(el, text, aiPowered) {
        if (!el) return;
        var old = el.querySelector(".niv-tip");
        if (old) old.remove();

        var tip = document.createElement("div");
        tip.className = "niv-tip";
        var badge = aiPowered ? '<span class="niv-tip-badge">✨ AI</span>' : '';
        tip.innerHTML = '<div class="niv-tip-msg">' + escapeHtml(text) + badge + '</div>' +
                        '<button class="niv-tip-x">&times;</button>';

        var origPos = getComputedStyle(el).position;
        if (origPos === "static") el.style.position = "relative";

        el.appendChild(tip);
        _tooltips.push(tip);
        _activeTooltipEl = el;
        _activeTooltipData = { tip: tip, origPos: origPos };

        requestAnimationFrame(function() {
            requestAnimationFrame(function() { tip.classList.add("niv-show"); });
        });

        tip.querySelector(".niv-tip-x").addEventListener("click", function() {
            removeTip(tip, el, origPos);
        });

        setTimeout(function() { removeTip(tip, el, origPos); }, TOOLTIP_MS);
    }

    // Update existing tooltip with AI message
    function updateTip(text) {
        if (!_activeTooltipData || !_activeTooltipData.tip) return;
        var tip = _activeTooltipData.tip;
        var msgEl = tip.querySelector(".niv-tip-msg");
        if (!msgEl) return;

        // Fade transition
        tip.classList.add("niv-tip-updating");
        setTimeout(function() {
            msgEl.innerHTML = escapeHtml(text) + '<span class="niv-tip-badge">✨ AI</span>';
            tip.classList.remove("niv-tip-updating");
        }, 200);
    }

    function removeTip(tip, el, origPos) {
        tip.classList.remove("niv-show");
        setTimeout(function() {
            if (tip.parentNode) tip.parentNode.removeChild(tip);
            if (origPos === "static" && el) el.style.position = "";
        }, 250);
    }

    // ═══════════════════════════════════════════════════════════
    // MAIN GUIDE — Hybrid: Instant + AI
    // ═══════════════════════════════════════════════════════════

    function guide(msg) {
        var now = Date.now();
        if (now - _lastTrigger < DEBOUNCE_MS) return;
        _lastTrigger = now;

        if (typeof cur_frm === "undefined" || !cur_frm) return;
        if (!msg) return;

        // ── PHASE 1: Instant smart match ──
        var parsed = instantParse(msg);
        if (parsed) {
            clearAll();
            applyParsed(parsed, false);
        }

        // ── PHASE 2: AI enhancement (background) ──
        callAI(msg, function(aiResult) {
            if (!aiResult || !aiResult.ai_powered) return;

            // If AI found fields that instant didn't
            if (aiResult.fields && aiResult.fields.length > 0) {
                // Re-apply with AI results (better field matching)
                clearAll();
                applyAIResult(aiResult);
            } else if (aiResult.user_message) {
                // Just update the tooltip text
                updateTip(aiResult.user_message);
            }
        });
    }

    function applyParsed(parsed, isAI) {
        // Permission
        if (parsed.type === "permission") {
            var hdr = document.querySelector(".page-head, .form-message");
            if (hdr) {
                showTip(hdr, "🔒 You don't have permission for this action.", isAI);
                hdr.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            return;
        }

        if (!parsed.fields || !parsed.fields.length) return;

        var scrolled = false;
        for (var i = 0; i < parsed.fields.length; i++) {
            var info = parsed.fields[i];
            var el = findFieldElement(info);

            if (!el) {
                // Retry after delay (child table row opening)
                (function(fieldInfo, isFirst, ptype) {
                    setTimeout(function() {
                        var e = findFieldElement(fieldInfo);
                        if (e) {
                            highlight(e);
                            if (isFirst) {
                                scrollTo(e);
                                var tipMsg = buildTipText(fieldInfo, ptype);
                                showTip(e, tipMsg, isAI);
                            }
                        }
                    }, 500);
                })(info, !scrolled, parsed.type);
                if (!scrolled) scrolled = true;
                continue;
            }

            highlight(el);
            if (!scrolled) {
                scrollTo(el);
                var tipText = buildTipText(info, parsed.type);
                showTip(el, tipText, isAI);
                scrolled = true;
            }
        }
    }

    function applyAIResult(data) {
        if (!data.fields || !data.fields.length) return;

        var scrolled = false;
        for (var i = 0; i < data.fields.length; i++) {
            var f = data.fields[i];
            var el = findFieldElement(f);

            if (!el) {
                (function(fInfo, isFirst, aiData) {
                    setTimeout(function() {
                        var e = findFieldElement(fInfo);
                        if (e) {
                            highlight(e);
                            if (isFirst) {
                                scrollTo(e);
                                showTip(e, aiData.user_message || fInfo.reason || (fInfo.label + " needs attention"), true);
                            }
                        }
                    }, 500);
                })(f, !scrolled, data);
                if (!scrolled) scrolled = true;
                continue;
            }

            highlight(el);
            if (!scrolled) {
                scrollTo(el);
                showTip(el, data.user_message || f.reason || (f.label + " needs attention"), true);
                scrolled = true;
            }
        }
    }

    function buildTipText(info, type) {
        var label = info.label || "This field";
        var row = info.row;

        if (type === "mandatory") {
            var msg = "📝 " + label + " is required. Please fill this field.";
            if (row) msg += " (Row " + row + ")";
            return msg;
        }
        if (type === "link_error") return "🔗 " + label + " — invalid or not found. Check this value.";
        if (type === "validation") return "⚠️ " + label + " — please check this value.";
        return "💡 " + label + " needs your attention.";
    }

    // ─── Hook Frappe ───────────────────────────────────────────
    function hookFrappe() {
        if (_hooked) return;
        _hooked = true;

        var origMsgprint = frappe.msgprint;
        frappe.msgprint = function(msg) {
            var result = origMsgprint.apply(this, arguments);
            try {
                var text = "";
                if (typeof msg === "string") text = msg;
                else if (msg && typeof msg === "object") text = msg.message || msg.msg || msg.body || "";
                if (text) setTimeout(function() { guide(text); }, 200);
            } catch(e) {}
            return result;
        };

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

        if (frappe.show_alert) {
            var origAlert = frappe.show_alert;
            frappe.show_alert = function(msg) {
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
            console.log("[NivFormGuide] Hybrid test:", msg);
            guide(msg);
        },
        parse: function(msg) {
            var r = instantParse(msg);
            console.log("[NivFormGuide] Instant parse:", JSON.stringify(r, null, 2));
            return r;
        },
        clear: clearAll,
        version: "5.0.0"
    };

    function init() {
        injectStyles();
        hookFrappe();
        console.log("[NivFormGuide] v5.0.0 Smart Hybrid loaded");
    }

    if (typeof frappe !== "undefined" && frappe.ready) {
        frappe.ready(init);
    } else {
        document.addEventListener("DOMContentLoaded", function() { setTimeout(init, 1000); });
    }
})();
