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

        # Logs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                filename TEXT,
                content TEXT,
                created_at BIGINT DEFAULT EXTRACT(EPOCH FROM now())
            )
        """)

# Get balance and total bet for a user
async def get_balance(user_id: int, username: str = ""):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance, total_bet FROM user_accounts WHERE user_id = $1", user_id
        )
        if row:
            if username:
                await conn.execute(
                    "UPDATE user_accounts SET username = $1 WHERE user_id = $2", username, user_id
                )
            return (row['balance'], row['total_bet'])
        
        # Insert new user with default balance
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

