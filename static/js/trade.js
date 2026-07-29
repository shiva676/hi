// ============================================================
// DEMO TRADING CONTROLLER
// ============================================================
//
// IMPORTANT:
//
// The frontend NEVER decides:
//
// - entry price
// - expiry time
// - exit price
// - WIN / LOSS
// - payout
// - actual balance
//
// It only displays values received from the Flask backend.
//
// ============================================================

const TradeManager = {

    // --------------------------------------------------------
    // State
    // --------------------------------------------------------

    activeTrade: null,

    currentBalance: 0,

    serverTimeOffset: 0,

    timerAnimationFrame: null,

    submittingTrade: false,

    resultTimeout: null,


    // ========================================================
    // INITIALIZE
    // ========================================================

    async init() {

        this.bindControls();

        await this.syncServerTime();

        await this.loadOpenTrade();

        await this.loadHistory();

    },


    // ========================================================
    // BIND UI CONTROLS
    // ========================================================

    bindControls() {

        const upButton =
            document.getElementById(
                "trade-up"
            );


        const downButton =
            document.getElementById(
                "trade-down"
            );


        const plusButton =
            document.getElementById(
                "amount-plus"
            );


        const minusButton =
            document.getElementById(
                "amount-minus"
            );


        const amountInput =
            document.getElementById(
                "trade-amount"
            );


        // ----------------------------------------------------
        // UP
        // ----------------------------------------------------

        if (upButton) {

            upButton.addEventListener(
                "click",
                () => {

                    this.openTrade(
                        "UP"
                    );

                }
            );

        }


        // ----------------------------------------------------
        // DOWN
        // ----------------------------------------------------

        if (downButton) {

            downButton.addEventListener(
                "click",
                () => {

                    this.openTrade(
                        "DOWN"
                    );

                }
            );

        }


        // ----------------------------------------------------
        // PLUS
        // ----------------------------------------------------

        if (plusButton) {

            plusButton.addEventListener(
                "click",
                () => {

                    const current =
                        this.getAmount();


                    this.setAmount(
                        current + 10
                    );

                }
            );

        }


        // ----------------------------------------------------
        // MINUS
        // ----------------------------------------------------

        if (minusButton) {

            minusButton.addEventListener(
                "click",
                () => {

                    const current =
                        this.getAmount();


                    this.setAmount(
                        Math.max(
                            1,
                            current - 10
                        )
                    );

                }
            );

        }


        // ----------------------------------------------------
        // QUICK AMOUNT BUTTONS
        // ----------------------------------------------------

        document
            .querySelectorAll(
                ".quick-amounts button"
            )
            .forEach(
                button => {

                    button.addEventListener(
                        "click",
                        () => {

                            const amount =
                                Number(
                                    button.dataset.amount
                                );


                            this.setAmount(
                                amount
                            );

                        }
                    );

                }
            );


        // ----------------------------------------------------
        // INPUT VALIDATION
        // ----------------------------------------------------

        if (amountInput) {

            amountInput.addEventListener(
                "change",
                () => {

                    let amount =
                        this.getAmount();


                    if (
                        !Number.isFinite(amount) ||
                        amount <= 0
                    ) {

                        amount = 1;

                    }


                    this.setAmount(
                        amount
                    );

                }
            );

        }

    },


    // ========================================================
    // GET INVESTMENT AMOUNT
    // ========================================================

    getAmount() {

        const input =
            document.getElementById(
                "trade-amount"
            );


        if (!input) {

            return 0;

        }


        return Number(
            input.value
        );

    },


    // ========================================================
    // SET INVESTMENT AMOUNT
    // ========================================================

    setAmount(amount) {

        const input =
            document.getElementById(
                "trade-amount"
            );


        if (!input) {

            return;

        }


        amount =
            Number(amount);


        if (!Number.isFinite(amount)) {

            return;

        }


        amount =
            Math.max(
                1,
                Math.min(
                    amount,
                    1000
                )
            );


        input.value =
            amount.toFixed(
                amount % 1 === 0
                    ? 0
                    : 2
            );

    },


    // ========================================================
    // SYNCHRONIZE SERVER TIME
    // ========================================================

    async syncServerTime() {

        try {

            // ------------------------------------------------
            // Measure request duration.
            //
            // This gives us a better approximation than simply
            // subtracting Date.now() after the response.
            // ------------------------------------------------

            const requestStarted =
                Date.now();


            const response =
                await fetch(
                    "/api/time",
                    {
                        credentials:
                            "same-origin"
                    }
                );


            const requestFinished =
                Date.now();


            if (!response.ok) {

                throw new Error(
                    "Unable to synchronize server time."
                );

            }


            const data =
                await response.json();


            const roundTripTime =

                requestFinished
                -
                requestStarted;


            const estimatedClientTimeAtServerResponse =

                requestStarted
                +
                (
                    roundTripTime / 2
                );


            this.serverTimeOffset =

                Number(
                    data.server_time
                )

                -

                estimatedClientTimeAtServerResponse;

        }

        catch (error) {

            console.warn(
                "Server time sync failed:",
                error
            );


            // Display fallback only.
            //
            // Backend settlement remains authoritative.

            this.serverTimeOffset =
                0;

        }

    },


    // ========================================================
    // ESTIMATED SERVER TIME
    // ========================================================

    getServerTime() {

        return (
            Date.now()
            +
            this.serverTimeOffset
        );

    },


    // ========================================================
    // LOAD OPEN TRADE
    // ========================================================

    async loadOpenTrade() {

        try {

            const response =
                await fetch(
                    "/api/trade/open",
                    {
                        credentials:
                            "same-origin"
                    }
                );


            if (!response.ok) {

                throw new Error(
                    "Unable to load open trade."
                );

            }


            const data =
                await response.json();


            // ------------------------------------------------
            // Resync using server_time included in response.
            // ------------------------------------------------

            if (data.server_time) {

                this.serverTimeOffset =

                    Number(
                        data.server_time
                    )

                    -

                    Date.now();

            }


            if (data.trade) {

                this.setActiveTrade(
                    data.trade
                );

            }

            else {

                this.clearActiveTrade();

            }

        }

        catch (error) {

            console.error(
                "Open trade error:",
                error
            );

        }

    },


    // ========================================================
    // OPEN TRADE
    // ========================================================

    async openTrade(direction) {

        if (
            this.submittingTrade
        ) {

            return;

        }


        if (
            this.activeTrade
        ) {

            this.showMessage(
                "Wait for your current trade to finish.",
                "error"
            );

            return;

        }


        const amount =
            this.getAmount();


        if (
            !Number.isFinite(amount) ||
            amount <= 0
        ) {

            this.showMessage(
                "Enter a valid investment amount.",
                "error"
            );

            return;

        }


        // ----------------------------------------------------
        // Client-side balance check is ONLY for UX.
        //
        // Backend checks it again authoritatively.
        // ----------------------------------------------------

        if (
            this.currentBalance > 0 &&
            amount > this.currentBalance
        ) {

            this.showMessage(
                "Insufficient demo balance.",
                "error"
            );

            return;

        }


        this.submittingTrade =
            true;


        this.setTradeButtonsDisabled(
            true
        );


        this.showMessage(
            "Opening trade..."
        );


        TelegramApp.haptic(
            "medium"
        );


        try {

            // ------------------------------------------------
            // Notice:
            //
            // We send ONLY:
            //
            // direction
            // amount
            //
            // No price.
            // No expiry.
            // No result.
            // ------------------------------------------------

            const response =
                await fetch(
                    "/api/trade",
                    {

                        method:
                            "POST",

                        credentials:
                            "same-origin",

                        headers: {

                            "Content-Type":
                                "application/json"

                        },

                        body:
                            JSON.stringify({

                                direction:
                                    direction,

                                amount:
                                    amount

                            })

                    }
                );


            const data =
                await response.json();


            if (!response.ok) {

                throw new Error(
                    data.error ||
                    "Unable to open trade."
                );

            }


            const trade =
                data.trade;


            // ------------------------------------------------
            // Use BACKEND trade object.
            // ------------------------------------------------

            this.setActiveTrade(
                trade
            );


            // Backend returns balance after stake deduction.

            if (
                trade.balance !==
                undefined
            ) {

                this.setBalance(
                    trade.balance
                );

            }


            this.showMessage(
                `${trade.direction} trade opened at ${this.formatPrice(trade.entry_price)}.`
            );


            TelegramApp.successHaptic();

        }

        catch (error) {

            console.error(
                "Trade creation error:",
                error
            );


            this.showMessage(
                error.message,
                "error"
            );


            TelegramApp.errorHaptic();


            this.setTradeButtonsDisabled(
                false
            );

        }

        finally {

            this.submittingTrade =
                false;


            if (!this.activeTrade) {

                this.setTradeButtonsDisabled(
                    false
                );

            }

        }

    },


    // ========================================================
    // SET ACTIVE TRADE
    // ========================================================

    setActiveTrade(trade) {

        if (!trade) {

            return;

        }


        this.activeTrade = {

            ...trade,

            id:
                Number(
                    trade.id
                ),

            amount:
                Number(
                    trade.amount
                ),

            entry_price:
                Number(
                    trade.entry_price
                ),

            entry_time:
                Number(
                    trade.entry_time
                ),

            expiry_time:
                Number(
                    trade.expiry_time
                ),

            direction:
                String(
                    trade.direction
                ).toUpperCase()

        };


        // ----------------------------------------------------
        // Show active trade panel
        // ----------------------------------------------------

        const panel =
            document.getElementById(
                "active-trade"
            );


        if (panel) {

            panel.classList.remove(
                "hidden"
            );

        }


        // Hide old result.

        this.hideResult();


        // ----------------------------------------------------
        // Direction
        // ----------------------------------------------------

        const directionElement =
            document.getElementById(
                "active-direction"
            );


        if (directionElement) {

            directionElement.textContent =
                this.activeTrade.direction;


            if (
                this.activeTrade.direction
                === "UP"
            ) {

                directionElement.style.color =
                    "#00c087";


                directionElement.style.background =
                    "rgba(0, 192, 135, 0.12)";

            }

            else {

                directionElement.style.color =
                    "#f6465d";


                directionElement.style.background =
                    "rgba(246, 70, 93, 0.12)";

            }

        }


        // ----------------------------------------------------
        // Investment
        // ----------------------------------------------------

        this.setText(
            "active-amount",
            this.formatMoney(
                this.activeTrade.amount
            )
        );


        // ----------------------------------------------------
        // Entry
        // ----------------------------------------------------

        this.setText(
            "active-entry",
            this.formatPrice(
                this.activeTrade.entry_price
            )
        );


        // ----------------------------------------------------
        // Current
        // ----------------------------------------------------

        const currentPrice =
            TradingChart.getCurrentPrice();


        this.setText(
            "active-current",

            currentPrice
                ? this.formatPrice(
                    currentPrice
                )
                : "--"
        );


        // ----------------------------------------------------
        // Potential profit
        //
        // DISPLAY ONLY.
        //
        // Backend remains authoritative.
        // ----------------------------------------------------

        const potentialProfit =

            this.activeTrade.amount
            *
            0.80;


        this.setText(
            "potential-profit",

            "+" +

            this.formatMoney(
                potentialProfit
            )
        );


        // ----------------------------------------------------
        // Entry line + circle
        // ----------------------------------------------------

        TradingChart.showEntry(

            this.activeTrade
                .entry_price,

            this.activeTrade
                .direction,

            this.activeTrade
                .entry_time

        );


        // ----------------------------------------------------
        // Prevent another trade
        // ----------------------------------------------------

        this.setTradeButtonsDisabled(
            true
        );


        // ----------------------------------------------------
        // Start timer renderer
        // ----------------------------------------------------

        this.startTimer();

    },


    // ========================================================
    // CLEAR ACTIVE TRADE
    // ========================================================

    clearActiveTrade() {

        this.activeTrade =
            null;


        const panel =
            document.getElementById(
                "active-trade"
            );


        if (panel) {

            panel.classList.add(
                "hidden"
            );

        }


        TradingChart.clearEntry();


        this.stopTimer();


        this.setTradeButtonsDisabled(
            false
        );

    },


    // ========================================================
    // TIMER
    // ========================================================

    startTimer() {

        this.stopTimer();


        const updateTimer =
            () => {

                if (
                    !this.activeTrade
                ) {

                    return;

                }


                const now =
                    this.getServerTime();


                const expiry =
                    Number(
                        this.activeTrade
                            .expiry_time
                    );


                const remaining =

                    Math.max(
                        0,
                        expiry - now
                    );


                this.renderTimer(
                    remaining
                );


                // ------------------------------------------------
                // IMPORTANT
                //
                // When this reaches 0, frontend does NOT:
                //
                // determine exit price
                // determine WIN
                // determine LOSS
                // update balance
                //
                // We simply wait for backend settlement.
                // ------------------------------------------------

                if (
                    remaining <= 0
                ) {

                    this.setText(
                        "trade-timer",
                        "00:00"
                    );


                    this.showMessage(
                        "Settling trade..."
                    );


                    // Keep checking backend in case WebSocket
                    // settlement event was missed.

                    this.waitForSettlement();


                    return;

                }


                this.timerAnimationFrame =
                    requestAnimationFrame(
                        updateTimer
                    );

            };


        this.timerAnimationFrame =
            requestAnimationFrame(
                updateTimer
            );

    },


    // ========================================================
    // STOP TIMER
    // ========================================================

    stopTimer() {

        if (
            this.timerAnimationFrame
        ) {

            cancelAnimationFrame(
                this.timerAnimationFrame
            );


            this.timerAnimationFrame =
                null;

        }

    },


    // ========================================================
    // RENDER TIMER
    // ========================================================

    renderTimer(
        remainingMilliseconds
    ) {

        // ----------------------------------------------------
        // Example:
        //
        // 58,421 ms -> 00:58
        //
        // We ceil so the display doesn't immediately show
        // 00:59 the instant a 60-second trade begins.
        // ----------------------------------------------------

        const totalSeconds =

            Math.ceil(
                remainingMilliseconds
                / 1000
            );


        const minutes =

            Math.floor(
                totalSeconds / 60
            );


        const seconds =

            totalSeconds % 60;


        const formatted =

            String(minutes)
                .padStart(
                    2,
                    "0"
                )

            +

            ":"

            +

            String(seconds)
                .padStart(
                    2,
                    "0"
                );


        this.setText(
            "trade-timer",
            formatted
        );

    },


    // ========================================================
    // SETTLEMENT FALLBACK
    // ========================================================

    async waitForSettlement() {

        // Prevent timer animation continuing.

        this.stopTimer();


        if (
            !this.activeTrade
        ) {

            return;

        }


        const tradeId =
            this.activeTrade.id;


        // ----------------------------------------------------
        // WebSocket should normally tell us immediately.
        //
        // But HTTP polling gives us recovery if:
        //
        // - socket disconnected
        // - mobile network switched
        // - app was backgrounded
        // ----------------------------------------------------

        for (
            let attempt = 0;
            attempt < 20;
            attempt++
        ) {

            // Trade might already have been settled
            // by WebSocket handler.

            if (
                !this.activeTrade ||
                this.activeTrade.id !== tradeId
            ) {

                return;

            }


            try {

                const response =
                    await fetch(
                        "/api/trades?limit=10",
                        {
                            credentials:
                                "same-origin"
                        }
                    );


                if (response.ok) {

                    const data =
                        await response.json();


                    const settled =
                        data.trades.find(
                            trade =>

                                Number(
                                    trade.id
                                )
                                === tradeId

                                &&

                                trade.status
                                !== "OPEN"
                        );


                    if (settled) {

                        await this.handleSettledTrade(
                            settled
                        );


                        return;

                    }

                }

            }

            catch (error) {

                console.warn(
                    "Settlement check failed:",
                    error
                );

            }


            await this.sleep(
                500
            );

        }


        // ----------------------------------------------------
        // Still no settlement.
        //
        // Don't invent a result.
        // ----------------------------------------------------

        if (
            this.activeTrade &&
            this.activeTrade.id
            === tradeId
        ) {

            this.showMessage(
                "Waiting for market settlement..."
            );


            // Try again later.

            setTimeout(
                () => {

                    if (
                        this.activeTrade &&
                        this.activeTrade.id
                        === tradeId
                    ) {

                        this.waitForSettlement();

                    }

                },
                2000
            );

        }

    },


    // ========================================================
    // REALTIME MARKET PRICE
    // ========================================================

    onMarketPrice(
        price,
        marketTime
    ) {

        if (
            !this.activeTrade
        ) {

            return;

        }


        this.setText(
            "active-current",
            this.formatPrice(
                price
            )
        );


        // ----------------------------------------------------
        // Optional live visual indication.
        //
        // This is NOT the final trade result.
        // ----------------------------------------------------

        const currentElement =
            document.getElementById(
                "active-current"
            );


        if (!currentElement) {

            return;

        }


        const entry =
            Number(
                this.activeTrade
                    .entry_price
            );


        const current =
            Number(
                price
            );


        let currentlyWinning =
            false;


        if (
            this.activeTrade.direction
            === "UP"
        ) {

            currentlyWinning =
                current > entry;

        }

        else {

            currentlyWinning =
                current < entry;

        }


        if (
            current === entry
        ) {

            currentElement.style.color =
                "#f4f6f8";

        }

        else if (
            currentlyWinning
        ) {

            currentElement.style.color =
                "#00c087";

        }

        else {

            currentElement.style.color =
                "#f6465d";

        }

    },


    // ========================================================
    // WEBSOCKET: TRADE OPENED
    // ========================================================

    handleTradeOpenedSocket(
        data
    ) {

        if (
            !data ||
            !data.trade
        ) {

            return;

        }


        // ----------------------------------------------------
        // For our current single-user prototype.
        //
        // Production websocket routing will ensure users only
        // receive their own private trade events.
        // ----------------------------------------------------

        if (
            this.activeTrade &&
            Number(
                this.activeTrade.id
            )
            ===
            Number(
                data.trade.id
            )
        ) {

            return;

        }


        this.setActiveTrade(
            data.trade
        );

    },


    // ========================================================
    // WEBSOCKET: TRADE SETTLED
    // ========================================================

    async handleTradeSettledSocket(
        data
    ) {

        if (
            !data ||
            !data.trade
        ) {

            return;

        }


        if (
            this.activeTrade &&
            Number(
                this.activeTrade.id
            )
            !==
            Number(
                data.trade.id
            )
        ) {

            return;

        }


        await this.handleSettledTrade(
            data.trade
        );

    },


    // ========================================================
    // HANDLE FINAL RESULT
    // ========================================================

    async handleSettledTrade(
        trade
    ) {

        if (!trade) {

            return;

        }


        // ----------------------------------------------------
        // Save values before clearing active trade.
        // ----------------------------------------------------

        const result =
            String(
                trade.result || ""
            ).toUpperCase();


        const profit =
            Number(
                trade.profit || 0
            );


        const entryPrice =
            Number(
                trade.entry_price
            );


        const exitPrice =
            Number(
                trade.exit_price
            );


        // ----------------------------------------------------
        // Clear active trade UI
        // ----------------------------------------------------

        this.clearActiveTrade();


        // ----------------------------------------------------
        // Balance
        //
        // WebSocket settlement contains final balance.
        // HTTP history fallback may not.
        // ----------------------------------------------------

        if (
            trade.balance !==
            undefined
        ) {

            this.setBalance(
                trade.balance
            );

        }

        else {

            await this.refreshBalance();

        }


        // ----------------------------------------------------
        // Show backend result
        // ----------------------------------------------------

        this.showResult({

            result:
                result,

            profit:
                profit,

            entryPrice:
                entryPrice,

            exitPrice:
                exitPrice

        });


        // ----------------------------------------------------
        // Feedback
        // ----------------------------------------------------

        if (
            result === "WIN"
        ) {

            TelegramApp.successHaptic();

        }

        else if (
            result === "LOSS"
        ) {

            TelegramApp.errorHaptic();

        }


        // ----------------------------------------------------
        // Refresh history
        // ----------------------------------------------------

        await this.loadHistory();


        this.hideMessage();

    },


    // ========================================================
    // SHOW RESULT
    // ========================================================

    showResult({
        result,
        profit,
        entryPrice,
        exitPrice
    }) {

        clearTimeout(
            this.resultTimeout
        );


        const panel =
            document.getElementById(
                "trade-result"
            );


        const title =
            document.getElementById(
                "result-title"
            );


        const profitElement =
            document.getElementById(
                "result-profit"
            );


        const description =
            document.getElementById(
                "result-description"
            );


        if (
            !panel ||
            !title ||
            !profitElement ||
            !description
        ) {

            return;

        }


        panel.classList.remove(
            "hidden"
        );


        title.textContent =
            result;


        // ----------------------------------------------------
        // WIN
        // ----------------------------------------------------

        if (
            result === "WIN"
        ) {

            title.style.color =
                "#00c087";


            profitElement.style.color =
                "#00c087";


            profitElement.textContent =

                "+"

                +

                this.formatMoney(
                    Math.abs(profit)
                );

        }


        // ----------------------------------------------------
        // LOSS
        // ----------------------------------------------------

        else if (
            result === "LOSS"
        ) {

            title.style.color =
                "#f6465d";


            profitElement.style.color =
                "#f6465d";


            profitElement.textContent =

                "-"

                +

                this.formatMoney(
                    Math.abs(profit)
                );

        }


        // ----------------------------------------------------
        // DRAW
        // ----------------------------------------------------

        else {

            title.style.color =
                "#8c96a5";


            profitElement.style.color =
                "#8c96a5";


            profitElement.textContent =
                "$0.00";

        }


        description.textContent =

            `${this.formatPrice(entryPrice)} → ${this.formatPrice(exitPrice)}`;


        // ----------------------------------------------------
        // Keep result visible for 6 seconds.
        // ----------------------------------------------------

        this.resultTimeout =
            setTimeout(
                () => {

                    this.hideResult();

                },
                6000
            );

    },


    // ========================================================
    // HIDE RESULT
    // ========================================================

    hideResult() {

        const panel =
            document.getElementById(
                "trade-result"
            );


        if (panel) {

            panel.classList.add(
                "hidden"
            );

        }

    },


    // ========================================================
    // REFRESH BALANCE
    // ========================================================

    async refreshBalance() {

        try {

            const response =
                await fetch(
                    "/api/me",
                    {
                        credentials:
                            "same-origin"
                    }
                );


            if (!response.ok) {

                return;

            }


            const data =
                await response.json();


            if (
                data.user &&
                data.user.demo_balance
                !== undefined
            ) {

                this.setBalance(
                    data.user.demo_balance
                );

            }

        }

        catch (error) {

            console.warn(
                "Balance refresh failed:",
                error
            );

        }

    },


    // ========================================================
    // SET BALANCE
    // ========================================================

    setBalance(balance) {

        balance =
            Number(
                balance
            );


        if (
            !Number.isFinite(balance)
        ) {

            return;

        }


        this.currentBalance =
            balance;


        this.setText(
            "demo-balance",
            this.formatMoney(
                balance
            )
        );

    },


    // ========================================================
    // LOAD TRADE HISTORY
    // ========================================================

    async loadHistory() {

        try {

            const response =
                await fetch(
                    "/api/trades?limit=10",
                    {
                        credentials:
                            "same-origin"
                    }
                );


            if (!response.ok) {

                return;

            }


            const data =
                await response.json();


            this.renderHistory(
                data.trades || []
            );

        }

        catch (error) {

            console.warn(
                "History load failed:",
                error
            );

        }

    },


    // ========================================================
    // RENDER HISTORY
    // ========================================================

    renderHistory(
        trades
    ) {

        const container =
            document.getElementById(
                "trade-history"
            );


        if (!container) {

            return;

        }


        // Only completed trades.

        const completed =
            trades.filter(
                trade =>

                    trade.status
                    !== "OPEN"
            );


        if (
            completed.length === 0
        ) {

            container.innerHTML = `

                <div class="empty-history">

                    <div class="empty-history-title">
                        No trades yet
                    </div>

                    <div class="empty-history-text">
                        Your completed trades will appear here.
                    </div>

                </div>

            `;


            return;

        }


        container.innerHTML = "";


        completed.forEach(
            trade => {

                const direction =
                    String(
                        trade.direction
                    ).toUpperCase();


                const result =
                    String(
                        trade.result
                    ).toUpperCase();


                const amount =
                    Number(
                        trade.amount
                    );


                const profit =
                    Number(
                        trade.profit || 0
                    );


                const item =
                    document.createElement(
                        "div"
                    );


                item.className =
                    "history-item";


                // ------------------------------------------------
                // Direction
                // ------------------------------------------------

                const directionClass =

                    direction === "UP"

                        ? "up"
                        : "down";


                const directionArrow =

                    direction === "UP"

                        ? "↑"
                        : "↓";


                // ------------------------------------------------
                // Result
                // ------------------------------------------------

                const resultClass =

                    result === "WIN"

                        ? "win"

                        : result === "LOSS"

                            ? "loss"
                            : "draw";


                let profitText;


                if (
                    result === "WIN"
                ) {

                    profitText =

                        "+"

                        +

                        this.formatMoney(
                            Math.abs(profit)
                        );

                }

                else if (
                    result === "LOSS"
                ) {

                    profitText =

                        "-"

                        +

                        this.formatMoney(
                            Math.abs(profit)
                        );

                }

                else {

                    profitText =
                        "$0.00";

                }


                // ------------------------------------------------
                // Build item
                // ------------------------------------------------

                item.innerHTML = `

                    <div class="history-left">

                        <div
                            class="history-direction ${directionClass}"
                        >
                            ${directionArrow}
                        </div>


                        <div>

                            <div class="history-symbol">
                                BTC / USDT · ${direction}
                            </div>

                            <div class="history-info">
                                ${this.formatMoney(amount)}
                                ·
                                ${this.formatPrice(trade.entry_price)}
                                →
                                ${this.formatPrice(trade.exit_price)}
                            </div>

                        </div>

                    </div>


                    <div class="history-right">

                        <div
                            class="history-result ${resultClass}"
                        >
                            ${result}
                        </div>

                        <div class="history-profit">
                            ${profitText}
                        </div>

                    </div>

                `;


                container.appendChild(
                    item
                );

            }
        );

    },


    // ========================================================
    // TRADE BUTTON STATE
    // ========================================================

    setTradeButtonsDisabled(
        disabled
    ) {

        const up =
            document.getElementById(
                "trade-up"
            );


        const down =
            document.getElementById(
                "trade-down"
            );


        if (up) {

            up.disabled =
                disabled;

        }


        if (down) {

            down.disabled =
                disabled;

        }

    },


    // ========================================================
    // MESSAGE
    // ========================================================

    showMessage(
        message,
        type = "normal"
    ) {

        const element =
            document.getElementById(
                "trade-message"
            );


        if (!element) {

            return;

        }


        element.textContent =
            message;


        element.classList.remove(
            "hidden"
        );


        if (
            type === "error"
        ) {

            element.style.color =
                "#f6465d";

        }

        else {

            element.style.color =
                "#8c96a5";

        }

    },


    hideMessage() {

        const element =
            document.getElementById(
                "trade-message"
            );


        if (element) {

            element.classList.add(
                "hidden"
            );

        }

    },


    // ========================================================
    // FORMAT MONEY
    // ========================================================

    formatMoney(value) {

        value =
            Number(
                value
            );


        if (
            !Number.isFinite(value)
        ) {

            return "$0.00";

        }


        return (

            "$"

            +

            value.toLocaleString(
                "en-US",
                {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                }
            )

        );

    },


    // ========================================================
    // FORMAT BTC PRICE
    // ========================================================

    formatPrice(value) {

        value =
            Number(
                value
            );


        if (
            !Number.isFinite(value)
        ) {

            return "--";

        }


        return (

            "$"

            +

            value.toLocaleString(
                "en-US",
                {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                }
            )

        );

    },


    // ========================================================
    // TEXT HELPER
    // ========================================================

    setText(
        id,
        value
    ) {

        const element =
            document.getElementById(
                id
            );


        if (element) {

            element.textContent =
                value;

        }

    },


    // ========================================================
    // SLEEP
    // ========================================================

    sleep(milliseconds) {

        return new Promise(
            resolve =>

                setTimeout(
                    resolve,
                    milliseconds
                )
        );

    }

};


// ============================================================
// EVENTS FROM chart.js
// ============================================================

// Realtime BTC price

window.onMarketPriceUpdate =
    function(
        price,
        marketTime
    ) {

        TradeManager.onMarketPrice(
            price,
            marketTime
        );

    };


// Backend says a trade opened

window.onTradeOpenedSocket =
    function(data) {

        TradeManager
            .handleTradeOpenedSocket(
                data
            );

    };


// Backend says a trade settled

window.onTradeSettledSocket =
    function(data) {

        TradeManager
            .handleTradeSettledSocket(
                data
            );

    };