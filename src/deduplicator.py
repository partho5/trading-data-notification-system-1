"""Content deduplication using hash-based tracking."""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from .config import Config


class Deduplicator:
    """Prevent posting duplicate content using content hashing."""

    def __init__(self, config: Config):
        """Initialize deduplicator.

        Args:
            config: Application configuration
        """
        self.config = config
        self.db_path = Path(config.database_path)

        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for tracking content hashes."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS content_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT UNIQUE NOT NULL,
                    endpoint TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_content_hash
                ON content_hashes(content_hash)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_posted_at
                ON content_hashes(posted_at)
                """
            )
            conn.commit()

        logger.info("Deduplicator database initialized")

    def _compute_hash(self, data: Dict[str, Any]) -> str:
        """Compute hash of content data.

        Args:
            data: Content data dict

        Returns:
            SHA256 hash of content
        """
        # Convert to JSON with sorted keys for consistent hashing
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def is_duplicate(self, data: Dict[str, Any], endpoint: str, platform: str) -> bool:
        """Check if content has already been posted.

        Args:
            data: Content data to check
            endpoint: API endpoint name
            platform: Platform name (twitter/discord)

        Returns:
            True if content is a duplicate
        """
        content_hash = self._compute_hash(data)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM content_hashes
                WHERE content_hash = ? AND endpoint = ? AND platform = ?
                """,
                (content_hash, endpoint, platform),
            )
            count = cursor.fetchone()[0]

        is_dup = count > 0
        if is_dup:
            logger.info(
                f"Duplicate content detected for {endpoint} on {platform} "
                f"(hash: {content_hash[:8]}...)"
            )

        return is_dup

    def record_post(self, data: Dict[str, Any], endpoint: str, platform: str):
        """Record that content has been posted.

        Args:
            data: Content data that was posted
            endpoint: API endpoint name
            platform: Platform name (twitter/discord)
        """
        content_hash = self._compute_hash(data)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO content_hashes (content_hash, endpoint, platform, posted_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content_hash, endpoint, platform, datetime.now()),
                )
                conn.commit()

            logger.debug(
                f"Recorded post for {endpoint} on {platform} (hash: {content_hash[:8]}...)"
            )

        except sqlite3.IntegrityError:
            # Hash already exists (race condition)
            logger.warning(f"Attempted to record duplicate hash: {content_hash[:8]}...")

    def cleanup_old_hashes(self, days: int = 7):
        """Remove content hashes older than specified days.

        Args:
            days: Number of days to keep hashes
        """
        cutoff = datetime.now() - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM content_hashes
                WHERE posted_at < ?
                """,
                (cutoff,),
            )
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old content hashes")

    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics.

        Returns:
            Dict with stats
        """
        with sqlite3.connect(self.db_path) as conn:
            # Total hashes
            cursor = conn.execute("SELECT COUNT(*) FROM content_hashes")
            total = cursor.fetchone()[0]

            # Last 24 hours
            one_day_ago = datetime.now() - timedelta(days=1)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM content_hashes
                WHERE posted_at > ?
                """,
                (one_day_ago,),
            )
            last_day = cursor.fetchone()[0]

            # By platform
            cursor = conn.execute(
                """
                SELECT platform, COUNT(*) FROM content_hashes
                WHERE posted_at > ?
                GROUP BY platform
                """,
                (one_day_ago,),
            )
            by_platform = dict(cursor.fetchall())

        return {
            "total_hashes": total,
            "hashes_last_24h": last_day,
            "by_platform": by_platform,
        }
