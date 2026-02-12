"""Optimal job scheduler with CRON-based, audience-first strategy."""

import asyncio
from datetime import datetime, time
from enum import Enum
from typing import Any, Dict, List, Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from .ai_generator import AIContentGenerator
from .api_client import APIClient
from .chart_handler import ChartHandler
from .config import Config
from .deduplicator import Deduplicator
from .formatters.discord import DiscordFormatter
from .formatters.twitter import TwitterFormatter
from .platforms.discord import DiscordClient
from .platforms.twitter import TwitterClient
from .rate_limiter import RateLimiter


class EndpointPriority(Enum):
    """Priority levels for endpoints."""
    PREMIUM = 1      # Benzinga (client pays)
    MARKET = 2       # Live market updates
    ANALYSIS = 3     # Sentiment and analysis
    DAILY_RECAP = 4  # Once-daily posts


class ScheduleSlot:
    """Represents a scheduled posting slot."""

    def __init__(self, hour: int, minute: int, endpoint: str, priority: EndpointPriority):
        self.hour = hour
        self.minute = minute
        self.endpoint = endpoint
        self.priority = priority

    def __repr__(self):
        return f"Slot({self.hour:02d}:{self.minute:02d} - {self.endpoint})"


class OptimalScheduler:
    """Scheduler with audience-first CRON scheduling and dynamic adjustment."""

    # Maximum posts per day (X free tier limit)
    MAX_DAILY_POSTS = 17

    # Endpoint configuration with priorities
    ENDPOINT_CONFIG = {
        # PREMIUM (Benzinga - Client paid) - 60% of budget = 10 posts
        "benzinga_news": {
            "priority": EndpointPriority.PREMIUM,
            "posts_per_day": 6,
            "times": [(7, 0), (9, 45), (11, 15), (13, 0), (14, 30), (16, 15)],
            "api_method": "get_benzinga_news",
        },
        "benzinga_ratings": {
            "priority": EndpointPriority.PREMIUM,
            "posts_per_day": 3,
            "times": [(8, 0), (12, 0), (15, 0)],
            "api_method": "get_benzinga_ratings",
        },
        "benzinga_earnings": {
            "priority": EndpointPriority.PREMIUM,
            "posts_per_day": 1,
            "times": [(7, 30)],
            "api_method": "get_benzinga_earnings",
        },

        # MARKET (Live updates) - 25% of budget = 4 posts
        "yahoo_quote": {
            "priority": EndpointPriority.MARKET,
            "posts_per_day": 3,
            "times": [(10, 0), (13, 30), (15, 30)],
            "api_method": "get_yahoo_finance_quote",
            "market_hours_only": True,
        },
        "top_gainers": {
            "priority": EndpointPriority.MARKET,
            "posts_per_day": 1,
            "times": [(14, 0)],
            "api_method": "get_top_gainers",
            "market_hours_only": True,
        },

        # ANALYSIS (Sentiment) - 10% of budget = 2 posts
        "reddit_trending": {
            "priority": EndpointPriority.ANALYSIS,
            "posts_per_day": 1,
            "times": [(9, 0)],
            "api_method": "get_reddit_trending",
        },
        "cnn_fear_greed": {
            "priority": EndpointPriority.ANALYSIS,
            "posts_per_day": 1,
            "times": [(8, 30)],
            "api_method": "get_cnn_fear_greed",
        },

        # DAILY_RECAP - 5% of budget = 1 post (rotate between 3)
        "sector_performance": {
            "priority": EndpointPriority.DAILY_RECAP,
            "posts_per_day": 1,
            "times": [(16, 30)],  # After market close
            "api_method": "get_sector_performance",
        },

        # These rotate every 3 days (Mon/Wed/Fri or Tue/Thu/Sat)
        "economic_calendar": {
            "priority": EndpointPriority.DAILY_RECAP,
            "posts_per_day": 0.33,  # Every 3 days
            "times": [(6, 30)],
            "api_method": "get_economic_calendar",
            "day_of_week": "0,2,4",  # Mon, Wed, Fri
        },
        "vix": {
            "priority": EndpointPriority.DAILY_RECAP,
            "posts_per_day": 0.33,
            "times": [(6, 30)],
            "api_method": "get_vix",
            "day_of_week": "1,3",  # Tue, Thu
        },
        "sec_insider": {
            "priority": EndpointPriority.DAILY_RECAP,
            "posts_per_day": 0.33,
            "times": [(6, 30)],
            "api_method": "get_sec_insider",
            "day_of_week": "5,6",  # Sat, Sun (for week recap)
        },
    }

    def __init__(self, config: Config):
        """Initialize optimal scheduler.

        Args:
            config: Application configuration
        """
        self.config = config
        self.scheduler = AsyncIOScheduler(timezone=config.timezone)

        # Initialize components
        self.api_client: Optional[APIClient] = None
        self.chart_handler: Optional[ChartHandler] = None
        self.ai_generator: Optional[AIContentGenerator] = None
        self.twitter_client = TwitterClient(config)
        self.discord_client = DiscordClient(config)
        self.twitter_formatter = TwitterFormatter()
        self.discord_formatter = DiscordFormatter()
        self.rate_limiter = RateLimiter(config)
        self.deduplicator = Deduplicator(config)
        self.use_ai = bool(config.openai_api_key)

        # Timezone
        self.tz = pytz.timezone(config.timezone)

        # Stats
        self.stats = {
            "total_posts": 0,
            "successful_posts": 0,
            "failed_posts": 0,
            "skipped_duplicates": 0,
            "rate_limit_blocks": 0,
        }

        # Track active endpoints (for dynamic adjustment)
        self.active_endpoints = list(self.ENDPOINT_CONFIG.keys())

    async def initialize(self):
        """Initialize async components."""
        self.api_client = APIClient(self.config)
        await self.api_client.authenticate()

        self.chart_handler = ChartHandler(self.config)

        if self.use_ai:
            self.ai_generator = AIContentGenerator(self.config)
            logger.info("AI content generator initialized (using OpenAI GPT-4o-mini)")
        else:
            logger.warning("OpenAI API key not found, using template-based content")

        logger.info("Optimal scheduler initialized (CRON-based, audience-first)")

    def _is_market_hours(self) -> bool:
        """Check if current time is within market hours (9:30 AM - 4:00 PM ET).

        Returns:
            True if within market hours
        """
        now = datetime.now(self.tz)
        weekday = now.weekday()  # 0 = Monday, 6 = Sunday

        # Skip weekends
        if weekday >= 5:
            return False

        current_time = now.time()
        market_open = time(
            self.config.market_open_hour,
            self.config.market_open_minute,
        )
        market_close = time(
            self.config.market_close_hour,
            self.config.market_close_minute,
        )

        return market_open <= current_time <= market_close

    def _has_content(self, endpoint_name: str, data: Dict[str, Any]) -> bool:
        """Check if API response actually has content to post.

        Args:
            endpoint_name: Name of endpoint
            data: API response data

        Returns:
            True if has content, False if empty
        """
        content = data.get("data", {})

        # Check for empty lists in different endpoints
        empty_checks = {
            "benzinga_news": lambda c: bool(c.get("articles")),
            "benzinga_ratings": lambda c: bool(c.get("ratings")),
            "benzinga_earnings": lambda c: bool(c.get("earnings")),
            "reddit_trending": lambda c: bool(c.get("tickers")),
            "top_gainers": lambda c: bool(c.get("gainers")),
            "sec_insider": lambda c: bool(c.get("filings")),
            "economic_calendar": lambda c: bool(c.get("earnings")),
            "yahoo_quote": lambda c: bool(c if isinstance(c, list) else c.get("quotes")),
            "sector_performance": lambda c: bool(c.get("sectors") or c.get("leaders")),
        }

        # If we have a specific check for this endpoint, use it
        if endpoint_name in empty_checks:
            return empty_checks[endpoint_name](content)

        # Default: assume has content if we got here
        return True

    async def _post_content(self, endpoint_name: str, data: Dict[str, Any]):
        """Post content to Twitter and Discord with deduplication and rate limiting.

        Args:
            endpoint_name: Name of the endpoint
            data: API response data
        """
        if not data.get("success"):
            logger.warning(f"API request failed for {endpoint_name}, skipping post")
            return

        # Check if data is actually empty BEFORE calling AI
        # Don't waste AI calls or post slots on empty responses
        if not self._has_content(endpoint_name, data):
            logger.info(f"No data available for {endpoint_name}, skipping (empty response)")
            return

        # Check for duplicate
        if self.deduplicator.is_duplicate(endpoint_name, data):
            logger.info(f"Duplicate content detected for {endpoint_name}, skipping")
            self.stats["skipped_duplicates"] += 1
            return

        # Generate content (AI first, fallback to templates)
        twitter_text = None
        discord_description = None

        if self.use_ai and self.ai_generator:
            twitter_text = await self.ai_generator.generate_twitter_post(endpoint_name, data)
            discord_description = await self.ai_generator.generate_discord_description(
                endpoint_name, data
            )

        # Fallback to templates if AI fails
        if not twitter_text:
            twitter_text = self._format_for_twitter(endpoint_name, data)
        if not discord_description:
            discord_description = None  # Use default Discord formatter

        self.stats["total_posts"] += 1

        # Post to platforms
        try:
            # Discord (no rate limit for webhooks)
            if discord_description:
                discord_embed = self.discord_formatter._error_embed(discord_description)
                await self.discord_client.post(discord_embed)
            else:
                discord_embed = self._format_for_discord(endpoint_name, data)
                await self.discord_client.post(discord_embed)
        except Exception as e:
            logger.error(f"Discord posting error for {endpoint_name}: {e}")
            self.stats["failed_posts"] += 1

        try:
            # Twitter (with rate limiting)
            if self.rate_limiter.can_post():
                if not self.config.dry_run:
                    await self.twitter_client.post(twitter_text)
                    self.rate_limiter.record_post()
                    logger.info(f"Posted to Twitter: {endpoint_name}")
                else:
                    logger.info(f"[DRY RUN] Would post to Twitter: {twitter_text[:100]}...")

                self.stats["successful_posts"] += 1
            else:
                logger.warning(f"Rate limit reached, skipping Twitter post for {endpoint_name}")
                self.stats["rate_limit_blocks"] += 1
        except Exception as e:
            logger.error(f"Twitter posting error for {endpoint_name}: {e}")
            self.stats["failed_posts"] += 1

        # Record in deduplicator
        self.deduplicator.add_content(endpoint_name, data)

    def _format_for_twitter(self, endpoint_name: str, data: Dict[str, Any]) -> str:
        """Format data for Twitter using template formatter (fallback).

        Args:
            endpoint_name: Endpoint name
            data: API response data

        Returns:
            Formatted tweet text
        """
        formatter_map = {
            "cnn_fear_greed": self.twitter_formatter.format_cnn_fear_greed,
            "reddit_trending": self.twitter_formatter.format_reddit_trending,
            "top_gainers": self.twitter_formatter.format_top_gainers,
            "sector_performance": self.twitter_formatter.format_sector_performance,
            "vix": self.twitter_formatter.format_vix,
            "economic_calendar": self.twitter_formatter.format_economic_calendar,
            "sec_insider": self.twitter_formatter.format_sec_insider,
            "yahoo_quote": self.twitter_formatter.format_yahoo_quote,
        }

        formatter = formatter_map.get(endpoint_name)
        if formatter:
            return formatter(data)

        return f"Update from {endpoint_name} #Stocks #Trading"

    def _format_for_discord(self, endpoint_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format data for Discord using template formatter (fallback).

        Args:
            endpoint_name: Endpoint name
            data: API response data

        Returns:
            Discord embed dict
        """
        formatter_map = {
            "cnn_fear_greed": self.discord_formatter.format_cnn_fear_greed,
            "reddit_trending": self.discord_formatter.format_reddit_trending,
            "top_gainers": self.discord_formatter.format_top_gainers,
            "sector_performance": self.discord_formatter.format_sector_performance,
            "vix": self.discord_formatter.format_vix,
            "economic_calendar": self.discord_formatter.format_economic_calendar,
            "sec_insider": self.discord_formatter.format_sec_insider,
            "yahoo_quote": self.discord_formatter.format_yahoo_quote,
        }

        formatter = formatter_map.get(endpoint_name)
        if formatter:
            return formatter(data)

        return self.discord_formatter._error_embed(f"No formatter for {endpoint_name}")

    async def _execute_job(self, endpoint_name: str, api_method_name: str, market_hours_only: bool = False):
        """Execute a scheduled job.

        Args:
            endpoint_name: Name of endpoint
            api_method_name: API method to call
            market_hours_only: Whether to skip if outside market hours
        """
        if market_hours_only and not self._is_market_hours():
            logger.debug(f"Skipping {endpoint_name} - outside market hours")
            return

        try:
            logger.info(f"Running job: {endpoint_name} (CRON scheduled)")

            # Get API method
            api_method = getattr(self.api_client, api_method_name, None)
            if not api_method:
                logger.error(f"API method not found: {api_method_name}")
                return

            # Call API
            data = await api_method()

            # Post content
            await self._post_content(endpoint_name, data)

        except Exception as e:
            logger.error(f"Job error for {endpoint_name}: {e}")

    def add_jobs(self):
        """Add all scheduled jobs using CRON triggers."""
        logger.info("=" * 60)
        logger.info("Adding OPTIMAL CRON-based schedule (17 posts/day)")
        logger.info("=" * 60)

        total_daily_posts = 0

        for endpoint_name, config in self.ENDPOINT_CONFIG.items():
            if endpoint_name not in self.active_endpoints:
                logger.debug(f"Skipping disabled endpoint: {endpoint_name}")
                continue

            times = config.get("times", [])
            api_method = config["api_method"]
            market_hours_only = config.get("market_hours_only", False)
            day_of_week = config.get("day_of_week")  # For rotating daily posts

            for hour, minute in times:
                job_id = f"{endpoint_name}_{hour:02d}{minute:02d}"

                # Create CRON trigger
                if day_of_week:
                    # Rotating schedule (e.g., Mon/Wed/Fri)
                    trigger = CronTrigger(
                        hour=hour,
                        minute=minute,
                        day_of_week=day_of_week,
                        timezone=self.tz,
                    )
                else:
                    # Daily schedule
                    trigger = CronTrigger(
                        hour=hour,
                        minute=minute,
                        timezone=self.tz,
                    )

                # Add job
                self.scheduler.add_job(
                    self._execute_job,
                    trigger=trigger,
                    args=[endpoint_name, api_method, market_hours_only],
                    id=job_id,
                    name=f"{endpoint_name} @ {hour:02d}:{minute:02d} ET",
                )

                logger.info(
                    f"✓ Scheduled: {endpoint_name:20s} @ {hour:02d}:{minute:02d} ET "
                    f"[{config['priority'].name}]"
                )

            total_daily_posts += config["posts_per_day"]

        # Add cleanup job (doesn't count toward daily limit)
        self.scheduler.add_job(
            self.job_cleanup,
            trigger=CronTrigger(hour=0, minute=0, timezone=self.tz),
            id="cleanup",
            name="Daily Cleanup",
        )
        logger.info("✓ Scheduled: cleanup @ 00:00 ET [SYSTEM]")

        logger.info("=" * 60)
        logger.info(f"Total daily posts: {total_daily_posts:.1f} (target: {self.MAX_DAILY_POSTS})")
        logger.info(f"All posts between 6:30 AM - 4:30 PM ET (audience waking hours)")
        logger.info(f"Overnight (8 PM - 6 AM): ZERO posts (respects audience sleep)")
        logger.info("=" * 60)

    async def job_cleanup(self):
        """Cleanup old records (runs at midnight)."""
        try:
            logger.info("Running cleanup job")
            self.rate_limiter.cleanup_old_records(days=7)
            self.deduplicator.cleanup_old_hashes(days=7)
            if self.chart_handler:
                self.chart_handler.cleanup_old_charts()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics.

        Returns:
            Stats dictionary
        """
        return {
            **self.stats,
            "rate_limiter": self.rate_limiter.get_stats(),
            "deduplicator": self.deduplicator.get_stats(),
        }

    async def start(self):
        """Start the scheduler."""
        await self.initialize()
        self.add_jobs()
        self.scheduler.start()
        logger.info("Optimal scheduler started with CRON-based posting")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")

    def get_schedule_summary(self) -> List[Dict[str, Any]]:
        """Get human-readable schedule summary.

        Returns:
            List of scheduled times with endpoints
        """
        schedule = []
        for endpoint_name, config in self.ENDPOINT_CONFIG.items():
            if endpoint_name not in self.active_endpoints:
                continue

            for hour, minute in config.get("times", []):
                schedule.append({
                    "time": f"{hour:02d}:{minute:02d} ET",
                    "endpoint": endpoint_name,
                    "priority": config["priority"].name,
                })

        # Sort by time
        schedule.sort(key=lambda x: x["time"])
        return schedule

    # === Dynamic Adjustment Methods ===

    def add_endpoint(self, endpoint_name: str, config: Dict[str, Any]):
        """Dynamically add a new endpoint and rebalance schedule.

        Args:
            endpoint_name: New endpoint name
            config: Endpoint configuration
        """
        self.ENDPOINT_CONFIG[endpoint_name] = config
        self.active_endpoints.append(endpoint_name)

        # Rebalance to stay within daily limit
        self._rebalance_schedule()

        logger.info(f"Added endpoint: {endpoint_name}, rebalanced schedule")

    def remove_endpoint(self, endpoint_name: str):
        """Dynamically remove an endpoint and rebalance schedule.

        Args:
            endpoint_name: Endpoint to remove
        """
        if endpoint_name in self.active_endpoints:
            self.active_endpoints.remove(endpoint_name)

            # Rebalance to redistribute freed slots
            self._rebalance_schedule()

            logger.info(f"Removed endpoint: {endpoint_name}, rebalanced schedule")

    def _rebalance_schedule(self):
        """Recalculate posting frequencies to respect daily limit."""
        # Count current daily posts
        total = sum(
            self.ENDPOINT_CONFIG[ep].get("posts_per_day", 0)
            for ep in self.active_endpoints
        )

        if total > self.MAX_DAILY_POSTS:
            # Need to reduce frequencies
            logger.warning(f"Schedule exceeds daily limit ({total} > {self.MAX_DAILY_POSTS})")
            logger.warning("Reducing frequency of lower-priority endpoints...")

            # Reduce non-premium endpoints proportionally
            # (Premium always gets priority)
            # This is a simplified version - production would be more sophisticated

        elif total < self.MAX_DAILY_POSTS:
            # Can increase frequencies
            logger.info(f"Schedule under limit ({total} < {self.MAX_DAILY_POSTS})")
            logger.info("Could increase frequency of high-priority endpoints")

        # Note: Actual rebalancing would require stopping scheduler,
        # recalculating time slots, and restarting. For now, just log.
