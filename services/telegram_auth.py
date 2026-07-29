import hashlib
import hmac
import json
import time

from urllib.parse import parse_qsl

from config import BOT_TOKEN


# ============================================================
# TELEGRAM AUTHENTICATION
# ============================================================

class TelegramAuth:

    def __init__(self):

        # Telegram initData should not be accepted forever.
        # 24 hours is fine for our prototype.
        self.max_auth_age = 86400


    # ========================================================
    # VERIFY TELEGRAM INIT DATA
    # ========================================================

    def verify_init_data(
        self,
        init_data
    ):

        """
        Verify Telegram Mini App initData.

        Returns:

        {
            "success": True,
            "user": {...}
        }

        or

        {
            "success": False,
            "error": "..."
        }
        """

        if not init_data:

            return {
                "success": False,
                "error": "Missing Telegram initData."
            }


        if not BOT_TOKEN:

            return {
                "success": False,
                "error": "Telegram bot token is not configured."
            }


        try:

            # ------------------------------------------------
            # Parse query string
            # ------------------------------------------------

            parsed_data = dict(
                parse_qsl(
                    init_data,
                    keep_blank_values=True
                )
            )


            received_hash = (
                parsed_data.pop(
                    "hash",
                    None
                )
            )


            if not received_hash:

                return {
                    "success": False,
                    "error": "Telegram hash is missing."
                }


            # ------------------------------------------------
            # Build Telegram data-check-string
            # ------------------------------------------------

            data_check_string = "\n".join(

                f"{key}={value}"

                for key, value
                in sorted(
                    parsed_data.items()
                )

            )


            # ------------------------------------------------
            # Generate secret key
            #
            # Telegram Mini Apps validation:
            #
            # secret_key =
            # HMAC_SHA256(
            #     key="WebAppData",
            #     msg=BOT_TOKEN
            # )
            # ------------------------------------------------

            secret_key = hmac.new(

                b"WebAppData",

                BOT_TOKEN.encode(
                    "utf-8"
                ),

                hashlib.sha256

            ).digest()


            # ------------------------------------------------
            # Calculate expected hash
            # ------------------------------------------------

            calculated_hash = hmac.new(

                secret_key,

                data_check_string.encode(
                    "utf-8"
                ),

                hashlib.sha256

            ).hexdigest()


            # ------------------------------------------------
            # Constant-time comparison
            # ------------------------------------------------

            if not hmac.compare_digest(
                calculated_hash,
                received_hash
            ):

                return {
                    "success": False,
                    "error": "Invalid Telegram signature."
                }


            # ------------------------------------------------
            # Validate auth_date
            # ------------------------------------------------

            auth_date = parsed_data.get(
                "auth_date"
            )


            if not auth_date:

                return {
                    "success": False,
                    "error": "Telegram auth date is missing."
                }


            try:

                auth_date = int(
                    auth_date
                )

            except ValueError:

                return {
                    "success": False,
                    "error": "Invalid Telegram auth date."
                }


            current_time = int(
                time.time()
            )


            age = (
                current_time -
                auth_date
            )


            if age < 0:

                return {
                    "success": False,
                    "error": "Invalid Telegram authentication time."
                }


            if age > self.max_auth_age:

                return {
                    "success": False,
                    "error": "Telegram authentication has expired."
                }


            # ------------------------------------------------
            # Extract Telegram user
            # ------------------------------------------------

            user_json = (
                parsed_data.get(
                    "user"
                )
            )


            if not user_json:

                return {
                    "success": False,
                    "error": "Telegram user data is missing."
                }


            try:

                telegram_user = (
                    json.loads(
                        user_json
                    )
                )

            except json.JSONDecodeError:

                return {
                    "success": False,
                    "error": "Invalid Telegram user data."
                }


            # ------------------------------------------------
            # Telegram ID is mandatory
            # ------------------------------------------------

            telegram_id = (
                telegram_user.get(
                    "id"
                )
            )


            if telegram_id is None:

                return {
                    "success": False,
                    "error": "Telegram user ID is missing."
                }


            # ------------------------------------------------
            # Return only fields we need
            # ------------------------------------------------

            user = {

                "telegram_id":
                    int(
                        telegram_id
                    ),

                "username":
                    telegram_user.get(
                        "username"
                    ),

                "first_name":
                    telegram_user.get(
                        "first_name"
                    ),

                "last_name":
                    telegram_user.get(
                        "last_name"
                    ),

                "language_code":
                    telegram_user.get(
                        "language_code"
                    )

            }


            return {
                "success": True,
                "user": user
            }


        except Exception as error:

            print(
                "Telegram authentication error:",
                error
            )


            return {
                "success": False,
                "error": "Telegram authentication failed."
            }


# ============================================================
# GLOBAL INSTANCE
# ============================================================

telegram_auth = TelegramAuth()