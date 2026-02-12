"""Main entry point for Trading Notification Bot."""

import asyncio
import signal
import sys
from pathlib import Path

from loguru import logger

from .config import get_config, load_config
from .health import HealthMonitor
from .scheduler import TradingBotScheduler  # Old interval-based scheduler
from .scheduler_v2 import OptimalScheduler  # New CRON-based scheduler


def setup_logging(config):
    """Setup logging configuration.

    Args:
        config: Application configuration
    """
    # Remove default handler
    logger.remove()

    # Console logging
    logger.add(
        sys.stderr,
        level=config.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    )

    # File logging with rotation
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "bot_{time:YYYY-MM-DD}.log",
        level=config.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=config.log_rotation,
        retention=f"{config.log_retention_days} days",
        compression="zip",
    )

    logger.info("Logging initialized")


async def main():
    """Main async function."""
    # Load configuration
    try:
        config = load_config()
        logger.info("Configuration loaded")
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Setup logging
    setup_logging(config)

    # Validate credentials
    missing = config.validate_required_credentials()
    if missing:
        logger.error(f"Missing required credentials: {', '.join(missing)}")
        logger.error("Please check your .env file")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Trading Notification Bot Starting...")
    logger.info("=" * 60)
    logger.info(f"API Base URL: {config.api_base_url}")
    logger.info(f"Twitter Rate Limits: {config.twitter_max_posts_per_minute}/min, {config.twitter_max_posts_per_day}/day")
    logger.info(f"Discord Webhooks: {len(config.discord_webhook_urls)} configured")
    logger.info(f"Timezone: {config.timezone}")
    logger.info(f"Dry Run Mode: {config.dry_run}")
    logger.info("=" * 60)

    # Create scheduler (use OPTIMAL by default)
    use_optimal = getattr(config, 'use_optimal_schedule', True)

    if use_optimal:
        logger.info("Using OPTIMAL CRON-based scheduler (audience-first, 17 posts/day)")
        scheduler = OptimalScheduler(config)
    else:
        logger.warning("Using OLD interval-based scheduler (for comparison)")
        scheduler = TradingBotScheduler(config)

    # Create health monitor
    health_monitor = HealthMonitor(scheduler, port=config.health_check_port)

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start scheduler
        await scheduler.start()

        # Start health monitor
        await health_monitor.start()

        logger.info("Bot is running. Press Ctrl+C to stop.")
        logger.info(f"Health monitor: http://localhost:{config.health_check_port}/health")
        logger.info(f"Manual trigger: POST http://localhost:{config.health_check_port}/trigger/{{endpoint}}")

        # Keep running
        while True:
            await asyncio.sleep(60)

            # Log stats every hour
            if asyncio.get_event_loop().time() % 3600 < 60:
                stats = scheduler.get_stats()
                logger.info(f"Stats: {stats}")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
    finally:
        scheduler.stop()
        await health_monitor.stop()
        logger.info("Bot stopped")


def run():
    """Entry point for the bot."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
