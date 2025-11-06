import asyncpg
import asyncio
import time
import os

DB_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWD')}"
    f"@postgres:5432/casino"
)

# Connection pool - create once, reuse connections
pool = None

async def sync_banned_users():
    """Ensure all users in user_accounts exist in banned_users."""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO banned_users (user_id, username)
            SELECT user_id, username
            FROM user_accounts
            ON CONFLICT (user_id) DO NOTHING
        """)

async def init_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(dsn=DB_DSN)

def get_pool():
    if pool is None:
        raise RuntimeError("Database pool not initialized yet!")
    return pool

# --- Database and user balance functions ---

async def init_db():
    async with pool.acquire() as conn:
        # Create table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_accounts (
                user_id BIGINT PRIMARY KEY,
                username TEXT DEFAULT '',
                balance INTEGER DEFAULT 30000 CHECK (balance >= 0),
                total_bet INTEGER DEFAULT 0,
                last_daily_claim BIGINT DEFAULT 0,
                wheel_state SMALLINT DEFAULT 0
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id BIGINT PRIMARY KEY,
                username TEXT DEFAULT '',
                ban_status BOOL DEFAULT false,
                ban_time INT DEFAULT 0,
                banned_games TEXT[] DEFAULT '{}'
            )
        """)

        # Populate banned_users for all existing users
        await sync_banned_users()

        # Make sure balance isn't already negative from old data
        await conn.execute("UPDATE user_accounts SET balance = 0 WHERE balance < 0;")
        
        # Now ensure CHECK constraint exists
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'balance_non_negative'
                ) THEN
                    ALTER TABLE user_accounts
                    ADD CONSTRAINT balance_non_negative CHECK (balance >= 0);
                END IF;
            END
            $$;
        """)
        # Define new columns to add if missing, with their SQL definitions
        new_columns = {
            "wheel_state": "SMALLINT DEFAULT 0",
            # Add more columns here, for example:
            # "new_column_name": "TEXT DEFAULT ''",
            # "another_column": "BOOLEAN DEFAULT FALSE"
        }

        for column, definition in new_columns.items():
            col = await conn.fetchval(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='user_accounts' AND column_name='{column}'
            """)
            if col is None:
                await conn.execute(f"""
                    ALTER TABLE user_accounts ADD COLUMN {column} {definition}
                """)

async def get_users_info() -> list[dict]:
    """
    Retrieve all users from the database, sorted by balance DESC.
    Returns a list of dicts with: user_id, username, balance, total_bet
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id, username, balance, total_bet
            FROM user_accounts
            ORDER BY balance DESC
        """)
        # Convert to list of dicts
        return [
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "balance": row["balance"],
                "total_bet": row["total_bet"]
            }
            for row in rows
        ]

# Get balance and total bet for a user
async def get_balance(user_id: int, username: str = "", admin=False):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance, total_bet FROM user_accounts WHERE user_id = $1", user_id
        )
        if row:
            if username and not admin:
                await conn.execute(
                    "UPDATE user_accounts SET username = $1 WHERE user_id = $2", username, user_id
                )
            return (row['balance'], row['total_bet'])
        
        # Insert new user with default balance
        if not admin:
            await conn.execute(
                "INSERT INTO user_accounts (user_id, username, balance, total_bet) VALUES ($1, $2, 30000, 0)",
                user_id, username
            )
            return (30000, 0)

# Update balance and total bet
async def update_balance(user_id: int, win_amount: int, bet_amount: int):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE user_accounts
            SET balance = GREATEST(balance + $1, 0),
                total_bet = total_bet + $2
            WHERE user_id = $3
            RETURNING balance
            """,
            win_amount, abs(bet_amount), user_id
        )

# Update balance and total bet
async def update_balance_atomic(user_id: int, net_change: int, bet_amount: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE user_accounts
            SET balance = balance + $1, total_bet = total_bet + $2
            WHERE user_id = $3 AND balance + $1 >= 0
            RETURNING balance
            """,
            net_change, abs(bet_amount), user_id
        )
        return row is not None

# async def get_user_ban_status(user_id: int= None):
#     async with pool.acquire() as conn:
#         if user_id:
#             row = await conn.fetchrow(
#                 """
#                 SELECT ban_status, ban_time, banned_games
#                 FROM banned_users
#                 WHERE user_id = $1
#                 """,
#                 user_id
#             )
#         else:
#             row = await conn.fetchrow(
#                 """
#                 SELECT user_id, ban_status, ban_time, banned_games
#                 FROM banned_users
#                 """
#             )
#         if not row:
#             return {
#                 "exists": False,
#                 "ban_status": False,
#                 "ban_time": 0,
#                 "banned_games": []
#             }

#         return {
#             "exists": True,
#             "ban_status": row["ban_status"],
#             "ban_time": row["ban_time"],
#             "banned_games": row["banned_games"] or []
#         }
    
# async def get_all_banned_users() -> list[dict]:
#     """
#     Retrieve all users with ban_status = TRUE from banned_users table.
#     """
#     async with pool.acquire() as conn:
#         rows = await conn.fetch("""
#             SELECT user_id, username, ban_time, banned_games
#             FROM banned_users
#             WHERE ban_status = TRUE
#             ORDER BY username
#         """)
#         return [
#             {
#                 "user_id": r["user_id"],
#                 "username": r["username"],
#                 "ban_time": r["ban_time"],
#                 "banned_games": r["banned_games"] or []
#             }
#             for r in rows
#         ]

# async def ban_user_management(user_id: int, ban: bool, ban_time: int, game: str):
#     async with pool.acquire() as conn:
#         if ban:  # Apply a ban
#             if game == "{}":  # ban ALL games
#                 await conn.execute(
#                     """
#                     UPDATE banned_users
#                     SET ban_status = TRUE,
#                         ban_time = $1,
#                         banned_games = '{}'
#                     WHERE user_id = $2
#                     """,
#                     ban_time, user_id
#                 )
#             else:  # ban specific game
#                 await conn.execute(
#                     """
#                     UPDATE banned_users
#                     SET ban_status = TRUE,
#                         ban_time = $1,
#                         banned_games = (
#                             SELECT array(SELECT DISTINCT unnest(banned_users.banned_games || $2::text))
#                         )
#                     WHERE user_id = $3
#                     """,
#                     ban_time, game, user_id
#                 )
#         else:  # Remove a ban
#             if game == "{}":  # unban ALL games
#                 await conn.execute(
#                     """
#                     UPDATE banned_users
#                     SET ban_status = FALSE,
#                         ban_time = 0,
#                         banned_games = '{}'
#                     WHERE user_id = $1
#                     """,
#                     user_id
#                 )
#             else:  # unban specific game
#                 await conn.execute(
#                     """
#                     UPDATE banned_users
#                     SET banned_games = array_remove(banned_games, $1)
#                     WHERE user_id = $2
#                     """,
#                     game, user_id
#                 )
#                 # Check if array is empty → then mark ban_status as False
#                 await conn.execute(
#                     """
#                     UPDATE banned_users
#                     SET ban_status = CASE WHEN array_length(banned_games, 1) IS NULL THEN FALSE ELSE TRUE END,
#                         ban_time = CASE WHEN array_length(banned_games, 1) IS NULL THEN 0 ELSE ban_time END
#                     WHERE user_id = $1
#                     """,
#                     user_id
#                 )

# User concurrency control (same logic as before)
user_locks = {}
user_last_action = {}

def get_user_lock(uid):
    if uid not in user_locks:
        user_locks[uid] = asyncio.Lock()
    return user_locks[uid]

def can_act(uid, cooldown):
    now = time.time()
    last = user_last_action.get(uid, 0)
    if now - last < cooldown:
        return False
    user_last_action[uid] = now
    return True

