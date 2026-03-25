frappe.pages["niv-ai-dashboard"].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "AI Business Intelligence",
        single_column: true
    });
    new NivBIDashboard(page);
};

class NivBIDashboard {
    constructor(page) {
        this.page = page;
        this.data = {};
        this.init();
    }

    async init() {
        this.page.main.html(this.skeleton());
        try {
            const r = await frappe.call({ method: "niv_ai.niv_ui.api.bi_dashboard.get_bi_data" });
            this.data = r.message || {};
            this.render();
        } catch(e) {
            this.page.main.html('<div style="padding:60px;text-align:center;color:#888">Failed to load dashboard. Check console.</div>');
            console.error(e);
        }
    }

    skeleton() {
        const cards = [1,2,3,4,5,6].map(() => '<div class="bi-skel-card"><div class="bi-skel-shine"></div></div>').join("");
        return `<div class="bi-dash"><div class="bi-skel-grid">${cards}</div></div>`;
    }

    fmt(n) {
        if (!n || n === 0) return "₹0";
        const abs = Math.abs(n);
        let str;
        if (abs >= 10000000) str = "₹" + (n/10000000).toFixed(1) + " Cr";
        else if (abs >= 100000) str = "₹" + (n/100000).toFixed(1) + " L";
        else if (abs >= 1000) str = "₹" + (n/1000).toFixed(1) + "K";
        else str = "₹" + Number(n).toLocaleString();
        return str;
    }

    fmtN(n) {
        if (!n) return "0";
        if (n >= 10000000) return (n/10000000).toFixed(1) + " Cr";
        if (n >= 100000) return (n/100000).toFixed(1) + " L";
        if (n >= 1000) return (n/1000).toFixed(1) + "K";
        return Number(n).toLocaleString();
    }

    render() {
        const fin = this.data.financial || {};
        const trend = this.data.trend || [];
        const top = this.data.top_doctypes || [];
        const risk = this.data.risk || [];
        const cust = this.data.customers || [];
        const recent = this.data.recent || [];
        const statuses = this.data.status_breakdown || [];
        const info = this.data.system_info || {};

        // Trend chart
        const maxTrend = Math.max(...trend.map(t => Math.max(t.income, t.expense)), 1);
        const trendBars = trend.map(t => {
            const incH = Math.max(4, (t.income / maxTrend) * 120);
            const expH = Math.max(4, (t.expense / maxTrend) * 120);
            return `<div class="bi-trend-col">
                <div class="bi-trend-bars">
                    <div class="bi-trend-bar income" style="height:${incH}px" title="Income: ${this.fmt(t.income)}"></div>
                    <div class="bi-trend-bar expense" style="height:${expH}px" title="Expense: ${this.fmt(t.expense)}"></div>
                </div>
                <div class="bi-trend-label">${t.month}</div>
            </div>`;
        }).join("");

        // Risk cards
        const riskCards = risk.slice(0, 6).map(r => {
            const sev = {"high": "🔴", "medium": "🟡", "low": "🟢"}[r.severity] || "⚪";
            const typeLabel = r.type === "overdue" ? "Overdue" : r.status || "Pending";
            return `<div class="bi-risk-item ${r.severity}">
                <span class="bi-risk-sev">${sev}</span>
                <div class="bi-risk-info">
                    <div class="bi-risk-dt">${r.doctype}</div>
                    <div class="bi-risk-detail">${r.count} ${typeLabel}${r.amount > 0 ? ' · ' + this.fmt(r.amount) : ''}</div>
                </div>
            </div>`;
        }).join("") || '<div class="bi-empty">No risks detected ✅</div>';

        // Top doctypes
        const dtRows = top.map((dt, i) => {
            const barPct = top[0] ? Math.max(5, (dt.count / top[0].count) * 100) : 0;
            const catIcon = {"income": "💰", "expense": "💸", "customer": "👤", "other": "📄"}[dt.category] || "📄";
            return `<div class="bi-dt-row">
                <span class="bi-dt-rank">${i+1}</span>
                <span class="bi-dt-icon">${catIcon}</span>
                <div class="bi-dt-info">
                    <div class="bi-dt-name">${dt.doctype}</div>
                    <div class="bi-dt-module">${dt.module}</div>
                </div>
                <div class="bi-dt-bar-wrap"><div class="bi-dt-bar" style="width:${barPct}%"></div></div>
                <span class="bi-dt-count">${this.fmtN(dt.count)}</span>
                ${dt.today > 0 ? `<span class="bi-dt-today">+${dt.today}</span>` : ''}
            </div>`;
        }).join("");

        // Recent high value
        const recentRows = recent.slice(0, 6).map(r => {
            const catCls = r.category === "income" ? "green" : "red";
            return `<div class="bi-recent-row">
                <span class="bi-recent-dot ${catCls}"></span>
                <div class="bi-recent-info">
                    <span class="bi-recent-dt">${r.doctype}</span>
                    <span class="bi-recent-name">${(r.name || "").substring(0, 25)}</span>
                </div>
                <span class="bi-recent-amt ${catCls}">${this.fmt(r.amount)}</span>
                <span class="bi-recent-time">${r.time_ago}</span>
            </div>`;
        }).join("") || '<div class="bi-empty">No transactions found</div>';

        // Customer insights
        const custCards = cust.map(c => `
            <div class="bi-cust-card">
                <div class="bi-cust-name">${c.doctype}</div>
                <div class="bi-cust-total">${this.fmtN(c.total)}</div>
                <div class="bi-cust-meta">
                    +${c.new_this_month} this month
                    <span class="bi-cust-growth ${c.growth_pct > 0 ? 'up' : 'down'}">${c.growth_pct > 0 ? '↑' : '↓'}${Math.abs(c.growth_pct)}%</span>
                </div>
            </div>
        `).join("") || '<div class="bi-empty">No customer data detected</div>';

        // Status breakdowns
        const statusCards = statuses.slice(0, 3).map(sb => {
            const total = sb.statuses.reduce((s, x) => s + x.count, 0);
            const bars = sb.statuses.map(s => {
                const pct = (s.count / total * 100).toFixed(0);
                return `<div class="bi-sb-row">
                    <span class="bi-sb-status">${s.status}</span>
                    <div class="bi-sb-bar-wrap"><div class="bi-sb-bar" style="width:${pct}%"></div></div>
                    <span class="bi-sb-pct">${pct}%</span>
                </div>`;
            }).join("");
            return `<div class="bi-sb-card">
                <div class="bi-sb-title">${sb.doctype}</div>
                ${bars}
            </div>`;
        }).join("");

        const marginCls = fin.margin_pct >= 20 ? "green" : fin.margin_pct >= 0 ? "yellow" : "red";

        this.page.main.html(`
            <div class="bi-dash">
                <!-- Header -->
                <div class="bi-header">
                    <div>
                        <h1 class="bi-title">Business Intelligence</h1>
                        <p class="bi-subtitle">${info.total_documents ? this.fmtN(info.total_documents) + ' records across ' + info.total_doctypes + ' types · ' + info.total_users + ' users' : 'Loading...'}</p>
                    </div>
                    <div class="bi-header-actions">
                        <button class="bi-btn-refresh" onclick="new NivBIDashboard(cur_page.page)">↻ Refresh</button>
                        <button class="bi-btn-ai" id="biAiBtn">✦ AI Analysis</button>
                    </div>
                </div>

                <!-- AI Analysis (hidden) -->
                <div class="bi-ai-panel" id="biAiPanel" style="display:none">
                    <div class="bi-ai-header">
                        <span class="bi-ai-icon">✦</span>
                        <span>AI Business Analysis</span>
                        <button class="bi-ai-close" onclick="document.getElementById('biAiPanel').style.display='none'">✕</button>
                    </div>
                    <div class="bi-ai-content" id="biAiContent">Analyzing...</div>
                </div>

                <!-- Financial Cards Row -->
                <div class="bi-fin-grid">
                    <div class="bi-fin-card income">
                        <div class="bi-fin-label">Income (Month)</div>
                        <div class="bi-fin-value">${this.fmt(fin.income_month)}</div>
                        <div class="bi-fin-sub">Year: ${this.fmt(fin.income_year)}</div>
                    </div>
                    <div class="bi-fin-card expense">
                        <div class="bi-fin-label">Expense (Month)</div>
                        <div class="bi-fin-value">${this.fmt(fin.expense_month)}</div>
                        <div class="bi-fin-sub">Year: ${this.fmt(fin.expense_year)}</div>
                    </div>
                    <div class="bi-fin-card profit">
                        <div class="bi-fin-label">Net Profit (Month)</div>
                        <div class="bi-fin-value ${fin.profit_month >= 0 ? 'green' : 'red'}">${this.fmt(fin.profit_month)}</div>
                        <div class="bi-fin-sub">Margin: <span class="${marginCls}">${fin.margin_pct}%</span></div>
                    </div>
                    <div class="bi-fin-card year-profit">
                        <div class="bi-fin-label">Year Profit</div>
                        <div class="bi-fin-value ${fin.profit_year >= 0 ? 'green' : 'red'}">${this.fmt(fin.profit_year)}</div>
                        <div class="bi-fin-sub">${info.installed_apps ? info.installed_apps.length + ' apps' : ''}</div>
                    </div>
                </div>

                <!-- Main Grid -->
                <div class="bi-grid">
                    <!-- Trend Chart -->
                    <div class="bi-card bi-span-2">
                        <div class="bi-card-header">
                            <h3>📈 Revenue vs Expense Trend</h3>
                            <div class="bi-legend">
                                <span class="bi-leg income">● Income</span>
                                <span class="bi-leg expense">● Expense</span>
                            </div>
                        </div>
                        <div class="bi-trend-chart">${trendBars || '<div class="bi-empty">No trend data</div>'}</div>
                    </div>

                    <!-- Risk Analysis -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>⚠️ Risk & Alerts</h3></div>
                        <div class="bi-risk-list">${riskCards}</div>
                    </div>

                    <!-- Top DocTypes -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>🏆 Top Document Types</h3></div>
                        <div class="bi-dt-list">${dtRows}</div>
                    </div>

                    <!-- Recent Transactions -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>💰 Recent High-Value</h3></div>
                        <div class="bi-recent-list">${recentRows}</div>
                    </div>

                    <!-- Customer Insights -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>👥 Customer Intelligence</h3></div>
                        <div class="bi-cust-grid">${custCards}</div>
                    </div>

                    <!-- Status Breakdown -->
                    <div class="bi-card bi-span-2">
                        <div class="bi-card-header"><h3>📊 Status Distribution</h3></div>
                        <div class="bi-sb-grid">${statusCards || '<div class="bi-empty">No status data</div>'}</div>
                    </div>
                </div>

                <div class="bi-footer">
                    Auto-discovered ${info.total_doctypes || 0} document types · ${info.income_doctypes || 0} income · ${info.expense_doctypes || 0} expense · ${info.customer_doctypes || 0} customer · Updated ${new Date().toLocaleTimeString()}
                </div>
            </div>
        `);

        // AI Analysis button
        document.getElementById("biAiBtn").addEventListener("click", async () => {
            const panel = document.getElementById("biAiPanel");
            const content = document.getElementById("biAiContent");
            panel.style.display = "block";
            content.innerHTML = '<div class="bi-ai-loading">✦ Analyzing your business data...</div>';
            try {
                const r = await frappe.call({ method: "niv_ai.niv_ui.api.bi_dashboard.get_ai_analysis" });
                content.innerHTML = '<div class="bi-ai-text">' + (r.message?.analysis || "No analysis available").replace(/\n/g, "<br>") + '</div>';
            } catch(e) {
                content.innerHTML = '<div class="bi-ai-error">Analysis failed. Try again.</div>';
            }
        });

        // Auto-refresh every 5 minutes
        if (this._refreshTimer) clearInterval(this._refreshTimer);
        this._refreshTimer = setInterval(() => this.init(), 300000);
    }
}
