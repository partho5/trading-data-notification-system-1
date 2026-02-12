"""Discord-specific content formatter."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseFormatter


class DiscordFormatter(BaseFormatter):
    """Format content for Discord rich embeds."""

    @staticmethod
    def create_embed(
        title: str,
        description: str = "",
        color: int = 0x3498DB,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None,
        image_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Create Discord embed structure.

        Args:
            title: Embed title
            description: Embed description
            color: Embed color as integer
            fields: List of field dicts with 'name', 'value', 'inline' keys
            footer: Footer text
            image_url: Large image URL
            thumbnail_url: Thumbnail image URL
            timestamp: Timestamp for embed

        Returns:
            Discord embed dict
        """
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields or [],
        }

        if footer:
            embed["footer"] = {"text": footer}

        if image_url:
            embed["image"] = {"url": image_url}

        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}

        if timestamp:
            embed["timestamp"] = timestamp.isoformat()

        return embed

    def format_cnn_fear_greed(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format CNN Fear & Greed data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch Fear & Greed data")

        content = data.get("data", {})
        current_score = content.get("score", 0)
        rating = content.get("rating", "Unknown")
        comparisons = content.get("comparisons", {})
        yesterday = comparisons.get("previous_close", 0)
        change = current_score - yesterday

        # Color based on sentiment
        color = self.get_color_for_sentiment(change)

        # Build description
        desc_parts = [
            f"**Current Sentiment:** {rating}",
            f"**Score:** {current_score:.1f}/100 {self.get_trend_indicator(change)}",
            f"**Yesterday:** {yesterday:.1f}",
        ]

        # Add sub-indicators (indicators is a list, not dict)
        indicators = content.get("indicators", [])
        if indicators:
            desc_parts.append("\n**Key Indicators:**")
            for indicator in indicators[:5]:  # Top 5
                name = indicator.get("name", "Unknown")
                score = indicator.get("score", 0)
                desc_parts.append(f"• {name}: {score}")

        description = "\n".join(desc_parts)

        embed = self.create_embed(
            title=f"{self.EMOJIS['chart']} Market Sentiment: Fear & Greed Index",
            description=description,
            color=color,
            footer="Source: CNN Business",
            timestamp=datetime.now(),
        )

        return embed

    def format_reddit_trending(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format Reddit trending data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch Reddit trending data")

        content = data.get("data", {})
        tickers = content.get("tickers", [])[:10]  # Top 10

        # Build description
        desc_parts = [f"{self.EMOJIS['fire']} **Reddit's Most Talked About Stocks**\n"]

        for i, ticker_data in enumerate(tickers, 1):
            ticker = ticker_data.get("ticker", "???")
            mentions = ticker_data.get("mentions", 0)
            medal = self.MEDALS.get(i, "")
            desc_parts.append(f"{medal} **{ticker}** - {mentions} mentions")

        description = "\n".join(desc_parts)

        embed = self.create_embed(
            title=f"{self.EMOJIS['fire']} Reddit Trending Tickers",
            description=description,
            color=0xE67E22,  # Orange
            footer="Source: r/wallstreetbets, r/stocks, r/options",
            timestamp=datetime.now(),
        )

        return embed

    def format_top_gainers(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format top gainers data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch top gainers data")

        content = data.get("data", {})
        gainers = content.get("gainers", [])[:10]

        desc_parts = [f"{self.EMOJIS['up']} **Biggest Movers Today**\n"]

        for i, stock in enumerate(gainers, 1):
            ticker = stock.get("ticker", "???")
            price = stock.get("price", 0)
            change_pct = stock.get("change_percent", 0)
            medal = self.MEDALS.get(i, "")

            desc_parts.append(
                f"{medal} **{ticker}** ${price:.2f} "
                f"({self.format_percentage(change_pct)}) {self.EMOJIS['rocket']}"
            )

        description = "\n".join(desc_parts)

        embed = self.create_embed(
            title=f"{self.EMOJIS['up']} Top Stock Gainers",
            description=description,
            color=0x2ECC71,  # Green
            footer="Source: Finviz",
            timestamp=datetime.now(),
        )

        return embed

    def format_sector_performance(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format sector performance data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch sector performance data")

        content = data.get("data", {})
        sectors = content.get("sectors", [])
        leaders = content.get("leaders", [])[:3]
        laggards = content.get("laggards", [])[:3]

        # Build fields
        fields = []

        # Top 3 leaders
        if leaders:
            leaders_text = "\n".join(
                [
                    f"{self.MEDALS.get(i+1, '')} {s.get('sector', 'Unknown')}: "
                    f"{self.format_percentage(s.get('change_percent', 0))}"
                    for i, s in enumerate(leaders)
                ]
            )
            fields.append({"name": f"{self.EMOJIS['trophy']} Leaders", "value": leaders_text, "inline": True})

        # Bottom 3 laggards
        if laggards:
            laggards_text = "\n".join(
                [
                    f"{s.get('sector', 'Unknown')}: "
                    f"{self.format_percentage(s.get('change_percent', 0))}"
                    for s in laggards
                ]
            )
            fields.append({"name": f"{self.EMOJIS['down']} Laggards", "value": laggards_text, "inline": True})

        # Determine overall color
        avg_change = sum(s.get("change_percent", 0) for s in sectors) / len(sectors) if sectors else 0
        color = self.get_color_for_sentiment(avg_change)

        embed = self.create_embed(
            title=f"{self.EMOJIS['chart']} Sector Performance Today",
            description=f"How all 11 sectors performed today",
            color=color,
            fields=fields,
            footer="Source: Alpha Vantage",
            timestamp=datetime.now(),
        )

        return embed

    def format_vix(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format VIX data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch VIX data")

        content = data.get("data", {})
        price = content.get("price", 0)
        change_pct = content.get("change_percent", 0)
        sentiment = content.get("sentiment", "Unknown")

        # Color (inverse - high VIX = bearish = red)
        color = self.get_color_for_sentiment(-change_pct)

        description = f"""
**Current VIX:** ${price:.2f} {self.get_trend_indicator(change_pct)}
**Change:** {self.format_percentage(change_pct)}
**Sentiment:** {sentiment}

{self.EMOJIS['warning']} Higher VIX = Higher market fear/volatility
        """.strip()

        embed = self.create_embed(
            title=f"{self.EMOJIS['chart']} Market Volatility (VIX)",
            description=description,
            color=color,
            footer="Source: VIXY ETF (VIX proxy)",
            timestamp=datetime.now(),
        )

        return embed

    def format_economic_calendar(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format economic calendar data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch economic calendar")

        content = data.get("data", {})
        earnings = content.get("earnings", [])[:10]  # Next 10 earnings

        desc_parts = [f"{self.EMOJIS['calendar']} **Upcoming Earnings**\n"]

        for earning in earnings:
            ticker = earning.get("ticker", "???")
            date = earning.get("date", "Unknown")
            desc_parts.append(f"• **{ticker}** - {date}")

        description = "\n".join(desc_parts)

        embed = self.create_embed(
            title=f"{self.EMOJIS['calendar']} Economic Calendar",
            description=description,
            color=0x3498DB,  # Blue
            footer="Source: Alpha Vantage",
            timestamp=datetime.now(),
        )

        return embed

    def format_sec_insider(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format SEC insider trading data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch insider trading data")

        content = data.get("data", {})
        filings = content.get("filings", [])[:10]  # Top 10

        desc_parts = [f"{self.EMOJIS['eyes']} **Recent Insider Activity**\n"]

        for filing in filings:
            ticker = filing.get("ticker", "???")
            insider = filing.get("insider_name", "Unknown")
            transaction = filing.get("transaction_type", "???")
            value = filing.get("value", 0)

            emoji = self.EMOJIS['up'] if "buy" in transaction.lower() else self.EMOJIS['down']
            desc_parts.append(
                f"{emoji} **{ticker}** - {insider[:20]}: {transaction} "
                f"(${self.format_large_number(value)})"
            )

        description = "\n".join(desc_parts)

        embed = self.create_embed(
            title=f"{self.EMOJIS['eyes']} SEC Insider Trading",
            description=description,
            color=0x9B59B6,  # Purple
            footer="Source: SEC EDGAR (Form 4 filings)",
            timestamp=datetime.now(),
        )

        return embed

    def format_yahoo_quote(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format Yahoo Finance quote data for Discord.

        Args:
            data: API response data

        Returns:
            Discord embed dict
        """
        if not data.get("success"):
            return self._error_embed("Failed to fetch quotes")

        content = data.get("data", {})
        # Handle both formats: {"quotes": [...]} and direct list [...]
        if isinstance(content, list):
            quotes = content
        else:
            quotes = content.get("quotes", [])

        fields = []
        for quote in quotes[:5]:  # Max 5 quotes
            ticker = quote.get("ticker", "???")
            price = quote.get("price", 0)
            change_pct = quote.get("change_percent", 0)
            volume = quote.get("volume", 0)

            field_value = f"""
Price: ${price:.2f} ({self.format_percentage(change_pct)})
Volume: {self.format_large_number(volume)}
            """.strip()

            fields.append({"name": f"{ticker} {self.get_trend_indicator(change_pct)}", "value": field_value, "inline": True})

        # Overall color based on average change
        avg_change = (
            sum(q.get("change_percent", 0) for q in quotes) / len(quotes) if quotes else 0
        )
        color = self.get_color_for_sentiment(avg_change)

        embed = self.create_embed(
            title=f"{self.EMOJIS['chart']} Market Quotes",
            description="Real-time stock quotes",
            color=color,
            fields=fields,
            footer="Source: Yahoo Finance",
            timestamp=datetime.now(),
        )

        return embed

    def _error_embed(self, message: str) -> Dict[str, Any]:
        """Create error embed.

        Args:
            message: Error message

        Returns:
            Discord embed dict
        """
        return self.create_embed(
            title=f"{self.EMOJIS['warning']} Error",
            description=message,
            color=0xE74C3C,  # Red
            timestamp=datetime.now(),
        )
