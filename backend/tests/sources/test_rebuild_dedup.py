"""③ O(n²) bucket dedup → sidecar set. Semantic equivalence is locked by the
existing dedup tests (test_csvsource_dedup_noloss / test_csvsource_accumulation);
these tests pin (a) semantics stay identical incl. dict-key order, and (b) the
sidecar-set path itself. Spec 2026-08-26 §2."""
import json

from ipdb._source_base import Source
from ipdb._evidence import Evidence


def test_source_rebuild_dedup_semantics_unchanged(tmp_path):
    """Full-evidence equality dedup: identical duplicates collapse, any field
    difference keeps both — exactly the dict-equality contract."""
    class S(Source):
        name = "dedup_t"
        filename = "dedup_t.csv"
        fields = ("spam",)
        stale_days = 1

        def harvest(self):
            rows = [
                ("1.2.3.4/32", Evidence(classification_type="spam",
                                        verdict="informational",
                                        reporter_count=10)),
                ("1.2.3.4/32", Evidence(classification_type="spam",
                                        verdict="informational",
                                        reporter_count=10)),   # exact dup
                ("1.2.3.4/32", Evidence(classification_type="spam",
                                        verdict="informational",
                                        reporter_count=11)),   # reporter differs
                ("1.2.3.4/32", Evidence(classification_type="scanner")),  # type differs
            ]
            yield from rows

    s = S(tmp_path)
    tmp_path.joinpath("dedup_t.csv").write_text("x\n")
    s.rebuild()
    # query returns the per-CIDR evidence LIST; 3 distinct evidences survive
    # (exact dup collapses; reporter_count / classification_type differ → keep).
    rec = s.query("1.2.3.4")
    assert isinstance(rec, list) and len(rec) == 3, f"expected 3 distinct evidences, got {rec!r}"


def test_json_key_equivalence():
    """The sidecar key json.dumps(d, sort_keys=True) is equality-equivalent
    to dict == for evidence dicts (scalar / scalar-list values, no NaN)."""
    a = {"classification_type": "spam", "reporter_count": 10,
         "tags": ["x", "y"], "extra": {"k": [1, 2]}}
    b = {"tags": ["x", "y"], "reporter_count": 10,
         "extra": {"k": [1, 2]}, "classification_type": "spam"}   # same, shuffled
    c = {"classification_type": "spam", "reporter_count": 11,
         "tags": ["x", "y"], "extra": {"k": [1, 2]}}
    ka = json.dumps(a, sort_keys=True)
    assert ka == json.dumps(b, sort_keys=True), "equal dicts must share a key"
    assert ka != json.dumps(c, sort_keys=True), "unequal dicts must differ"
