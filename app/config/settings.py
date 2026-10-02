from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = Field(default="postgresql+psycopg://gateway@127.0.0.1:5432/gateway", repr=False)
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", repr=False)
    api_token: SecretStr
    instance_name: str = "WhatsApp QA"
    instance_phone_number: str | None = None
    adb_serial: str = "emulator-5554"
    adb_host: str = "127.0.0.1"
    adb_port: int = 5037
    adb_binary: str = "adb"
    appium_url: str = "http://127.0.0.1:4723"
    system_port: int = 8200
    whatsapp_package: str = "com.whatsapp"
    ui_language: str = "es"
    debug_automation: bool = False
    incoming_dir: Path = Path("/data/incoming")
    media_dir: Path = Path("/data/media")
    screenshot_dir: Path = Path("/data/screenshots")
    image_limit_bytes: int = 10 * 1024 * 1024
    av_limit_bytes: int = 16 * 1024 * 1024
    document_limit_bytes: int = 100 * 1024 * 1024
    lock_ttl_seconds: int = 90
    lock_renew_seconds: int = 15
    command_timeout_seconds: int = 25
    ui_wait_seconds: int = 20
    send_wait_seconds: int = 120
    task_time_limit_seconds: int = 300
    stale_processing_seconds: int = 360
    max_attempts: int = Field(default=3, ge=1, le=3)
    health_interval_seconds: int = 60
    debug_timeout_seconds: int = 10

    @field_validator("instance_phone_number", mode="before")
    @classmethod
    def empty_phone(cls, value):
        return value or None

    @model_validator(mode="after")
    def check_configuration(self):
        if len(self.api_token.get_secret_value()) < 32:
            raise ValueError("API_TOKEN must contain at least 32 characters")
        if self.ui_language not in {"es", "en"}:
            raise ValueError("UI_LANGUAGE must be es or en")
        if not (0 < self.lock_renew_seconds < self.lock_ttl_seconds / 3):
            raise ValueError("Lock renewal must be shorter than one third of TTL")
        if not (0 < self.command_timeout_seconds < self.lock_ttl_seconds / 2):
            raise ValueError("Command timeout must be shorter than half of lock TTL")
        if self.stale_processing_seconds <= self.task_time_limit_seconds:
            raise ValueError("Stale threshold must exceed the task time limit")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
