import discord
from discord.ext import commands
from database import (
    get_users_info, get_balance, update_balance,
    get_all_banned_users, ban_user_management, get_user_ban_status
)

# --- User Select Dropdown ---
class UserDatabaseSelect(discord.ui.Select):
    def __init__(self, users: list[dict]):
        options = [discord.SelectOption(label="All Users", value="all")]
        for u in users[:24]:
            username = u.get('username') or "Unknown"
            username = username[:100]
            options.append(discord.SelectOption(label=username, value=str(u['user_id'])))
        super().__init__(
            placeholder="Select a user...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="admin_user_select"
        )
        self.users = users

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "all":
            users = await get_users_info()
            if not users:
                await interaction.response.send_message("No users found.", ephemeral=True)
                return
            msg = ""
            for u in users:
                msg += f"👤 {u['username'][:100]} | 💰 {u['balance']} | 🧮 Total Bet: {u['total_bet']}\n"
                if len(msg) > 1800:
                    await interaction.followup.send(msg, ephemeral=True)
                    msg = ""
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            uid = int(self.values[0])
            self.view.selected_user = uid
            username = next((u['username'][:100] for u in self.users if u['user_id'] == uid), "Unknown")
            balance, total_bet = await get_balance(uid)
            ban_info = await get_user_ban_status(uid)
            msg = (
                f"👤 **{username}**\n"
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
            discord.SelectOption(label="Custom", value="custom")
        ]
        super().__init__(placeholder="Select ban duration...", min_values=1, max_values=1, options=options, custom_id="admin_ban_time_select")

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "custom":
            await interaction.response.send_modal(CustomBanTimeModal(self.view))
        else:
            self.view.ban_duration = int(self.values[0])
            await interaction.response.send_message(f"Ban duration set to {self.values[0]} seconds.", ephemeral=True)

# --- Custom Ban Modal ---
class CustomBanTimeModal(discord.ui.Modal, title="Enter Custom Ban Time"):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.add_item(discord.ui.TextInput(
            label="Enter time in seconds",
            placeholder="e.g., 300 for 5 minutes",
            style=discord.TextStyle.short
        ))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            custom_time = int(self.children[0].value)
        except ValueError:
            await interaction.response.send_message("Invalid number entered.", ephemeral=True)
            return
        self.view.ban_duration = custom_time
        await interaction.response.send_message(f"Custom ban duration set to {custom_time} seconds.", ephemeral=True)

# --- Game Selection Dropdown ---
class GameSelect(discord.ui.Select):
    def __init__(self, games: list[str]):
        options = [discord.SelectOption(label=g[:100], value=g[:100]) for g in games]
        super().__init__(placeholder="Select game...", min_values=1, max_values=1, options=options, custom_id="admin_game_select")

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_game = self.values[0]
        await interaction.response.send_message(f"Selected game: {self.values[0]}", ephemeral=True)

# --- Unban Dropdown ---
class UnbanUserSelect(discord.ui.Select):
    def __init__(self, banned_users: list[dict]):
        options = [
            discord.SelectOption(
                label=(u['username'][:100] if u['username'] else f"User {u['user_id']}"),
                value=str(u['user_id'])
            ) for u in banned_users
        ]
        super().__init__(
            placeholder="Select user to unban",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="admin_unban_select"
        )

    async def callback(self, interaction: discord.Interaction):
        uid = int(self.values[0])
        self.view.selected_user = uid
        await ban_user_management(uid, False, 0, "{}")
        await interaction.response.send_message(f"✅ User <@{uid}> has been unbanned.", ephemeral=True)

# --- Manage Balance Flow ---
class BalanceUserSelect(discord.ui.Select):
    def __init__(self, users: list[dict]):
        options = [discord.SelectOption(label=u['username'][:100], value=str(u['user_id'])) for u in users]
        super().__init__(placeholder="Select user...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_user = int(self.values[0])
        await interaction.response.send_message("Select type to adjust:", view=BalanceTypeView(), ephemeral=True)

class BalanceTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Balance", value="balance"),
            discord.SelectOption(label="Total Bet", value="total_bet")
        ]
        super().__init__(placeholder="Select type to adjust...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.adjust_type = self.values[0]
        await interaction.response.send_message("Select operation:", view=BalanceOperationView(), ephemeral=True)

class BalanceOperationSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Add", value="add"),
            discord.SelectOption(label="Remove", value="remove")
        ]
        super().__init__(placeholder="Select operation...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.operation = self.values[0]
        await interaction.response.send_modal(BalanceAmountModal(self.view.selected_user, self.view.adjust_type, self.view.operation))

class BalanceAmountModal(discord.ui.Modal, title="Enter Amount"):
    def __init__(self, user_id, adjust_type, operation):
        super().__init__()
        self.user_id = user_id
        self.adjust_type = adjust_type
        self.operation = operation
        self.add_item(discord.ui.InputText(label="Amount", placeholder="Enter integer"))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.children[0].value)
            if self.operation == "remove":
                amount = -abs(amount)
        except ValueError:
            await interaction.response.send_message("Invalid number.", ephemeral=True)
            return
        if self.adjust_type == "balance":
            await update_balance(self.user_id, amount, 0)
        else:
            await update_balance(self.user_id, 0, amount)
        await interaction.response.send_message(
            f"✅ Updated <@{self.user_id}>: {self.adjust_type} {'added' if amount>0 else 'removed'} {abs(amount)}", ephemeral=True
        )

class BalanceTypeView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.selected_user = None
        self.adjust_type = None
        self.operation = None
        self.add_item(BalanceTypeSelect())

class BalanceOperationView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.selected_user = None
        self.adjust_type = None
        self.operation = None
        self.add_item(BalanceOperationSelect())

# --- Admin View ---
class AdminView(discord.ui.View):
    def __init__(self, users: list[dict] = None, games: list[str] = None):
        super().__init__(timeout=None)
        self.users = users or []
        self.games = games or []
        self.selected_user = None
        self.selected_game = None
        self.ban_duration = None

    @discord.ui.button(label="Show Users", style=discord.ButtonStyle.primary, custom_id='show_users', row=1)
    async def show_user_dropdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.users:
            self.users = await get_users_info()
        view = discord.ui.View()
        view.add_item(UserDatabaseSelect(self.users))
        await interaction.response.send_message("Choose a user:", view=view, ephemeral=True)

    @discord.ui.button(label="Manage Balance", style=discord.ButtonStyle.primary, custom_id='manage_balance', row=1) 
    async def manage_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.users:
            self.users = await get_users_info()
        view = discord.ui.View()
        view.add_item(BalanceUserSelect(self.users))
        await interaction.response.send_message("Select a user to adjust balance/total bet:", view=view, ephemeral=True)

    @discord.ui.button(label="Show Banned Users", style=discord.ButtonStyle.secondary, custom_id='show_banned_users', row=2)
    async def show_banned_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        banned_users = await get_all_banned_users()
        if not banned_users:
            await interaction.response.send_message("No banned users.", ephemeral=True)
            return
        msg = ""
        for u in banned_users:
            msg += f"👤 {u['username'][:100]} | ⛔ Banned Games: {', '.join(u['banned_games']) if u['banned_games'] else 'ALL'} | 🕒 Ban Time: {u['ban_time']}\n"
            if len(msg) > 1800:
                await interaction.followup.send(msg, ephemeral=True)
                msg = ""
        if msg:
            await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Ban User", style=discord.ButtonStyle.danger, custom_id='ban_user', row=2)
    async def ban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.users:
            self.users = await get_users_info()
        view = discord.ui.View()
        view.add_item(UserDatabaseSelect(self.users))
        view.add_item(GameSelect(self.games))
        view.add_item(BanTimeSelect())
        await interaction.response.send_message("Select user, game, and duration to ban:", view=view, ephemeral=True)

    @discord.ui.button(label="Unban User", style=discord.ButtonStyle.success, custom_id='unban_user', row=2)
    async def unban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        banned_users = await get_all_banned_users()
        if not banned_users:
            await interaction.response.send_message("No banned users.", ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(UnbanUserSelect(banned_users))
        view.add_item(GameSelect(self.games + ["{}"]))
        await interaction.response.send_message("Select a user (and optionally game) to unban:", view=view, ephemeral=True)
