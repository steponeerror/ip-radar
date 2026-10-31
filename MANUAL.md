# IP Radar — User Manual

**English** | [简体中文](MANUAL.zh-CN.md)

This is the manual for people who have deployed IP Radar (or are about to): how to query, how to read what comes back, how to run the admin console, the full API surface, and how to operate the box day to day. For installation, the source catalog, and the project pitch, see the [README](README.md) — this manual is the deep reference it links to.

All examples below assume the default deployment: one container on `http://127.0.0.1:8000`, data in the `ipradar-data` volume. Screenshots were taken from the English dark theme; the UI also ships Simplified Chinese, Traditional Chinese, and a light theme (toggle in the top-right corner).

## Contents

- [1. First run](#1-first-run)
- [2. Querying](#2-querying)
- [3. Reading results](#3-reading-results)
- [4. Exports](#4-exports)
- [5. The admin console](#5-the-admin-console)
- [6. Source lifecycle: add → evaluate → tune](#6-source-lifecycle-add--evaluate--tune)
- [7. API reference](#7-api-reference)
- [8. Troubleshooting](#8-troubleshooting)
- [9. Operations](#9-operations)
- [10. Around the project](#10-around-the-project)

## 1. First run

After `docker compose up -d --build`, the container is reachable within seconds — but it is not finished yet. On first start it downloads and builds every keyless feed (54 of the 61 sources) into millions of records. What you will see:

- **A progress banner at the top** tracks the download/build progress of the keyless feeds, live. It disappears (or goes quiet) once the build settles.
- **Queries hold until the keyless build settles.** Until then, lookups answer `503` with `X-IPRadar-Reason: warming` — the tool refuses to serve verdicts on a half-built dataset. This is deliberate: never a verdict on partial evidence.
- **A safety window, tiered by RAM** (30 min under 6 GB, 20 min under 12 GB, 15 min above), guarantees a stalled build can't lock queries forever — after the window, the container serves whatever coverage exists. Override with `IP_RADAR_COLD_START_TIMEOUT` (seconds) if you need to.
- **Subsequent starts load from the `ipradar-data` volume in seconds.** The cold start happens once.

Expect the first build to take a while and to consume disk: budget **≥ 6 GB** for the data volume. RAM-wise the build bends its concurrency to what the host has; on small boxes it will grind swap but recover. The seven keyed sources (AbuseIPDB, OTX ×2, IP2Proxy, IPinfo, ThreatFox, URLhaus) stay dark until you add keys to `.env.local` — see the README [Quick Start](README.md#quick-start) table.

The status bar at the bottom of the page shows the live state of the store:

```
19,464,131 records | 12,231,840 scalar · 3,926,761 threat · 3,305,530 asset | Updated 2026-10-15T12:29:24Z (stale)
```

Total records split into scalar (geo/ASN/range facts), threat (per-type evidence), and asset (proxy/VPN/Tor/service attributes). `(stale)` marks that the newest refresh slot hasn't completed everywhere — routine during staggered refreshes; see [Sources tab](#5-the-admin-console).

## 2. Querying

![The query page: input area and empty results](assets/manual/01-lookup-input.png)

The main page is one screen: an input area on top, results below.

**Input modes** (tabs at the top of the input card):

- **Text Input** — one entry per line. Each line can be a bare IPv4 (`1.1.1.1`), a bare IPv6 (`2001:db8::1`), or a CIDR range (`1.2.3.0/24`). Ranges are expanded server-side; small ranges stream back row by row, large ones arrive as a CSV download (see below). Invalid lines are counted and reported, not silently dropped.
- **File Upload** — same format expectations, one IP/range per line, uploaded as a file.

**Deep links**: `?ip=<address>` runs a single lookup automatically when the page opens — this is what the README's sample links use. Book one per report template if you paste IPs into documents all day.

**Results table**: one row per expanded address, columns `IP · ASN · Country · City · Operator · Verdict · Tags · Range`. Every column header sorts. The small numbers in parentheses next to values are per-field consensus confidences — see the next chapter for how to read them. The filter box above the table narrows by IP, org, country, or range; pagination is 20/50/100/200 per page.

**Row capacity**: tables render up to **50,000** expanded rows. Above that the UI switches modes and streams the results straight into a CSV download instead of a table — the same query, zero DOM cost. (React state memory is the real ceiling, roughly ~50k rows × ~2 KB.)

**Disagreement tooling** (buttons above the table): **Disagreements first** re-sorts so rows where sources contradict each other (different countries, different ASNs) float to the top; **Expand disagreements** opens the per-source evidence for exactly those fields inline. For triage workflows this is the fast lane: the rows that need a human are the rows where machines disagreed.

**Theme & language**: the ☀/🌙 toggle switches light/dark and is remembered across visits (restored before first paint — no flash of the wrong theme). EN / 简体 / 繁體 switch the interface language.

## 3. Reading results

### The verdict line

Every lookup returns one fused verdict — `benign`, `suspicious`, or `malicious` — with a 0–100 confidence. The fusion is a log-odds (Bayesian) model over per-source evidence: each source carries a hand-set reliability, threat assertions decay with a 60-day half-life (yesterday's sighting weighs more than last quarter's; scalar facts like geo don't decay), and independent corroboration multiplies up. Two honest caveats are built into the semantics:

- **0 means "no evidence", not "innocent".** A clean verdict on an address no list has ever seen is weak evidence of innocence, and the UI and API both treat it that way (`threat.verdict: "benign", confidence: 0`).
- **Confidence is per-field, not just per-verdict.** The same IP can be `Country NL (88)` and `City Amsterdam (52)` — the table shows each field's own consensus.

![A malicious lookup: verdict, per-type tags, per-field confidences](assets/manual/02-result-malicious.png)

The **Tags** cell carries the classification types that fired (`Abuse reports · Spam · Blacklist · Scanner · … · C2·cobalt_strike`), the number of distinct sources that hit (`14src`), whether any evidence comes from the decay archive (`incl. archive` = some sightings are old enough to be decayed, but they're still on the table), and malware families where a source named one.

![A clean lookup: benign verdict, geo/ASN enrichment](assets/manual/03-result-clean.png)

A clean IP still comes back rich: country/city/ASN with per-field confidence, registration data (registry, registering country, allocation date), ISP classification for CN networks (`is_isp`), and asset attributes — anycast (`is_anycast`), carrier, the AS's domain (`as_domain`). Known infrastructure also shows its service identity: `8.8.8.8` comes back labeled DNS · Google Public DNS.

### Per-field consensus

Click any row to expand its detail panel — every field's fusion is laid out there (the API exposes the same structure; trimmed):

```json
"country": {
  "value": "NL", "confidence": 88, "algorithm": "logodds",
  "sources": [
    {"source": "dbip_city",     "value": "AD", "reliability": 0.80},
    {"source": "geolite_city",  "value": "NL", "reliability": 0.85},
    {"source": "ipinfo_lite",   "value": "NL", "reliability": 0.95},
    {"source": "iptoasn",       "value": "GB", "reliability": 0.90}
  ],
  "alternatives": [
    {"value": "NL", "probability": 88.5},
    {"value": "GB", "probability": 7.4},
    {"value": "AD", "probability": 3.3}
  ]
}
```

Four fusion algorithms exist, and every fused value badges which one produced it:

| Badge | Algorithm | Used for | Meaning |
|---|---|---|---|
| σ P | `logodds` | country, ASN, per-type threat | posterior probability via log-odds Bayesian fusion |
| ▮ share | `voting` | city (and other multi-option votes) | weighted vote share across sources |
| ★ r | `authority` | AS org, AS name | single trusted source; confidence = its reliability |
| ◇ fixed | `specificity` | IP range | fixed anchors — most specific covering range wins |

The `sources[]` breakdown is the full evidence for that field — who said what, at what reliability. `alternatives[]` are the losing candidates with their probabilities, which is how you notice a contested field without expanding anything.

### Per-type threat evidence

Each classification type (IntelMQ vocabulary: `abuse-reports`, `spam`, `blacklist`, `scanner`, `brute-force`, `c2-server`, `ddos`, `exploit`, `infected-system`, `other`) carries its own fused verdict plus the lossless per-source detail:

```json
"spam": {
  "verdict": "malicious", "detected": true, "confidence": 82,
  "algorithm": "logodds", "corroborated": true, "reporter_total": 9,
  "details": [
    {"source": "blocklist_de",  "verdict": "malicious", "native_categories": ["bots", "all"]},
    {"source": "reportedip",    "verdict": "malicious", "native_confidence": 87,
     "first_seen": "2026-10-13T01:04:28", "native_categories": ["Email Spam", "WP Fake SEO Bot"]},
    {"source": "stopforumspam", "verdict": "suspicious", "native_confidence": 62, "reporter_count": 9},
    {"source": "firehol",       "verdict": "informational", "tags": ["firehol_abusers_30d"]}
  ]
}
```

The fields worth knowing: `corroborated` (more than one independent source agrees), `reporter_total` (how many human reporters, where a source counts them), `verdict_conflict` (sources actively disagree on direction — e.g. one says malicious, another benign), `malware_names` (families, e.g. `win.cobalt_strike`), `native_confidence` / `native_categories` / `tags` / `extra` (the upstream's own labels, preserved verbatim — nothing is lost in translation to the shared vocabulary).

### Attributes & short-circuits

`attributes` collects asset signals: `is_proxy`, `is_vpn` (incl. NordVPN/ProtonVPN ranges), `is_tor`, `is_hosting`/cloud (AWS · Google · Azure · Oracle · Alibaba — one fused source, per-feed health), `is_cdn` (CloudFront/Cloudflare/Fastly edges), `is_anycast`, `carrier`, `service` (DNS/NTP/root-server identities). Private and reserved addresses (`10/8`, `127/8`, …) never hit the threat sources at all — they're short-circuited and marked `is_reserved: true`, so RFC1918 space can't come back "malicious" because some blocklist sloppy-ranged over it.

## 4. Exports

**CSV** — the `Export CSV` button above the table exports every row currently in results with the full evidence depth: 27 columns including fused verdict + confidence, per-type tags with malware families, aggregated `reporter_total` / `corroborated` / `verdict_conflict`, earliest `first_seen` / latest `last_seen` across sources, top source reliability, and the asset attribute set. Values that could execute as spreadsheet formulas are prefixed so hostile feed data stays text. Above 50,000 expanded rows the export happens automatically (table mode switches off — see [Querying](#2-querying)).

**STIX 2.1** — `GET /api/lookup/{ip}/stix` returns a STIX 2.1 bundle for the address: identities for every contributing source, indicators and observed-data with the same per-source evidence the API carries. The `stix2` library ships in the image, so this works out of the box — handy for feeding SIEMs that speak STIX natively. The UI's **Export STIX** button (above the results table) produces the same bundle from the current selection.

## 5. The admin console

Point your browser at `/admin` (a separate page from the public lookup). Unlock it by setting `IP_RADAR_ADMIN_EMAIL` (default `admin@ipradar.local`) and `IP_RADAR_ADMIN_PASSWORD` in the `environment` block of `docker-compose.yml` — the account is created on next start. The login is brute-force guarded (5 attempts/minute).

After sign-in you get three tabs (plus a floating task-progress pill that mirrors the Tasks tab — click it to jump there):

### Sources (default tab)

![The admin Sources tab: 61 sources, health, r/θ dual track, toggles](assets/manual/04-admin-sources.png)

Every source in one list, grouped into **Geo & ASN data / Threat intel / Asset attributes**, with columns:

- **Field** — what the source contributes (`is_malicious`, `city`, `is_tor`, `service`, …).
- **Covered IPs** — how much address space the loaded snapshot covers.
- **Updated** — wall-clock age of the last refresh, with content age and refresh cadence on hover (`26h · every 12h` — content age is the upstream data's internal timestamp, which is the honest one).
- **Status** — `fresh` / `stale` / `off`. `stale` means the refresh slot is due or overdue — watch it across many sources to spot a stuck scheduler or a dead feed.
- **Eval / r / θ** — the dual reliability track. **r** is the declared, production-authoritative weight (hand-set, changed only by human-reviewed PR). **θ** is the *measured* corroboration posterior from the eval layer — advisory, never auto-fed into fusion. A source whose θ sits far below its r is over-claiming; see [the lifecycle chapter](#6-source-lifecycle-add--evaluate--tune).
- **Actions** — the toggle enables/disables the source (disabled sources keep their data but stop refreshing and stop contributing); the **Update** button forces an immediate single-source refresh (its state is a live button label: `Queued`, `Downloading… 42%`, `Loading…`).
- **Refresh all** at the top enqueues a batch refresh of every enabled source — same thing `POST /api/update-db` does.

### API Keys

![Creating an API key: one-time token reveal](assets/manual/05-admin-keys.png)

Programmatic access needs a key (the same-origin web page doesn't). **Create key** asks for a name, an optional expiry in days, and a scope — the *All sources* switch, or a per-source allowlist via **Edit sources** on an existing key (use this to hand a script access to, say, only the geo sources). The token is shown **exactly once** — copy it then; afterwards the list only shows name/created/last-used/status and the **Revoke** (disable) / **Delete** actions. Last-used timestamps make dormant keys easy to spot and clean up.

Keys are JWTs signed with `IP_RADAR_API_JWT_SECRET`; send as `Authorization: Bearer <key>`. Rate limits differ per identity — see the [API reference](#7-api-reference).

### Tasks

![The Tasks tab: a live batch with per-source progress, failures, and controls](assets/manual/06-admin-tasks.png)

The task feed for all downloads/builds: each row is one source refresh with live state (`Queued → Downloading → Loading → Done/Failed`), byte/percent progress where the upstream reports it, and — the useful part — the **failure reason in plain text**: `OTX_API_KEY not set — register at … and add the key to .env` tells you exactly which knob is missing; `urlopen error … Connection reset by peer` is upstream flakiness and will retry on the backoff ladder. Each running task can be **canceled** (✕); a batch has **Pause / Abort / Collapse** controls at the top. This tab updates over SSE in real time — no refresh.

### The update banner (public page)

The public page's top banner includes a **Check for updates** button and, when a new release exists, a copy-paste upgrade command. If you enable the self-update mounts in `docker-compose.yml` (docker.sock + repo dir + `IP_RADAR_UPDATE_TOKEN`), an **Update now** button appears instead — the full mechanics and caveats live in [Operations](#9-operations).

## 6. Source lifecycle: add → evaluate → tune

The 61 shipped sources aren't a ceiling. The whole loop — grow the pool, measure whether a source actually helps, adjust or retire it — is designed to be run by the self-hoster, with a human deciding at every step that matters.

### Add

Four paths, in order of effort:

1. **Flip a toggle.** Sources you've disabled (or want to quiet) are one switch on the [Sources tab](#5-the-admin-console). No code, no restart.
2. **Light up a keyed source.** The seven keyed feeds activate by adding their API keys to `.env.local` and restarting — table with key names and signup links in the README [Quick Start](README.md#quick-start).
3. **Let an AI agent wire in a new source.** The repo ships three agent skills (`.pi/skills/`, loaded by agents that read project-level skills, e.g. [pi](https://github.com/earendil-works/pi)). One sentence each: *"Find me threat-intel sources worth adding"* (discover → scored shortlist), *"Add GreyNoise"* (implements one named source end-to-end), *"Check the health of all sources"* (manage/tune loop).
4. **Hand-write a source module.** A source is one Python file in `backend/ipdb/_sources/` implementing a small contract — map-first parsing into the lossless evidence record, a registry entry, tests. Reading one small existing module (e.g. [`backend/ipdb/_sources/bruteforce.py`](backend/ipdb/_sources/bruteforce.py) plus its test) is the whole onboarding; mirror the shape and the guards.

### Evaluate

Two consumers of evaluation, same numbers:

- **The admin console** shows each source's measured θ (90% CI) beside its declared r, and `/api/eval*` serves the report cards behind it (admin-only; see [API reference](#7-api-reference)).
- **The eval CLI**, run from `backend/` of your clone:

```bash
python -m ipdb._eval --model          # corroboration-contrast model over the fleet (= all other enabled sources) + acceptance suite
python -m ipdb._eval --all            # evaluate every source
python -m ipdb._eval --audit          # lineage audit over persisted model history (advisory)
python -m ipdb._eval --anchors        # known-answer regression gate; exit 1 on any failure
python -m ipdb._eval --dsem           # DS-EM fair fight: market vs declared vs π̂ (advisory; π̂ = truth-rate estimate from the eval harness)
python -m ipdb._eval --help           # full flag list (temporal, demand, readout, …)
```

The philosophy the flags encode: **measurements advise, humans decide.** θ is a corroboration posterior — it measures independent agreement, not correctness. Nothing measured ever flows into production weights automatically; adopting a measured value is a human-reviewed PR referencing the eval report. The `--anchors` gate is the one hard failure mode — it pins known answers so refactors can't silently drift the fusion.

### Tune

- **A source over-claims** (θ persistently below its r): lower the declared r in a PR referencing the eval report, or disable it from the Sources tab while you decide.
- **A source is redundant or harmful** (net-impact eval says removing it improves the fleet): disable, then delete the module if you're sure.
- **A source went quiet upstream**: the sunset detection story — feeds freeze, content age grows while wall-clock refreshes "succeed". The admission gate (`--gate`/sentinel machinery, maintainer-grade — see the module help) exists so a frozen feed can't be re-admitted by accident; the `Updated` column's content-age number is your user-level signal.

### Retire

Disabling keeps the data (re-enable is instant); deleting the module removes the source from the registry on next start. Either way, re-run `--anchors` and a `--model` pass after retiring anything that carried weight — the fleet's corroboration structure changed, and the gate is cheap.

## 7. API reference

The same-origin web page needs no key. Programmatic access needs an API key ([admin console → API Keys](#5-the-admin-console)) sent as `Authorization: Bearer <key>`. Errors come in one envelope, `{"error": {"code": "...", "message": "..."}}`, with machine codes (`unauthorized`, `bad_request`, `rate_limited`, `source_not_found`, `internal`, …); rate-limited responses add `retry_after` seconds. While warming, query endpoints answer `503` with header `X-IPRadar-Reason: warming`.

The interactive schema lives at `/docs` / `/redoc` / `/openapi.json`, disabled by default — set `IP_RADAR_ENABLE_DOCS=1` (restart) to enable; keep it off on public deployments.

### Rate limits

| Identity | Bucket | Limit |
|---|---|---|
| anonymous (per IP) | batch queries (`query/stream`, `upload/stream`) | 6 / minute |
| anonymous (per IP) | single lookups (`lookup/{ip}`, `…/stix`) | 30 / minute |
| API key (per key) | all query endpoints, one shared bucket | 60 / minute |
| anyone (per IP) | admin login attempts | 5 / minute |

Disable entirely with `IP_RADAR_RATELIMIT=0` (not recommended on anything reachable).

### Endpoints

| Method & path | What it does | Auth |
|---|---|---|
| `GET /api/lookup/{ip}` | Single lookup — full fused result | key |
| `GET /api/lookup/{ip}/stix` | Same, as a STIX 2.1 bundle | key |
| `POST /api/query/stream` | Batch lookup, NDJSON stream | key |
| `POST /api/upload/stream` | Batch lookup from uploaded file, NDJSON stream | key |
| `GET /api/db-status` | Record counts, staleness, warming flag | key |
| `GET /api/sources` | Source catalog + health | admin |
| `PATCH /api/sources/{name}` | Enable/disable a source (`{"enabled": false}`) | admin |
| `POST /api/sources/{name}/update` | Force single-source refresh → `task_id` | admin |
| `POST /api/update-db` | Enqueue batch refresh of all enabled sources | admin |
| `POST /api/update-db/pause` / `resume` / `cancel` | Batch lifecycle control | admin |
| `GET /api/tasks` | Task snapshot (states, progress, errors) | admin |
| `POST /api/tasks/{task_id}/cancel` | Cancel one task | admin |
| `GET /api/events` | SSE stream of task/batch events | admin |
| `GET /api/eval` · `/api/eval/model` · `/api/eval/{source}` | Eval overview / fleet model / per-source report | admin |
| `POST /api/eval/{source}/run` | Trigger an eval run (202 Accepted) | admin |
| `POST /api/admin/keys` · `GET` · `PATCH /{sub}` · `DELETE /{sub}` | API key CRUD | admin |
| `POST /api/auth/jwt/login` / `logout` | Admin session (HTTP-only cookie) | — |
| `GET/PATCH /api/users/me` | Admin account management (fastapi-users) | admin |
| `GET /api/version` | Current vs latest release, update flag | key |
| `POST /api/update` · `GET /api/update/status` | In-page self-update (opt-in mounts) | admin + token |

### Examples

Single lookup (response trimmed — the full shape is documented in [Reading results](#3-reading-results)):

```bash
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:8000/api/lookup/1.12.0.1
# → {"ip":"1.12.0.1","country":{"value":"CN","confidence":100,...},"city":{...},
#     "asn":{...},"as_name":{...},"threat":{"verdict":"benign","confidence":0,...},
#     "classifications":{...},"attributes":{...},"is_reserved":false}
```

Batch stream — NDJSON, one JSON object per line; `row` events carry full results in input order, `progress` events let you render live counts:

```bash
curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
     -d '{"ips":["1.12.0.1","45.148.10.238"]}' \
     -X POST http://127.0.0.1:8000/api/query/stream
# → {"type":"start","total":2}
#   {"type":"progress","done":0,"total":2}
#   {"type":"row","idx":0,"result":{...}}
#   {"type":"row","idx":1,"result":{...}}
#   {"type":"progress","done":2,"total":2}
#   {"type":"done","ok":2,"invalid":0}
```

Admin session — login sets an HTTP-only cookie (204, no body); keep a cookie jar:

```bash
curl -s -c jar.txt -X POST http://127.0.0.1:8000/api/auth/jwt/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     --data "username=admin@ipradar.local&password=<yours>"
curl -s -b jar.txt -X POST http://127.0.0.1:8000/api/sources/blocklist_de/update
# → {"task_id":"0d125a7b..."}
```

Task events over SSE — first event is always a full snapshot (safe reconnects), then one event per lifecycle change:

```bash
curl -s -b jar.txt -N http://127.0.0.1:8000/api/events
# → data: {"type":"snapshot","data":{"tasks":[...],"batch":{...}}}
#   data: {"type":"task","source":"bruteforce","state":"downloading","pct":42,...}
```

## 8. Troubleshooting

**Lookups answer 503 "database is warming up"** — normal during first build; the banner tracks progress. If it persists past the RAM-tiered window (15–30 min), check `docker logs` for a source stuck in retry loops, and check disk — a full volume stalls builds. `503 no-sources` means every source is disabled: re-enable on the Sources tab.

**Keyed sources keep failing** — the Tasks tab failure text names the missing env (`OTX_API_KEY not set…`). Keys go in `.env.local` (gitignored), then `docker compose up -d` to apply.

**A source shows `stale` for days** — look at its row's content age vs refresh period. Content age growing while refreshes "succeed" = the upstream froze (see [retire](#6-source-lifecycle-add--evaluate--tune)). Wall-clock age growing with failures = check the failure text; transient network errors retry on a backoff ladder (three consecutive real failures trip an alert if configured — [Operations](#9-operations)).

**Disk filling up** — every refresh builds a fresh epoch dir before flipping a pointer, so during big rebuilds both old and new copies exist. 6 GB is the floor; give it more if you enable everything including the big geo feeds on a busy box.

**Behind a reverse proxy, rate limits bite everyone at once** — the limiter sees the proxy's IP. Set `IP_RADAR_PROXY_HEADERS=1` (and `IP_RADAR_FORWARDED_ALLOW_IPS` to your proxy's range) so per-IP buckets see real clients.

**Admin page 404s or looks locked down** — on instances with `IP_RADAR_PUBLIC_DEMO=1`, the write/internal surface (including `/admin` login from non-bypass IPs) is hidden from anonymous visitors; maintainer bypass is `IP_RADAR_DEMO_ADMIN_IPS` — full semantics in [`deploy/README.md`](deploy/README.md). On normal self-hosts, make sure the admin env block is uncommented.

**Update banner claims an update that isn't there** — that's the deploy-side tag cache: on the server, `git fetch --tags` before build, else `git describe` falls back to an older baseline (v1.4.2 field note).

**Firefox/other client gets repeated 429s** — you're hitting the anonymous buckets from one IP; move to an API key (60/min shared) or spread batches.

## 9. Operations

### Upgrading

```bash
git pull && docker compose up -d --build
```

The `ipradar-data` volume stays put — no data migration on upgrades. The public page's banner tells you when a new release lands and shows the command ("Check for updates" refreshes the check).

**In-page self-update (optional)**: uncomment the self-update mounts in `docker-compose.yml` (docker.sock + repo dir + `IP_RADAR_UPDATE_TOKEN`), restart, and an "Update now" button appears on the banner. Three caveats worth their bullets:

- The repo-dir mount must be an **absolute host path** (`/home/you/ip-radar:/app/repo`) — a `./` relative path breaks the in-container compose replay.
- Mounting docker.sock grants the container host-level root control — this mode is for LAN self-hosting, not public boxes.
- Files written by in-container git pull are owned by root (host-side operations may need `sudo` / `git safe.directory`), and if you edit tracked files like `.env`, `git pull --ff-only` refuses by design — put local overrides in `.env.local`.

### Backup & restore

All state lives in one named volume (`ipradar-data` → `/app/data`): per-source raw downloads, LMDB epoch dirs with their `.ptr/.count/.cov/.disjoint` sidecars, and the SQLite pair `auth.db`/`alerts.db`. Rebuilds never write in place — a fresh epoch lands, then the pointer flips atomically.

**Stopped copy (simplest, always consistent):**

```bash
docker compose stop ipradar
docker run --rm -v ipradar-data:/data -v "$PWD:/backup" alpine \
     tar czf /backup/ipradar-data-$(date +%F).tgz -C /data .
docker compose start ipradar      # never `down -v` — that deletes the volume
```

**Hot copy (per source, if you can't stop):** copy the epoch dir first and the sidecars last, then re-check `.ptr` didn't flip mid-copy (if it did, redo that source). For the SQLite pair use `sqlite3 <db> ".backup /target"` — a mid-write `-journal` sibling makes naive copies torn.

**Restore:** copy the volume back, `docker compose up -d`, then verify the startup line `Loaded <count> <source> + …` matches `/api/db-status` from before the backup.

Only `auth.db`/`alerts.db` are irreplaceable (keys, alert history); a `_calibrated.json` calibration override, if you keep one, joins that set (hand-declared reliabilities are never regenerated). Every data file re-downloads from its public feed — worst case, a lost volume costs a cold start, not your setup.

### Source alerts (optional, silent by default)

The scheduler tracks every source's liveness but says nothing unless you wire a sink. Set `IP_RADAR_ALERT_URLS` (any `environment` block, or `.env.local`) to a comma-separated list of [apprise](https://github.com/caronc/apprise)-style URLs — `mailto:you@example.com`, a Discord/Telegram/Lark webhook — and you'll get one combined message when a source stops updating, keeps failing downloads, or its database fails to load (e.g. a corrupted epoch). Takes effect on restart. Per-source health stays visible under `/api/sources` regardless.

### Maintainer notes

Two traps when cutting a release: the release commit must include at least one non-markdown file change (CI's `paths-ignore` skips `**.md`-only pushes, so an md-only release commit never triggers the tag↔CHANGELOG↔GitHub Release consistency gate); and on the deploy server `git fetch --tags` before build, or the version endpoint falls back to an older baseline and the banner false-announces.

## 10. Around the project

- **[IP Radar Desktop](https://github.com/steponeerror/ip-radar-desktop)** — tray-resident companion app: one global hotkey looks up whatever IP is on your clipboard, every source's verdict side by side, whole lists in one shot. Installers for Linux/macOS/Windows on its Releases page.
- **Integrations** — each ships its own README: [fail2ban](scripts/fail2ban/README.md) (triage every ban against the local verdict first; CDN edges skip the ban, confirmed-malicious go long-ban), [Graylog](integrations/graylog/README.md) (lookup tables turning source IPs into country/ASN/fused verdict, no plugin), [Wazuh](integrations/wazuh/README.md) (enrich every IP-bearing alert into an ECS `threat.indicator` follow-up).
- **AI skills** — the three source-lifecycle skills live in `.pi/skills/` (`discover-intel-sources`, `add-intel-source`, `manage-intel-source`); see [the lifecycle chapter](#6-source-lifecycle-add--evaluate--tune) and the README table.
- **Eval report cards** — every source's θ history and report cards are served in the admin console (`/api/eval*`), no separate artifacts to keep.
- **Live demo** — [ipradar.huxiao0207.dpdns.org](https://ipradar.huxiao0207.dpdns.org), read-only mode (queries fully working).
