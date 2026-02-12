"""Job scheduler for automated trading data posting."""

import asyncio
from datetime import datetime, time
from typing import Any, Dict, Optional

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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


class TradingBotScheduler:
    """Scheduler for coordinating all trading data posting jobs."""

    def __init__(self, config: Config):
        """Initialize scheduler.

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
        self.twitter_formatter = TwitterFormatter()  # Fallback
        self.discord_formatter = DiscordFormatter()  # Fallback
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

        logger.info("Scheduler initialized")

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

    async def _post_content(
        self,
        endpoint_name: str,
        data: Dict[str, Any],
        chart_url: Optional[str] = None,
    ):
        """Post content to Twitter and Discord.

        Args:
            endpoint_name: Name of the API endpoint
            data: API response data
            chart_url: Optional chart URL to download
        """
        # Download chart if available
        chart_path = None
        if chart_url and self.chart_handler:
            chart_path = await self.chart_handler.download_chart(chart_url)

        # Post to Discord
        try:
            if not self.deduplicator.is_duplicate(data, endpoint_name, "discord"):
                # Try AI generation first, fallback to template
                if self.use_ai and self.ai_generator:
                    discord_description = await self.ai_generator.generate_discord_description(
                        endpoint_name, data
                    )
                    if discord_description:
                        # Create simple embed with AI-generated description
                        discord_embed = {
                            "title": self._get_embed_title(endpoint_name),
                            "description": discord_description,
                            "color": 0x3498DB,
                            "footer": {"text": "AI-powered market insights"},
                        }
                    else:
                        discord_embed = self._format_for_discord(endpoint_name, data)
                else:
                    discord_embed = self._format_for_discord(endpoint_name, data)

                if discord_embed:
                    success = await self.discord_client.post_embed(discord_embed, chart_path)
                    if success:
                        self.deduplicator.record_post(data, endpoint_name, "discord")
                        self.stats["successful_posts"] += 1
                        logger.info(f"Posted {endpoint_name} to Discord")
                    else:
                        self.stats["failed_posts"] += 1
            else:
                self.stats["skipped_duplicates"] += 1
                logger.info(f"Skipped duplicate {endpoint_name} for Discord")

        except Exception as e:
            logger.error(f"Discord posting error for {endpoint_name}: {e}")
            self.stats["failed_posts"] += 1

        # Post to Twitter (with rate limiting)
        try:
            can_post, reason = self.rate_limiter.can_post()

            if not can_post:
                logger.warning(f"Twitter rate limit: {reason}")
                self.stats["rate_limit_blocks"] += 1
                return

            if not self.deduplicator.is_duplicate(data, endpoint_name, "twitter"):
                # Try AI generation first, fallback to template
                if self.use_ai and self.ai_generator:
                    twitter_text = await self.ai_generator.generate_twitter_post(
                        endpoint_name, data
                    )
                    if not twitter_text:
                        twitter_text = self._format_for_twitter(endpoint_name, data)
                else:
                    twitter_text = self._format_for_twitter(endpoint_name, data)

                if twitter_text:
                    success = self.twitter_client.post_tweet(twitter_text, chart_path)
                    if success:
                        self.rate_limiter.record_post()
                        self.deduplicator.record_post(data, endpoint_name, "twitter")
                        self.stats["successful_posts"] += 1
                        logger.info(f"Posted {endpoint_name} to Twitter")
                    else:
                        self.stats["failed_posts"] += 1
            else:
                self.stats["skipped_duplicates"] += 1
                logger.info(f"Skipped duplicate {endpoint_name} for Twitter")

        except Exception as e:
            logger.error(f"Twitter posting error for {endpoint_name}: {e}")
            self.stats["failed_posts"] += 1

        self.stats["total_posts"] += 1

    def _get_embed_title(self, endpoint_name: str) -> str:
        """Get Discord embed title for endpoint.

        Args:
            endpoint_name: Name of endpoint

        Returns:
            Embed title string
        """
        titles = {
            "cnn_fear_greed": "📊 Market Sentiment Analysis",
            "reddit_trending": "🔥 Reddit Trending Stocks",
            "top_gainers": "📈 Top Stock Gainers",
            "sector_performance": "📊 Sector Performance",
            "vix": "📊 Market Volatility Update",
            "economic_calendar": "📅 Upcoming Earnings",
            "sec_insider": "👀 Insider Trading Activity",
            "yahoo_quote": "📊 Market Update",
            # Benzinga (Premium)
            "benzinga_news": "🚨 Breaking Market News",
            "benzinga_ratings": "⭐ Analyst Ratings Update",
            "benzinga_earnings": "📅 Earnings Calendar",
        }
        return titles.get(endpoint_name, "📊 Market Update")

    def _format_for_discord(self, endpoint_name: str, data: Dict[str, Any]) -> Optional[Dict]:
        """Format data for Discord based on endpoint.

        Args:
            endpoint_name: Name of endpoint
            data: API response data

        Returns:
            Discord embed dict or None
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
        return None

    def _format_for_twitter(self, endpoint_name: str, data: Dict[str, Any]) -> Optional[str]:
        """Format data for Twitter based on endpoint.

        Args:
            endpoint_name: Name of endpoint
            data: API response data

        Returns:
            Tweet text or None
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
        return None

    # ==================== Job Handlers ====================

    async def job_cnn_fear_greed(self):
        """Fetch and post CNN Fear & Greed Index."""
        try:
            logger.info("Running job: CNN Fear & Greed")
            data = await self.api_client.get_cnn_fear_greed(with_chart=True)
            chart_url = data.get("data", {}).get("graphics")
            await self._post_content("cnn_fear_greed", data, chart_url)
        except Exception as e:
            logger.error(f"CNN Fear & Greed job error: {e}")

    async def job_reddit_trending(self):
        """Fetch and post Reddit trending tickers."""
        try:
            logger.info("Running job: Reddit Trending")
            data = await self.api_client.get_reddit_trending(with_chart=True)
            chart_url = data.get("data", {}).get("graphics")
            await self._post_content("reddit_trending", data, chart_url)
        except Exception as e:
            logger.error(f"Reddit Trending job error: {e}")

    async def job_top_gainers(self):
        """Fetch and post top stock gainers."""
        if not self._is_market_hours():
            logger.debug("Skipping top gainers - outside market hours")
            return

        try:
            logger.info("Running job: Top Gainers")
            data = await self.api_client.get_top_gainers(limit=10, with_chart=True)
            chart_url = data.get("data", {}).get("graphics")
            await self._post_content("top_gainers", data, chart_url)
        except Exception as e:
            logger.error(f"Top Gainers job error: {e}")

    async def job_sector_performance(self):
        """Fetch and post sector performance."""
        try:
            logger.info("Running job: Sector Performance (takes ~13s)")
            data = await self.api_client.get_sector_performance(with_chart=True)
            chart_url = data.get("data", {}).get("graphics")
            await self._post_content("sector_performance", data, chart_url)
        except Exception as e:
            logger.error(f"Sector Performance job error: {e}")

    async def job_vix(self):
        """Fetch and post VIX volatility index."""
        try:
            logger.info("Running job: VIX")
            data = await self.api_client.get_vix()
            await self._post_content("vix", data)
        except Exception as e:
            logger.error(f"VIX job error: {e}")

    async def job_economic_calendar(self):
        """Fetch and post economic calendar."""
        try:
            logger.info("Running job: Economic Calendar")
            data = await self.api_client.get_economic_calendar()
            await self._post_content("economic_calendar", data)
        except Exception as e:
            logger.error(f"Economic Calendar job error: {e}")

    async def job_sec_insider(self):
        """Fetch and post SEC insider trading."""
        try:
            logger.info("Running job: SEC Insider Trading")
            data = await self.api_client.get_sec_insider_filings()
            await self._post_content("sec_insider", data)
        except Exception as e:
            logger.error(f"SEC Insider job error: {e}")

    async def job_yahoo_quote(self):
        """Fetch and post Yahoo Finance quotes."""
        if not self._is_market_hours():
            logger.debug("Skipping Yahoo quotes - outside market hours")
            return

        try:
            logger.info("Running job: Yahoo Finance Quotes")
            data = await self.api_client.get_yahoo_finance_quote()
            await self._post_content("yahoo_quote", data)
        except Exception as e:
            logger.error(f"Yahoo Finance job error: {e}")

    async def job_cleanup(self):
        """Cleanup old records."""
        try:
            logger.info("Running cleanup job")
            self.rate_limiter.cleanup_old_records(days=7)
            self.deduplicator.cleanup_old_hashes(days=7)
            if self.chart_handler:
                self.chart_handler.cleanup_old_charts()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Cleanup job error: {e}")

    # ==================== Benzinga Jobs (Premium) ====================

    async def job_benzinga_news(self):
        """Fetch and post Benzinga breaking news."""
        try:
            logger.info("Running job: Benzinga Breaking News")
            data = await self.api_client.get_benzinga_news(ticker="all", limit=10)
            await self._post_content("benzinga_news", data)
        except Exception as e:
            logger.error(f"Benzinga News job error: {e}")

    async def job_benzinga_ratings(self):
        """Fetch and post Benzinga analyst ratings."""
        try:
            logger.info("Running job: Benzinga Analyst Ratings")
            data = await self.api_client.get_benzinga_ratings(ticker="all", limit=10)
            await self._post_content("benzinga_ratings", data)
        except Exception as e:
            logger.error(f"Benzinga Ratings job error: {e}")

    async def job_benzinga_earnings(self):
        """Fetch and post Benzinga earnings calendar."""
        try:
            logger.info("Running job: Benzinga Earnings Calendar")
            data = await self.api_client.get_benzinga_earnings(ticker="all", limit=20)
            await self._post_content("benzinga_earnings", data)
        except Exception as e:
            logger.error(f"Benzinga Earnings job error: {e}")

    def add_jobs(self):
        """Add all scheduled jobs to the scheduler."""
        # CNN Fear & Greed - Every 4 hours
        if self.config.schedule_cnn_fear_greed > 0:
            self.scheduler.add_job(
                self.job_cnn_fear_greed,
                trigger=IntervalTrigger(minutes=self.config.schedule_cnn_fear_greed),
                id="cnn_fear_greed",
                name="CNN Fear & Greed Index",
            )
            logger.info(f"Scheduled CNN Fear & Greed every {self.config.schedule_cnn_fear_greed}min")

        # Reddit Trending - Every 2 hours
        if self.config.schedule_reddit_trending > 0:
            self.scheduler.add_job(
                self.job_reddit_trending,
                trigger=IntervalTrigger(minutes=self.config.schedule_reddit_trending),
                id="reddit_trending",
                name="Reddit Trending Tickers",
            )
            logger.info(f"Scheduled Reddit Trending every {self.config.schedule_reddit_trending}min")

        # Top Gainers - Every 1 hour during market hours
        if self.config.schedule_top_gainers > 0:
            self.scheduler.add_job(
                self.job_top_gainers,
                trigger=IntervalTrigger(minutes=self.config.schedule_top_gainers),
                id="top_gainers",
                name="Top Stock Gainers",
            )
            logger.info(f"Scheduled Top Gainers every {self.config.schedule_top_gainers}min (market hours only)")

        # Sector Performance - Daily at 4 PM ET
        if self.config.schedule_sector_performance > 0:
            self.scheduler.add_job(
                self.job_sector_performance,
                trigger=CronTrigger(hour=16, minute=0, timezone=self.tz),
                id="sector_performance",
                name="Sector Performance",
            )
            logger.info("Scheduled Sector Performance daily at 4:00 PM ET")

        # VIX - Every 6 hours
        if self.config.schedule_vix > 0:
            self.scheduler.add_job(
                self.job_vix,
                trigger=IntervalTrigger(minutes=self.config.schedule_vix),
                id="vix",
                name="VIX Volatility Index",
            )
            logger.info(f"Scheduled VIX every {self.config.schedule_vix}min")

        # Economic Calendar - Daily at 7 AM ET
        if self.config.schedule_economic_calendar > 0:
            self.scheduler.add_job(
                self.job_economic_calendar,
                trigger=CronTrigger(hour=7, minute=0, timezone=self.tz),
                id="economic_calendar",
                name="Economic Calendar",
            )
            logger.info("Scheduled Economic Calendar daily at 7:00 AM ET")

        # SEC Insider - Daily at 6 PM ET
        if self.config.schedule_sec_insider > 0:
            self.scheduler.add_job(
                self.job_sec_insider,
                trigger=CronTrigger(hour=18, minute=0, timezone=self.tz),
                id="sec_insider",
                name="SEC Insider Trading",
            )
            logger.info("Scheduled SEC Insider daily at 6:00 PM ET")

        # Yahoo Finance - Every 30 min during market hours
        if self.config.schedule_yahoo_finance > 0:
            self.scheduler.add_job(
                self.job_yahoo_quote,
                trigger=IntervalTrigger(minutes=self.config.schedule_yahoo_finance),
                id="yahoo_quote",
                name="Yahoo Finance Quotes",
            )
            logger.info(f"Scheduled Yahoo Finance every {self.config.schedule_yahoo_finance}min (market hours only)")

        # Cleanup - Daily at midnight
        self.scheduler.add_job(
            self.job_cleanup,
            trigger=CronTrigger(hour=0, minute=0, timezone=self.tz),
            id="cleanup",
            name="Database Cleanup",
        )
        logger.info("Scheduled cleanup daily at midnight")

        # ==================== Benzinga (Premium - Priority) ====================

        # Benzinga Breaking News - Every 30 minutes
        if self.config.schedule_benzinga_news > 0:
            self.scheduler.add_job(
                self.job_benzinga_news,
                trigger=IntervalTrigger(minutes=self.config.schedule_benzinga_news),
                id="benzinga_news",
                name="Benzinga Breaking News",
            )
            logger.info(f"Scheduled Benzinga News every {self.config.schedule_benzinga_news}min (PREMIUM)")

        # Benzinga Analyst Ratings - Every 60 minutes
        if self.config.schedule_benzinga_ratings > 0:
            self.scheduler.add_job(
                self.job_benzinga_ratings,
                trigger=IntervalTrigger(minutes=self.config.schedule_benzinga_ratings),
                id="benzinga_ratings",
                name="Benzinga Analyst Ratings",
            )
            logger.info(f"Scheduled Benzinga Ratings every {self.config.schedule_benzinga_ratings}min (PREMIUM)")

        # Benzinga Earnings Calendar - Every 2 hours
        if self.config.schedule_benzinga_earnings > 0:
            self.scheduler.add_job(
                self.job_benzinga_earnings,
                trigger=IntervalTrigger(minutes=self.config.schedule_benzinga_earnings),
                id="benzinga_earnings",
                name="Benzinga Earnings Calendar",
            )
            logger.info(f"Scheduled Benzinga Earnings every {self.config.schedule_benzinga_earnings}min (PREMIUM)")

    async def start(self):
        """Start the scheduler."""
        await self.initialize()
        self.add_jobs()
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics.

        Returns:
            Dict with stats
        """
        return {
            **self.stats,
            "rate_limiter": self.rate_limiter.get_stats(),
            "deduplicator": self.deduplicator.get_stats(),
        }
