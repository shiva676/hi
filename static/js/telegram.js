// ============================================================
// TELEGRAM MINI APP
// ============================================================

const TelegramApp = {

    tg: null,

    isTelegram: false,

    user: null,


    // ========================================================
    // INITIALIZE
    // ========================================================

    init() {

        // Check whether Telegram WebApp SDK exists

        if (
            window.Telegram &&
            window.Telegram.WebApp
        ) {

            this.tg =
                window.Telegram.WebApp;


            // Tell Telegram that our Mini App is ready

            this.tg.ready();


            // Expand Mini App

            this.tg.expand();


            // Telegram provides signed initData here

            if (this.tg.initData) {

                this.isTelegram = true;

            }

        }


        console.log(
            "Telegram environment:",
            this.isTelegram
        );

    },


    // ========================================================
    // AUTHENTICATE WITH OUR BACKEND
    // ========================================================

    async authenticate() {

        let initData = "";


        if (
            this.isTelegram &&
            this.tg
        ) {

            initData =
                this.tg.initData;

        }


        try {

            const response =
                await fetch(
                    "/api/auth",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        credentials:
                            "same-origin",

                        body:
                            JSON.stringify({

                                init_data:
                                    initData

                            })
                    }
                );


            const data =
                await response.json();


            if (!response.ok) {

                throw new Error(
                    data.error ||
                    "Authentication failed."
                );

            }


            this.user =
                data.user;


            console.log(
                "Authenticated:",
                data.mode
            );


            return data.user;

        }

        catch (error) {

            console.error(
                "Authentication error:",
                error
            );


            throw error;

        }

    },


    // ========================================================
    // GET TELEGRAM USER
    // ========================================================

    getTelegramUser() {

        if (
            !this.tg ||
            !this.tg.initDataUnsafe
        ) {

            return null;

        }


        return (
            this.tg
                .initDataUnsafe
                .user || null
        );

    },


    // ========================================================
    // HAPTIC FEEDBACK
    // ========================================================

    haptic(type = "light") {

        if (
            !this.tg ||
            !this.tg.HapticFeedback
        ) {

            return;

        }


        try {

            this.tg
                .HapticFeedback
                .impactOccurred(
                    type
                );

        }

        catch (error) {

            // Haptics are optional.
        }

    },


    // ========================================================
    // SUCCESS HAPTIC
    // ========================================================

    successHaptic() {

        if (
            !this.tg ||
            !this.tg.HapticFeedback
        ) {

            return;

        }


        try {

            this.tg
                .HapticFeedback
                .notificationOccurred(
                    "success"
                );

        }

        catch (error) {

        }

    },


    // ========================================================
    // ERROR HAPTIC
    // ========================================================

    errorHaptic() {

        if (
            !this.tg ||
            !this.tg.HapticFeedback
        ) {

            return;

        }


        try {

            this.tg
                .HapticFeedback
                .notificationOccurred(
                    "error"
                );

        }

        catch (error) {

        }

    }

};


// ============================================================
// INITIALIZE IMMEDIATELY
// ============================================================

TelegramApp.init();