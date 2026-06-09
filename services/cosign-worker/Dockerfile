# cosign-worker — Python 3.12 + uv. Runs as root because the DockerDriver needs
# access to the mounted docker socket (hardening: map to a docker-group GID).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# git + ca-certificates for any runtime needs; libstdc++ ships in the base.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev
COPY . .

EXPOSE 8001 50052
LABEL org.opencontainers.image.title="cosign-worker"
CMD ["python", "-m", "cosign_worker"]
