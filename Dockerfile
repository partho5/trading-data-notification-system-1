# Multi-stage Dockerfile for Trading Notification Bot

FROM python:3.12-slim AS builder

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies
RUN uv venv && \
    . .venv/bin/activate && \
    uv pip install -e .

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/
COPY pyproject.toml ./

# Create data directories
RUN mkdir -p data/chart_cache logs

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose health check port
EXPOSE 8080

# Run the bot
CMD ["python", "-m", "src.main"]
