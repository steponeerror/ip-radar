---
name: discover-intel-sources
description: Use when the user wants to **discover, shortlist, compare, or evaluate candidate intelligence sources/feeds — WITHOUT a commitment to add any right now** — e.g. "what feeds are out there for X", "find me more candidates", "research candidate intel sources", "what's worth adding to the shortlist", "compare/evaluate these feeds", "rank X vs Y". Produces a scored shortlist only; does NOT implement anything. NOT for implementing a specific already-chosen source (use add-intel-source), nor for "find AND wire up new sources" / optimizing the pool / the full lifecycle (use manage-intel-source).
---

# Discovering & Qualifying Intelligence Sources for ip-lookup-tool

This skill turns "what sources should I add?" into a **scored, gap-first shortlist**
where every candidate is documented in the same shape and the top pick drops
straight into `add-intel-source` Phase 1. It is the discovery/qualification
companion to **add-intel-source** (which does the implementation):

- **discover-intel-sources** = *which* source(s), and why (this skill)
- **add-intel-source** = *how* to plug a chosen source in

Read these once before scoring — they define the contract every dossier must satisfy:
- `.pi/skills/add-intel-source/SKILL.md` — the Phase-1 input table this skill's dossier mirrors.
- `backend/ipdb/_registry.py` 源 `category` attr(registry 聚合为 `SOURCE_CATEGORIES`)— the coverage axes.
- `backend/ipdb/_classification.py` — the controlled vocabulary + per-source `_MAP`s.

## Core principle

Two rules, and everything else follows:

1. **Census-first across the whole information landscape, not feed-first and
   not schema-first.** Walk the IP information taxonomy (Step 1) — *what can
   be known about an IP* — then check each category against the pool and the
   local-bulk availability. Starting from *what feeds exist* misses feeds you
   never thought to search for; starting from *the current schema's holes*
   can never propose a new information dimension (the DNS resolver batch,
   2026-10-10: a real need the old gap-first method was structurally unable to
   surface). The answer surface spans classification types (threat intel),
   scalar slots (geo/ASN/range/city), asset slots (proxy/vpn/hosting/tor/
   mobile/carrier/service) — plus askable-but-absent info (rDNS hostname,
   abuse contact, cloud-provider range labels), which MUST land in
   `NEEDS.md` rather than staying anecdotal.
   The tool's product is a comprehensive IP profile; threat intel is one
   axis, and in practice the most saturated one (2026-09-01: 22 of 37
   sources feed `is_malicious` while `city`/`carrier`/`is_isp` sit at one
   witness each). A source that gives a 1-witness field its second vote, or
   opens a missing field, beats one that reinforces a saturated axis, even
   if the latter is bigger.
2. **Every candidate gets the same dossier.** A shortlist you can't compare
   side-by-side is a list of essays, not a decision. One template, filled
   identically, scored on a fixed rubric.

## The workflow

1. **Census first, then map the gap.** The compass is the **IP information
taxonomy** (census-first, 2026-10-10 grill ruling #9 — gap-first inside the
existing schema could never have proposed the DNS resolver batch; that need
came from the landscape). Walk the taxonomy category by category and ask per
category: which sources in the pool can answer it, and is a local bulk source
available? The census proposes; the gates dispose. Taxonomy (extensible — a
census run may add categories, dated; mirror of the `CLASSIFICATION_TYPES`
Extensible discipline):
   1. 网络定位 — country / city / lat-lon / timezone / accuracy
   2. 路由与分配 — ASN / AS name / prefix / RIR registry / alloc date & status / BGP
   3. 所有权与联系 — org / registrant / abuse contact / rDNS
   4. 基础设施角色 — cloud / CDN / hosting / DNS(root·resolver·TLD) / IX / NTP / anycast
   5. 隐私与中继 — proxy / VPN / Tor / residential relay
   6. 移动与接入 — carrier / ISP type / mobile / CGNAT
   7. 通信暴露面 — open ports / services / banners / TLS / OS
   8. 声誉与恶意 — blocklist / abuse / scanner / brute / spam / C2 / drone / phishing / malware / DDoS / exploit
   9. 时间动态 — first/last seen / activity timeline
   10. 组织与商业 — org names / ASN business type / brand

   Then **prioritize the census with four inputs** — the gap statement must cite
demand evidence (a NEEDS row or a probe column), never schema alone:
   - **`NEEDS.md`** (repo root): the living demand ledger — read every open /
     候选 row first; any "想问而无槽/答不出" lands there (census output seeds
     it; 2026-10-10 first seed = ip-info census, docs/research archive).
   - **`cd backend && python -m ipdb._eval --demand`**: per-field answer-rate
     over two cohorts (fleet corpus + random routable v4) — the measured form
     of "what we cannot answer" (e.g. service ≈2%/≈0% pre-DNS batch).
   - **eval verdicts** (`--overview`): fleet POSITIVE/NEGATIVE/MARGINAL report.
   - **The schema map** — roster dump first: `cd backend && python -m ipdb._registry
     --roster` (one line per source: `name | category | download_host | fields |
     sublists`). **The roster dump is part of the report** — counting categories
     without naming sources is how the dataplane incident happened (2026-09-05:
     DataPlane.org was "discovered" as new despite `dataplane` being registered
     since v1.0.0; its telnetlogin/dnsrd signals were already in the pool).
     Ad-hoc inventory scripts are forbidden — they choose what to print, and the
     choice is where the blind spot lives. Then read `SOURCE_CATEGORIES`(由源文件
     `category` attr 派生); count sources per axis (`threat` / `geo_asn` / `asset`).
     Then count **witnesses per answer field** — scalar/asset slots: union of each
     source's `fields` attr (a x1 field is a single point of failure; sanctioned
     example: `city` has awaited its second voting source since 2026-08-15).
     Classification slots: **map reachability**, not `fields`/`classification_type`
     grep — per-row emission goes through the `*_MAP`s in `_classification.py`
     (witnesses = each map's `set(values())` ∪ single-type class-attr sources).
     2026-10-10 incident: the fields-attr grep claimed 5 dead slots & phishing=x1;
     truth was 2 dead (vulnerable-system, misconfiguration) and phishing
     4-map-reachable. Reachable ≠ dense (phishing: 4 maps yet 0/300 live-sample
     hits) — back any "thin axis" claim with a live-probe sample. Then read
     `CLASSIFICATION_TYPES` and find **dead slots** — vocab terms no source
     actually emits.

   Census × four inputs in hand, state the gap in one sentence before
   looking at any feed: which taxonomy rows have no/weak witnesses, which of
   those have a local bulk path, and what demand evidence backs each.
2. **Search hard for candidates (maximize discovery).** Use `agent-reach`
   (Exa search + GitHub) and cast a **wide, multi-angle** net — a single query
   always misses something. Sweep these angles:
   - **By attack type:** `"<threat-type> IP blocklist"` — scanner / botnet / phishing / ddos / proxy…
   - **By format:** `"IP CIDR netset"`, `"IP blocklist txt"`, `"IP feed csv"`
   - **By community/feed catalogs:** `Bert-JanP/Open-Source-Threat-Intel-Feeds`,
     kraloveckey's collection, `firehol/blocklist-ipsets` (browse its ipsets for
     sublists NOT already aggregated by this tool's `firehol` source), abuse.ch
     feeds, AlienVault OTX pulses
   - **By code:** `gh search code "<threat-type>" extension:txt` / `extension:netset` —
     finds raw lists buried in repos that catalog/search misses
   - **By the gap, not the feed:** a dead slot is the *highest-value* search target —
     search it the *hardest*, do not skip it on the assumption it's "probably empty."

   **gap-first = priority, not permission to skip.** A dead slot that looks empty
   is a signal to search *harder* (its value is highest precisely because nothing
   fills it), never to give up after one query. Cast wide; you'll cut later.

   **Before recording a slot as "no native-IP feed found":** have you swept every
   angle above + checked every catalog + tried `gh search code`? "Not found *this
   run*" is a *finding* (write it to the report, dated) — **never** a permanent
   claim baked back into this skill, which would suppress future discovery effort.
3. **Verify each candidate against reality — never trust marketing.** `curl` the
   URL, fetch a real sample (3–5 lines verbatim), check the actual byte/record
   count. A feed advertised as "thousands of IOCs" that ships 37 rows changes
   everything. This single step catches most mirages.
4. **Score on the rubric + run the hard gates** (both below). The gates decide
   pass/fail; the rubric ranks the survivors.
5. **Write one dossier per surviving candidate** (template below), then rank by
   **total rubric score, descending** — not by prose. Hand the top pick to
   `add-intel-source`.

## The rubric (score every candidate 1–5 on each dimension)

These six dimensions are the field's standard TI-feed quality metrics
(Pearce et al., USENIX Security 2019: Volume, Uniqueness, Latency, Accuracy,
Coverage) mapped onto this tool's contract. Score them, don't narrate them.

| Dimension | What 5 looks like | What 1 looks like | Maps to |
|---|---|---|---|
| **Coverage value** | opens a dead slot / thin axis | near-100% overlap with an existing source | classification axis gap |
| **Integration cost** | a simple base class (~10 lines) | a full `Source` subclass | archetype |
| **Access / license** | free, no auth, bulk download | per-IP / per-query billing | `__init__` + `.env` |
| **Freshness** | updates daily, actively maintained | stale, no update signal | `stale_days` |
| **Data quality** | human-curated, high-confidence | auto-inferred / "unverified" | `reliability` |
| **Class. cleanliness** | native vocab maps cleanly to controlled vocab | most rows would bloat to `other` | `_MAP` / `_classification` |

**Total = sum of the six (6–30).** Rank survivors by total. The rubric is the
*ranking* mechanism — if your final order isn't the rubric order, say explicitly
why (e.g. "cost tied, #2 wins on uniqueness").

**Reading `other`% on the cleanliness axis:** crowd-sourced / hashtag feeds
(TweetFeed, community IOC lists) naturally run 20–40% `other` — empty tags,
niche malware families, arch/file tokens. That alone is **not** a reject signal;
the corroboration axis still benefits from the rows that *do* map. To keep
`other` low when the feed has a defining role, map a **base classification**
(URLhaus: every row serves malware → unmappable tags fall to
`malware-distribution`, not `other` → `other`% ≈ 0). See
`add-intel-source/references/classification.md` § "Multi-value category columns".

## Hard gates (kill criteria — apply before scoring saves time)

Run these first. A candidate hitting any gate is out (or flagged), regardless of
rubric score. Each gate exists because a real candidate was rejected for it. Feed
names in the table are illustrative — **verify the candidate's current
pricing/model/terms before applying a gate**, since access tiers and licenses drift.

| Gate | Outcome | Why |
|---|---|---|
| **Per-IP / per-query billing** (Shodan, Censys single-IP APIs) | REJECT | cost black hole for a batch-lookup tool |
| **Structural model mismatch** — reports scoped to *your own* ASN/CIDR (Shadowserver), not global | REJECT | doesn't serve arbitrary-IP lookup |
| **Feed marked "unverified" / "community"** and you'd consume it on the corroboration axis | REJECT | pollutes fusion; keep only verified for the axis |
| **Unverifiable provenance** — anonymous push-only data dump: no upstream attribution AND no in-repo derivation code (SentinelPhishFeed, 2026-10-10: 2★ anonymous repo, zero code, 203k IPs, "without per-source attribution") | REJECT | rubric cannot price provenance opacity — it scored quality 2 yet 26/30 still topped the shortlist. The gate's intent is auditability; a feed need not be *labeled* unverified to fail it. User-rejected same day. Scope: targets **anonymous aggregation** — a community-maintained PRIMARY list with per-entry attribution and a known maintaining org passes (dns_public: DNSCrypt stamps, per-resolver names like "a-and-a"; root_servers: IANA; both 2026-10-10). Asset/service sources are judged on provenance verifiability, not on threat-corroboration standards |
| **Publisher already integrated** — candidate and a roster row are published by the **same party** (repo owner/organization/project — NOT a bare `download_host` match: `raw.githubusercontent.com` is shared by 12 roster rows, and host-matching would have falsely rejected `dns_public`, 2026-10-10) (or a signal name matches its sublists column) | REJECT as *new source* | dataplane precedent: the publisher was registered since v1.0.0 yet was researched as a discovery. A same-publisher unconsumed signal is still viable — but must be framed as **extension of the existing source** (edit its `SIGNALS`/map), not a new source |
| **~100% overlap with an existing source** (verify: is it already aggregated into `firehol`/`ipsum`/`spamhaus`?) | REJECT | redundant |
| **Sunset/frozen feed** — data-internal timestamp (`Last updated`/`Generated`/`As-of`) older than 30 days at sample-fetch; OR (no internal timestamp) publisher shows no GitHub commit / changelog / release within 30 days AND no content change across ≥2 fetches on different days | REJECT | re-serves a stale file though the URL responds; `file-mtime` is NOT liveness evidence (frozen re-download bumps it — this is how the sunset `feodo` feed slipped in) |
| **Domain/URL-only feed** needing URL→IP resolution at fetch time (PhishTank, OpenPhish free) | FLAG | fragile, expires; prefer native-IP feeds |
| **Ambiguous commercial-use license** ("not for commercial resale") | FLAG | needs explicit user sign-off before integrating |

`REJECT` = dropped with a one-line reason; **no dossier, no rubric score** (it's
gate-killed — scoring it wastes work). `FLAG` = **kept in the shortlist with a
full dossier and rubric score**, ranked alongside PASS candidates; the
gate-verdict slot names the blocker and marks it "needs user decision." Only
REJECT leaves the ranking — PASS and FLAG are both survivors you score and sort.

## The dossier (one per candidate — fill every slot, identically)

This template IS the output. It is also `add-intel-source` Phase 1's input
table, so a filled dossier hands off with zero rework.

```
### <candidate name>
- URL:            <curl-verified, with the exact file fetched>
- Sample:         <3–5 lines verbatim, real fetch>
- Publisher:      <who maintains it, since when, reputation>
- Coverage target:<which classification axis/slot — "opens spam (dead slot)" | "reinforces c2-server">
- Archetype:      <simple base (see `add-intel-source` live discovery) | Source subclass>  + template source to copy
- Format:         <plain IP list | CSV cols | JSON | ZIP/gzip-wrapped>
- Auth:           <none | API key (env var name) | licensed>
- Cadence:        <hourly|daily|weekly>  →  stale_days = <N>
- Data freshness verified: <internal timestamp, e.g. "Last updated 2026-08-01"> | <"no internal ts — publisher liveness: <evidence URL> checked on YYYY-MM-DD, content changed across fetches on D1/D2">
- Fields:         <what a row carries; per-field routing: X→Evidence.Y, ...>
- Reliability:    <0–1, with reason>
- License/quota:  <terms + any rate limit>
- Rubric score:   coverage __ / cost __ / access __ / freshness __ / quality __ / cleanliness __ = __/30
- Gate verdict:   PASS | FLAG(<blocker>) | REJECT(<reason>)
- Notes:          <overlap check vs existing sources; the one trade-off the user should know>
```

Leave no slot blank. "Unknown" is an acceptable value only for `Fields`/`Cadence`
*until you fetch the sample* — the sample resolves them, so by dossier time they
are filled. A dossier with missing slots is incomplete; go back and fetch.

The `Data freshness verified` slot is mandatory: a candidate whose data is stale beyond the sunset hard-gate is REJECTed before dossier time, so a surviving dossier always has fresh data. `file-mtime` / "the URL responds" are not acceptable freshness evidence.

## Common mistakes

- **Feed-first instead of gap-first.** Don't start with "GreyNoise looks cool."
  Start with "the `scanner` axis has one real source." The gap determines which
  feeds are even worth evaluating.
- **Unattributed overlap numbers.** An overlap probe that reports "73% of sampled IPs already flagged" without naming **which sources** flagged them is not verification — in the dataplane incident the covering source WAS dataplane itself, visible in one lookup's attribution list. Overlap probes must print covering source names.
- **Declaring a dead slot empty after one query.** A single search angle misses
  most feeds — in this campaign, one run concluded "phishing has no native-IP
  feed"; a wider sweep next run found TweetFeed. Sweep every angle (attack-type
  / format / catalogs / `gh search code`) before recording "no native-IP feed
  found *this run*", and never bake that claim back in as permanent.
- **Trusting the landing page.** The number of rows a feed *claims* vs *ships*
  diverges constantly. Always `curl` a sample. ThreatCluster claims "thousands,"
  ships 37.
- **Narrating instead of scoring.** "Good coverage, easy to integrate" is not a
  score. Put the number in the rubric row; the ranking must be reproducible from
  the scores alone.
- **Different shape per candidate.** If two dossiers have different field sets,
  the comparison is rigged. One template, every slot, every candidate.
- **Reinventing the integration.** The dossier's archetype/format/auth/cadence/
  fields slots exist so you can hand off to `add-intel-source`. Don't start
  writing the source here — discover stops at the ranked shortlist + top-pick dossier.
- **Fake-zero overlap probes.** An overlap probe must first pass a known-positive
  control (look up one IP already in the fleet, confirm it returns flagged) and
  must never swallow exceptions silently — 2026-10-10: `except Exception:
  continue` ate `Database not loaded` and the probe reported 0/300 "unique"
  before the self-check caught it.
- **Polishing the lone survivor.** When the gates kill everyone but one
  marginal candidate, the finding IS the stop signal (硬凑数量 = 加噪音) —
  report "nothing worth adding this run" and stop. A dressed-up top pick from
  a thin pool is salesmanship, not discovery (SentinelPhishFeed, 2026-10-10,
  user-rejected).

## Handoff

For the top-ranked surviving candidate, the completed dossier is ready for
implementation — invoke **add-intel-source** with it. That skill picks up at
Phase 1 (the same fields, now filled) and walks through archetype → parse hook →
in-file metadata declaration (category / reliability / authoritative_for) → test.
