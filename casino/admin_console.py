import discord
from discord.ext import commands
import time
import json
import datetime

from database import (
    get_users_info, get_balance, update_balance,
    get_all_banned_users, ban_user_management, get_user_ban_status
)

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
            ban_info = await get_user_ban_status(uid)
            msg = (
                f"👤 **{username}**\n"
                f"💰 Balance: {balance}\n"
                f"🧮 Total Bet: {total_bet}\n"
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


# # -----------------------
# # Ban flow (new, works like balance flow)
# # -----------------------
# class BanUserSelect(discord.ui.Select):
#     def __init__(self, users: list[dict]):
#         options = [
#             discord.SelectOption(label=(u.get('username','User '+str(u['user_id']))[:100]), value=str(u['user_id']))
#             for u in users[:25]
#         ]
#         super().__init__(placeholder="Select user to ban...", min_values=1, max_values=1, options=options, custom_id="ban_user_select")

#     async def callback(self, interaction: discord.Interaction):
#         uid = int(self.values[0])
#         # open the BanOptionsView and pass the selected user
#         options_view = BanOptionsView(self.view.games if hasattr(self.view, "games") else [])
#         options_view.selected_user = uid
#         await interaction.response.send_message("Choose game and duration, then confirm:", view=options_view, ephemeral=True)


# class BanOptionsView(discord.ui.View):
#     def __init__(self, games: list[str]):
#         super().__init__()
#         self.selected_user = None
#         self.selected_game = None
#         self.ban_duration = None
#         self.games = games or []
#         # add GameSelect and BanTimeSelect into this view so their callbacks set this view's attributes
#         self.add_item(GameSelect(self.games + ["{}"]))   # "{}" to mean ALL (keeps your prior convention)
#         self.add_item(BanTimeSelect())
#         # confirm button
#         self.add_item(BanConfirmButton())


# class BanConfirmButton(discord.ui.Button):
#     def __init__(self):
#         super().__init__(label="Confirm Ban", style=discord.ButtonStyle.danger, custom_id="confirm_ban_btn")

#     async def callback(self, interaction: discord.Interaction):
#         view: BanOptionsView = self.view
#         if not view or not getattr(view, "selected_user", None):
#             await interaction.response.send_message("No user selected to ban.", ephemeral=True)
#             return

#         uid = view.selected_user
#         sel_game = view.selected_game
#         duration = view.ban_duration

#         # Prepare banned_games payload - use "{}" to mean all (keeps your earlier uses)
#         if not sel_game or sel_game == "{}":
#             banned_games_payload = "{}"
#         else:
#             banned_games_payload = json.dumps([sel_game])

#         # Convert duration to an absolute end timestamp, or -1 for permanent
#         if duration is None:
#             # default to permanent if not chosen
#             ban_time_val = -1
#         else:
#             if int(duration) == -1:
#                 ban_time_val = -1
#             else:
#                 ban_time_val = int(time.time()) + int(duration)

#         # Call your DB function
#         await ban_user_management(uid, True, ban_time_val, banned_games_payload)
#         await interaction.response.send_message(f"✅ Banned <@{uid}> for game: {sel_game or 'ALL'} until: {ban_time_val}", ephemeral=True)


# # -----------------------
# # Unban flow (same pattern)
# # -----------------------
# class UnbanUserSelect(discord.ui.Select):
#     def __init__(self, banned_users: list[dict]):
#         options = [
#             discord.SelectOption(
#                 label=(u.get('username','User '+str(u['user_id']))[:100]),
#                 value=str(u['user_id'])
#             ) for u in banned_users
#         ]
#         super().__init__(
#             placeholder="Select user to unban",
#             min_values=1,
#             max_values=1,
#             options=options,
#             custom_id="admin_unban_select"
#         )

#     async def callback(self, interaction: discord.Interaction):
#         uid = int(self.values[0])
#         options_view = UnbanOptionsView(self.view.games if hasattr(self.view, "games") else [])
#         options_view.selected_user = uid
#         await interaction.response.send_message("Choose game to unban (or ALL), then confirm:", view=options_view, ephemeral=True)


# class UnbanOptionsView(discord.ui.View):
#     def __init__(self, games: list[str]):
#         super().__init__()
#         self.selected_user = None
#         self.selected_game = None
#         self.games = games or []
#         self.add_item(GameSelect(self.games + ["{}"]))
#         self.add_item(UnbanConfirmButton())


# class UnbanConfirmButton(discord.ui.Button):
#     def __init__(self):
#         super().__init__(label="Confirm Unban", style=discord.ButtonStyle.success, custom_id="confirm_unban_btn")

#     async def callback(self, interaction: discord.Interaction):
#         view: UnbanOptionsView = self.view
#         uid = view.selected_user
#         sel_game = view.selected_game

#         if not uid:
#             await interaction.response.send_message("No user selected.", ephemeral=True)
#             return

#         # If user selected "{}", treat as all games
#         if not sel_game or sel_game == "{}":
#             banned_games_payload = "{}"
#         else:
#             banned_games_payload = json.dumps([sel_game])

#         # Unban call - previously you used ban_user_management(uid, False, 0, "{}")
#         await ban_user_management(uid, False, 0, banned_games_payload)
#         await interaction.response.send_message(f"✅ Unbanned <@{uid}> for game: {sel_game or 'ALL'}", ephemeral=True)


# # -----------------------
# # GameSelect and BanTimeSelect and CustomBanTimeModal stay mostly the same,
# # but they now rely on the view they are put in (BanOptionsView, UnbanOptionsView, etc.)
# # to store state.
# # -----------------------
# class GameSelect(discord.ui.Select):
#     def __init__(self, games: list[str]):
#         options = [discord.SelectOption(label=g[:100], value=g[:100]) for g in games]
#         super().__init__(placeholder="Select game...", min_values=1, max_values=1, options=options, custom_id="admin_game_select")

#     async def callback(self, interaction: discord.Interaction):
#         # store on the containing view (BanOptionsView, UnbanOptionsView, etc.)
#         self.view.selected_game = self.values[0]
#         await interaction.response.send_message(f"Selected game: {self.values[0]}", ephemeral=True)


# class BanTimeSelect(discord.ui.Select):
#     def __init__(self):
#         options = [
#             discord.SelectOption(label="1 min", value="60"),
#             discord.SelectOption(label="10 minutes", value="600"),
#             discord.SelectOption(label="1 hour", value="3600"),
#             discord.SelectOption(label="1 day", value="86400"),
#             discord.SelectOption(label="Permanent", value="-1"),
#             discord.SelectOption(label="Custom", value="custom")
#         ]
#         super().__init__(placeholder="Select ban duration...", min_values=1, max_values=1, options=options, custom_id="admin_ban_time_select")

#     async def callback(self, interaction: discord.Interaction):
#         if self.values[0] == "custom":
#             # send a modal that receives a reference to the view (so it can set ban_duration)
#             await interaction.response.send_modal(CustomBanTimeModal(self.view))
#         else:
#             # store the duration on the parent view
#             self.view.ban_duration = int(self.values[0])
#             await interaction.response.send_message(f"Ban duration set to {self.values[0]} seconds.", ephemeral=True)


# class CustomBanTimeModal(discord.ui.Modal, title="Enter Custom Ban Time"):
#     def __init__(self, view):
#         super().__init__()
#         self.view = view
#         self.add_item(discord.ui.TextInput(
#             label="Enter time in seconds",
#             placeholder="e.g., 300 for 5 minutes",
#             style=discord.TextStyle.short
#         ))

#     async def on_submit(self, interaction: discord.Interaction):
#         try:
#             custom_time = int(self.children[0].value)
#         except ValueError:
#             await interaction.response.send_message("Invalid number entered.", ephemeral=True)
#             return
#         self.view.ban_duration = custom_time
#         await interaction.response.send_message(f"Custom ban duration set to {custom_time} seconds.", ephemeral=True)


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
        # we will use the BalanceUserSelect to begin the flow
        view.add_item(BalanceUserSelect(self.users))
        await interaction.response.send_message("Select a user to adjust balance/total bet:", view=view, ephemeral=True)

#     @discord.ui.button(label="Show Banned Users", style=discord.ButtonStyle.secondary, custom_id='show_banned_users', row=2)
#     async def show_banned_users(self, interaction: discord.Interaction, button: discord.ui.Button):
#         banned_users = await get_all_banned_users()
#         if not banned_users:
#             await interaction.response.send_message("No banned users.", ephemeral=True)
#             return
#         msg = ""
#         for u in banned_users:
#             # Convert timestamp if not permanent
#             if u['ban_time'] == -1:
#                 ban_time_str = "Permanent"
#             elif u['ban_time'] == 0:
#                 ban_time_str = "Not Banned"
#             else:
#                 ban_time_str = datetime.datetime.utcfromtimestamp(u['ban_time']).strftime("%Y-%m-%d %H:%M:%S UTC")
    
#             msg += (
#                 f"👤 {u.get('username','Unknown')[:100]} | "
#                 f"⛔ Banned Games: {', '.join(u['banned_games']) if u['banned_games'] else 'ALL'} | "
#                 f"🕒 Ban Time: {ban_time_str}\n"
#             )
#             if len(msg) > 1800:
#                 await interaction.followup.send(msg, ephemeral=True)
#                 msg = ""
#         if msg:
#             await interaction.response.send_message(msg, ephemeral=True)

#     @discord.ui.button(label="Ban User", style=discord.ButtonStyle.danger, custom_id='ban_user', row=2)
#     async def ban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if not self.users:
#             self.users = await get_users_info()
#         # start the ban flow by showing a select of users
#         view = discord.ui.View()
#         # attach games to the view so BanUserSelect can pass them into BanOptionsView
#         view.games = self.games
#         view.add_item(BanUserSelect(self.users))
#         await interaction.response.send_message("Select a user to ban:", view=view, ephemeral=True)

#     @discord.ui.button(label="Unban User", style=discord.ButtonStyle.success, custom_id='unban_user', row=2)
#     async def unban_user(self, interaction: discord.Interaction, button: discord.ui.Button):
#         banned_users = await get_all_banned_users()
#         if not banned_users:
#             await interaction.response.send_message("No banned users.", ephemeral=True)
#             return
#         view = discord.ui.View()
#         view.games = self.games
#         view.add_item(UnbanUserSelect(banned_users))
#         await interaction.response.send_message("Select a user to unban:", view=view, ephemeral=True)
