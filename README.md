# Trading Notification Bot

Automatically share market insights with your trading audience on X (Twitter) and Discord. Get real-time stock, forex, and crypto data delivered as AI-powered posts with charts - helping traders stay informed while you focus on analysis.

## ⚡ Quick Reference

```bash
# Start bot
uv run python -m src.main

# Or run in background
nohup uv run python -m src.main > bot.log 2>&1 &

# Check health
curl http://localhost:8080/health

# Trigger manually
curl -X POST http://localhost:8080/trigger/benzinga_news

# View logs
tail -f logs/bot_*.log

# Stop
pkill -f "python -m src.main"
```

## 📦 One-Command Deployment

**Option 1: Automated Script (Recommended)**
```bash
git clone <repo-url>
cd trading-notification-saqib-khan
./deploy.sh
```
*Guided setup with options for foreground, background, or Docker*

**Option 2: Manual One-Liner**
```bash
git clone <repo-url> && cd trading-notification-saqib-khan && cp .env.example .env && nano .env && uv sync && uv run python -m src.main
```

## Features

- **11 Data Sources**: Benzinga News/Ratings/Earnings (premium), CNN Fear & Greed, Reddit Trending, Top Gainers, Sector Performance, VIX, Economic Calendar, SEC Insider Trading, Yahoo Finance
- **AI-Powered**: Uses OpenAI GPT-4o-mini to generate natural, insightful market updates
- **Optimal Scheduling**: CRON-based, audience-first posting at fixed times (6:30 AM - 4:30 PM ET)
- **Dual Platform**: Posts to both Twitter/X and Discord simultaneously
- **Smart Charts**: Automatically downloads and attaches charts when available
- **Rate Limiting**: Respects Twitter's free tier (17 posts/day max) with SQLite tracking
- **Deduplication**: Never posts the same content twice using content hashing
- **Empty Data Skipping**: Doesn't waste posts on "no updates" - only valuable content
- **Market Hours**: Smart scheduling for market-hours-only endpoints
- **Production Ready**: Docker, systemd, or direct deployment
- **Health Monitoring**: HTTP API for status, stats, manual triggers
- **Comprehensive Logging**: Rotating logs with configurable retention

## Quick Start

### Prerequisites

- Python 3.11+ (recommended 3.12)
- [uv](https://github.com/astral-sh/uv) package manager (`pip install uv`)
- Twitter/X API credentials (OAuth 1.0a) - [Get here](https://developer.twitter.com/)
- Discord webhook URL(s) - [Create in Discord channel settings](https://support.discord.com/hc/en-us/articles/228383668)
- OpenAI API key - [Get here](https://platform.openai.com/api-keys)
- Access to Trading Data Hub API (contact admin for credentials)

### 30-Second Setup

```bash
# Clone, configure, and run
git clone <repository-url>
cd trading-notification-saqib-khan
cp .env.example .env
nano .env  # Add your credentials
uv sync
uv run python -m src.main
```

**That's it!** Bot starts posting at optimal times (6:30 AM - 4:30 PM ET)

## Configuration

All configuration is done via environment variables in `.env` file:

### Required Credentials

| Variable | Description |
|----------|-------------|
| `API_USERNAME` | Trading Data Hub username |
| `API_PASSWORD` | Trading Data Hub password |
| `OPENAI_API_KEY` | OpenAI API key (for AI content generation) |
| `TWITTER_API_KEY` | Twitter API Key (Consumer Key) |
| `TWITTER_API_SECRET` | Twitter API Secret (Consumer Secret) |
| `TWITTER_ACCESS_TOKEN` | Twitter Access Token |
| `TWITTER_ACCESS_TOKEN_SECRET` | Twitter Access Token Secret |
| `DISCORD_WEBHOOKS` | Comma-separated Discord webhook URLs |

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_OPTIMAL_SCHEDULE` | true | Use CRON-based optimal scheduler (recommended) |
| `OPENAI_MODEL` | gpt-4o-mini | OpenAI model for content generation |
| `OPENAI_MAX_TOKENS` | 150 | Max tokens for AI responses |
| `API_BASE_URL` | production URL | Trading Data Hub API base URL |
| `TWITTER_PROXY` | none | Proxy URL for Twitter API requests |
| `TWITTER_MAX_POSTS_PER_DAY` | 17 | Twitter free tier limit |
| `TIMEZONE` | America/New_York | Timezone for scheduling |
| `LOG_LEVEL` | INFO | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `DRY_RUN` | false | If true, don't actually post (testing mode) |

### Optimal Schedule (Default)

When `USE_OPTIMAL_SCHEDULE=true`, bot posts at **fixed times** (not intervals):

**Daily Schedule (USA Eastern Time):**
- **6:30 AM** - Economic Calendar (Mon/Wed/Fri) or VIX (Tue/Thu) or SEC Insider (Sat/Sun)
- **7:00 AM** - Benzinga News
- **7:30 AM** - Benzinga Earnings
- **8:00 AM** - Benzinga Ratings
- **8:30 AM** - CNN Fear & Greed
- **9:00 AM** - Reddit Trending
- **9:45 AM** - Benzinga News
- **10:00 AM** - Yahoo Quotes
- **11:15 AM** - Benzinga News
- **12:00 PM** - Benzinga Ratings
- **1:00 PM** - Benzinga News
- **1:30 PM** - Yahoo Quotes
- **2:00 PM** - Top Gainers
- **2:30 PM** - Benzinga News
- **3:00 PM** - Benzinga Ratings
- **3:30 PM** - Yahoo Quotes
- **4:15 PM** - Benzinga News
- **4:30 PM** - Sector Performance
- **Overnight (8 PM - 6 AM)** - No posts (respects audience sleep)

**Total: 17-18 posts/day** (within Twitter free tier limit)

See [OPTIMAL_SCHEDULE.md](OPTIMAL_SCHEDULE.md) for details on the audience-first strategy.

## Architecture

```
trading-notification-saqib-khan/
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration management
│   ├── api_client.py        # Trading Data Hub API client (11 endpoints)
│   ├── scheduler_v2.py      # Optimal CRON-based scheduler ⭐
│   ├── scheduler.py         # Legacy interval-based scheduler
│   ├── ai_generator.py      # OpenAI GPT-4o-mini content generation ⭐
│   ├── rate_limiter.py      # Twitter rate limit enforcement
│   ├── deduplicator.py      # Duplicate content detection
│   ├── chart_handler.py     # Chart downloading & caching
│   ├── health.py            # Health monitoring + manual triggers
│   ├── formatters/
│   │   ├── base.py          # Base formatter utilities
│   │   ├── twitter.py       # Twitter-specific formatting (280 char)
│   │   └── discord.py       # Discord embed formatting
│   └── platforms/
│       ├── twitter.py       # Twitter/X API client (OAuth 1.0a)
│       └── discord.py       # Discord webhook client
├── data/                    # SQLite databases & chart cache
├── logs/                    # Rotating log files
├── .env                     # Environment configuration
├── pyproject.toml           # Dependencies (uv)
├── Dockerfile               # Docker image
├── docker-compose.yml       # Docker deployment
├── bot.service              # Systemd service file
├── OPTIMAL_SCHEDULE.md      # Scheduling strategy guide ⭐
├── AI_CONTENT_GUIDE.md      # AI generation setup & customization ⭐
└── MIGRATION_TO_OPTIMAL.md  # Migration from old to new scheduler
```

### Component Overview

- **Optimal Scheduler** (`scheduler_v2.py`): CRON-based scheduling at fixed times (6:30 AM - 4:30 PM ET), audience-first strategy, respects market hours
- **AI Generator** (`ai_generator.py`): OpenAI GPT-4o-mini for natural content generation with endpoint-specific prompts, automatic fallback to templates
- **API Client** (`api_client.py`): Handles JWT authentication, retries, token refresh, 11 endpoints including Benzinga premium data
- **Rate Limiter**: Tracks Twitter posts in SQLite, enforces X free tier limit (17/day)
- **Deduplicator**: Uses content hashing (SHA256) to prevent duplicate posts
- **Empty Data Skip**: Checks data before AI calls, skips empty responses (saves API costs + post slots)
- **Chart Handler**: Downloads, validates, and caches chart images with PIL
- **Formatters**: Platform-specific content formatting (Twitter 280 char limit, Discord rich embeds)
- **Platform Clients**: Handle posting to Twitter (OAuth 1.0a with proxy support) and Discord (webhooks)
- **Health Monitor**: HTTP API for status, stats, manual triggers, scheduled jobs

## Deployment

### ⚡ Quick Deploy (Direct)

```bash
# One command - run in background
nohup uv run python -m src.main > bot.log 2>&1 &

# Check status
curl http://localhost:8080/health

# View logs
tail -f logs/bot_*.log

# Stop
pkill -f "python -m src.main"
```

### Docker (Recommended for Production)

```bash
# One command - build and start
docker-compose up -d

# Useful commands
docker-compose logs -f    # View logs
docker-compose restart    # Restart
docker-compose down       # Stop
```

### Systemd Service (Auto-restart)

```bash
# One-time setup
sudo cp bot.service /etc/systemd/system/trading-bot.service
sudo systemctl enable trading-bot && sudo systemctl start trading-bot

# Manage
sudo systemctl status trading-bot     # Check status
sudo systemctl restart trading-bot    # Restart
sudo journalctl -u trading-bot -f     # View logs
```

## Health Monitoring & Manual Triggers

The bot exposes an HTTP API on port 8080:

```bash
# Check health
curl http://localhost:8080/health

# Get detailed stats
curl http://localhost:8080/stats

# View scheduled jobs
curl http://localhost:8080/jobs

# Manually trigger any endpoint (doesn't count against daily limit)
curl -X POST http://localhost:8080/trigger/benzinga_news
curl -X POST http://localhost:8080/trigger/yahoo_quote
```

**Health Response:**
```json
{
  "status": "healthy",
  "uptime_seconds": 86400,
  "last_post_time": {"twitter": "2026-02-11T07:00:00Z"},
  "total_posts": 15,
  "successful_posts": 15,
  "failed_posts": 0,
  "rate_limit_blocks": 0
}
```

See [MANUAL_TRIGGER_GUIDE.md](MANUAL_TRIGGER_GUIDE.md) for use cases.

## Adding a New Endpoint

To add a new data source:

1. **Add API method** in `src/api_client.py`:
   ```python
   async def get_new_data(self) -> Dict[str, Any]:
       params = {"ticker": "any"}
       return await self._make_request("GET", "new/endpoint", params)
   ```

2. **Add formatters** in `src/formatters/`:
   - Add method to `TwitterFormatter`
   - Add method to `DiscordFormatter`

3. **Add job handler** in `src/scheduler.py`:
   ```python
   async def job_new_data(self):
       logger.info("Running job: New Data")
       data = await self.api_client.get_new_data()
       chart_url = data.get("data", {}).get("graphics")
       await self._post_content("new_data", data, chart_url)
   ```

4. **Schedule the job** in `add_jobs()` method:
   ```python
   if self.config.schedule_new_data > 0:
       self.scheduler.add_job(
           self.job_new_data,
           trigger=IntervalTrigger(minutes=self.config.schedule_new_data),
           id="new_data",
           name="New Data Source",
       )
   ```

5. **Add config** in `src/config.py`:
   ```python
   schedule_new_data: int = Field(default=120, description="New Data interval")
   ```

6. **Add to .env.example**:
   ```bash
   SCHEDULE_NEW_DATA=120
   ```

## Removing an Endpoint

To disable an endpoint:

1. **Quick disable**: Set schedule to 0 in `.env`:
   ```bash
   SCHEDULE_CNN_FEAR_GREED=0
   ```

2. **Complete removal**:
   - Remove job handler from `scheduler.py`
   - Remove API method from `api_client.py`
   - Remove formatters from `formatters/*.py`
   - Remove config field from `config.py`

## Troubleshooting

### Bot won't start

```bash
# Check credentials
cat .env | grep -E "API_|TWITTER_|DISCORD_"

# Validate config
uv run python -c "from src.config import load_config; c = load_config(); print(c.validate_required_credentials())"

# Check logs
tail -f logs/bot_*.log
```

### Twitter rate limit exceeded

```bash
# Check rate limiter stats
sqlite3 data/post_history.db "SELECT COUNT(*) FROM twitter_posts WHERE posted_at > datetime('now', '-24 hours');"

# Wait or increase limits in .env
TWITTER_MAX_POSTS_PER_DAY=30
```

### Duplicate posts

```bash
# Check deduplicator
sqlite3 data/post_history.db "SELECT endpoint, platform, COUNT(*) FROM content_hashes GROUP BY endpoint, platform;"

# Clear old hashes
sqlite3 data/post_history.db "DELETE FROM content_hashes WHERE posted_at < datetime('now', '-7 days');"
```

### Chart download failures

```bash
# Check chart cache
ls -lh data/chart_cache/

# Test chart download
curl -I <chart-url>

# Clear cache
rm data/chart_cache/*.png
```

## Development

### Run in dry-run mode (no actual posting)

```bash
# Edit .env
DRY_RUN=true

# Run
uv run python -m src.main
```

### Run with debug logging

```bash
LOG_LEVEL=DEBUG uv run python -m src.main
```

### Format code

```bash
uv run black src/
uv run ruff check src/
```

## Tech Stack

- **Python 3.12** - Modern async/await
- **OpenAI** - GPT-4o-mini for AI content generation
- **httpx** - Async HTTP client
- **tweepy** - Twitter/X API (OAuth 1.0a)
- **discord-webhook** - Discord webhooks
- **APScheduler** - CRON-based job scheduling
- **SQLite** - Data persistence (rate limits, deduplication)
- **Pillow** - Image validation
- **loguru** - Logging with rotation
- **Pydantic** - Config validation
- **uv** - Fast Python package manager

## License

MIT License - See LICENSE file

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## Support

For issues or questions:
- Check the troubleshooting section above
- Review logs in `logs/` directory
- Open an issue on GitHub

---

Built with ❤️ for the trading community
