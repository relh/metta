import os
import re

import httpx
from fastapi import HTTPException

COMPAT_IMAGE_TAG_PREFIX = "compat-v"
COMPAT_IMAGE_TAG_PATTERN = re.compile(rf"^{COMPAT_IMAGE_TAG_PREFIX}(\d+\.\d+)$")
DEFAULT_EPISODE_RUNNER_REGISTRY = "ghcr.io/metta-ai/episode-runner"
REGISTRY_REQUEST_TIMEOUT_SECONDS = 10.0


def get_episode_runner_registry() -> str:
    return os.environ.get("EPISODE_RUNNER_REGISTRY", DEFAULT_EPISODE_RUNNER_REGISTRY)


def build_episode_runner_compat_image(compat_version: str) -> str:
    return f"{get_episode_runner_registry()}:{COMPAT_IMAGE_TAG_PREFIX}{compat_version}"


def _split_registry_reference(registry_reference: str) -> tuple[str, str]:
    reference = registry_reference.strip().split("@", maxsplit=1)[0]
    if "/" not in reference:
        raise ValueError(f"Invalid registry reference: {registry_reference}")
    host, repository_with_tag = reference.split("/", maxsplit=1)
    repository = repository_with_tag
    if ":" in repository.rsplit("/", maxsplit=1)[-1]:
        repository = repository.rsplit(":", maxsplit=1)[0]
    if not host or not repository:
        raise ValueError(f"Invalid registry reference: {registry_reference}")
    return host, repository


def _sort_compat_versions(versions: set[str]) -> list[str]:
    return sorted(versions, key=lambda value: tuple(int(part) for part in value.split(".")), reverse=True)


async def list_available_episode_runner_compat_versions() -> list[str]:
    registry = get_episode_runner_registry()
    host, repository = _split_registry_reference(registry)
    compat_versions: set[str] = set()

    try:
        async with httpx.AsyncClient(timeout=REGISTRY_REQUEST_TIMEOUT_SECONDS) as client:
            token_response = await client.get(
                f"https://{host}/token",
                params={"scope": f"repository:{repository}:pull"},
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            token: str | None = None
            if "token" in token_payload:
                token = token_payload["token"]
            elif "access_token" in token_payload:
                token = token_payload["access_token"]
            if not token:
                raise HTTPException(status_code=503, detail=f"Unable to fetch registry token for {registry}")

            headers = {"Authorization": f"Bearer {token}"}
            next_url: str | None = f"https://{host}/v2/{repository}/tags/list?n=100"
            while next_url:
                tags_response = await client.get(next_url, headers=headers)
                tags_response.raise_for_status()
                payload = tags_response.json()
                tags = payload["tags"]
                if tags is None:
                    tags = []
                for tag in tags:
                    match = COMPAT_IMAGE_TAG_PATTERN.match(tag)
                    if match:
                        compat_versions.add(match.group(1))
                next_link: str | None = None
                if "next" in tags_response.links and "url" in tags_response.links["next"]:
                    next_link = tags_response.links["next"]["url"]
                if next_link and next_link.startswith("/"):
                    next_url = f"https://{host}{next_link}"
                else:
                    next_url = next_link
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Unable to fetch compat versions from {registry}") from exc

    return _sort_compat_versions(compat_versions)
