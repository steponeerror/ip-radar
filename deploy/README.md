# Public Deployment Notes

Operational knobs for instances exposed to untrusted networks, expanded from the README's summary. Applies to the app container in any deployment shape (direct port exposure, reverse proxy, Cloudflare→Caddy chain).

## Public-demo guard (opt-in)

For any instance exposed to the public internet, an opt-in guard middleware hides the write/internal surface from anonymous visitors. Three knobs, all off by default — unset means zero behavior change for self-hosted deployments:

- `IP_RADAR_PUBLIC_DEMO=1` — enable the guard: write/internal endpoints (`/api/update-db`, `/api/sources`, `/api/eval`, `/api/tasks`, `/api/events`, `/api/update`, …) answer **404 as if they don't exist** to anonymous visitors; read/query endpoints (`/api/lookup*`, `/api/query/stream`, `/api/upload/stream`, `/api/db-status`) require the `x-ipradar-client: web` header. Real CORS preflights (OPTIONS carrying both `Origin` and `Access-Control-Request-Method`), loopback (docker healthcheck), and `/api/version` are exempt — bare OPTIONS falls through to the same checks; requests carrying an admin cookie or `Authorization` header are handed to the real auth dependencies (superuser / API-key) — forged credentials get 401/403 there, no bypass. `/api/update/status` requires admin authentication in every deployment (superuser only).
- `IP_RADAR_DEMO_ADMIN_IPS` — maintainer bypass: a comma-separated **direct-peer** allowlist. Only fits deployments where the app port is exposed directly; behind a reverse proxy the peer is always the proxy IP, and `X-Forwarded-For` is client-forgeable (verified to pierce a CF→Caddy chain) — do not trust it by default.
- `IP_RADAR_DEMO_TRUST_XFF=1` — explicitly opt in to first-hop `X-Forwarded-For` matching for the admin bypass. Must be paired with a gateway guarantee (a reverse proxy that strips/overwrites XFF); otherwise a client can forge it.

Security premise of the `IP_RADAR_DEMO_ADMIN_IPS` + `IP_RADAR_DEMO_TRUST_XFF=1` combination: `X-Forwarded-For` is client-forgeable, so trusting the first hop is safe **only** when your gateway (Caddy/Cloudflare chain) is guaranteed to strip/overwrite that header on ingress — by default no header is trusted. Also set `IP_RADAR_PUBLIC_DEMO` to exactly `1`: any other non-empty value enables nothing (the guard stays silently off) and just logs a warning at startup — it never blocks startup.

## Hiding sources from anonymous identities

Moved from the README API section:

`IP_RADAR_PRIVATE_SOURCES` (comma-separated, read at startup) hides the listed sources from web/anonymous identities and from null-scope keys; an admin can still grant one explicitly to a regular key, but never to the web seed row.
