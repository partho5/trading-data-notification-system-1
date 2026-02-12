"""Rate limiter for Twitter posts with SQLite persistence."""

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

from .config import Config


class RateLimiter:
    """Track and enforce Twitter rate limits."""

    def __init__(self, config: Config):
        """Initialize rate limiter.

        Args:
            config: Application configuration
        """
        self.config = config
        self.db_path = Path(config.database_path)
        self.max_per_minute = config.twitter_max_posts_per_minute
        self.max_per_day = config.twitter_max_posts_per_day

        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for tracking posts."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS twitter_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_posted_at
                ON twitter_posts(posted_at)
                """
            )
            conn.commit()

        logger.info("Rate limiter database initialized")

    def can_post(self) -> tuple[bool, Optional[str]]:
        """Check if we can post to Twitter based on rate limits.

        Returns:
            Tuple of (can_post, reason)
            - can_post: True if posting is allowed
            - reason: String explaining why posting is blocked, or None if allowed
        """
        with sqlite3.connect(self.db_path) as conn:
            # Check per-minute limit
            one_minute_ago = datetime.now() - timedelta(minutes=1)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM twitter_posts
                WHERE posted_at > ?
                """,
                (one_minute_ago,),
            )
            count_last_minute = cursor.fetchone()[0]

            if count_last_minute >= self.max_per_minute:
                wait_seconds = 60 - (datetime.now() - one_minute_ago).seconds
                return False, f"Per-minute limit reached. Wait {wait_seconds}s"

            # Check per-day limit
            one_day_ago = datetime.now() - timedelta(days=1)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM twitter_posts
                WHERE posted_at > ?
                """,
                (one_day_ago,),
            )
            count_last_day = cursor.fetchone()[0]

            if count_last_day >= self.max_per_day:
                return False, f"Daily limit reached ({self.max_per_day} posts/day)"

        return True, None

    def record_post(self):
        """Record a Twitter post in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO twitter_posts (posted_at)
                VALUES (?)
                """,
                (datetime.now(),),
            )
            conn.commit()

        logger.debug("Twitter post recorded in rate limiter")

    def get_stats(self) -> dict:
        """Get current rate limit statistics.

        Returns:
            Dict with post counts and limits
        """
        with sqlite3.connect(self.db_path) as conn:
            # Last minute
            one_minute_ago = datetime.now() - timedelta(minutes=1)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM twitter_posts
                WHERE posted_at > ?
                """,
                (one_minute_ago,),
            )
            last_minute = cursor.fetchone()[0]

            # Last day
            one_day_ago = datetime.now() - timedelta(days=1)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM twitter_posts
                WHERE posted_at > ?
                """,
                (one_day_ago,),
            )
            last_day = cursor.fetchone()[0]

            # Last post time
            cursor = conn.execute(
                """
                SELECT MAX(posted_at) FROM twitter_posts
                """
            )
            last_post = cursor.fetchone()[0]

        return {
            "posts_last_minute": last_minute,
            "posts_last_day": last_day,
            "limit_per_minute": self.max_per_minute,
            "limit_per_day": self.max_per_day,
            "last_post_time": last_post,
            "can_post_now": last_minute < self.max_per_minute and last_day < self.max_per_day,
        }

    def cleanup_old_records(self, days: int = 7):
        """Remove post records older than specified days.

        Args:
            days: Number of days to keep records
        """
        cutoff = datetime.now() - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM twitter_posts
                WHERE posted_at < ?
                """,
                (cutoff,),
            )
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old rate limit records")

    def wait_if_needed(self, max_wait_seconds: int = 120) -> bool:
        """Wait if rate limit is reached.

        Args:
            max_wait_seconds: Maximum seconds to wait

        Returns:
            True if we can proceed, False if wait time exceeds max
        """
        can_post, reason = self.can_post()

        if can_post:
            return True

        # Extract wait time from reason if it's a per-minute limit
        if "Wait" in reason and "s" in reason:
            try:
                wait_seconds = int(reason.split("Wait ")[1].split("s")[0])
                if wait_seconds <= max_wait_seconds:
                    logger.info(f"Rate limit reached, waiting {wait_seconds}s")
                    time.sleep(wait_seconds)
                    return True
            except Exception:
                pass

        logger.warning(f"Rate limit exceeded: {reason}")
        return False
