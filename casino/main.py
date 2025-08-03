import discord
from discord.ext import commands
import aiosqlite
import time
from datetime import datetime
from fundamentals import *
from slots import SlotView
from blackjack import BlackjackBetView
from wheel_of_fortune import FortuneView, embed_wheel, get_wheel_state

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Update last daily claim timestamp
async def update_last_daily_claim(user_id: int, current_time: int) -> bool:
    today = datetime.fromtimestamp(current_time).date()

    async with aiosqlite.connect(DB_PATH) as db:
        # Ensure user exists
        await db.execute(
            "INSERT OR IGNORE INTO Users_Balance (user_id, balance, total_bet, last_daily_claim) VALUES (?, 30000, 0, 0)",
            (user_id,)
        )

        # Check last claim date
        async with db.execute(
            "SELECT last_daily_claim FROM Users_Balance WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()

        last_claim_date = None
        if row and row[0] is not None:
            last_claim_date = datetime.fromtimestamp(row[0]).date()

        if last_claim_date == today:
            # Already claimed today, no update done
            return False

        # Update last_daily_claim to now
        await db.execute(
            "UPDATE Users_Balance SET last_daily_claim = ? WHERE user_id = ?",
            (current_time, user_id)
        )
        await db.commit()
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

    @discord.ui.button(label="🃏 Go to Blackjack", style=discord.ButtonStyle.success, custom_id="goto_blackjack")
    async def goto_blackjack(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Show Blackjack UI privately
        await interaction.response.send_message(
            "🃏 **Blackjack Game**\nHit `Hit` to draw a card, `Stand` to hold your hand.\nTry to beat the dealer without going over 21!",
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
            success = await update_last_daily_claim(uid, now)

            if not success:
                await interaction.followup.send(
                    "🕒 You already claimed your daily reward today. Try again tomorrow!", ephemeral=True
                )
                return

            bal, _ = await get_balance(uid, interaction.user.name)
            await update_balance(uid, bal + 3000, 0)

            await interaction.followup.send(
                "✅ You claimed your daily reward of 3000 coins!", ephemeral=True
            )

    @discord.ui.button(label="💰 Check Balance", style=discord.ButtonStyle.primary, custom_id="check_balance", row = 1)
    async def check_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        bal, total = await get_balance(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(
            f"💰 Balance: {bal}\n🧮 Total Bet: {total}", ephemeral=True
        )
    
    @discord.ui.button(label="👑 Check Leaders", style=discord.ButtonStyle.primary, custom_id="top_5", row = 1)
    async def leaders(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT username, balance FROM Users_Balance ORDER BY balance DESC LIMIT 5")
            top_rows = await cur.fetchone()
        
        if not top_rows:
            await interaction.response.send_message("No one gambled yet :(", ephemeral=True)
            return

        # Build leaderboard text
        leaderboard = "\n".join(
            [f"**#{i+1}** — {row[0]}: 💰 {int(row[1]):,}" for i, row in enumerate(top_rows)]
        )

        # Create the embed
        embed = discord.Embed(
            title="🏆 Top 5 Leaders",
            description=leaderboard,
            color=discord.Color.gold()
        )
        embed.set_footer(text="Updated in real-time")

        await interaction.response.send_message(embed=embed, ephemeral=True)
            
@bot.event
async def on_ready():
    await init_db()  # DB setup on start
    await bot.tree.sync()  # Sync slash commands
    print(f"✅ {bot.user} is ready!")

# Slash command to show the casino home screen message publicly
@bot.tree.command(name="casino", description="Open the Casino home screen")
async def casino(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=discord.Embed(title="🎮 Casino Home", description="Click buttons below to play!"),
        view=CasinoHomeView(),
        ephemeral=False
    )

bot.run("MTM5NDQ1Njk1MzkyNDYxNjM2NA.GEZt41.ErXreQ2iBCrosVKWrp_pa3AniBFpVSlUHyDMWQ")
