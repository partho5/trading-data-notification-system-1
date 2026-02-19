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
    """Scheduler with dynamic CRON scheduling auto-adjusted to the active endpoint count.

    Discord: every endpoint posts on every scheduled run (no cap).
    Twitter: total daily posts capped at config.twitter_max_posts_per_day,
             distributed across endpoints by priority.
    Adding or removing an endpoint automatically rebalances the schedule.
    """

    # Endpoint configuration — no hardcoded times or frequencies.
    # 'window'      : 'full_day' (7:00–16:15) or 'market_hours' (9:30–15:30)
    # 'fixed_times' : [(hour, minute), ...] — bypasses dynamic time generation
    # 'max_daily'   : used with fixed_times; these slots are reserved first
    # 'day_of_week' : APScheduler CRON day-of-week string (e.g. "0,2,4")
    ENDPOINT_CONFIG = {
        # PREMIUM (Benzinga - client paid) — highest priority, gets most Twitter slots
        "benzinga_news": {
            "priority": EndpointPriority.PREMIUM,
            "api_method": "get_benzinga_news",
            "window": "full_day",
        },
        "benzinga_ratings": {
            "priority": EndpointPriority.PREMIUM,
            "api_method": "get_benzinga_ratings",
            "window": "full_day",
        },
        "benzinga_earnings": {
            "priority": EndpointPriority.PREMIUM,
            "api_method": "get_benzinga_earnings",
            "window": "full_day",
        },

        # MARKET (live data, market-hours only)
        "yahoo_quote": {
            "priority": EndpointPriority.MARKET,
            "api_method": "get_yahoo_finance_quote",
            "window": "market_hours",
            "market_hours_only": True,
        },
        "top_gainers": {
            "priority": EndpointPriority.MARKET,
            "api_method": "get_top_gainers",
            "window": "market_hours",
            "market_hours_only": True,
        },

        # ANALYSIS (sentiment)
        "reddit_trending": {
            "priority": EndpointPriority.ANALYSIS,
            "api_method": "get_reddit_trending",
            "window": "full_day",
        },
        "cnn_fear_greed": {
            "priority": EndpointPriority.ANALYSIS,
            "api_method": "get_cnn_fear_greed",
            "window": "full_day",
        },

        # DAILY_RECAP — fixed time, once per occurrence, reserves 1 Twitter slot each
        "sector_performance": {
            "priority": EndpointPriority.DAILY_RECAP,
            "api_method": "get_sector_performance",
            "fixed_times": [(16, 30)],   # After market close, every day
            "max_daily": 1,
        },
        "economic_calendar": {
            "priority": EndpointPriority.DAILY_RECAP,
            "api_method": "get_economic_calendar",
            "fixed_times": [(6, 30)],
            "max_daily": 1,
            "day_of_week": "0,2,4",      # Mon, Wed, Fri
        },
        "vix": {
            "priority": EndpointPriority.DAILY_RECAP,
            "api_method": "get_vix",
            "fixed_times": [(6, 30)],
            "max_daily": 1,
            "day_of_week": "1,3",        # Tue, Thu
        },
        "sec_insider": {
            "priority": EndpointPriority.DAILY_RECAP,
            "api_method": "get_sec_insider_filings",
            "fixed_times": [(6, 30)],
            "max_daily": 1,
            "day_of_week": "5,6",        # Sat, Sun
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
            "reddit_trending": lambda c: bool(c.get("trending_tickers")),
            "top_gainers": lambda c: bool(c.get("data")),
            "sec_insider": lambda c: bool(c.get("filings")),
            "economic_calendar": lambda c: bool(c.get("upcoming_earnings")),
            "yahoo_quote": lambda c: bool(c if isinstance(c, list) else c.get("quotes")),
            "sector_performance": lambda c: bool(c.get("sectors") or c.get("leaders")),
        }

        # If we have a specific check for this endpoint, use it
        if endpoint_name in empty_checks:
            return empty_checks[endpoint_name](content)

        # Default: assume has content if we got here
        return True

    @staticmethod
    def _generate_times(n_slots: int, window: str) -> List[tuple]:
        """Generate N evenly-spaced (hour, minute) tuples across a posting window.

        Args:
            n_slots: Number of posting slots required
            window:  'full_day' (7:00–16:15 ET) or 'market_hours' (9:30–15:30 ET)

        Returns:
            List of (hour, minute) tuples
        """
        if n_slots <= 0:
            return []

        windows = {
            "full_day":     (7 * 60,       16 * 60 + 15),  # 7:00 – 16:15
            "market_hours": (9 * 60 + 30,  15 * 60 + 30),  # 9:30 – 15:30
        }
        start, end = windows.get(window, windows["full_day"])

        if n_slots == 1:
            return [(start // 60, start % 60)]

        interval = (end - start) / (n_slots - 1)
        times = []
        for i in range(n_slots):
            t = round(start + i * interval)
            times.append((t // 60, t % 60))
        return times

    def _allocate_slots(self) -> Dict[str, int]:
        """Dynamically allocate Twitter posting slots across active endpoints.

        Fixed (once-daily) endpoints always reserve their max_daily slots first.
        The remaining cap is distributed to flexible endpoints by priority —
        higher-priority endpoints receive more slots when there is a remainder.
        If the cap is exhausted, lower-priority endpoints get 0 Twitter slots
        (they still post to Discord on every scheduled run).

        Returns:
            Dict mapping endpoint_name -> number of Twitter slots per day
        """
        daily_cap = self.config.twitter_max_posts_per_day

        fixed_eps = [
            ep for ep in self.active_endpoints
            if self.ENDPOINT_CONFIG[ep].get("max_daily") is not None
        ]
        flexible_eps = [ep for ep in self.active_endpoints if ep not in fixed_eps]

        allocation: Dict[str, int] = {}

        # Fixed endpoints always get exactly their max_daily
        for ep in fixed_eps:
            allocation[ep] = self.ENDPOINT_CONFIG[ep]["max_daily"]

        remaining = daily_cap - sum(allocation.values())
        n_flex = len(flexible_eps)

        if n_flex == 0:
            return allocation

        if remaining <= 0:
            # Cap already consumed by fixed endpoints — flexible are Discord-only
            for ep in flexible_eps:
                allocation[ep] = 0
            return allocation

        # Base slots per flexible endpoint, remainder to highest-priority first
        base = remaining // n_flex
        extra = remaining % n_flex

        sorted_flex = sorted(
            flexible_eps,
            key=lambda ep: self.ENDPOINT_CONFIG[ep]["priority"].value,
        )
        for i, ep in enumerate(sorted_flex):
            allocation[ep] = base + (1 if i < extra else 0)

        return allocation

    async def _post_content(self, endpoint_name: str, data: Dict[str, Any], chart_url: Optional[str] = None):
        """Post content to Twitter and Discord with deduplication and rate limiting.

        Args:
            endpoint_name: Name of the endpoint
            data: API response data
            chart_url: Optional chart image URL to download and attach
        """
        if not data.get("success"):
            logger.warning(f"API request failed for {endpoint_name}, skipping post")
            return

        # Check if data is actually empty BEFORE calling AI
        # Don't waste AI calls or post slots on empty responses
        if not self._has_content(endpoint_name, data):
            logger.info(f"No data available for {endpoint_name}, skipping (empty response)")
            return

        # Download chart if available
        chart_path = None
        if chart_url and self.chart_handler:
            chart_path = await self.chart_handler.download_chart(chart_url)

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

        # Post to Discord
        try:
            # Check for duplicate on Discord
            if self.deduplicator.is_duplicate(data, endpoint_name, "discord"):
                logger.info(f"Duplicate content for {endpoint_name} on Discord, skipping")
                self.stats["skipped_duplicates"] += 1
            else:
                # Discord (no rate limit for webhooks)
                if discord_description:
                    # Create proper embed with AI-generated description
                    endpoint_titles = {
                        "benzinga_news": "📰 Benzinga News",
                        "benzinga_ratings": "⭐ Analyst Ratings",
                        "benzinga_earnings": "📊 Earnings Report",
                        "yahoo_quote": "📈 Market Update",
                        "top_gainers": "🚀 Top Gainers",
                        "reddit_trending": "🔥 Reddit Trending",
                        "cnn_fear_greed": "📊 Market Sentiment",
                        "sector_performance": "🏢 Sector Performance",
                        "vix": "📉 Volatility Index",
                        "economic_calendar": "📅 Economic Calendar",
                        "sec_insider": "📝 SEC Insider Trading",
                    }
                    title = endpoint_titles.get(endpoint_name, "📊 Market Update")
                    discord_embed = self.discord_formatter.create_embed(
                        title=title,
                        description=discord_description,
                        color=0x3498DB,
                        timestamp=datetime.now(),
                    )
                    await self.discord_client.post_embed(discord_embed, chart_path)
                else:
                    discord_embed = self._format_for_discord(endpoint_name, data)
                    await self.discord_client.post_embed(discord_embed, chart_path)

                # Record successful Discord post
                self.deduplicator.record_post(data, endpoint_name, "discord")
                logger.info(f"Posted to Discord: {endpoint_name}")
        except Exception as e:
            logger.error(f"Discord posting error for {endpoint_name}: {e}")
            self.stats["failed_posts"] += 1

        # Post to Twitter
        try:
            # Check for duplicate on Twitter
            if self.deduplicator.is_duplicate(data, endpoint_name, "twitter"):
                logger.info(f"Duplicate content for {endpoint_name} on Twitter, skipping")
                self.stats["skipped_duplicates"] += 1
            else:
                can_post, rate_limit_reason = self.rate_limiter.can_post()
                if can_post:
                    if not self.config.dry_run:
                        success = self.twitter_client.post_tweet(twitter_text, chart_path)
                        if success:
                            self.rate_limiter.record_post()

                            # Record successful Twitter post
                            self.deduplicator.record_post(data, endpoint_name, "twitter")
                            logger.info(f"Posted to Twitter: {endpoint_name}")
                        else:
                            logger.error(f"Failed to post to Twitter: {endpoint_name}")
                            self.stats["failed_posts"] += 1
                            return
                    else:
                        logger.info(f"[DRY RUN] Would post to Twitter: {twitter_text[:100]}...")

                    self.stats["successful_posts"] += 1
                else:
                    logger.warning(f"Rate limit reached, skipping Twitter post for {endpoint_name}: {rate_limit_reason}")
                    self.stats["rate_limit_blocks"] += 1
        except Exception as e:
            logger.error(f"Twitter posting error for {endpoint_name}: {e}")
            self.stats["failed_posts"] += 1

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

            # Extract chart URL from response (present on CNN, Reddit, Gainers, Sector endpoints)
            data_payload = data.get("data")
            chart_url = data_payload.get("graphics") if isinstance(data_payload, dict) else None

            # Post content
            await self._post_content(endpoint_name, data, chart_url)

        except Exception as e:
            logger.error(f"Job error for {endpoint_name}: {e}")

    def add_jobs(self):
        """Add all scheduled jobs with dynamically computed CRON triggers.

        Twitter allocation is derived from config.twitter_max_posts_per_day
        and spread across active endpoints by priority.
        Discord receives every scheduled run regardless of Twitter limits.
        Calling this again (e.g. after add_endpoint/remove_endpoint) is safe
        because replace_existing=True is used on every job.
        """
        allocation = self._allocate_slots()
        total_twitter = sum(allocation.values())

        logger.info("=" * 60)
        logger.info(
            f"Dynamic schedule: {len(self.active_endpoints)} endpoint types, "
            f"{total_twitter} Twitter posts/day "
            f"(cap={self.config.twitter_max_posts_per_day})"
        )
        logger.info("Discord: ALL types posted on every scheduled run (no cap)")
        logger.info("=" * 60)

        for endpoint_name in self.active_endpoints:
            ep_config = self.ENDPOINT_CONFIG[endpoint_name]
            api_method = ep_config["api_method"]
            market_hours_only = ep_config.get("market_hours_only", False)
            day_of_week = ep_config.get("day_of_week")
            n_twitter = allocation[endpoint_name]

            # Determine posting times
            if "fixed_times" in ep_config:
                times = ep_config["fixed_times"]
            elif n_twitter > 0:
                times = self._generate_times(n_twitter, ep_config.get("window", "full_day"))
            else:
                # 0 Twitter slots — still schedule 2 runs/day for Discord
                times = self._generate_times(2, ep_config.get("window", "full_day"))

            for hour, minute in times:
                job_id = f"{endpoint_name}_{hour:02d}{minute:02d}"

                if day_of_week:
                    trigger = CronTrigger(
                        hour=hour, minute=minute,
                        day_of_week=day_of_week, timezone=self.tz,
                    )
                else:
                    trigger = CronTrigger(hour=hour, minute=minute, timezone=self.tz)

                self.scheduler.add_job(
                    self._execute_job,
                    trigger=trigger,
                    args=[endpoint_name, api_method, market_hours_only],
                    id=job_id,
                    name=f"{endpoint_name} @ {hour:02d}:{minute:02d} ET",
                    replace_existing=True,
                )

                logger.info(
                    f"✓ {endpoint_name:20s} @ {hour:02d}:{minute:02d} ET"
                    f"  [{ep_config['priority'].name}]"
                    f"  [twitter={n_twitter}/day  discord=all]"
                )

        # Cleanup at midnight — does not count toward daily limit
        self.scheduler.add_job(
            self.job_cleanup,
            trigger=CronTrigger(hour=0, minute=0, timezone=self.tz),
            id="cleanup",
            name="Daily Cleanup",
            replace_existing=True,
        )
        logger.info("✓ cleanup @ 00:00 ET [SYSTEM]")

        logger.info("=" * 60)
        logger.info(
            f"Twitter: {total_twitter} posts/day across "
            f"{len(self.active_endpoints)} endpoint types"
        )
        logger.info(
            f"Discord: all {len(self.active_endpoints)} types, "
            f"every run, no cap"
        )
        logger.info(f"Window: 6:30 AM – 4:30 PM {self.config.timezone}")
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
        """Get human-readable schedule summary derived from current dynamic allocation."""
        allocation = self._allocate_slots()
        schedule = []

        for endpoint_name in self.active_endpoints:
            ep_config = self.ENDPOINT_CONFIG[endpoint_name]
            n_twitter = allocation[endpoint_name]

            if "fixed_times" in ep_config:
                times = ep_config["fixed_times"]
            elif n_twitter > 0:
                times = self._generate_times(n_twitter, ep_config.get("window", "full_day"))
            else:
                times = self._generate_times(2, ep_config.get("window", "full_day"))

            for hour, minute in times:
                schedule.append({
                    "time": f"{hour:02d}:{minute:02d} ET",
                    "endpoint": endpoint_name,
                    "priority": ep_config["priority"].name,
                    "twitter_slots_per_day": n_twitter,
                    "discord": "always",
                    "day_of_week": ep_config.get("day_of_week", "daily"),
                })

        schedule.sort(key=lambda x: x["time"])
        return schedule

    # === Dynamic Adjustment Methods ===

    def add_endpoint(self, endpoint_name: str, config: Dict[str, Any]):
        """Dynamically add a new endpoint and rebalance the full schedule.

        Args:
            endpoint_name: New endpoint name
            config: Endpoint configuration dict (same structure as ENDPOINT_CONFIG)
        """
        self.ENDPOINT_CONFIG[endpoint_name] = config
        self.active_endpoints.append(endpoint_name)
        self._rebalance_schedule()
        logger.info(f"Added endpoint '{endpoint_name}', schedule rebalanced")

    def remove_endpoint(self, endpoint_name: str):
        """Dynamically remove an endpoint and rebalance the full schedule.

        Args:
            endpoint_name: Endpoint to remove
        """
        if endpoint_name in self.active_endpoints:
            self.active_endpoints.remove(endpoint_name)
            self._rebalance_schedule()
            logger.info(f"Removed endpoint '{endpoint_name}', schedule rebalanced")

    def _rebalance_schedule(self):
        """Remove all non-system CRON jobs and re-add with freshly computed allocation.

        Called automatically by add_endpoint() and remove_endpoint().
        Safe to call while the scheduler is running.
        """
        if not self.scheduler.running:
            return

        # Remove all dynamically generated jobs (keep cleanup)
        for job in self.scheduler.get_jobs():
            if job.id != "cleanup":
                job.remove()

        # Re-add with updated allocation
        self.add_jobs()
        logger.info(
            f"Schedule rebalanced: {len(self.active_endpoints)} endpoints, "
            f"{sum(self._allocate_slots().values())} Twitter posts/day"
        )
