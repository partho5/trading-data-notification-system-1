"""Base formatter with shared utilities."""

from typing import Any, Dict


class BaseFormatter:
    """Base class for content formatters with shared utilities."""

    # Emoji mapping
    EMOJIS = {
        "chart": "📊",
        "up": "📈",
        "down": "📉",
        "fire": "🔥",
        "eyes": "👀",
        "calendar": "📅",
        "warning": "⚠️",
        "rocket": "🚀",
        "trophy": "🏆",
        "money": "💰",
        "bell": "🔔",
        "lightning": "⚡",
    }

    # Trend indicators
    TRENDS = {
        "up": "⬆️",
        "down": "⬇️",
        "flat": "➡️",
    }

    # Medal emojis for rankings
    MEDALS = {
        1: "🥇",
        2: "🥈",
        3: "🥉",
    }

    @staticmethod
    def format_number(value: float, decimals: int = 2) -> str:
        """Format number with commas and specified decimals.

        Args:
            value: Number to format
            decimals: Number of decimal places

        Returns:
            Formatted number string
        """
        return f"{value:,.{decimals}f}"

    @staticmethod
    def format_percentage(value: float, decimals: int = 2, include_sign: bool = True) -> str:
        """Format percentage with sign.

        Args:
            value: Percentage value
            decimals: Number of decimal places
            include_sign: Include + sign for positive values

        Returns:
            Formatted percentage string
        """
        sign = "+" if value > 0 and include_sign else ""
        return f"{sign}{value:.{decimals}f}%"

    @staticmethod
    def format_large_number(value: float) -> str:
        """Format large numbers with K, M, B suffixes.

        Args:
            value: Number to format

        Returns:
            Formatted number with suffix
        """
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        elif value >= 1_000:
            return f"{value / 1_000:.2f}K"
        else:
            return f"{value:.0f}"

    @staticmethod
    def get_trend_indicator(value: float, threshold: float = 0.1) -> str:
        """Get trend indicator emoji based on value.

        Args:
            value: Numeric value (e.g., percentage change)
            threshold: Minimum absolute value to be considered trending

        Returns:
            Trend emoji (up/down/flat)
        """
        if value > threshold:
            return BaseFormatter.TRENDS["up"]
        elif value < -threshold:
            return BaseFormatter.TRENDS["down"]
        else:
            return BaseFormatter.TRENDS["flat"]

    @staticmethod
    def get_color_for_sentiment(value: float, inverse: bool = False) -> int:
        """Get Discord embed color based on sentiment value.

        Args:
            value: Sentiment/change value
            inverse: Invert color logic (e.g., for VIX where high = bad)

        Returns:
            Color as integer (for Discord embeds)
        """
        # Discord colors as integers (hex to decimal)
        GREEN = 0x2ECC71  # Positive/bullish
        RED = 0xE74C3C  # Negative/bearish
        BLUE = 0x3498DB  # Neutral
        ORANGE = 0xE67E22  # Warning

        if inverse:
            if value > 0.5:
                return RED
            elif value < -0.5:
                return GREEN
            else:
                return BLUE
        else:
            if value > 0.5:
                return GREEN
            elif value < -0.5:
                return RED
            else:
                return BLUE

    @staticmethod
    def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
        """Truncate text to max length.

        Args:
            text: Text to truncate
            max_length: Maximum length
            suffix: Suffix to add if truncated

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[: max_length - len(suffix)] + suffix
