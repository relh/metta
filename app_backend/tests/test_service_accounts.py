import pytest

from metta.app_backend.service_accounts import (
    compare_tokens,
    generate_token_pair,
    generate_token_preview,
)


def test_generate_token_pair_default_prefix():
    token, hashed = generate_token_pair()
    assert token != hashed
    assert token.startswith("ssa_")


def test_generate_token_pair_failure():
    with pytest.raises(ValueError):
        generate_token_pair("UNKNOWNPREFIX")  # pyright: ignore[reportArgumentType]


def test_generate_token_preview():
    token, _ = generate_token_pair()
    preview = generate_token_preview(token)
    assert preview == f"ssa_....{token[-5:]}"


def test_compare_tokens():
    token_other, _ = generate_token_pair()
    token, hashed = generate_token_pair()

    result = compare_tokens(token, hashed)
    assert result

    result = compare_tokens(token_other, hashed)
    assert not result
