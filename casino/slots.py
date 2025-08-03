import discord
import random
import asyncio
from fundamentals import get_balance, update_balance, get_user_lock, can_act

SLOT_SYMBOLS = (
    ["🍒"] * 10 + ["🍋"] * 7 + ["🍉"] * 5 +
    ["🍇"] * 3 + ["🔔"] * 2 + ["🍀"] * 1
)
SYMBOL_COEFFICIENTS = {
    "🍒": 2, "🍋": 3, "🍉": 4,
    "🍇": 5, "🔔": 7, "🍀": 10
}

async def slot_machine_run(interaction, bet):
    """
    Run the slot machine spin:
    - get_balance_func: async function(user_id) -> (balance, total_bet)
    - update_balance_func: async function(user_id, new_balance, bet_amount)
    """
    uid = interaction.user.id
    lock = get_user_lock(uid)
    async with lock:
        bal, _ = await get_balance(uid, interaction.user.name)
        if bet and bal < bet:
            try:
                await interaction.response.send_message(f"❌ Not enough coins! You have {bal}.", ephemeral=True)
            except discord.errors.NotFound:
                pass
            return
        
        try:
            await interaction.response.defer(ephemeral=True)
        except (discord.errors.NotFound, discord.errors.InteractionResponded):
            # Interaction already responded or expired, ignore and exit
            return
        reels = ["❓"] * 3
        embed = discord.Embed(title="🎰 Rolling...", description=" | ".join(reels), color=discord.Color.gold())
        msg = await interaction.followup.send(embed=embed, ephemeral=True)

        for i in range(3):
            await asyncio.sleep(random.uniform(0.4, 0.9))
            reels[i] = random.choice(SLOT_SYMBOLS)
            embed.description = " | ".join(reels)
            await msg.edit(embed=embed)

        await asyncio.sleep(0.3)
        if reels[0] == reels[1] == reels[2]:
            m = SYMBOL_COEFFICIENTS[reels[0]]
            bonus = 1
            if bet == 1000:
                bonus = 4
            elif bet == 500:
                bonus = 2
            elif bet == 100:
                bonus = 1.5
            win = int(bet * m * bonus)
            newbal = bal - bet + win
            await update_balance(uid, newbal, bet)
            embed.color = discord.Color.green()
            embed.add_field(name="🎉 Win", value=f"You won {win} coins!")
        else:
            newbal = bal - bet
            await update_balance(uid, newbal, bet)
            embed.color = discord.Color.red()
            embed.add_field(name="😢 Loss", value=f"You lost {bet} coins.")
        embed.set_footer(text=f"Balance: {newbal}")
        await msg.edit(embed=embed)

# SlotView UI class with buttons
class SlotView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def common(self, interaction, bet):
        if not can_act(interaction.user.id, 1.5):
            await interaction.response.send_message("⏱️ Cooldown: wait a few seconds before spinning again!", ephemeral=True)
            return
        
        # Use bot's balance functions via attributes or injected later
        await slot_machine_run(interaction, bet)

    @discord.ui.button(label="Spin (Free)", style=discord.ButtonStyle.secondary, custom_id="slot_spin")
    async def spin(self, interaction, button): await self.common(interaction, 0)
    @discord.ui.button(label="Bet 50", style=discord.ButtonStyle.success, custom_id="bet_50")
    async def bet50(self, interaction, button): await self.common(interaction, 50)
    @discord.ui.button(label="Bet 100", style=discord.ButtonStyle.success, custom_id="bet_100")
    async def bet100(self, interaction, button): await self.common(interaction, 100)
    @discord.ui.button(label="Bet 500", style=discord.ButtonStyle.success, custom_id="bet_500")
    async def bet500(self, interaction, button): await self.common(interaction, 500)
    @discord.ui.button(label="Bet 1000", style=discord.ButtonStyle.danger, custom_id="bet_1000")
    async def bet1000(self, interaction, button): await self.common(interaction, 1000)

    @discord.ui.button(label="Check My Balance", style=discord.ButtonStyle.primary, custom_id="check_balance")
    async def check(self, interaction, button):
        bal, total = await get_balance(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(f"💰 Balance: {bal}\n🧮 Total Bet: {total}", ephemeral=True)

    @discord.ui.button(label="Show Coefficients", style=discord.ButtonStyle.secondary, custom_id="show_coeffs")
    async def coeffs(self, interaction, button):
        embed = discord.Embed(title="🎰 Coefficients", color=discord.Color.purple())
        for e, c in SYMBOL_COEFFICIENTS.items():
            chance = SLOT_SYMBOLS.count(e) / len(SLOT_SYMBOLS)
            embed.add_field(name=e, value=f"{c}× • {chance:.1%}", inline=True)
        embed.add_field(name="Additional Coefficients by Bet",
                        value="• 50 - x1\n• 100 - x1.5\n• 500 - x2\n• 1000 - x4",
                        inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

def get_slot_view():
    """
    Factory to create a SlotView with attached balance functions.
    To be called from main.py where balance/db functions are available.
    """
    view = SlotView()
<<<<<<< HEAD
=======
    # These should be assigned in main.py after importing slots
    # For example:
    # view.get_balance_func = main.get_balance
    # view.update_balance_func = main.update_balance
>>>>>>> 397f3a965a495eb1e8dd959340f7facb818e767a
    return view
