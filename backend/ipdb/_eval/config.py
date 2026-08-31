"""Tunable parameters for the source net-impact eval harness."""

# Verdict gate thresholds. Absolute defaults; verdict uses these, the report
# ALSO shows the portfolio percentile for advisory context.
THRESHOLDS = {
    "MC": 0.02,        # marginal coverage >= 2% of corpus (ip,type) pairs
    "CG": 5,           # >= 5 corroboration upgrades (1 -> >=2 indep sources)
    "conflict": 3,     # >= 3 conflict-introduced pairs
    "fp": 0.05,        # >= 5% benign-infrastructure hit rate
    "other": 0.50,     # >= 50% rows map to 'other' (reuses existing FLAG)
}

# Below this candidate-touched corpus size, withhold the verdict.
N_FLOOR = 20

# Two sources declared independent but with (ip,type) overlap above this are
# FLAGGED "probable shared upstream". Advisory, not auto-downgrade.
OC_SUSPICION = 0.70

# ── source-eval model (brief v3.1) ──────────────────────────────
# Hard-exclusion bar for the model's independence predicate. Over-exclusion is
# safe (source falls back to market prior); OC_SUSPICION above stays
# advisory-only flags and must NOT be reused as this bar.
OC_EXCLUSION = 0.30

# Static lineage clusters for the event layer (aligned with production
# DERIVED_SOURCES; per-sublist prose lineage folds in here as confirmed).
LINEAGE_CLUSTERS = {
    "firehol": "aggregated-threat",
    "ipsum":   "aggregated-threat",
    "otx":     "aggregated-threat",
    "greensnow": "aggregated-threat",  # OC=1.0 w/ firehol, containment ≥0.9 (2026-09-01)
    "drb_ra": "aggregated-threat",     # C2 aggregator (search-derived, mirrors trackers)
}

MODEL_W = 10        # G1' prior strength
MODEL_N_FLOOR = 10  # mover floor for suite checks

# Fountainhead heuristic (spec 2026-09-01 Part 2): a source is "suspected
# fountain" when >= FOUNTAIN_MIN_CONTAINEES other sources, each holding
# >= FOUNTAIN_MIN_PAIRS assertions, are >= FOUNTAIN_CONTAINMENT contained
# in it (directed). Presentation-only metadata — never alters theta or
# below_market, never auto-exempts (aggregator vs fountainhead is
# indistinguishable without temporal data).
FOUNTAIN_CONTAINMENT = 0.9
FOUNTAIN_MIN_PAIRS = 10
FOUNTAIN_MIN_CONTAINEES = 2

# PyMISPWarningLists provider substrings treated as benign infrastructure
# (FP-proxy). Matched case-insensitively against each WarningList's .name
# (a human description, e.g. "List of known Amazon AWS IP address ranges").
# search() only returns lists the IP actually hits, so non-IP lists never
# appear; this just narrows to cloud/CDN/DNS providers.
IP_WARNINGLISTS = [
    "amazon aws", "azure", "gcp", "cloudflare", "fastly", "akamai",
    "ipv4 public dns",
]

# Corpus sizing.
# Epoch 2026-09-01 (spec Part 5): per_type_n 30→60, corpus.json frozen.
# Any --rebuild from here on starts a NEW epoch — record old/new
# fingerprints in superpowers/runbooks/eval-model-monthly.md first.
CORPUS_PER_TYPE_N = 60     # malicious IPs sampled per classification_type
CORPUS_CANDIDATE_N = 100
