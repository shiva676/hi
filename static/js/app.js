// ============================================================
// APPLICATION CONTROLLER
// ============================================================

const TradingApp = {

    user: null,

    initialized: false,


    // ========================================================
    // START APPLICATION
    // ========================================================

    async init() {

        if (this.initialized) {
            return;
        }

        this.initialized = true;


        console.log(
            "Starting Trading Prototype..."
        );


        try {

            // =================================================
            // STEP 1
            // TELEGRAM / DEVELOPMENT AUTHENTICATION
            // =================================================

            await this.authenticate();


            // =================================================
            // STEP 2
            // LOAD USER
            // =================================================

            await this.loadUser();


            // =================================================
            // STEP 3
            // INITIALIZE CHART
            //
            // This:
            //
            // - loads historical candles
            // - creates Lightweight Charts
            // - connects /ws
            // - starts realtime candle rendering
            // =================================================

            await TradingChart.init();


            // =================================================
            // STEP 4
            // INITIALIZE TRADING
            //
            // This:
            //
            // - binds UP/DOWN
            // - binds amount buttons
            // - syncs server time
            // - restores open trade
            // - loads trade history
            // =================================================

            await TradeManager.init();


            // =================================================
            // STEP 5
            // SYNC BALANCE
            // =================================================

            if (
                this.user &&
                this.user.demo_balance !== undefined
            ) {

                TradeManager.setBalance(
                    this.user.demo_balance
                );

            }


            console.log(
                "Trading Prototype ready."
            );

        }

        catch (error) {

            console.error(
                "Application initialization failed:",
                error
            );


            this.showFatalError(
                error.message ||
                "Unable to start trading application."
            );

        }

    },


    // ========================================================
    // AUTHENTICATE
    // ========================================================

    async authenticate() {

        console.log(
            "Authenticating..."
        );


        const user =
            await TelegramApp.authenticate();


        if (!user) {

            throw new Error(
                "Authentication failed."
            );

        }


        this.user = user;


        return user;

    },


    // ========================================================
    // LOAD USER FROM BACKEND
    // ========================================================

    async loadUser() {

        const response =
            await fetch(
                "/api/me",
                {
                    method: "GET",

                    credentials:
                        "same-origin",

                    cache:
                        "no-store"
                }
            );


        let data;


        try {

            data =
                await response.json();

        }

        catch (error) {

            throw new Error(
                "Invalid response from server."
            );

        }


        if (!response.ok) {

            throw new Error(
                data.error ||
                "Unable to load account."
            );

        }


        if (!data.user) {

            throw new Error(
                "User account was not returned."
            );

        }


        this.user =
            data.user;


        this.renderUser(
            this.user
        );


        return this.user;

    },


    // ========================================================
    // RENDER USER
    // ========================================================

    renderUser(user) {

        if (!user) {
            return;
        }


        const nameElement =
            document.getElementById(
                "user-name"
            );


        const avatarElement =
            document.getElementById(
                "user-avatar"
            );


        const balanceElement =
            document.getElementById(
                "demo-balance"
            );


        // ----------------------------------------------------
        // Display name
        // ----------------------------------------------------

        let displayName =
            "Trader";


        if (user.first_name) {

            displayName =
                user.first_name;

        }

        else if (user.username) {

            displayName =
                "@" + user.username;

        }


        if (nameElement) {

            nameElement.textContent =
                displayName;

        }


        // ----------------------------------------------------
        // Avatar letter
        // ----------------------------------------------------

        if (avatarElement) {

            let firstLetter =
                "T";


            if (
                displayName &&
                displayName.length > 0
            ) {

                firstLetter =
                    displayName
                        .replace(
                            "@",
                            ""
                        )
                        .charAt(0)
                        .toUpperCase();

            }


            avatarElement.textContent =
                firstLetter;

        }


        // ----------------------------------------------------
        // Demo balance
        // ----------------------------------------------------

        const balance =
            Number(
                user.demo_balance
            );


        if (
            balanceElement &&
            Number.isFinite(balance)
        ) {

            balanceElement.textContent =

                "$"

                +

                balance.toLocaleString(
                    "en-US",
                    {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    }
                );

        }

    },


    // ========================================================
    // REFRESH USER
    // ========================================================

    async refreshUser() {

        try {

            const response =
                await fetch(
                    "/api/me",
                    {
                        credentials:
                            "same-origin",

                        cache:
                            "no-store"
                    }
                );


            if (!response.ok) {
                return null;
            }


            const data =
                await response.json();


            if (!data.user) {
                return null;
            }


            this.user =
                data.user;


            this.renderUser(
                data.user
            );


            TradeManager.setBalance(
                data.user.demo_balance
            );


            return data.user;

        }

        catch (error) {

            console.warn(
                "User refresh failed:",
                error
            );


            return null;

        }

    },


    // ========================================================
    // PAGE VISIBILITY
    //
    // Telegram Mini Apps can be backgrounded.
    //
    // When the user returns we re-sync:
    //
    // - server time
    // - balance
    // - open trade
    // ========================================================

    async handleVisibilityChange() {

        if (
            document.visibilityState
            !== "visible"
        ) {

            return;

        }


        if (
            !this.initialized
        ) {

            return;

        }


        try {

            await TradeManager
                .syncServerTime();


            await this
                .refreshUser();


            await TradeManager
                .loadOpenTrade();


            await TradeManager
                .loadHistory();

        }

        catch (error) {

            console.warn(
                "Resume synchronization failed:",
                error
            );

        }

    },


    // ========================================================
    // FATAL ERROR UI
    // ========================================================

    showFatalError(message) {

        const marketStatus =
            document.getElementById(
                "market-status"
            );


        if (marketStatus) {

            marketStatus.textContent =
                "Unavailable";

        }


        const upButton =
            document.getElementById(
                "trade-up"
            );


        const downButton =
            document.getElementById(
                "trade-down"
            );


        if (upButton) {

            upButton.disabled =
                true;

        }


        if (downButton) {

            downButton.disabled =
                true;

        }


        const messageElement =
            document.getElementById(
                "trade-message"
            );


        if (messageElement) {

            messageElement.textContent =
                message;


            messageElement.style.color =
                "#f6465d";


            messageElement.classList.remove(
                "hidden"
            );

        }

    }

};


// ============================================================
// PAGE VISIBILITY
// ============================================================

document.addEventListener(
    "visibilitychange",
    () => {

        TradingApp
            .handleVisibilityChange();

    }
);


// ============================================================
// START WHEN HTML IS READY
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    () => {

        TradingApp.init();

    }
);