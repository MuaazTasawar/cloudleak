"""
Centralized application configuration for CloudLeak.

Loads settings from environment variables (via a local .env file in
development, or real environment variables when deployed). All other
modules should import `settings` from here rather than reading
os.environ directly.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # AWS
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "eu-north-1"

    # DynamoDB tables
    DYNAMODB_TABLE_SPEND: str = "cloudleak-spend-baseline"
    DYNAMODB_TABLE_ANOMALIES: str = "cloudleak-anomalies"
    DYNAMODB_TABLE_RESOURCES: str = "cloudleak-flagged-resources"

    # Slack alerting
    SLACK_WEBHOOK_URL: str = ""

    # Anomaly detection tuning
    ANOMALY_ZSCORE_THRESHOLD: float = 2.5
    COST_BASELINE_DAYS: int = 7

    # Idle resource heuristics
    IDLE_CPU_THRESHOLD_PERCENT: float = 5.0
    IDLE_NETWORK_THRESHOLD_BYTES: int = 1_000_000
    IDLE_HOURS_THRESHOLD: int = 6

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import and call this, don't instantiate Settings() directly."""
    return Settings()


settings = get_settings()