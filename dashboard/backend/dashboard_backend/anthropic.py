from dataclasses import dataclass

import httpx

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
