/**
 * Niv AI Floating Widget — iframe panel
 * ✦ click → mini window with /app/niv-chat inside
 * Expand → full page
 */
(function () {
    "use strict";

    if (typeof frappe === "undefined") return;

    function init() {
        if (document.getElementById("niv-widget-root")) return;

        // Build widget DOM
        var root = document.createElement("div");
        root.id = "niv-widget-root";

        // FAB
        var fab = document.createElement("button");
        fab.id = "niv-fab";
        fab.className = "niv-fab";
        fab.title = "Niv AI";
        fab.innerHTML = '<span>✦</span>';

        // Panel
        var panel = document.createElement("div");
        panel.id = "niv-panel";
        panel.className = "niv-panel";
        panel.innerHTML = [
            '<div class="niv-panel-header">',
            '  <div class="niv-panel-title"><span class="niv-panel-avatar">N</span> Niv AI</div>',
            '  <div class="niv-panel-actions">',
            '    <button class="niv-panel-btn" id="niv-fullscreen" title="Full page"><i class="fa fa-external-link"></i></button>',
            '    <button class="niv-panel-btn" id="niv-close" title="Close"><i class="fa fa-times"></i></button>',
            '  </div>',
            '</div>',
            '<div class="niv-panel-loading" id="niv-loading">',
            '  <div class="niv-loading-spinner"></div>',
            '  <div>Loading Niv AI...</div>',
            '</div>',
            '<iframe id="niv-iframe" class="niv-iframe" src="about:blank" allow="microphone"></iframe>'
        ].join('\n');

        root.appendChild(fab);
        root.appendChild(panel);
        document.body.appendChild(root);

        // State
        var isOpen = false;
        var loaded = false;
        var iframe = document.getElementById("niv-iframe");
        var loading = document.getElementById("niv-loading");

        function getParentContext() {
            var route = frappe.get_route() || [];
            var ctx = { route: route };
            if (route[0] === "Form" && route.length >= 3) {
                ctx.doctype = route[1];
                ctx.docname = route[2];
            } else if (route[0] === "List" && route.length >= 2) {
                ctx.doctype = route[1];
                ctx.view = "list";
            }
            return ctx;
        }

        function openPanel() {
            isOpen = true;
            panel.classList.add("open");
            fab.classList.add("hidden");
            // Always update context when opening (user may have navigated)
            var ctx = getParentContext();
            var widgetUrl = "/app/niv-chat?widget=1&parent_context=" + encodeURIComponent(JSON.stringify(ctx));
            if (!loaded) {
                loaded = true;
                iframe.src = widgetUrl;
                iframe.onload = function() {
                    loading.style.display = "none";
                    iframe.style.display = "block";
                    // Hide Frappe navbar inside iframe
                    try {
                        var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        var style = iframeDoc.createElement("style");
                        style.textContent = [
                            "* { box-sizing: border-box !important; }",
                            ".navbar, .page-head, #page-niv-chat > .page-head, .frappe-list-sidebar, .niv-sidebar-footer, .niv-model-badge-wrapper, .niv-model-dropdown, .niv-model-popover, .niv-header-actions, .msg-tokens { display: none !important; }",
                            "html, body { padding: 0 !important; margin: 0 !important; overflow: hidden !important; width: 100% !important; height: 100% !important; }",
                            ".container, .container.page-body, .page-container, .main-section, .layout-main, .layout-main-section, .page-body { padding: 0 !important; margin: 0 !important; max-width: 100% !important; width: 100% !important; }",
                            ".niv-chat-container { --niv-chat-width: 100% !important; height: 100vh !important; width: 100% !important; border-radius: 0 !important; }",
                            ".niv-main { width: 100% !important; padding: 0 !important; margin: 0 !important; }",
                            ".niv-chat-messages { max-width: 100% !important; width: 100% !important; margin: 0 !important; padding: 12px !important; }",
                            ".niv-message { max-width: 100% !important; width: 100% !important; margin: 0 !important; padding: 10px 0 !important; }",
                            ".niv-input-area { padding: 0 12px 12px !important; width: 100% !important; }",
                            ".niv-input-pill { max-width: 100% !important; width: 100% !important; margin: 0 !important; }",
                            ".niv-attach-preview, .niv-welcome-container, .niv-disclaimer, .niv-typing-indicator, .niv-empty-state, .niv-input-footer { max-width: 100% !important; width: 100% !important; margin-left: 0 !important; margin-right: 0 !important; }",
                        ].join("\n");
                        iframeDoc.head.appendChild(style);
                    } catch(e) { console.log("[NivWidget] Could not inject iframe styles:", e); }
                };
            } else {
                // Already loaded — update context via postMessage AND update iframe URL for reliability
                try {
                    iframe.contentWindow.postMessage({ type: "niv_parent_context", context: ctx }, "*");
                    // Also store on iframe window for direct access
                    iframe.contentWindow.__niv_parent_context = ctx;
                } catch(e) {}
            }
        }

        function closePanel() {
            isOpen = false;
            panel.classList.remove("open");
            fab.classList.remove("hidden");
        }

        fab.addEventListener("click", openPanel);
        document.getElementById("niv-close").addEventListener("click", closePanel);
        document.getElementById("niv-fullscreen").addEventListener("click", function() {
            closePanel();
            frappe.set_route("niv-chat");
        });

        // ESC to close
        document.addEventListener("keydown", function(e) {
            if (e.key === "Escape" && isOpen) closePanel();
        });

        // SPA navigation — hide on chat page, show elsewhere
        function checkRoute() {
            var onChat = window.location.pathname.indexOf("/app/niv-chat") === 0;
            root.style.display = onChat ? "none" : "block";
            if (onChat && isOpen) closePanel();
        }
        // Check immediately on init
        checkRoute();
        $(document).on("page-change", checkRoute);
        window.addEventListener("popstate", checkRoute);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        setTimeout(init, 200);
    }
})();
