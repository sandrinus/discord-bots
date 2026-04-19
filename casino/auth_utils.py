import os
import discord

def parse_admin_ids() -> set[int]:
    raw = os.getenv("CASINO_ADMIN_IDS", "")
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return {int(x) for x in values if x.isdigit()}

def is_admin_user(interaction: discord.Interaction, admin_ids: set[int] | None = None) -> bool:
    allowed_ids = admin_ids if admin_ids is not None else parse_admin_ids()
    if interaction.user.id in allowed_ids:
        return True
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.administrator)
