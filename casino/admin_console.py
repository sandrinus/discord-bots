import discord
from discord.ext import commands
from my_logginng import db_log
# import json
# import datetime

from database import get_users_info, get_balance, update_balance
    # get_all_banned_users, ban_user_management, get_user_ban_status

# --- (keep your original UserDatabaseSelect if you like) ---
class UserDatabaseSelect(discord.ui.Select):
    def __init__(self, users: list[dict]):
        options = [discord.SelectOption(label="All Users", value="all")]
        for u in users[:24]:
            username = u.get('username')[:100] if u.get('username') else f"User {u['user_id']}"
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
                msg += f"👤 {u.get('username','Unknown')[:100]} | 💰 {u['balance']} | 🧮 Total Bet: {u['total_bet']}\n"
                if len(msg) > 1800:
                    await interaction.followup.send(msg, ephemeral=True)
                    msg = ""
            if msg:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            uid = int(self.values[0])
            self.view.selected_user = uid
            username = next((u.get('username','Unknown')[:100] for u in self.users if u['user_id'] == uid), "Unknown")
            balance, total_bet = await get_balance(user_id=uid, admin=True)
            # ban_info = await get_user_ban_status(uid)
            msg = (
                f"👤 **{username}**\n"
                f"💰 Balance: {balance}\n"
                f"🧮 Total Bet: {total_bet}"
                # f"⛔ Banned: {ban_info['ban_status']}\n"
                # f"🕒 Ban Time: {ban_info['ban_time']}\n"
                # f"🎮 Banned Games: {', '.join(ban_info['banned_games']) if ban_info['banned_games'] else 'None'}"
            )
            await interaction.response.send_message(msg, ephemeral=True)


# -----------------------
# Balance flow (fixed)
# -----------------------
class BalanceUserSelect(discord.ui.Select):
    def __init__(self, users: list[dict]):
        options = [
            discord.SelectOption(label=(u.get('username','User '+str(u['user_id']))[:100]), value=str(u['user_id']))
            for u in users[:25]
        ]
        super().__init__(placeholder="Select user...", min_values=1, max_values=1, options=options, custom_id="balance_user_select")

    async def callback(self, interaction: discord.Interaction):
        # store selected_user in the parent view (the ephemeral view that showed this select)
        self.view.selected_user = int(self.values[0])

        # create a new BalanceTypeView but pass the selected_user to it
        next_view = BalanceTypeView()
        next_view.selected_user = self.view.selected_user
        await interaction.response.send_message("Select type to adjust:", view=next_view, ephemeral=True)


class BalanceTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Balance", value="balance"),
            discord.SelectOption(label="Total Bet", value="total_bet")
        ]
        super().__init__(placeholder="Select type to adjust...", min_values=1, max_values=1, options=options, custom_id="balance_type_select")

    async def callback(self, interaction: discord.Interaction):
        # self.view is BalanceTypeView, set its adjust_type
        self.view.adjust_type = self.values[0]

        # create the next view and pass along the selected_user and adjust_type
        op_view = BalanceOperationView()
        op_view.selected_user = self.view.selected_user
        op_view.adjust_type = self.view.adjust_type
        await interaction.response.send_message("Select operation:", view=op_view, ephemeral=True)


class BalanceOperationSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Add", value="add"),
            discord.SelectOption(label="Remove", value="remove")
        ]
        super().__init__(placeholder="Select operation...", min_values=1, max_values=1, options=options, custom_id="balance_operation_select")

    async def callback(self, interaction: discord.Interaction):
        # self.view is BalanceOperationView
        self.view.operation = self.values[0]
        # now open modal with the state available on this view
        await interaction.response.send_modal(BalanceAmountModal(self.view.selected_user, self.view.adjust_type, self.view.operation))


class BalanceAmountModal(discord.ui.Modal, title="Enter Amount"):
    def __init__(self, user_id, adjust_type, operation):
        super().__init__()
        self.user_id = user_id
        self.adjust_type = adjust_type
        self.operation = operation
        self.add_item(discord.ui.TextInput(label="Amount", placeholder="Enter integer"))

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
        # Log the admin action
        bal, bet = await get_balance(user_id=self.user_id, admin=True)
        await db_log(
            user_id=self.user_id,
            username="NULL",
            source="admin_panel",
            action=self.operation,
            bet_amount=0,
            delta=amount,
            balance_after=bal,
            total_bet_after=bet,
            metadata={
                "admin_id": interaction.user.id,
                "admin_name": interaction.user.name,
                "adjust_type": self.adjust_type,
                "operation": self.operation,
                "amount": amount
            }
        )
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

# -----------------------
# AdminView: hook up the new flows
# -----------------------
class AdminView(discord.ui.View):
    def __init__(self, users: list[dict] = None, games: list[str] = None):
        super().__init__(timeout=None)
        self.users = users or []
        self.games = games or []
        self.selected_user = None
        self.selected_game = None

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
        # we will use the BalanceUserSelect to begin the flow
        view.add_item(BalanceUserSelect(self.users))
        await interaction.response.send_message("Select a user to adjust balance/total bet:", view=view, ephemeral=True)