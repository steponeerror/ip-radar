# Public Deployment Notes

Operational knobs for instances exposed to untrusted networks, expanded from [the README's summary](../README.md#public-demo-guard-opt-in). Applies to the app container in any deployment shape (direct port exposure, reverse proxy, Cloudflare→Caddy chain).

## Public-demo guard (opt-in)

For any instance exposed to the public internet, an opt-in guard middleware hides the write/internal surface from anonymous visitors. Three knobs, all off by default — unset means zero behavior change for self-hosted deployments:

- `IP_RADAR_PUBLIC_DEMO=1` — enable the guard: every route whose dependency tree carries an admin dependency (`require_admin_configured` or `current_superuser`) is derived from the route table on first use and answers **404 as if it doesn't exist** to anonymous visitors — this covers the write/internal surface (`/api/update-db*`, `/api/sources`, `/api/eval*`, `/api/tasks`, `/api/events`, `/api/ops*`, `/api/admin/*`, `/api/users/*`, `/api/auth/jwt/logout`, …) with no hand-maintained list to drift; the two explicit exceptions are `/api/update` (token check lives in the handler body, invisible to the dependency tree — stays hidden) and `POST /api/auth/jwt/login` (the owner must be able to log in from non-allowlisted addresses — stays reachable). Read/query endpoints (`/api/lookup*`, `/api/query/stream`, `/api/upload/stream`, `/api/db-status`) require the `x-ipradar-client: web` header. CORS preflights (OPTIONS carrying both `Origin` and `Access-Control-Request-Method`) pass through for visible routes so browser negotiation is unaffected; on hidden or nonexistent paths the guard itself answers the 404 envelope — hidden and nonexistent are indistinguishable. Loopback (docker healthcheck) and `/api/version` are exempt — bare OPTIONS falls through to the same checks; requests carrying an admin cookie or `Authorization` header are handed to the real auth dependencies (superuser / API-key) — forged credentials get 401/403 there, no bypass. `/api/update/status` requires admin authentication in every deployment (superuser only).
- `IP_RADAR_DEMO_ADMIN_IPS` — maintainer exemption: a comma-separated **direct-peer** allowlist. Only fits deployments where the app port is exposed directly; behind a reverse proxy the peer is always the proxy IP, and `X-Forwarded-For` is client-forgeable (verified to pierce a CF→Caddy chain) — do not trust it by default.
- `IP_RADAR_DEMO_TRUST_XFF=1` — explicitly opt in to first-hop `X-Forwarded-For` matching for the admin exemption. Must be paired with a gateway guarantee (a reverse proxy that strips/overwrites XFF); otherwise a client can forge it.

Security premise of the `IP_RADAR_DEMO_ADMIN_IPS` + `IP_RADAR_DEMO_TRUST_XFF=1` combination: `X-Forwarded-For` is client-forgeable, so trusting the first hop is safe **only** when your gateway (Caddy/Cloudflare chain) is guaranteed to strip/overwrite that header on ingress — by default no header is trusted. Also set `IP_RADAR_PUBLIC_DEMO` to exactly `1`: any other non-empty value enables nothing (the guard stays silently off) and just logs a warning at startup — it never blocks startup.

## Hiding sources from anonymous identities

See [the README](../README.md)'s API section for the key model.

`IP_RADAR_PRIVATE_SOURCES` (comma-separated, read at startup) hides the listed sources from web/anonymous identities and from null-scope keys; an admin can still grant one explicitly to a regular key, but never to the web seed row.
