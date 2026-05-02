FROM python:3.12-slim

# curl: docker-compose healthcheck. gosu: drop privileges from root → throughline
# user inside the entrypoint (needed because bind-mount targets are owned by
# root on the host and our unprivileged user couldn't write to them otherwise).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gosu \
    && rm -rf /var/lib/apt/lists/*

# Non-root user with a known UID so volume permissions are predictable.
RUN useradd --create-home --uid 1000 throughline
WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Pre-create bind-mount targets so the entrypoint's chown has something to work
# on even when the dirs come from named volumes (no host bind-mount).
RUN mkdir -p /app/.throughline /app/.docs \
    && chown -R throughline:throughline /app

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV THROUGHLINE_HOST=0.0.0.0 \
    THROUGHLINE_PORT=8765 \
    THROUGHLINE_DB_PATH=/app/.throughline/state.db \
    THROUGHLINE_DOCS_DIR=/app/.docs

EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=3s --retries=5 --start-period=5s \
    CMD curl -fsS http://localhost:8765/health || exit 1

# Entrypoint runs as root, fixes mount perms, then execs as 'throughline' via gosu.
ENTRYPOINT ["/entrypoint.sh"]
