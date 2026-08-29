from ipdb._merge import _assess_classification
from ipdb._types import EvidenceObservation


def _obs(verdict, reliability=0.8):
    return EvidenceObservation(
        source=f"src_{verdict}", classification_type="scanner",
        verdict=verdict, reliability=reliability,
    )


def test_conflict_picks_malicious_deterministically():
    group = [_obs("malicious"), _obs("benign")]
    a = _assess_classification(group)
    assert a.verdict == "malicious"
    assert a.verdict_conflict is True


def test_no_conflict_flag_when_uniform():
    a = _assess_classification([_obs("malicious"), _obs("malicious")])
    assert a.verdict == "malicious"
    assert a.verdict_conflict is False


def test_precedence_order():
    # malicious > suspicious > benign > informational
    assert _assess_classification([_obs("suspicious"), _obs("benign")]).verdict == "suspicious"
    assert _assess_classification([_obs("benign"), _obs("informational")]).verdict == "benign"


def test_single_observation_no_conflict():
    a = _assess_classification([_obs("malicious")])
    assert a.verdict == "malicious"
    assert a.verdict_conflict is False


def test_all_unknown_verdicts_deterministic():
    # Unknown verdicts: result is alphabetical (deterministic), not set-order dependent.
    a = _assess_classification([_obs("zzz_unknown"), _obs("aaa_unknown")])
    assert a.verdict == "aaa_unknown"
    assert a.verdict_conflict is True


def test_stale_observation_decays_only_itself():
    # Regression: decay is per-source on each observation's own first_seen.
    # An ancient obs decays to ~0; an obs with no first_seen keeps its full
    # coefficient. Σ ≈ logit(0.8) = 1.386 → P = 0.800 → 80. If decay were
    # wrongly shared across the group (e.g. anchored on the oldest), the
    # fresh coeff would also collapse and conf would fall toward 50.
    old = EvidenceObservation(
        source="src_old", classification_type="c2-server", verdict="malicious",
        reliability=0.8, first_seen="2010-01-01T00:00:00")    # 16y old -> coeff ~ 0
    fresh = EvidenceObservation(
        source="src_fresh", classification_type="c2-server", verdict="malicious",
        reliability=0.8)                                      # no first_seen -> full coeff
    a = _assess_classification([old, fresh])
    assert a.confidence == 80

