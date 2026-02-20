from sqlmodel import select

from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.service_accounts import ServiceAccount, TokenPrefixType
from metta.app_backend.service_accounts import ServiceAccountUser, get_token_hash

ADMIN_SERVICE_ACCOUNT_PREFIXES = [TokenPrefixType.SOFTMAX]


@with_db
async def get_service_account_user(token: str) -> ServiceAccountUser | None:
    hashed_token = get_token_hash(token)
    session = get_db()
    service_account = (
        await session.execute(select(ServiceAccount).where(ServiceAccount.token_hash == hashed_token))
    ).scalar_one_or_none()

    if service_account is None:
        return None

    return ServiceAccountUser(
        id=service_account.user_id,
        is_softmax_team_member=service_account.token_prefix in ADMIN_SERVICE_ACCOUNT_PREFIXES,
    )
