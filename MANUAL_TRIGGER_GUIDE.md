# Manual Trigger API Guide

## Overview

The bot includes an HTTP API for manually triggering posts outside the regular schedule. This is useful for:
- 🚨 Breaking news / urgent market updates
- 🔄 Retrying failed posts
- 🧪 Testing individual endpoints
- ⏰ Posting before the scheduled time

## API Endpoints

### 1. Health Check
```bash
curl http://localhost:8080/health
```

**Response:**
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "last_post_time": {"twitter": "2026-02-09T16:00:00Z"},
  "total_posts": 12,
  "successful_posts": 11,
  "failed_posts": 1,
  "rate_limit_blocks": 0
}
```

### 2. View Stats
```bash
curl http://localhost:8080/stats
```

**Response:** Detailed statistics including rate limiter and deduplicator data

### 3. List Scheduled Jobs
```bash
curl http://localhost:8080/jobs
```

**Response:**
```json
{
  "jobs": [
    {
      "id": "cnn_fear_greed",
      "name": "CNN Fear & Greed Index",
      "next_run": "2026-02-09T20:00:00+00:00",
      "trigger": "interval[0:04:00:00]"
    },
    ...
  ],
  "count": 9
}
```

### 4. Manual Trigger (POST)
```bash
curl -X POST http://localhost:8080/trigger/{endpoint}
```

**Available Endpoints:**
- `cnn_fear_greed` - CNN Fear & Greed Index
- `reddit_trending` - Reddit Trending Tickers
- `top_gainers` - Top Stock Gainers
- `sector_performance` - Sector Performance
- `vix` - VIX Volatility Index
- `economic_calendar` - Economic Calendar
- `sec_insider` - SEC Insider Trading
- `yahoo_quote` - Yahoo Finance Quotes

**Example:**
```bash
# Manually trigger CNN Fear & Greed post
curl -X POST http://localhost:8080/trigger/cnn_fear_greed

# Response:
{
  "success": true,
  "message": "Successfully triggered cnn_fear_greed",
  "endpoint": "cnn_fear_greed"
}
```

## Use Cases

### Breaking News - Post Immediately
```bash
# Market just crashed, post VIX immediately
curl -X POST http://localhost:8080/trigger/vix

# Big sector move, post sector performance
curl -X POST http://localhost:8080/trigger/sector_performance
```

### Test Single Endpoint
```bash
# Test Reddit Trending without waiting 2 hours
curl -X POST http://localhost:8080/trigger/reddit_trending
```

### Retry Failed Post
```bash
# Check stats first
curl http://localhost:8080/stats

# Retry the endpoint that failed
curl -X POST http://localhost:8080/trigger/economic_calendar
```

### Post All Endpoints at Once (Bash Script)
```bash
#!/bin/bash
# post_all.sh - Manually trigger all endpoints

endpoints=(
  "cnn_fear_greed"
  "reddit_trending"
  "top_gainers"
  "sector_performance"
  "vix"
  "economic_calendar"
  "sec_insider"
  "yahoo_quote"
)

for endpoint in "${endpoints[@]}"; do
  echo "Triggering $endpoint..."
  curl -X POST "http://localhost:8080/trigger/$endpoint"
  echo ""
  sleep 2  # Respect rate limits
done
```

## Important Notes

### Rate Limits Still Apply
- Manual triggers respect Twitter rate limits (1/min, 15/day)
- If rate limit is reached, the post will be blocked
- Check rate limit status: `curl http://localhost:8080/stats`

### Deduplication Still Active
- If you manually trigger the same endpoint twice in quick succession
- And the data hasn't changed
- The second post will be skipped as a duplicate

### Market Hours Check
- `top_gainers` and `yahoo_quote` check market hours
- Manual trigger during off-hours will be skipped
- Override by temporarily disabling market hours check in code

### Dry Run Mode
- If `DRY_RUN=true` in .env, manual triggers won't actually post
- Logs will show "[DRY RUN] Would post to..."
- Set `DRY_RUN=false` for production

## Integration Examples

### Python Script
```python
import requests

# Trigger endpoint
response = requests.post("http://localhost:8080/trigger/vix")
if response.json()["success"]:
    print("VIX post triggered successfully!")
```

### Cron Job (Post every market open)
```bash
# crontab -e
# Post top gainers at market open (9:30 AM ET) on weekdays
30 9 * * 1-5 curl -X POST http://localhost:8080/trigger/top_gainers
```

### Discord/Slack Bot Integration
```javascript
// In your Discord/Slack bot
if (message.content === '!post vix') {
  fetch('http://localhost:8080/trigger/vix', { method: 'POST' })
    .then(res => res.json())
    .then(data => reply(data.message));
}
```

### Monitoring Alert Integration
```bash
# When monitoring detects high volatility
if [ "$VIX_VALUE" -gt "30" ]; then
  curl -X POST http://localhost:8080/trigger/vix
  curl -X POST http://localhost:8080/trigger/cnn_fear_greed
fi
```

## Troubleshooting

### "Unknown endpoint" Error
```json
{
  "success": false,
  "error": "Unknown endpoint: foo",
  "available": ["cnn_fear_greed", "reddit_trending", ...]
}
```
**Solution:** Use one of the available endpoint names listed

### Rate Limit Reached
**Check current status:**
```bash
curl http://localhost:8080/stats | jq '.rate_limiter'
```

**Solution:** Wait for rate limit window to reset

### Connection Refused
**Solution:** Make sure bot is running and health check port is correct:
```bash
# Check if bot is running
ps aux | grep "python -m src.main"

# Check port in .env
grep HEALTH_CHECK_PORT .env
```

## Security Considerations

### Production Deployment
- The health API is exposed on `0.0.0.0:8080` (all interfaces)
- Consider adding authentication for trigger endpoint
- Use firewall rules to restrict access
- Or bind to `127.0.0.1` only for local access

### Add Basic Auth (Optional)
```python
# In health.py trigger_handler, add:
auth_header = request.headers.get('Authorization')
if auth_header != f'Bearer {YOUR_SECRET_TOKEN}':
    return web.json_response({'error': 'Unauthorized'}, status=401)
```

---

**Quick Commands Reference:**
```bash
# Health check
curl localhost:8080/health

# List jobs
curl localhost:8080/jobs

# Stats
curl localhost:8080/stats

# Trigger post
curl -X POST localhost:8080/trigger/cnn_fear_greed
```
