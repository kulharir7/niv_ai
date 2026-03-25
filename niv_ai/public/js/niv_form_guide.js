/**
 * Niv AI Form Guide v6.0 — Pure AI
 * 
 * Every message goes to AI. AI reads the message + form fields.
 * AI decides which field(s) need attention. JS guides user there.
 * 
 * No hardcoded patterns. No regex. 100% AI-powered.
 * Shows "thinking" indicator while AI processes.
 */
(function() {
    "use strict";

    var HIGHLIGHT_COLOR = "#7c3aed";
    var HIGHLIGHT_MS = 8000;
    var TOOLTIP_MS = 12000;
    var DEBOUNCE_MS = 500;

    var _lastTrigger = 0;
    var _highlights = [];
    var _tooltips = [];
    var _hooked = false;
    var _thinkingEl = null;

    // ─── CSS ───────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById("niv-fg6-css")) return;
        var s = document.createElement("style");
        s.id = "niv-fg6-css";
        s.textContent = [
            "@keyframes nivPulse{0%,100%{box-shadow:0 0 8px 2px " + HIGHLIGHT_COLOR + "55}50%{box-shadow:0 0 18px 6px " + HIGHLIGHT_COLOR + "88}}",
            "@keyframes nivDots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}",
            ".niv-hl{animation:nivPulse 1.2s ease-in-out infinite;border-radius:6px;position:relative;z-index:1}",
            ".niv-hl input,.niv-hl select,.niv-hl .ql-editor,.niv-hl .link-field,.niv-hl .control-input,.niv-hl .control-input-wrapper{border-color:" + HIGHLIGHT_COLOR + " !important}",
            ".niv-tip{position:absolute;left:0;right:0;background:linear-gradient(135deg,#1e1b2e,#2d2640);color:#e2e0ea;padding:12px 16px;border-radius:10px;font-size:13px;line-height:1.6;z-index:1050;box-shadow:0 6px 24px rgba(124,58,237,.25);border:1px solid " + HIGHLIGHT_COLOR + "44;margin-top:6px;opacity:0;transform:translateY(-8px);transition:opacity .3s,transform .3s}",
            ".niv-tip.niv-show{opacity:1;transform:translateY(0)}",
            ".niv-tip-x{position:absolute;top:6px;right:10px;cursor:pointer;color:#9f9bb0;font-size:16px;line-height:1;border:none;background:none;padding:2px 4px}",
            ".niv-tip-x:hover{color:#fff}",
            ".niv-tip-badge{display:inline-block;background:" + HIGHLIGHT_COLOR + "33;color:#c4b5fd;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:6px;vertical-align:middle}",
            ".niv-thinking{position:fixed;bottom:20px;right:20px;background:linear-gradient(135deg,#1e1b2e,#2d2640);color:#c4b5fd;padding:10px 18px;border-radius:10px;font-size:13px;z-index:2000;box-shadow:0 6px 24px rgba(124,58,237,.3);border:1px solid " + HIGHLIGHT_COLOR + "44;opacity:0;transform:translateY(10px);transition:opacity .3s,transform .3s}",
            ".niv-thinking.niv-show{opacity:1;transform:translateY(0)}",
            ".niv-thinking::after{content:'';animation:nivDots 1.5s infinite}"
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
        hideThinking();
    }

    // ─── Thinking Indicator ────────────────────────────────────
    function showThinking() {
        hideThinking();
        var el = document.createElement("div");
        el.className = "niv-thinking";
        el.innerHTML = "✨ Niv AI is reading the error";
        document.body.appendChild(el);
        _thinkingEl = el;
        requestAnimationFrame(function() {
            requestAnimationFrame(function() { el.classList.add("niv-show"); });
        });
    }

    function hideThinking() {
        if (_thinkingEl) {
            _thinkingEl.classList.remove("niv-show");
            var e = _thinkingEl;
            setTimeout(function() { if (e.parentNode) e.parentNode.removeChild(e); }, 300);
            _thinkingEl = null;
        }
    }

    // ─── Collect Form Fields ───────────────────────────────────
    function getFormFields() {
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

    // ─── Call AI ───────────────────────────────────────────────
    function callAI(message, callback) {
        var formFields = getFormFields();
        var doctype = cur_frm ? cur_frm.doctype : "";

        showThinking();

        frappe.call({
            method: "niv_ai.niv_core.api.form_guide.parse_message",
            args: {
                message: message,
                doctype: doctype,
                fields_json: JSON.stringify(formFields)
            },
            async: true,
            callback: function(r) {
                hideThinking();
                if (r && r.message) {
                    callback(r.message);
                }
            },
            error: function() {
                hideThinking();
            }
        });
    }

    // ─── Find Field ────────────────────────────────────────────
    function findFieldElement(info) {
        if (!cur_frm || !info) return null;

        var fieldname = info.fieldname;
        var label = info.label;
        var rowNum = info.row;
        var tableName = info.table;

        // Child table field
        if (tableName && rowNum) {
            var tableField = cur_frm.fields_dict[tableName];
            if (tableField && tableField.grid) {
                var r = findInChild(tableField.grid, rowNum, fieldname, label);
                if (r) return r;
            }
            for (var fn in cur_frm.fields_dict) {
                var ff = cur_frm.fields_dict[fn];
                if ((ff.df || {}).fieldtype === "Table" && ff.grid) {
                    var r2 = findInChild(ff.grid, rowNum, fieldname, label);
                    if (r2) return r2;
                }
            }
        }

        // By fieldname
        if (fieldname && cur_frm.fields_dict[fieldname]) {
            var fld = cur_frm.fields_dict[fieldname];
            if (fld.$wrapper && fld.$wrapper.length) return fld.$wrapper[0];
        }

        // By label
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

        // Row without table — try all child tables
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

        try {
            if (row.open_form) row.open_form();
            else if (row.toggle_view) row.toggle_view(true);
        } catch(e) {}

        var sn = (fieldname || "").toLowerCase();
        var sl = (label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "").trim();

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

    // ─── UI ────────────────────────────────────────────────────
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

    function showTip(el, text) {
        if (!el) return;
        var old = el.querySelector(".niv-tip");
        if (old) old.remove();

        var tip = document.createElement("div");
        tip.className = "niv-tip";
        tip.innerHTML = '<div>' + escapeHtml(text) + '<span class="niv-tip-badge">✨ AI</span></div>' +
                        '<button class="niv-tip-x">&times;</button>';

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

    // ─── Apply AI Result ───────────────────────────────────────
    function applyResult(data) {
        if (!data) return;
        clearAll();

        // Permission
        if (data.type === "permission") {
            var hdr = document.querySelector(".page-head, .form-message");
            if (hdr) {
                showTip(hdr, data.user_message || "You don't have permission for this action.");
                hdr.scrollIntoView({ behavior: "smooth", block: "start" });
            }
            return;
        }

        if (!data.fields || !data.fields.length) {
            // AI couldn't find specific fields — show general message
            if (data.user_message) {
                var formBody = document.querySelector(".form-layout, .form-page");
                if (formBody) showTip(formBody, data.user_message);
            }
            return;
        }

        var scrolled = false;
        for (var i = 0; i < data.fields.length; i++) {
            var f = data.fields[i];
            var el = findFieldElement(f);

            if (!el) {
                // Retry — child table row might still be opening
                (function(fieldInfo, isFirst, aiData) {
                    setTimeout(function() {
                        var e = findFieldElement(fieldInfo);
                        if (e) {
                            highlight(e);
                            if (isFirst) {
                                scrollTo(e);
                                showTip(e, aiData.user_message || fieldInfo.reason || (fieldInfo.label + " needs attention"));
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
                showTip(el, data.user_message || f.reason || (f.label + " needs attention"));
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

        // Send to AI — pure AI, no hardcode
        callAI(msg, function(result) {
            applyResult(result);
        });
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
            console.log("[NivFormGuide] Pure AI test:", msg);
            guide(msg);
        },
        clear: clearAll,
        version: "6.0.0"
    };

    function init() {
        injectStyles();
        hookFrappe();
        console.log("[NivFormGuide] v6.0.0 Pure AI loaded");
    }

    if (typeof frappe !== "undefined" && frappe.ready) {
        frappe.ready(init);
    } else {
        document.addEventListener("DOMContentLoaded", function() { setTimeout(init, 1000); });
    }
})();
