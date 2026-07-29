import threading
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from config import (
    DATABASE_URL,
    DEMO_STARTING_BALANCE
)


# =========================================================
# DATABASE LOCK
# =========================================================

db_lock = threading.RLock()


# =========================================================
# CONNECTION
# =========================================================

def get_connection():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    connection = psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=10
    )

    return connection


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_database():

    with db_lock:

        with get_connection() as connection:

            with connection.cursor() as cursor:

                # ---------------------------------------------
                # USERS
                # ---------------------------------------------

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (

                        id BIGSERIAL PRIMARY KEY,

                        telegram_id BIGINT UNIQUE NOT NULL,

                        username TEXT,

                        first_name TEXT,

                        demo_balance NUMERIC(18, 2)
                            NOT NULL DEFAULT 10000.00,

                        created_at TIMESTAMPTZ NOT NULL,

                        updated_at TIMESTAMPTZ NOT NULL

                    )
                """)


                # ---------------------------------------------
                # DEMO TRADES
                # ---------------------------------------------

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS demo_trades (

                        id BIGSERIAL PRIMARY KEY,

                        user_id BIGINT NOT NULL,

                        direction TEXT NOT NULL,

                        amount NUMERIC(18, 2) NOT NULL,

                        entry_price NUMERIC(24, 8) NOT NULL,

                        exit_price NUMERIC(24, 8),

                        entry_time BIGINT NOT NULL,

                        expiry_time BIGINT NOT NULL,

                        status TEXT NOT NULL
                            DEFAULT 'OPEN',

                        result TEXT,

                        profit NUMERIC(18, 2)
                            DEFAULT 0,

                        created_at TIMESTAMPTZ NOT NULL,

                        CONSTRAINT fk_demo_trades_user

                            FOREIGN KEY (user_id)

                            REFERENCES users(id)

                            ON DELETE CASCADE

                    )
                """)


                # ---------------------------------------------
                # INDEXES
                # ---------------------------------------------

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_demo_trades_user_id

                    ON demo_trades(user_id)
                """)


                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_demo_trades_status

                    ON demo_trades(status)
                """)


                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS
                    idx_demo_trades_expiry

                    ON demo_trades(expiry_time)
                """)


        print(
            "PostgreSQL database initialized."
        )


# =========================================================
# NORMALIZE USER
# =========================================================

def normalize_user(user):

    if user is None:
        return None

    user = dict(user)

    # psycopg returns PostgreSQL NUMERIC as Decimal.
    # Our existing frontend/API expects normal numbers.

    if user.get("demo_balance") is not None:

        user["demo_balance"] = float(
            user["demo_balance"]
        )

    # Convert datetime values into JSON-friendly strings.

    for field in (
        "created_at",
        "updated_at"
    ):

        if (
            field in user
            and user[field] is not None
            and hasattr(
                user[field],
                "isoformat"
            )
        ):

            user[field] = (
                user[field].isoformat()
            )

    return user


# =========================================================
# GET USER BY TELEGRAM ID
# =========================================================

def get_user_by_telegram_id(
    telegram_id
):

    with get_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE telegram_id = %s
                """,
                (
                    int(telegram_id),
                )
            )

            user = cursor.fetchone()

    return normalize_user(
        user
    )


# =========================================================
# GET USER BY INTERNAL ID
# =========================================================

def get_user_by_id(
    user_id
):

    with get_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE id = %s
                """,
                (
                    int(user_id),
                )
            )

            user = cursor.fetchone()

    return normalize_user(
        user
    )


# =========================================================
# CREATE OR UPDATE TELEGRAM USER
# =========================================================

def create_or_update_user(
    telegram_id,
    username=None,
    first_name=None
):

    telegram_id = int(
        telegram_id
    )

    now = datetime.now(
        timezone.utc
    )


    # PostgreSQL UPSERT avoids:
    #
    # SELECT
    # ↓
    # check
    # ↓
    # INSERT/UPDATE
    #
    # and is safer when multiple requests arrive together.

    with db_lock:

        with get_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO users
                    (
                        telegram_id,
                        username,
                        first_name,
                        demo_balance,
                        created_at,
                        updated_at
                    )

                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )

                    ON CONFLICT (telegram_id)

                    DO UPDATE SET

                        username =
                            EXCLUDED.username,

                        first_name =
                            EXCLUDED.first_name,

                        updated_at =
                            EXCLUDED.updated_at

                    RETURNING *
                    """,
                    (
                        telegram_id,
                        username,
                        first_name,
                        float(
                            DEMO_STARTING_BALANCE
                        ),
                        now,
                        now
                    )
                )

                user = cursor.fetchone()


    return normalize_user(
        user
    )


# =========================================================
# GET BALANCE
# =========================================================

def get_demo_balance(
    user_id
):

    with get_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT demo_balance

                FROM users

                WHERE id = %s
                """,
                (
                    int(user_id),
                )
            )

            row = cursor.fetchone()


    if row is None:
        return None


    return float(
        row["demo_balance"]
    )


# =========================================================
# UPDATE BALANCE
# =========================================================

def update_demo_balance(
    user_id,
    new_balance
):

    now = datetime.now(
        timezone.utc
    )


    with db_lock:

        with get_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    UPDATE users

                    SET
                        demo_balance = %s,
                        updated_at = %s

                    WHERE id = %s
                    """,
                    (
                        float(
                            new_balance
                        ),
                        now,
                        int(user_id)
                    )
                )

                success = (
                    cursor.rowcount > 0
                )


    return success


# =========================================================
# TEST DATABASE CONNECTION
# =========================================================

def test_connection():

    try:

        with get_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    "SELECT version()"
                )

                result = cursor.fetchone()


        print(
            "PostgreSQL connection successful."
        )

        print(
            result
        )

        return True

    except Exception as error:

        print(
            "PostgreSQL connection failed:"
        )

        print(
            error
        )

        return False


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    if test_connection():

        init_database()

        print(
            "Supabase PostgreSQL database ready."
        )