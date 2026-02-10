frappe.pages["niv-credits"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Niv Credits",
        single_column: true,
    });

    $(wrapper).find(".page-head").hide();
    new NivCredits(page);
};

class NivCredits {
    constructor(page) {
        this.page = page;
        this.wrapper = $(page.body);
        this.plans = [];
        this.demo_mode = false;
        this.init();
    }

    async init() {
        this.wrapper.html(frappe.render_template("niv_credits"));

        this.$demoBadge = this.wrapper.find(".niv-demo-badge");
        this.$demoModal = this.wrapper.find(".niv-demo-modal");
        this.$successOverlay = this.wrapper.find(".niv-success-overlay");

        this.$demoModal.find(".demo-modal-close, .niv-demo-modal-backdrop").on("click", () => {
            this.$demoModal.hide();
        });

        this.$successOverlay.find(".dismiss-btn").on("click", () => {
            this.$successOverlay.hide();
        });

        this.loadBalance();
        this.loadPlans();
        this.loadHistory();
    }

    async loadBalance() {
        try {
            const data = await frappe.call({
                method: "niv_ai.niv_billing.api.billing.check_balance",
            });
            const bal = data.message;
            const balance = Number(bal.balance) || 0;
            const monthlyUsed = Number(bal.monthly_used || bal.used_this_month || 0);
            const dailyUsed = Number(bal.daily_used || 0);
            const totalPool = balance + monthlyUsed;

            this.wrapper.find(".balance-value").text(balance.toLocaleString());

            const modeText = bal.mode === "shared_pool" ? "Shared Pool" : "Personal Wallet";
            this.wrapper.find(".niv-balance-mode-tag").text(modeText);

            this.wrapper.find(".monthly-used").text(monthlyUsed.toLocaleString());
            this.wrapper.find(".daily-used").text(dailyUsed.toLocaleString());

            // Usage bar
            const usagePercent = totalPool > 0 ? Math.min((monthlyUsed / totalPool) * 100, 100) : 0;
            this.wrapper.find(".niv-usage-bar-fill").css("width", usagePercent + "%");
            this.wrapper.find(".usage-used-label").text(monthlyUsed.toLocaleString() + " used");
            this.wrapper.find(".usage-total-label").text(totalPool.toLocaleString() + " total");
        } catch (e) {
            this.wrapper.find(".balance-value").text("?");
        }
    }

    async loadPlans() {
        try {
            const data = await frappe.call({
                method: "niv_ai.niv_billing.api.payment.get_plans",
            });
            const result = data.message || {};
            this.plans = result.plans || result || [];
            this.demo_mode = result.demo_mode || false;

            if (this.demo_mode) {
                this.$demoBadge.show();
            }

            this.renderPlans();
        } catch (e) {
            this.wrapper.find(".niv-plans-grid").html(
                "<p style=\"color: var(--nrc-danger); text-align: center;\">Failed to load plans.</p>"
            );
        }
    }

    renderPlans() {
        const grid = this.wrapper.find(".niv-plans-grid");
        grid.empty();

        const plans = Array.isArray(this.plans) ? this.plans : [];

        if (!plans.length) {
            grid.html("<p style=\"text-align:center; color: var(--nrc-text-muted);\">No plans available.</p>");
            return;
        }

        plans.forEach((plan, idx) => {
            const currency = plan.currency || "INR";
            const symbol = currency === "INR" ? "\u20B9" : currency === "USD" ? "$" : currency;
            const isPopular = idx === 1 && plans.length > 2;
            const tokens = Number(plan.tokens);
            const price = Number(plan.price);
            const rate = tokens > 0 ? (price / tokens * 1000).toFixed(2) : "0";

            const cardEl = document.createElement("div");
            cardEl.className = "niv-plan-card" + (isPopular ? " popular" : "");
            cardEl.setAttribute("data-plan", encodeURIComponent(plan.name));

            let html = "";
            if (isPopular) {
                html += "<div class=\"popular-badge\">Popular</div>";
            }
            html += "<div class=\"plan-name\">" + frappe.utils.escape_html(plan.plan_name) + "</div>";
            html += "<div class=\"plan-tokens\">" + tokens.toLocaleString() + " <span class=\"plan-tokens-unit\">tokens</span></div>";
            html += "<div class=\"plan-price\">" + symbol + " " + price.toLocaleString() + "</div>";
            html += "<div class=\"plan-rate\">" + symbol + rate + " per 1K tokens</div>";
            if (plan.description) {
                html += "<div class=\"plan-desc\">" + frappe.utils.escape_html(plan.description) + "</div>";
            }
            html += "<button class=\"plan-buy-btn\">" + (this.demo_mode ? "\uD83E\uDDEA Demo Buy" : "Buy Now") + "</button>";

            cardEl.innerHTML = html;

            $(cardEl).find(".plan-buy-btn").on("click", (e) => {
                e.stopPropagation();
                this.initPayment(plan);
            });
            $(cardEl).on("click", () => this.initPayment(plan));
            grid.append(cardEl);
        });
    }

    async initPayment(plan) {
        frappe.show_alert({ message: "Creating order...", indicator: "blue" });

        try {
            const data = await frappe.call({
                method: "niv_ai.niv_billing.api.payment.create_order",
                args: { plan_name: plan.name },
            });

            const order = data.message;

            if (order.free) {
                frappe.show_alert({ message: order.message || "Tokens credited!", indicator: "green" }, 5);
                this.loadBalance();
                this.loadTransactions();
                return;
            } else if (order.demo_mode) {
                this.openDemoCheckout(order);
            } else {
                this.openRazorpayCheckout(order);
            }
        } catch (e) {
            frappe.msgprint({
                title: "Error",
                indicator: "red",
                message: e.message || "Failed to create order.",
            });
        }
    }

    openDemoCheckout(order) {
        const currency = order.currency || "INR";
        const symbol = currency === "INR" ? "\u20B9" : currency === "USD" ? "$" : currency;

        this.$demoModal.find(".demo-plan-name").text(order.plan_name);
        this.$demoModal.find(".demo-plan-price").text(
            symbol + " " + (order.amount / 100).toLocaleString() + " \u2014 " + Number(order.tokens).toLocaleString() + " tokens"
        );

        const $payBtn = this.$demoModal.find(".demo-pay-btn");
        $payBtn.prop("disabled", false);
        this.$demoModal.find(".demo-pay-text").show();
        this.$demoModal.find(".demo-pay-spinner").hide();

        $payBtn.off("click").on("click", () => {
            $payBtn.prop("disabled", true);
            this.$demoModal.find(".demo-pay-text").hide();
            this.$demoModal.find(".demo-pay-spinner").show();

            setTimeout(() => {
                this.$demoModal.hide();
                this.verifyPayment({
                    razorpay_order_id: order.order_id,
                    razorpay_payment_id: "demo_pay_" + Date.now(),
                    razorpay_signature: "demo_sig_" + Date.now(),
                });
            }, 2000);
        });

        this.$demoModal.show();
    }

    openRazorpayCheckout(order) {
        const doOpen = () => {
            const self = this;
            const options = {
                key: order.razorpay_key,
                amount: order.amount,
                currency: order.currency,
                name: "Niv AI",
                description: order.plan_name + " \u2014 " + Number(order.tokens).toLocaleString() + " tokens",
                order_id: order.order_id,
                prefill: {
                    email: order.user_email,
                    name: order.user_name,
                },
                theme: { color: "#7C3AED" },
                handler: function (response) {
                    self.verifyPayment(response);
                },
                modal: {
                    ondismiss: function () {
                        frappe.show_alert({ message: "Payment cancelled", indicator: "orange" });
                    },
                },
            };
            const rzp = new Razorpay(options);
            rzp.on("payment.failed", function (response) {
                frappe.msgprint({
                    title: "Payment Failed",
                    indicator: "red",
                    message: response.error.description || "Payment was not completed.",
                });
            });
            rzp.open();
        };

        if (!window.Razorpay) {
            const s = document.createElement("script");
            s.src = "https://checkout.razorpay.com/v1/checkout.js";
            s.onload = doOpen;
            s.onerror = () => frappe.msgprint("Failed to load Razorpay SDK");
            document.head.appendChild(s);
        } else {
            doOpen();
        }
    }

    async verifyPayment(response) {
        frappe.show_alert({ message: "Verifying payment...", indicator: "blue" });

        try {
            const data = await frappe.call({
                method: "niv_ai.niv_billing.api.payment.verify_payment",
                args: {
                    razorpay_order_id: response.razorpay_order_id,
                    razorpay_payment_id: response.razorpay_payment_id,
                    razorpay_signature: response.razorpay_signature,
                },
            });

            const result = data.message;
            this.showSuccess(result);
            this.loadBalance();
            this.loadHistory();
        } catch (e) {
            frappe.msgprint({
                title: "Verification Failed",
                indicator: "red",
                message: e.message || "Could not verify payment. Contact support if amount was deducted.",
            });
        }
    }

    showSuccess(result) {
        this.$successOverlay.find(".tokens-added").text(Number(result.tokens_added).toLocaleString());
        this.$successOverlay.find(".new-balance").text(Number(result.new_balance).toLocaleString());

        this.createConfetti();

        this.$successOverlay.show().css("opacity", 0).animate({ opacity: 1 }, 300);

        setTimeout(() => {
            if (this.$successOverlay.is(":visible")) {
                this.$successOverlay.fadeOut(300);
            }
        }, 5000);
    }

    createConfetti() {
        const $container = this.$successOverlay.find(".success-confetti");
        $container.empty();
        const colors = ["#7C3AED", "#a855f7", "#f59e0b", "#10b981", "#3b82f6", "#ef4444", "#ec4899"];
        for (let i = 0; i < 60; i++) {
            const $piece = $("<div class=\"confetti-piece\"></div>");
            $piece.css({
                left: Math.random() * 100 + "%",
                background: colors[Math.floor(Math.random() * colors.length)],
                animationDelay: Math.random() * 0.5 + "s",
                animationDuration: (Math.random() * 1 + 1.5) + "s",
            });
            $container.append($piece);
        }
    }

    async loadHistory() {
        try {
            const data = await frappe.call({
                method: "niv_ai.niv_billing.api.payment.get_recharge_history",
                args: { page: 1, page_size: 20 },
            });

            const records = (data.message && data.message.records) || [];
            const tbody = this.wrapper.find(".niv-history-body");
            const empty = this.wrapper.find(".niv-history-empty");
            tbody.empty();

            if (!records.length) {
                empty.show();
                this.wrapper.find(".niv-history-table").hide();
                return;
            }

            empty.hide();
            this.wrapper.find(".niv-history-table").show();

            records.forEach((r) => {
                const date = frappe.datetime.str_to_user(r.creation);
                const statusClass = "status-" + (r.status || "").toLowerCase();
                const isDemo = (r.transaction_type === "demo" || (r.remarks && r.remarks.includes("[DEMO]")));
                const paymentId = r.payment_id || r.razorpay_payment_id || "\u2014";

                const tr = document.createElement("tr");
                tr.innerHTML =
                    "<td>" + date + "</td>" +
                    "<td>" + frappe.utils.escape_html(r.plan || r.remarks || "\u2014") +
                        (isDemo ? " <span class=\"demo-tag\">DEMO</span>" : "") + "</td>" +
                    "<td>" + Number(r.tokens).toLocaleString() + "</td>" +
                    "<td>" + (r.amount ? "\u20B9" + Number(r.amount).toLocaleString() : "\u2014") + "</td>" +
                    "<td class=\"" + statusClass + "\">" + frappe.utils.escape_html(r.status || "\u2014") + "</td>" +
                    "<td class=\"payment-id-cell\">" + frappe.utils.escape_html(paymentId) + "</td>";
                tbody.append(tr);
            });
        } catch (e) {
            // silently fail
        }
    }
}
