/**
 * Niv AI Floating Widget — iframe panel
 * ✦ click → mini window with /app/niv-chat inside
 * Expand → full page
 */
(function () {
    "use strict";

    // PWA: Inject manifest + meta tags
    (function() {
        if (document.getElementById("pwa-manifest-link")) return;
        var link = document.createElement("link");
        link.id = "pwa-manifest-link";
        link.rel = "manifest";
        link.href = "/assets/niv_ai/manifest.json";
        document.head.appendChild(link);

        var metas = [
            {name: "mobile-web-app-capable", content: "yes"},
            {name: "apple-mobile-web-app-capable", content: "yes"},
            {name: "apple-mobile-web-app-status-bar-style", content: "black-translucent"},
            {name: "apple-mobile-web-app-title", content: "Chanakya AI"},
            {name: "theme-color", content: "#7c3aed"},
            {name: "viewport", content: "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"}
        ];
        metas.forEach(function(m) {
            if (!document.querySelector('meta[name="' + m.name + '"]')) {
                var meta = document.createElement("meta");
                meta.name = m.name;
                meta.content = m.content;
                document.head.appendChild(meta);
            }
        });

        // Apple touch icon
        if (!document.querySelector('link[rel="apple-touch-icon"]')) {
            var icon = document.createElement("link");
            icon.rel = "apple-touch-icon";
            icon.href = "/assets/niv_ai/images/niv-icon-192.png";
            document.head.appendChild(icon);
        }
    })();


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
        fab.innerHTML = '<img src="/assets/niv_ai/images/niv_fab_logo.png" style="width:56px;height:56px;border-radius:50%;object-fit:cover;" alt="Niv AI" />';

        // Panel
        var panel = document.createElement("div");
        panel.id = "niv-panel";
        panel.className = "niv-panel";
        panel.innerHTML = [
            '<div class="niv-panel-header">',
            '  <div class="niv-panel-title"><span class="niv-panel-avatar" id="niv-panel-avatar-el">N</span> <span id="niv-panel-title-text">Niv AI</span></div>',
            '  <div class="niv-panel-actions">',
            '    <button class="niv-panel-btn" id="niv-fullscreen" title="Full page"><i class="fa fa-external-link"></i></button>',
            '    <button class="niv-panel-btn" id="niv-close" title="Close"><i class="fa fa-times"></i></button>',
            '  </div>',
            '</div>',
            '<div class="niv-panel-loading" id="niv-loading">',
            '  <div class="niv-loading-spinner"></div>',
            '  <div>Loading...</div>',
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
                    // Hide Frappe navbar inside iframe and fix layout
                    try {
                        var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                        var style = iframeDoc.createElement("style");
                        style.textContent = [
                            "/* Widget mode - complete reset */",
                            "* { box-sizing: border-box !important; }",
                            "",
                            "/* Hide ALL unnecessary elements */",
                            ".navbar, .page-head, #page-niv-chat > .page-head, .frappe-list-sidebar, .niv-sidebar-footer, .niv-model-badge-wrapper, .niv-model-dropdown, .niv-model-popover, .niv-header-actions, .msg-tokens, .niv-chat-header, .niv-header, .niv-sidebar, .niv-chat-sidebar { display: none !important; }",
                            "",
                            "/* Full viewport reset - FORCE LIGHT THEME */",
                            "html, body { padding: 0 !important; margin: 0 !important; overflow: hidden !important; width: 100% !important; height: 100% !important; background: #18181e !important; }",
                            "body { --niv-bg: #18181e !important; --niv-text: #e5e5e5 !important; --niv-text-muted: #9ca3af !important; }",
                            "",
                            "/* Container reset - remove ALL padding/margins */",
                            ".container, .container.page-body, .page-container, .main-section, .layout-main, .layout-main-section, .page-body, #page-niv-chat, #page-niv-chat .layout-main-section-wrapper, #page-niv-chat .layout-main-section { padding: 0 !important; margin: 0 !important; max-width: 100% !important; width: 100% !important; height: 100% !important; background: #18181e !important; border: none !important; }",
                            "",
                            "/* Chat container - fill completely */",
                            ".niv-chat-container { --niv-chat-width: 100% !important; height: 100% !important; width: 100% !important; border-radius: 0 !important; display: flex !important; flex-direction: column !important; border: none !important; box-shadow: none !important; margin: 0 !important; max-width: 100% !important; background: #18181e !important; }",
                            ".niv-chat-container::before, .niv-chat-container::after { display: none !important; }",
                            "",
                            "/* Main area - flex fill */",
                            ".niv-main { width: 100% !important; padding: 0 !important; margin: 0 !important; height: 100% !important; display: flex !important; flex-direction: column !important; flex: 1 !important; min-height: 0 !important; background: #18181e !important; }",
                            "",
                            "/* Messages area - scrollable */",
                            ".niv-chat-messages { max-width: 100% !important; width: 100% !important; margin: 0 !important; padding: 16px !important; flex: 1 !important; overflow-y: auto !important; min-height: 0 !important; }",
                            "",
                            "/* Individual messages */",
                            ".niv-message { max-width: 100% !important; margin: 0 !important; padding: 8px 0 !important; }",
                            "",
                            "/* Input area - fixed at bottom with proper spacing */",
                            ".niv-input-area { padding: 12px 16px 16px !important; width: 100% !important; flex-shrink: 0 !important; background: #18181e !important; border-top: 1px solid #e5e5e5 !important; }",
                            ".niv-input-pill { max-width: 100% !important; width: 100% !important; margin: 0 !important; }",
                            "",
                            "/* Hide disclaimer in widget */",
                            ".niv-disclaimer, .niv-input-footer { display: none !important; }",
                            "",
                            "/* Welcome screen */",
                            ".niv-welcome-container { flex: 1 !important; display: flex !important; flex-direction: column !important; justify-content: center !important; align-items: center !important; max-width: 100% !important; width: 100% !important; margin: 0 !important; padding: 20px !important; }",
                            "",
                            "/* Empty state - compact, centered, no excess whitespace */",
                            ".niv-chat-messages { display: flex !important; flex-direction: column !important; justify-content: center !important; }",
                            ".niv-chat-messages:has(.niv-message) { justify-content: flex-start !important; }",
                            ".niv-empty-state { max-width: 100% !important; width: 100% !important; margin: 0 auto !important; padding: 20px 16px !important; flex-shrink: 0 !important; }",
                            ".niv-empty-state .empty-orb { width: 52px !important; height: 52px !important; margin-bottom: 12px !important; }",
                            ".niv-empty-state .empty-greeting { color: #e5e5e5 !important; font-weight: 600 !important; font-size: 18px !important; margin-bottom: 4px !important; }",
                            ".niv-empty-state .empty-subtitle { color: #9ca3af !important; font-size: 13px !important; margin-bottom: 16px !important; }",
                            ".empty-suggestions { gap: 6px !important; padding: 0 8px !important; }",
                            "",
                            "/* User message - white text on dark bubble */",
                            ".niv-message.user .msg-content { background: #7c3aed !important; color: #ffffff !important; }",
                            "",
                            "/* Assistant message - dark text */",
                            ".niv-message.assistant .msg-content { color: #e5e5e5 !important; }",
                            "",
                                        "/* Other elements */",
                            "/* Dark theme for widget */",
                            ".niv-input-pill { background: #2a2a35 !important; border-color: rgba(255,255,255,0.1) !important; }",
                            ".niv-input-textarea { color: #e5e5e5 !important; background: transparent !important; }",
                            ".niv-input-textarea::placeholder { color: #6b7280 !important; }",
                            ".niv-input-right .btn, .btn-attach-file { color: #9ca3af !important; }",
                            ".msg-content pre, .msg-content code { background: #1e1e2e !important; color: #e5e5e5 !important; border-color: rgba(255,255,255,0.08) !important; }",
                            ".empty-suggestion-card, .msg-suggestion-chip { background: #2a2a35 !important; color: #e5e5e5 !important; border-color: rgba(255,255,255,0.08) !important; }",
                            ".niv-scroll-bottom { background: #2a2a35 !important; color: #e5e5e5 !important; border-color: rgba(255,255,255,0.1) !important; }",
                            ".niv-attach-preview, .niv-typing-indicator, .niv-input-footer { max-width: 100% !important; width: 100% !important; margin-left: 0 !important; margin-right: 0 !important; }",
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
            // Cleanup: ensure parent body doesn't have chat-active class
            document.body.classList.remove("niv-chat-active");
        }

        fab.addEventListener("click", openPanel);
        document.getElementById("niv-close").addEventListener("click", closePanel);
        document.getElementById("niv-fullscreen").addEventListener("click", function() {
            closePanel();
            // Pass current conversation ID to full page chat
            try {
                var iframeWin = document.getElementById("niv-iframe").contentWindow;
                var nivChat = iframeWin.cur_niv_chat || (iframeWin.cur_page && iframeWin.cur_page.page && iframeWin.cur_page.page.niv_chat);
                var convId = nivChat ? nivChat.current_conversation : null;
                if (convId) {
                    frappe.set_route("niv-chat", convId);
                    return;
                }
            } catch(e) {}
            frappe.set_route("niv-chat");
        });

        // ESC to close
        document.addEventListener("keydown", function(e) {
            if (e.key === "Escape" && isOpen) closePanel();
        });

        // SPA navigation — hide on chat page, show elsewhere
        // Load dynamic widget title and avatar from Niv Settings
        (function loadWidgetBranding() {
            if (typeof frappe !== "undefined" && frappe.call) {
                frappe.call({
                    method: "niv_ai.niv_core.api.chat.get_chat_config",
                    args: {},
                    async: true,
                    callback: function(r) {
                        if (r && r.message) {
                            var title = r.message.widget_title || "Niv AI";
                            var logo = r.message.widget_logo;
                            var titleEl = document.getElementById("niv-panel-title-text");
                            var avatarEl = document.getElementById("niv-panel-avatar-el");
                            if (titleEl) titleEl.textContent = title;
                            if (avatarEl) {
                                if (logo) {
                                    avatarEl.innerHTML = '<img src="' + logo + '" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;" />';
                                } else {
                                    avatarEl.textContent = title.charAt(0).toUpperCase();
                                }
                            }
                            if (fab) fab.title = title;
                            var loadingEl = document.getElementById("niv-loading-text");
                            if (loadingEl) loadingEl.textContent = "Loading " + title + "...";
                        }
                    }
                });
            }
        })();

        function checkRoute() {
            var onChat = window.location.pathname.indexOf("/app/niv-chat") === 0;
            root.style.display = onChat ? "none" : "block";
            if (onChat && isOpen) closePanel();
            // Safety: remove niv-chat-active from body when NOT on chat page
            if (!onChat) {
                document.body.classList.remove("niv-chat-active");
            }
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
