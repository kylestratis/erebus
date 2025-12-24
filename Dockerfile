# Multi-stage build for smaller final image
FROM python:3.12-slim as builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Production stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 bot && \
    mkdir -p /app && \
    chown -R bot:bot /app

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=bot:bot /app/.venv /app/.venv

# Copy application code
COPY --chown=bot:bot bot/ ./bot/
COPY --chown=bot:bot agents/ ./agents/
COPY --chown=bot:bot config/ ./config/

# Switch to non-root user
USER bot

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Run the bot
CMD ["python", "-m", "bot"]
