import logging
from uuid import UUID

import httpx
from pydantic import BaseModel, Field

from metta.app_backend.config import settings
from metta.app_backend.user_data import UserRow, load_user_id

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"


class DiscordEmbedField(BaseModel):
    name: str
    value: str
    inline: bool = False


class DiscordEmbed(BaseModel):
    title: str
    description: str
    fields: list[DiscordEmbedField] = Field(default_factory=list)


async def send_discord_notification(user: UserRow, title: str, description: str) -> None:
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        logger.warning("DISCORD_BOT_TOKEN not configured, skipping notification")
        return
    if not user.discord_id:
        logger.info("User %s has no discord_id, skipping notification", user.id)
        return

    headers = {"Authorization": f"Bot {token}"}

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        dm_resp = await client.post(f"{DISCORD_API}/users/@me/channels", json={"recipient_id": user.discord_id})
        dm_resp.raise_for_status()
        channel_id = dm_resp.json()["id"]

        (
            await client.post(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                json={"embeds": [{"title": title, "description": description}]},
            )
        ).raise_for_status()


async def send_discord_announcement(embed: DiscordEmbed) -> None:
    webhook_url = settings.DISCORD_ANNOUNCEMENTS_WEBHOOK_URL
    if not webhook_url:
        logger.info("DISCORD_ANNOUNCEMENTS_WEBHOOK_URL not configured, skipping announcement")
        return

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json={"embeds": [embed.model_dump()]})
            response.raise_for_status()
    except Exception:
        logger.warning("Failed to send Discord announcement", exc_info=True)


async def announce_first_policy_submission(
    *,
    user_id: str,
    fallback_email: str | None,
    policy_name: str,
    policy_version: int,
    policy_version_id: UUID,
    season_name: str,
) -> None:
    resolved_user = await load_user_id(user_id)
    display_name = resolved_user.name if resolved_user is not None and resolved_user.name else fallback_email or user_id
    email = resolved_user.email if resolved_user is not None and resolved_user.email else fallback_email
    site_url = settings.LOGIN_SERVICE_URL.rstrip("/")
    policy_url = f"{site_url}/observatory/policies/versions/{policy_version_id}"

    fields = [
        DiscordEmbedField(name="User", value=display_name),
        DiscordEmbedField(name="Policy", value=f"{policy_name} v{policy_version}"),
        DiscordEmbedField(name="Season", value=season_name),
        DiscordEmbedField(name="Policy page", value=policy_url),
    ]
    if email:
        fields.insert(1, DiscordEmbedField(name="Email", value=email))

    await send_discord_announcement(
        DiscordEmbed(
            title="First Softmax policy submission",
            description=f"{display_name} submitted their first policy to {season_name}.",
            fields=fields,
        )
    )
