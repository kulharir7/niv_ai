frappe.pages["niv-dashboard"].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "AI Dashboard",
        single_column: true
    });
    new NivDashboard(page);
};

class NivDashboard {
    constructor(page) {
        this.page = page;
        this.data = {};
        this.init();
    }

    async init() {
        this.page.main.html(this.skeleton());
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_ui.api.dashboard.get_dashboard_data"
            });
            this.data = r.message || {};
            this.render();
        } catch(e) {
            this.page.main.html('<div style="padding:40px;text-align:center;color:#888">Failed to load dashboard</div>');
        }
    }

    skeleton() {
        return `<div class="niv-dash">
            <div class="nd-loading">
                <div class="nd-skel-grid">
                    ${[1,2,3,4].map(() => '<div class="nd-skel-card"><div class="nd-skel-shine"></div></div>').join("")}
                </div>
            </div>
        </div>`;
    }

    fmt(n) {
        if (!n) return "0";
        if (n >= 10000000) return (n/10000000).toFixed(1) + " Cr";
        if (n >= 100000) return (n/100000).toFixed(1) + " L";
        if (n >= 1000) return (n/1000).toFixed(1) + "K";
        return Number(n).toLocaleString();
    }

    render() {
        const o = this.data.system_overview || {};
        const u = this.data.user_stats || {};
        const ai = this.data.ai_health || {};
        const top = this.data.top_doctypes || [];
        const activity = this.data.recent_activity || [];
        const growth = this.data.growth_data || [];

        // Growth chart bars
        const maxG = Math.max(...growth.map(g => g.count), 1);
        const bars = growth.map(g => {
            const pct = Math.max(4, (g.count / maxG) * 100);
            return `<div class="nd-bar-col">
                <div class="nd-bar" style="height:${pct}%"></div>
                <div class="nd-bar-label">${g.day}</div>
            </div>`;
        }).join("");

        // Top doctypes rows
        const dtRows = top.map((dt, i) => {
            const barPct = top[0] ? Math.max(5, (dt.count / top[0].count) * 100) : 0;
            return `<div class="nd-dt-row">
                <span class="nd-dt-rank">${i+1}</span>
                <div class="nd-dt-info">
                    <div class="nd-dt-name">${dt.doctype}</div>
                    <div class="nd-dt-module">${dt.module}</div>
                </div>
                <div class="nd-dt-bar-wrap"><div class="nd-dt-bar" style="width:${barPct}%"></div></div>
                <span class="nd-dt-count">${this.fmt(dt.count)}</span>
                ${dt.today > 0 ? `<span class="nd-dt-today">+${dt.today}</span>` : ''}
            </div>`;
        }).join("");

        // Recent activity
        const actRows = activity.slice(0, 10).map(a => {
            const isCreate = a.action_type === "Created";
            return `<div class="nd-act-row">
                <span class="nd-act-dot ${isCreate ? 'green' : 'blue'}"></span>
                <div class="nd-act-info">
                    <span class="nd-act-type">${a.ref_doctype}</span>
                    <span class="nd-act-name">${(a.docname || "").substring(0, 30)}</span>
                </div>
                <span class="nd-act-user">${a.user_fullname || ""}</span>
                <span class="nd-act-time">${a.time_ago}</span>
            </div>`;
        }).join("");

        this.page.main.html(`
            <div class="niv-dash">
                <!-- Header -->
                <div class="nd-header">
                    <div>
                        <h1 class="nd-title">Dashboard</h1>
                        <p class="nd-subtitle">Real-time system intelligence powered by AI</p>
                    </div>
                    <button class="nd-btn-ai" onclick="this.disabled=true;this.textContent='Analyzing...';frappe.call({method:'niv_ai.niv_ui.api.dashboard.get_ai_summary',callback:r=>{const d=document.querySelector('.nd-ai-summary');if(d){d.style.display='block';d.querySelector('.nd-ai-text').textContent=r.message?.summary||'No summary';} this.disabled=false;this.innerHTML='✦ AI Summary';}})">
                        ✦ AI Summary
                    </button>
                </div>

                <!-- AI Summary (hidden by default) -->
                <div class="nd-ai-summary" style="display:none">
                    <div class="nd-ai-icon">✦</div>
                    <div class="nd-ai-text"></div>
                    <button class="nd-ai-close" onclick="this.parentElement.style.display='none'">✕</button>
                </div>

                <!-- Stat Cards -->
                <div class="nd-stats">
                    <div class="nd-stat-card">
                        <div class="nd-stat-icon" style="background:rgba(124,58,237,0.1);color:#7c3aed">📊</div>
                        <div class="nd-stat-info">
                            <div class="nd-stat-value">${this.fmt(o.total_documents)}</div>
                            <div class="nd-stat-label">Total Records</div>
                        </div>
                    </div>
                    <div class="nd-stat-card">
                        <div class="nd-stat-icon" style="background:rgba(16,185,129,0.1);color:#10b981">👥</div>
                        <div class="nd-stat-info">
                            <div class="nd-stat-value">${o.total_users}</div>
                            <div class="nd-stat-label">Active Users</div>
                        </div>
                    </div>
                    <div class="nd-stat-card">
                        <div class="nd-stat-icon" style="background:rgba(249,115,22,0.1);color:#f97316">⚡</div>
                        <div class="nd-stat-info">
                            <div class="nd-stat-value">${this.fmt(o.today_changes)}</div>
                            <div class="nd-stat-label">Changes Today</div>
                        </div>
                    </div>
                    <div class="nd-stat-card">
                        <div class="nd-stat-icon" style="background:rgba(59,130,246,0.1);color:#3b82f6">🤖</div>
                        <div class="nd-stat-info">
                            <div class="nd-stat-value">${this.fmt(ai.total_messages)}</div>
                            <div class="nd-stat-label">AI Messages</div>
                        </div>
                    </div>
                </div>

                <!-- Main Grid -->
                <div class="nd-grid">
                    <!-- Activity Chart -->
                    <div class="nd-card nd-chart-card">
                        <div class="nd-card-header">
                            <h3>Activity Trend</h3>
                            <span class="nd-badge">Last 7 days</span>
                        </div>
                        <div class="nd-chart-bars">${bars}</div>
                    </div>

                    <!-- AI System Health -->
                    <div class="nd-card nd-ai-card">
                        <div class="nd-card-header">
                            <h3>AI System</h3>
                            <span class="nd-status-dot green"></span>
                        </div>
                        <div class="nd-ai-stats">
                            <div class="nd-ai-stat">
                                <span class="nd-ai-stat-val">${this.fmt(ai.total_conversations)}</span>
                                <span class="nd-ai-stat-lbl">Conversations</span>
                            </div>
                            <div class="nd-ai-stat">
                                <span class="nd-ai-stat-val">${ai.active_providers}</span>
                                <span class="nd-ai-stat-lbl">Providers</span>
                            </div>
                            <div class="nd-ai-stat">
                                <span class="nd-ai-stat-val">${ai.total_tools}</span>
                                <span class="nd-ai-stat-lbl">MCP Tools</span>
                            </div>
                            <div class="nd-ai-stat">
                                <span class="nd-ai-stat-val">${u.today_messages}</span>
                                <span class="nd-ai-stat-lbl">Your Msgs Today</span>
                            </div>
                        </div>
                    </div>

                    <!-- Top DocTypes -->
                    <div class="nd-card nd-dt-card">
                        <div class="nd-card-header">
                            <h3>Top Document Types</h3>
                            <span class="nd-badge">${top.length} types</span>
                        </div>
                        <div class="nd-dt-list">${dtRows || '<div style="padding:20px;text-align:center;color:#666">No data found</div>'}</div>
                    </div>

                    <!-- Recent Activity -->
                    <div class="nd-card nd-act-card">
                        <div class="nd-card-header">
                            <h3>Recent Activity</h3>
                            <span class="nd-badge">Live</span>
                        </div>
                        <div class="nd-act-list">${actRows || '<div style="padding:20px;text-align:center;color:#666">No recent activity</div>'}</div>
                    </div>
                </div>
            </div>
        `);
    }
}
