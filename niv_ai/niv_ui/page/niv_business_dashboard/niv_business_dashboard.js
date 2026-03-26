frappe.pages["niv-business-dashboard"].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "AI Business Intelligence",
        single_column: true
    });
    new NivAIDashboard(page);
};

class NivAIDashboard {
    constructor(page) {
        this.page = page;
        this.period = "this_year";
        this.data = null;
        window._biDash = this;
        this.init();
    }

    async init(period) {
        this.period = period || this.period;
        this.page.main.html(this.loadingScreen());
        
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_ui.api.bi_dashboard.get_bi_data",
                args: { period: this.period }
            });
            
            const result = r.message;
            
            if (result.status === "ok" && result.data) {
                this.data = result.data;
                this.render();
            } else if (result.raw) {
                this.renderRaw(result.raw);
            } else {
                this.renderError("AI returned no data. Try again.");
            }
        } catch(e) {
            console.error(e);
            this.renderError("Failed to connect to AI. Check console.");
        }
    }

    loadingScreen() {
        return `
            <div class="ai-dash">
                <div class="ai-loading">
                    <div class="ai-loading-spinner">&#x2728;</div>
                    <div class="ai-loading-title">AI is analyzing your business</div>
                    <div class="ai-loading-sub">Querying database using MCP tools...</div>
                    <div class="ai-loading-steps">
                        <div class="ai-step active">&#x1F50D; Fetching financial data</div>
                        <div class="ai-step">&#x1F3E6; Analyzing loan portfolio</div>
                        <div class="ai-step">&#x1F4CA; Processing trends</div>
                        <div class="ai-step">&#x1F9E0; Generating predictions</div>
                    </div>
                    <div class="ai-loading-note">This may take 30-60 seconds</div>
                </div>
            </div>`;
    }

    fmt(n) {
        if (!n || n === 0) return "\u20B90";
        const abs = Math.abs(n);
        if (abs >= 10000000) return "\u20B9" + (n/10000000).toFixed(1) + " Cr";
        if (abs >= 100000) return "\u20B9" + (n/100000).toFixed(1) + " L";
        if (abs >= 1000) return "\u20B9" + (n/1000).toFixed(1) + "K";
        return "\u20B9" + Number(n).toLocaleString();
    }

    fmtN(n) {
        if (!n) return "0";
        if (n >= 10000000) return (n/10000000).toFixed(1) + " Cr";
        if (n >= 100000) return (n/100000).toFixed(1) + " L";
        if (n >= 1000) return (n/1000).toFixed(1) + "K";
        return Number(n).toLocaleString();
    }

    renderError(msg) {
        this.page.main.html(`
            <div class="ai-dash">
                <div class="ai-error">
                    <div class="ai-error-icon">&#x26A0;</div>
                    <div class="ai-error-msg">${msg}</div>
                    <button class="ai-retry-btn" onclick="window._biDash.init()">&#x21BB; Retry</button>
                </div>
            </div>`);
    }

    renderRaw(text) {
        this.page.main.html(`
            <div class="ai-dash">
                <div class="ai-header">
                    <div>
                        <h1 class="ai-title">&#x2728; AI Business Intelligence</h1>
                        <p class="ai-subtitle">Period: ${this.period.replace("_", " ")}</p>
                    </div>
                    <div class="ai-header-actions">
                        ${this.dateFilterHtml()}
                        <button class="ai-btn-refresh" onclick="window._biDash.init()">&#x21BB; Reload</button>
                    </div>
                </div>
                <div class="ai-raw-panel">
                    <div class="ai-raw-header">&#x2728; AI Analysis</div>
                    <div class="ai-raw-body">${(text || "").replace(/\n/g, "<br>")}</div>
                </div>
            </div>`);
    }

    dateFilterHtml() {
        const opts = [
            ["this_month", "This Month"], ["last_month", "Last Month"],
            ["this_quarter", "This Quarter"], ["last_quarter", "Last Quarter"],
            ["this_year", "This Year"], ["last_year", "Last Year"],
            ["all", "All Time"]
        ];
        return '<select class="ai-date-filter" onchange="window._biDash.init(this.value)">' +
            opts.map(([v, l]) => '<option value="' + v + '"' + (v === this.period ? ' selected' : '') + '>' + l + '</option>').join("") +
            '</select>';
    }

    renderSection(title, content, span2) {
        return '<div class="ai-card' + (span2 ? ' ai-span-2' : '') + '"><div class="ai-card-header"><h3>' + title + '</h3></div>' + content + '</div>';
    }

    render() {
        const d = this.data;
        let sections = '';

        // Financial Summary
        if (d.financial) {
            const f = d.financial;
            const income = f.total_income || f.income || f.income_month || 0;
            const expense = f.total_expense || f.expense || f.expense_month || 0;
            const profit = f.profit || f.net_profit || (income - expense);
            const margin = income > 0 ? ((profit / income) * 100).toFixed(1) : 0;
            
            sections += `
                <div class="ai-kpi-grid">
                    <div class="ai-kpi income"><div class="ai-kpi-label">Income</div><div class="ai-kpi-value">${this.fmt(income)}</div></div>
                    <div class="ai-kpi expense"><div class="ai-kpi-label">Expense</div><div class="ai-kpi-value">${this.fmt(expense)}</div></div>
                    <div class="ai-kpi profit"><div class="ai-kpi-label">Profit</div><div class="ai-kpi-value ${profit >= 0 ? 'green' : 'red'}">${this.fmt(profit)}</div></div>
                    <div class="ai-kpi margin"><div class="ai-kpi-label">Margin</div><div class="ai-kpi-value">${margin}%</div></div>
                </div>`;
        }

        // Loan Summary
        if (d.loan_summary) {
            const l = d.loan_summary;
            sections += this.renderSection("&#x1F3E6; Loan Portfolio", `
                <div class="ai-kpi-grid small">
                    <div class="ai-kpi"><div class="ai-kpi-label">Total Loans</div><div class="ai-kpi-value">${this.fmtN(l.total_loans || l.total || 0)}</div></div>
                    <div class="ai-kpi"><div class="ai-kpi-label">Sanctioned</div><div class="ai-kpi-value">${this.fmt(l.total_sanctioned || l.sanctioned || 0)}</div></div>
                    <div class="ai-kpi"><div class="ai-kpi-label">Disbursed</div><div class="ai-kpi-value green">${this.fmt(l.total_disbursed || l.disbursed || 0)}</div></div>
                    <div class="ai-kpi"><div class="ai-kpi-label">Collected</div><div class="ai-kpi-value blue">${this.fmt(l.total_collected || l.collected || 0)}</div></div>
                    <div class="ai-kpi"><div class="ai-kpi-label">Active</div><div class="ai-kpi-value">${this.fmtN(l.active_loans || l.active || 0)}</div></div>
                    <div class="ai-kpi"><div class="ai-kpi-label">Closure Req</div><div class="ai-kpi-value orange">${this.fmtN(l.closure_requested || l.closure || 0)}</div></div>
                </div>`, true);
        }

        // Loan Status
        if (d.loan_status && Array.isArray(d.loan_status)) {
            const items = d.loan_status.map(s => {
                const colors = {"Disbursed":"#10b981","Closed":"#6b7280","Loan Closure Requested":"#f59e0b","Partially Disbursed":"#3b82f6","Sanctioned":"#8b5cf6"};
                return '<div class="ai-status-row"><span class="ai-dot" style="background:' + (colors[s.status] || '#6b7280') + '"></span><span class="ai-status-name">' + s.status + '</span><span class="ai-status-count">' + this.fmtN(s.count) + '</span><span class="ai-status-amt">' + this.fmt(s.amount || s.total_amount || 0) + '</span></div>';
            }).join("");
            sections += this.renderSection("&#x1F4CA; Loan Status", '<div class="ai-status-list">' + items + '</div>');
        }

        // Disbursement Trend
        if (d.disbursement_trend && Array.isArray(d.disbursement_trend) && d.disbursement_trend.length) {
            const trend = d.disbursement_trend;
            const maxAmt = Math.max(...trend.map(t => t.amount || t.total || 0), 1);
            const w = 460, h = 130, padT = 15, padB = 35, padL = 10, padR = 10;
            const cw = w - padL - padR, ch = h - padT - padB;
            const step = cw / Math.max(trend.length - 1, 1);
            
            let points = trend.map((t, i) => {
                const x = padL + i * step;
                const y = padT + ch - ((t.amount || t.total || 0) / maxAmt) * ch;
                return {x, y, d: t};
            });
            const line = points.map((p, i) => (i ? 'L' : 'M') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
            const area = line + ' L' + points[points.length-1].x.toFixed(1) + ',' + (padT+ch) + ' L' + points[0].x.toFixed(1) + ',' + (padT+ch) + ' Z';
            const dots = points.map(p => '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="3" fill="#3b82f6" stroke="#fff" stroke-width="1.5"><title>' + (p.d.month || '') + ': ' + this.fmt(p.d.amount || p.d.total || 0) + '</title></circle>').join('');
            const labels = points.map((p, i) => (trend.length > 8 && i % 2 !== 0) ? '' : '<text x="' + p.x.toFixed(1) + '" y="' + (h-8) + '" text-anchor="middle" class="ai-chart-label">' + (p.d.month || '') + '</text>').join('');
            
            const svg = '<svg viewBox="0 0 ' + w + ' ' + h + '" class="ai-chart-svg"><defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#3b82f6" stop-opacity="0.25"/><stop offset="100%" stop-color="#3b82f6" stop-opacity="0.02"/></linearGradient></defs><path d="' + area + '" fill="url(#ag)"/><path d="' + line + '" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round"/>' + dots + labels + '</svg>';
            sections += this.renderSection("&#x1F4C8; Disbursement Trend", svg, true);
        }

        // Pending Approvals
        if (d.pending_approvals && Array.isArray(d.pending_approvals)) {
            const items = d.pending_approvals.map(a => '<div class="ai-appr-row"><span>' + (a.doctype || a.reference_doctype || '') + '</span><span class="ai-badge-warn">' + (a.count || a.cnt || 0) + '</span></div>').join("");
            sections += this.renderSection("&#x1F4CB; Pending Approvals", items || '<div class="ai-empty">None</div>');
        }

        // Team Activity
        if (d.team_activity && Array.isArray(d.team_activity)) {
            const items = d.team_activity.map((t, i) => {
                const colors = ["#3b82f6","#10b981","#f59e0b","#8b5cf6","#ef4444"];
                const name = (t.user || t.owner || "").split("@")[0] || "Unknown";
                return '<div class="ai-team-row"><div class="ai-avatar" style="background:' + colors[i%5] + '">' + name[0].toUpperCase() + '</div><div class="ai-team-info"><span class="ai-team-name">' + name + '</span><span class="ai-team-count">' + (t.actions || t.count || t.cnt || 0) + ' actions</span></div></div>';
            }).join("");
            sections += this.renderSection("&#x1F465; Team Activity", items || '<div class="ai-empty">No activity</div>');
        }

        // NPA Warning
        if (d.npa_warning && Array.isArray(d.npa_warning) && d.npa_warning.length) {
            const items = d.npa_warning.map(n => '<div class="ai-npa-row"><span class="ai-dot" style="background:#ef4444"></span><span class="ai-npa-name">' + (n.applicant || n.loan || n.name || '') + '</span><span class="ai-npa-amt">' + this.fmt(n.amount || n.loan_amount || 0) + '</span></div>').join("");
            sections += this.renderSection("&#x1F6A8; NPA Warning", items);
        }

        // Collection Today
        if (d.collection_today) {
            const c = d.collection_today;
            sections += this.renderSection("&#x1F4B5; Collections", `
                <div class="ai-kpi-grid small">
                    <div class="ai-kpi"><div class="ai-kpi-label">Today</div><div class="ai-kpi-value green">${this.fmt(c.today || c.today_collections || 0)}</div></div>
                    <div class="ai-kpi"><div class="ai-kpi-label">This Week</div><div class="ai-kpi-value blue">${this.fmt(c.this_week || c.week || 0)}</div></div>
                    <div class="ai-kpi"><div class="ai-kpi-label">Avg/Day</div><div class="ai-kpi-value">${this.fmt(c.avg_daily || c.average || 0)}</div></div>
                </div>`);
        }

        // Predictions / Insights
        if (d.predictions) {
            const p = d.predictions;
            let insightHtml = '';
            if (p.insights && Array.isArray(p.insights)) {
                insightHtml = p.insights.map(i => '<div class="ai-insight-item">&#x1F4A1; ' + i + '</div>').join("");
            } else if (p.trend_prediction || p.revenue_trend) {
                insightHtml = '<div class="ai-insight-item">&#x1F4C8; Revenue trend: ' + (p.trend_prediction || p.revenue_trend || 'stable') + '</div>';
            }
            if (typeof p === 'string') {
                insightHtml = '<div class="ai-insight-item">' + p + '</div>';
            }
            if (insightHtml) {
                sections += this.renderSection("&#x1F9E0; AI Predictions & Insights", '<div class="ai-insights">' + insightHtml + '</div>', true);
            }
        }

        // Render everything
        this.page.main.html(`
            <div class="ai-dash">
                <div class="ai-header">
                    <div>
                        <h1 class="ai-title">&#x2728; AI Business Intelligence</h1>
                        <p class="ai-subtitle">All data fetched by AI using MCP tools &middot; Period: ${this.period.replace("_", " ")}</p>
                    </div>
                    <div class="ai-header-actions">
                        ${this.dateFilterHtml()}
                        <button class="ai-btn-refresh" onclick="window._biDash.init()">&#x21BB; Reload</button>
                    </div>
                </div>
                ${sections}
                <div class="ai-footer">&#x2728; Powered by AI Agent &middot; Data fetched via MCP tools &middot; ${new Date().toLocaleTimeString()}</div>
            </div>`);
    }
}
