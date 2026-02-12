"""Configuration management for Trading Notification Bot."""

import os
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ConfigDict


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="",
    )

    # Trading Data Hub API
    api_base_url: str = Field(
        default="https://trading-data-hub.nanybot.com/api/v1/data",
        description="Base URL for Trading Data Hub API",
    )
    api_username: str = Field(default="admin", description="API username")
    api_password: str = Field(default="", description="API password")

    # OpenAI API (for AI-generated content)
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model to use")
    openai_max_tokens: int = Field(default=150, description="Max tokens for AI generation")

    # Twitter/X API
    twitter_api_key: str = Field(default="", description="Twitter API Key (Consumer Key)")
    twitter_api_secret: str = Field(
        default="", description="Twitter API Secret (Consumer Secret)"
    )
    twitter_bearer_token: str = Field(default="", description="Twitter Bearer Token")
    twitter_access_token: str = Field(default="", description="Twitter Access Token")
    twitter_access_token_secret: str = Field(
        default="", description="Twitter Access Token Secret"
    )
    twitter_proxy: str = Field(
        default="", description="Proxy URL for Twitter API requests (optional)"
    )

    # Discord
    discord_webhooks: str = Field(
        default="", description="Comma-separated Discord webhook URLs"
    )

    @field_validator("discord_webhooks")
    @classmethod
    def parse_discord_webhooks(cls, v: str) -> List[str]:
        """Parse comma-separated webhook URLs."""
        if not v:
            return []
        return [url.strip() for url in v.split(",") if url.strip()]

    # Rate Limits
    twitter_max_posts_per_minute: int = Field(
        default=1, description="Max Twitter posts per minute"
    )
    twitter_max_posts_per_day: int = Field(default=15, description="Max Twitter posts per day")

    # Schedule Intervals (in minutes, 0 = disabled)
    schedule_cnn_fear_greed: int = Field(default=240, description="CNN Fear & Greed interval")
    schedule_reddit_trending: int = Field(default=120, description="Reddit Trending interval")
    schedule_top_gainers: int = Field(default=60, description="Top Gainers interval")
    schedule_sector_performance: int = Field(
        default=1440, description="Sector Performance interval"
    )
    schedule_vix: int = Field(default=360, description="VIX interval")
    schedule_economic_calendar: int = Field(
        default=1440, description="Economic Calendar interval"
    )
    schedule_sec_insider: int = Field(default=1440, description="SEC Insider Trading interval")
    schedule_yahoo_finance: int = Field(default=30, description="Yahoo Finance interval")

    # Benzinga (Premium Data - Higher Priority)
    schedule_benzinga_news: int = Field(default=30, description="Benzinga Breaking News interval")
    schedule_benzinga_ratings: int = Field(default=60, description="Benzinga Analyst Ratings interval")
    schedule_benzinga_earnings: int = Field(default=120, description="Benzinga Earnings Calendar interval")

    # Market Hours (Eastern Time)
    market_open_hour: int = Field(default=9, ge=0, le=23)
    market_open_minute: int = Field(default=30, ge=0, le=59)
    market_close_hour: int = Field(default=16, ge=0, le=23)
    market_close_minute: int = Field(default=0, ge=0, le=59)

    # Timezone
    timezone: str = Field(default="America/New_York", description="Timezone for scheduling")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_rotation: str = Field(default="daily", description="Log rotation interval")
    log_retention_days: int = Field(default=30, description="Days to keep logs")

    # Health Monitoring
    health_check_port: int = Field(default=8080, description="Port for health check endpoint")
    alert_no_posts_hours: int = Field(
        default=4, description="Alert if no posts in X hours"
    )
    alert_error_rate_threshold: float = Field(
        default=0.10, description="Alert if error rate exceeds threshold"
    )

    # Data Storage
    database_path: str = Field(
        default="data/post_history.db", description="Path to SQLite database"
    )
    chart_cache_path: str = Field(
        default="data/chart_cache", description="Path to chart cache directory"
    )
    chart_cache_max_age_hours: int = Field(
        default=24, description="Max age of cached charts in hours"
    )

    # Scheduler Mode
    use_optimal_schedule: bool = Field(
        default=True,
        description="Use optimal CRON-based schedule (True) or old interval-based (False)"
    )

    # Development
    dry_run: bool = Field(
        default=False, description="If True, don't actually post to platforms"
    )

    def __init__(self, **kwargs):
        """Initialize config and create necessary directories."""
        super().__init__(**kwargs)
        self._create_directories()

    def _create_directories(self):
        """Create necessary directories if they don't exist."""
        dirs = [
            Path(self.database_path).parent,
            Path(self.chart_cache_path),
            Path("logs"),
        ]
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_market_hours_only_endpoint(self) -> dict:
        """Return endpoints that should only run during market hours."""
        return {
            "top_gainers": self.schedule_top_gainers > 0,
            "yahoo_finance": self.schedule_yahoo_finance > 0,
        }

    @property
    def discord_webhook_urls(self) -> List[str]:
        """Get parsed Discord webhook URLs."""
        if isinstance(self.discord_webhooks, list):
            return self.discord_webhooks
        if isinstance(self.discord_webhooks, str):
            return [url.strip() for url in self.discord_webhooks.split(",") if url.strip()]
        return []

    def validate_required_credentials(self) -> List[str]:
        """Validate that required credentials are present. Returns list of missing fields."""
        missing = []

        # API credentials
        if not self.api_password:
            missing.append("API_PASSWORD")

        # Twitter credentials
        if not self.twitter_api_key:
            missing.append("TWITTER_API_KEY")
        if not self.twitter_api_secret:
            missing.append("TWITTER_API_SECRET")
        if not self.twitter_access_token:
            missing.append("TWITTER_ACCESS_TOKEN")
        if not self.twitter_access_token_secret:
            missing.append("TWITTER_ACCESS_TOKEN_SECRET")

        # Discord webhooks
        if not self.discord_webhook_urls:
            missing.append("DISCORD_WEBHOOKS")

        return missing


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def load_config(env_file: str | None = None) -> Config:
    """Load configuration from environment file."""
    global _config
    if env_file:
        os.environ["ENV_FILE"] = env_file
    _config = Config()
    return _config
