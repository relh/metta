from pydantic import Field
from pydantic_settings import BaseSettings

DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST: tuple[str, ...] = (
    "reward",
    "miner.gained",
    "germanium.deposited",
    "silicon.deposited",
    "carbon.deposited",
    "oxygen.deposited",
    "heart.gained",
    "scout.gained",
    "scrambler.gained",
    "aligner.gained",
    "cell.visited",
    "junction.scrambled_by_agent",
    "junction.aligned_by_agent",
    "death",
)


class Settings(BaseSettings):
    """FastAPI backend settings, loaded from environment variables and .env file.

    There are two independent .env loading paths in Observatory:
    - This file (config.py): pydantic-settings loads .env for backend settings (DB URI, API keys).
    - cli.py (_base_env): dotenv_values loads .env for process-compose subprocess environments.
    Both are intentional — they serve different processes at different stages.
    """

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    STATS_DB_URI: str = "postgresql://postgres:password@127.0.0.1/metta"
    STATS_DB_READ_ONLY_URI: str | None = None
    OBSERVATORY_AUTH_SECRET: str | None = None
    DEBUG_USER_EMAIL: str | None = None  # if set, you can set machine_token to this value and it will be accepted
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    ANTHROPIC_API_KEY: str | None = None
    LOGIN_SERVICE_URL: str = "https://softmax.com"
    RUN_MIGRATIONS: bool = Field(default=False, description="Run migrations on startup")
    SMART_PLUGS_ENABLED: bool = Field(default=False, description="Enable smart plug control routes")
    SMART_PLUGS_ALLOW_WRITE: bool = Field(default=False, description="Allow on/off actions for smart plugs")
    SMART_PLUGS_CONFIG_JSON: str | None = None

    LOCAL_DEV: bool = False


settings = Settings()
