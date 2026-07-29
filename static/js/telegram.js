// ============================================================
// TELEGRAM MINI APP
// ============================================================

const TelegramApp = {
    tg: null,
    isTelegram: false,
    user: null,

    init() {
        if (window.Telegram && window.Telegram.WebApp) {
            this.tg = window.Telegram.WebApp;
            this.tg.ready();
            this.tg.expand();

            // SDK existence alone is not authentication. Signed initData must
            // be present and will also be verified by the Flask backend.
            if (this.tg.initData && this.tg.initData.length > 0) {
                this.isTelegram = true;
            }
        }

        console.log("Telegram environment:", this.isTelegram);

        if (!this.isTelegram) {
            this.blockOutsideTelegram();
        }
    },

    blockOutsideTelegram() {
        document.addEventListener("DOMContentLoaded", () => {
            document.body.innerHTML = `
                <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;background:#0b0f17;color:#fff;font-family:Arial,sans-serif;text-align:center;box-sizing:border-box;">
                    <div style="max-width:420px;">
                        <h2 style="margin:0 0 12px;">Open in Telegram</h2>
                        <p style="margin:0;opacity:.75;line-height:1.5;">This trading demo is available only through the Telegram Mini App. Open the bot in Telegram and use its Open App button.</p>
                    </div>
                </div>`;
        });
    },

    async authenticate() {
        if (!this.isTelegram || !this.tg || !this.tg.initData) {
            throw new Error("Open this app from Telegram to continue.");
        }

        try {
            const response = await fetch("/api/auth", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "same-origin",
                body: JSON.stringify({init_data: this.tg.initData})
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || "Authentication failed.");
            }

            this.user = data.user;
            console.log("Authenticated:", data.mode);
            return data.user;
        } catch (error) {
            console.error("Authentication error:", error);
            throw error;
        }
    },

    getTelegramUser() {
        if (!this.tg || !this.tg.initDataUnsafe) return null;
        return this.tg.initDataUnsafe.user || null;
    },

    haptic(type = "light") {
        if (!this.tg || !this.tg.HapticFeedback) return;
        try { this.tg.HapticFeedback.impactOccurred(type); } catch (error) {}
    },

    successHaptic() {
        if (!this.tg || !this.tg.HapticFeedback) return;
        try { this.tg.HapticFeedback.notificationOccurred("success"); } catch (error) {}
    },

    errorHaptic() {
        if (!this.tg || !this.tg.HapticFeedback) return;
        try { this.tg.HapticFeedback.notificationOccurred("error"); } catch (error) {}
    }
};

TelegramApp.init();
