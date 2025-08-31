import discord
from discord.ext import commands
from database import get_users_info, get_balance, update_balance, get_user_ban_status, ban_user_management

# --- User Select Dropdown ---
class UserDatabaseSelect(discord.ui.Select):
    def __init__(self, users):
        # Add "All Users" option at the top
        options = [discord.SelectOption(label="All Users", value="all")]

        # Add up to 24 individual users (Discord allows max 25 options per dropdown)
        options += [
            discord.SelectOption(label=u['username'], value=str(u['user_id']))
            for u in users[:24]
        ]

        super().__init__(placeholder="Select a user...", min_values=1, max_values=1, options=options, custom_id="admin_user_select")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "all":
            # Show all users
            users = await get_users_info()
            if not users:
                await interaction.response.send_message("No users found.", ephemeral=True)
                return

            msg = ""
            for u in users:
                msg += f"👤 {u['username']} | 💰 {u['balance']} | 🧮 Total Bet: {u['total_bet']}\n"
                if len(msg) > 1800:  # send in chunks to avoid Discord message limit
                    await interaction.user.send(msg)
                    msg = ""
            if msg:
                await interaction.user.send(msg)

            await interaction.response.send_message("User list sent via DM.", ephemeral=True)
        else:
            # Show a specific user
            uid = int(self.values[0])
            self.view.selected_user = uid

            balance, total_bet = await get_balance(uid)
            ban_info = await get_user_ban_status(uid)

            msg = (
                f"👤 **{interaction.guild.get_member(uid) or 'User'}**\n"
                f"💰 Balance: {balance}\n"
                f"🧮 Total Bet: {total_bet}\n"
                f"⛔ Banned: {ban_info['ban_status']}\n"
                f"🕒 Ban Time: {ban_info['ban_time']}\n"
                f"🎮 Banned Games: {', '.join(ban_info['banned_games']) if ban_info['banned_games'] else 'None'}"
            )
            await interaction.response.send_message(msg, ephemeral=True)

# --- Ban Duration Dropdown ---
class BanTimeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 min", value="60"),
            discord.SelectOption(label="10 minutes", value="600"),
            discord.SelectOption(label="1 hour", value="3600"),
            discord.SelectOption(label="1 day", value="86400"),
            discord.SelectOption(label="Permanent", value="-1"),
            discord.SelectOption(label="Custom", value="custom")  # special value
        ]
        super().__init__(placeholder="Select ban duration...", min_values=1, max_values=1, options=options, custom_id="admin_ban_time_select")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "custom":
            # Show a modal to enter custom seconds
            await interaction.response.send_modal(CustomBanTimeModal(self.view))
        else:
            self.view.ban_duration = int(self.values[0])
            await interaction.response.send_message(
                f"Ban duration set to {self.values[0]} seconds.", ephemeral=True
            )

class CustomBanTimeModal(discord.ui.Modal, title="Enter Custom Ban Time"):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.add_item(discord.ui.InputText(
            label="Enter time in seconds",
            placeholder="e.g., 300 for 5 minutes",
            style=discord.InputTextStyle.short
        ))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            custom_time = int(self.children[0].value)
        except ValueError:
            await interaction.response.send_message("Invalid number entered.", ephemeral=True)
            return

        self.view.ban_duration = custom_time
        await interaction.response.send_message(
            f"Custom ban duration set to {custom_time} seconds.", ephemeral=True
        )

# --- Game Selection Dropdown ---
class GameSelect(discord.ui.Select):
    def __init__(self, games: list[str]):
        options = [discord.SelectOption(label=g, value=g) for g in games]
        super().__init__(placeholder="Select game...", min_values=1, max_values=1, options=options, custom_id="admin_game_select")

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_game = self.values[0]
        await interaction.response.send_message(f"Selected game: {self.values[0]}", ephemeral=True)

# --- Balance Modal ---
class UpdateBalanceModal(discord.ui.Modal, title="Update User Balance"):
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
        self.add_item(discord.ui.InputText(label="Amount (+/-)", placeholder="Enter integer"))
        self.add_item(discord.ui.InputText(label="Total Bet Adjustment", placeholder="Enter integer"))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.children[0].value)
            bet_adjust = int(self.children[1].value)
        except ValueError:
            await interaction.response.send_message("Invalid input.", ephemeral=True)
            return

        await update_balance(self.user_id, amount, bet_adjust)
        await interaction.response.send_message(
            f"✅ Updated <@{self.user_id}>: Balance change: {amount}, Total Bet change: {bet_adjust}", ephemeral=True
        )

# --- Admin View ---
class AdminView(discord.ui.View):
    def __init__(self, users: list[dict] = None, games: list[str] = None):
        super().__init__(timeout=None)
        self.users = users if users is not None else []
        self.games = games if games is not None else []
        self.selected_user = None
        self.selected_game = None
        self.ban_duration = None

    @discord.ui.button(label="Select User", style=discord.ButtonStyle.primary, custom_id="admin_select_user")
    async def show_user_dropdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create a new view with the dropdowns only
        view = discord.ui.View()
        view.add_item(UserDatabaseSelect(self.users))  # the dropdown
        view.add_item(BanTimeSelect())
        view.add_item(GameSelect(self.games))

        await interaction.response.send_message(
            "Choose a user and configure ban/balance:", view=view, ephemeral=True
        )

    @discord.ui.button(label="Manage Balance", style=discord.ButtonStyle.primary, custom_id="admin_manage_balance")
    async def manage_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_user:
            await interaction.response.send_message("Select a user first.", ephemeral=True)
            return
        await interaction.response.send_modal(UpdateBalanceModal(self.selected_user))

    @discord.ui.button(label="Ban User", style=discord.ButtonStyle.danger, custom_id="admin_ban_user")
    async def ban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_user:
            await interaction.response.send_message("Select a user first.", ephemeral=True)
            return

        game = self.selected_game or "ALL"
        duration = self.ban_duration or -1
        await ban_user_management(self.selected_user, True, duration, game)
        await interaction.response.send_message(
            f"User <@{self.selected_user}> banned for game `{game}` for {duration} seconds.", ephemeral=True
        )

    @discord.ui.button(label="Unban User", style=discord.ButtonStyle.success, custom_id="admin_unban_user")
    async def unban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_user:
            await interaction.response.send_message("Select a user first.", ephemeral=True)
            return

        game = self.selected_game or "ALL"
        await ban_user_management(self.selected_user, False, 0, game)
        await interaction.response.send_message(
            f"User <@{self.selected_user}> unbanned for game `{game}`.", ephemeral=True
        )
