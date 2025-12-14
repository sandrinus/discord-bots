from json import dumps
from database import get_pool

async def db_log(
    user_id: int,
    username: str,
    source: str,
    action: str,
    bet_amount: int,
    delta: int,
    balance_after: int,
    total_bet_after: int,
    metadata: dict = None
):
    """Log a user action to the logs table."""
    if metadata is None:
        metadata = {}

    async with get_pool().acquire() as conn:
        await conn.execute("""
            INSERT INTO logs (user_id, username, source, action, bet_amount, delta, balance_after, total_bet_after, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, user_id, username, source, action, bet_amount, delta, balance_after, total_bet_after, dumps(metadata))
    