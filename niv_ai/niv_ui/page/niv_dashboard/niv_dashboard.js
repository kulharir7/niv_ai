frappe.pages["niv-dashboard"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Niv AI Analytics",
        single_column: true,
    });

    // Load Chart.js from CDN
    if (!window.Chart) {
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js";
        script.onload = () => new NivDashboard(page);
        document.head.appendChild(script);
    } else {
        new NivDashboard(page);
    }
};

class NivDashboard {
    constructor(page) {
        this.page = page;
        this.wrapper = $(page.body);
        this.wrapper.html(frappe.render_template("niv_dashboard"));
        this.days = 30;
        this.charts = {};
        this.usageData = [];
        this.currentMetric = "tokens";
        this.refreshTimer = null;

        this._initDates();
        this._bindEvents();
        this.loadAll();
        this._startAutoRefresh();
    }

    _initDates() {
        const today = frappe.datetime.get_today();
        const from = frappe.datetime.add_days(today, -30);
        this.wrapper.find(".niv-dash-to-date").val(today);
        this.wrapper.find(".niv-dash-from-date").val(from);
    }

    _bindEvents() {
        this.wrapper.find(".niv-dash-period-select").on("change", (e) => {
            this.days = parseInt(e.target.value);
            const today = frappe.datetime.get_today();
            this.wrapper.find(".niv-dash-from-date").val(frappe.datetime.add_days(today, -this.days));
            this.wrapper.find(".niv-dash-to-date").val(today);
            this.loadAll();
        });
        this.wrapper.find(".niv-dash-refresh").on("click", () => this.loadAll());
        this.wrapper.find(".niv-dash-export").on("click", () => this.exportCSV());
        this.wrapper.find(".niv-dash-from-date, .niv-dash-to-date").on("change", () => {
            const from = this.wrapper.find(".niv-dash-from-date").val();
            const to = this.wrapper.find(".niv-dash-to-date").val();
            if (from && to) {
                const diffMs = new Date(to) - new Date(from);
                this.days = Math.max(1, Math.ceil(diffMs / 86400000));
                this.loadAll();
            }
        });
        this.wrapper.on("click", ".niv-dash-toggle", (e) => {
            this.wrapper.find(".niv-dash-toggle").removeClass("active");
            $(e.target).addClass("active");
            this.currentMetric = $(e.target).data("metric");
            this.renderUsageChart();
        });
    }

    _startAutoRefresh() {
        this.refreshTimer = setInterval(() => this.loadAll(true), 60000);
        // Cleanup on page change
        $(this.page.parent).on("remove", () => clearInterval(this.refreshTimer));
    }

    async loadAll(silent) {
        if (!silent) {
            this.wrapper.find(".niv-dash-stats-row").html(
                '<div class="niv-dash-loading"><i class="fa fa-spinner fa-spin"></i> Loading analytics...</div>'
            );
        }

        const api = (method, args) => frappe.call({
            method: "niv_ai.niv_billing.api.admin." + method,
            args: { days: this.days, ...args },
        }).then(r => r.message);

        try {
            const [stats, usage, topUsers, models, tools, heatmap] = await Promise.all([
                api("get_dashboard_stats"),
                api("get_usage_over_time", { period: "daily" }),
                api("get_top_users", { limit: 10 }),
                api("get_model_usage"),
                api("get_tool_usage"),
                api("get_hourly_distribution"),
            ]);

            this.usageData = usage || [];
            this.renderStats(stats);
            this.renderUsageChart();
            this.renderModelChart(models || []);
            this.renderToolChart(tools || []);
            this.renderHeatmap(heatmap || {});
            this.renderTopUsers(topUsers || []);

            this.wrapper.find(".niv-dash-last-updated").text(
                "Updated " + frappe.datetime.prettyDate(frappe.datetime.now_datetime())
            );
        } catch (e) {
            if (!silent) {
                this.wrapper.find(".niv-dash-stats-row").html(
                    '<div class="niv-dash-loading" style="color:#f87171;">Failed to load. Ensure System Manager role.</div>'
                );
            }
        }
    }

    renderStats(data) {
        const t = data.trends || {};
        const cards = [
            { icon: "👥", value: this.fmt(data.total_users), label: "Total Users", trend: t.users },
            { icon: "💬", value: this.fmt(data.total_conversations), label: "Conversations", trend: null },
            { icon: "📨", value: this.fmt(data.total_messages), label: "Messages", trend: t.requests },
            { icon: "🔤", value: this.fmt(data.total_tokens), label: "Tokens Used", trend: t.tokens },
            { icon: "💰", value: "₹" + (data.total_cost || 0).toFixed(2), label: "Total Cost", trend: t.cost },
        ];

        let html = "";
        for (const c of cards) {
            const trendHtml = c.trend !== null ? this._trendHtml(c.trend) : "";
            html += `
                <div class="niv-dash-stat">
                    <div class="niv-dash-stat-icon">${c.icon}</div>
                    <div class="niv-dash-stat-value">${c.value}</div>
                    <div class="niv-dash-stat-label">${c.label}</div>
                    ${trendHtml}
                </div>`;
        }
        this.wrapper.find(".niv-dash-stats-row").html(html);
    }

    _trendHtml(pct) {
        if (pct === null || pct === undefined) return "";
        const cls = pct > 0 ? "niv-dash-trend-up" : pct < 0 ? "niv-dash-trend-down" : "niv-dash-trend-flat";
        const arrow = pct > 0 ? "↑" : pct < 0 ? "↓" : "→";
        return `<div class="niv-dash-stat-trend ${cls}">${arrow} ${Math.abs(pct)}% vs prev</div>`;
    }

    renderUsageChart() {
        const data = this.usageData;
        if (this.charts.usage) this.charts.usage.destroy();
        const canvas = document.getElementById("niv-usage-chart");
        if (!canvas || !data.length) return;

        const labels = data.map(d => d.date);
        let values, label, color;

        if (this.currentMetric === "messages") {
            values = data.map(d => d.messages || d.requests);
            label = "Messages"; color = "#a78bfa";
        } else if (this.currentMetric === "cost") {
            values = data.map(d => d.cost);
            label = "Cost (₹)"; color = "#f59e0b";
        } else {
            values = data.map(d => d.total_tokens);
            label = "Tokens"; color = "#7c3aed";
        }

        this.charts.usage = new Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label,
                    data: values,
                    backgroundColor: color + "66",
                    borderColor: color,
                    borderWidth: 2,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { backgroundColor: "#1e1b2e", titleColor: "#c4b5fd", bodyColor: "#e2e8f0" },
                },
                scales: {
                    x: { grid: { color: "rgba(124,58,237,0.1)" }, ticks: { color: "#94a3b8", maxRotation: 45 } },
                    y: { grid: { color: "rgba(124,58,237,0.1)" }, ticks: { color: "#94a3b8" }, beginAtZero: true },
                },
            },
        });
    }

    renderModelChart(data) {
        if (this.charts.model) this.charts.model.destroy();
        const canvas = document.getElementById("niv-model-chart");
        if (!canvas || !data.length) return;

        const colors = ["#7c3aed", "#3b82f6", "#10b981", "#f97316", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899"];

        this.charts.model = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: data.map(d => d.model),
                datasets: [{
                    data: data.map(d => d.total_tokens),
                    backgroundColor: colors.slice(0, data.length),
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "60%",
                plugins: {
                    legend: { position: "bottom", labels: { color: "#94a3b8", padding: 12, usePointStyle: true, pointStyleWidth: 8 } },
                    tooltip: { backgroundColor: "#1e1b2e", titleColor: "#c4b5fd", bodyColor: "#e2e8f0" },
                },
            },
        });
    }

    renderToolChart(data) {
        if (this.charts.tool) this.charts.tool.destroy();
        const canvas = document.getElementById("niv-tool-chart");
        const emptyEl = this.wrapper.find(".niv-dash-tool-empty");

        if (!canvas || !data.length) {
            $(canvas).hide();
            emptyEl.show();
            return;
        }
        $(canvas).show();
        emptyEl.hide();

        this.charts.tool = new Chart(canvas, {
            type: "bar",
            data: {
                labels: data.map(d => d.tool_name),
                datasets: [
                    {
                        label: "Success",
                        data: data.map(d => d.success_count),
                        backgroundColor: "#10b981aa",
                        borderColor: "#10b981",
                        borderWidth: 1,
                        borderRadius: 3,
                    },
                    {
                        label: "Failed",
                        data: data.map(d => d.fail_count),
                        backgroundColor: "#ef4444aa",
                        borderColor: "#ef4444",
                        borderWidth: 1,
                        borderRadius: 3,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top", labels: { color: "#94a3b8", usePointStyle: true, pointStyleWidth: 8 } },
                    tooltip: { backgroundColor: "#1e1b2e" },
                },
                scales: {
                    x: { stacked: true, grid: { color: "rgba(124,58,237,0.1)" }, ticks: { color: "#94a3b8" } },
                    y: { stacked: true, grid: { display: false }, ticks: { color: "#e2e8f0" } },
                },
            },
        });
    }

    renderHeatmap(data) {
        const $container = this.wrapper.find(".niv-dash-heatmap");
        const matrix = data.matrix || [];
        const dayLabels = data.day_labels || ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

        if (!matrix.length) {
            $container.html('<p class="text-muted" style="text-align:center;padding:20px;">No data</p>');
            return;
        }

        // Find max for scaling
        let maxVal = 1;
        for (const row of matrix) for (const v of row) if (v > maxVal) maxVal = v;

        let html = '<table><thead><tr><th></th>';
        for (let h = 0; h < 24; h++) html += `<th>${h}</th>`;
        html += "</tr></thead><tbody>";

        for (let d = 0; d < 7; d++) {
            html += `<tr><th>${dayLabels[d]}</th>`;
            for (let h = 0; h < 24; h++) {
                const v = matrix[d] ? matrix[d][h] || 0 : 0;
                const level = v === 0 ? 0 : Math.min(5, Math.ceil((v / maxVal) * 5));
                html += `<td class="niv-heat-${level}" title="${dayLabels[d]} ${h}:00 — ${v} requests">${v || ""}</td>`;
            }
            html += "</tr>";
        }
        html += "</tbody></table>";
        $container.html(html);
    }

    renderTopUsers(users) {
        const $container = this.wrapper.find(".niv-dash-top-users");
        if (!users.length) {
            $container.html('<p class="text-muted" style="text-align:center;padding:20px;">No data</p>');
            return;
        }

        let html = "";
        users.forEach((u, i) => {
            html += `
                <div class="niv-dash-user-row">
                    <div class="niv-dash-user-rank">#${i + 1}</div>
                    <div class="niv-dash-user-info">
                        <div class="niv-dash-user-name">${frappe.utils.escape_html(u.full_name || u.user)}</div>
                        <div class="niv-dash-user-meta">${u.conversations} convos · ${u.requests} requests</div>
                    </div>
                    <div class="niv-dash-user-bar-wrap">
                        <div class="niv-dash-user-bar" style="width:${u.bar_pct}%"></div>
                    </div>
                    <div class="niv-dash-user-tokens">${this.fmt(u.total_tokens)}</div>
                </div>`;
        });
        $container.html(html);
    }

    async exportCSV() {
        const from = this.wrapper.find(".niv-dash-from-date").val();
        const to = this.wrapper.find(".niv-dash-to-date").val();

        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.export_usage_csv",
                args: { from_date: from, to_date: to },
            });
            const csv = r.message;
            if (!csv) { frappe.msgprint("No data to export"); return; }

            const blob = new Blob([csv], { type: "text/csv" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `niv_usage_${from}_to_${to}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            frappe.msgprint("Export failed");
        }
    }

    fmt(n) {
        n = n || 0;
        if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
        if (n >= 1000) return (n / 1000).toFixed(1) + "K";
        return n.toLocaleString();
    }
}


// ═══════════════════════════════════════════════════════════
// NEW DASHBOARD METHODS — Append to NivDashboard class
// ═══════════════════════════════════════════════════════════

// Patch loadAll to include new sections
(function() {
    const origLoadAll = NivDashboard.prototype.loadAll;
    NivDashboard.prototype.loadAll = async function(silent) {
        await origLoadAll.call(this, silent);
        // Load new sections
        this.loadInsights();
        this.loadRecommendations();
        this.loadQuality();
        this.loadResponseTimes();
        this.loadSatisfaction();
        this.loadPopularQuestions();
        this.loadBillingOverview();
    };

    NivDashboard.prototype.loadInsights = async function() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.get_ai_insights",
                args: { days: this.days },
            });
            const data = r.message;
            if (!data || !data.insights || !data.insights.length) return;

            let html = '<span class="niv-dash-insights-title">🧠 AI Insights</span>';
            for (const item of data.insights) {
                html += `<div class="niv-dash-insight-item">
                    <span class="niv-dash-insight-icon">${item.icon}</span>
                    <span>${item.text}</span>
                </div>`;
            }
            this.wrapper.find("#niv-insights-bar").html(html);
        } catch(e) {}
    };

    NivDashboard.prototype.loadRecommendations = async function() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.get_ai_recommendations",
                args: { days: this.days },
            });
            const data = r.message;
            if (!data || !data.recommendations || !data.recommendations.length) return;

            let html = '';
            for (const rec of data.recommendations) {
                html += `<div class="niv-dash-rec niv-dash-rec-${rec.type}">
                    <span>${rec.icon}</span>
                    <span>${rec.text}</span>
                </div>`;
            }
            this.wrapper.find("#niv-recommendations").html(html);
        } catch(e) {}
    };

    NivDashboard.prototype.loadQuality = async function() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.get_conversation_quality",
                args: { days: this.days },
            });
            const d = r.message;
            if (!d) return;

            const successClass = d.tool_success_rate >= 90 ? "good" : d.tool_success_rate >= 70 ? "warn" : "bad";
            const errorClass = d.error_response_rate <= 5 ? "good" : d.error_response_rate <= 15 ? "warn" : "bad";

            let html = `
                <div class="niv-dash-quality-card">
                    <div class="niv-dash-quality-value">${d.avg_messages_per_convo}</div>
                    <div class="niv-dash-quality-label">Avg Messages/Convo</div>
                </div>
                <div class="niv-dash-quality-card">
                    <div class="niv-dash-quality-value niv-dash-quality-${successClass}">${d.tool_success_rate}%</div>
                    <div class="niv-dash-quality-label">Tool Success Rate</div>
                </div>
                <div class="niv-dash-quality-card">
                    <div class="niv-dash-quality-value niv-dash-quality-${errorClass}">${d.error_response_rate}%</div>
                    <div class="niv-dash-quality-label">Error Response Rate</div>
                </div>
                <div class="niv-dash-quality-card">
                    <div class="niv-dash-quality-value">${d.tool_usage_pct}%</div>
                    <div class="niv-dash-quality-label">Conversations Using Tools</div>
                </div>`;
            this.wrapper.find("#niv-quality-row").html(html);
        } catch(e) {}
    };

    NivDashboard.prototype.loadResponseTimes = async function() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.get_response_times",
                args: { days: this.days },
            });
            const data = r.message;
            if (!data || !data.daily || !data.daily.length) return;

            // Chart
            if (this.charts.response) this.charts.response.destroy();
            const canvas = document.getElementById("niv-response-chart");
            if (!canvas) return;

            this.charts.response = new Chart(canvas, {
                type: "line",
                data: {
                    labels: data.daily.map(d => d.date),
                    datasets: [{
                        label: "Avg (ms)",
                        data: data.daily.map(d => d.avg_ms),
                        borderColor: "#a78bfa",
                        backgroundColor: "#a78bfa22",
                        fill: true,
                        tension: 0.4,
                        pointRadius: 2,
                    }, {
                        label: "Max (ms)",
                        data: data.daily.map(d => d.max_ms),
                        borderColor: "#f8717144",
                        borderDash: [5, 5],
                        fill: false,
                        tension: 0.4,
                        pointRadius: 0,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: "top", labels: { color: "#94a3b8", usePointStyle: true, pointStyleWidth: 8 } },
                        tooltip: { backgroundColor: "#1e1b2e" },
                    },
                    scales: {
                        x: { grid: { color: "rgba(124,58,237,0.1)" }, ticks: { color: "#94a3b8", maxRotation: 45 } },
                        y: { grid: { color: "rgba(124,58,237,0.1)" }, ticks: { color: "#94a3b8" }, beginAtZero: true },
                    },
                },
            });

            // Stats below chart
            let statsHtml = `
                <div class="niv-dash-response-stat">
                    <div class="niv-dash-response-stat-val">${data.overall.avg_ms || 0}ms</div>
                    <div class="niv-dash-response-stat-label">Average</div>
                </div>
                <div class="niv-dash-response-stat">
                    <div class="niv-dash-response-stat-val">${data.overall.max_ms || 0}ms</div>
                    <div class="niv-dash-response-stat-label">Slowest</div>
                </div>`;
            this.wrapper.find("#niv-response-stats").html(statsHtml);
        } catch(e) {}
    };

    NivDashboard.prototype.loadSatisfaction = async function() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.get_satisfaction_stats",
                args: { days: this.days },
            });
            const data = r.message;
            if (!data) return;

            // Chart
            if (this.charts.satisfaction) this.charts.satisfaction.destroy();
            const canvas = document.getElementById("niv-satisfaction-chart");
            if (!canvas) return;

            if (data.total_rated > 0) {
                this.charts.satisfaction = new Chart(canvas, {
                    type: "doughnut",
                    data: {
                        labels: ["👍 Positive", "👎 Negative"],
                        datasets: [{
                            data: [data.thumbs_up, data.thumbs_down],
                            backgroundColor: ["#34d39966", "#f8717166"],
                            borderColor: ["#34d399", "#f87171"],
                            borderWidth: 2,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: "65%",
                        plugins: {
                            legend: { position: "bottom", labels: { color: "#94a3b8", padding: 12 } },
                        },
                    },
                });
            } else {
                $(canvas).parent().html('<p style="text-align:center;color:#94a3b8;padding:40px;">No ratings yet</p>');
            }

            // Stats
            let html = `
                <div class="niv-dash-sat-item">
                    <div class="niv-dash-sat-value niv-dash-sat-up">👍 ${data.thumbs_up}</div>
                    <div class="niv-dash-sat-label">Positive</div>
                </div>
                <div class="niv-dash-sat-item">
                    <div class="niv-dash-sat-value niv-dash-sat-down">👎 ${data.thumbs_down}</div>
                    <div class="niv-dash-sat-label">Negative</div>
                </div>
                <div class="niv-dash-sat-item">
                    <div class="niv-dash-sat-value niv-dash-sat-score">${data.satisfaction_pct}%</div>
                    <div class="niv-dash-sat-label">Score</div>
                </div>`;
            this.wrapper.find("#niv-satisfaction-stats").html(html);
        } catch(e) {}
    };

    NivDashboard.prototype.loadPopularQuestions = async function() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.get_popular_questions",
                args: { days: this.days },
            });
            const data = r.message;
            if (!data) return;

            let html = '';
            if (data.question_types) {
                for (const qt of data.question_types) {
                    html += `<div class="niv-dash-popular-item">
                        <span class="niv-dash-popular-type">${qt.type}</span>
                        <span class="niv-dash-popular-count">${qt.count}</span>
                    </div>`;
                }
            }

            // Word cloud
            if (data.top_words && data.top_words.length) {
                html += '<div class="niv-dash-word-cloud">';
                for (const w of data.top_words.slice(0, 15)) {
                    const size = Math.min(16, Math.max(11, 10 + Math.log2(w.count + 1)));
                    html += `<span class="niv-dash-word" style="font-size:${size}px">${w.word} (${w.count})</span>`;
                }
                html += '</div>';
            }

            this.wrapper.find("#niv-popular-questions").html(html || '<p style="text-align:center;color:#94a3b8;padding:20px;">No data</p>');
        } catch(e) {}
    };

    NivDashboard.prototype.loadBillingOverview = async function() {
        try {
            const r = await frappe.call({
                method: "niv_ai.niv_billing.api.admin.get_billing_overview",
                args: { days: this.days },
            });
            const d = r.message;
            if (!d) return;

            let html = '';

            html += `<div class="niv-dash-billing-stat">
                <span class="niv-dash-billing-label">Mode</span>
                <span class="niv-dash-billing-value">${d.billing_mode}</span>
            </div>`;

            if (d.billing_mode === "Shared Pool") {
                const total = d.pool_balance + d.pool_used;
                const pct = total > 0 ? Math.round((d.pool_balance / total) * 100) : 0;
                const barClass = d.days_remaining < 7 ? "niv-dash-billing-bar-danger" : "";

                html += `<div class="niv-dash-billing-stat">
                    <span class="niv-dash-billing-label">Pool Balance</span>
                    <span class="niv-dash-billing-value">${this.fmt(d.pool_balance)} tokens</span>
                </div>
                <div class="niv-dash-billing-bar ${barClass}">
                    <div class="niv-dash-billing-bar-fill" style="width:${pct}%"></div>
                </div>
                <div class="niv-dash-billing-stat">
                    <span class="niv-dash-billing-label">Daily Burn Rate</span>
                    <span class="niv-dash-billing-value">~${this.fmt(d.burn_rate_daily)}/day</span>
                </div>
                <div class="niv-dash-billing-stat">
                    <span class="niv-dash-billing-label">Days Remaining</span>
                    <span class="niv-dash-billing-value" style="color:${d.days_remaining < 7 ? '#f87171' : d.days_remaining < 30 ? '#fbbf24' : '#34d399'}">${d.days_remaining > 999 ? '∞' : '~' + d.days_remaining + ' days'}</span>
                </div>`;
            } else {
                html += `<div class="niv-dash-billing-stat">
                    <span class="niv-dash-billing-label">Total Wallets</span>
                    <span class="niv-dash-billing-value">${d.total_wallets}</span>
                </div>
                <div class="niv-dash-billing-stat">
                    <span class="niv-dash-billing-label">Total Balance</span>
                    <span class="niv-dash-billing-value">${this.fmt(d.total_wallet_balance)} tokens</span>
                </div>`;
            }

            // Per-user costs
            if (d.per_user_costs && d.per_user_costs.length) {
                html += '<div style="margin-top:12px;padding-top:12px;border-top:1px solid rgba(124,58,237,.1);font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Top Spenders</div>';
                for (const u of d.per_user_costs) {
                    html += `<div class="niv-dash-billing-stat">
                        <span class="niv-dash-billing-label">${u.user}</span>
                        <span class="niv-dash-billing-value">${this.fmt(u.tokens)}</span>
                    </div>`;
                }
            }

            this.wrapper.find("#niv-billing-overview").html(html);
        } catch(e) {}
    };
})();
