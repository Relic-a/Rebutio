import os
import secrets
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./rebutio.db"

    # Security & Encryption
    # In production, REBUTIO_DATA_ENCRYPTION_KEY must be a 32-byte hex/base64 key.
    # In local dev without env var, use a stable dev key to preserve data across restarts.
    REBUTIO_DATA_ENCRYPTION_KEY: str = Field(
        default_factory=lambda: os.getenv("REBUTIO_DATA_ENCRYPTION_KEY") or "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    )
    REBUTIO_SESSION_SECRET: str = Field(
        default_factory=lambda: os.getenv("REBUTIO_SESSION_SECRET") or "rebutio-stable-dev-session-secret-key-32b"
    )
    SESSION_COOKIE_NAME: str = "rebutio_session"
    SESSION_COOKIE_MAX_AGE_DAYS: int = 365
    COOKIE_SECURE: bool = False  # Set to True in production HTTPS

    # AI Gateways
    OPENROUTER_API_KEY: Optional[str] = None
    RAMP_ROUTER_API_KEY: Optional[str] = None

    # OpenRouter Role Models (defaults from architecture contract)
    OPENROUTER_TRANSCRIPTION_MODEL: str = "microsoft/mai-transcribe-1.5"
    OPENROUTER_DEBATE_MODEL: str = "deepseek/deepseek-v4-pro-0813:nitro"
    OPENROUTER_TTS_MODEL: str = "fish-audio/s2.1-pro"
    OPENROUTER_ANALYSIS_MODEL: str = "openai/gpt-5.6-luna-pro:nitro"
    OPENROUTER_FINAL_PATCH_MODEL: str = "openai/gpt-5.6-luna-pro:nitro"
    OPENROUTER_REVIEW_MODEL: str = "openai/gpt-5.6-luna-pro:nitro"
    OPENROUTER_TOPIC_MODEL: str = "deepseek/deepseek-v4-flash-0731:nitro"

    # Router.com / Ramp Router Models (optional per role)
    ROUTER_DEBATE_MODEL: Optional[str] = None
    ROUTER_ANALYSIS_MODEL: Optional[str] = None
    ROUTER_REVIEW_MODEL: Optional[str] = None
    ROUTER_TOPIC_MODEL: Optional[str] = None

    # Opponent Voice (optional, model-dependent)
    REBUTIO_TTS_VOICE: Optional[str] = None

    # Modal Speech Analysis
    MODAL_APP_NAME: str = "rebutio-speech-analysis"
    MODAL_FUNCTION_NAME: str = "SpeechAnalysisWorker.analyze_phonemes"

    # Retention & Privacy Policies
    EVIDENCE_RETENTION_HOURS: int = 24
    SAVE_TRANSCRIPTS_DEFAULT: bool = False

    # Observability & Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "console"  # "console" or "json"
    LOG_AI_CONTENT: bool = False  # Explicit development-only flag. NEVER enable in production.
    DB_SLOW_QUERY_MS: int = 500

    # Topic Inventory settings
    INVENTORY_TARGET_COUNT: int = 5
    INVENTORY_REFILL_THRESHOLD: int = 2


settings = Settings()
