"""Discord webhook client for posting messages."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from discord_webhook import AsyncDiscordWebhook, DiscordEmbed
from loguru import logger

from ..config import Config


class DiscordClient:
    """Client for posting to Discord via webhooks."""

    def __init__(self, config: Config):
        """Initialize Discord client.

        Args:
            config: Application configuration
        """
        self.config = config
        self.webhook_urls = config.discord_webhook_urls

        if not self.webhook_urls:
            logger.warning("No Discord webhooks configured")

    async def post_embed(
        self,
        embed_data: Dict[str, Any],
        chart_path: Optional[Path] = None,
    ) -> bool:
        """Post embed to all configured Discord webhooks.

        Args:
            embed_data: Discord embed dict
            chart_path: Optional path to chart image file

        Returns:
            True if posted successfully to at least one webhook
        """
        if self.config.dry_run:
            logger.info("[DRY RUN] Would post to Discord:")
            logger.info(f"Embed: {embed_data.get('title', 'No title')}")
            if chart_path:
                logger.info(f"Chart: {chart_path}")
            return True

        if not self.webhook_urls:
            logger.error("No Discord webhooks configured")
            return False

        success_count = 0
        for webhook_url in self.webhook_urls:
            try:
                # Create webhook
                webhook = AsyncDiscordWebhook(url=webhook_url)

                # Create embed
                embed = DiscordEmbed()
                embed.title = embed_data.get("title", "")
                embed.description = embed_data.get("description", "")
                embed.color = embed_data.get("color", 0x3498DB)

                # Add fields
                for field in embed_data.get("fields", []):
                    embed.add_embed_field(
                        name=field.get("name", ""),
                        value=field.get("value", ""),
                        inline=field.get("inline", False),
                    )

                # Add footer
                if "footer" in embed_data:
                    embed.set_footer(text=embed_data["footer"]["text"])

                # Add timestamp
                if "timestamp" in embed_data:
                    embed.set_timestamp(embed_data["timestamp"])

                # Add image (chart)
                if chart_path and chart_path.exists():
                    with open(chart_path, "rb") as f:
                        webhook.add_file(file=f.read(), filename=chart_path.name)
                        embed.set_image(url=f"attachment://{chart_path.name}")

                # Add embed to webhook
                webhook.add_embed(embed)

                # Execute webhook
                response = await webhook.execute()

                if response:
                    logger.info(f"Posted to Discord webhook successfully")
                    success_count += 1
                else:
                    logger.error(f"Failed to post to Discord webhook")

            except Exception as e:
                logger.error(f"Discord post error: {e}")
                continue

        return success_count > 0

    async def post_message(
        self,
        content: str,
        embeds: Optional[List[Dict[str, Any]]] = None,
        chart_path: Optional[Path] = None,
    ) -> bool:
        """Post simple message to Discord.

        Args:
            content: Message text content
            embeds: Optional list of embed dicts
            chart_path: Optional path to chart image

        Returns:
            True if posted successfully
        """
        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would post to Discord: {content[:100]}")
            return True

        if not self.webhook_urls:
            logger.error("No Discord webhooks configured")
            return False

        success_count = 0
        for webhook_url in self.webhook_urls:
            try:
                webhook = AsyncDiscordWebhook(url=webhook_url, content=content)

                # Add embeds if provided
                if embeds:
                    for embed_data in embeds:
                        embed = DiscordEmbed()
                        embed.title = embed_data.get("title", "")
                        embed.description = embed_data.get("description", "")
                        embed.color = embed_data.get("color", 0x3498DB)
                        webhook.add_embed(embed)

                # Add file if provided
                if chart_path and chart_path.exists():
                    with open(chart_path, "rb") as f:
                        webhook.add_file(file=f.read(), filename=chart_path.name)

                response = await webhook.execute()

                if response:
                    logger.info(f"Posted message to Discord webhook")
                    success_count += 1
                else:
                    logger.error(f"Failed to post message to Discord webhook")

            except Exception as e:
                logger.error(f"Discord post error: {e}")
                continue

        return success_count > 0
