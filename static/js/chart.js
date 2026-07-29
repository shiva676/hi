// ============================================================
// CHART SERVICE
// ============================================================

const TradingChart = {

    chart: null,

    candleSeries: null,

    socket: null,

    markerPrimitive: null,

    entryPriceLine: null,


    targetCandle: null,

    displayedCandle: null,

    currentPrice: null,

    currentMarketTime: null,


    animationStarted: false,

    reconnectTimer: null,

    manuallyClosed: false,


    // ========================================================
    // INITIALIZE CHART
    // ========================================================

    async init() {

        const chartElement =
            document.getElementById(
                "chart"
            );


        if (!chartElement) {

            console.error(
                "Chart element not found."
            );

            return;

        }


        // ----------------------------------------------------
        // Create TradingView Lightweight Chart
        // ----------------------------------------------------

        this.chart =
            LightweightCharts.createChart(
                chartElement,
                {

                    width:
                        chartElement.clientWidth,

                    height:
                        chartElement.clientHeight,


                    layout: {

                        background: {
                            color:
                                "#0b0e13"
                        },

                        textColor:
                            "#8c96a5"

                    },


                    grid: {

                        vertLines: {
                            color:
                                "#181d25"
                        },

                        horzLines: {
                            color:
                                "#181d25"
                        }

                    },


                    rightPriceScale: {

                        borderColor:
                            "#232933",

                        scaleMargins: {

                            top: 0.10,

                            bottom: 0.10

                        }

                    },


                    timeScale: {

                        borderColor:
                            "#232933",

                        timeVisible:
                            true,

                        secondsVisible:
                            false,

                        rightOffset:
                            6,

                        barSpacing:
                            8,

                        minBarSpacing:
                            3

                    },


                    crosshair: {

                        mode:
                            LightweightCharts
                                .CrosshairMode
                                .Normal

                    },


                    handleScroll: {

                        mouseWheel:
                            true,

                        pressedMouseMove:
                            true,

                        horzTouchDrag:
                            true,

                        vertTouchDrag:
                            false

                    },


                    handleScale: {

                        axisPressedMouseMove:
                            true,

                        mouseWheel:
                            true,

                        pinch:
                            true

                    }

                }
            );


        // ----------------------------------------------------
        // Candlestick series
        // ----------------------------------------------------

        this.candleSeries =
            this.chart.addSeries(

                LightweightCharts
                    .CandlestickSeries,

                {

                    upColor:
                        "#00c087",

                    downColor:
                        "#f6465d",

                    wickUpColor:
                        "#00c087",

                    wickDownColor:
                        "#f6465d",

                    borderVisible:
                        false,

                    priceLineVisible:
                        true,

                    lastValueVisible:
                        true

                }

            );


        // ----------------------------------------------------
        // Resize
        // ----------------------------------------------------

        window.addEventListener(
            "resize",
            () => {

                this.resize();

            }
        );


        // ----------------------------------------------------
        // Load history
        // ----------------------------------------------------

        await this.loadHistory();


        // ----------------------------------------------------
        // Start smooth renderer
        // ----------------------------------------------------

        this.startAnimation();


        // ----------------------------------------------------
        // Connect realtime backend
        // ----------------------------------------------------

        this.connectWebSocket();

    },


    // ========================================================
    // RESIZE
    // ========================================================

    resize() {

        const chartElement =
            document.getElementById(
                "chart"
            );


        if (
            !chartElement ||
            !this.chart
        ) {

            return;

        }


        this.chart.applyOptions({

            width:
                chartElement.clientWidth,

            height:
                chartElement.clientHeight

        });

    },


    // ========================================================
    // LOAD HISTORICAL CANDLES
    // ========================================================

    async loadHistory() {

        try {

            this.setStatus(
                "Loading chart..."
            );


            const response =
                await fetch(
                    "/api/chart",
                    {
                        credentials:
                            "same-origin"
                    }
                );


            if (!response.ok) {

                throw new Error(
                    "Unable to load chart history."
                );

            }


            const candles =
                await response.json();


            if (
                !Array.isArray(candles) ||
                candles.length === 0
            ) {

                throw new Error(
                    "No chart data received."
                );

            }


            // ------------------------------------------------
            // Ensure numeric OHLC values
            // ------------------------------------------------

            const formattedCandles =
                candles.map(
                    candle => ({

                        time:
                            Number(
                                candle.time
                            ),

                        open:
                            Number(
                                candle.open
                            ),

                        high:
                            Number(
                                candle.high
                            ),

                        low:
                            Number(
                                candle.low
                            ),

                        close:
                            Number(
                                candle.close
                            )

                    })
                );


            this.candleSeries.setData(
                formattedCandles
            );


            const lastCandle =
                formattedCandles[
                    formattedCandles.length - 1
                ];


            this.targetCandle = {
                ...lastCandle
            };


            this.displayedCandle = {
                ...lastCandle
            };


            this.currentPrice =
                lastCandle.close;


            this.updatePriceDisplay(
                this.currentPrice
            );


            this.chart
                .timeScale()
                .fitContent();


            this.setStatus(
                "Connecting..."
            );

        }

        catch (error) {

            console.error(
                "Chart history error:",
                error
            );


            this.setStatus(
                "Chart error"
            );


            throw error;

        }

    },


    // ========================================================
    // CONNECT TO OUR BACKEND WEBSOCKET
    // ========================================================

    connectWebSocket() {

        // Don't create duplicate sockets.

        if (
            this.socket &&
            (
                this.socket.readyState
                === WebSocket.OPEN ||

                this.socket.readyState
                === WebSocket.CONNECTING
            )
        ) {

            return;

        }


        clearTimeout(
            this.reconnectTimer
        );


        const protocol =

            window.location.protocol
            === "https:"

                ? "wss:"
                : "ws:";


        const websocketURL =

            protocol
            + "//"
            + window.location.host
            + "/ws";


        this.manuallyClosed =
            false;


        this.socket =
            new WebSocket(
                websocketURL
            );


        // ----------------------------------------------------
        // Connected
        // ----------------------------------------------------

        this.socket.onopen =
            () => {

                console.log(
                    "Backend WebSocket connected."
                );


                this.setStatus(
                    "Live"
                );


                // Optional keepalive

                this.startPing();

            };


        // ----------------------------------------------------
        // Message
        // ----------------------------------------------------

        this.socket.onmessage =
            event => {

                try {

                    const data =
                        JSON.parse(
                            event.data
                        );


                    this.handleSocketMessage(
                        data
                    );

                }

                catch (error) {

                    console.error(
                        "WebSocket message error:",
                        error
                    );

                }

            };


        // ----------------------------------------------------
        // Error
        // ----------------------------------------------------

        this.socket.onerror =
            error => {

                console.error(
                    "WebSocket error:",
                    error
                );


                this.setStatus(
                    "Connection error"
                );

            };


        // ----------------------------------------------------
        // Closed
        // ----------------------------------------------------

        this.socket.onclose =
            () => {

                console.log(
                    "Backend WebSocket closed."
                );


                this.stopPing();


                this.setStatus(
                    "Reconnecting..."
                );


                if (
                    !this.manuallyClosed
                ) {

                    this.reconnectTimer =
                        setTimeout(
                            () => {

                                this.connectWebSocket();

                            },
                            2000
                        );

                }

            };

    },


    // ========================================================
    // HANDLE BACKEND EVENT
    // ========================================================

    handleSocketMessage(data) {

        if (!data) {
            return;
        }


        // ----------------------------------------------------
        // Initial connection state
        // ----------------------------------------------------

        if (
            data.type ===
            "connected"
        ) {

            if (
                data.market &&
                data.market.price
                !== null
            ) {

                this.currentPrice =
                    Number(
                        data.market.price
                    );


                this.currentMarketTime =
                    data.market.price_time;


                this.updatePriceDisplay(
                    this.currentPrice
                );

            }


            if (
                data.market &&
                data.market.candle
            ) {

                this.setTargetCandle(
                    data.market.candle
                );

            }


            return;

        }


        // ----------------------------------------------------
        // Realtime market event
        // ----------------------------------------------------

        if (
            data.type ===
            "market"
        ) {

            this.currentPrice =
                Number(
                    data.price
                );


            this.currentMarketTime =
                data.price_time;


            this.updatePriceDisplay(
                this.currentPrice
            );


            if (data.candle) {

                this.setTargetCandle(
                    data.candle
                );

            }


            // trade.js will use this callback later.

            if (
                typeof window
                    .onMarketPriceUpdate
                === "function"
            ) {

                window
                    .onMarketPriceUpdate(
                        this.currentPrice,
                        this.currentMarketTime
                    );

            }


            return;

        }


        // ----------------------------------------------------
        // Trade opened
        // ----------------------------------------------------

        if (
            data.type ===
            "trade_opened"
        ) {

            if (
                typeof window
                    .onTradeOpenedSocket
                === "function"
            ) {

                window
                    .onTradeOpenedSocket(
                        data
                    );

            }


            return;

        }


        // ----------------------------------------------------
        // Trade settled
        // ----------------------------------------------------

        if (
            data.type ===
            "trade_settled"
        ) {

            if (
                typeof window
                    .onTradeSettledSocket
                === "function"
            ) {

                window
                    .onTradeSettledSocket(
                        data
                    );

            }

            return;

        }

    },


    // ========================================================
    // TARGET CANDLE
    // ========================================================

    setTargetCandle(candle) {

        const incoming = {

            time:
                Number(
                    candle.time
                ),

            open:
                Number(
                    candle.open
                ),

            high:
                Number(
                    candle.high
                ),

            low:
                Number(
                    candle.low
                ),

            close:
                Number(
                    candle.close
                )

        };


        // ----------------------------------------------------
        // First realtime candle
        // ----------------------------------------------------

        if (!this.targetCandle) {

            this.targetCandle = {
                ...incoming
            };


            this.displayedCandle = {
                ...incoming
            };


            return;

        }


        // ----------------------------------------------------
        // New minute
        // ----------------------------------------------------

        if (
            incoming.time >
            this.targetCandle.time
        ) {

            // Ensure previous candle reaches its
            // authoritative final value before moving on.

            if (this.targetCandle) {

                this.candleSeries.update({
                    ...this.targetCandle
                });

            }


            this.targetCandle = {
                ...incoming
            };


            this.displayedCandle = {
                ...incoming
            };


            return;

        }


        // ----------------------------------------------------
        // Same candle
        // ----------------------------------------------------

        if (
            incoming.time ===
            this.targetCandle.time
        ) {

            this.targetCandle = {
                ...incoming
            };

        }

    },


    // ========================================================
    // SMOOTH CHART ANIMATION
    // ========================================================

    startAnimation() {

        if (this.animationStarted) {

            return;

        }


        this.animationStarted =
            true;


        const animate = () => {

            this.renderFrame();


            requestAnimationFrame(
                animate
            );

        };


        requestAnimationFrame(
            animate
        );

    },


    // ========================================================
    // RENDER ONE FRAME
    // ========================================================

    renderFrame() {

        if (
            !this.targetCandle ||
            !this.candleSeries
        ) {

            return;

        }


        // ----------------------------------------------------
        // New candle / missing displayed state
        // ----------------------------------------------------

        if (
            !this.displayedCandle ||
            this.displayedCandle.time
            !== this.targetCandle.time
        ) {

            this.displayedCandle = {
                ...this.targetCandle
            };

        }


        // ----------------------------------------------------
        // Smooth only the visual close price
        //
        // REAL trade calculations NEVER use this.
        // ----------------------------------------------------

        const difference =

            this.targetCandle.close
            -
            this.displayedCandle.close;


        const smoothing =
            0.22;


        this.displayedCandle.close +=

            difference
            *
            smoothing;


        // Snap when extremely close.

        if (
            Math.abs(
                difference
            ) < 0.01
        ) {

            this.displayedCandle.close =
                this.targetCandle.close;

        }


        // ----------------------------------------------------
        // Open remains authoritative
        // ----------------------------------------------------

        this.displayedCandle.open =
            this.targetCandle.open;


        // ----------------------------------------------------
        // High / Low
        // ----------------------------------------------------

        this.displayedCandle.high =
            Math.max(

                this.targetCandle.high,

                this.displayedCandle.close,

                this.displayedCandle.open

            );


        this.displayedCandle.low =
            Math.min(

                this.targetCandle.low,

                this.displayedCandle.close,

                this.displayedCandle.open

            );


        // ----------------------------------------------------
        // Draw latest candle
        // ----------------------------------------------------

        this.candleSeries.update({

            time:
                this.displayedCandle.time,

            open:
                this.displayedCandle.open,

            high:
                this.displayedCandle.high,

            low:
                this.displayedCandle.low,

            close:
                this.displayedCandle.close

        });

    },


    // ========================================================
    // PRICE DISPLAY
    // ========================================================

    updatePriceDisplay(price) {

        const element =
            document.getElementById(
                "market-price"
            );


        if (!element) {
            return;
        }


        if (
            price === null ||
            price === undefined ||
            Number.isNaN(
                Number(price)
            )
        ) {

            element.textContent =
                "--";

            return;

        }


        element.textContent =

            "$" +

            Number(price)
                .toLocaleString(
                    "en-US",
                    {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    }
                );

    },


    // ========================================================
    // MARKET STATUS
    // ========================================================

    setStatus(text) {

        const element =
            document.getElementById(
                "market-status"
            );


        if (!element) {
            return;
        }


        element.innerHTML =

            '<span class="status-dot"></span>'

            +

            text;

    },


    // ========================================================
    // GET REAL LATEST PRICE
    //
    // NOTE:
    // This is useful for DISPLAY ONLY.
    //
    // Trade creation/settlement still happens on backend.
    // ========================================================

    getCurrentPrice() {

        return this.currentPrice;

    },


    // ========================================================
    // SHOW ENTRY ON CHART
    // ========================================================

    showEntry(
        entryPrice,
        direction,
        entryTime
    ) {

        if (
            !this.candleSeries
        ) {

            return;

        }


        this.clearEntry();


        entryPrice =
            Number(
                entryPrice
            );


        direction =
            String(
                direction
            ).toUpperCase();


        // ----------------------------------------------------
        // Horizontal entry line
        // ----------------------------------------------------

        this.entryPriceLine =
            this.candleSeries
                .createPriceLine({

                    price:
                        entryPrice,

                    color:
                        direction === "UP"
                            ? "#00c087"
                            : "#f6465d",

                    lineWidth:
                        2,

                    lineStyle:
                        LightweightCharts
                            .LineStyle
                            .Dashed,

                    axisLabelVisible:
                        true,

                    title:
                        "ENTRY"

                });


        // ----------------------------------------------------
        // Entry marker
        // ----------------------------------------------------

        const chartTime =

            Math.floor(
                Number(entryTime)
                / 1000
            );


        // Markers need candle-aligned time for
        // a 1-minute candle series.

        const candleTime =

            Math.floor(
                chartTime / 60
            ) * 60;


        const marker = {

            time:
                candleTime,

            position:
                direction === "UP"
                    ? "belowBar"
                    : "aboveBar",

            color:
                direction === "UP"
                    ? "#00c087"
                    : "#f6465d",

            shape:
                "circle",

            text:
                direction
                + " $"
                + entryPrice.toLocaleString(
                    "en-US",
                    {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    }
                )

        };


        // ----------------------------------------------------
        // Lightweight Charts v5 marker API
        // ----------------------------------------------------

        try {

            this.markerPrimitive =
                LightweightCharts
                    .createSeriesMarkers(

                        this.candleSeries,

                        [
                            marker
                        ]

                    );

        }

        catch (error) {

            console.warn(
                "Chart marker unavailable:",
                error
            );

        }


        // ----------------------------------------------------
        // HTML chart badge
        // ----------------------------------------------------

        const badge =
            document.getElementById(
                "chart-trade-badge"
            );


        const directionElement =
            document.getElementById(
                "chart-direction"
            );


        const priceElement =
            document.getElementById(
                "chart-entry-price"
            );


        if (badge) {

            badge.classList.remove(
                "hidden"
            );

        }


        if (directionElement) {

            directionElement.textContent =
                direction;


            directionElement.style.color =

                direction === "UP"

                    ? "#00c087"
                    : "#f6465d";

        }


        if (priceElement) {

            priceElement.textContent =

                "$" +

                entryPrice.toLocaleString(
                    "en-US",
                    {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    }
                );

        }

    },


    // ========================================================
    // CLEAR ENTRY
    // ========================================================

    clearEntry() {

        // ----------------------------------------------------
        // Remove price line
        // ----------------------------------------------------

        if (
            this.entryPriceLine &&
            this.candleSeries
        ) {

            try {

                this.candleSeries
                    .removePriceLine(
                        this.entryPriceLine
                    );

            }

            catch (error) {

            }


            this.entryPriceLine =
                null;

        }


        // ----------------------------------------------------
        // Remove marker
        // ----------------------------------------------------

        if (
            this.markerPrimitive &&
            typeof this.markerPrimitive
                .setMarkers
            === "function"
        ) {

            try {

                this.markerPrimitive
                    .setMarkers([]);

            }

            catch (error) {

            }

        }


        this.markerPrimitive =
            null;


        // ----------------------------------------------------
        // Hide badge
        // ----------------------------------------------------

        const badge =
            document.getElementById(
                "chart-trade-badge"
            );


        if (badge) {

            badge.classList.add(
                "hidden"
            );

        }

    },


    // ========================================================
    // KEEPALIVE
    // ========================================================

    startPing() {

        this.stopPing();


        this.pingInterval =
            setInterval(
                () => {

                    if (
                        this.socket &&
                        this.socket.readyState
                        === WebSocket.OPEN
                    ) {

                        try {

                            this.socket.send(
                                "ping"
                            );

                        }

                        catch (error) {

                        }

                    }

                },
                20000
            );

    },


    stopPing() {

        if (this.pingInterval) {

            clearInterval(
                this.pingInterval
            );


            this.pingInterval =
                null;

        }

    }

};