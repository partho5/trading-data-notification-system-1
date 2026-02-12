"""Trading Data Hub API client with JWT authentication and retry logic."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from .config import Config


class APIClient:
    """Client for Trading Data Hub API with automatic authentication and retries."""

    def __init__(self, config: Config):
        """Initialize API client.

        Args:
            config: Application configuration
        """
        self.config = config
        self.base_url = config.api_base_url
        self.username = config.api_username
        self.password = config.api_password
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.client.aclose()

    async def authenticate(self) -> bool:
        """Authenticate and obtain JWT token.

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Construct login URL (base_url has /data at the end, we need /login)
            login_url = self.base_url.replace("/api/v1/data", "/api/v1/login")

            logger.info(f"Authenticating with Trading Data Hub API at {login_url}")

            # Use files parameter to send as multipart/form-data (like Postman's form-data)
            # This is what the API expects based on the working Postman request
            response = await self.client.post(
                login_url,
                files={
                    "username": (None, self.username),
                    "password": (None, self.password),
                },
            )

            logger.debug(f"Auth response status: {response.status_code}")

            response.raise_for_status()

            data = response.json()
            self.access_token = data.get("access_token")
            if not self.access_token:
                logger.error("No access_token in authentication response")
                return False

            # Assume token expires in 30 days (as per spec)
            self.token_expires_at = datetime.now() + timedelta(days=30)
            logger.info("Authentication successful, token obtained")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"Authentication failed with status {e.response.status_code}: {e}")
            logger.error(f"Response body: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    def _is_token_expired(self) -> bool:
        """Check if the current token is expired or about to expire.

        Returns:
            True if token is expired or expires within 1 hour
        """
        if not self.access_token or not self.token_expires_at:
            return True
        return datetime.now() >= (self.token_expires_at - timedelta(hours=1))

    async def _ensure_authenticated(self):
        """Ensure we have a valid token, refresh if needed."""
        if self._is_token_expired():
            logger.info("Token expired or missing, re-authenticating")
            await self.authenticate()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 3,
    ) -> Dict[str, Any]:
        """Make authenticated API request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            retry_count: Number of retry attempts

        Returns:
            Response JSON data

        Raises:
            httpx.HTTPStatusError: If request fails after retries
        """
        await self._ensure_authenticated()

        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        for attempt in range(retry_count):
            try:
                response = await self.client.request(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                )

                # Handle 401 - re-authenticate and retry once
                if response.status_code == 401:
                    logger.warning("Received 401, re-authenticating")
                    await self.authenticate()
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    response = await self.client.request(
                        method=method,
                        url=url,
                        params=params,
                        headers=headers,
                    )

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code in [500, 503]:
                    # Server errors - retry with exponential backoff
                    if attempt < retry_count - 1:
                        wait_time = 2 ** attempt  # 2s, 4s, 8s
                        logger.warning(
                            f"Request failed with {e.response.status_code}, "
                            f"retrying in {wait_time}s (attempt {attempt + 1}/{retry_count})"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"Request failed after {retry_count} attempts: "
                            f"{e.response.status_code} - {e.response.text}"
                        )
                        raise
                else:
                    # Other errors - don't retry
                    logger.error(
                        f"Request failed with {e.response.status_code}: {e.response.text}"
                    )
                    raise

            except Exception as e:
                if attempt < retry_count - 1:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Request error: {e}, retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{retry_count})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Request failed after {retry_count} attempts: {e}")
                    raise

    # ==================== API Endpoint Methods ====================

    async def get_cnn_fear_greed(self, with_chart: bool = True) -> Dict[str, Any]:
        """Get CNN Fear & Greed Index.

        Args:
            with_chart: Include chart graphic

        Returns:
            Fear & Greed data with historical comparisons
        """
        params = {"ticker": "any", "chart": str(with_chart).lower()}
        return await self._make_request("GET", "cnn_sentiment/fear_greed", params)

    async def get_reddit_trending(self, with_chart: bool = True) -> Dict[str, Any]:
        """Get Reddit trending tickers.

        Args:
            with_chart: Include chart graphic

        Returns:
            Top 20 trending tickers from Reddit
        """
        params = {"ticker": "any", "chart": str(with_chart).lower()}
        return await self._make_request("GET", "reddit/trending", params)

    async def get_top_gainers(
        self, limit: int = 10, with_chart: bool = True
    ) -> Dict[str, Any]:
        """Get top stock gainers from Finviz.

        Args:
            limit: Number of gainers to return
            with_chart: Include chart graphic

        Returns:
            Top gaining stocks with price and volume data
        """
        params = {"ticker": "any", "chart": str(with_chart).lower(), "limit": limit}
        return await self._make_request("GET", "finviz/gainers", params)

    async def get_sector_performance(self, with_chart: bool = True) -> Dict[str, Any]:
        """Get sector performance data.

        Note: This endpoint takes ~13 seconds due to rate limits.

        Args:
            with_chart: Include chart graphic

        Returns:
            All 11 sector ETFs ranked by performance
        """
        params = {"ticker": "any", "chart": str(with_chart).lower()}
        return await self._make_request("GET", "alpha_vantage/sector_performance", params)

    async def get_vix(self) -> Dict[str, Any]:
        """Get VIX volatility index (via VIXY ETF proxy).

        Returns:
            VIX data with sentiment interpretation
        """
        params = {"ticker": "any"}
        return await self._make_request("GET", "alpha_vantage/vix", params)

    async def get_economic_calendar(self) -> Dict[str, Any]:
        """Get economic calendar with upcoming earnings and IPOs.

        Returns:
            Earnings calendar for next 30 days
        """
        params = {"ticker": "any"}
        return await self._make_request("GET", "alpha_vantage/economic_calendar", params)

    async def get_sec_insider_filings(self) -> Dict[str, Any]:
        """Get SEC insider trading filings (Form 4).

        Returns:
            Last 30 days of insider trading activity
        """
        params = {"ticker": "any"}
        return await self._make_request("GET", "sec_edgar/insider_filings", params)

    async def get_yahoo_finance_quote(self, tickers: str = "AAPL,TSLA,NVDA") -> Dict[str, Any]:
        """Get Yahoo Finance quotes for specified tickers.

        Args:
            tickers: Comma-separated ticker symbols

        Returns:
            Real-time quotes with price, volume, and fundamental data
        """
        params = {"ticker": tickers}
        return await self._make_request("GET", "yahoo_finance/quote", params)

    # ==================== Benzinga Endpoints (Premium) ====================

    async def get_benzinga_news(
        self, ticker: str = "all", limit: int = 10
    ) -> Dict[str, Any]:
        """Get breaking news from Benzinga.

        Args:
            ticker: Stock ticker or "all" for market news
            limit: Number of articles to return

        Returns:
            News articles with title, teaser, url, image, etc.
        """
        params = {"ticker": ticker, "limit": limit}
        return await self._make_request("GET", "benzinga/news", params)

    async def get_benzinga_ratings(
        self, ticker: str = "all", action: str = None, limit: int = 10
    ) -> Dict[str, Any]:
        """Get analyst ratings (upgrades/downgrades) from Benzinga.

        Args:
            ticker: Stock ticker or "all"
            action: Filter by "Upgrades", "Downgrades", or None for all
            limit: Number of ratings to return

        Returns:
            Analyst ratings with action, firm, from/to ratings, price target
        """
        params = {"ticker": ticker, "limit": limit}
        if action:
            params["action"] = action
        return await self._make_request("GET", "benzinga/ratings", params)

    async def get_benzinga_earnings(
        self, ticker: str = "all", date_from: str = None, date_to: str = None, limit: int = 20
    ) -> Dict[str, Any]:
        """Get earnings calendar from Benzinga.

        Args:
            ticker: Stock ticker or "all"
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            limit: Number of earnings to return

        Returns:
            Upcoming earnings with date, time, EPS estimate, revenue estimate
        """
        params = {"ticker": ticker, "limit": limit}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return await self._make_request("GET", "benzinga/earnings", params)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
