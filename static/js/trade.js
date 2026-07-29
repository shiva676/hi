const TradeManager = {
    activeTrades: [],
    currentBalance: 0,
    serverTimeOffset: 0,
    submittingTrade: false,
    timer: null,
    refreshBusy: false,

    async init() {
        this.bindControls();
        await this.syncServerTime();
        await this.loadOpenTrade();
        await this.loadHistory();
        this.timer = setInterval(() => this.tick(), 500);
    },

    bindControls() {
        document.getElementById("trade-up")?.addEventListener("click", () => this.openTrade("UP"));
        document.getElementById("trade-down")?.addEventListener("click", () => this.openTrade("DOWN"));
        document.getElementById("amount-plus")?.addEventListener("click", () => this.setAmount(this.getAmount() + 10));
        document.getElementById("amount-minus")?.addEventListener("click", () => this.setAmount(this.getAmount() - 10));
        document.querySelectorAll(".quick-amounts button").forEach(button => {
            button.addEventListener("click", () => this.setAmount(Number(button.dataset.amount)));
        });
    },

    getAmount() {
        return Number(document.getElementById("trade-amount")?.value || 0);
    },

    setAmount(value) {
        const input = document.getElementById("trade-amount");
        if (!input) return;
        const n = Math.max(1, Math.min(1000, Number(value) || 1));
        input.value = Number.isInteger(n) ? String(n) : n.toFixed(2);
    },

    async syncServerTime() {
        try {
            const started = Date.now();
            const response = await fetch("/api/time", {credentials: "same-origin", cache: "no-store"});
            const data = await response.json();
            const midpoint = started + (Date.now() - started) / 2;
            this.serverTimeOffset = Number(data.server_time) - midpoint;
        } catch (_) {
            this.serverTimeOffset = 0;
        }
    },

    getServerTime() {
        return Date.now() + this.serverTimeOffset;
    },

    async openTrade(direction) {
        if (this.submittingTrade) return;
        const amount = this.getAmount();
        if (!Number.isFinite(amount) || amount <= 0) return this.showMessage("Enter a valid investment amount.", "error");
        if (amount > this.currentBalance) return this.showMessage("Insufficient demo balance.", "error");
        if (!TradingChart.currentPrice) return this.showMessage("Waiting for live market data.", "error");

        this.submittingTrade = true;
        this.setTradeButtonsDisabled(true);
        this.showMessage("Opening trade...");
        TelegramApp.haptic("medium");

        try {
            const response = await fetch("/api/trade", {
                method: "POST",
                credentials: "same-origin",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({direction, amount}),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Unable to open trade.");

            this.activeTrades.push(data.trade);
            this.activeTrades.sort((a, b) => Number(a.expiry_time) - Number(b.expiry_time));
            this.setBalance(data.trade.balance);
            this.renderActiveTrade();
            this.showMessage(`${direction} trade #${data.trade.id} opened at ${this.formatPrice(data.trade.entry_price)}.`);
            TelegramApp.successHaptic();
        } catch (error) {
            this.showMessage(error.message || "Unable to open trade.", "error");
            TelegramApp.errorHaptic();
        } finally {
            this.submittingTrade = false;
            this.setTradeButtonsDisabled(false);
        }
    },

    async loadOpenTrade() {
        try {
            const response = await fetch("/api/trade/open", {credentials: "same-origin", cache: "no-store"});
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Unable to load open trades.");
            if (data.server_time) this.serverTimeOffset = Number(data.server_time) - Date.now();
            this.activeTrades = Array.isArray(data.trades) ? data.trades : (data.trade ? [data.trade] : []);
            this.renderActiveTrade();
        } catch (error) {
            console.warn("Open trades refresh failed:", error);
        }
    },

    async loadHistory() {
        try {
            const response = await fetch("/api/trades?limit=20", {credentials: "same-origin", cache: "no-store"});
            const data = await response.json();
            if (!response.ok) return;
            this.renderHistory(data.trades || []);
        } catch (error) {
            console.warn("History refresh failed:", error);
        }
    },

    async refreshState() {
        if (this.refreshBusy) return;
        this.refreshBusy = true;
        try {
            await Promise.all([this.loadOpenTrade(), this.loadHistory(), this.refreshBalance()]);
        } finally {
            this.refreshBusy = false;
        }
    },

    async refreshBalance() {
        try {
            const response = await fetch("/api/balance", {credentials: "same-origin", cache: "no-store"});
            const data = await response.json();
            if (response.ok) this.setBalance(data.balance);
        } catch (_) {}
    },

    tick() {
        const now = this.getServerTime();
        const before = this.activeTrades.length;
        const pendingExpired = this.activeTrades.some(t => Number(t.expiry_time) <= now);
        if (pendingExpired) {
            // Settlement is server-side. Poll shortly after expiry until DB state changes.
            this.refreshState();
        }
        if (before) this.renderActiveTrade();
    },

    onMarketUpdate(price) {
        const current = document.getElementById("active-current");
        if (current && this.activeTrades.length) current.textContent = this.formatPrice(price);
    },

    renderActiveTrade() {
        const panel = document.getElementById("active-trade");
        if (!panel) return;
        if (!this.activeTrades.length) {
            panel.classList.add("hidden");
            TradingChart.clearTrade();
            return;
        }

        // Existing compact panel displays the next trade to expire. All other
        // positions remain active and settle independently in PostgreSQL.
        this.activeTrades.sort((a, b) => Number(a.expiry_time) - Number(b.expiry_time));
        const trade = this.activeTrades[0];
        panel.classList.remove("hidden");
        const remaining = Math.max(0, Number(trade.expiry_time) - this.getServerTime());
        const seconds = Math.ceil(remaining / 1000);

        this.text("active-direction", trade.direction);
        this.text("active-amount", this.money(trade.amount));
        this.text("active-entry", this.formatPrice(trade.entry_price));
        this.text("active-current", this.formatPrice(TradingChart.currentPrice || trade.entry_price));
        this.text("potential-profit", "+" + this.money(Number(trade.amount) * 0.8));
        this.text("trade-timer", `00:${String(Math.min(seconds, 59)).padStart(2, "0")}`);
        const label = document.querySelector("#active-trade .active-label");
        if (label) label.textContent = this.activeTrades.length > 1 ? `ACTIVE TRADES: ${this.activeTrades.length}` : "ACTIVE TRADE";
        TradingChart.showTrade(trade);
    },

    renderHistory(trades) {
        const container = document.getElementById("trade-history");
        if (!container) return;
        if (!trades.length) {
            container.innerHTML = '<div class="empty-history"><div class="empty-history-title">No trades yet</div><div class="empty-history-text">Your trades will appear here.</div></div>';
            return;
        }
        container.innerHTML = trades.map(t => {
            const result = t.status === "OPEN" ? "OPEN" : (t.result || "CLOSED");
            const profit = Number(t.profit || 0);
            return `<div class="history-item"><div><strong>${this.escape(t.direction)} #${Number(t.id)}</strong><span>${this.money(t.amount)} · ${this.formatPrice(t.entry_price)}</span></div><div class="history-result ${result.toLowerCase()}"><strong>${this.escape(result)}</strong><span>${profit > 0 ? "+" : ""}${this.money(profit)}</span></div></div>`;
        }).join("");
    },

    setBalance(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return;
        this.currentBalance = n;
        const el = document.getElementById("demo-balance");
        if (el) el.textContent = this.money(n);
    },

    setTradeButtonsDisabled(disabled) {
        const up = document.getElementById("trade-up");
        const down = document.getElementById("trade-down");
        if (up) up.disabled = Boolean(disabled);
        if (down) down.disabled = Boolean(disabled);
    },

    showMessage(message, type = "info") {
        const el = document.getElementById("trade-message");
        if (!el) return;
        el.textContent = message;
        el.style.color = type === "error" ? "#f6465d" : "";
        el.classList.remove("hidden");
        clearTimeout(this.messageTimer);
        this.messageTimer = setTimeout(() => el.classList.add("hidden"), 4000);
    },

    text(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    },

    money(value) {
        return "$" + Number(value || 0).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    },

    formatPrice(value) {
        return "$" + Number(value || 0).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    },

    escape(value) {
        return String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
    },
};
