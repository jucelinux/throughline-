#!/bin/sh
# Entrypoint: ensure data dirs are writable by the 'throughline' user, then
# drop privileges. Required because docker creates bind-mount targets as root
# on the host, and the unprivileged container user can't write there otherwise.
set -eu

if [ "$(id -u)" = "0" ]; then
    # Best-effort: chown bind-mounted dirs. Ignore failures (read-only mounts).
    for d in /app/.throughline /app/.docs; do
        if [ -d "$d" ]; then
            chown -R throughline:throughline "$d" 2>/dev/null || true
        fi
    done
    exec gosu throughline python -m throughline
fi

exec python -m throughline
