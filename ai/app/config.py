from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from the environment; keys never leave this service."""

    model_config = SettingsConfigDict(env_file=None, extra='ignore')

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    deepgram_api_key: SecretStr | None = None

    # Shared with Django to verify short-lived service tokens.
    ai_service_secret: SecretStr = Field(...)
    token_audience: str = 'andromeda-ai'  # noqa: S105 - a JWT audience, not a secret
    token_issuer: str = 'andromeda-api'  # noqa: S105

    redis_url: str | None = None
    # Per-user daily token allowance across all AI features.
    daily_user_token_budget: int = 200_000
    # Background work Django does on nobody's behalf (search indexing).
    system_daily_token_budget: int = 20_000_000
    daily_user_audio_seconds: int = 1800
    provider_timeout_seconds: float = 25.0

    max_text_chars: int = 10_000
    # Path to the distilled moderation model (JSON from ai/distill/train.py); unset disables it.
    moderation_student_path: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
