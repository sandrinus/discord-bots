import discord
import random
import asyncio
from database import get_balance, update_balance_atomic, can_act

SLOT_SYMBOLS = (
    ["🍒"] * 10 + ["🍋"] * 7 + ["🍉"] * 5 +
    ["🍇"] * 3 + ["🔔"] * 2 + ["🍀"] * 1
)
SYMBOL_COEFFICIENTS = {
    "🍒": 2, "🍋": 3, "🍉": 4,
    "🍇": 5, "🔔": 7, "🍀": 10
}

async def slot_machine_run(msg, bet, uid, username):
    reels = ["❓"] * 3
    embed = discord.Embed(title="🎰 Rolling...", description=" | ".join(reels), color=discord.Color.gold())
    await msg.edit(embed=embed)

    for i in range(3):
        await asyncio.sleep(random.uniform(0.4, 0.9))
        reels[i] = random.choice(SLOT_SYMBOLS)
        embed.description = " | ".join(reels)
        await msg.edit(embed=embed)

    result = (reels[0] == reels[1] == reels[2])
    bal, _ = await get_balance(uid, username)
    if bet and bal < bet:
        embed.color = discord.Color.red()
        embed.add_field(name="❌ Error", value=f"Not enough coins! You have {bal}.")
    else:
        if result:
            m = SYMBOL_COEFFICIENTS[reels[0]]
            bonus = 1
            if bet == 1000:
                bonus = 4
            elif bet == 500:
                bonus = 2
            elif bet == 100:
                bonus = 1.5
            win = int(bet * m * bonus)
            net_change = win - bet  # net gain
        else:
            win = 0
            net_change = -bet  # net loss
    
        # Atomically update balance, ensuring no overdraft
        success = await update_balance_atomic(uid, net_change, bet)
        if not success:
            # The balance check above might be stale due to concurrent spins
            embed.color = discord.Color.red()
            embed.add_field(name="❌ Error", value="Balance changed during spin, insufficient funds.")
        else:
            if win > 0 or (result and win==bet==0):
                embed.color = discord.Color.green()
                embed.add_field(name="🎉 Win", value=f"You won {win} coins!")
            else:
                embed.color = discord.Color.red()
                embed.add_field(name="😢 Loss", value=f"You lost {bet} coins.")

    # Fetch updated balance to show in footer
    bal, _ = await get_balance(uid, username)
    embed.set_footer(text=f"Balance: {bal}")
    await msg.edit(embed=embed)

# SlotView UI class with buttons
class SlotView(discord.ui.View):
    def __init__(self, msg=None):
        super().__init__(timeout=60)
        self.msg = msg  # store original ephemeral message

    async def common(self, interaction, bet):
        if not can_act(interaction.user.id, 0.5):
            await interaction.response.send_message(
                "⏱️ Cooldown: wait a few seconds before spinning again!", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        if self.msg:
            # Replace original message with animation
            embed = discord.Embed(
                title="🎰 Rolling...",
                description=" | ".join(["❓"] * 3),
                color=discord.Color.gold()
            )
            await self.msg.edit(content=None, embed=embed, view=None)

            # Run animation asynchronously
            asyncio.create_task(
                slot_machine_run(self.msg, bet, interaction.user.id, interaction.user.name)
            )

        # Spawn new ephemeral message and get its message object
        new_msg = await interaction.followup.send(
            "🎰 Ready for another spin?", view=SlotView(), ephemeral=True, wait=True
        )
        new_buttons = SlotView(new_msg)
        await new_msg.edit(view=new_buttons)

    @discord.ui.button(label="Spin (Free)", style=discord.ButtonStyle.secondary, custom_id="slot_spin")
    async def spin(self, interaction, button: discord.ui.Button): await self.common(interaction, 0)
    @discord.ui.button(label="Bet 50", style=discord.ButtonStyle.success, custom_id="bet_50")
    async def bet50(self, interaction, button: discord.ui.Button): await self.common(interaction, 50)
    @discord.ui.button(label="Bet 100", style=discord.ButtonStyle.success, custom_id="bet_100")
    async def bet100(self, interaction, button: discord.ui.Button): await self.common(interaction, 100)
    @discord.ui.button(label="Bet 500", style=discord.ButtonStyle.success, custom_id="bet_500")
    async def bet500(self, interaction, button: discord.ui.Button): await self.common(interaction, 500)
    @discord.ui.button(label="Bet 1000", style=discord.ButtonStyle.danger, custom_id="bet_1000")
    async def bet1000(self, interaction, button: discord.ui.Button): await self.common(interaction, 1000)

    @discord.ui.button(label="Check My Balance", style=discord.ButtonStyle.primary, custom_id="check_balance")
    async def check(self, interaction, button: discord.ui.Button):
        bal, total = await get_balance(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(f"💰 Balance: {bal}\n🧮 Total Bet: {total}", ephemeral=True)

    @discord.ui.button(label="Show Coefficients", style=discord.ButtonStyle.secondary, custom_id="show_coeffs")
    async def coeffs(self, interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🎰 Coefficients", color=discord.Color.purple())
        for e, c in SYMBOL_COEFFICIENTS.items():
            chance = SLOT_SYMBOLS.count(e) / len(SLOT_SYMBOLS)
            embed.add_field(name=e, value=f"{c}× • {chance:.1%}", inline=True)
        embed.add_field(name="Additional Coefficients by Bet",
                        value="• 50 - x1\n• 100 - x1.5\n• 500 - x2\n• 1000 - x4",
                        inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
