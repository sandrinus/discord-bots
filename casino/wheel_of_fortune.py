import discord
import random
import asyncio
import aiosqlite
from fundamentals import get_balance, update_balance, get_user_lock, can_act, DB_PATH

wheel_of_fortune = ["x2", 500, -1000, 350, "/2", -750, 1000, -250]

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

async def get_wheel_state(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT wheel_state FROM Users_Balance WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0  # default to 0 if missing

async def update_wheel_state(user_id: int, state: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE Users_Balance SET wheel_state = ? WHERE user_id = ?", (state, user_id))
        await db.commit()

async def spin_wheel_logic(interaction: discord.Interaction, bet=1000, view=None):
    uid = interaction.user.id
    lock = get_user_lock(uid)

    async with lock:
        bal, _ = await get_balance(uid, interaction.user.name)
        if bal < bet:
            await interaction.response.send_message(f"❌ Not enough coins! You have {bal}.", ephemeral=True)
            return
        
        wheel_state = await get_wheel_state(uid)

        await interaction.edit_original_response(embed=embed_wheel(wheel_state), view=view)

    winner = random.randint(10, 30)
    final_index = (wheel_state + winner) % len(wheel_of_fortune)

    for step in range(winner+1):
        pos = (step + wheel_state) % len(wheel_of_fortune)
        delay = 0.05 + ((step / winner)**3) * 1.1
        await asyncio.sleep(delay)
        try:
            await interaction.edit_original_response(embed=embed_wheel(pos), view=view)
        except discord.errors.NotFound:
            return
            
        await update_wheel_state(uid, final_index)
        result = wheel_of_fortune[final_index]

        if result == "x2":
            new_amount = bal * 2
            await update_balance(uid, new_amount, 0)
            msg_text = f"✨ You hit `x2`! Your bet is doubled! You win **{new_amount}** coins!"
        elif result == "/2":
            if bal % 2 != 0:
                bal+=75
            new_amount = bal // 2
            await update_balance(uid, new_amount, 0)
            msg_text = f"➗ You hit `/2`! You lose half your coins: **-{bal - new_amount}** coins."
        else:
            new_amount = bal + result
            await update_balance(uid, new_amount, 0)
            outcome = "won" if result > 0 else "lost"
            msg_text = f"You {outcome} **{abs(result)}** coins!"

        final_embed = embed_wheel(final_index)
        final_embed.add_field(name="Result", value=msg_text, inline=False)

        await interaction.edit_original_response(embed=final_embed, view=view)


class FortuneView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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

        