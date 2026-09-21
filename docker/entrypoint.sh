#!/bin/sh
set -e
mkdir -p /app/data
cd /app/backend

# Behind a reverse proxy (Caddy/Nginx), set IP_RADAR_PROXY_HEADERS=1 so uvicorn
# honors X-Forwarded-For — otherwise every visitor looks like the proxy IP and
# per-IP rate limits share one global bucket. IP_RADAR_FORWARDED_ALLOW_IPS
# (comma-separated IPs/CIDRs, default 172.16.0.0/12 = docker bridge nets) lists
# the proxies uvicorn may trust: it then walks XFF right-to-left and stops at
# the first untrusted hop (the real client), so a client-appended fake prefix
# can never become the rate-limit key. A wrong default merely degrades back to
# the shared bucket. '*' overrides explicitly but trusts any direct client and
# then takes the LEFTMOST XFF entry — attacker-spoofable behind an appending
# proxy; do not use it on a reachable port.
set -- --host 0.0.0.0 --port 8000
if [ "$IP_RADAR_PROXY_HEADERS" = "1" ]; then
    set -- "$@" --proxy-headers \
        --forwarded-allow-ips="${IP_RADAR_FORWARDED_ALLOW_IPS:-172.16.0.0/12}"
fi
exec python -m uvicorn main:app "$@"
