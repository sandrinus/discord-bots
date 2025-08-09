import discord
import random
import asyncio
from database import get_pool, get_balance, update_balance, get_user_lock

wheel_of_fortune = ["x2", 500, -1000, 350, "/2", -750, 1000, -250]
active_wheel_spins = set() # set to control active spins so users cannot spam

def embed_wheel(i):
    def fmt(val):
        return str(val).center(5) 
    desc = f"""
            🔻
            🔻
            🔻
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
        return row['wheel_state'] if row else 0  # default to 0 if missing

async def update_wheel_state(user_id: int, state: int):
    async with get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE user_accounts SET wheel_state = $1 WHERE user_id = $2",
            state, user_id
        )

async def spin_wheel_logic(interaction: discord.Interaction, bet=1000, view=None):
    uid = interaction.user.id

    if uid in active_wheel_spins:
        await interaction.response.send_message(
            "⚠️ You are already spinning the wheel!", ephemeral=True
        )
        return
    active_wheel_spins.add(uid)

    lock = get_user_lock(uid)

    async with lock:
        bal, _ = await get_balance(uid, interaction.user.name)
        if bal < bet:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Not enough coins! You need at least {bet}.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Not enough coins! You need at least {bet}.", ephemeral=True)
            return
        
        wheel_state = await get_wheel_state(uid)

    await interaction.edit_original_response(embed=embed_wheel(wheel_state), view=view)

    full_rotations = random.randint(2, 5)
    offset = random.randint(0, len(wheel_of_fortune) - 1)
    winner = full_rotations * len(wheel_of_fortune) + offset
    final_index = (wheel_state + winner) % len(wheel_of_fortune)

    for step in range(winner+1):
        pos = (step + wheel_state) % len(wheel_of_fortune)
        delay = 0.05 + ((step / winner)**3) * 1.5
        await asyncio.sleep(delay)
        try:
            await interaction.edit_original_response(embed=embed_wheel(pos), view=view)
        except discord.errors.NotFound:
            return

    async with lock:
        await update_wheel_state(uid, final_index)
        result = wheel_of_fortune[final_index]

        win_amount_delta = 0
        bet_amount_delta = 0

        if result == "x2":
            # double balance means add current balance (win_amount_delta)
            win_amount_delta = bal
            msg_text = f"✨ You hit `x2`! Your balance is doubled! Now you have **{bal * 2}** coins!"
        elif result == "/2":
            # round up balance to nearest 50, lose half of that
            rounded_bal = round_up_to_50(bal)
            half = rounded_bal // 2
            win_amount_delta = -half
            msg_text = f"➗ You hit `/2`! You lose half your coins: **{half}**."
        else:
            if result > 0:
                win_amount_delta = result
                msg_text = f"You won **{result}** coins!"
            else:
                win_amount_delta = result
                bet_amount_delta = result # negative amount increases total_bet by abs(value)
                msg_text = f"You lost **{abs(result)}** coins!"

        await update_balance(uid, win_amount_delta, bet_amount_delta)

    final_embed = embed_wheel(final_index)
    final_embed.add_field(name="Result", value=msg_text, inline=False)
    await interaction.edit_original_response(embed=final_embed, view=view)
    active_wheel_spins.discard(uid)


class FortuneView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="Spin Wheel 🎯", style=discord.ButtonStyle.success, custom_id="wheel_spin")
    async def spin(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable the button to prevent multiple clicks
        button.disabled = True
        await interaction.response.edit_message(view=self)  # FIRST response

        # Run the spin logic (which includes defer and animations)
        await spin_wheel_logic(interaction, view=self)

        # Re-enable the button after the spin
        button.disabled = False
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Check Balance", style=discord.ButtonStyle.primary, custom_id="wheel_check")
    async def check(self, interaction, button):
        bal, total = await get_balance(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(f"💰 Balance: {bal}\n🧮 Total Bet: {total}", ephemeral=True)

        
