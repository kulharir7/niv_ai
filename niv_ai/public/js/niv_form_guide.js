/**
 * Niv AI Form Guide v1.0
 * Auto-scroll + highlight + tooltip when validation/mandatory errors occur.
 * Pure client-side JS — zero API calls, zero AI cost, instant.
 */
(function() {
    "use strict";

    // ─── Config ────────────────────────────────────────────────
    var CONFIG = {
        highlightColor: "#7c3aed",
        highlightDuration: 6000,
        tooltipDuration: 8000,
        scrollBehavior: "smooth",
        scrollBlock: "center",
        debounceMs: 300,
    };

    // ─── State ─────────────────────────────────────────────────
    var _lastTrigger = 0;
    var _activeHighlights = [];
    var _activeTooltips = [];

    // ─── CSS Injection ─────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById("niv-form-guide-styles")) return;
        var style = document.createElement("style");
        style.id = "niv-form-guide-styles";
        style.textContent = [
            "@keyframes niv-pulse-glow {",
            "  0%, 100% { box-shadow: 0 0 8px 2px " + CONFIG.highlightColor + "66; }",
            "  50% { box-shadow: 0 0 18px 6px " + CONFIG.highlightColor + "99; }",
            "}",
            ".niv-field-highlight {",
            "  animation: niv-pulse-glow 1.2s ease-in-out infinite;",
            "  border-radius: 6px;",
            "  position: relative;",
            "  z-index: 1;",
            "  transition: box-shadow 0.3s ease;",
            "}",
            ".niv-field-highlight .control-input,",
            ".niv-field-highlight .control-input-wrapper,",
            ".niv-field-highlight input,",
            ".niv-field-highlight select,",
            ".niv-field-highlight .ql-editor,",
            ".niv-field-highlight .link-field {",
            "  border-color: " + CONFIG.highlightColor + " !important;",
            "}",
            ".niv-guide-tooltip {",
            "  position: absolute;",
            "  left: 0; right: 0;",
            "  background: #1e1b2e;",
            "  color: #e2e0ea;",
            "  padding: 10px 14px;",
            "  border-radius: 8px;",
            "  font-size: 13px;",
            "  line-height: 1.5;",
            "  z-index: 1050;",
            "  box-shadow: 0 4px 20px rgba(124, 58, 237, 0.25);",
            "  border: 1px solid " + CONFIG.highlightColor + "44;",
            "  margin-top: 4px;",
            "  opacity: 0;",
            "  transform: translateY(-6px);",
            "  transition: opacity 0.25s ease, transform 0.25s ease;",
            "}",
            ".niv-guide-tooltip.niv-visible {",
            "  opacity: 1;",
            "  transform: translateY(0);",
            "}",
            ".niv-guide-tooltip .niv-tooltip-close {",
            "  position: absolute; top: 4px; right: 8px;",
            "  cursor: pointer; color: #9f9bb0; font-size: 16px;",
            "  line-height: 1; border: none; background: none; padding: 2px 4px;",
            "}",
            ".niv-guide-tooltip .niv-tooltip-close:hover { color: #fff; }",
            ".niv-guide-tooltip .niv-tooltip-icon { margin-right: 6px; }",
        ].join("\n");
        document.head.appendChild(style);
    }

    // ─── Message Parsing ───────────────────────────────────────
    function parseMessage(msg) {
        if (!msg || typeof msg !== "string") return null;
        msg = msg.replace(/<[^>]*>/g, "").trim();
        if (!msg) return null;

        var results = [];
        var m;

        // Pattern 1: "Mandatory: Field1, Field2"
        m = msg.match(/(?:mandatory|required)[\s:]+(.+)/i);
        if (m) {
            var fields = m[1].split(/[,]+/).map(function(f) { return f.trim(); }).filter(Boolean);
            for (var i = 0; i < fields.length; i++) {
                results.push({ label: fields[i], type: "mandatory", row: null });
            }
            if (results.length) return results;
        }

        // Pattern 2: "Row #N: Mandatory: Field"
        m = msg.match(/row\s*#?\s*(\d+)[\s:]+(?:mandatory[\s:]+)?(.+)/i);
        if (m) {
            var rowNum = parseInt(m[1]);
            var fieldPart = m[2].replace(/is\s+required.*$/i, "").trim();
            results.push({ label: fieldPart, type: "mandatory", row: rowNum });
            return results;
        }

        // Pattern 3: "Field is required"
        m = msg.match(/^(.+?)\s+(?:is required|cannot be empty|is mandatory|must be filled)/i);
        if (m) {
            results.push({ label: m[1].trim(), type: "mandatory", row: null });
            return results;
        }

        // Pattern 4: "Value missing for: Field"
        m = msg.match(/value\s+missing\s+for[\s:]+(.+)/i);
        if (m) {
            results.push({ label: m[1].trim(), type: "mandatory", row: null });
            return results;
        }

        // Pattern 5: Validation errors
        m = msg.match(/(?:invalid|wrong|incorrect)\s+(.+?)(?:\s+format|\s+value|$)/i);
        if (m) {
            results.push({ label: m[1].trim(), type: "validation", row: null });
            return results;
        }

        // Pattern 6: Permission errors
        if (/not\s+permitted|permission\s+denied|access\s+denied/i.test(msg)) {
            results.push({ label: null, type: "permission", row: null });
            return results;
        }

        return null;
    }

    // ─── Field Finder ──────────────────────────────────────────
    function findField(label, rowNum) {
        if (!cur_frm) return null;
        var labelLower = label.toLowerCase().replace(/[^a-z0-9_ ]/g, "");

        var fname, field, df, fieldLabel, fieldName;
        for (fname in cur_frm.fields_dict) {
            field = cur_frm.fields_dict[fname];
            df = field.df || {};
            fieldLabel = (df.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "");
            fieldName = (df.fieldname || "").toLowerCase();

            if (fieldLabel === labelLower || fieldName === labelLower ||
                fieldLabel.indexOf(labelLower) !== -1 || labelLower.indexOf(fieldLabel) !== -1) {

                if (rowNum && df.fieldtype === "Table" && field.grid) {
                    return findChildField(field.grid, rowNum, label);
                }
                if (field.$wrapper && field.$wrapper.length) {
                    return { el: field.$wrapper[0], field: field, df: df };
                }
            }
        }

        // Deep search in child tables
        if (rowNum) {
            for (fname in cur_frm.fields_dict) {
                field = cur_frm.fields_dict[fname];
                if ((field.df || {}).fieldtype === "Table" && field.grid) {
                    var found = findChildField(field.grid, rowNum, label);
                    if (found) return found;
                }
            }
        }
        return null;
    }

    function findChildField(grid, rowNum, label) {
        var labelLower = label.toLowerCase().replace(/[^a-z0-9_ ]/g, "");
        var rows = grid.grid_rows || [];
        var row = rows[rowNum - 1];
        if (!row) return null;

        try { row.toggle_view(true); } catch(e) {}

        var rowFields = row.columns || row.fields_dict || {};
        var fn, rf, rdf, rl, rn, el;
        for (fn in rowFields) {
            rf = rowFields[fn];
            rdf = rf.df || {};
            rl = (rdf.label || "").toLowerCase().replace(/[^a-z0-9_ ]/g, "");
            rn = (rdf.fieldname || "").toLowerCase();

            if (rl === labelLower || rn === labelLower ||
                rl.indexOf(labelLower) !== -1 || labelLower.indexOf(rl) !== -1) {
                el = rf.$wrapper ? rf.$wrapper[0] : rf.wrapper;
                if (el) return { el: el, field: rf, df: rdf, row: rowNum };
            }
        }
        return null;
    }

    // ─── Highlight ─────────────────────────────────────────────
    function highlightField(target) {
        if (!target || !target.el) return;
        var el = target.el;
        el.classList.add("niv-field-highlight");
        _activeHighlights.push(el);

        setTimeout(function() {
            el.classList.remove("niv-field-highlight");
            _activeHighlights = _activeHighlights.filter(function(e) { return e !== el; });
        }, CONFIG.highlightDuration);
    }

    function clearHighlights() {
        for (var i = 0; i < _activeHighlights.length; i++) {
            _activeHighlights[i].classList.remove("niv-field-highlight");
        }
        _activeHighlights = [];
    }

    // ─── Tooltip ───────────────────────────────────────────────
    function showTooltip(target, message, type) {
        if (!target || !target.el) return;
        var el = target.el;

        var existing = el.querySelector(".niv-guide-tooltip");
        if (existing) existing.remove();

        var icons = { mandatory: "📝", validation: "⚠️", permission: "🔒" };
        var icon = icons[type] || "💡";

        var tooltip = document.createElement("div");
        tooltip.className = "niv-guide-tooltip";
        tooltip.innerHTML =
            '<span class="niv-tooltip-icon">' + icon + '</span>' +
            escapeHtml(message) +
            '<button class="niv-tooltip-close" title="Close">&times;</button>';

        var pos = getComputedStyle(el).position;
        if (pos === "static") el.style.position = "relative";

        el.appendChild(tooltip);
        _activeTooltips.push(tooltip);

        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                tooltip.classList.add("niv-visible");
            });
        });

        tooltip.querySelector(".niv-tooltip-close").addEventListener("click", function() {
            removeTooltip(tooltip, el, pos);
        });

        setTimeout(function() {
            removeTooltip(tooltip, el, pos);
        }, CONFIG.tooltipDuration);
    }

    function removeTooltip(tooltip, parentEl, origPos) {
        tooltip.classList.remove("niv-visible");
        setTimeout(function() {
            if (tooltip.parentNode) tooltip.parentNode.removeChild(tooltip);
            if (origPos === "static" && parentEl) parentEl.style.position = "";
            _activeTooltips = _activeTooltips.filter(function(t) { return t !== tooltip; });
        }, 250);
    }

    function clearTooltips() {
        for (var i = 0; i < _activeTooltips.length; i++) {
            if (_activeTooltips[i].parentNode) _activeTooltips[i].parentNode.removeChild(_activeTooltips[i]);
        }
        _activeTooltips = [];
    }

    // ─── Scroll ────────────────────────────────────────────────
    function scrollToField(target) {
        if (!target || !target.el) return;
        target.el.scrollIntoView({
            behavior: CONFIG.scrollBehavior,
            block: CONFIG.scrollBlock,
        });

        setTimeout(function() {
            var input = target.el.querySelector(
                "input:not([type=hidden]), select, textarea, .ql-editor, [contenteditable]"
            );
            if (input) {
                try { input.focus(); } catch(e) {}
            }
        }, 400);
    }

    // ─── Main Guide Logic ──────────────────────────────────────
    function guide(msg) {
        var now = Date.now();
        if (now - _lastTrigger < CONFIG.debounceMs) return;
        _lastTrigger = now;

        if (typeof cur_frm === "undefined" || !cur_frm) return;

        var parsed = parseMessage(msg);
        if (!parsed || !parsed.length) return;

        clearHighlights();
        clearTooltips();

        var scrolled = false;

        for (var i = 0; i < parsed.length; i++) {
            var info = parsed[i];

            if (info.type === "permission") {
                var header = document.querySelector(".form-page .page-head, .form-message");
                if (header) {
                    showTooltip({ el: header }, "You don't have permission for this action. Contact your administrator.", "permission");
                    if (!scrolled) {
                        header.scrollIntoView({ behavior: "smooth", block: "start" });
                        scrolled = true;
                    }
                }
                continue;
            }

            if (!info.label) continue;

            var target = findField(info.label, info.row);
            if (!target) continue;

            highlightField(target);

            if (!scrolled) {
                scrollToField(target);
                var tooltipMsg = info.type === "mandatory"
                    ? info.label + " is required to save this form. Please fill it in."
                    : "Please check the value of " + info.label + ".";
                showTooltip(target, tooltipMsg, info.type);
                scrolled = true;
            }
        }
    }

    // ─── Hook into Frappe ──────────────────────────────────────
    function hookFrappe() {
        // Hook frappe.msgprint
        var origMsgprint = frappe.msgprint;
        frappe.msgprint = function(msg, title) {
            var result = origMsgprint.apply(this, arguments);
            var text = "";
            if (typeof msg === "string") {
                text = msg;
            } else if (msg && typeof msg === "object") {
                text = msg.message || msg.msg || "";
            }
            if (text) {
                setTimeout(function() { guide(text); }, 100);
            }
            return result;
        };

        // Hook frappe.throw
        var origThrow = frappe.throw;
        frappe.throw = function(msg) {
            var text = "";
            if (typeof msg === "string") {
                text = msg;
            } else if (msg && typeof msg === "object") {
                text = msg.message || msg.msg || "";
            }
            if (text) {
                setTimeout(function() { guide(text); }, 100);
            }
            return origThrow.apply(this, arguments);
        };

        // Hook .has-error class via MutationObserver
        var observer = new MutationObserver(function(mutations) {
            for (var m = 0; m < mutations.length; m++) {
                var mutation = mutations[m];
                if (mutation.type === "attributes" && mutation.attributeName === "class") {
                    var el = mutation.target;
                    if (el.classList && el.classList.contains("has-error")) {
                        var wrapper = el.closest(".frappe-control");
                        if (wrapper) {
                            var labelEl = wrapper.querySelector(".control-label, label");
                            if (labelEl) {
                                var label = labelEl.textContent.trim();
                                if (label) {
                                    (function(l) {
                                        setTimeout(function() { guide("Mandatory: " + l); }, 200);
                                    })(label);
                                }
                            }
                        }
                    }
                }
            }
        });

        var formArea = document.getElementById("body") || document.body;
        observer.observe(formArea, {
            attributes: true,
            attributeFilter: ["class"],
            subtree: true,
        });
    }

    // ─── Utilities ─────────────────────────────────────────────
    function escapeHtml(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ─── Public API ────────────────────────────────────────────
    window.NivFormGuide = {
        guide: guide,
        test: function(msg) {
            msg = msg || "Mandatory: Customer";
            console.log("[NivFormGuide] Testing with:", msg);
            guide(msg);
        },
        clear: function() {
            clearHighlights();
            clearTooltips();
        },
        version: "1.0.0",
    };

    // ─── Init ──────────────────────────────────────────────────
    function init() {
        injectStyles();
        hookFrappe();
        console.log("[NivFormGuide] v1.0.0 loaded ✓");
    }

    if (typeof frappe !== "undefined" && frappe.ready) {
        frappe.ready(init);
    } else {
        document.addEventListener("DOMContentLoaded", function() {
            setTimeout(init, 1000);
        });
    }
})();
