"""Validated settings shared by both scraping engines."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCRAPING_", env_file=".env", extra="ignore")

    max_pages: int = Field(default=2, ge=1)
    max_items: int | None = Field(default=None, ge=1)
    delay: float = Field(default=1.0, ge=0, allow_inf_nan=False)
    timeout: int = Field(default=30, ge=1)
    retries: int = Field(default=2, ge=0, le=10)
    headless: bool = True
    browser_binary: str | None = None
    selenium_url: str | None = None
    database_url: str | None = Field(default=None, repr=False)
