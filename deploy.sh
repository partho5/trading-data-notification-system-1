#!/bin/bash
# One-command deployment script for Trading Notification Bot

set -e

echo "🚀 Trading Notification Bot - One-Command Deploy"
echo "================================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✓ .env created from .env.example"
    else
        echo "❌ .env.example not found!"
        exit 1
    fi

    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your credentials:"
    echo "   - API_USERNAME & API_PASSWORD (Trading Data Hub)"
    echo "   - OPENAI_API_KEY (OpenAI)"
    echo "   - TWITTER_* credentials (Twitter/X API)"
    echo "   - DISCORD_WEBHOOKS (Discord)"
    echo ""
    read -p "Press Enter after editing .env..."
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv package manager..."
    pip install uv
    echo "✓ uv installed"
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
uv sync
echo "✓ Dependencies installed"

# Start bot
echo ""
echo "🤖 Starting bot..."
echo ""
echo "Options:"
echo "  1) Run in foreground (see output, Ctrl+C to stop)"
echo "  2) Run in background (nohup, check logs with 'tail -f logs/bot_*.log')"
echo "  3) Run with Docker (docker-compose up -d)"
echo ""
read -p "Choose option (1-3): " choice

case $choice in
    1)
        echo "Starting in foreground..."
        uv run python -m src.main
        ;;
    2)
        echo "Starting in background..."
        nohup uv run python -m src.main > bot.log 2>&1 &
        PID=$!
        echo "✓ Bot started (PID: $PID)"
        echo ""
        echo "Useful commands:"
        echo "  tail -f logs/bot_*.log          # View logs"
        echo "  curl http://localhost:8080/health    # Check status"
        echo "  pkill -f 'python -m src.main'   # Stop bot"
        ;;
    3)
        if ! command -v docker-compose &> /dev/null; then
            echo "❌ docker-compose not found!"
            exit 1
        fi
        echo "Starting with Docker..."
        docker-compose up -d
        echo "✓ Bot started in Docker"
        echo ""
        echo "Useful commands:"
        echo "  docker-compose logs -f           # View logs"
        echo "  docker-compose restart           # Restart"
        echo "  docker-compose down              # Stop"
        ;;
    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📊 Monitor bot:"
echo "  http://localhost:8080/health  # Health status"
echo "  http://localhost:8080/stats   # Statistics"
echo "  http://localhost:8080/jobs    # Scheduled jobs"
echo ""
echo "📅 Bot posts at fixed times daily (6:30 AM - 4:30 PM ET)"
echo "   See OPTIMAL_SCHEDULE.md for complete schedule"
echo ""
