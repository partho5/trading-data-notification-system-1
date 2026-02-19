"""Twitter/X client for posting tweets with media."""

import time
from pathlib import Path
from typing import Optional

import tweepy
from loguru import logger

from ..config import Config


class TwitterClient:
    """Client for posting to Twitter/X with OAuth 1.0a authentication."""

    def __init__(self, config: Config):
        """Initialize Twitter client.

        Args:
            config: Application configuration
        """
        self.config = config

        # OAuth 1.0a authentication
        auth = tweepy.OAuth1UserHandler(
            consumer_key=config.twitter_api_key,
            consumer_secret=config.twitter_api_secret,
            access_token=config.twitter_access_token,
            access_token_secret=config.twitter_access_token_secret,
        )

        # Setup proxy if configured
        proxy = config.twitter_proxy if config.twitter_proxy else None

        # Create API client
        self.api = tweepy.API(auth, proxy=proxy)

        # Create v2 client for newer endpoints
        self.client = tweepy.Client(
            consumer_key=config.twitter_api_key,
            consumer_secret=config.twitter_api_secret,
            access_token=config.twitter_access_token,
            access_token_secret=config.twitter_access_token_secret,
        )

        logger.info("Twitter client initialized")

    def post_tweet(
        self,
        text: str,
        chart_path: Optional[Path] = None,
    ) -> bool:
        """Post tweet with optional image.

        Args:
            text: Tweet text (max 280 characters)
            chart_path: Optional path to image file

        Returns:
            True if posted successfully
        """
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would post to Twitter:")
            logger.info(f"Text: {text}")
            if chart_path:
                logger.info(f"Chart: {chart_path}")
            return True

        try:
            # Validate text length
            if len(text) > 280:
                logger.warning(f"Tweet text too long ({len(text)} chars), truncating")
                text = text[:277] + "..."

            media_ids = []

            # Upload media with retry (SSL errors on upload.twitter.com are transient)
            if chart_path and chart_path.exists():
                for attempt in range(2):
                    try:
                        logger.info(f"Uploading media: {chart_path}")
                        media = self.api.media_upload(filename=str(chart_path))
                        media_ids.append(media.media_id)
                        logger.info(f"Media uploaded successfully: {media.media_id}")
                        break
                    except Exception as e:
                        if attempt == 0:
                            logger.warning(f"Media upload failed, retrying in 3s: {e}")
                            time.sleep(3)
                        else:
                            logger.error(f"Failed to upload media after 2 attempts: {e}")
                            # Continue posting without media

            # Post tweet with retry (Twitter intermittently returns 403 on valid requests)
            for attempt in range(2):
                try:
                    if media_ids:
                        response = self.client.create_tweet(
                            text=text,
                            media_ids=media_ids,
                        )
                    else:
                        response = self.client.create_tweet(text=text)

                    if response and response.data:
                        tweet_id = response.data.get("id")
                        logger.info(f"Tweet posted successfully: {tweet_id}")
                        return True
                    else:
                        logger.error("Tweet post failed: No response data")
                        return False

                except tweepy.TweepyException as e:
                    if "403" in str(e) and attempt == 0:
                        logger.warning(f"Tweet returned 403, retrying in 5s: {e}")
                        time.sleep(5)
                        continue
                    logger.error(f"Tweepy error: {e}")
                    return False

        except Exception as e:
            logger.error(f"Twitter post error: {e}")
            return False

    def verify_credentials(self) -> bool:
        """Verify Twitter credentials are valid.

        Returns:
            True if credentials are valid
        """
        try:
            user = self.api.verify_credentials()
            if user:
                logger.info(f"Twitter credentials verified for @{user.screen_name}")
                return True
            else:
                logger.error("Failed to verify Twitter credentials")
                return False
        except tweepy.TweepyException as e:
            logger.error(f"Twitter credential verification failed: {e}")
            return False
