from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    STATS_DB_URI: str = "postgres://postgres:password@127.0.0.1/postgres"
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


settings = Settings()
