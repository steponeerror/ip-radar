# backend/test_eval_cli.py
from pathlib import Path
from ipdb._eval.__main__ import run_for_source

# 25 candidate IPs — clears the n-floor (N_FLOOR=20) so the verdict is
# POSITIVE-UNVERIFIED (dead-slot fill, CG=0), not INSUFFICIENT-SAMPLE.
_CAND_IPS = [f"203.0.113.{i}" for i in range(1, 26)]


class _FakeSource:
    """Stand-in source with REAL .name/.classification_type/._path.
    MagicMock's `name=` kwarg sets the repr, not the attribute, so a real
    class is required for `s.name == 'cand'` to match in run_for_source.
    query() returns [] so compute_other_distribution sees no classification.
    health() feeds the W4 NO-DATA 判据(rc = record_count)。"""
    def __init__(self, name, path, classification_type):
        self.name = name
        self._path = path
        self.classification_type = classification_type
        self._rc = 1000
    def query(self, ip):
        return []
    def health(self):
        from types import SimpleNamespace
        return SimpleNamespace(record_count=self._rc, is_stale=False)


class _FakeBenign:
    """Hermetic benign checker: no IPs hit infrastructure (FP=0)."""
    def overall_hit_pct(self, ips): return 0.0
    def hit_pct(self, ips): return {}


class _FakeRegistry:
    """Minimal registry double. Candidate 'cand' fills phishing on _CAND_IPS."""
    def __init__(self):
        self.disabled = set()
        self.sources = [_FakeSource("cand", Path("/nonexistent"), "phishing")]
    def lookup(self, ip):
        if "cand" in self.disabled or ip not in set(_CAND_IPS):
            return {"ip": ip, "classifications": {}}
        return {"ip": ip, "classifications": {"phishing": {
            "type": "phishing", "verdict_conflict": False, "confidence": 50,
            "sources": [{"source": "cand"}]}}}
    def toggle(self, name, enabled):
        self.disabled = (self.disabled - {name}) if enabled else (self.disabled | {name})

def test_run_for_source_produces_verdict_and_report(tmp_path):
    reg = _FakeRegistry()
    reg.sources[0]._path = tmp_path / "cand.txt"
    reg.sources[0]._path.write_text("\n".join(_CAND_IPS) + "\n")
    md, js, verdict = run_for_source("cand", registry=reg, corpus_path=tmp_path / "c.json",
                                     out_dir=tmp_path, benign=_FakeBenign())
    assert verdict.state == "POSITIVE-UNVERIFIED"   # dead-slot fill, CG=0, n>=floor
    assert md.exists() and js.exists()
    # candidate is left enabled (no on-disk state mutation leak)
    assert "cand" not in reg.disabled


def test_run_for_source_dead_source_nodata(tmp_path):
    # W4:rc(record_count)=0 → run_for_source 必须把 health 接进 assess,
    # 死源端到端拿到 NO-DATA/empty(out_dir 无 model/ 历史 → 只判 empty)
    reg = _FakeRegistry()
    reg.sources[0]._rc = 0
    _, _, verdict = run_for_source("cand", registry=reg, corpus_path=tmp_path / "c.json",
                                   out_dir=tmp_path, benign=_FakeBenign())
    assert verdict.state == "NO-DATA"
    assert verdict.reason == "empty"


def test_real_registry_toggle_visible_to_enabled_sources(monkeypatch):
    """消融 CLI 的 _real_registry().toggle 必须「重赋值」_disabled:registry
    身份键控缓存(_enabled_cache/_org_hooks_cache,Task 4)按对象身份失效,
    原地 .add/.discard 令 baseline/candidate 恒同、消融指标静默全零
    (终审 Critical-1)。断言可见性:toggle 后 _enabled_sources() 立即反映。"""
    import ipdb._registry as reg
    from ipdb._eval.__main__ import _real_registry

    # 任取当前启用的真实源;monkeypatch 充当快照,终结时恢复原 _disabled 对象
    name = next(s.name for s in reg._sources if s.name not in reg._disabled)
    monkeypatch.setattr(reg, "_disabled", reg._disabled)

    before = [s.name for s in reg._enabled_sources()]   # 预热身份缓存(命中态)
    assert name in before
    _real_registry().toggle(name, False)
    assert name not in [s.name for s in reg._enabled_sources()]   # 立即可见
    _real_registry().toggle(name, True)
    assert name in [s.name for s in reg._enabled_sources()]       # 往返恢复
