frappe.pages["niv-chat"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Niv AI Chat",
        single_column: true,
    });

    // Hide Frappe page chrome
    $(wrapper).find(".page-head").hide();

    // Restore Frappe chrome when leaving this page
    frappe.pages["niv-chat"].on_page_hide = function () {
        document.body.classList.remove("niv-chat-active");
    };
    frappe.pages["niv-chat"].on_page_show = function () {
        document.body.classList.add("niv-chat-active");
    };

    // Load marked.js + highlight.js
    const loadScript = (src) => new Promise((resolve) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = resolve;
        document.head.appendChild(s);
    });
    const loadCSS = (href) => {
        const l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = href;
        document.head.appendChild(l);
    };

    const deps = [];
    if (!window.marked) {
        deps.push(loadScript("https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"));
    }
    if (!window.hljs) {
        deps.push(loadScript("https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"));
        loadCSS("https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css");
        loadCSS("https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css");
    }

    Promise.all(deps).then(() => {
        if (window.marked) {
            marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });
        }
        new NivChat(page);
    });
};

class NivChat {
    constructor(page) {
        this.page = page;
        this.wrapper = $(page.body);
        this.current_conversation = null;
        this.conversations = [];
        this.is_streaming = false;
        this.recognition = null;
        this.selected_model = "";
        this.event_source = null;
        this.typing_timer = null;
        this.typing_start = null;
        this.messages_data = [];
        this.reactions = {};
        this.search_matches = [];
        this.search_index = -1;
        this.unread_count = 0;
        this.edit_mode = false;
        this.models_list = [];
        this.slash_commands = [
            { cmd: "/clear", desc: "Clear chat history", icon: "🗑️" },
            { cmd: "/export", desc: "Export chat as markdown", icon: "📥" },
            { cmd: "/help", desc: "Show available commands", icon: "❓" },
            { cmd: "/model", desc: "Switch model", icon: "🤖", hasArg: true },
            { cmd: "/system", desc: "Set system prompt", icon: "⚙️", hasArg: true },
            { cmd: "/summarize", desc: "Summarize conversation", icon: "📝" },
            { cmd: "/translate", desc: "Translate last AI message", icon: "🌐", hasArg: true },
            { cmd: "/new", desc: "New chat", icon: "✨" },
            { cmd: "/instructions", desc: "Manage custom instructions", icon: "📋" },
        ];
        this.slash_selected_index = 0;

        this.setup_page();
        this.setup_voice_mode();
        this.last_used_model = "";
        this.setup_dark_mode();
        // emoji picker disabled
        this.setup_drag_drop();
        this.setup_slash_commands();
        this.setup_themes();
        this.setup_settings_panel();
        this.load_conversations();
        this.load_balance();
        this.load_models();
        this.setup_keyboard_shortcuts();
        this.setup_scroll_watcher();
        this.setup_mobile_touch();
    }

    setup_page() {
        this.wrapper.html(frappe.render_template("niv_chat"));

        // Full immersive mode — hide Frappe chrome
        document.body.classList.add("niv-chat-active");

        // (settings panel moved to body in setup_settings_panel)

        // Ensure viewport-fit=cover for iOS safe areas
        let vp = document.querySelector('meta[name="viewport"]');
        if (vp && !vp.content.includes('viewport-fit')) {
            vp.content += ', viewport-fit=cover';
        }

        // Widget mode — compact layout for iframe embedding
        const urlParams = new URLSearchParams(window.location.search);
        this.isWidgetMode = urlParams.get("widget") === "1";
        if (this.isWidgetMode) {
            document.body.classList.add("niv-widget-mode");
            // Start with sidebar collapsed in widget mode
            this.wrapper.find(".niv-sidebar").addClass("collapsed");
            // Read parent page context passed from widget
            try {
                const parentCtx = urlParams.get("parent_context");
                if (parentCtx) this.parent_context = JSON.parse(decodeURIComponent(parentCtx));
            } catch(e) {}
            // Listen for context updates from parent
            window.addEventListener("message", (e) => {
                if (e.data && e.data.type === "niv_parent_context") {
                    this.parent_context = e.data.context;
                }
            });
        }
        
        this.$sidebar = this.wrapper.find(".niv-sidebar");
        this.$convList = this.wrapper.find(".niv-conversation-list");
        this.$chatArea = this.wrapper.find(".niv-chat-messages");
        this.$input = this.wrapper.find(".niv-input-textarea");
        this.$sendBtn = this.wrapper.find(".btn-send");
        this.$stopBtn = this.wrapper.find(".btn-stop");
        this.$newChatBtn = this.wrapper.find(".btn-new-chat");
        this.$fileBtn = this.wrapper.find(".btn-attach-file");
        this.$voiceBtn = this.wrapper.find(".btn-voice-input");
        this.$fileInput = this.wrapper.find(".niv-file-input");
        this.$attachPreview = this.wrapper.find(".niv-attach-preview");
        this.$credits = this.wrapper.find(".credit-amount");
        this.$lowBalanceWarning = this.wrapper.find(".niv-low-balance-warning");
        this.$searchInput = this.wrapper.find(".niv-sidebar-search input");
        this.$modelDropdown = this.wrapper.find(".niv-model-dropdown");
        this.$modelBadge = this.wrapper.find(".niv-model-badge");
        this.$modelPopover = this.wrapper.find(".niv-model-popover");
        this.$scrollBottom = this.wrapper.find(".niv-scroll-bottom");
        this.$searchBar = this.wrapper.find(".niv-search-bar");
        this.$msgSearchInput = this.wrapper.find(".niv-search-input");
        this.$inputPill = this.wrapper.find(".niv-input-pill");

        this.pending_files = [];

        // Set user profile in sidebar
        this.setup_user_profile();

        // Bind events
        this.$sendBtn.on("click", () => this.send_message());
        this.$stopBtn.on("click", () => this.stop_generation());
        this.$newChatBtn.on("click", () => this.new_conversation());
        this.$fileBtn.on("click", () => this.$fileInput.click());
        this.$fileInput.on("change", (e) => this.handle_file_select(e));
        this.$voiceBtn.on("click", () => this.toggle_voice_input());
        this.wrapper.find(".recharge-link").on("click", (e) => { e.preventDefault(); this.show_recharge_dialog(); });
        this.wrapper.find(".btn-usage-stats").on("click", () => this.show_usage_dialog());
        this.$searchInput.on("input", (e) => this.filter_conversations(e.target.value));
        this.$modelDropdown.on("change", (e) => { this.switch_model(e.target.value); });
        this.$scrollBottom.on("click", () => this.scroll_to_bottom());

        // Sidebar model selector
        this.$sidebarModelBtn = this.wrapper.find(".niv-sidebar-model-btn");
        this.$sidebarModelPopover = this.wrapper.find(".niv-sidebar-model-popover");
        this.$sidebarModelBtn.on("click", (e) => {
            e.stopPropagation();
            this.$sidebarModelPopover.toggle();
        });

        // Model badge click (legacy, hidden)
        this.$modelBadge.on("click", (e) => {
            e.stopPropagation();
            this.toggle_model_popover();
        });

        // Close model popovers on outside click
        $(document).on("click.nivmodel", () => {
            this.$modelPopover.hide();
            this.$sidebarModelPopover.hide();
        });
        this.$modelPopover.on("click", (e) => e.stopPropagation());
        this.$sidebarModelPopover.on("click", (e) => e.stopPropagation());
        
        // Show close button only in widget mode
        if (this.isWidgetMode) {
            this.wrapper.find(".btn-close-sidebar").show();
        }

        // Auto-resize textarea + track text state + save draft
        this.$input.on("input", () => {
            this.auto_resize_input();
            const val = this.$input.val().trim();
            if (val) {
                this.$inputPill.addClass("has-text");
                localStorage.setItem("niv_draft", this.$input.val());
            } else {
                this.$inputPill.removeClass("has-text");
                localStorage.removeItem("niv_draft");
            }
        });

        // Restore draft message on page load
        const draft = localStorage.getItem("niv_draft");
        if (draft) {
            this.$input.val(draft);
            this.$inputPill.addClass("has-text");
            this.auto_resize_input();
        }

        // Enter to send
        this.$input.on("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                this.send_message();
            }
        });

        // Header actions
        // Pinned section
        this.$pinnedSection = this.wrapper.find(".niv-pinned-section");
        this.$pinnedList = this.wrapper.find(".niv-pinned-list");
        this.wrapper.find(".btn-toggle-pinned").on("click", () => {
            this.$pinnedList.slideToggle(200);
            this.wrapper.find(".btn-toggle-pinned i").toggleClass("fa-chevron-up fa-chevron-down");
        });

        // Header actions
        this.wrapper.find(".btn-share-chat").on("click", () => this.share_conversation());
        this.wrapper.find(".btn-delete-chat").on("click", () => this.delete_conversation());
        this.wrapper.find(".btn-rename-chat").on("click", () => this.rename_conversation());
        this.wrapper.find(".btn-fullscreen").on("click", () => this.toggle_fullscreen());
        this.wrapper.find(".btn-export-chat").on("click", () => this.export_chat());
        this.wrapper.find(".btn-search-messages").on("click", () => this.toggle_search_bar());
        this.wrapper.find(".btn-search-close").on("click", () => this.toggle_search_bar(false));
        this.wrapper.find(".btn-search-prev").on("click", () => this.navigate_search(-1));
        this.wrapper.find(".btn-search-next").on("click", () => this.navigate_search(1));
        this.$msgSearchInput.on("input", (e) => this.search_in_messages(e.target.value));
        this.$msgSearchInput.on("keydown", (e) => {
            if (e.key === "Enter") this.navigate_search(e.shiftKey ? -1 : 1);
            if (e.key === "Escape") this.toggle_search_bar(false);
        });

        // Toggle sidebar
        this.wrapper.find(".btn-toggle-sidebar").on("click", () => {
            if (this.isWidgetMode) {
                // Widget mode: sidebar is absolute overlay, use collapsed class
                const isCollapsed = this.$sidebar.hasClass("collapsed");
                if (isCollapsed) {
                    this.$sidebar.removeClass("collapsed");
                } else {
                    this.$sidebar.addClass("collapsed");
                }
            } else {
                // Desktop: use open class for mobile overlay
                const isOpen = this.$sidebar.hasClass("open");
                if (isOpen) {
                    this.$sidebar.removeClass("open");
                } else if (this.$sidebar.hasClass("collapsed") || this.$sidebar.css("transform") !== "none") {
                    this.$sidebar.removeClass("collapsed").addClass("open");
                } else {
                    this.$sidebar.addClass("collapsed");
                }
            }
        });

        // Close sidebar button (inside sidebar)
        this.wrapper.find(".btn-close-sidebar").on("click", () => {
            if (this.isWidgetMode) {
                this.$sidebar.addClass("collapsed");
            } else {
                this.$sidebar.removeClass("open").addClass("collapsed");
            }
        });
    }

    setup_user_profile() {
        const fullName = frappe.session.user_fullname || "User";
        const initials = fullName.split(" ").map(n => n[0]).join("").substring(0, 2).toUpperCase();
        this.wrapper.find(".niv-user-avatar").text(initials);
        this.wrapper.find(".niv-user-name").text(fullName);
    }

    auto_resize_input() {
        this.$input.css("height", "auto");
        this.$input.css("height", Math.min(this.$input[0].scrollHeight, 200) + "px");
    }

    setup_keyboard_shortcuts() {
        $(document).on("keydown.nivchat", (e) => {
            if ((e.ctrlKey && e.shiftKey && e.key === "N") || (e.altKey && e.key === "n")) {
                e.preventDefault();
                this.new_conversation();
            }
            if (e.key === "Escape") {
                if (this.edit_mode) this.cancel_edit();
                else if (this.is_streaming) this.stop_generation();
                else if (this.$searchBar.is(":visible")) this.toggle_search_bar(false);
            }
        });
    }

    setup_scroll_watcher() {
        this.$chatArea.on("scroll", () => {
            const el = this.$chatArea[0];
            const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
            if (distFromBottom > 200) {
                this.$scrollBottom.show();
            } else {
                this.$scrollBottom.hide();
                this.unread_count = 0;
                this.$scrollBottom.find(".scroll-unread-badge").hide();
            }
        });
    }

    // ─── Greeting ───────────────────────────────────────────────────

    get_greeting() {
        const hour = new Date().getHours();
        if (hour < 12) return "Good morning";
        if (hour < 17) return "Good afternoon";
        return "Good evening";
    }

    get_first_name() {
        const full = frappe.session.user_fullname || "there";
        return full.split(" ")[0];
    }

    // ─── Models ─────────────────────────────────────────────────────

    async load_models() {
        try {
            const settings = await frappe.call({ method: "frappe.client.get", args: { doctype: "Niv Settings", name: "Niv Settings" } });
            const s = settings.message;
            const defaultModel = s.default_model || "";
            const providerName = s.default_provider;

            this.$modelDropdown.empty();
            this.$modelDropdown.append(`<option value="">Default</option>`);

            const displayName = s.widget_title || "Niv AI";
            this.models_list = [{ name: displayName, value: "", provider: providerName || "" }];

            // Update badge text
            this.update_model_badge(displayName, providerName || "");

            if (providerName) {
                try {
                    const prov = await frappe.call({ method: "frappe.client.get", args: { doctype: "Niv AI Provider", name: providerName } });
                    const models = prov.message.models || [];
                    for (const m of models) {
                        const name = m.model_name || m.model_id || m.name;
                        this.$modelDropdown.append(`<option value="${frappe.utils.escape_html(name)}">${frappe.utils.escape_html(name)}</option>`);
                        this.models_list.push({ name, value: name, provider: providerName });
                    }
                } catch (e) { /* no models child table */ }
            }

            this.render_model_popover();
        } catch (e) { /* settings not accessible */ }
    }

    update_model_badge(modelName, provider) {
        this.$modelBadge.find(".model-badge-text").text(modelName);
        // Detect provider for coloring
        const p = (provider || modelName || "").toLowerCase();
        let providerKey = "";
        if (p.includes("mistral")) providerKey = "mistral";
        else if (p.includes("openai") || p.includes("gpt")) providerKey = "openai";
        else if (p.includes("claude") || p.includes("anthropic")) providerKey = "anthropic";
        else if (p.includes("gemini") || p.includes("google")) providerKey = "google";
        this.$modelBadge.attr("data-provider", providerKey);

        // Icon
        const icons = { mistral: "✦", openai: "◉", anthropic: "⬡", google: "◆" };
        this.$modelBadge.find(".model-badge-icon").text(icons[providerKey] || "✦");
        
        // Update sidebar model button
        if (this.$sidebarModelBtn) {
            this.$sidebarModelBtn.find(".sidebar-model-text").text(modelName);
            this.$sidebarModelBtn.find(".sidebar-model-icon").text(icons[providerKey] || "✦");
        }
    }

    render_model_popover() {
        const $list = this.$modelPopover.find(".model-popover-list");
        const $sidebarList = this.$sidebarModelPopover.find(".sidebar-model-popover-list");
        $list.empty();
        $sidebarList.empty();
        for (const m of this.models_list) {
            const isActive = m.value === this.selected_model;
            const p = (m.provider || m.name || "").toLowerCase();
            let color = "#7c3aed";
            if (p.includes("mistral")) color = "#f97316";
            else if (p.includes("openai") || p.includes("gpt")) color = "#10b981";
            else if (p.includes("claude") || p.includes("anthropic")) color = "#8b5cf6";
            else if (p.includes("gemini") || p.includes("google")) color = "#3b82f6";

            const selectModel = () => {
                this.switch_model(m.value, m.name);
                this.$modelDropdown.val(m.value);
                this.update_model_badge(m.name, m.provider);
                this.$modelPopover.hide();
                this.$sidebarModelPopover.hide();
                this.$sidebarModelBtn.find(".sidebar-model-text").text(m.name);
                this.render_model_popover();
            };

            const $item = $(`
                <div class="model-popover-item ${isActive ? 'active' : ''}" data-value="${frappe.utils.escape_html(m.value)}">
                    <span class="model-item-icon" style="background:${color}"></span>
                    ${frappe.utils.escape_html(m.name)}
                </div>
            `);
            $item.on("click", selectModel);
            $list.append($item);

            const $sidebarItem = $item.clone(false);
            $sidebarItem.on("click", selectModel);
            $sidebarList.append($sidebarItem);
        }
    }

    toggle_model_popover() {
        if (this.$modelPopover.is(":visible")) {
            this.$modelPopover.hide();
        } else {
            this.$modelPopover.show();
        }
    }

    switch_model(modelValue, displayName) {
        const oldModel = this.selected_model;
        this.selected_model = modelValue;

        if (oldModel !== modelValue && this.current_conversation && this.messages_data.length > 0) {
            const name = displayName || modelValue || "Default Model";
            this.$chatArea.append(`
                <div class="niv-system-message">
                    <span class="system-msg-text">Switched to ${frappe.utils.escape_html(name)}</span>
                </div>
            `);
            this.scroll_to_bottom();
        }
    }

    // ─── Themes ─────────────────────────────────────────────────────

    setup_themes() {
        const saved = localStorage.getItem("niv_chat_theme") || "default";
        this.apply_theme(saved);

        this.wrapper.find(".niv-theme-dot").on("click", (e) => {
            const themeId = $(e.currentTarget).data("theme-id");
            this.apply_theme(themeId);
            localStorage.setItem("niv_chat_theme", themeId);
        });
    }

    apply_theme(themeId) {
        const $container = this.wrapper.find(".niv-chat-container");
        if (themeId && themeId !== "default") {
            $container.attr("data-theme", themeId);
        } else {
            $container.removeAttr("data-theme");
        }
        this.wrapper.find(".niv-theme-dot").removeClass("active");
        this.wrapper.find(`.niv-theme-dot[data-theme-id="${themeId}"]`).addClass("active");
    }

    // ─── Settings Panel ─────────────────────────────────────────────

    setup_settings_panel() {
        // Move settings panel + overlay to body so they escape sidebar overflow
        this.$settingsPanel = this.wrapper.find(".niv-settings-panel").detach().appendTo(document.body);
        this.$settingsOverlay = this.wrapper.find(".niv-settings-overlay").detach().appendTo(document.body);

        this.wrapper.find(".btn-settings-toggle").on("click", () => this.toggle_settings_panel());
        this.$settingsPanel.find(".btn-settings-close").on("click", () => this.close_settings_panel());
        this.$settingsOverlay.on("click", () => this.close_settings_panel());

        // Load MCP servers into settings
        this.load_mcp_servers();
    }

    toggle_settings_panel() {
        if (this.$settingsPanel.is(":visible")) {
            this.close_settings_panel();
        } else {
            this.open_settings_panel();
        }
    }

    open_settings_panel() {
        this.$settingsOverlay.show().addClass("visible");
        this.$settingsPanel.show().addClass("open");
        this.load_mcp_servers();
    }

    close_settings_panel() {
        this.$settingsPanel.removeClass("open");
        this.$settingsOverlay.removeClass("visible");
        setTimeout(() => {
            this.$settingsPanel.hide();
            this.$settingsOverlay.hide();
        }, 300);
    }

    async load_mcp_servers() {
        try {
            const r = await frappe.call({ method: "niv_ai.niv_core.api.mcp.get_mcp_servers" });
            const servers = r.message || [];
            const $list = this.wrapper.find(".niv-mcp-server-list");
            $list.empty();
            if (!servers.length) {
                $list.html('<div class="niv-mcp-empty">No MCP servers configured</div>');
                return;
            }
            for (const s of servers) {
                const statusClass = s.is_active ? (s.status === "Connected" ? "connected" : (s.status === "Error" ? "error" : "active")) : "disabled";
                const $item = $(`<div class="niv-mcp-server-item">
                    <span class="niv-mcp-status-dot ${statusClass}"></span>
                    <span class="niv-mcp-server-name">${frappe.utils.escape_html(s.server_name)}</span>
                    <label class="niv-toggle-switch niv-toggle-sm">
                        <input type="checkbox" class="niv-mcp-toggle" data-server="${frappe.utils.escape_html(s.name)}" ${s.is_active ? "checked" : ""} />
                        <span class="niv-toggle-slider"></span>
                    </label>
                </div>`);
                $item.find(".niv-mcp-toggle").on("change", (e) => {
                    this.toggle_mcp_server($(e.target).data("server"), $(e.target).is(":checked"));
                });
                $list.append($item);
            }
        } catch (e) {
            // MCP not available
        }
    }

    async toggle_mcp_server(serverName, isActive) {
        try {
            await frappe.call({
                method: "niv_ai.niv_core.api.mcp.toggle_server",
                args: { server_name: serverName, is_active: isActive ? 1 : 0 }
            });
            this.load_mcp_servers();
        } catch (e) {
            frappe.msgprint("Failed to toggle MCP server");
        }
    }

    // ─── Conversations ──────────────────────────────────────────────

    async load_conversations() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.conversation.list_conversations",
                args: { limit: 100 },
            });
            this.conversations = r.message || [];
            this.render_conversation_list();

            if (this.conversations.length === 0 || !this.current_conversation) {
                // Always start fresh like ChatGPT — show welcome screen
                this.show_empty_state();
            }
        } catch (e) {
            frappe.msgprint(__("Failed to load conversations"));
        }
    }

    render_conversation_list() {
        this.$convList.empty();

        // Group conversations by date
        const groups = { today: [], yesterday: [], week: [], older: [] };
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
        const weekAgo = new Date(today); weekAgo.setDate(weekAgo.getDate() - 7);

        for (const conv of this.conversations) {
            const modified = new Date(conv.modified);
            if (modified >= today) groups.today.push(conv);
            else if (modified >= yesterday) groups.yesterday.push(conv);
            else if (modified >= weekAgo) groups.week.push(conv);
            else groups.older.push(conv);
        }

        const renderGroup = (label, convs) => {
            if (convs.length === 0) return;
            this.$convList.append(`<div class="niv-conv-date-group">${label}</div>`);
            for (const conv of convs) {
                const isActive = conv.name === this.current_conversation;
                const title = conv.title || "New Chat";
                const $item = $(`
                    <div class="niv-conv-item ${isActive ? "active" : ""}" data-name="${conv.name}">
                        <i class="fa fa-comment-o conv-icon"></i>
                        <span class="conv-title">${frappe.utils.escape_html(title)}</span>
                    </div>
                `);
                $item.on("click", () => this.select_conversation(conv.name));
                this.$convList.append($item);
            }
        };

        renderGroup("Today", groups.today);
        renderGroup("Yesterday", groups.yesterday);
        renderGroup("Previous 7 Days", groups.week);
        renderGroup("Older", groups.older);
    }

    async select_conversation(name) {
        this.current_conversation = name;
        this.$convList.find(".niv-conv-item").removeClass("active");
        this.$convList.find(`[data-name="${name}"]`).addClass("active");

        this.hide_empty_state();
        this.messages_data = [];
        this.reactions = {};
        await this.load_messages(name);
        this.load_pinned_messages();
    }

    async new_conversation() {
        // Don't create a conversation until user sends a message
        // This prevents empty "New Chat" entries in sidebar
        this.current_conversation = null;
        this.$convList.find(".niv-conv-item").removeClass("active");
        this.messages_data = [];
        this.show_empty_state();
        this.$input.val("").focus();
    }

    async _create_conversation_on_server(title) {
        // Actually create the conversation — called only when first message is sent
        const r = await frappe.call({
            method: "niv_ai.niv_core.api.conversation.create_conversation",
            args: { title: title || "New Chat" },
        });
        const conv = r.message;
        this.conversations.unshift(conv);
        this.render_conversation_list();
        this.$convList.find(`[data-name="${conv.name}"]`).addClass("active");
        return conv;
    }

    async delete_conversation() {
        if (!this.current_conversation) return;
        const confirmed = await new Promise((resolve) => {
            frappe.confirm(__("Delete this conversation?"), () => resolve(true), () => resolve(false));
        });
        if (!confirmed) return;

        try {
            await frappe.call({
                method: "niv_ai.niv_core.api.conversation.delete_conversation",
                args: { conversation_id: this.current_conversation },
            });
            this.conversations = this.conversations.filter((c) => c.name !== this.current_conversation);
            this.current_conversation = null;
            this.render_conversation_list();
            this.$chatArea.empty();
            this.messages_data = [];

            if (this.conversations.length > 0) {
                this.select_conversation(this.conversations[0].name);
            } else {
                this.show_empty_state();
            }
        } catch (e) {
            frappe.msgprint(__("Failed to delete conversation"));
        }
    }

    rename_conversation() {
        if (!this.current_conversation) return;
        const conv = this.conversations.find((c) => c.name === this.current_conversation);
        const d = new frappe.ui.Dialog({
            title: __("Rename Chat"),
            fields: [{ fieldname: "title", fieldtype: "Data", label: "Title", default: conv?.title || "" }],
            primary_action_label: __("Save"),
            primary_action: async (values) => {
                d.hide();
                await frappe.call({
                    method: "niv_ai.niv_core.api.conversation.rename_conversation",
                    args: { conversation_id: this.current_conversation, title: values.title },
                });
                if (conv) conv.title = values.title;
                this.render_conversation_list();
            },
        });
        d.show();
    }

    filter_conversations(query) {
        const q = query.toLowerCase();
        this.$convList.find(".niv-conv-item").each(function () {
            const title = $(this).find(".conv-title").text().toLowerCase();
            $(this).toggle(title.includes(q));
        });
        // Hide empty group headers
        this.$convList.find(".niv-conv-date-group").each(function () {
            const $next = $(this).nextUntil(".niv-conv-date-group");
            const anyVisible = $next.filter(":visible").length > 0;
            $(this).toggle(anyVisible);
        });
    }

    // ─── Messages ───────────────────────────────────────────────────

    async load_messages(conversation_id) {
        this.$chatArea.empty();
        this.messages_data = [];
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.conversation.get_messages",
                args: { conversation_id, limit: 100 },
            });
            const messages = r.message || [];
            if (messages.length === 0) {
                this.show_empty_state();
                return;
            }
            for (const msg of messages) {
                this.append_message(msg.role, msg.content, msg);
            }
            this.scroll_to_bottom();
            this.update_last_assistant_actions();
        } catch (e) {
            this.$chatArea.html('<div class="niv-error">Messages load nahi ho paye. Please try again. 🔄</div>');
        }
    }

    append_message(role, content, meta = {}) {
        this.hide_empty_state();
        const isUser = role === "user";
        const avatar = isUser ? this.get_user_avatar() : '<span style="font-size:16px;font-weight:700;">N</span>';
        const time = meta.creation ? frappe.datetime.prettyDate(meta.creation) : "";
        const msgIndex = this.messages_data.length;

        const toolsHtml = meta.tool_calls_json
            ? this.render_tool_calls(JSON.parse(meta.tool_calls_json), meta.tool_results_json ? JSON.parse(meta.tool_results_json) : [])
            : "";

        const tokenInfo = meta.total_tokens > 0
            ? `<span class="msg-tokens" title="Input: ${meta.input_tokens || 0} | Output: ${meta.output_tokens || 0}">${meta.total_tokens} tokens</span>`
            : "";

        const modelTag = "";

        const $msg = $(`
            <div class="niv-message ${isUser ? "user" : "assistant"}" data-msg-index="${msgIndex}">
                <div class="msg-avatar">${avatar}</div>
                <div class="msg-body">
                    ${modelTag}
                    ${toolsHtml}
                    <div class="msg-content">${this.render_markdown(content || "")}</div>
                    <div class="msg-footer">
                        <span class="msg-time">${time}</span>
                        ${tokenInfo}
                    </div>
                    <div class="msg-actions">
                        ${isUser ? `
                            <button class="msg-action-btn btn-copy-msg" title="Copy"><i class="fa fa-copy"></i></button>
                            <button class="msg-action-btn btn-edit-msg" title="Edit"><i class="fa fa-pencil"></i></button>
                            <button class="msg-action-btn btn-pin-msg ${meta.is_pinned ? 'active' : ''}" title="Pin"><i class="fa fa-thumb-tack"></i></button>
                        ` : `
                            <button class="msg-action-btn btn-copy-msg" title="Copy"><i class="fa fa-copy"></i></button>
                            <button class="msg-action-btn btn-tts-msg" title="Read aloud"><i class="fa fa-volume-up"></i></button>
                            <button class="msg-action-btn btn-pin-msg ${meta.is_pinned ? 'active' : ''}" title="Pin"><i class="fa fa-thumb-tack"></i></button>
                            <button class="msg-action-btn btn-regen-msg" title="Regenerate" style="display:none;"><i class="fa fa-refresh"></i></button>
                        `}
                    </div>
                </div>
            </div>
        `);

        // Bind action events
        $msg.find(".btn-copy-msg").on("click", () => this.copy_message(msgIndex));
        $msg.find(".btn-edit-msg").on("click", () => this.edit_message(msgIndex));
        $msg.find(".btn-tts-msg").on("click", () => this.speak(content));
        $msg.find(".btn-regen-msg").on("click", () => this.regenerate_response());
        $msg.find(".btn-pin-msg").on("click", () => this.toggle_pin(msgIndex));
        $msg.find(".btn-react-up").on("click", (e) => this.toggle_reaction(msgIndex, "up", $(e.currentTarget)));
        $msg.find(".btn-react-down").on("click", (e) => this.toggle_reaction(msgIndex, "down", $(e.currentTarget)));

        // Pinned indicator
        if (meta.is_pinned) {
            $msg.addClass("pinned");
        }

        this.$chatArea.append($msg);
        this.messages_data.push({ role, content: content || "", meta, $el: $msg });

        // Reactions disabled
        if (false && meta.reactions_json) {
            try {
                const reactions = typeof meta.reactions_json === "string" ? JSON.parse(meta.reactions_json) : meta.reactions_json;
                this.render_reactions($msg, reactions, msgIndex);
            } catch (e) {}
        }

        this.add_code_copy_buttons($msg);

        if (window.hljs) {
            $msg.find("pre code").each(function () {
                hljs.highlightElement(this);
            });
        }

        return $msg;
    }

    update_last_assistant_actions() {
        this.$chatArea.find(".btn-regen-msg").hide();
        const assistantMsgs = this.$chatArea.find(".niv-message.assistant");
        if (assistantMsgs.length > 0) {
            assistantMsgs.last().find(".btn-regen-msg").show();
        }
    }

    add_code_copy_buttons($container) {
        $container.find("pre").each(function () {
            if ($(this).find(".code-copy-btn").length) return;
            const $btn = $('<button class="code-copy-btn" title="Copy code"><i class="fa fa-copy"></i></button>');
            $(this).css("position", "relative").append($btn);
            $btn.on("click", function () {
                const code = $(this).closest("pre").find("code").text();
                navigator.clipboard.writeText(code).then(() => {
                    const $b = $(this);
                    $b.html('<i class="fa fa-check"></i>');
                    setTimeout(() => $b.html('<i class="fa fa-copy"></i>'), 1500);
                });
            });
        });
    }

    render_markdown(text) {
        if (!text) return "";
        if (window.marked) {
            try {
                let html = marked.parse(text);
                html = html.replace(/<a /g, '<a target="_blank" ');
                // Render inline images with lightbox
                html = html.replace(/<img\s+([^>]*?)src="([^"]+)"([^>]*?)>/g,
                    '<img $1src="$2"$3 class="niv-inline-image" onclick="window.open(\'$2\', \'_blank\')" style="max-width:100%;border-radius:8px;cursor:pointer;margin:8px 0;" />');
                // Detect bare /files/ URLs and render as images
                html = html.replace(/(?<!="|'|src=")(\/(files|private\/files)\/[^\s<"']+\.(png|jpg|jpeg|gif|webp))/gi,
                    '<img src="$1" class="niv-inline-image" onclick="window.open(\'$1\', \'_blank\')" style="max-width:100%;border-radius:8px;cursor:pointer;margin:8px 0;" />');
                return html;
            } catch (e) {
                console.error("Markdown parse error:", e);
            }
        }
        let html = frappe.utils.escape_html(text);
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
        });
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        html = html.replace(/\n/g, "<br>");
        return html;
    }

    render_tool_calls(toolCalls, toolResults = []) {
        if (!toolCalls || toolCalls.length === 0) return "";
        let html = '<div class="msg-tool-calls">';
        for (let i = 0; i < toolCalls.length; i++) {
            const tc = toolCalls[i];
            const result = toolResults[i] || null;
            const resultJson = result ? JSON.stringify(result.result || result, null, 2) : "";
            const argsJson = JSON.stringify(tc.arguments || {}, null, 2);
            html += `
                <div class="tool-call-accordion">
                    <div class="tool-call-header" onclick="$(this).closest('.tool-call-accordion').toggleClass('open')">
                        <i class="fa fa-check-circle tool-status-icon"></i>
                        <span class="tool-name">${frappe.utils.escape_html(tc.name)}</span>
                        <i class="fa fa-chevron-right tool-chevron"></i>
                    </div>
                    <div class="tool-call-body">
                        <div class="tool-section"><strong>Input:</strong><pre><code>${frappe.utils.escape_html(argsJson)}</code></pre></div>
                        ${resultJson ? `<div class="tool-section"><strong>Output:</strong><pre><code>${frappe.utils.escape_html(resultJson.substring(0, 2000))}</code></pre></div>` : ""}
                    </div>
                </div>
            `;
        }
        html += "</div>";
        return html;
    }

    get_user_avatar() {
        const fullName = frappe.session.user_fullname || "U";
        const initials = fullName.split(" ").map((n) => n[0]).join("").substring(0, 2).toUpperCase();
        return `<span class="user-initials">${initials}</span>`;
    }

    // ─── Message Actions ────────────────────────────────────────────

    copy_message(msgIndex) {
        const data = this.messages_data[msgIndex];
        if (!data) return;
        navigator.clipboard.writeText(data.content).then(() => {
            const $btn = data.$el.find(".btn-copy-msg");
            $btn.html('<i class="fa fa-check"></i>');
            setTimeout(() => $btn.html('<i class="fa fa-copy"></i>'), 1500);
        });
    }

    edit_message(msgIndex) {
        const data = this.messages_data[msgIndex];
        if (!data || data.role !== "user") return;
        this.edit_mode = true;

        const $content = data.$el.find(".msg-content");
        const originalText = data.content;
        $content.html(`
            <div class="edit-message-form">
                <textarea class="form-control edit-textarea">${frappe.utils.escape_html(originalText)}</textarea>
                <div class="edit-actions">
                    <button class="btn btn-primary btn-sm btn-save-edit">Save & Submit</button>
                    <button class="btn btn-default btn-sm btn-cancel-edit">Cancel</button>
                </div>
            </div>
        `);

        const $textarea = $content.find(".edit-textarea");
        $textarea.focus();
        $textarea.css("height", Math.min($textarea[0].scrollHeight, 200) + "px");

        $content.find(".btn-save-edit").on("click", () => {
            const newText = $content.find(".edit-textarea").val().trim();
            if (!newText) return;
            this.edit_mode = false;

            for (let i = this.messages_data.length - 1; i > msgIndex; i--) {
                this.messages_data[i].$el.remove();
            }
            this.messages_data = this.messages_data.slice(0, msgIndex);
            data.$el.remove();

            this.$input.val(newText);
            this.send_message();
        });

        $content.find(".btn-cancel-edit").on("click", () => this.cancel_edit_at(msgIndex));
    }

    cancel_edit() {
        this.edit_mode = false;
        this.$chatArea.find(".edit-message-form").each((_, el) => {
            const $msg = $(el).closest(".niv-message");
            const idx = parseInt($msg.data("msg-index"));
            if (this.messages_data[idx]) {
                $msg.find(".msg-content").html(this.render_markdown(this.messages_data[idx].content));
            }
        });
    }

    cancel_edit_at(msgIndex) {
        this.edit_mode = false;
        const data = this.messages_data[msgIndex];
        if (data) {
            data.$el.find(".msg-content").html(this.render_markdown(data.content));
            this.add_code_copy_buttons(data.$el);
        }
    }

    async regenerate_response() {
        if (this.is_streaming) return;
        let lastUserIndex = -1;
        for (let i = this.messages_data.length - 1; i >= 0; i--) {
            if (this.messages_data[i].role === "user") {
                lastUserIndex = i;
                break;
            }
        }
        if (lastUserIndex === -1) return;

        const userText = this.messages_data[lastUserIndex].content;

        const lastAssistant = this.messages_data[this.messages_data.length - 1];
        if (lastAssistant && lastAssistant.role === "assistant") {
            lastAssistant.$el.remove();
            this.messages_data.pop();
        }

        this.$input.val(userText);
        this.send_message();
    }

    toggle_reaction(msgIndex, type, $btn) {
        const current = this.reactions[msgIndex];
        const $msg = this.messages_data[msgIndex].$el;

        $msg.find(".btn-react-up, .btn-react-down").removeClass("active");

        if (current === type) {
            this.reactions[msgIndex] = null;
        } else {
            this.reactions[msgIndex] = type;
            $btn.addClass("active");
        }
    }

    // ─── Send Message ───────────────────────────────────────────────

    async send_message() {
        const text = this.$input.val().trim();
        if (!text && this.pending_files.length === 0) return;
        if (this.is_streaming) return;

        // Handle slash commands
        if (text.startsWith("/")) {
            this.$input.val("").css("height", "auto");
            this.$inputPill.removeClass("has-text");
            this.$slashDropdown.hide();
            this.execute_slash_command(text);
            return;
        }

        if (!this.current_conversation) {
            // Create conversation on server (lazy — only when user actually sends a message)
            try {
                const conv = await this._create_conversation_on_server("New Chat");
                this.current_conversation = conv.name;
                this.hide_empty_state();
            } catch (e) {
                frappe.msgprint(__("Failed to create conversation"));
                return;
            }
        }

        this.$input.val("").css("height", "auto");
        this.$inputPill.removeClass("has-text");
        localStorage.removeItem("niv_draft");

        this.append_message("user", text);
        this.scroll_to_bottom();

        const attachments = this.pending_files.map((f) => ({ file_url: f.file_url }));
        this.pending_files = [];
        this.$attachPreview.empty().hide();

        this.show_typing();
        this.is_streaming = true;
        this.$sendBtn.hide();
        this.$stopBtn.show();

        try {
            await this.send_with_stream(text, attachments);
        } catch (e) {
            try {
                const args = {
                    conversation_id: this.current_conversation,
                    message: text,
                    attachments: JSON.stringify(attachments),
                    context: JSON.stringify(this.get_current_context()),
                };
                if (this.selected_model) args.model = this.selected_model;

                const r = await frappe.call({
                    method: "niv_ai.niv_core.api.chat.send_message",
                    args,
                });
                this.hide_typing();
                const data = r.message;
                this.append_message("assistant", data.response || data.message, {
                    total_tokens: data.total_tokens,
                    input_tokens: data.input_tokens,
                    output_tokens: data.output_tokens,
                    model: data.model || this.selected_model || "",
                    tool_calls_json: data.tool_calls ? JSON.stringify(data.tool_calls) : null,
                });
            } catch (err) {
                this.hide_typing();
                this.append_message("assistant", `❌ Kuch galat ho gaya. Please try again.\n\n_${err.message || ""}_`, { is_error: 1 });
            }
        }

        this.is_streaming = false;
        this.$sendBtn.show();
        this.$stopBtn.hide();
        this.scroll_to_bottom();
        this.load_balance();
        this.update_last_assistant_actions();

        this.auto_title(text);
    }

    auto_title(text) {
        const conv = this.conversations.find((c) => c.name === this.current_conversation);
        if (conv && conv.title === "New Chat" && text.length > 0) {
            const title = text.substring(0, 50).trim() + (text.length > 50 ? "..." : "");
            conv.title = title;
            this.render_conversation_list();
            frappe.call({
                method: "frappe.client.set_value",
                args: { doctype: "Niv Conversation", name: this.current_conversation, fieldname: "title", value: title },
            });
        }
    }

    get_current_context() {
        // In widget mode, use parent page's context
        if (this.parent_context) {
            return this.parent_context;
        }
        // Fallback: check if parent set context directly on window
        if (window.__niv_parent_context) {
            return window.__niv_parent_context;
        }
        // Fallback: try to read from parent window (iframe scenario)
        try {
            if (window.parent !== window) {
                const parentRoute = window.parent.frappe && window.parent.frappe.get_route();
                if (parentRoute && parentRoute[0] === "Form" && parentRoute.length >= 3) {
                    return { route: parentRoute, doctype: parentRoute[1], docname: parentRoute[2] };
                }
            }
        } catch(e) {}
        const route = frappe.get_route();
        const ctx = { route };
        if (route && route[0] === "Form" && route.length >= 3) {
            ctx.doctype = route[1];
            ctx.docname = route[2];
        }
        return ctx;
    }

    async send_with_stream(text, attachments) {
        return new Promise((resolve, reject) => {
            const params = {
                conversation_id: this.current_conversation,
                message: text,
                attachments: JSON.stringify(attachments),
                context: JSON.stringify(this.get_current_context()),
            };
            if (this.selected_model) params.model = this.selected_model;

            const url = "/api/method/niv_ai.niv_core.api.stream.stream_chat?" +
                new URLSearchParams(params).toString();

            const evtSource = new EventSource(url, { withCredentials: true });
            this.event_source = evtSource;
            let $msgEl = null;
            let fullContent = "";
            let toolCallsAccum = [];
            let toolResultsAccum = [];

            evtSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === "token" || data.type === "chunk") {
                        if (!$msgEl) {
                            this.hide_typing();
                            $msgEl = this.append_message("assistant", "", {
                                model: this.selected_model || data.model || ""
                            });
                        }
                        fullContent += data.content;
                        $msgEl.find(".msg-content").html(this.render_markdown(fullContent));
                        const idx = this.messages_data.length - 1;
                        if (this.messages_data[idx]) this.messages_data[idx].content = fullContent;
                        this.add_code_copy_buttons($msgEl);
                        if (window.hljs) {
                            $msgEl.find("pre code:not(.hljs)").each(function () { hljs.highlightElement(this); });
                        }
                        this.scroll_to_bottom_if_near();
                    } else if (data.type === "tool_call") {
                        if (!$msgEl) {
                            this.hide_typing();
                            $msgEl = this.append_message("assistant", "");
                        }
                        this.update_typing_text("Niv is calling tools...");
                        toolCallsAccum.push({ name: data.tool, arguments: data.params });
                        const $toolHtml = $(`
                            <div class="tool-call-accordion running">
                                <div class="tool-call-header">
                                    <i class="fa fa-spinner fa-spin tool-status-icon"></i>
                                    <span class="tool-name">${frappe.utils.escape_html(data.tool)}</span>
                                    <span class="tool-running-text">Running...</span>
                                </div>
                            </div>
                        `);
                        if (!$msgEl.find(".msg-tool-calls").length) {
                            $msgEl.find(".msg-body").find(".msg-content").before('<div class="msg-tool-calls"></div>');
                        }
                        $msgEl.find(".msg-tool-calls").append($toolHtml);
                        this.scroll_to_bottom_if_near();
                    } else if (data.type === "tool_result") {
                        toolResultsAccum.push({ name: data.tool, result: data.result });
                        const $running = $msgEl.find(".tool-call-accordion.running").first();
                        $running.removeClass("running");
                        $running.find(".tool-status-icon").removeClass("fa-spinner fa-spin").addClass("fa-check-circle");
                        $running.find(".tool-running-text").remove();
                        const resultStr = JSON.stringify(data.result || {}, null, 2).substring(0, 2000);
                        $running.find(".tool-call-header").attr("onclick", "$(this).closest('.tool-call-accordion').toggleClass('open')");
                        $running.append(`
                            <div class="tool-call-body">
                                <div class="tool-section"><strong>Result:</strong><pre><code>${frappe.utils.escape_html(resultStr)}</code></pre></div>
                            </div>
                        `);
                        $running.find(".tool-call-header").append('<i class="fa fa-chevron-right tool-chevron"></i>');
                    } else if (data.type === "suggestions") {
                        // AI follow-up suggestions
                        if ($msgEl && data.items && data.items.length > 0) {
                            this.render_suggestions(data.items, $msgEl);
                        }
                        evtSource.close();
                        this.event_source = null;
                    } else if (data.type === "done") {
                        // Don't close yet — wait for possible suggestions event
                        if ($msgEl) {
                            const tokens = data.tokens?.total_tokens || 0;
                            if (tokens) {
                                $msgEl.find(".msg-footer").prepend(`<span class="msg-tokens">${tokens} tokens</span>`);
                            }
                        }
                        // Update balance from stream response
                        if (data.remaining_balance !== undefined) {
                            this.update_balance_from_response(data.remaining_balance);
                        }
                        resolve();
                        // Auto-close after timeout if no suggestions arrive
                        setTimeout(() => {
                            if (this.event_source === evtSource) {
                                evtSource.close();
                                this.event_source = null;
                            }
                        }, 20000);
                    } else if (data.type === "error") {
                        evtSource.close();
                        this.event_source = null;
                        this.hide_typing();
                        const errMsg = data.message || data.content || "Something went wrong";
                        if (errMsg.toLowerCase().includes("insufficient") || errMsg.toLowerCase().includes("balance")) {
                            this.append_message("assistant", `💳 Credits khatam ho gaye!\n\n${errMsg}\n\nPlease recharge karein.`, { is_error: 1 });
                            this.load_balance();
                        } else if (errMsg.toLowerCase().includes("rate limit")) {
                            this.append_message("assistant", `⏳ Bahut zyada messages! Thodi der mein try karein.\n\n_${errMsg}_`, { is_error: 1 });
                        } else if (errMsg.toLowerCase().includes("timeout") || errMsg.toLowerCase().includes("timed out")) {
                            this.append_message("assistant", `⏱️ Request timeout ho gayi. Please dubara try karein.`, { is_error: 1 });
                        } else if (errMsg.toLowerCase().includes("api key") || errMsg.toLowerCase().includes("auth")) {
                            this.append_message("assistant", `🔑 AI provider authentication failed. Admin se contact karein.`, { is_error: 1 });
                        } else {
                            this.append_message("assistant", `❌ ${errMsg}`, { is_error: 1 });
                        }
                        resolve();
                    }
                } catch (e) { /* ignore parse errors */ }
            };

            let retryCount = 0;
            evtSource.onerror = () => {
                evtSource.close();
                this.event_source = null;
                if (!$msgEl && retryCount < 1) {
                    // First failure before any response — retry once via non-stream fallback
                    retryCount++;
                    reject(new Error("SSE failed — retrying via fallback"));
                } else if (!$msgEl) {
                    this.hide_typing();
                    this.append_message("assistant", `🔄 Connection lost. Please try again.\n\n_Network ya server issue ho sakta hai._`, { is_error: 1 });
                    resolve();
                } else {
                    // Partial response received — keep what we have
                    resolve();
                }
            };
        });
    }

    stop_generation() {
        if (this.event_source) {
            this.event_source.close();
            this.event_source = null;
        }
        this.hide_typing();
        this.is_streaming = false;
        this.$sendBtn.show();
        this.$stopBtn.hide();
        this.update_last_assistant_actions();
    }

    scroll_to_bottom_if_near() {
        const el = this.$chatArea[0];
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        if (distFromBottom < 300) {
            this.scroll_to_bottom();
        } else {
            this.unread_count++;
            this.$scrollBottom.find(".scroll-unread-badge").text(this.unread_count).show();
        }
    }

    // ─── File Upload ────────────────────────────────────────────────

    handle_file_select(e) {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        for (const file of files) {
            if (file.size > 10 * 1024 * 1024) {
                frappe.msgprint(__(`File "${file.name}" exceeds 10MB limit`));
                continue;
            }
            this.upload_file(file);
        }
        this.$fileInput.val("");
    }

    async upload_file(file) {
        // Show uploading indicator
        const tempId = "upload-" + Date.now();
        this.$attachPreview.show();
        const $uploading = $(`
            <div class="attach-item" id="${tempId}">
                <div class="attach-icon"><i class="fa fa-spinner fa-spin"></i></div>
                <div class="attach-info">
                    <div class="attach-name">${frappe.utils.escape_html(file.name)}</div>
                    <div class="attach-size">Uploading...</div>
                </div>
            </div>
        `);
        this.$attachPreview.append($uploading);

        try {
            const r = await frappe.call({
                method: "frappe.client.upload_file",
                args: { file, is_private: 1, folder: "Home/Niv AI" },
                file_args: { file },
            });
            const fileDoc = r.message;
            fileDoc._local_file = file; // keep ref for preview
            this.pending_files.push(fileDoc);
            $uploading.remove();
            this.render_file_preview(fileDoc);
        } catch (e) {
            $uploading.remove();
            if (this.pending_files.length === 0) this.$attachPreview.hide();
            frappe.msgprint(__("File upload failed"));
        }
    }

    _get_file_icon(filename) {
        const ext = (filename || "").split(".").pop().toLowerCase();
        const icons = {
            pdf: "📄", xlsx: "📊", xls: "📊", csv: "📊",
            docx: "📝", doc: "📝", txt: "📃", md: "📃",
            py: "🐍", js: "📜", json: "📋", html: "🌐", css: "🎨",
            jpg: "🖼️", jpeg: "🖼️", png: "🖼️", gif: "🖼️", webp: "🖼️",
        };
        return icons[ext] || "📎";
    }

    _format_file_size(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    _is_image_file(filename) {
        const ext = (filename || "").split(".").pop().toLowerCase();
        return ["jpg", "jpeg", "png", "gif", "webp"].includes(ext);
    }

    render_file_preview(fileDoc) {
        this.$attachPreview.show();
        const fileName = fileDoc.file_name || fileDoc.name || "file";
        const isImage = this._is_image_file(fileName);
        const icon = this._get_file_icon(fileName);
        const size = fileDoc._local_file ? this._format_file_size(fileDoc._local_file.size) : "";

        let thumbHtml = "";
        if (isImage && fileDoc._local_file) {
            const objectUrl = URL.createObjectURL(fileDoc._local_file);
            thumbHtml = `<img class="attach-thumb" src="${objectUrl}" alt="" />`;
        } else {
            thumbHtml = `<div class="attach-icon">${icon}</div>`;
        }

        const $preview = $(`
            <div class="attach-item" data-url="${fileDoc.file_url}">
                ${thumbHtml}
                <div class="attach-info">
                    <div class="attach-name">${frappe.utils.escape_html(fileName)}</div>
                    ${size ? `<div class="attach-size">${size}</div>` : ""}
                </div>
                <button class="btn-remove-attach"><i class="fa fa-times"></i></button>
            </div>
        `);
        $preview.find(".btn-remove-attach").on("click", () => {
            this.pending_files = this.pending_files.filter((f) => f.file_url !== fileDoc.file_url);
            $preview.remove();
            if (this.pending_files.length === 0) this.$attachPreview.hide();
        });
        this.$attachPreview.append($preview);
    }

    // ─── Voice Input ────────────────────────────────────────────────

    toggle_voice_input() {
        if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
            frappe.msgprint(__("Voice input not supported in this browser"));
            return;
        }
        if (this.recognition) {
            this.recognition.stop();
            this.recognition = null;
            this.$voiceBtn.removeClass("recording");
            return;
        }
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = false;
        this.recognition.lang = "hi-IN";
        this.$voiceBtn.addClass("recording");

        this.recognition.onresult = (event) => {
            let finalTranscript = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    finalTranscript += event.results[i][0].transcript;
                }
            }
            if (finalTranscript.trim()) {
                // Append to existing text (don't overwrite)
                const existing = this.$input.val().trim();
                this.$input.val(existing ? existing + " " + finalTranscript.trim() : finalTranscript.trim());
                this.$input.trigger("input");
            }
        };
        this.recognition.onend = () => {
            this.$voiceBtn.removeClass("recording");
            this.recognition = null;
        };
        this.recognition.onerror = (e) => {
            if (e.error !== "no-speech") console.warn("STT error:", e.error);
            this.$voiceBtn.removeClass("recording");
            this.recognition = null;
        };
        this.recognition.start();
    }

    // ─── TTS ────────────────────────────────────────────────────────

    cleanTextForTTS(text) {
        if (!text) return "";
        let t = text;

        // Remove code blocks entirely → "code block"
        t = t.replace(/```[\s\S]*?```/g, ' code block ');
        // Remove inline code
        t = t.replace(/`[^`]+`/g, '');

        // Collapse error stack traces
        t = t.replace(/Traceback \(most recent call last\):[\s\S]*?(?:\n\S|$)/g, ' There was an error. ');
        t = t.replace(/^[ \t]*(?:at |File "|Exception|Error:|Caused by:).*$/gm, '');

        // Remove HTML tags
        t = t.replace(/<[^>]+>/g, '');

        // Markdown images ![alt](url) → alt
        t = t.replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1');
        // Markdown links [text](url) → text
        t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
        // Bare URLs
        t = t.replace(/https?:\/\/\S+/g, '');

        // Tables (lines of pipes)
        t = t.replace(/^\|.*\|$/gm, '');
        t = t.replace(/^[\s|:-]+$/gm, '');

        // Headings → sentence ending
        t = t.replace(/^#{1,6}\s+(.*)/gm, '$1.');

        // Bold/italic/strikethrough
        t = t.replace(/\*\*\*(.+?)\*\*\*/g, '$1');
        t = t.replace(/\*\*(.+?)\*\*/g, '$1');
        t = t.replace(/\*(.+?)\*/g, '$1');
        t = t.replace(/__(.+?)__/g, '$1');
        t = t.replace(/_(.+?)_/g, '$1');
        t = t.replace(/~~(.+?)~~/g, '$1');

        // Blockquotes
        t = t.replace(/^>\s?/gm, '');

        // List markers
        t = t.replace(/^\s*[-*+]\s+/gm, '');
        t = t.replace(/^\s*\d+\.\s+/gm, '');

        // Horizontal rules
        t = t.replace(/^[-*=]{3,}\s*$/gm, '');

        // Emoji shortcodes
        t = t.replace(/:([a-zA-Z0-9_+-]+):/g, '$1');

        // Collapse whitespace
        t = t.replace(/\n{2,}/g, '. ');
        t = t.replace(/\n/g, ' ');
        t = t.replace(/\s{2,}/g, ' ');
        t = t.replace(/\.(\s*\.)+/g, '.');

        return t.trim();
    }

    speak(text) {
        let clean = this.cleanTextForTTS(text);
        if (!clean) return;

        // Try Piper TTS API first
        frappe.call({
            method: "niv_ai.niv_core.api.voice.text_to_speech",
            args: { text: clean },
            async: true,
            callback: (r) => {
                if (r.message && r.message.audio_url) {
                    // Play server-generated audio
                    const audio = new Audio(r.message.audio_url);
                    audio.play().catch(() => this._speak_browser(clean));
                    // Cleanup file after playback
                    audio.onended = () => {
                        frappe.call({
                            method: "niv_ai.niv_core.api.voice.cleanup_voice_file",
                            args: { file_url: r.message.audio_url },
                            async: true,
                        });
                    };
                } else {
                    // Fallback to browser TTS
                    this._speak_browser(clean);
                }
            },
            error: () => this._speak_browser(clean),
        });
    }

    _speak_browser(text) {
        if (!("speechSynthesis" in window)) return;
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "hi-IN";
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        window.speechSynthesis.speak(utterance);
    }

    // ─── Search in Messages ─────────────────────────────────────────

    toggle_search_bar(show) {
        if (show === undefined) show = !this.$searchBar.is(":visible");
        if (show) {
            this.$searchBar.show();
            this.$msgSearchInput.focus();
        } else {
            this.$searchBar.hide();
            this.$msgSearchInput.val("");
            this.clear_search_highlights();
        }
    }

    search_in_messages(query) {
        this.clear_search_highlights();
        this.search_matches = [];
        this.search_index = -1;

        if (!query || query.length < 2) {
            this.wrapper.find(".niv-search-count").text("");
            return;
        }

        const q = query.toLowerCase();
        this.$chatArea.find(".niv-message .msg-content").each((_, el) => {
            const $el = $(el);
            const text = $el.text().toLowerCase();
            if (text.includes(q)) {
                this.search_matches.push($el);
                const html = $el.html();
                const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
                $el.html(html.replace(regex, '<mark class="niv-search-highlight">$1</mark>'));
            }
        });

        const count = this.search_matches.length;
        this.wrapper.find(".niv-search-count").text(count ? `${count} found` : "No results");
        if (count > 0) this.navigate_search(1);
    }

    navigate_search(dir) {
        if (this.search_matches.length === 0) return;
        this.$chatArea.find(".niv-search-highlight.active").removeClass("active");

        this.search_index += dir;
        if (this.search_index >= this.search_matches.length) this.search_index = 0;
        if (this.search_index < 0) this.search_index = this.search_matches.length - 1;

        const $match = this.search_matches[this.search_index];
        const $highlight = $match.find(".niv-search-highlight").first();
        $highlight.addClass("active");
        $match.closest(".niv-message")[0].scrollIntoView({ behavior: "smooth", block: "center" });

        this.wrapper.find(".niv-search-count").text(`${this.search_index + 1}/${this.search_matches.length}`);
    }

    clear_search_highlights() {
        this.$chatArea.find("mark.niv-search-highlight").each(function () {
            $(this).replaceWith($(this).text());
        });
    }

    // ─── Export Chat ────────────────────────────────────────────────

    export_chat() {
        if (this.messages_data.length === 0) {
            frappe.msgprint(__("No messages to export"));
            return;
        }
        let md = "";
        for (const msg of this.messages_data) {
            const heading = msg.role === "user" ? "User" : "Assistant";
            md += `## ${heading}\n${msg.content}\n\n---\n\n`;
        }
        const blob = new Blob([md], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `niv-chat-${this.current_conversation || "export"}.md`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // ─── UI Helpers ─────────────────────────────────────────────────

    show_typing() {
        this.typing_start = Date.now();
        if (!this.wrapper.find(".niv-typing-indicator").length) {
            this.$chatArea.append(`
                <div class="niv-typing-indicator">
                    <div class="msg-avatar"><span style="font-size:16px;font-weight:700;">N</span></div>
                    <div class="typing-content">
                        <span class="typing-text">Niv is thinking</span>
                        <span class="typing-dots-anim"><span></span><span></span><span></span></span>
                        <span class="typing-elapsed"></span>
                    </div>
                </div>
            `);
        }
        this.typing_timer = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.typing_start) / 1000);
            this.wrapper.find(".typing-elapsed").text(`${elapsed}s`);
        }, 1000);
        this.scroll_to_bottom();
    }

    update_typing_text(text) {
        this.wrapper.find(".typing-text").text(text);
    }

    hide_typing() {
        this.wrapper.find(".niv-typing-indicator").remove();
        if (this.typing_timer) {
            clearInterval(this.typing_timer);
            this.typing_timer = null;
        }
    }

    show_empty_state() {
        if (this.wrapper.find(".niv-empty-state").length) return;
        const greeting = this.get_greeting();
        const firstName = this.get_first_name();
        this.$chatArea.html(`
            <div class="niv-empty-state">
                <div class="empty-orb">
                    <div class="empty-orb-inner"></div>
                    <div class="empty-orb-ring"></div>
                </div>
                <div class="empty-greeting">${greeting}, ${frappe.utils.escape_html(firstName)}</div>
                <div class="empty-subtitle">How can I help you today?</div>
            </div>
        `);
    }

    hide_empty_state() {
        this.wrapper.find(".niv-empty-state").remove();
    }

    scroll_to_bottom() {
        const el = this.$chatArea[0];
        if (el) el.scrollTop = el.scrollHeight;
    }

    toggle_fullscreen() {
        const container = this.wrapper.find(".niv-chat-container")[0];
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else {
            container.requestFullscreen().catch(() => {});
        }
    }

    async load_balance() {
        try {
            // Check if billing is enabled
            const settings = await frappe.call({ method: "frappe.client.get", args: { doctype: "Niv Settings", name: "Niv Settings" } });
            if (!settings.message || !settings.message.enable_billing) {
                // Billing disabled — hide billing UI
                this.wrapper.find(".niv-settings-credits-row").hide();
                this.$lowBalanceWarning.hide();
                this.wrapper.find(".btn-usage-stats").hide();
                return;
            }
            this.wrapper.find(".niv-settings-credits-row").show();
            this.wrapper.find(".btn-usage-stats").show();
            const r = await frappe.call({ method: "niv_ai.niv_billing.api.billing.check_balance" });
            const data = r.message;
            if (data && data.balance !== undefined) {
                const label = data.mode === "shared_pool" ? "pool" : "credits";
                this.$credits.text(this.format_credits(data.balance));
                this.wrapper.find(".credit-label").text(label);
                // Show daily usage for shared pool
                if (data.mode === "shared_pool" && data.daily_limit) {
                    this.$credits.attr("title", `Daily: ${data.daily_used || 0}/${data.daily_limit} tokens`);
                }
                this.current_balance = data.balance;

                // Low balance warning
                if (data.balance < 500 && data.balance > 0) {
                    this.$lowBalanceWarning.show();
                    this.$credits.css("color", "#f59e0b");
                } else if (data.balance <= 0) {
                    this.$lowBalanceWarning.show().find("span").html(
                        '<strong>No credits remaining!</strong> <a href="#" class="recharge-link">Recharge now</a>'
                    );
                    this.$lowBalanceWarning.find(".recharge-link").on("click", (e) => {
                        e.preventDefault(); this.show_recharge_dialog();
                    });
                    this.$credits.css("color", "#ef4444");
                    // Disable input when no credits
                    this.$input.prop("disabled", true).attr("placeholder", "No credits remaining. Please recharge.");
                    this.$sendBtn.prop("disabled", true);
                } else {
                    this.$lowBalanceWarning.hide();
                    this.$credits.css("color", "");
                    this.$input.prop("disabled", false).attr("placeholder", "Message Niv AI...");
                    this.$sendBtn.prop("disabled", false);
                }
            }
        } catch (e) {
            this.$credits.text("∞");
        }
    }

    update_balance_from_response(balance) {
        if (balance !== undefined && balance !== null) {
            this.$credits.text(this.format_credits(balance));
            this.current_balance = balance;
            if (balance < 500 && balance > 0) {
                this.$lowBalanceWarning.show();
                this.$credits.css("color", "#f59e0b");
                this.$input.prop("disabled", false).attr("placeholder", "Message Niv AI...");
                this.$sendBtn.prop("disabled", false);
            } else if (balance <= 0) {
                this.$lowBalanceWarning.show();
                this.$credits.css("color", "#ef4444");
                this.$input.prop("disabled", true).attr("placeholder", "No credits remaining. Please recharge.");
                this.$sendBtn.prop("disabled", true);
            } else {
                this.$lowBalanceWarning.hide();
                this.$credits.css("color", "");
                this.$input.prop("disabled", false).attr("placeholder", "Message Niv AI...");
                this.$sendBtn.prop("disabled", false);
            }
        }
    }

    async show_recharge_dialog() {
        frappe.set_route("niv-credits");
    }

    async show_usage_dialog() {
        const d = new frappe.ui.Dialog({
            title: __("Usage Statistics"),
            fields: [
                { fieldname: "period", fieldtype: "Select", label: "Period",
                  options: "today\nweek\nmonth", default: "month",
                  change: () => loadUsage(d.get_value("period")) },
                { fieldname: "usage_html", fieldtype: "HTML" },
            ],
            size: "large",
        });
        d.show();

        const loadUsage = async (period) => {
            try {
                const r = await frappe.call({
                    method: "niv_ai.niv_billing.api.billing.get_usage_stats",
                    args: { period },
                });
                const data = r.message;
                const s = data.summary || {};
                const balance = data.balance || 0;
                const total = balance + (s.total_tokens || 0);
                const usedPct = total > 0 ? Math.round((s.total_tokens / total) * 100) : 0;

                let html = `
                    <div style="margin-top:12px;">
                        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;">
                            <div style="background:#f3f4f6;border-radius:8px;padding:12px;text-align:center;">
                                <div style="font-size:22px;font-weight:700;color:#7c3aed;">${(s.total_tokens || 0).toLocaleString()}</div>
                                <div style="font-size:12px;color:#6b7280;">Tokens Used</div>
                            </div>
                            <div style="background:#f3f4f6;border-radius:8px;padding:12px;text-align:center;">
                                <div style="font-size:22px;font-weight:700;color:#10b981;">${balance.toLocaleString()}</div>
                                <div style="font-size:12px;color:#6b7280;">Remaining</div>
                            </div>
                            <div style="background:#f3f4f6;border-radius:8px;padding:12px;text-align:center;">
                                <div style="font-size:22px;font-weight:700;color:#3b82f6;">${s.total_requests || 0}</div>
                                <div style="font-size:12px;color:#6b7280;">Requests</div>
                            </div>
                        </div>
                        <div style="margin-bottom:16px;">
                            <div style="display:flex;justify-content:space-between;font-size:12px;color:#6b7280;margin-bottom:4px;">
                                <span>Usage</span><span>${usedPct}%</span>
                            </div>
                            <div style="background:#e5e7eb;border-radius:4px;height:8px;overflow:hidden;">
                                <div style="background:linear-gradient(90deg,#7c3aed,#a78bfa);height:100%;width:${usedPct}%;border-radius:4px;transition:width 0.5s;"></div>
                            </div>
                        </div>
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                            <div style="background:#fefce8;border-radius:8px;padding:10px;">
                                <div style="font-size:14px;font-weight:600;">${(s.total_input_tokens || 0).toLocaleString()}</div>
                                <div style="font-size:11px;color:#92400e;">Input Tokens</div>
                            </div>
                            <div style="background:#eff6ff;border-radius:8px;padding:10px;">
                                <div style="font-size:14px;font-weight:600;">${(s.total_output_tokens || 0).toLocaleString()}</div>
                                <div style="font-size:11px;color:#1e40af;">Output Tokens</div>
                            </div>
                        </div>
                        ${data.current_plan ? '<div style="margin-top:12px;font-size:13px;color:#6b7280;">Plan: <strong>' + frappe.utils.escape_html(data.current_plan) + '</strong></div>' : ''}
                    </div>
                `;
                d.fields_dict.usage_html.$wrapper.html(html);
            } catch (e) {
                d.fields_dict.usage_html.$wrapper.html('<p class="text-muted">Failed to load usage data.</p>');
            }
        };

        loadUsage("month");
    }

    format_credits(n) {
        return Number(n).toLocaleString();
    }

    // ─── Voice Mode ─────────────────────────────────────────────────

    setup_voice_mode() {
        this.$voiceOverlay = this.wrapper.find(".niv-voice-overlay");
        this.$voiceOrb = this.$voiceOverlay.find(".voice-orb");
        this.$voiceStatus = this.$voiceOverlay.find(".voice-status-text");
        this.$voiceTranscript = this.$voiceOverlay.find(".voice-transcript");
        this.$voiceResponse = this.$voiceOverlay.find(".voice-response-text");

        this.voiceState = "idle"; // idle | listening | processing | speaking | error
        this.voiceAudioCtx = null;
        this.voiceAnalyser = null;
        this.voiceMediaRecorder = null;
        this.voiceAudioChunks = [];
        this.voiceStream = null;
        this.voiceAnimFrame = null;
        this.voiceSilenceTimer = null;
        this.voiceSilenceStart = null;
        this.voiceAudio = null;
        this.voicePlaybackSource = null;
        this.voiceContinuous = true;
        // Conversational mode: monitor mic during AI speech for auto-interrupt
        this.voiceMonitorStream = null;
        this.voiceMonitorAnalyser = null;
        this.voiceMonitorTimer = null;
        this.voiceSpeechDetectedAt = null;

        // Bind events
        this.wrapper.find(".btn-voice-mode").on("click", () => this.open_voice_mode());
        this.$voiceOverlay.find(".voice-close-btn").on("click", () => this.close_voice_mode());
        this.$voiceOrb.on("click", () => this.voice_orb_clicked());

        // ESC to close
        this.$voiceOverlay.on("keydown", (e) => {
            if (e.key === "Escape") this.close_voice_mode();
        });
    }

    async open_voice_mode() {
        if (!this.current_conversation) {
            await this.new_conversation();
        }
        this.$voiceOverlay.fadeIn(200);
        this.set_voice_state("idle");
        $("body").css("overflow", "hidden");
    }

    close_voice_mode() {
        this.stop_voice_recording();
        this.stop_voice_playback();
        this.stop_voice_monitor();
        this.cancel_voice_animation();
        if (this.voiceStream) {
            this.voiceStream.getTracks().forEach(t => t.stop());
            this.voiceStream = null;
        }
        if (this.voiceMonitorStream) {
            this.voiceMonitorStream.getTracks().forEach(t => t.stop());
            this.voiceMonitorStream = null;
        }
        if (this.voiceAudioCtx && this.voiceAudioCtx.state !== "closed") {
            this.voiceAudioCtx.close().catch(() => {});
            this.voiceAudioCtx = null;
            this.voiceAnalyser = null;
            this.voiceMonitorAnalyser = null;
        }
        this.$voiceOverlay.fadeOut(200);
        this.voiceState = "idle";
        $("body").css("overflow", "");
    }

    voice_orb_clicked() {
        if (this.voiceState === "idle") {
            this.start_voice_recording();
        } else if (this.voiceState === "listening") {
            this.stop_voice_recording();
        } else if (this.voiceState === "speaking") {
            // Interrupt AI speech → immediately start listening
            this.stop_voice_playback();
            this.start_voice_recording();
        }
    }

    set_voice_state(state, extra) {
        this.voiceState = state;
        this.$voiceOverlay.attr("data-voice-state", state);

        const statusMap = {
            idle: "Tap to speak",
            listening: "Listening...",
            processing: "Thinking...",
            speaking: "Speaking...",
            error: extra || "Something went wrong",
        };
        this.$voiceStatus.text(statusMap[state] || "");

        if (state === "idle") {
            this.$voiceTranscript.text("");
            this.$voiceResponse.text("");
        }
        if (state === "error") {
            setTimeout(() => {
                if (this.voiceState === "error") this.set_voice_state("idle");
            }, 3000);
        }
    }

    async start_voice_recording() {
        try {
            if (!this.voiceAudioCtx || this.voiceAudioCtx.state === "closed") {
                this.voiceAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (this.voiceAudioCtx.state === "suspended") {
                await this.voiceAudioCtx.resume();
            }

            this.voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // Setup analyser for visualization
            const source = this.voiceAudioCtx.createMediaStreamSource(this.voiceStream);
            this.voiceAnalyser = this.voiceAudioCtx.createAnalyser();
            this.voiceAnalyser.fftSize = 256;
            source.connect(this.voiceAnalyser);

            // Start MediaRecorder
            let mimeType = "audio/webm;codecs=opus";
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                mimeType = "audio/webm";
                if (!MediaRecorder.isTypeSupported(mimeType)) {
                    mimeType = "audio/mp4";
                }
            }
            this.voiceMediaRecorder = new MediaRecorder(this.voiceStream, { mimeType });
            this.voiceAudioChunks = [];

            this.voiceMediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.voiceAudioChunks.push(e.data);
            };
            this.voiceMediaRecorder.onstop = () => this.process_voice_recording();

            this.voiceMediaRecorder.start(250); // collect in 250ms chunks
            this.set_voice_state("listening");
            this.voice_visualize_input();
            this.voice_start_silence_detection();

            // Also start browser STT as fallback transcript
            this.voiceBrowserTranscript = "";
            const SpeechRecog = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (SpeechRecog) {
                this.voiceSpeechRecog = new SpeechRecog();
                this.voiceSpeechRecog.continuous = true;
                this.voiceSpeechRecog.interimResults = true;
                this.voiceSpeechRecog.lang = "en-IN";
                this.voiceSpeechRecog.onresult = (event) => {
                    let finalTranscript = "";
                    let interimTranscript = "";
                    for (let i = 0; i < event.results.length; i++) {
                        if (event.results[i].isFinal) {
                            finalTranscript += event.results[i][0].transcript;
                        } else {
                            interimTranscript += event.results[i][0].transcript;
                        }
                    }
                    // Store only final results for sending
                    this.voiceBrowserTranscript = finalTranscript.trim();
                    // Show both for live feedback (final + interim in gray)
                    this.$voiceTranscript.html(
                        finalTranscript + (interimTranscript ? '<span style="opacity:0.5">' + interimTranscript + '</span>' : '')
                    );
                };
                this.voiceSpeechRecog.onerror = () => {};
                this.voiceSpeechRecog.onend = () => {};
                try { this.voiceSpeechRecog.start(); } catch(e) {}
            }

        } catch (err) {
            console.error("Voice recording error:", err);
            if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
                this.set_voice_state("error", "Microphone access denied");
            } else {
                this.set_voice_state("error", "Could not start recording");
            }
        }
    }

    stop_voice_recording() {
        if (this.voiceSilenceTimer) {
            clearInterval(this.voiceSilenceTimer);
            this.voiceSilenceTimer = null;
        }
        this.cancel_voice_animation();
        if (this.voiceSpeechRecog) {
            try { this.voiceSpeechRecog.stop(); } catch(e) {}
            this.voiceSpeechRecog = null;
        }
        if (this.voiceMediaRecorder && this.voiceMediaRecorder.state !== "inactive") {
            this.voiceMediaRecorder.stop();
        }
        if (this.voiceStream) {
            this.voiceStream.getTracks().forEach(t => t.stop());
            this.voiceStream = null;
        }
    }

    voice_visualize_input() {
        if (!this.voiceAnalyser || this.voiceState !== "listening") return;
        const dataArray = new Uint8Array(this.voiceAnalyser.frequencyBinCount);

        const draw = () => {
            if (this.voiceState !== "listening") return;
            this.voiceAnimFrame = requestAnimationFrame(draw);
            this.voiceAnalyser.getByteFrequencyData(dataArray);
            const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
            const level = Math.min(avg / 80, 1); // normalize 0-1
            this.$voiceOrb.css("--voice-level", level);
        };
        draw();
    }

    voice_start_silence_detection() {
        this.voiceSilenceStart = null;
        const silenceThreshold = 10;
        const silenceDuration = 1500; // 1.5 seconds for faster turn-taking

        this.voiceSilenceTimer = setInterval(() => {
            if (this.voiceState !== "listening" || !this.voiceAnalyser) return;
            const dataArray = new Uint8Array(this.voiceAnalyser.frequencyBinCount);
            this.voiceAnalyser.getByteFrequencyData(dataArray);
            const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;

            if (avg < silenceThreshold) {
                if (!this.voiceSilenceStart) this.voiceSilenceStart = Date.now();
                if (Date.now() - this.voiceSilenceStart > silenceDuration) {
                    // Only auto-stop if we have some audio data
                    if (this.voiceAudioChunks.length > 0) {
                        this.stop_voice_recording();
                    }
                }
            } else {
                this.voiceSilenceStart = null;
            }
        }, 200);
    }

    cancel_voice_animation() {
        if (this.voiceAnimFrame) {
            cancelAnimationFrame(this.voiceAnimFrame);
            this.voiceAnimFrame = null;
        }
        this.$voiceOrb && this.$voiceOrb.css("--voice-level", 0);
    }

    async process_voice_recording() {
        if (this.voiceAudioChunks.length === 0 && !this.voiceBrowserTranscript) {
            this.set_voice_state("idle");
            return;
        }

        this.set_voice_state("processing");

        try {
            // Try server-side voice_chat first (OpenAI Whisper + TTS)
            let useServerAPI = true;
            let result = null;

            try {
                const blob = new Blob(this.voiceAudioChunks, { type: this.voiceAudioChunks[0]?.type || "audio/webm" });
                const formData = new FormData();
                formData.append("file", blob, "voice_input.webm");
                formData.append("is_private", "1");
                formData.append("folder", "Home/Niv AI");

                const uploadResp = await fetch("/api/method/upload_file", {
                    method: "POST",
                    body: formData,
                    headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
                });

                if (!uploadResp.ok) throw new Error("Upload failed");
                const uploadData = await uploadResp.json();
                const fileUrl = uploadData.message?.file_url;
                if (!fileUrl) throw new Error("No file URL");

                const r = await frappe.call({
                    method: "niv_ai.niv_core.api.voice.voice_chat",
                    args: { conversation_id: this.current_conversation, audio_file: fileUrl },
                });
                result = r.message;
                if (!result || !result.response) throw new Error("Empty response");
            } catch (serverErr) {
                console.warn("Server voice API unavailable, using browser fallback:", serverErr.message);
                useServerAPI = false;
            }

            // Fallback: Browser STT (already captured) + regular chat API + Browser TTS
            if (!useServerAPI) {
                const transcript = this.voiceBrowserTranscript || "";
                if (!transcript) {
                    // Use browser STT as one-shot
                    this.set_voice_state("error", "Could not transcribe. Try again.");
                    return;
                }

                this.$voiceTranscript.text(transcript);

                // Send to regular chat API
                if (!this.current_conversation) {
                    const conv = await this._create_conversation_on_server("Voice Chat");
                    this.current_conversation = conv.name;
                }
                const chatResp = await frappe.call({
                    method: "niv_ai.niv_core.api.chat.send_message",
                    args: {
                        conversation_id: this.current_conversation,
                        message: transcript,
                        attachments: "[]",
                    },
                });
                const chatData = chatResp.message;
                result = {
                    text: transcript,
                    response: chatData.message || chatData.content || "",
                    tokens: { total: chatData.total_tokens, input: chatData.input_tokens, output: chatData.output_tokens },
                    audio_url: null, // Will use browser TTS
                };
            }

            // Show transcript & response
            this.$voiceTranscript.text(result.text || "");
            this.$voiceResponse.text(result.response || "");

            // Append messages to chat UI
            if (result.text) this.append_message("user", result.text);
            if (result.response) {
                this.append_message("assistant", result.response, {
                    total_tokens: result.tokens?.total || 0,
                    input_tokens: result.tokens?.input || 0,
                    output_tokens: result.tokens?.output || 0,
                });
                this.update_last_assistant_actions();
            }
            this.scroll_to_bottom();
            this.load_balance();
            this.auto_title(result.text || "");

            // Play audio: server TTS (Piper) or browser TTS fallback
            if (result.audio_url) {
                this.play_voice_response(result.audio_url);
            } else if (result.response) {
                // Try Piper TTS first, then browser fallback
                this.play_voice_piper_or_browser(result.response);
            } else {
                this.set_voice_state("idle");
            }

        } catch (err) {
            console.error("Voice chat error:", err);
            this.set_voice_state("error", err.message || "Voice chat failed");
        }
    }

    _strip_markdown(text) {
        return this.cleanTextForTTS(text);
    }

    async play_voice_piper_or_browser(text) {
        const clean = this._strip_markdown(text);
        if (!clean) { this.set_voice_state("idle"); return; }

        this.set_voice_state("speaking");
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.voice.text_to_speech",
                args: { text: clean },
            });
            if (r.message && r.message.audio_url) {
                this.play_voice_response(r.message.audio_url);
                return;
            }
        } catch (e) {
            console.warn("Piper TTS failed in voice mode, using browser:", e);
        }
        this.play_voice_browser_tts(clean);
    }

    play_voice_browser_tts(text) {
        if (!("speechSynthesis" in window)) {
            this.set_voice_state("idle");
            return;
        }
        this.set_voice_state("speaking");
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "hi-IN";
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.onend = () => {
            if (this.voiceContinuous && this.voiceState === "speaking") {
                this.start_voice_recording();
            } else {
                this.set_voice_state("idle");
            }
        };
        utterance.onerror = () => this.set_voice_state("idle");
        window.speechSynthesis.speak(utterance);
        // Start monitoring mic for user interruption during browser TTS
        this.start_voice_monitor();
    }

    play_voice_response(audioUrl) {
        this.set_voice_state("speaking");

        this.voiceAudio = new Audio(audioUrl);

        // Try to connect to analyser for visualization
        try {
            if (!this.voiceAudioCtx || this.voiceAudioCtx.state === "closed") {
                this.voiceAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            this.voicePlaybackSource = this.voiceAudioCtx.createMediaElementSource(this.voiceAudio);
            this.voiceAnalyser = this.voiceAudioCtx.createAnalyser();
            this.voiceAnalyser.fftSize = 256;
            this.voicePlaybackSource.connect(this.voiceAnalyser);
            this.voiceAnalyser.connect(this.voiceAudioCtx.destination);
            this.voice_visualize_playback();
        } catch (e) {
            // Fallback: play without visualization
            console.warn("Could not setup audio visualization:", e);
        }

        this.voiceAudio.onended = () => {
            this.cancel_voice_animation();
            // Cleanup the TTS file
            frappe.call({
                method: "niv_ai.niv_core.api.voice.cleanup_voice_file",
                args: { file_url: audioUrl },
            }).catch(() => {});

            if (this.voiceContinuous && this.voiceState === "speaking") {
                // Auto-start next recording immediately
                if (this.$voiceOverlay.is(":visible")) {
                    this.start_voice_recording();
                }
            } else {
                this.set_voice_state("idle");
            }
        };

        this.voiceAudio.onerror = () => {
            this.set_voice_state("error", "Audio playback failed");
        };

        this.voiceAudio.play().then(() => {
            // Start monitoring mic for user interruption during playback
            this.start_voice_monitor();
        }).catch((e) => {
            console.error("Audio play error:", e);
            this.set_voice_state("error", "Could not play audio");
        });
    }

    voice_visualize_playback() {
        if (!this.voiceAnalyser || this.voiceState !== "speaking") return;
        const dataArray = new Uint8Array(this.voiceAnalyser.frequencyBinCount);

        const draw = () => {
            if (this.voiceState !== "speaking") return;
            this.voiceAnimFrame = requestAnimationFrame(draw);
            this.voiceAnalyser.getByteFrequencyData(dataArray);
            const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
            const level = Math.min(avg / 60, 1);
            this.$voiceOrb.css("--voice-level", level);
        };
        draw();
    }

    // ─── Voice Monitor: detect user speech during AI playback ──────
    async start_voice_monitor() {
        this.stop_voice_monitor();
        try {
            if (!this.voiceAudioCtx || this.voiceAudioCtx.state === "closed") {
                this.voiceAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (this.voiceAudioCtx.state === "suspended") {
                await this.voiceAudioCtx.resume();
            }
            this.voiceMonitorStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const src = this.voiceAudioCtx.createMediaStreamSource(this.voiceMonitorStream);
            this.voiceMonitorAnalyser = this.voiceAudioCtx.createAnalyser();
            this.voiceMonitorAnalyser.fftSize = 256;
            src.connect(this.voiceMonitorAnalyser);

            const speechThreshold = 25; // voice level to detect speech
            const speechConfirmMs = 350; // must speak for 350ms to trigger interrupt
            this.voiceSpeechDetectedAt = null;

            this.voiceMonitorTimer = setInterval(() => {
                if (this.voiceState !== "speaking") {
                    this.stop_voice_monitor();
                    return;
                }
                const data = new Uint8Array(this.voiceMonitorAnalyser.frequencyBinCount);
                this.voiceMonitorAnalyser.getByteFrequencyData(data);
                const avg = data.reduce((a, b) => a + b, 0) / data.length;

                if (avg >= speechThreshold) {
                    if (!this.voiceSpeechDetectedAt) this.voiceSpeechDetectedAt = Date.now();
                    if (Date.now() - this.voiceSpeechDetectedAt >= speechConfirmMs) {
                        // User is speaking — interrupt AI and start listening
                        console.log("Voice monitor: user speech detected, interrupting AI");
                        this.stop_voice_playback();
                        this.stop_voice_monitor();
                        this.start_voice_recording();
                    }
                } else {
                    this.voiceSpeechDetectedAt = null;
                }
            }, 100);
        } catch (e) {
            console.warn("Voice monitor failed:", e);
        }
    }

    stop_voice_monitor() {
        if (this.voiceMonitorTimer) {
            clearInterval(this.voiceMonitorTimer);
            this.voiceMonitorTimer = null;
        }
        if (this.voiceMonitorStream) {
            this.voiceMonitorStream.getTracks().forEach(t => t.stop());
            this.voiceMonitorStream = null;
        }
        this.voiceMonitorAnalyser = null;
        this.voiceSpeechDetectedAt = null;
    }

    stop_voice_playback() {
        this.stop_voice_monitor();
        if (this.voiceAudio) {
            this.voiceAudio.pause();
            this.voiceAudio.currentTime = 0;
            this.voiceAudio.onended = null;
            this.voiceAudio = null;
        }
        // Also stop browser speechSynthesis if playing
        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
        }
        this.cancel_voice_animation();
    }

    // ─── Dark Mode ────────────────────────────────────────────────

    setup_dark_mode() {
        this.$darkModeToggle = this.wrapper.find(".btn-dark-mode-toggle");

        // Auto-detect system preference or load saved
        const saved = localStorage.getItem("niv-dark-mode");
        if (saved === "true" || (saved === null && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
            this.enable_dark_mode(true);
        }

        this.$darkModeToggle.on("change", () => {
            this.enable_dark_mode(this.$darkModeToggle.is(":checked"));
        });

        // Listen for system theme changes
        window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
            if (localStorage.getItem("niv-dark-mode") === null) {
                this.enable_dark_mode(e.matches);
            }
        });
    }

    enable_dark_mode(on) {
        if (on) {
            document.body.classList.add("niv-dark-mode");
        } else {
            document.body.classList.remove("niv-dark-mode");
        }
        this.$darkModeToggle.prop("checked", on);
        localStorage.setItem("niv-dark-mode", on ? "true" : "false");
    }

    // ─── Emoji Picker ───────────────────────────────────────────────

    setup_emoji_picker() {
        this.$emojiBtn = this.wrapper.find(".btn-emoji-picker");
        this.$emojiPicker = this.wrapper.find(".niv-emoji-picker");
        this.$emojiMainGrid = this.$emojiPicker.find(".emoji-main-grid");
        this.$emojiRecentGrid = this.$emojiPicker.find(".emoji-recent-grid");

        this.emoji_data = {
            smileys: ["😀","😃","😄","😁","😆","😅","🤣","😂","🙂","😊","😇","🥰","😍","🤩","😘","😗","😋","😛","😜","🤪","😝","🤑","🤗","🤭","🤫","🤔","🫡","🤐","🤨","😐","😑","😶","😏","😒","🙄","😬","😮‍💨","🤥","😌","😔","😪","🤤","😴","😷","🤒","🤕","🤢","🤮","🥵","🥶","🥴","😵","🤯","🤠","🥳","🥸","😎","🤓","🧐","😕","🫤","😟","🙁","☹️","😮","😯","😲","😳","🥺","🥹","😦","😧","😨","😰","😥","😢","😭","😱","😖","😣","😞","😓","😩","😫","🥱"],
            hearts: ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔","❤️‍🔥","❤️‍🩹","❣️","💕","💞","💓","💗","💖","💘","💝","💟","♥️","😻","🫶","🥰","😍","😘","💋","💏","💑"],
            hands: ["👍","👎","👊","✊","🤛","🤜","👏","🙌","🫶","👐","🤲","🤝","🙏","✌️","🤞","🫰","🤟","🤘","🤙","👈","👉","👆","🖕","👇","☝️","🫵","👋","🤚","🖐️","✋","🖖","🫱","🫲","🫳","🫴","👌","🤌","🤏","✍️","💪","🦾"],
            objects: ["💡","🔥","⭐","✨","🎉","🎊","🎈","💯","✅","❌","⚡","💎","🏆","🎯","🚀","💰","📊","📈","📌","📎","🔗","💻","📱","⌨️","🖥️","🖨️","📸","🎵","🎶","🔔","📢","💬","🗯️","💭","🕐","📅","📝","📋","📁","🗂️","🔍","🔒","🔓","🔑","⚙️","🛠️","🧩","♻️"]
        };

        this.recent_emojis = JSON.parse(localStorage.getItem("niv-recent-emojis") || "[]");
        this.render_emoji_grid("smileys");
        this.render_recent_emojis();

        this.$emojiBtn.on("click", (e) => {
            e.stopPropagation();
            this.$emojiPicker.toggle();
        });

        this.$emojiPicker.on("click", (e) => e.stopPropagation());

        this.$emojiPicker.find(".emoji-tab").on("click", (e) => {
            const cat = $(e.currentTarget).data("category");
            this.$emojiPicker.find(".emoji-tab").removeClass("active");
            $(e.currentTarget).addClass("active");
            this.render_emoji_grid(cat);
        });

        $(document).on("click.nivemoji", () => this.$emojiPicker.hide());
    }

    render_emoji_grid(category) {
        const emojis = this.emoji_data[category] || [];
        this.$emojiMainGrid.empty();
        for (const em of emojis) {
            const $btn = $(`<button class="emoji-item">${em}</button>`);
            $btn.on("click", () => this.insert_emoji(em));
            this.$emojiMainGrid.append($btn);
        }
    }

    render_recent_emojis() {
        this.$emojiRecentGrid.empty();
        if (this.recent_emojis.length === 0) {
            this.$emojiPicker.find(".emoji-recent-section").hide();
            return;
        }
        this.$emojiPicker.find(".emoji-recent-section").show();
        for (const em of this.recent_emojis.slice(0, 16)) {
            const $btn = $(`<button class="emoji-item">${em}</button>`);
            $btn.on("click", () => this.insert_emoji(em));
            this.$emojiRecentGrid.append($btn);
        }
    }

    insert_emoji(emoji) {
        const textarea = this.$input[0];
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const text = textarea.value;
        textarea.value = text.substring(0, start) + emoji + text.substring(end);
        textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
        this.$input.trigger("input");
        textarea.focus();

        // Update recents
        this.recent_emojis = [emoji, ...this.recent_emojis.filter(e => e !== emoji)].slice(0, 24);
        localStorage.setItem("niv-recent-emojis", JSON.stringify(this.recent_emojis));
        this.render_recent_emojis();

        this.$emojiPicker.hide();
    }

    // ─── Drag & Drop ────────────────────────────────────────────────

    setup_drag_drop() {
        const $main = this.wrapper.find(".niv-main");
        const $overlay = this.wrapper.find(".niv-drag-overlay");
        let dragCounter = 0;

        $main.on("dragenter", (e) => {
            e.preventDefault();
            dragCounter++;
            $overlay.show();
        });

        $main.on("dragleave", (e) => {
            e.preventDefault();
            dragCounter--;
            if (dragCounter <= 0) {
                dragCounter = 0;
                $overlay.hide();
            }
        });

        $main.on("dragover", (e) => {
            e.preventDefault();
        });

        $main.on("drop", (e) => {
            e.preventDefault();
            dragCounter = 0;
            $overlay.hide();
            const files = e.originalEvent.dataTransfer.files;
            if (files && files.length > 0) {
                for (const file of files) {
                    if (file.size > 10 * 1024 * 1024) {
                        frappe.msgprint(__(`File "${file.name}" exceeds 10MB limit`));
                        continue;
                    }
                    this.upload_file(file);
                }
            }
        });
    }

    // ─── Message Reactions (emoji) ──────────────────────────────────

    render_reaction_bar($msg, msgIndex) {
        const quickEmojis = ["👍", "❤️", "😂", "🔥", "👏"];
        const $bar = $(`<div class="msg-reaction-bar"></div>`);
        for (const em of quickEmojis) {
            const $btn = $(`<button class="reaction-quick-btn">${em}</button>`);
            $btn.on("click", () => this.toggle_message_reaction(msgIndex, em));
            $bar.append($btn);
        }
        $msg.find(".msg-body").append($bar);
    }

    render_reactions($msg, reactions, msgIndex) {
        $msg.find(".msg-reactions").remove();
        if (!reactions || Object.keys(reactions).length === 0) return;

        const $container = $('<div class="msg-reactions"></div>');
        const currentUser = frappe.session.user;
        for (const [emoji, users] of Object.entries(reactions)) {
            const isMine = users.includes(currentUser);
            const $pill = $(`<span class="reaction-pill ${isMine ? 'mine' : ''}">${emoji} <span class="reaction-count">${users.length}</span></span>`);
            $pill.on("click", () => this.toggle_message_reaction(msgIndex, emoji));
            $container.append($pill);
        }
        $msg.find(".msg-footer").after($container);
    }

    async toggle_message_reaction(msgIndex, emoji) {
        const data = this.messages_data[msgIndex];
        if (!data || !data.meta || !data.meta.name) return;

        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.conversation.toggle_reaction",
                args: { message_id: data.meta.name, emoji },
            });
            const reactions = r.message.reactions;
            data.meta.reactions_json = JSON.stringify(reactions);
            this.render_reactions(data.$el, reactions, msgIndex);
        } catch (e) {
            // silently fail
        }
    }

    // ─── Slash Commands ─────────────────────────────────────────────

    setup_slash_commands() {
        this.$slashDropdown = this.wrapper.find(".niv-slash-commands");

        this.$input.on("input", () => {
            const val = this.$input.val();
            if (val.startsWith("/")) {
                this.show_slash_dropdown(val);
            } else {
                this.$slashDropdown.hide();
            }
        });

        this.$input.on("keydown", (e) => {
            if (!this.$slashDropdown.is(":visible")) return;
            const items = this.$slashDropdown.find(".slash-item");
            if (e.key === "ArrowDown") {
                e.preventDefault();
                this.slash_selected_index = Math.min(this.slash_selected_index + 1, items.length - 1);
                items.removeClass("selected");
                $(items[this.slash_selected_index]).addClass("selected");
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                this.slash_selected_index = Math.max(this.slash_selected_index - 1, 0);
                items.removeClass("selected");
                $(items[this.slash_selected_index]).addClass("selected");
            } else if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
                const $selected = items.filter(".selected");
                if ($selected.length) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    const cmd = $selected.data("cmd");
                    const hasArg = $selected.data("hasarg");
                    if (hasArg) {
                        this.$input.val(cmd + " ");
                        this.$slashDropdown.hide();
                    } else {
                        this.$input.val("");
                        this.$slashDropdown.hide();
                        this.execute_slash_command(cmd);
                    }
                }
            } else if (e.key === "Escape") {
                this.$slashDropdown.hide();
            }
        });
    }

    show_slash_dropdown(val) {
        const query = val.toLowerCase();
        const filtered = this.slash_commands.filter(c => c.cmd.startsWith(query));
        if (filtered.length === 0) {
            this.$slashDropdown.hide();
            return;
        }

        this.slash_selected_index = 0;
        let html = "";
        filtered.forEach((c, i) => {
            html += `<div class="slash-item ${i === 0 ? 'selected' : ''}" data-cmd="${c.cmd}" data-hasarg="${c.hasArg ? '1' : ''}">
                <span class="slash-icon">${c.icon}</span>
                <span class="slash-cmd">${c.cmd}</span>
                <span class="slash-desc">${c.desc}</span>
            </div>`;
        });
        this.$slashDropdown.html(html).show();

        this.$slashDropdown.find(".slash-item").on("click", (e) => {
            const $item = $(e.currentTarget);
            const cmd = $item.data("cmd");
            const hasArg = $item.data("hasarg");
            if (hasArg) {
                this.$input.val(cmd + " ");
                this.$input.focus();
                this.$slashDropdown.hide();
            } else {
                this.$input.val("");
                this.$slashDropdown.hide();
                this.execute_slash_command(cmd);
            }
        });
    }

    execute_slash_command(input) {
        const parts = input.trim().split(/\s+/);
        const cmd = parts[0];
        const arg = parts.slice(1).join(" ");

        switch (cmd) {
            case "/clear":
                frappe.confirm(__("Clear all messages in this chat?"), () => {
                    if (this.current_conversation) {
                        this.$chatArea.empty();
                        this.messages_data = [];
                        frappe.call({
                            method: "niv_ai.niv_core.api.conversation.delete_conversation",
                            args: { conversation_id: this.current_conversation },
                        }).then(() => {
                            this.current_conversation = null;
                            this.new_conversation();
                        });
                    }
                });
                break;
            case "/export":
                this.export_chat();
                break;
            case "/help":
                let helpText = "**Available Commands:**\n\n";
                for (const c of this.slash_commands) {
                    helpText += `- \`${c.cmd}\` — ${c.desc}\n`;
                }
                this.append_message("assistant", helpText);
                this.scroll_to_bottom();
                break;
            case "/model":
                if (arg) {
                    const m = this.models_list.find(m => m.name.toLowerCase().includes(arg.toLowerCase()));
                    if (m) {
                        this.selected_model = m.value;
                        this.$modelDropdown.val(m.value);
                        this.update_model_badge(m.name, m.provider);
                        this.render_model_popover();
                        frappe.show_alert({ message: `Model switched to ${m.name}`, indicator: "green" });
                    } else {
                        frappe.show_alert({ message: "Model not found", indicator: "orange" });
                    }
                }
                break;
            case "/system":
                if (arg && this.current_conversation) {
                    frappe.call({
                        method: "frappe.client.set_value",
                        args: { doctype: "Niv Conversation", name: this.current_conversation, fieldname: "system_prompt", value: arg },
                    }).then(() => {
                        frappe.show_alert({ message: "System prompt updated", indicator: "green" });
                    });
                }
                break;
            case "/summarize":
                this.$input.val("Please summarize our entire conversation so far.");
                this.send_message();
                break;
            case "/translate":
                if (arg) {
                    const lastAssistant = [...this.messages_data].reverse().find(m => m.role === "assistant");
                    if (lastAssistant) {
                        this.$input.val(`Translate the following to ${arg}:\n\n${lastAssistant.content}`);
                        this.send_message();
                    }
                }
                break;
            case "/new":
                this.new_conversation();
                break;
            case "/instructions":
                this.show_instructions_dialog();
                break;
        }
    }

    async show_instructions_dialog() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.instructions.get_instructions",
            });
            const instructions = r.message || [];

            const d = new frappe.ui.Dialog({
                title: __("Custom Instructions"),
                fields: [
                    {
                        fieldname: "instructions_html",
                        fieldtype: "HTML",
                        options: instructions.length
                            ? instructions.map(i => `<div style="padding:8px 12px;margin-bottom:8px;background:#f3f4f6;border-radius:8px;font-size:13px;">${frappe.utils.escape_html(i.instruction)}</div>`).join("")
                            : '<p class="text-muted">No custom instructions set.</p>',
                    },
                    { fieldtype: "Section Break", label: "Add New Instruction" },
                    { fieldname: "instruction", fieldtype: "Long Text", label: "Instruction" },
                    {
                        fieldname: "scope",
                        fieldtype: "Select",
                        label: "Scope",
                        options: "Per User\nGlobal",
                        default: "Per User",
                    },
                ],
                primary_action_label: __("Save"),
                primary_action: async (values) => {
                    if (!values.instruction) return;
                    await frappe.call({
                        method: "niv_ai.niv_core.api.instructions.save_instruction",
                        args: { instruction: values.instruction, scope: values.scope },
                    });
                    d.hide();
                    frappe.show_alert({ message: "Instruction saved!", indicator: "green" });
                },
            });
            d.show();
        } catch (e) {
            frappe.msgprint(__("Failed to load instructions."));
        }
    }

    // ─── Pin Messages ───────────────────────────────────────────────

    async toggle_pin(msgIndex) {
        const data = this.messages_data[msgIndex];
        if (!data || !data.meta.name) return;

        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.conversation.toggle_pin",
                args: { message_id: data.meta.name },
            });
            const isPinned = r.message.is_pinned;
            data.meta.is_pinned = isPinned;

            const $btn = data.$el.find(".btn-pin-msg");
            if (isPinned) {
                $btn.addClass("active");
                data.$el.addClass("pinned");
            } else {
                $btn.removeClass("active");
                data.$el.removeClass("pinned");
            }
            this.load_pinned_messages();
        } catch (e) {
            frappe.msgprint(__("Failed to pin message"));
        }
    }

    async load_pinned_messages() {
        if (!this.current_conversation) {
            this.$pinnedSection.hide();
            return;
        }
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.conversation.get_pinned_messages",
                args: { conversation_id: this.current_conversation },
            });
            const pinned = r.message || [];
            if (pinned.length === 0) {
                this.$pinnedSection.hide();
                return;
            }
            this.$pinnedList.empty();
            for (const msg of pinned) {
                const preview = (msg.content || "").substring(0, 100) + (msg.content.length > 100 ? "..." : "");
                const roleLabel = msg.role === "user" ? "You" : "Niv";
                this.$pinnedList.append(`
                    <div class="pinned-item" data-name="${msg.name}">
                        <span class="pinned-role">${roleLabel}:</span>
                        <span class="pinned-preview">${frappe.utils.escape_html(preview)}</span>
                    </div>
                `);
            }
            this.$pinnedSection.show();
        } catch (e) {
            this.$pinnedSection.hide();
        }
    }

    // ─── Share Conversation ─────────────────────────────────────────

    async share_conversation() {
        if (!this.current_conversation) return;
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_core.api.conversation.share_conversation",
                args: { conversation_id: this.current_conversation },
            });
            const url = window.location.origin + r.message.url;
            const d = new frappe.ui.Dialog({
                title: __("Share Chat"),
                fields: [
                    { fieldname: "share_url", fieldtype: "Data", label: "Shareable Link", read_only: 1, default: url },
                    { fieldname: "info", fieldtype: "HTML", options: '<p class="text-muted" style="font-size:12px;">Anyone with this link can view this conversation (read-only).</p>' },
                ],
                primary_action_label: __("Copy Link"),
                primary_action: () => {
                    navigator.clipboard.writeText(url).then(() => {
                        frappe.show_alert({ message: "Link copied!", indicator: "green" });
                        d.hide();
                    });
                },
            });
            d.show();
        } catch (e) {
            frappe.msgprint(__("Failed to share conversation"));
        }
    }

    // ─── AI Suggestions ─────────────────────────────────────────────

    render_suggestions(items, $afterMsg) {
        const $suggestions = $('<div class="niv-suggestions"></div>');
        for (const item of items) {
            const $pill = $(`<button class="niv-suggestion-pill">${frappe.utils.escape_html(item)}</button>`);
            $pill.on("click", () => {
                $suggestions.remove();
                this.$input.val(item);
                this.send_message();
            });
            $suggestions.append($pill);
        }
        $afterMsg.find(".msg-body").append($suggestions);
        this.scroll_to_bottom_if_near();
    }

    // ── Mobile Touch Interactions ──
    setup_mobile_touch() {
        if (!('ontouchstart' in window)) return;
        const isMobile = () => window.innerWidth <= 768;

        // -- Sidebar backdrop --
        this.$sidebarBackdrop = $('<div class="niv-sidebar-backdrop"></div>');
        this.wrapper.find('.niv-chat-container').append(this.$sidebarBackdrop);
        this.$sidebarBackdrop.on('click', () => this._closeMobileSidebar());

        // Observe sidebar open/close to toggle backdrop
        const sidebarEl = this.$sidebar[0];
        if (sidebarEl) {
            const obs = new MutationObserver(() => {
                if (!isMobile()) return;
                const isOpen = this.$sidebar.hasClass('open') ||
                    (!this.isWidgetMode && !this.$sidebar.hasClass('collapsed') && this.$sidebar.css('transform') === 'none');
                const widgetOpen = this.isWidgetMode && !this.$sidebar.hasClass('collapsed');
                this.$sidebarBackdrop.toggleClass('visible', isOpen || widgetOpen);
            });
            obs.observe(sidebarEl, { attributes: true, attributeFilter: ['class'] });
        }

        // -- Swipe to open/close sidebar --
        let touchStartX = 0, touchStartY = 0, touchStartTime = 0, swiping = false;
        const SWIPE_THRESHOLD = 50;
        const EDGE_ZONE = 30;

        this.wrapper[0].addEventListener('touchstart', (e) => {
            if (!isMobile()) return;
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchStartTime = Date.now();
            swiping = touchStartX < EDGE_ZONE || this.$sidebar.hasClass('open');
        }, { passive: true });

        this.wrapper[0].addEventListener('touchend', (e) => {
            if (!isMobile() || !swiping) return;
            const dx = e.changedTouches[0].clientX - touchStartX;
            const dy = Math.abs(e.changedTouches[0].clientY - touchStartY);
            const dt = Date.now() - touchStartTime;
            if (dt < 400 && dy < 100) {
                const sidebarOpen = this.$sidebar.hasClass('open') || (this.isWidgetMode && !this.$sidebar.hasClass('collapsed'));
                if (dx > SWIPE_THRESHOLD && touchStartX < EDGE_ZONE && !sidebarOpen) {
                    this._openMobileSidebar();
                } else if (dx < -SWIPE_THRESHOLD && sidebarOpen) {
                    this._closeMobileSidebar();
                }
            }
            swiping = false;
        }, { passive: true });

        // -- Long press on messages --
        let longPressTimer = null;
        let longPressTarget = null;

        this.$messages[0].addEventListener('touchstart', (e) => {
            const msgEl = e.target.closest('.niv-message');
            if (!msgEl || !isMobile()) return;
            longPressTarget = msgEl;
            longPressTimer = setTimeout(() => {
                e.preventDefault();
                this._showLongPressMenu(msgEl, e.touches[0].clientX, e.touches[0].clientY);
            }, 500);
        }, { passive: false });

        this.$messages[0].addEventListener('touchmove', () => {
            clearTimeout(longPressTimer);
        }, { passive: true });

        this.$messages[0].addEventListener('touchend', () => {
            clearTimeout(longPressTimer);
        }, { passive: true });

        // Close long-press menu on any tap
        $(document).on('touchstart.nivlongpress click.nivlongpress', (e) => {
            if (!$(e.target).closest('.niv-longpress-menu').length) {
                $('.niv-longpress-menu').remove();
            }
        });

        // -- Pull to load more (scroll to top) --
        let pulling = false;
        this.$messages[0].addEventListener('scroll', () => {
            if (!isMobile() || pulling) return;
            if (this.$messages[0].scrollTop <= 5 && this.conversations && this.current_conversation) {
                pulling = true;
                // Could load older messages here if pagination exists
                setTimeout(() => { pulling = false; }, 1000);
            }
        }, { passive: true });

        // -- Debounce resize --
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                if (!isMobile()) {
                    this.$sidebarBackdrop.removeClass('visible');
                    this.$sidebar.removeClass('open');
                }
            }, 150);
        });
    }

    _openMobileSidebar() {
        if (this.isWidgetMode) {
            this.$sidebar.removeClass('collapsed');
        } else {
            this.$sidebar.addClass('open');
        }
        this.$sidebarBackdrop.addClass('visible');
    }

    _closeMobileSidebar() {
        if (this.isWidgetMode) {
            this.$sidebar.addClass('collapsed');
        } else {
            this.$sidebar.removeClass('open');
        }
        this.$sidebarBackdrop.removeClass('visible');
    }

    _showLongPressMenu(msgEl, x, y) {
        $('.niv-longpress-menu').remove();
        const $msg = $(msgEl);
        const role = $msg.data('role');
        const items = [
            { icon: 'fa-copy', label: 'Copy text', action: 'copy' },
            { icon: 'fa-reply', label: 'Quote reply', action: 'quote' },
        ];
        if (role === 'assistant') {
            items.push({ icon: 'fa-refresh', label: 'Regenerate', action: 'regenerate' });
        }
        items.push({ icon: 'fa-thumb-tack', label: 'Pin message', action: 'pin' });

        const $menu = $('<div class="niv-longpress-menu"></div>');
        items.forEach(item => {
            $menu.append(`<div class="niv-longpress-menu-item" data-action="${item.action}">
                <i class="fa ${item.icon}"></i> ${item.label}
            </div>`);
        });

        // Position: ensure within viewport
        const menuW = 170, menuH = items.length * 44;
        const posX = Math.min(x, window.innerWidth - menuW - 8);
        const posY = Math.min(y, window.innerHeight - menuH - 8);
        $menu.css({ left: posX + 'px', top: posY + 'px' });
        $('body').append($menu);

        // Haptic feedback if available
        if (navigator.vibrate) navigator.vibrate(30);

        $menu.on('click', '.niv-longpress-menu-item', (e) => {
            const action = $(e.currentTarget).data('action');
            const text = $msg.find('.msg-content').text();
            switch (action) {
                case 'copy':
                    navigator.clipboard.writeText(text).then(() => frappe.show_alert('Copied!'));
                    break;
                case 'quote':
                    const quoted = text.split('\n').slice(0, 3).map(l => '> ' + l).join('\n') + '\n';
                    this.$input.val(quoted).focus();
                    this.auto_resize_input();
                    break;
                case 'regenerate':
                    $msg.find('.btn-regenerate').click();
                    break;
                case 'pin':
                    $msg.find('.btn-pin-msg').click();
                    break;
            }
            $menu.remove();
        });
    }

    destroy() {
        document.body.classList.remove("niv-chat-active");
        $("body > .niv-settings-panel, body > .niv-settings-overlay").remove();
        $(document).off("keydown.nivchat");
        $(document).off("click.nivmodel");
        $(document).off("click.nivemoji");
        $(document).off("touchstart.nivlongpress click.nivlongpress");
        if (this.recognition) this.recognition.stop();
        if (this.event_source) this.event_source.close();
        if (this.typing_timer) clearInterval(this.typing_timer);
        window.speechSynthesis && window.speechSynthesis.cancel();
        this.close_voice_mode();
    }
}
