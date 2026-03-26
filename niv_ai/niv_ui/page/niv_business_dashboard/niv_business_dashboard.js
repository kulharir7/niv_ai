frappe.pages["niv-business-dashboard"].on_page_load = function(wrapper) {
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


        // Loan Portfolio
        const loan = this.data.loan_portfolio || {};
        const loanSum = loan.summary || {};
        const loanStatuses = loan.status_breakdown || [];
        const loanTrend = loan.disbursement_trend || [];
        
        const loanStatusCards = loanStatuses.map(s => {
            const colors = {"Disbursed":"#10b981","Closed":"#6b7280","Loan Closure Requested":"#f59e0b","Partially Disbursed":"#3b82f6","Sanctioned":"#8b5cf6","Cancel":"#ef4444","Terminated":"#ef4444"};
            const color = colors[s.status] || "#6b7280";
            return '<div class="bi-loan-status-item"><span class="bi-loan-dot" style="background:' + color + '"></span><div class="bi-loan-status-info"><span class="bi-loan-status-name">' + s.status + '</span><span class="bi-loan-status-count">' + s.count + ' loans · ' + this.fmt(s.amount) + '</span></div></div>';
        }).join("");
        
        // Build SVG area chart for disbursement
        const maxDisb = Math.max(...loanTrend.map(t => t.amount), 1);
        const disbChartHtml = (() => {
            if (!loanTrend.length) return '<div class="bi-empty">No disbursement data</div>';
            const w = 460, h = 140, padL = 10, padR = 10, padT = 20, padB = 40;
            const cw = w - padL - padR, ch = h - padT - padB;
            const step = cw / Math.max(loanTrend.length - 1, 1);
            
            let points = loanTrend.map((t, i) => {
                const x = padL + i * step;
                const y = padT + ch - (t.amount / maxDisb) * ch;
                return {x, y, data: t};
            });
            
            const linePath = points.map((p, i) => (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
            const areaPath = linePath + ' L' + points[points.length-1].x.toFixed(1) + ',' + (padT+ch) + ' L' + points[0].x.toFixed(1) + ',' + (padT+ch) + ' Z';
            
            const dots = points.map((p, i) => {
                return '<circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="3.5" fill="#3b82f6" stroke="#fff" stroke-width="1.5" class="bi-svg-dot"><title>' + p.data.count + ' disbursements\n' + this.fmt(p.data.amount) + '</title></circle>';
            }).join('');
            
            const labels = points.map((p, i) => {
                if (loanTrend.length > 8 && i % 2 !== 0 && i !== loanTrend.length - 1) return '';
                return '<text x="' + p.x.toFixed(1) + '" y="' + (h - 18) + '" text-anchor="middle" class="bi-svg-label">' + p.data.month + '</text>' +
                       '<text x="' + p.x.toFixed(1) + '" y="' + (h - 6) + '" text-anchor="middle" class="bi-svg-amt">' + this.fmt(p.data.amount) + '</text>';
            }).join('');
            
            // Grid lines
            const gridLines = [0.25, 0.5, 0.75].map(pct => {
                const gy = padT + ch - pct * ch;
                return '<line x1="' + padL + '" y1="' + gy.toFixed(1) + '" x2="' + (w-padR) + '" y2="' + gy.toFixed(1) + '" stroke="#e5e7eb" stroke-width="0.5" stroke-dasharray="3,3"/>';
            }).join('');
            
            return '<svg viewBox="0 0 ' + w + ' ' + h + '" class="bi-svg-chart">' +
                '<defs><linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#3b82f6" stop-opacity="0.3"/><stop offset="100%" stop-color="#3b82f6" stop-opacity="0.02"/></linearGradient></defs>' +
                gridLines +
                '<path d="' + areaPath + '" fill="url(#areaGrad)"/>' +
                '<path d="' + linePath + '" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>' +
                dots + labels +
                '</svg>';
        })();
        // TAT + Pipeline
        const pipeData = this.data.pipeline || {};
        const tat = pipeData.tat || {};
        const pipeline = pipeData.pipeline || [];
        
        const funnelHtml = pipeline.map((p, i) => {
            const colors = ['#3b82f6','#6366f1','#8b5cf6','#10b981','#f59e0b','#6b7280'];
            const w = Math.max(30, p.pct);
            return '<div class="bi-funnel-row">' +
                '<span class="bi-funnel-label">' + p.stage + '</span>' +
                '<div class="bi-funnel-bar-wrap"><div class="bi-funnel-bar" style="width:' + w + '%;background:' + colors[i % 6] + '"></div></div>' +
                '<span class="bi-funnel-count">' + this.fmtN(p.count) + '</span>' +
                '</div>';
        }).join("");
        
        const tatColor = (tat.avg || 0) <= 7 ? '#10b981' : (tat.avg || 0) <= 15 ? '#f59e0b' : '#ef4444';

        // Branch Performance + Quick Stats
        const branchData = this.data.branches || {};
        const branches = branchData.branches || [];
        const qStats = branchData.quick_stats || {};
        
        const branchRows = branches.map((b, i) => {
            const effColor = b.efficiency >= 80 ? '#10b981' : b.efficiency >= 50 ? '#f59e0b' : '#ef4444';
            return '<div class="bi-branch-row">' +
                '<span class="bi-branch-rank">' + (i+1) + '</span>' +
                '<div class="bi-branch-info"><span class="bi-branch-name">' + b.name + '</span>' +
                '<span class="bi-branch-meta">' + b.loans + ' loans</span></div>' +
                '<div class="bi-branch-bar-wrap"><div class="bi-branch-bar" style="width:' + Math.min(b.efficiency, 100) + '%;background:' + effColor + '"></div></div>' +
                '<span class="bi-branch-eff" style="color:' + effColor + '">' + b.efficiency + '%</span>' +
                '<span class="bi-branch-amt">' + this.fmt(b.disbursed) + '</span>' +
                '</div>';
        }).join("") || '<div class="bi-empty">No branch data</div>';

        // Growth & Collection
        const growth = this.data.growth || {};
        const coll = growth.collection || {};
        const newLoans = growth.new_loans_trend || [];
        const newCusts = growth.new_customers_trend || [];
        
        // Collection gauge
        const collRate = coll.rate || 0;
        const collColor = collRate >= 80 ? '#10b981' : collRate >= 50 ? '#f59e0b' : '#ef4444';
        const collDeg = Math.min(collRate, 100) * 1.8; // 180 deg max
        
        // New loans mini sparkline
        const maxNewLoans = Math.max(...newLoans.map(l => l.count), 1);
        const loanSparkW = 200, loanSparkH = 40;
        const loanSparkStep = loanSparkW / Math.max(newLoans.length - 1, 1);
        const loanSparkPoints = newLoans.map((l, i) => (loanSparkStep * i).toFixed(0) + ',' + (loanSparkH - (l.count / maxNewLoans) * (loanSparkH - 4)).toFixed(0)).join(' ');
        const loanSparkArea = loanSparkPoints + ' ' + loanSparkW + ',' + loanSparkH + ' 0,' + loanSparkH;
        
        // New customers sparkline
        const maxNewCusts = Math.max(...newCusts.map(c => c.count), 1);
        const custSparkPoints = newCusts.map((c, i) => (loanSparkStep * i).toFixed(0) + ',' + (loanSparkH - (c.count / maxNewCusts) * (loanSparkH - 4)).toFixed(0)).join(' ');
        const custSparkArea = custSparkPoints + ' ' + loanSparkW + ',' + loanSparkH + ' 0,' + loanSparkH;

        // Pending Approvals
        const pend = this.data.pending || {};
        const approvals = pend.approvals || [];
        const drafts = pend.drafts || [];
        const teamAct = pend.team_activity || [];
        
        const approvalRows = approvals.map(a => {
            return '<div class="bi-appr-row"><span class="bi-appr-dt">' + a.doctype + '</span><span class="bi-appr-cnt">' + a.count + '</span></div>';
        }).join("") || '<div class="bi-empty">No pending approvals</div>';
        
        const draftRows = drafts.map(d => {
            return '<div class="bi-appr-row"><span class="bi-appr-dt">' + d.doctype + '</span><span class="bi-appr-cnt draft">' + d.count + '</span></div>';
        }).join("");
        
        const teamRows = teamAct.map((t, i) => {
            const colors = ["#3b82f6","#10b981","#f59e0b","#8b5cf6","#ef4444"];
            return '<div class="bi-team-row">' +
                '<div class="bi-team-avatar" style="background:' + colors[i % 5] + '">' + (t.user || "?")[0].toUpperCase() + '</div>' +
                '<div class="bi-team-info"><span class="bi-team-name">' + t.user + '</span><span class="bi-team-meta">' + t.actions + ' actions</span></div>' +
                '</div>';
        }).join("") || '<div class="bi-empty">No activity in 24h</div>';

        // Receivables Ageing
        const recv = this.data.receivables || {};
        const recvBuckets = recv.buckets || [];
        const recvTotal = recv.total_outstanding || 0;
        const topDefault = recv.top_defaulters || [];
        
        const recvBars = recvBuckets.map(b => {
            return '<div class="bi-recv-row">' +
                '<span class="bi-recv-label">' + b.label + '</span>' +
                '<div class="bi-recv-bar-wrap"><div class="bi-recv-bar" style="width:' + b.pct + '%;background:' + b.color + '"></div></div>' +
                '<span class="bi-recv-amt">' + this.fmt(b.amount) + '</span>' +
                '<span class="bi-recv-pct">' + b.pct + '%</span>' +
                '</div>';
        }).join("");
        
        const defaulterRows = topDefault.map((d, i) => {
            return '<div class="bi-def-row">' +
                '<span class="bi-def-rank">' + (i+1) + '</span>' +
                '<div class="bi-def-info"><span class="bi-def-name">' + (d.party || "").substring(0, 25) + '</span>' +
                '<span class="bi-def-meta">' + d.invoices + ' invoices \u00b7 ' + d.days + ' days old</span></div>' +
                '<span class="bi-def-amt">' + this.fmt(d.amount) + '</span>' +
                '</div>';
        }).join("") || '<div class="bi-empty">No overdue found</div>';

        this.page.main.html(`
            <div class="bi-dash">
                <!-- Header -->
                <div class="bi-header">
                    <div>
                        <h1 class="bi-title">Business Intelligence</h1>
                        <p class="bi-subtitle">${info.total_documents ? this.fmtN(info.total_documents) + ' records across ' + info.total_doctypes + ' types · ' + info.total_users + ' users' : 'Loading...'}</p>
                    </div>
                    <div class="bi-header-actions">
                        <button class="bi-btn-ai-mode" id="biAiMode" onclick="window._biLoadAI && window._biLoadAI()">&#x2728; Load via AI</button>
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



                    <!-- Pending Approvals -->
                    <div class="bi-card">
                        <div class="bi-card-header">
                            <h3>&#x1F4CB; Pending Approvals</h3>
                            <span class="bi-badge-warn">${pend.total_pending || 0}</span>
                        </div>
                        <div class="bi-appr-list">${approvalRows}</div>
                        ${draftRows ? '<div class="bi-appr-divider">Drafts</div><div class="bi-appr-list">' + draftRows + '</div>' : ''}
                    </div>

                    <!-- Team Activity -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>&#x1F465; Team Activity (24h)</h3></div>
                        <div class="bi-team-list">${teamRows}</div>
                    </div>

                    <!-- Branch Performance -->
                    <div class="bi-card bi-span-2">
                        <div class="bi-card-header">
                            <h3>&#x1F3E2; Branch Performance</h3>
                            <span class="bi-badge">${branches.length} branches</span>
                        </div>
                        <div class="bi-branch-header-row">
                            <span style="width:24px"></span>
                            <span class="bi-branch-col-label" style="flex:1">Branch</span>
                            <span class="bi-branch-col-label" style="width:100px">Efficiency</span>
                            <span class="bi-branch-col-label" style="width:50px;text-align:right"></span>
                            <span class="bi-branch-col-label" style="width:70px;text-align:right">Disbursed</span>
                        </div>
                        <div class="bi-branch-list">${branchRows}</div>
                    </div>

                    <!-- Loan Pipeline Funnel -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>&#x1F4CA; Loan Pipeline</h3></div>
                        <div class="bi-funnel-list">${funnelHtml || '<div class="bi-empty">No pipeline data</div>'}</div>
                    </div>

                    <!-- Turnaround Time -->
                    <div class="bi-card bi-tat-card">
                        <div class="bi-card-header"><h3>&#x23F1; Turnaround Time</h3></div>
                        <div class="bi-tat-body">
                            <div class="bi-tat-main">
                                <div class="bi-tat-big" style="color:${tatColor}">${tat.avg || 'N/A'}</div>
                                <div class="bi-tat-unit">avg days</div>
                                <div class="bi-tat-sub">Application to Disbursement</div>
                            </div>
                            <div class="bi-tat-range">
                                <div class="bi-tat-range-item">
                                    <span class="bi-tat-range-label">Fastest</span>
                                    <span class="bi-tat-range-val green">${tat.min || 0} days</span>
                                </div>
                                <div class="bi-tat-range-item">
                                    <span class="bi-tat-range-label">Slowest</span>
                                    <span class="bi-tat-range-val red">${tat.max || 0} days</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- EMI Collection -->
                    <div class="bi-card bi-coll-card">
                        <div class="bi-card-header"><h3>&#x1F4B0; EMI Collection</h3></div>
                        <div class="bi-coll-body">
                            <div class="bi-coll-gauge">
                                <svg viewBox="0 0 120 70" class="bi-gauge-svg">
                                    <path d="M 10 65 A 50 50 0 0 1 110 65" fill="none" stroke="#e5e7eb" stroke-width="8" stroke-linecap="round"/>
                                    <path d="M 10 65 A 50 50 0 0 1 110 65" fill="none" stroke="${collColor}" stroke-width="8" stroke-linecap="round" stroke-dasharray="${collDeg} 180" class="bi-gauge-fill"/>
                                </svg>
                                <div class="bi-gauge-value" style="color:${collColor}">${collRate}%</div>
                                <div class="bi-gauge-label">Collection Rate</div>
                            </div>
                            <div class="bi-coll-stats">
                                <div class="bi-coll-stat"><span class="bi-coll-stat-label">Collected</span><span class="bi-coll-stat-val green">${this.fmt(coll.collected_month)}</span></div>
                                <div class="bi-coll-stat"><span class="bi-coll-stat-label">Outstanding</span><span class="bi-coll-stat-val">${this.fmt(coll.total_outstanding)}</span></div>
                            </div>
                        </div>
                    </div>

                    <!-- New Loans + Customers Sparklines -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>&#x1F4C8; Growth Trends</h3></div>
                        <div class="bi-spark-section">
                            <div class="bi-spark-item">
                                <div class="bi-spark-header"><span>New Loans</span><span class="bi-spark-total">${newLoans.reduce((s,l) => s+l.count, 0)}</span></div>
                                <svg viewBox="0 0 ${loanSparkW} ${loanSparkH}" class="bi-sparkline">
                                    <polygon points="${loanSparkArea}" fill="rgba(59,130,246,0.1)"/>
                                    <polyline points="${loanSparkPoints}" fill="none" stroke="#3b82f6" stroke-width="2"/>
                                </svg>
                                <div class="bi-spark-labels">${newLoans.map(l => '<span>' + l.month + '</span>').join('')}</div>
                            </div>
                            <div class="bi-spark-item">
                                <div class="bi-spark-header"><span>Loan Applications</span><span class="bi-spark-total">${newCusts.reduce((s,c) => s+c.count, 0)}</span></div>
                                <svg viewBox="0 0 ${loanSparkW} ${loanSparkH}" class="bi-sparkline">
                                    <polygon points="${custSparkArea}" fill="rgba(16,185,129,0.1)"/>
                                    <polyline points="${custSparkPoints}" fill="none" stroke="#10b981" stroke-width="2"/>
                                </svg>
                                <div class="bi-spark-labels">${newCusts.map(c => '<span>' + c.month + '</span>').join('')}</div>
                            </div>
                        </div>
                    </div>

                    <!-- Outstanding Receivables -->
                    <div class="bi-card">
                        <div class="bi-card-header">
                            <h3>&#x23F3; Outstanding Receivables</h3>
                            <span class="bi-badge-warn">${this.fmt(recvTotal)}</span>
                        </div>
                        <div class="bi-recv-list">${recvBars || '<div class="bi-empty">No outstanding</div>'}</div>
                        <div class="bi-recv-stacked">
                            ${recvBuckets.map(b => '<div class="bi-recv-seg" style="flex:' + (b.pct || 1) + ';background:' + b.color + '" title="' + b.label + ': ' + b.pct + '%"></div>').join("")}
                        </div>
                    </div>

                    <!-- Top Overdue -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>&#x1F6A8; Top Overdue Parties</h3></div>
                        <div class="bi-def-list">${defaulterRows}</div>
                    </div>

                    <!-- Today Quick Stats -->
                    <div class="bi-card bi-span-2 bi-quick-card">
                        <div class="bi-card-header"><h3>&#x26A1; Today's Snapshot</h3></div>
                        <div class="bi-quick-grid">
                            <div class="bi-quick-item">
                                <div class="bi-quick-icon">&#x1F4B5;</div>
                                <div class="bi-quick-val green">${this.fmt(qStats.today_collections)}</div>
                                <div class="bi-quick-label">Collections Today</div>
                            </div>
                            <div class="bi-quick-item">
                                <div class="bi-quick-icon">&#x1F4E4;</div>
                                <div class="bi-quick-val blue">${this.fmt(qStats.today_disbursements)}</div>
                                <div class="bi-quick-label">Disbursed Today</div>
                            </div>
                            <div class="bi-quick-item">
                                <div class="bi-quick-icon">&#x1F4CA;</div>
                                <div class="bi-quick-val">${this.fmtN(qStats.active_loans)}</div>
                                <div class="bi-quick-label">Active Loans</div>
                            </div>
                            <div class="bi-quick-item">
                                <div class="bi-quick-icon">&#x1F3AF;</div>
                                <div class="bi-quick-val">${this.fmt(qStats.avg_loan_size)}</div>
                                <div class="bi-quick-label">Avg Loan Size</div>
                            </div>
                        </div>
                    </div>

                    <!-- Loan Portfolio Overview -->
                    <div class="bi-card bi-span-2 bi-loan-card">
                        <div class="bi-card-header">
                            <h3>🏦 Loan Portfolio Overview</h3>
                            <span class="bi-badge">${this.fmtN(loanSum.active_loans || 0)} Active</span>
                        </div>
                        <div class="bi-loan-kpis">
                            <div class="bi-loan-kpi">
                                <div class="bi-loan-kpi-label">Total Sanctioned</div>
                                <div class="bi-loan-kpi-value">${this.fmt(loanSum.total_sanctioned)}</div>
                            </div>
                            <div class="bi-loan-kpi">
                                <div class="bi-loan-kpi-label">Total Disbursed</div>
                                <div class="bi-loan-kpi-value green">${this.fmt(loanSum.total_disbursed)}</div>
                            </div>
                            <div class="bi-loan-kpi">
                                <div class="bi-loan-kpi-label">Total Collected</div>
                                <div class="bi-loan-kpi-value blue">${this.fmt(loanSum.total_collected)}</div>
                            </div>
                            <div class="bi-loan-kpi">
                                <div class="bi-loan-kpi-label">Written Off</div>
                                <div class="bi-loan-kpi-value red">${this.fmt(loanSum.written_off)}</div>
                            </div>
                            <div class="bi-loan-kpi">
                                <div class="bi-loan-kpi-label">New Applications</div>
                                <div class="bi-loan-kpi-value">${loanSum.new_applications_month || 0} <small>this month</small></div>
                            </div>
                            <div class="bi-loan-kpi">
                                <div class="bi-loan-kpi-label">Closure Requests</div>
                                <div class="bi-loan-kpi-value orange">${loanSum.closure_requests || 0} <small>pending</small></div>
                            </div>
                        </div>
                    </div>

                    <!-- Loan Status Breakdown -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>📊 Loan Status</h3></div>
                        <div class="bi-loan-status-list">${loanStatusCards || '<div class="bi-empty">No loan data</div>'}</div>
                    </div>

                    <!-- Disbursement Trend -->
                    <div class="bi-card">
                        <div class="bi-card-header"><h3>📈 Disbursement Trend</h3></div>
                        <div class="bi-disb-chart">${disbChartHtml}</div>
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

        // AI Mode — reload all data via AI agent
        window._biLoadAI = async () => {
            const btn = document.getElementById("biAiMode");
            btn.innerHTML = "&#x2728; AI Loading...";
            btn.disabled = true;
            
            // Show loading overlay
            const overlay = document.createElement("div");
            overlay.className = "bi-ai-overlay";
            overlay.innerHTML = '<div class="bi-ai-overlay-content"><div class="bi-ai-spinner">&#x2728;</div><div class="bi-ai-overlay-text">AI is analyzing your business data...</div><div class="bi-ai-overlay-sub">Using tools to query database</div></div>';
            document.querySelector(".bi-dash").prepend(overlay);
            
            try {
                const r = await frappe.call({
                    method: "niv_ai.niv_ui.api.bi_dashboard.get_ai_dashboard_data",
                    freeze: false
                });
                const result = r.message;
                overlay.remove();
                btn.innerHTML = "&#x2728; Load via AI";
                btn.disabled = false;
                
                if (result.data) {
                    // Show AI response in a panel
                    const panel = document.createElement("div");
                    panel.className = "bi-ai-result-panel";
                    panel.innerHTML = '<div class="bi-ai-result-header"><span>&#x2728; AI Dashboard Analysis</span><button onclick="this.closest(\'.bi-ai-result-panel\').remove()">&#x2715;</button></div>' +
                        '<pre class="bi-ai-result-json">' + JSON.stringify(result.data, null, 2) + '</pre>';
                    document.querySelector(".bi-header").after(panel);
                } else if (result.raw) {
                    const panel = document.createElement("div");
                    panel.className = "bi-ai-result-panel";
                    panel.innerHTML = '<div class="bi-ai-result-header"><span>&#x2728; AI Response</span><button onclick="this.closest(\'.bi-ai-result-panel\').remove()">&#x2715;</button></div>' +
                        '<div class="bi-ai-result-text">' + (result.raw || "").replace(/\n/g, "<br>") + '</div>';
                    document.querySelector(".bi-header").after(panel);
                }
            } catch(e) {
                overlay.remove();
                btn.innerHTML = "&#x2728; Load via AI";
                btn.disabled = false;
                frappe.msgprint("AI analysis failed. Try again.");
            }
        };

        // Auto-refresh every 5 minutes
        if (this._refreshTimer) clearInterval(this._refreshTimer);
        this._refreshTimer = setInterval(() => this.init(), 300000);
    }
}
