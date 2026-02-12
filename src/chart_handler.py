"""Chart downloading and caching handler."""

import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger
from PIL import Image

from .config import Config


class ChartHandler:
    """Handles downloading, validating, and caching chart images."""

    def __init__(self, config: Config):
        """Initialize chart handler.

        Args:
            config: Application configuration
        """
        self.config = config
        self.cache_dir = Path(config.chart_cache_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_seconds = config.chart_cache_max_age_hours * 3600
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    def _get_cache_path(self, url: str) -> Path:
        """Generate cache file path from URL.

        Args:
            url: Chart image URL

        Returns:
            Path to cached file
        """
        # Create hash of URL for filename
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.png"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cached file is still valid (not expired).

        Args:
            cache_path: Path to cached file

        Returns:
            True if cache is valid and not expired
        """
        if not cache_path.exists():
            return False

        # Check file age
        file_age = time.time() - cache_path.stat().st_mtime
        if file_age > self.max_age_seconds:
            logger.debug(f"Cache expired for {cache_path.name}")
            return False

        return True

    async def _validate_image(self, file_path: Path) -> bool:
        """Validate that the file is a valid PNG image.

        Args:
            file_path: Path to image file

        Returns:
            True if valid PNG image
        """
        try:
            with Image.open(file_path) as img:
                # Verify it's a PNG
                if img.format != "PNG":
                    logger.warning(f"Image is not PNG format: {img.format}")
                    return False

                # Check minimum dimensions (at least 100x100)
                if img.width < 100 or img.height < 100:
                    logger.warning(
                        f"Image too small: {img.width}x{img.height}"
                    )
                    return False

                return True

        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return False

    async def download_chart(self, url: str) -> Optional[Path]:
        """Download chart from URL and cache it.

        Args:
            url: URL to chart image

        Returns:
            Path to cached chart file, or None if download failed
        """
        if not url:
            return None

        cache_path = self._get_cache_path(url)

        # Check if valid cache exists
        if self._is_cache_valid(cache_path):
            logger.debug(f"Using cached chart: {cache_path.name}")
            return cache_path

        # Download chart
        try:
            logger.info(f"Downloading chart from {url}")
            response = await self.client.get(url, follow_redirects=True)
            response.raise_for_status()

            # Save to cache
            cache_path.write_bytes(response.content)

            # Validate image
            if not await self._validate_image(cache_path):
                logger.error("Chart validation failed, removing invalid file")
                cache_path.unlink(missing_ok=True)
                return None

            logger.info(f"Chart downloaded and cached: {cache_path.name}")
            return cache_path

        except httpx.TimeoutException:
            logger.warning(f"Chart download timeout: {url}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"Chart download failed with status {e.response.status_code}: {url}")
            return None
        except Exception as e:
            logger.error(f"Chart download error: {e}")
            return None

    def cleanup_old_charts(self):
        """Remove cached charts older than max age."""
        try:
            now = time.time()
            removed_count = 0

            for chart_file in self.cache_dir.glob("*.png"):
                file_age = now - chart_file.stat().st_mtime
                if file_age > self.max_age_seconds:
                    chart_file.unlink()
                    removed_count += 1
                    logger.debug(f"Removed expired chart: {chart_file.name}")

            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired charts")

        except Exception as e:
            logger.error(f"Chart cleanup error: {e}")

    def get_cached_chart(self, url: str) -> Optional[Path]:
        """Get cached chart if it exists and is valid.

        Args:
            url: Chart URL

        Returns:
            Path to cached chart or None
        """
        cache_path = self._get_cache_path(url)
        if self._is_cache_valid(cache_path):
            return cache_path
        return None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
