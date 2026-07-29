// Multiple-trade UI compatibility layer.
// The backend remains authoritative for balance, entry, expiry and settlement.

(function () {
    if (typeof TradeManager === "undefined") return;

    // Keep UP/DOWN available while another position is open.
    const originalDisable = TradeManager.setTradeButtonsDisabled.bind(TradeManager);
    TradeManager.setTradeButtonsDisabled = function (disabled) {
        // Only lock during the actual POST request, not for the full 60-second trade.
        originalDisable(Boolean(disabled && this.submittingTrade));
    };

    TradeManager.openTrade = async function (direction) {
        if (this.submittingTrade) return;

        const amount = this.getAmount();
        if (!Number.isFinite(amount) || amount <= 0) {
            this.showMessage("Enter a valid investment amount.", "error");
            return;
        }
        if (this.currentBalance > 0 && amount > this.currentBalance) {
            this.showMessage("Insufficient demo balance.", "error");
            return;
        }

        this.submittingTrade = true;
        this.setTradeButtonsDisabled(true);
        this.showMessage("Opening trade...");
        TelegramApp.haptic("medium");

        try {
            const response = await fetch("/api/trade", {
                method: "POST",
                credentials: "same-origin",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({direction, amount})
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Unable to open trade.");

            const trade = data.trade;
            // Existing panel shows the newest position. Older positions remain
            // active and are independently settled by the backend/database.
            this.setActiveTrade(trade);
            if (trade.balance !== undefined) this.setBalance(trade.balance);
            this.showMessage(`${trade.direction} trade #${trade.id} opened at ${this.formatPrice(trade.entry_price)}.`);
            TelegramApp.successHaptic();
        } catch (error) {
            console.error("Trade creation error:", error);
            this.showMessage(error.message, "error");
            TelegramApp.errorHaptic();
        } finally {
            this.submittingTrade = false;
            originalDisable(false);
        }
    };

    // setActiveTrade in the original single-trade UI disables the buttons.
    // Re-enable them immediately after rendering the newest position.
    const originalSetActive = TradeManager.setActiveTrade.bind(TradeManager);
    TradeManager.setActiveTrade = function (trade) {
        originalSetActive(trade);
        originalDisable(false);
    };

    console.log("Multiple-trade frontend enabled.");
})();
