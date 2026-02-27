import base64
import hashlib
import secrets

from pydantic import BaseModel

from metta.app_backend.models.service_accounts import TokenPrefixType


class ServiceAccountUser(BaseModel):
    id: str
    is_softmax_team_member: bool

    @property
    def email(self) -> str:
        postfix = "admin" if self.is_softmax_team_member else "external"
        return f"{postfix}+{self.id}@serviceaccounts.softmax.com"


def validate_token_prefix(value: str) -> TokenPrefixType:
    try:
        return TokenPrefixType(value)
    except ValueError as e:
        raise ValueError(
            f"Invalid token_prefix: {value!r}. Must be one of: {', '.join(e.value for e in TokenPrefixType)}"
        ) from e


def parse_token_prefix(user_token: str) -> tuple[TokenPrefixType, str]:
    """
    Generates a (prefix, token) tuple where prefix
    has been validated against TokenPrefixType.

    Use prefix to determine authorization level.
    """
    # token may contain more than one _
    [prefix, *token] = user_token.split("_")
    return (validate_token_prefix(prefix + "_"), "_".join(token))


def generate_token_preview(user_token: str) -> str:
    (prefix, token) = parse_token_prefix(user_token)
    return f"{prefix}....{token[-5:]}"


def generate_token_pair(prefix: TokenPrefixType = TokenPrefixType.SOFTMAX) -> tuple[str, str]:
    """
    Generates a (token, hashed_token) key pair. Hashed tokens are stored in
    the database, token is returned for one-time sharing to the caller.

    Args:
        prefix: TokenPrefixType (default="ssa_"), a prefix that must end with _
    """
    validate_token_prefix(prefix)
    raw = secrets.token_bytes(32)  # 256bit
    b64_encoded = base64.urlsafe_b64encode(raw).decode()
    token = f"{prefix}{b64_encoded}"
    hashed_token = hashlib.sha256(raw).hexdigest()
    return (token, hashed_token)


def get_token_hash(user_token: str) -> str:
    """
    Generate a SHA256
    """
    (_, token) = parse_token_prefix(user_token)
    b64_decoded = base64.urlsafe_b64decode(token)
    return hashlib.sha256(b64_decoded).hexdigest()


def compare_tokens(given: str, stored: str) -> bool:
    """
    Compares an un-hashed, prefixed token with a token
    that is stored in the db (hashed and unprefixed)

    Raises if:
        - Token prefix is not a known prefix
        - Encode/Decode/Hash fails
    """
    return get_token_hash(given) == stored
