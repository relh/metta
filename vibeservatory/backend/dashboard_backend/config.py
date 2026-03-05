from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    STATS_DB_READ_ONLY_URI: str = "postgresql://postgres:password@127.0.0.1/metta"
    DASHBOARD_HOST: str = "127.0.0.1"
    DASHBOARD_PORT: int = 8010
    DASHBOARD_CORS_ORIGINS: str = "*"
    DASHBOARD_COGAMES_DIAGNOSE_ROOT: str | None = None

    DASHBOARD_AUTH_SECRET: str | None = None
    DASHBOARD_LOGIN_SERVICE_URL: str = "https://softmax.com"
    DASHBOARD_DEBUG_USER_EMAIL: str | None = None
    DASHBOARD_DEV_AUTH_BYPASS: bool = True

    ANTHROPIC_API_KEY: str | None = None


settings = Settings()
