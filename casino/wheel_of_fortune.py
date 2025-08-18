import discord
import random
import asyncio
from database import get_pool, get_balance, update_balance, get_user_lock
from main import log  # import the logger function from main.py

wheel_of_fortune = ["x2", 500, -1000, 350, "/2", -750, 1000, -250]
active_wheel_spins = set()  # prevent spamming

def embed_wheel(i):
    def fmt(val):
        return str(val).center(5)
    desc = f"""
          {fmt('🔻')}
          {fmt('🔻')}
          {fmt('🔻')}
           {fmt(wheel_of_fortune[i%len(wheel_of_fortune)])}
             |
 {fmt(wheel_of_fortune[(i+1)%len(wheel_of_fortune)])}   \\   |   /   {fmt(wheel_of_fortune[(i+7)%len(wheel_of_fortune)])}
      \\   \\  |  /   /
       \\   \\ | /   /
  {fmt(wheel_of_fortune[(i+2)%len(wheel_of_fortune)])} ----[●]---- {fmt(wheel_of_fortune[(i+6)%len(wheel_of_fortune)])}
       /   / | \\   \\
      /   /  |  \\   \\
 {fmt(wheel_of_fortune[(i+3)%len(wheel_of_fortune)])}   /   |   \\   {fmt(wheel_of_fortune[(i+5)%len(wheel_of_fortune)])}
             |
           {fmt(wheel_of_fortune[(i+4)%len(wheel_of_fortune)])}"""

    embed = discord.Embed(title="Wheel of Fortune 🎯", description=f"```{desc}```", color=0xFFD700)
    return embed

def round_up_to_50(x: int) -> int:
    return ((x + 49) // 50) * 50

async def get_wheel_state(user_id: int) -> int:
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT wheel_state FROM user_accounts WHERE user_id = $1",
            user_id
        )
        return row['wheel_state'] if row else 0

async def update_wheel_state(user_id: int, state: int):
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE user_accounts SET wheel_state = $1 WHERE user_id = $2",
            state, user_id
        )

async def spin_wheel_logic(interaction: discord.Interaction, bet=1000, view=None):
    uid = interaction.user.id

    if uid in active_wheel_spins:
        await interaction.followup.send(
            "⚠️ You are already spinning the wheel!", ephemeral=True
        )
        await log(f"User {interaction.user} ({uid}) tried to spin while already spinning", level="WARNING")
        return
    active_wheel_spins.add(uid)

    lock = get_user_lock(uid)

    async with lock:
        bal, _ = await get_balance(uid, interaction.user.name)
        if bal < bet:
            msg = f"❌ Not enough coins! You need at least {bet}."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            await log(f"User {interaction.user} ({uid}) tried to spin but had insufficient balance: {bal} < {bet}", level="WARNING")
            active_wheel_spins.discard(uid)
            return

        wheel_state = await get_wheel_state(uid)

    await interaction.edit_original_response(embed=embed_wheel(wheel_state), view=view)
    await log(f"User {interaction.user} ({uid}) started a wheel spin with balance {bal} coins")

    full_rotations = random.randint(2, 4)
    offset = random.randint(0, len(wheel_of_fortune) - 1)
    winner = full_rotations * len(wheel_of_fortune) + offset
    final_index = (wheel_state + winner) % len(wheel_of_fortune)

    for step in range(winner+1):
        pos = (step + wheel_state) % len(wheel_of_fortune)
        delay = 0.05 + ((step / winner)**3) * 1.3
        await asyncio.sleep(delay)
        try:
            await interaction.edit_original_response(embed=embed_wheel(pos), view=view)
        except discord.errors.NotFound:
            active_wheel_spins.discard(uid)
            return

    async with lock:
        await update_wheel_state(uid, final_index)
        result = wheel_of_fortune[final_index]

        win_amount_delta = 0
        bet_amount_delta = 0

        if result == "x2":
            win_amount_delta = bal
            msg_text = f"✨ You hit `x2`! Your balance is doubled! Now you have **{bal * 2}** coins!"
        elif result == "/2":
            # round up balance to nearest 50, lose half of that
            half = bal // 2
            rounded_half = round_up_to_50(half)
            win_amount_delta = -rounded_half
            msg_text = f"➗ You hit `/2`! You lose half your coins: **{half}**."
        else:
            if result > 0:
                win_amount_delta = result
                msg_text = f"You won **{result}** coins!"
            else:
                win_amount_delta = result
                bet_amount_delta = result
                msg_text = f"You lost **{abs(result)}** coins!"

        await update_balance(uid, win_amount_delta, bet_amount_delta)
        await log(f"User {interaction.user} ({uid}) spin result: {result}, balance change: {win_amount_delta}, total bet change: {bet_amount_delta}")

    final_embed = embed_wheel(final_index)
    final_embed.add_field(name="Result", value=msg_text, inline=False)
    await interaction.edit_original_response(embed=final_embed, view=view)
    active_wheel_spins.discard(uid)

# ------------------ UI View ------------------
class FortuneView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="Spin Wheel 🎯", style=discord.ButtonStyle.success, custom_id="wheel_spin")
    async def spin(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await spin_wheel_logic(interaction, view=self)
        button.disabled = False
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Check Balance", style=discord.ButtonStyle.primary, custom_id="wheel_check")
    async def check(self, interaction, button):
        bal, total = await get_balance(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(f"💰 Balance: {bal}\n🧮 Total Bet: {total}", ephemeral=True)
        await log(f"User {interaction.user} ({interaction.user.id}) checked balance via wheel UI: {bal} coins")
