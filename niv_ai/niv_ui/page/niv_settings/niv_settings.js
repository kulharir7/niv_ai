frappe.pages["niv-settings"].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Niv Settings",
		single_column: true
	});

	new NivSettings(page);
};

class NivSettings {
	constructor(page) {
		this.page = page;
		this.doc = null;
		this.dirty = false;
		this.activeTab = "general";
		this.providers = [];
		this.tabs = [
			{ id: "general", label: "General", icon: "\u2699\ufe0f" },
			{ id: "ai_config", label: "AI Config", icon: "\ud83e\udde0" },
			{ id: "capabilities", label: "Capabilities", icon: "\u26a1" },
			{ id: "billing", label: "Billing", icon: "\ud83d\udcb3" },
			{ id: "usage", label: "Usage", icon: "\ud83d\udcca" },
			{ id: "voice", label: "Voice", icon: "\ud83c\udf99\ufe0f" },
			{ id: "connectors", label: "Connectors", icon: "\ud83d\udd17" }
		];
		this.load();
	}

	async load() {
		try {
			var res = await frappe.call({ method: "frappe.client.get", args: { doctype: "Niv Settings" } });
			this.doc = res.message;
		} catch(e) {
			this.doc = {};
		}
		try {
			var pRes = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Niv AI Provider", fields: ["*"], limit_page_length: 50 } });
			this.providers = pRes.message || [];
		} catch(e) {
			this.providers = [];
		}
		try {
			var mcpRes = await frappe.call({ method: "frappe.client.get_list", args: { doctype: "Niv MCP Server", fields: ["*"], limit_page_length: 50 } });
			this.mcpServers = mcpRes.message || [];
		} catch(e) {
			this.mcpServers = [
				{ server_name: "Frappe Assistant Core", tool_count: 23, connection_type: "Direct", enabled: 1 },
				{ server_name: "niv_tools", tool_count: 6, connection_type: "Direct", enabled: 1 }
			];
		}
		if (this.mcpServers.length === 0) {
			this.mcpServers = [
				{ server_name: "Frappe Assistant Core", tool_count: 23, connection_type: "Direct", enabled: 1 },
				{ server_name: "niv_tools", tool_count: 6, connection_type: "Direct", enabled: 1 }
			];
		}
		this.render();
	}

	render() {
		var root = this.page.main.find("#niv-settings-root");
		if (!root.length) {
			root = $(this.page.main);
		}
		root.html(this.buildLayout());
		this.bindEvents();
	}

	buildLayout() {
		var sidebarItems = this.tabs.map(function(t) {
			var cls = t.id === this.activeTab ? "ns-nav-item active" : "ns-nav-item";
			return '<div class="' + cls + '" data-tab="' + t.id + '">' +
				'<span class="ns-nav-icon">' + t.icon + '</span>' +
				'<span>' + t.label + '</span></div>';
		}.bind(this)).join("");

		return '<div class="niv-settings">' +
			'<div class="ns-sidebar">' +
				'<div class="ns-sidebar-header">' +
					'<h2><span class="ns-logo">\u2728</span> Niv AI</h2>' +
					'<p>Settings &amp; Configuration</p>' +
				'</div>' +
				sidebarItems +
				'<div class="ns-sidebar-footer">' +
					'<div style="font-size:12px;color:#64748b;">v1.0 \u00b7 Niv AI</div>' +
				'</div>' +
			'</div>' +
			'<div class="ns-main">' +
				this.buildSection() +
			'</div>' +
			'<div class="ns-save-bar' + (this.dirty ? " visible" : "") + '">' +
				'<button class="ns-btn ns-btn-ghost" data-action="discard">Discard</button>' +
				'<button class="ns-btn ns-btn-primary" data-action="save">Save Changes</button>' +
			'</div>' +
		'</div>';
	}

	buildSection() {
		switch(this.activeTab) {
			case "general": return this.sectionGeneral();
			case "ai_config": return this.sectionAIConfig();
			case "capabilities": return this.sectionCapabilities();
			case "billing": return this.sectionBilling();
			case "usage": return this.sectionUsage();
			case "voice": return this.sectionVoice();
			case "connectors": return this.sectionConnectors();
			default: return "";
		}
	}

	val(field, fallback) {
		if (!this.doc) return fallback || "";
		var v = this.doc[field];
		return (v === undefined || v === null) ? (fallback || "") : v;
	}

	bool(field) {
		return this.doc ? (this.doc[field] ? true : false) : false;
	}

	fieldInput(field, label, type, placeholder) {
		type = type || "text";
		placeholder = placeholder || "";
		return '<div class="ns-field">' +
			'<label class="ns-label">' + label + '</label>' +
			'<input class="ns-input" type="' + type + '" data-field="' + field + '" value="' + this.escAttr(this.val(field)) + '" placeholder="' + placeholder + '">' +
		'</div>';
	}

	fieldTextarea(field, label, placeholder) {
		return '<div class="ns-field">' +
			'<label class="ns-label">' + label + '</label>' +
			'<textarea class="ns-textarea" data-field="' + field + '" placeholder="' + (placeholder || "") + '">' + this.escHtml(this.val(field)) + '</textarea>' +
		'</div>';
	}

	fieldSelect(field, label, options) {
		var current = this.val(field);
		var opts = options.map(function(o) {
			var v = typeof o === "string" ? o : o.value;
			var l = typeof o === "string" ? o : o.label;
			var sel = v === current ? " selected" : "";
			return '<option value="' + v + '"' + sel + '>' + l + '</option>';
		}).join("");
		return '<div class="ns-field">' +
			'<label class="ns-label">' + label + '</label>' +
			'<select class="ns-select" data-field="' + field + '">' + opts + '</select>' +
		'</div>';
	}

	toggleRow(field, label, desc) {
		var checked = this.bool(field) ? " checked" : "";
		return '<div class="ns-toggle-row">' +
			'<div class="ns-toggle-info">' +
				'<div class="ns-toggle-label">' + label + '</div>' +
				(desc ? '<p class="ns-toggle-desc">' + desc + '</p>' : '') +
			'</div>' +
			'<label class="ns-toggle">' +
				'<input type="checkbox" data-field="' + field + '"' + checked + '>' +
				'<span class="ns-toggle-slider"></span>' +
			'</label>' +
		'</div>';
	}

	sectionGeneral() {
		var colorVal = this.val("widget_color", "#7c3aed");
		return '<h1 class="ns-section-title">General</h1>' +
			'<p class="ns-section-desc">Configure the basic settings for your Niv AI assistant.</p>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Widget Settings</div>' +
				'<div class="ns-card-desc">Customize the chat widget appearance and behavior.</div>' +
				this.fieldInput("widget_title", "Widget Title", "text", "Niv AI Assistant") +
				'<div class="ns-input-row">' +
					this.fieldSelect("widget_position", "Widget Position", [
						{value: "Bottom Right", label: "Bottom Right"},
						{value: "Bottom Left", label: "Bottom Left"},
						{value: "Top Right", label: "Top Right"},
						{value: "Top Left", label: "Top Left"}
					]) +
					'<div class="ns-field">' +
						'<label class="ns-label">Widget Color</label>' +
						'<div class="ns-color-input">' +
							'<div class="ns-color-swatch"><input type="color" data-field="widget_color" value="' + colorVal + '"></div>' +
							'<input class="ns-input" type="text" data-field="widget_color" value="' + colorVal + '" style="flex:1">' +
						'</div>' +
					'</div>' +
				'</div>' +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Access Control</div>' +
				'<div class="ns-card-desc">Specify which roles can access the AI assistant.</div>' +
				this.fieldInput("allowed_roles", "Allowed Roles", "text", "System Manager, Administrator") +
			'</div>';
	}

	sectionAIConfig() {
		return '<h1 class="ns-section-title">AI Configuration</h1>' +
			'<p class="ns-section-desc">Configure the AI model, provider, and conversation behavior.</p>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Model Settings</div>' +
				'<div class="ns-card-desc">Choose your AI provider and model for generating responses.</div>' +
				'<div class="ns-input-row">' +
					this.fieldInput("default_provider", "Default Provider", "text", "e.g. OpenAI") +
					this.fieldInput("default_model", "Default Model", "text", "e.g. gpt-4") +
				'</div>' +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">System Prompt</div>' +
				'<div class="ns-card-desc">Define the base personality and instructions for the AI.</div>' +
				this.fieldTextarea("system_prompt", "System Prompt", "You are a helpful AI assistant...") +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Conversation Limits</div>' +
				'<div class="ns-card-desc">Control token usage and context window size.</div>' +
				'<div class="ns-input-row">' +
					this.fieldInput("max_tokens_per_message", "Max Tokens Per Message", "number", "4096") +
					this.fieldInput("max_messages_per_conversation", "Max Messages in Context", "number", "50") +
				'</div>' +
				this.fieldSelect("tool_priority", "Tool Priority", [
					{value: "MCP First", label: "MCP First"},
					{value: "Native First", label: "Native First"}
				]) +
			'</div>';
	}

	sectionCapabilities() {
		return '<h1 class="ns-section-title">Capabilities</h1>' +
			'<p class="ns-section-desc">Enable or disable AI features and integrations.</p>' +
			'<div class="ns-card">' +
				this.toggleRow("enable_tools", "Enable Tools", "Allow the AI to use configured tools and function calls to perform actions in your system.") +
				this.toggleRow("enable_knowledge_base", "Enable Knowledge Base / RAG", "Let the AI retrieve and reference documents from your knowledge base for more accurate answers.") +
				this.toggleRow("enable_widget", "Enable Widget", "Show the floating chat widget on your website for visitors and users.") +
				this.toggleRow("per_user_tool_permissions", "Per-User Tool Permissions", "Restrict tool access based on individual user roles and permissions instead of global settings.") +
			'</div>';
	}

	sectionBilling() {
		var balance = parseFloat(this.val("shared_pool_balance", 0)) || 0;
		var used = parseFloat(this.val("shared_pool_used", 0)) || 0;
		var pct = balance > 0 ? Math.min(100, (used / balance) * 100) : 0;

		return '<h1 class="ns-section-title">Billing</h1>' +
			'<p class="ns-section-desc">Manage billing, token budgets, and payment integrations.</p>' +
			'<div class="ns-card">' +
				this.toggleRow("enable_billing", "Enable Billing", "Track and charge for AI token usage.") +
				this.fieldSelect("billing_mode", "Billing Mode", [
					{value: "Shared Pool", label: "Shared Pool"},
					{value: "Per User", label: "Per User"}
				]) +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Token Budget</div>' +
				'<div class="ns-card-desc">Monitor shared pool usage and set limits.</div>' +
				'<div class="ns-input-row">' +
					this.fieldInput("shared_pool_balance", "Shared Pool Balance", "number", "100000") +
					this.fieldInput("shared_pool_used", "Shared Pool Used", "number", "0") +
				'</div>' +
				'<div class="ns-progress-wrap">' +
					'<div class="ns-progress-bar"><div class="ns-progress-fill" style="width:' + pct + '%"></div></div>' +
					'<div class="ns-progress-labels"><span>' + used.toLocaleString() + ' used</span><span>' + balance.toLocaleString() + ' total</span></div>' +
				'</div>' +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Limits &amp; Costs</div>' +
				'<div class="ns-input-row">' +
					this.fieldInput("per_user_daily_limit", "Per User Daily Limit", "number", "10000") +
					this.fieldInput("token_cost_input", "Cost per 1K Input Tokens", "number", "1") +
				'</div>' +
				'<div class="ns-input-row">' +
					this.fieldInput("token_cost_output", "Cost per 1K Output Tokens", "number", "3") +
				'</div>' +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Razorpay Integration</div>' +
				'<div class="ns-card-desc">Connect Razorpay for automated billing and payments.</div>' +
				this.fieldInput("razorpay_key_id", "Razorpay Key ID", "text", "rzp_...") +
				this.fieldInput("razorpay_key_secret", "Razorpay Key Secret", "password", "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022") +
			'</div>';
	}

	sectionUsage() {
		var inputTokens = parseFloat(this.val("total_input_tokens", 0)) || 0;
		var outputTokens = parseFloat(this.val("total_output_tokens", 0)) || 0;
		var totalTokens = inputTokens + outputTokens;
		var maxBar = Math.max(totalTokens, 1);

		return '<h1 class="ns-section-title">Usage</h1>' +
			'<p class="ns-section-desc">Monitor AI usage across your organization.</p>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Token Usage Overview</div>' +
				'<div class="ns-card-desc">Current period token consumption.</div>' +
				'<div class="ns-usage-item">' +
					'<div class="ns-usage-header"><span class="ns-usage-label">Input Tokens</span><span class="ns-usage-value">' + inputTokens.toLocaleString() + '</span></div>' +
					'<div class="ns-usage-bar"><div class="ns-usage-fill purple" style="width:' + (maxBar > 0 ? (inputTokens/maxBar*100) : 0) + '%"></div></div>' +
				'</div>' +
				'<div class="ns-usage-item">' +
					'<div class="ns-usage-header"><span class="ns-usage-label">Output Tokens</span><span class="ns-usage-value">' + outputTokens.toLocaleString() + '</span></div>' +
					'<div class="ns-usage-bar"><div class="ns-usage-fill blue" style="width:' + (maxBar > 0 ? (outputTokens/maxBar*100) : 0) + '%"></div></div>' +
				'</div>' +
				'<div class="ns-usage-item">' +
					'<div class="ns-usage-header"><span class="ns-usage-label">Total</span><span class="ns-usage-value">' + totalTokens.toLocaleString() + '</span></div>' +
					'<div class="ns-usage-bar"><div class="ns-usage-fill green" style="width:100%"></div></div>' +
				'</div>' +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Rate Limiting</div>' +
				'<div class="ns-card-desc">Protect against excessive usage.</div>' +
				'<div class="ns-input-row">' +
					this.fieldInput("rate_limit_per_hour", "Requests per Hour", "number", "60") +
					this.fieldInput("rate_limit_per_day", "Requests per Day", "number", "500") +
				'</div>' +
			'</div>';
	}

	sectionVoice() {
		return '<h1 class="ns-section-title">Voice</h1>' +
			'<p class="ns-section-desc">Configure speech-to-text and text-to-speech settings.</p>' +
			'<div class="ns-card">' +
				this.toggleRow("enable_voice", "Enable Voice", "Allow users to interact with the AI using voice input and output.") +
				this.toggleRow("auto_play_response", "Auto-play Responses", "Automatically play AI voice responses without requiring a click.") +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">Speech Engines</div>' +
				'<div class="ns-card-desc">Choose your preferred speech-to-text and text-to-speech providers.</div>' +
				'<div class="ns-input-row">' +
					this.fieldSelect("stt_engine", "STT Engine", [
						{value: "browser", label: "Browser Native"},
						{value: "whisper", label: "Whisper (OpenAI)"}
					]) +
					this.fieldSelect("tts_engine", "TTS Engine", [
						{value: "browser", label: "Browser Native"},
						{value: "openai", label: "OpenAI TTS"},
						{value: "elevenlabs", label: "ElevenLabs"}
					]) +
				'</div>' +
				'<div class="ns-input-row">' +
					this.fieldInput("tts_voice", "TTS Voice", "text", "alloy") +
					this.fieldSelect("tts_language", "Language", [
						{value: "en", label: "English"},
						{value: "hi", label: "Hindi"},
						{value: "es", label: "Spanish"},
						{value: "fr", label: "French"},
						{value: "de", label: "German"},
						{value: "ja", label: "Japanese"},
						{value: "zh", label: "Chinese"}
					]) +
				'</div>' +
			'</div>' +
			'<div class="ns-card">' +
				'<div class="ns-card-title">API Configuration</div>' +
				this.fieldInput("voice_api_key", "Voice API Key", "password", "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022") +
				this.fieldInput("voice_base_url", "Voice API URL", "text", "https://api.openai.com/v1") +
			'</div>';
	}

	sectionConnectors() {
		var mcpIcons = ["\ud83d\udd27", "\u2699\ufe0f", "\ud83d\udce6", "\ud83e\udde9", "\ud83d\ude80", "\ud83d\udd0c"];
		var mcpColors = ["#7c3aed", "#10b981", "#3b82f6", "#f59e0b", "#06b6d4", "#ef4444"];
		var totalTools = 0;

		var mcpCards = this.mcpServers.map(function(s, i) {
			var color = mcpColors[i % mcpColors.length];
			var icon = mcpIcons[i % mcpIcons.length];
			var name = s.server_name || s.name || "MCP Server";
			var toolCount = parseInt(s.tool_count || s.tools || 0);
			var connType = s.connection_type || s.type || "Direct";
			var isActive = s.enabled || s.status === "Active" || s.status === "active";
			var desc = s.description || s.desc || "";
			totalTools += toolCount;

			return '<div class="ns-mcp-card">' +
				'<div class="ns-mcp-top">' +
					'<div class="ns-mcp-icon" style="background:' + color + '15;color:' + color + ';border-color:' + color + '30">' + icon + '</div>' +
					'<div class="ns-mcp-status-wrap">' +
						'<span class="ns-mcp-dot ' + (isActive ? "green" : "red") + '"></span>' +
						'<span class="ns-mcp-status-text">' + (isActive ? "Connected" : "Disconnected") + '</span>' +
					'</div>' +
				'</div>' +
				'<div class="ns-mcp-name">' + name + '</div>' +
				(desc ? '<div class="ns-mcp-desc">' + desc + '</div>' : '') +
				'<div class="ns-mcp-footer">' +
					'<span class="ns-mcp-badge tools">\ud83d\udee0\ufe0f ' + toolCount + ' tools</span>' +
					'<span class="ns-mcp-badge type-' + connType.toLowerCase() + '">' + connType + '</span>' +
				'</div>' +
			'</div>';
		}).join("");

		var providerColors = ["#3b82f6", "#f59e0b", "#ef4444", "#06b6d4", "#7c3aed", "#10b981"];
		var defaultProvider = this.val("default_provider", "");
		var providerCards = "";

		if (this.providers.length > 0) {
			providerCards = this.providers.map(function(p, i) {
				var color = providerColors[i % providerColors.length];
				var initial = (p.provider_name || p.name || "?").charAt(0).toUpperCase();
				var isActive = p.enabled ? true : false;
				var isDefault = (p.provider_name === defaultProvider || p.name === defaultProvider);
				var model = p.default_model || p.model || "";
				var url = p.api_base_url || "";

				return '<div class="ns-prov-card">' +
					'<div class="ns-prov-left">' +
						'<div class="ns-prov-icon" style="background:linear-gradient(135deg,' + color + ',' + color + 'bb)">' + initial + '</div>' +
						'<div class="ns-prov-info">' +
							'<div class="ns-prov-name-row">' +
								'<span class="ns-prov-name">' + (p.provider_name || p.name) + '</span>' +
								(isDefault ? '<span class="ns-badge-default">DEFAULT</span>' : '') +
							'</div>' +
							(url ? '<div class="ns-prov-url">' + url + '</div>' : '') +
							(model ? '<div class="ns-prov-model">\ud83e\udde0 ' + model + '</div>' : '') +
						'</div>' +
					'</div>' +
					'<div class="ns-prov-right">' +
						'<span class="ns-prov-dot ' + (isActive ? "active" : "inactive") + '"></span>' +
						'<button class="ns-btn-config" onclick="frappe.set_route(\'niv-ai-provider\',\'' + p.name + '\')">' +
							(isActive ? "Configure" : "Connect") +
						'</button>' +
					'</div>' +
				'</div>';
			}).join("");
		} else {
			providerCards = '<div class="ns-empty">' +
				'<div class="ns-empty-icon">\ud83d\udd17</div>' +
				'<p>No providers configured yet.</p>' +
				'<p style="font-size:12px;margin-top:4px;color:#64748b">Add a provider to start using AI capabilities.</p>' +
				'<button class="ns-btn ns-btn-primary" style="margin-top:16px;font-size:13px" onclick="frappe.new_doc(\'Niv AI Provider\')">+ Add Provider</button>' +
			'</div>';
		}

		return '<h1 class="ns-section-title">Connectors</h1>' +
			'<p class="ns-section-desc">Manage MCP servers, AI providers, and integrations.</p>' +

			'<div class="ns-card">' +
				'<div class="ns-card-title-row">' +
					'<div>' +
						'<div class="ns-card-title">\ud83d\udd27 MCP Servers</div>' +
						'<div class="ns-card-desc">Model Context Protocol servers providing tools and capabilities to the AI.</div>' +
					'</div>' +
					'<span class="ns-header-count">' + this.mcpServers.length + ' server' + (this.mcpServers.length !== 1 ? "s" : "") + '</span>' +
				'</div>' +
				'<div class="ns-mcp-grid">' + mcpCards + '</div>' +
				'<div class="ns-mcp-summary">' +
					'<span>\u2728 <strong>' + totalTools + ' tools</strong> available across ' + this.mcpServers.length + ' server' + (this.mcpServers.length !== 1 ? "s" : "") + '</span>' +
				'</div>' +
			'</div>' +

			'<div class="ns-card">' +
				'<div class="ns-card-title-row">' +
					'<div>' +
						'<div class="ns-card-title">\ud83e\udd16 AI Providers</div>' +
						'<div class="ns-card-desc">Connected language model providers and their configuration.</div>' +
					'</div>' +
					'<span class="ns-header-count">' + this.providers.length + ' provider' + (this.providers.length !== 1 ? "s" : "") + '</span>' +
				'</div>' +
				providerCards +
			'</div>' +

			'<div class="ns-card">' +
				'<div class="ns-card-title">\ud83c\udfa8 Image Generation</div>' +
				'<div class="ns-card-desc">Configure AI image generation capabilities.</div>' +
				this.toggleRow("enable_image_generation", "Enable Image Generation", "Allow users to generate images using AI models.") +
				this.fieldSelect("image_model", "Image Model", [
					{value: "", label: "Select..."},
					{value: "dall-e-3", label: "DALL-E 3"},
					{value: "dall-e-2", label: "DALL-E 2"},
					{value: "stable-diffusion-xl", label: "Stable Diffusion XL"},
					{value: "midjourney", label: "Midjourney"}
				]) +
				this.fieldInput("image_size", "Default Image Size", "text", "1024x1024") +
			'</div>';
	}

	escAttr(str) {
		return String(str).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
	}

	escHtml(str) {
		return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
	}

	bindEvents() {
		var self = this;
		var $root = $(this.page.main);

		$root.off(".nivsettings");

		$root.on("click.nivsettings", ".ns-nav-item", function() {
			self.activeTab = $(this).data("tab");
			self.render();
		});

		$root.on("input.nivsettings change.nivsettings", ".ns-input, .ns-select, .ns-textarea, input[type=color]", function() {
			var field = $(this).data("field");
			if (field && self.doc) {
				self.doc[field] = $(this).val();
				self.markDirty();
				if (field === "widget_color") {
					$root.find("[data-field=widget_color]").not(this).val($(this).val());
				}
			}
		});

		$root.on("change.nivsettings", ".ns-toggle input[type=checkbox]", function() {
			var field = $(this).data("field");
			if (field && self.doc) {
				self.doc[field] = $(this).is(":checked") ? 1 : 0;
				self.markDirty();
			}
		});

		$root.on("click.nivsettings", "[data-action=save]", function() {
			self.save();
		});

		$root.on("click.nivsettings", "[data-action=discard]", function() {
			self.dirty = false;
			self.load();
		});
	}

	markDirty() {
		this.dirty = true;
		$(this.page.main).find(".ns-save-bar").addClass("visible");
	}

	async save() {
		var btn = $(this.page.main).find("[data-action=save]");
		btn.prop("disabled", true).text("Saving...");
		try {
			this.doc.doctype = "Niv Settings";
			await frappe.call({ method: "frappe.client.save", args: { doc: this.doc } });
			this.dirty = false;
			$(this.page.main).find(".ns-save-bar").removeClass("visible");
			frappe.show_alert({ message: "Settings saved successfully!", indicator: "green" }, 3);
		} catch(e) {
			frappe.show_alert({ message: "Failed to save settings.", indicator: "red" }, 5);
		}
		btn.prop("disabled", false).text("Save Changes");
	}
}
