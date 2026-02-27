#!/usr/bin/env python3
"""Post content to Discord webhook with message splitting."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

DISCORD_MESSAGE_CHARACTER_LIMIT = 2000
RATE_LIMIT_DELAY_S = 0.5
MESSAGE_PREFIX = "...\r\n   \r\n"


def _split_content(content: str, max_len: int) -> list[str]:
    if not content:
        return []

    chunks: list[str] = []
    remaining = content.strip()
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n\n", 0, max_len)
        if split_at != -1:
            chunk = remaining[: split_at + 2]
            remaining = remaining[split_at + 2 :]
        else:
            split_at = remaining.rfind("\n", 0, max_len)
            if split_at != -1:
                chunk = remaining[: split_at + 1]
                remaining = remaining[split_at + 1 :]
            else:
                split_at = remaining.rfind(" ", 0, max_len)
                if split_at != -1:
                    chunk = remaining[:split_at]
                    remaining = remaining[split_at + 1 :]
                else:
                    chunk = remaining[:max_len]
                    remaining = remaining[max_len:]

        chunks.append(chunk.strip())

    return [chunk for chunk in chunks if chunk]


def _sanitize_content(content: str) -> str:
    content = content.replace("@everyone", "@\u200beveryone")
    content = content.replace("@here", "@\u200bhere")
    content = content.replace("@ everyone", "@ \u200beveryone")
    return content.replace("@ here", "@ \u200bhere")


def _send_to_discord(webhook_url: str, content: str, suppress_embeds: bool) -> bool:
    safe_content = _sanitize_content(content)
    effective_max_len = DISCORD_MESSAGE_CHARACTER_LIMIT - len(MESSAGE_PREFIX)
    chunks = _split_content(safe_content, max_len=effective_max_len)
    if not chunks:
        print("No content to send to Discord.")
        return True

    print(f"Splitting message into {len(chunks)} chunk(s)...")
    for index, chunk in enumerate(chunks):
        prefixed_chunk = MESSAGE_PREFIX + chunk
        if len(prefixed_chunk) > DISCORD_MESSAGE_CHARACTER_LIMIT:
            chunk = chunk[:effective_max_len]
            prefixed_chunk = MESSAGE_PREFIX + chunk

        payload: dict[str, Any] = {"content": prefixed_chunk}
        if suppress_embeds:
            payload["flags"] = 4

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            print(f"Successfully sent chunk {index + 1}/{len(chunks)} to Discord.")
        except requests.exceptions.RequestException as exc:
            print(f"Error sending message to Discord: {exc}", file=sys.stderr)
            if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
                print(f"Discord API response: {exc.response.text}", file=sys.stderr)
            return False

        if index < len(chunks) - 1:
            time.sleep(RATE_LIMIT_DELAY_S)

    return True


def _get_content() -> str:
    content = os.getenv("DISCORD_CONTENT")
    if content:
        return content

    content_file = os.getenv("DISCORD_CONTENT_FILE")
    if not content_file:
        print("Error: Neither DISCORD_CONTENT nor DISCORD_CONTENT_FILE provided", file=sys.stderr)
        sys.exit(1)

    content_path = Path(content_file)
    if not content_path.exists():
        print(f"Error: Content file '{content_file}' does not exist", file=sys.stderr)
        sys.exit(1)
    try:
        return content_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Error reading content file '{content_file}': {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Error: DISCORD_WEBHOOK_URL not provided", file=sys.stderr)
        sys.exit(1)
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        print("Warning: Webhook URL does not match expected Discord format", file=sys.stderr)

    content = _get_content()
    if not content.strip():
        print("Error: Content is empty", file=sys.stderr)
        sys.exit(1)

    suppress_embeds = os.getenv("DISCORD_SUPPRESS_EMBEDS", "true").lower() == "true"
    sys.exit(0 if _send_to_discord(webhook_url, content, suppress_embeds) else 1)


if __name__ == "__main__":
    main()
