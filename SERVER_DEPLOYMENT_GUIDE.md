# 🚀 Server Deployment Guide

## Quick Deploy (Pull Latest Code & Restart)

This guide is for deploying the latest bot updates on your production server.

---

## ⚡ One-Command Deploy

```bash
cd /root/trading-data-notification-system-1 && \
git pull origin main && \
pkill -f "python -m src.main" && \
sleep 2 && \
nohup uv run python -m src.main > bot.log 2>&1 & \
sleep 5 && \
curl http://localhost:8080/health
```

**What this does:**
1. Navigate to bot directory
2. Pull latest code from GitHub
3. Stop current bot process
4. Wait 2 seconds for cleanup
5. Start bot in background
6. Wait 5 seconds for startup
7. Check health to verify success

---

## 📋 Step-by-Step Deploy

If you prefer manual steps:

### 1. Navigate to Bot Directory
```bash
cd /root/trading-data-notification-system-1
```

### 2. Pull Latest Code
```bash
git pull origin main
```

**Expected output:**
```
Updating 01cb29c..c291405
Fast-forward
 src/health.py        | 58 ++++++++++++++++++++++++++--------------
 src/scheduler_v2.py  | 38 +++++++++++++++++--------
 2 files changed, 88 insertions(+), 38 deletions(-)
```

### 3. Stop Current Bot
```bash
pkill -f "python -m src.main"
```

**Verify it stopped:**
```bash
ps aux | grep "python.*src.main" | grep -v grep
# Should return nothing
```

### 4. Start Bot in Background
```bash
nohup uv run python -m src.main > bot.log 2>&1 &
```

**Get the process ID:**
```bash
echo $!
# Save this PID for later reference
```

### 5. Verify Bot Started Successfully
```bash
# Wait 5 seconds for startup
sleep 5

# Check health
curl http://localhost:8080/health
```

**Expected healthy response:**
```json
{
  "status": "healthy",
  "uptime_seconds": 5,
  "total_posts": 0,
  "successful_posts": 0
}
```

### 6. Monitor Logs
```bash
# Real-time logs
tail -f logs/bot_*.log

# Or check bot.log
tail -f bot.log
```

**Look for these success indicators:**
```
INFO     | Optimal scheduler started with CRON-based posting
INFO     | Health monitor started on port 8080
INFO     | Bot is running. Press Ctrl+C to stop.
```

---

## 🔍 Verification Checklist

After deployment, verify everything is working:

### ✅ 1. Process Running
```bash
ps aux | grep "python -m src.main"
```
Should show the bot process.

### ✅ 2. Health Endpoint
```bash
curl http://localhost:8080/health
```
Should return `"status": "healthy"`.

### ✅ 3. Scheduled Jobs
```bash
curl http://localhost:8080/jobs | python3 -m json.tool | head -30
```
Should show 18-20 scheduled jobs.

### ✅ 4. Manual Test Post
```bash
curl -X POST http://localhost:8080/trigger/benzinga_news
```
Should return `"success": true` and post to Discord + Twitter.

### ✅ 5. Check Discord
- Open your Discord channel
- Verify the test post appeared
- Check title shows "📰 Benzinga News" (not "⚠️ Error")

### ✅ 6. Check Twitter/X
- Open your Twitter profile
- Verify the test post appeared

---

## 🐛 Troubleshooting

### Bot Won't Start

**Problem:** `pkill` doesn't stop the old bot

**Solution:**
```bash
# Find and kill manually
ps aux | grep "python.*src.main"
kill -9 <PID>
```

---

### Health Endpoint Not Responding

**Problem:** `curl http://localhost:8080/health` times out

**Solution:**
```bash
# Check if port is in use
netstat -tlnp | grep 8080

# Check bot logs for errors
tail -30 logs/bot_*.log

# Check bot.log
tail -30 bot.log
```

---

### Git Pull Conflicts

**Problem:** `git pull` shows conflicts

**Solution:**
```bash
# Stash local changes
git stash

# Pull latest
git pull origin main

# Apply stashed changes (if needed)
git stash pop
```

---

### Bot Crashes Immediately

**Problem:** Bot starts but exits after a few seconds

**Solution:**
```bash
# Check logs for errors
tail -50 logs/bot_*.log

# Common issues:
# 1. Missing .env file
ls -la .env

# 2. Invalid credentials
grep -E "API_USERNAME|TWITTER_API_KEY|DISCORD_WEBHOOKS" .env

# 3. Permission issues
ls -la data/
chmod 755 data/
```

---

## 📊 Monitoring After Deploy

### Check Post Statistics
```bash
curl http://localhost:8080/stats
```

**Expected output:**
```json
{
  "total_posts": 5,
  "successful_posts": 5,
  "failed_posts": 0,
  "skipped_duplicates": 0,
  "rate_limit_blocks": 0
}
```

### Monitor Scheduled Posts
```bash
# See next 5 scheduled posts
curl http://localhost:8080/jobs | python3 -m json.tool | grep -A1 "next_run" | head -10
```

### Watch Live Logs
```bash
# Follow bot logs in real-time
tail -f logs/bot_*.log

# Filter for important events only
tail -f logs/bot_*.log | grep -E "Posted|ERROR|Running job"
```

---

## 🔄 Rollback (If Needed)

If the new version has issues, rollback to previous version:

### 1. Find Previous Commit
```bash
git log --oneline -5
```

**Example output:**
```
c291405 (HEAD -> master, origin/main) Fix critical bugs
01cb29c Add complete trading bot with AI generation
07eb726 Merge remote-tracking branch 'origin/main'
```

### 2. Rollback to Previous Commit
```bash
# Stop bot
pkill -f "python -m src.main"

# Rollback
git reset --hard 01cb29c

# Restart
nohup uv run python -m src.main > bot.log 2>&1 &
```

---

## 📝 What Changed in This Deploy

### Bug Fixes (c291405)

1. **Deduplicator crash fixed**
   - Was crashing with: `missing 1 required positional argument: platform`
   - Now correctly tracks duplicates per platform (Twitter/Discord)

2. **Discord titles fixed**
   - Before: Showed "⚠️ Error" as title
   - After: Shows proper titles like "📰 Benzinga News", "📊 Market Sentiment"

3. **Client methods fixed**
   - Discord: `post()` → `post_embed()`
   - Twitter: `await post()` → `post_tweet()`

4. **Manual triggers fixed**
   - Health monitor now compatible with OptimalScheduler
   - Can trigger any endpoint: `/trigger/benzinga_news`

### Features Still Working

✅ AI-powered content generation (GPT-4o-mini)
✅ 11 data endpoints (Benzinga, Yahoo, CNN, Reddit, etc.)
✅ Optimal scheduling (6:30 AM - 4:30 PM ET)
✅ Empty data skipping (saves post slots)
✅ Rate limiting (15 posts/day max)
✅ Deduplication (no duplicate posts)
✅ Dual platform posting (Twitter + Discord)

---

## 🎯 Success Indicators

After deploy, you should see:

### In Logs
```
✓ Optimal scheduler started with CRON-based posting
✓ Health monitor started on port 8080
✓ Bot is running. Press Ctrl+C to stop.
✓ Total daily posts: 18.0 (target: 17)
✓ AI content generator initialized (using OpenAI GPT-4o-mini)
```

### In Discord
- Posts appear with proper titles
- AI-generated descriptions
- Posted to both webhooks

### On Twitter
- Posts appear successfully
- Natural language (not template text)
- Within rate limits

---

## 🆘 Emergency Contacts

If deployment fails or bot misbehaves:

1. **Stop immediately:**
   ```bash
   pkill -f "python -m src.main"
   ```

2. **Check logs:**
   ```bash
   tail -100 logs/bot_*.log
   ```

3. **Contact developer** with:
   - Error messages from logs
   - Output of `curl http://localhost:8080/health`
   - Last 50 lines of `bot.log`

---

## ✅ Post-Deploy Checklist

After successful deployment:

- [ ] Bot process is running (`ps aux | grep python`)
- [ ] Health endpoint responds (`curl http://localhost:8080/health`)
- [ ] Scheduled jobs are loaded (`curl http://localhost:8080/jobs`)
- [ ] Manual test post works (`curl -X POST http://localhost:8080/trigger/benzinga_news`)
- [ ] Discord shows proper titles (not "Error")
- [ ] Twitter post successful
- [ ] Logs show no errors
- [ ] Rate limiter working (check stats)

---

**Deployment Date:** 2026-02-13
**Version:** c291405 (Bug fix release)
**Deploy Time:** ~2 minutes
**Downtime:** ~5 seconds

🎉 **You're all set! The bot is now running with all bug fixes applied.**
