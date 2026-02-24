import logging

import httpx

from metta.app_backend.config import settings
from metta.app_backend.user_data import UserRow

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"


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
