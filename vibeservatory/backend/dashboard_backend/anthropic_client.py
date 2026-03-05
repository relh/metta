from dataclasses import dataclass

import anthropic
import httpx
from anthropic import AsyncAnthropicBedrock
from anthropic.types import TextBlock

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicTimeoutError(Exception):
    pass


class AnthropicConnectionError(Exception):
    pass


@dataclass(slots=True)
class AnthropicHTTPError(Exception):
    status_code: int
    response_text: str


@dataclass(slots=True)
class AnthropicResponseFormatError(Exception):
    response_body: object


async def request_anthropic_message(
    *,
    api_key: str,
    prompt: str,
    model: str,
    max_tokens: int,
    timeout: float,
) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ANTHROPIC_URL,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
            response.raise_for_status()
    except httpx.TimeoutException as e:
        raise AnthropicTimeoutError from e
    except httpx.HTTPStatusError as e:
        raise AnthropicHTTPError(status_code=e.response.status_code, response_text=e.response.text) from e
    except httpx.ConnectError as e:
        raise AnthropicConnectionError from e

    data = response.json()
    try:
        return data["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise AnthropicResponseFormatError(response_body=data) from e


async def request_bedrock_message(
    *,
    prompt: str,
    model: str,
    max_tokens: int,
    timeout: float,
) -> str:
    """Call Claude via AWS Bedrock. Uses the default AWS credential chain (IAM role, env vars, etc.)."""
    client = AsyncAnthropicBedrock()
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout,
        )
    except anthropic.APITimeoutError as e:
        raise AnthropicTimeoutError from e
    except anthropic.APIStatusError as e:
        raise AnthropicHTTPError(status_code=e.status_code, response_text=str(e.body)) from e
    except anthropic.APIConnectionError as e:
        raise AnthropicConnectionError from e

    text_block = next((b for b in response.content if isinstance(b, TextBlock)), None)
    if text_block is None:
        raise AnthropicResponseFormatError(response_body=response.model_dump())
    return text_block.text.strip()
