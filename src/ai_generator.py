"""AI-powered content generator using OpenAI GPT-4o-mini."""

import json
from typing import Any, Dict, Optional

from loguru import logger
from openai import AsyncOpenAI

from .config import Config


class AIContentGenerator:
    """Generate natural, insightful content using OpenAI."""

    def __init__(self, config: Config):
        """Initialize AI content generator.

        Args:
            config: Application configuration
        """
        self.config = config
        self.client = AsyncOpenAI(api_key=config.openai_api_key)
        self.model = config.openai_model
        self.max_tokens = config.openai_max_tokens

    async def generate_twitter_post(
        self, endpoint_name: str, data: Dict[str, Any]
    ) -> Optional[str]:
        """Generate Twitter post using AI.

        Args:
            endpoint_name: Name of the data endpoint
            data: API response data

        Returns:
            Generated tweet text or None if generation fails
        """
        prompt = self._build_twitter_prompt(endpoint_name, data)
        if not prompt:
            return None

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional financial analyst writing concise, insightful market updates for Twitter. Focus on key insights and actionable information. Use 1-2 essential emojis maximum. Stay under 250 characters to leave room for hashtags.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=0.7,
            )

            tweet = response.choices[0].message.content.strip()

            # Add hashtags
            tweet += "\n\n#Stocks #Trading"

            # Ensure under 280 characters
            if len(tweet) > 280:
                tweet = tweet[:277] + "..."

            logger.info(f"AI generated Twitter post for {endpoint_name}")
            return tweet

        except Exception as e:
            logger.error(f"AI generation failed for Twitter {endpoint_name}: {e}")
            return None

    async def generate_discord_description(
        self, endpoint_name: str, data: Dict[str, Any]
    ) -> Optional[str]:
        """Generate Discord embed description using AI.

        Args:
            endpoint_name: Name of the data endpoint
            data: API response data

        Returns:
            Generated description or None if generation fails
        """
        prompt = self._build_discord_prompt(endpoint_name, data)
        if not prompt:
            return None

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional financial analyst writing detailed market insights for Discord. Provide clear analysis with context and implications. Use markdown formatting. Keep it concise but informative (3-5 sentences).",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.7,
            )

            description = response.choices[0].message.content.strip()
            logger.info(f"AI generated Discord description for {endpoint_name}")
            return description

        except Exception as e:
            logger.error(f"AI generation failed for Discord {endpoint_name}: {e}")
            return None

    def _build_twitter_prompt(self, endpoint_name: str, data: Dict[str, Any]) -> Optional[str]:
        """Build prompt for Twitter post generation.

        Args:
            endpoint_name: Name of endpoint
            data: API response data

        Returns:
            Prompt string or None
        """
        if not data.get("success"):
            return None

        content = data.get("data", {})

        prompts = {
            "cnn_fear_greed": self._prompt_cnn_fear_greed_twitter,
            "reddit_trending": self._prompt_reddit_trending_twitter,
            "top_gainers": self._prompt_top_gainers_twitter,
            "sector_performance": self._prompt_sector_performance_twitter,
            "vix": self._prompt_vix_twitter,
            "economic_calendar": self._prompt_economic_calendar_twitter,
            "sec_insider": self._prompt_sec_insider_twitter,
            "yahoo_quote": self._prompt_yahoo_quote_twitter,
            # Benzinga (Premium)
            "benzinga_news": self._prompt_benzinga_news_twitter,
            "benzinga_ratings": self._prompt_benzinga_ratings_twitter,
            "benzinga_earnings": self._prompt_benzinga_earnings_twitter,
        }

        prompt_func = prompts.get(endpoint_name)
        if prompt_func:
            return prompt_func(content)
        return None

    def _build_discord_prompt(self, endpoint_name: str, data: Dict[str, Any]) -> Optional[str]:
        """Build prompt for Discord post generation.

        Args:
            endpoint_name: Name of endpoint
            data: API response data

        Returns:
            Prompt string or None
        """
        # For Discord, we can reuse similar prompts but ask for more detail
        twitter_prompt = self._build_twitter_prompt(endpoint_name, data)
        if not twitter_prompt:
            return None

        return f"{twitter_prompt}\n\nProvide more detailed analysis with market context and what traders should watch for."

    # ==================== Prompt Builders ====================

    def _prompt_cnn_fear_greed_twitter(self, content: Dict[str, Any]) -> str:
        score = content.get("score", 0)
        rating = content.get("rating", "Unknown")
        comparisons = content.get("comparisons", {})
        yesterday = comparisons.get("previous_close", 0)
        change = score - yesterday

        indicators = content.get("indicators", [])
        fear_count = sum(1 for ind in indicators if "fear" in ind.get("rating", "").lower())
        greed_count = sum(1 for ind in indicators if "greed" in ind.get("rating", "").lower())

        return f"""Write a concise market sentiment update based on this data:

CNN Fear & Greed Index: {score}/100 ({rating})
Change from yesterday: {change:+.1f} (was {yesterday})
Indicators breakdown: {fear_count} showing fear, {greed_count} showing greed out of {len(indicators)} total

Focus on what this means for traders and market direction. Be insightful and actionable."""

    def _prompt_reddit_trending_twitter(self, content: Dict[str, Any]) -> str:
        tickers = content.get("tickers", [])[:5]
        ticker_list = [f"${t.get('ticker')} ({t.get('mentions')} mentions)" for t in tickers]

        return f"""Write a concise update about Reddit's most talked about stocks:

Top trending tickers:
{chr(10).join(ticker_list)}

Focus on the retail sentiment and what's driving the conversation. Be insightful about the momentum."""

    def _prompt_top_gainers_twitter(self, content: Dict[str, Any]) -> str:
        gainers = content.get("gainers", [])[:3]
        gainer_list = [
            f"{g.get('ticker')}: +{g.get('change_percent', 0):.1f}% (${g.get('price', 0):.2f})"
            for g in gainers
        ]

        return f"""Write a concise update about today's top stock gainers:

{chr(10).join(gainer_list)}

Focus on the strength of the market move and what traders should note. Be insightful."""

    def _prompt_sector_performance_twitter(self, content: Dict[str, Any]) -> str:
        leaders = content.get("leaders", [])[:3]
        laggards = content.get("laggards", [])[:2]

        leader_list = [f"{s.get('sector')}: +{s.get('change_percent', 0):.1f}%" for s in leaders]
        laggard_list = [
            f"{s.get('sector')}: {s.get('change_percent', 0):.1f}%" for s in laggards
        ]

        return f"""Write a concise update about today's sector performance:

Top performers:
{chr(10).join(leader_list)}

Weakest:
{chr(10).join(laggard_list)}

Focus on market rotation and what this sector performance tells us about investor sentiment."""

    def _prompt_vix_twitter(self, content: Dict[str, Any]) -> str:
        price = content.get("price", 0)
        change_pct = content.get("change_percent", 0)
        sentiment = content.get("sentiment", "Unknown")

        return f"""Write a concise update about market volatility:

VIX: ${price:.2f} ({change_pct:+.1f}%)
Market sentiment: {sentiment}

Focus on what this volatility level means for traders and risk management. Be actionable."""

    def _prompt_economic_calendar_twitter(self, content: Dict[str, Any]) -> str:
        earnings = content.get("earnings", [])[:5]
        earnings_list = [f"{e.get('ticker')} on {e.get('date')}" for e in earnings]

        return f"""Write a concise update about upcoming earnings:

This week's key earnings:
{chr(10).join(earnings_list)}

Focus on which reports traders should watch and why they matter."""

    def _prompt_sec_insider_twitter(self, content: Dict[str, Any]) -> str:
        filings = content.get("filings", [])[:3]
        filing_list = [
            f"{f.get('ticker')}: {f.get('transaction_type')} (${f.get('value', 0)/1000000:.1f}M)"
            for f in filings
        ]

        return f"""Write a concise update about recent insider trading:

{chr(10).join(filing_list)}

Focus on what these insider moves might signal about company outlook. Be insightful."""

    def _prompt_yahoo_quote_twitter(self, content: Dict[str, Any]) -> str:
        quotes = content.get("quotes", [])[:3]
        quote_list = [
            f"{q.get('ticker')}: ${q.get('price', 0):.2f} ({q.get('change_percent', 0):+.1f}%)"
            for q in quotes
        ]

        return f"""Write a concise market update for these tickers:

{chr(10).join(quote_list)}

Focus on the overall market direction and key price action. Be actionable."""

    # ==================== Benzinga Prompts (Premium) ====================

    def _prompt_benzinga_news_twitter(self, content: Dict[str, Any]) -> str:
        articles = content.get("articles", [])[:3]

        if not articles:
            return None  # Should never reach here (checked in scheduler), but defensive

        # Extract key information from top articles
        news_items = []
        for article in articles:
            title = article.get("title", "")
            # Extract tickers mentioned
            stocks = article.get("stocks", [])
            tickers = [s.get("name") for s in stocks[:3]]  # Top 3 tickers
            ticker_str = ", ".join(f"${t}" for t in tickers) if tickers else ""

            news_items.append(f"{title[:100]} [{ticker_str}]" if ticker_str else title[:100])

        return f"""Write a concise breaking news alert based on these headlines:

{chr(10).join(news_items)}

Focus on the most significant story and what traders should know. Be urgent and actionable. This is BREAKING news from Benzinga."""

    def _prompt_benzinga_ratings_twitter(self, content: Dict[str, Any]) -> str:
        ratings = content.get("ratings", [])[:5]

        if not ratings:
            return None  # Should never reach here (checked in scheduler), but defensive

        rating_items = []
        for rating in ratings:
            ticker = rating.get("ticker", "???")
            action = rating.get("action", "???")  # Upgrade/Downgrade
            analyst_firm = rating.get("analyst_firm", "Unknown")
            rating_current = rating.get("rating_current", "")
            price_target = rating.get("price_target_current", 0)

            pt_str = f" PT ${price_target}" if price_target else ""
            rating_items.append(f"${ticker}: {action} by {analyst_firm[:20]} to {rating_current}{pt_str}")

        return f"""Write a concise analyst ratings update based on these actions:

{chr(10).join(rating_items)}

Focus on the most significant upgrades/downgrades and what they mean for traders. Be insightful about analyst sentiment."""

    def _prompt_benzinga_earnings_twitter(self, content: Dict[str, Any]) -> str:
        earnings = content.get("earnings", [])[:5]

        if not earnings:
            return None  # Should never reach here (checked in scheduler), but defensive

        earning_items = []
        for earning in earnings:
            ticker = earning.get("ticker", "???")
            date = earning.get("date", "TBD")
            time = earning.get("time", "")
            eps_estimate = earning.get("eps_estimate", "")

            time_str = f" {time}" if time and time != "None" else ""
            eps_str = f" (Est. EPS: ${eps_estimate})" if eps_estimate else ""
            earning_items.append(f"${ticker}: {date}{time_str}{eps_str}")

        return f"""Write a concise earnings calendar alert for upcoming reports:

{chr(10).join(earning_items)}

Focus on which reports matter most and what traders should watch for. This is premium Benzinga data."""

    async def close(self):
        """Close the OpenAI client."""
        await self.client.close()
