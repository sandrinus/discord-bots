import discord
import random
import asyncio
from database import get_balance, update_balance, get_user_lock

CARD_VALUES = {
    "A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
    "7": 7, "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10
}
SUITS = ["♠", "♥", "♦", "♣"]
CARDS = [f"{rank}{suit}" for rank in CARD_VALUES for suit in SUITS]
active_blackjack_tables = set()

def draw_card():
    return random.choice(CARDS)

def hand_value(hand):
    value = sum(CARD_VALUES[c[:-1]] for c in hand)
    aces = sum(1 for c in hand if c.startswith("A"))
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value

def format_hand(hand, hide_second_card=False):
    if hide_second_card and len(hand) > 1:
        return f"{hand[0]} | ❓"
    return " | ".join(hand)

class BlackjackView(discord.ui.View):
    def __init__(self, uid, bet):
        super().__init__(timeout=180)
        self.uid = uid
        self.bet = bet

        self.player_hand = [draw_card(), draw_card()]
        self.dealer_hand = [draw_card(), draw_card()]
        self.game_over = False

        self.message = None

    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

    async def update_embed(self, interaction=None, *, footer=None, color=discord.Color.blurple(), reveal_dealer=False):
        embed = discord.Embed(title="🃏 Blackjack", color=color)
        embed.add_field(name="Your Hand", value=f"{format_hand(self.player_hand)}\n({hand_value(self.player_hand)})", inline=False)
        embed.add_field(
            name="Dealer's Hand",
            value=f"{format_hand(self.dealer_hand, hide_second_card=not reveal_dealer)}\n({hand_value(self.dealer_hand) if reveal_dealer else '?'})",
            inline=False
        )
        if footer:
            embed.set_footer(text=footer)
    
        if interaction is not None:
            # edit the original interaction response (works after defer)
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            # fallback to editing stored message if available
            if self.message:
                await self.message.edit(embed=embed, view=self)
            
    async def end_game(self, result_text, win=False, bonus=False):
        self.game_over = True
        await self.disable_all_items()

        if win:
            if bonus:
                await update_balance(self.uid, self.bet*5, self.bet)
            else:
                await update_balance(self.uid, self.bet, self.bet)
        else:
            await update_balance(self.uid, -self.bet, self.bet)

        embed = discord.Embed(
            title="🃏 Blackjack",
            color=discord.Color.green() if win else discord.Color.red()
        )
        embed.add_field(
            name="Your Hand",
            value=f"{format_hand(self.player_hand)}\n({hand_value(self.player_hand)})",
            inline=False
        )
        embed.add_field(
            name="Dealer's Hand",
            value=f"{format_hand(self.dealer_hand, hide_second_card=False)}\n({hand_value(self.dealer_hand)})",
            inline=False
        )
        embed.set_footer(text=result_text)

        # Just edit the existing ephemeral message
        await self.message.edit(embed=embed, view=self)
        async with active_blackjack_tables_lock:
            active_blackjack_tables.discard(self.uid)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.primary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            return
    
        lock = get_user_lock(self.uid)
        async with lock:
            if self.game_over:
                await interaction.response.send_message("Game over! Start a new game to play again.", ephemeral=True)
                return
    
            await interaction.response.defer(ephemeral=True)
    
            player_total = hand_value(self.player_hand)
    
            while True:
                dealer_total = hand_value(self.dealer_hand)
    
                if dealer_total < player_total and dealer_total < 21:
                    self.dealer_hand.append(draw_card())
                    await self.update_embed(interaction=interaction, reveal_dealer=True)
                    await asyncio.sleep(1)
                else:
                    break
    
            dealer_total = hand_value(self.dealer_hand)
            
            if dealer_total > 21 or player_total > dealer_total:
                if player_total == 21:
                    await self.end_game(f"🎉 You win! +{self.bet * 5}", win=True, bonus=True)
                else:
                    await self.end_game(f"🎉 You win! +{self.bet}", win=True)
            elif player_total == dealer_total:
                await self.disable_all_items()
                await self.update_embed(interaction=interaction, footer="🤝 Draw. Bet returned.", color=discord.Color.gold(), reveal_dealer=True)
                self.game_over = True
            else:
                await self.end_game(f"💀 You lose {self.bet}.", win=False)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("❌ Not your game!", ephemeral=True)
            return
        
        # Prevent spam clicks
        button.disabled = True
        await self.message.edit(view=self)

        self.player_hand.append(draw_card()) 
        player_total = hand_value(self.player_hand)

        if player_total > 21:
            await self.end_game(f"💥 Bust! You lose {self.bet}.", win=False)
            await interaction.response.defer()
        else:
            # Re-enable buttons after valid hit
            button.disabled = False
            await self.message.edit(view=self)
            await self.update_embed()
            await interaction.response.defer()

async def start_blackjack(interaction: discord.Interaction, bet: int):
    uid = interaction.user.id

    if uid in active_blackjack_tables:
        await interaction.response.send_message(
            "⚠️ You need to finish the previous game", ephemeral=True
        )
        return
    active_blackjack_tables.add(uid)

    username = interaction.user.name
    balance, _ = await get_balance(uid, username)
    if balance < bet:
        await interaction.response.send_message(f"❌ You need at least {bet} coins!", ephemeral=True)
        return
    view = BlackjackView(uid, bet)

    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.blurple())
    embed.add_field(name="Your Hand", value=f"{format_hand(view.player_hand)}\n({hand_value(view.player_hand)})", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{format_hand(view.dealer_hand, hide_second_card=True)}\n(?)", inline=False)
    embed.set_footer(text="Hit or Stand?")
    await interaction.response.defer(ephemeral=True)
    msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    view.message = msg


class BlackjackBetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    async def start_game(self, interaction, bet):
        await start_blackjack(interaction, bet)

    @discord.ui.button(label="Bet 50", style=discord.ButtonStyle.success, custom_id="blackjack_bet_50")
    async def bet50(self, interaction, button):
        await self.start_game(interaction, 50)

    @discord.ui.button(label="Bet 100", style=discord.ButtonStyle.success, custom_id="blackjack_bet_100")
    async def bet100(self, interaction, button):
        await self.start_game(interaction, 100)

    @discord.ui.button(label="Bet 500", style=discord.ButtonStyle.success, custom_id="blackjack_bet_500")
    async def bet500(self, interaction, button):
        await self.start_game(interaction, 500)

    @discord.ui.button(label="Bet 1000", style=discord.ButtonStyle.danger, custom_id="blackjack_bet_1000")
    async def bet1000(self, interaction, button):
        await self.start_game(interaction, 1000)

    @discord.ui.button(label="Check My Balance", style=discord.ButtonStyle.primary, custom_id="check_balance", row=1)
    async def check(self, interaction, button):
        bal, total = await get_balance(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(f"💰 Balance: {bal}\n🧮 Total Bet: {total}", ephemeral=True)
