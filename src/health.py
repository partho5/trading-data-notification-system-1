"""Health monitoring HTTP endpoint."""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict

from aiohttp import web
from loguru import logger

from .scheduler import TradingBotScheduler


class HealthMonitor:
    """Simple HTTP health check endpoint."""

    def __init__(self, scheduler: TradingBotScheduler, port: int = 8080):
        """Initialize health monitor.

        Args:
            scheduler: Bot scheduler instance
            port: HTTP port for health endpoint
        """
        self.scheduler = scheduler
        self.port = port
        self.start_time = time.time()
        self.app = web.Application()
        self.app.router.add_get("/health", self.health_handler)
        self.app.router.add_get("/stats", self.stats_handler)
        self.app.router.add_post("/trigger/{endpoint}", self.trigger_handler)
        self.app.router.add_get("/jobs", self.jobs_handler)
        self.runner = None

    async def health_handler(self, request: web.Request) -> web.Response:
        """Handle /health requests.

        Args:
            request: HTTP request

        Returns:
            JSON health response
        """
        uptime_seconds = int(time.time() - self.start_time)

        stats = self.scheduler.get_stats()
        rate_limiter_stats = stats.get("rate_limiter", {})

        health = {
            "status": "healthy",
            "uptime_seconds": uptime_seconds,
            "last_post_time": {
                "twitter": rate_limiter_stats.get("last_post_time"),
            },
            "total_posts": stats.get("total_posts", 0),
            "successful_posts": stats.get("successful_posts", 0),
            "failed_posts": stats.get("failed_posts", 0),
            "rate_limit_blocks": stats.get("rate_limit_blocks", 0),
            "timestamp": datetime.now().isoformat(),
        }

        return web.json_response(health)

    async def stats_handler(self, request: web.Request) -> web.Response:
        """Handle /stats requests.

        Args:
            request: HTTP request

        Returns:
            JSON stats response
        """
        stats = self.scheduler.get_stats()

        return web.json_response(stats)

    async def trigger_handler(self, request: web.Request) -> web.Response:
        """Handle /trigger/{endpoint} requests to manually trigger a job.

        Args:
            request: HTTP request

        Returns:
            JSON response with trigger status
        """
        endpoint = request.match_info.get("endpoint")

        # Map endpoint names to job methods
        job_map = {
            "cnn_fear_greed": self.scheduler.job_cnn_fear_greed,
            "reddit_trending": self.scheduler.job_reddit_trending,
            "top_gainers": self.scheduler.job_top_gainers,
            "sector_performance": self.scheduler.job_sector_performance,
            "vix": self.scheduler.job_vix,
            "economic_calendar": self.scheduler.job_economic_calendar,
            "sec_insider": self.scheduler.job_sec_insider,
            "yahoo_quote": self.scheduler.job_yahoo_quote,
            # Benzinga (Premium)
            "benzinga_news": self.scheduler.job_benzinga_news,
            "benzinga_ratings": self.scheduler.job_benzinga_ratings,
            "benzinga_earnings": self.scheduler.job_benzinga_earnings,
        }

        if endpoint not in job_map:
            return web.json_response(
                {
                    "success": False,
                    "error": f"Unknown endpoint: {endpoint}",
                    "available": list(job_map.keys()),
                },
                status=404,
            )

        try:
            logger.info(f"Manually triggering job: {endpoint}")
            await job_map[endpoint]()

            return web.json_response(
                {
                    "success": True,
                    "message": f"Successfully triggered {endpoint}",
                    "endpoint": endpoint,
                }
            )
        except Exception as e:
            logger.error(f"Error triggering {endpoint}: {e}")
            return web.json_response(
                {"success": False, "error": str(e), "endpoint": endpoint}, status=500
            )

    async def jobs_handler(self, request: web.Request) -> web.Response:
        """Handle /jobs requests to list all scheduled jobs.

        Args:
            request: HTTP request

        Returns:
            JSON list of scheduled jobs
        """
        jobs = []
        for job in self.scheduler.scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": next_run.isoformat() if next_run else None,
                    "trigger": str(job.trigger),
                }
            )

        return web.json_response({"jobs": jobs, "count": len(jobs)})

    async def start(self):
        """Start health monitor HTTP server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            site = web.TCPSite(self.runner, "0.0.0.0", self.port)
            await site.start()

            logger.info(f"Health monitor started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start health monitor: {e}")

    async def stop(self):
        """Stop health monitor HTTP server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health monitor stopped")
