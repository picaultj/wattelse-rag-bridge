# Use the specified base image
FROM python:3.13-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# Install system dependencies
# - curl for the container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Handle UID and GID for the application user to avoid permission issues with volumes
# Use build args with defaults that can be overridden
ARG USER_UID=1000
ARG USER_GID=1000

# Create a non-root user
RUN groupadd --gid $USER_GID appuser \
    && useradd --uid $USER_UID --gid $USER_GID -m appuser

# Install project dependencies
# We copy only the files needed for installation first to leverage Docker cache
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir -r pyproject.toml

# Copy the rest of the application code
COPY . .

# Ensure the appuser has permissions for the /app directory
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Container-level liveness check against the server's own /health route
# (see wattelse_mcp/server.py:_health_check) -- WATTELSE_MCP_PORT is provided at
# runtime via env_file/.env; falls back to the app's own default (8000) if unset.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${WATTELSE_MCP_PORT:-8000}/health || exit 1

# Start the server (streamable-http transport; port is set via WATTELSE_MCP_PORT)
CMD ["python", "-m", "wattelse_mcp.server"]
