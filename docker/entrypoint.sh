#!/bin/sh
set -e
mkdir -p /app/data
cd /app/backend

# Behind a reverse proxy (Caddy/Nginx), set IP_RADAR_PROXY_HEADERS=1 so uvicorn
# honors X-Forwarded-For — otherwise every visitor looks like the proxy IP and
# per-IP rate limits share one global bucket. '*' trusts any direct client:
# right for the compose topology where uvicorn is only reachable via the proxy;
# narrow it if uvicorn is exposed beyond the trusted proxy.
set -- --host 0.0.0.0 --port 8000
if [ "$IP_RADAR_PROXY_HEADERS" = "1" ]; then
    set -- "$@" --proxy-headers --forwarded-allow-ips='*'
fi
exec python -m uvicorn main:app "$@"
