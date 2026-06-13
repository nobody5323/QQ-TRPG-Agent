#!/bin/sh
# Bot entrypoint — keep alive even when WS connection drops temporarily
while true; do
    echo "[bot] Starting at $(date)" >&2
    python -u -m app.bot
    rc=$?
    echo "[bot] Exited with code $rc at $(date), restarting in 5s..." >&2
    sleep 5
done
