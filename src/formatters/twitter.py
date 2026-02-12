"""Twitter-specific content formatter with 280 character limit."""

from typing import Any, Dict, List

from .base import BaseFormatter


class TwitterFormatter(BaseFormatter):
    """Format content for Twitter/X with character limit compliance."""

    MAX_TWEET_LENGTH = 280
    MAX_HASHTAGS = 3

    def format_cnn_fear_greed(self, data: Dict[str, Any]) -> str:
        """Format CNN Fear & Greed for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch market sentiment data"

        content = data.get("data", {})
        current_score = content.get("score", 0)
        rating = content.get("rating", "Unknown").upper()
        comparisons = content.get("comparisons", {})
        yesterday = comparisons.get("previous_close", 0)
        change = current_score - yesterday
        trend = self.get_trend_indicator(change)

        tweet = (
            f"{self.EMOJIS['chart']} Market Sentiment: {rating} ({current_score:.1f}) {trend}\n\n"
            f"Down from {yesterday:.1f} yesterday\n"
        )

        # Count fear/greed indicators (indicators is a list)
        indicators = content.get("indicators", [])
        if indicators:
            fear_count = sum(1 for ind in indicators if "fear" in ind.get("rating", "").lower())
            total = len(indicators)
            tweet += f"{fear_count}/{total} indicators show fear\n"

        tweet += "\n#Stocks #MarketSentiment #Trading"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def format_reddit_trending(self, data: Dict[str, Any]) -> str:
        """Format Reddit trending for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch Reddit trending data"

        content = data.get("data", {})
        tickers = content.get("tickers", [])[:5]  # Top 5 for Twitter

        tweet_parts = [f"{self.EMOJIS['fire']} Reddit Trending Tickers:\n"]

        for i, ticker_data in enumerate(tickers, 1):
            ticker = ticker_data.get("ticker", "???")
            mentions = ticker_data.get("mentions", 0)
            medal = self.MEDALS.get(i, "")
            tweet_parts.append(f"{medal} ${ticker} - {mentions} mentions")

        tweet = "\n".join(tweet_parts)
        tweet += "\n\n#WallStreetBets #Stocks #Reddit"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def format_top_gainers(self, data: Dict[str, Any]) -> str:
        """Format top gainers for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch top gainers data"

        content = data.get("data", {})
        gainers = content.get("gainers", [])[:3]  # Top 3 for Twitter

        tweet_parts = [f"{self.EMOJIS['up']} Biggest Movers Today:\n"]

        for i, stock in enumerate(gainers, 1):
            ticker = stock.get("ticker", "???")
            change_pct = stock.get("change_percent", 0)
            medal = self.MEDALS.get(i, "")
            tweet_parts.append(
                f"{medal} ${ticker} {self.format_percentage(change_pct)} {self.EMOJIS['rocket']}"
            )

        tweet = "\n".join(tweet_parts)
        tweet += "\n\n#Stocks #Trading #StockMarket"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def format_sector_performance(self, data: Dict[str, Any]) -> str:
        """Format sector performance for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch sector performance"

        content = data.get("data", {})
        leaders = content.get("leaders", [])[:3]

        tweet_parts = [f"{self.EMOJIS['chart']} Sector Winners Today:\n"]

        for i, sector in enumerate(leaders, 1):
            sector_name = sector.get("sector", "Unknown")
            change_pct = sector.get("change_percent", 0)
            medal = self.MEDALS.get(i, "")

            # Shorten sector names if needed
            sector_name = sector_name.replace("Technology", "Tech").replace(
                "Communication", "Comm"
            )

            tweet_parts.append(f"{medal} {sector_name} {self.format_percentage(change_pct)}")

        tweet = "\n".join(tweet_parts)
        tweet += "\n\n#Stocks #Sectors #Market"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def format_vix(self, data: Dict[str, Any]) -> str:
        """Format VIX for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch VIX data"

        content = data.get("data", {})
        price = content.get("price", 0)
        change_pct = content.get("change_percent", 0)
        sentiment = content.get("sentiment", "Unknown")
        trend = self.get_trend_indicator(change_pct)

        tweet = (
            f"{self.EMOJIS['chart']} Market Volatility: {sentiment}\n\n"
            f"VIX: ${price:.2f} {trend}\n"
            f"Change: {self.format_percentage(change_pct)}\n\n"
        )

        if change_pct > 5:
            tweet += f"{self.EMOJIS['warning']} Volatility spike detected!\n\n"

        tweet += "#VIX #Volatility #Markets"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def format_economic_calendar(self, data: Dict[str, Any]) -> str:
        """Format economic calendar for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch economic calendar"

        content = data.get("data", {})
        earnings = content.get("earnings", [])[:5]

        tweet_parts = [f"{self.EMOJIS['calendar']} This Week's Earnings:\n"]

        for earning in earnings:
            ticker = earning.get("ticker", "???")
            date = earning.get("date", "TBD")
            tweet_parts.append(f"• ${ticker} - {date}")

        tweet = "\n".join(tweet_parts)
        tweet += "\n\n#Earnings #Stocks #Calendar"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def format_sec_insider(self, data: Dict[str, Any]) -> str:
        """Format SEC insider trading for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch insider trading data"

        content = data.get("data", {})
        filings = content.get("filings", [])[:3]

        tweet_parts = [f"{self.EMOJIS['eyes']} Recent Insider Activity:\n"]

        for filing in filings:
            ticker = filing.get("ticker", "???")
            transaction = filing.get("transaction_type", "???")
            value = filing.get("value", 0)
            emoji = self.EMOJIS['up'] if "buy" in transaction.lower() else self.EMOJIS['down']

            tweet_parts.append(
                f"{emoji} ${ticker} - {transaction[:10]} (${self.format_large_number(value)})"
            )

        tweet = "\n".join(tweet_parts)
        tweet += "\n\n#InsiderTrading #SEC #Stocks"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def format_yahoo_quote(self, data: Dict[str, Any]) -> str:
        """Format Yahoo Finance quote for Twitter.

        Args:
            data: API response data

        Returns:
            Tweet text
        """
        if not data.get("success"):
            return f"{self.EMOJIS['warning']} Unable to fetch quotes"

        content = data.get("data", {})
        # Handle both formats: {"quotes": [...]} and direct list [...]
        if isinstance(content, list):
            quotes = content[:3]
        else:
            quotes = content.get("quotes", [])[:3]

        tweet_parts = [f"{self.EMOJIS['chart']} Market Update:\n"]

        for quote in quotes:
            ticker = quote.get("ticker", "???")
            price = quote.get("price", 0)
            change_pct = quote.get("change_percent", 0)
            trend = self.get_trend_indicator(change_pct)

            tweet_parts.append(
                f"${ticker} ${price:.2f} ({self.format_percentage(change_pct)}) {trend}"
            )

        tweet = "\n".join(tweet_parts)
        tweet += "\n\n#Stocks #Market #Trading"

        return self.truncate_text(tweet, self.MAX_TWEET_LENGTH)

    def add_hashtags(self, text: str, hashtags: List[str]) -> str:
        """Add hashtags to tweet if space allows.

        Args:
            text: Tweet text
            hashtags: List of hashtags (without #)

        Returns:
            Tweet with hashtags added
        """
        # Limit hashtags
        hashtags = hashtags[: self.MAX_HASHTAGS]

        # Format hashtags
        hashtag_text = " ".join([f"#{tag}" for tag in hashtags])

        # Add if space allows
        combined = f"{text}\n\n{hashtag_text}"
        if len(combined) <= self.MAX_TWEET_LENGTH:
            return combined

        return text
