// Live BTC/USDT chart. Uses authenticated HTTP polling instead of a long-lived
// browser WebSocket so it works reliably behind Render/Gunicorn sync workers.
const TradingChart = {
    chart: null,
    candleSeries: null,
    currentPrice: null,
    currentMarketTime: null,
    pollTimer: null,
    polling: false,
    failures: 0,

    async init() {
        const el = document.getElementById("chart");
        if (!el) throw new Error("Chart element not found.");

        this.chart = LightweightCharts.createChart(el, {
            width: el.clientWidth,
            height: el.clientHeight,
            layout: {background: {color: "#0b0e13"}, textColor: "#8c96a5"},
            grid: {vertLines: {color: "#181d25"}, horzLines: {color: "#181d25"}},
            rightPriceScale: {borderColor: "#232933", scaleMargins: {top: 0.10, bottom: 0.10}},
            timeScale: {
                borderColor: "#232933",
                timeVisible: true,
                secondsVisible: false,
                rightOffset: 6,
                barSpacing: 8,
                minBarSpacing: 2,
                fixLeftEdge: false,
                fixRightEdge: false,
            },
            crosshair: {mode: LightweightCharts.CrosshairMode.Normal},
            handleScroll: {mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false},
            handleScale: {axisPressedMouseMove: true, mouseWheel: true, pinch: true},
        });

        this.candleSeries = this.chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: "#00c087", downColor: "#f6465d",
            wickUpColor: "#00c087", wickDownColor: "#f6465d",
            borderVisible: false, priceLineVisible: true, lastValueVisible: true,
        });

        window.addEventListener("resize", () => this.resize());
        await this.loadHistory();
        await this.pollMarket();
        this.pollTimer = setInterval(() => this.pollMarket(), 750);
    },

    resize() {
        const el = document.getElementById("chart");
        if (el && this.chart) this.chart.applyOptions({width: el.clientWidth, height: el.clientHeight});
    },

    async loadHistory() {
        this.setStatus("Loading chart...");
        const response = await fetch("/api/chart", {credentials: "same-origin", cache: "no-store"});
        if (!response.ok) throw new Error("Unable to load chart history.");
        const rows = await response.json();
        if (!Array.isArray(rows) || !rows.length) throw new Error("No chart data received.");

        const candles = rows.map(c => ({
            time: Number(c.time), open: Number(c.open), high: Number(c.high),
            low: Number(c.low), close: Number(c.close),
        })).filter(c => Number.isFinite(c.time) && Number.isFinite(c.close));

        this.candleSeries.setData(candles);
        const last = candles[candles.length - 1];
        this.currentPrice = last.close;
        this.updatePriceDisplay(last.close);
        this.chart.timeScale().fitContent();
        this.setStatus("Connecting...");
    },

    async pollMarket() {
        if (this.polling || document.visibilityState === "hidden") return;
        this.polling = true;
        try {
            const response = await fetch("/api/market", {credentials: "same-origin", cache: "no-store"});
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || "Market request failed");

            this.currentPrice = Number(data.price);
            this.currentMarketTime = Number(data.price_time);
            this.updatePriceDisplay(this.currentPrice);

            if (data.candle) {
                const c = data.candle;
                this.candleSeries.update({
                    time: Number(c.time), open: Number(c.open), high: Number(c.high),
                    low: Number(c.low), close: Number(c.close),
                });
            }

            this.failures = 0;
            this.setStatus(data.connected ? "Live" : "Reconnecting...");
            if (typeof TradeManager !== "undefined" && TradeManager.onMarketUpdate) {
                TradeManager.onMarketUpdate(this.currentPrice, this.currentMarketTime);
            }
        } catch (error) {
            this.failures += 1;
            console.warn("Market polling error:", error);
            this.setStatus(this.failures >= 3 ? "Market unavailable" : "Reconnecting...");
        } finally {
            this.polling = false;
        }
    },

    updatePriceDisplay(price) {
        const el = document.getElementById("market-price");
        if (el && Number.isFinite(Number(price))) {
            el.textContent = "$" + Number(price).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
    },

    setStatus(text) {
        const el = document.getElementById("market-status");
        if (!el) return;
        const dot = el.querySelector(".status-dot");
        el.innerHTML = "";
        if (dot) el.appendChild(dot);
        else {
            const span = document.createElement("span");
            span.className = "status-dot";
            el.appendChild(span);
        }
        el.appendChild(document.createTextNode(text));
    },

    showTrade(trade) {
        const badge = document.getElementById("chart-trade-badge");
        const direction = document.getElementById("chart-direction");
        const entry = document.getElementById("chart-entry-price");
        if (badge) badge.classList.remove("hidden");
        if (direction) direction.textContent = trade.direction;
        if (entry) entry.textContent = this.formatPrice(trade.entry_price);
    },

    clearTrade() {
        const badge = document.getElementById("chart-trade-badge");
        if (badge) badge.classList.add("hidden");
    },

    formatPrice(value) {
        return "$" + Number(value).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    },
};
