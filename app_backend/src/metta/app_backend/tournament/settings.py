from pydantic_settings import BaseSettings

DEFAULT_SEASON: str = "beta-cvc"

POLL_INTERVAL_SECONDS: float = 30.0
POLL_INTERVAL_FAST_SECONDS: float = 2.0
MAX_OUTSTANDING_MATCHES_PER_SEASON: int = 50
PROMOTION_MIN_SCORE: float = 0.1

# Job timeout for episode runner k8s jobs. Worst case: 10k steps, 4 agents in
# sequence, 250ms each = 10k seconds (~2.8h), so 3h gives some headroom.
JOB_TIMEOUT_SECONDS: int = 3 * 60 * 60


class CommissionerSettings(BaseSettings):
    STATS_SERVER_URI: str = "http://localhost:8000"
    STATS_DB_URI: str = "postgres://postgres:password@127.0.0.1:5432/metta"
    MACHINE_TOKEN: str | None = None
    ENABLE_MOCK_TOURNAMENTS: bool = False
    GIT_COMMIT: str | None = None


settings = CommissionerSettings()
