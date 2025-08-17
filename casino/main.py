import discord
from discord.ext import commands
import time
import os
from datetime import datetime
from database import init_pool, get_pool, init_db, get_balance, update_balance, get_user_lock
from slots import SlotView
from blackjack import BlackjackBetView
from wheel_of_fortune import FortuneView, embed_wheel, get_wheel_state

intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)

# Update last daily claim timestamp
async def update_last_daily_claim(user_id: int, username: str, current_time: int) -> bool:
    today = datetime.fromtimestamp(current_time).date()

    async with get_pool().acquire() as conn:
        # Insert user if not exists (Postgres syntax)
        await conn.execute(
            """
            INSERT INTO user_accounts (user_id, username, balance, total_bet, last_daily_claim)
            VALUES ($1, $2, 30000, 0, 0)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id, username
        )

        # Fetch last_daily_claim timestamp
        row = await conn.fetchrow(
            "SELECT last_daily_claim FROM user_accounts WHERE user_id = $1",
            user_id
        )

        last_claim_date = None
        if row and row['last_daily_claim'] is not None:
            last_claim_date = datetime.fromtimestamp(row['last_daily_claim']).date()

        if last_claim_date == today:
            # Already claimed today
            return False

        # Update last_daily_claim to now
        await conn.execute(
            "UPDATE user_accounts SET last_daily_claim = $1 WHERE user_id = $2",
            current_time, user_id
        )

        return True

# --- UI Views and Bot Commands ---

class CasinoHomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Persistent buttons

    @discord.ui.button(label="🎰 Go to Slot Machine", style=discord.ButtonStyle.success, custom_id="goto_slots")
    async def goto_slots(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Show slot machine UI privately
        await interaction.response.send_message(
            "🎰 **Slot Machine**\nPress a button below to spin!\nUse **Show Coefficients** to view odds.",
            view=SlotView(),
            ephemeral=True
        )
        msg = await interaction.original_response()
        slot_view = SlotView(msg)
        await msg.edit(view=slot_view)
        
    @discord.ui.button(label="🃏 Go to Blackjack", style=discord.ButtonStyle.success, custom_id="goto_blackjack")
    async def goto_blackjack(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Show Blackjack UI privately
        await interaction.response.send_message(
            "🃏 **Blackjack Game**\nHit `Hit` to draw a card, `Stand` to hold your hand.\nTry to beat the dealer without going over 21!\n-# Score a perfect 21 and earn a sweet bonus!:)",
            view=BlackjackBetView(),
            ephemeral=True
        )

    @discord.ui.button(label="🍀 Spin Fortune Wheel", style=discord.ButtonStyle.success, custom_id="goto_fortune")
    async def goto_fortune(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🍀 **Fortune Wheel**\nPress to spin and test your luck!",
            embed=embed_wheel(await get_wheel_state(interaction.user.id)),
            view=FortuneView(),
            ephemeral=True
        )
        
    
    @discord.ui.button(label="📆 Claim Daily (3000)", style=discord.ButtonStyle.secondary, custom_id="daily_reward", row=1)
    async def daily_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        uid = interaction.user.id
        lock = get_user_lock(uid)

        async with lock:
            now = int(time.time())
            success = await update_last_daily_claim(uid, interaction.user.name, now)

            if not success:
                await interaction.followup.send(
                    "🕒 You already claimed your daily reward today. Try again tomorrow!", ephemeral=True
                )
                return

            # Add 3000 coins to balance
            await update_balance(uid, 3000, 0)

            await interaction.followup.send(
                "✅ You claimed your daily reward of 3000 coins!", ephemeral=True
            )

    @discord.ui.button(label="💰 Check Balance", style=discord.ButtonStyle.primary, custom_id="check_balance_main", row = 1)
    async def check_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        bal, total = await get_balance(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(
            f"💰 Balance: {bal}\n🧮 Total Bet: {total}", ephemeral=True
        )
    
    @discord.ui.button(label="👑 Leaderboard", style=discord.ButtonStyle.primary, custom_id="top_5", row=1)
    async def leaders(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with get_pool().acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, username, balance FROM user_accounts ORDER BY balance DESC"
            )

        if not rows:
            await interaction.response.send_message("No one gambled yet :(", ephemeral=True)
            return

        leaderboard = [f"**#1 {rows[0]['username']}** - {rows[0]['balance']}$"]
        leaderboard += [f"**#{i+2}** {row['username']}" for i, row in enumerate(rows[1:5])]

        leaderboard_text = "\n".join(leaderboard)

        user_id = interaction.user.id
        user_rank = None
        for i, row in enumerate(rows):
            if row["user_id"] == user_id:
                user_rank = i + 1
                break

        embed = discord.Embed(
            title="🏆 Top 5 Leaders",
            description=leaderboard_text,
            color=discord.Color.gold()
        )

        if user_rank and user_rank > 5:
            embed.set_footer(text=f"Your rank: #{user_rank}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

persistent_home_view = None

@bot.event
async def on_ready():
    global persistent_home_view

    # Initialize the asyncpg connection pool once
    await init_pool()

    if persistent_home_view is None:  # Prevent re-creating on reconnects
        persistent_home_view = CasinoHomeView()
    bot.add_view(persistent_home_view)
    
    # Initialize the database schema after pool is ready
    await init_db()  

    await bot.tree.sync()  # Sync slash commands
    print(f"✅ {bot.user} is ready!", flush=True)

# Slash command to show the casino home screen message publicly
@bot.tree.command(name="casino", description="Open the Casino home screen")
async def casino(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=discord.Embed(title="🎮 Casino Home", description="Click buttons below to play!"),
        view=persistent_home_view,
        ephemeral=False
    )

token = os.getenv("CASINO_TOKEN")
if not token:
    raise RuntimeError("CASINO_TOKEN is not set in environment variables.")

bot.run(token)
