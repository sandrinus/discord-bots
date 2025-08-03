import aiosqlite
import time
import asyncio

DB_PATH = "./app/user_balance.db"

# --- Database and user balance functions ---

# Initialize DB and ensure table + columns exist
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS Users_Balance (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                balance INTEGER DEFAULT 30000,
                total_bet INTEGER DEFAULT 0,
                last_daily_claim INTEGER DEFAULT 0
            )
        """)
        
        # List of new columns to add if they don't exist
        new_columns = {
            "wheel_state": "INTEGER DEFAULT 0",
            # Add more migrations below if needed in the future:
            # "new_column_name": "TEXT DEFAULT ''"
        }

        # Fetch current schema
        cur = await db.execute("PRAGMA table_info(Users_Balance)")
        existing_columns = [row[1] for row in await cur.fetchall()]

        for column, definition in new_columns.items():
            if column not in existing_columns:
                try:
                    await db.execute(f"ALTER TABLE Users_Balance ADD COLUMN {column} {definition}")
                except aiosqlite.OperationalError as e:
                    print(f"Error adding column {column}: {e}")

        await db.commit()

# Get balance and total bet for a user
async def get_balance(user_id: int, username: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT balance, total_bet FROM Users_Balance WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row:
            if username:
                await db.execute("UPDATE Users_Balance SET username = ? WHERE user_id = ?", (username, user_id))
                await db.commit()
            return row
        # Insert new user with default balance
        await db.execute(
            "INSERT INTO Users_Balance (user_id, username, balance, total_bet) VALUES (?, ?, 30000, 0)",
            (user_id, username)
        )
        await db.commit()
        return (30000, 0)

# Update balance and total bet
async def update_balance(user_id: int, new_balance: int, bet_amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE Users_Balance SET balance = ?, total_bet = total_bet + ? WHERE user_id = ?",
            (new_balance, bet_amount, user_id)
        )
        await db.commit()

user_locks = {}
user_last_action = {}

def get_user_lock(uid):
    if uid not in user_locks:
        user_locks[uid] = asyncio.Lock()
    return user_locks[uid]

def can_act(uid, cooldown):
    now = time.time()
    last = user_last_action.get(uid, 0)
    if now - last < cooldown:  # 2 second cooldown per user
        return False
    user_last_action[uid] = now
    return True