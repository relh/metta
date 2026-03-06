from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatadogConfig(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
    )

    DD_SITE: str = Field(default="datadoghq.com", description="Datadog site")


datadog_config = DatadogConfig()
