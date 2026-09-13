# backend/tests/core/test_verify_watermark.py
"""Verifier tests (spec §5.4): detect() core + probe_data_dir round-trip."""
import random
from pathlib import Path

from ipdb._watermark import canary_family, mark_hit
from ipdb._sources.canary import CanarySource
from ipdb._sources._base import IpListSource
from scripts.verify_watermark import detect, probe_data_dir


class _FixedRng:
    def randrange(self, lo, hi):
        return 250
    def sample(self, pop, k):
        return list(pop)[:k]


def _obs(ip, source="sentinel", ctype="scanner", verdict="suspicious"):
    return [{"source": source, "classification_type": ctype,
             "verdict": verdict}]


def test_detect_confirmed_partial_none():
    fam = canary_family()
    full = {c.ip: _obs(c.ip, ctype=c.ctype) for c in fam}
    r = detect(lambda ip: full.get(ip) or [])
    assert r["hits"] == 500 and r["verdict"] == "CONFIRMED"
    half = {c.ip: _obs(c.ip, ctype=c.ctype) for c in fam[:150]}
    r = detect(lambda ip: half.get(ip) or [])
    assert r["hits"] == 150 and r["verdict"] == "CONFIRMED"   # threshold=100
    few = {c.ip: _obs(c.ip, ctype=c.ctype) for c in fam[:50]}
    r = detect(lambda ip: few.get(ip) or [])
    assert r["hits"] == 50 and r["verdict"] == "PARTIAL"
    assert detect(lambda ip: [])["verdict"] == "NOT_DETECTED"


def test_detect_rejects_wrong_triples():
    fam = canary_family()
    wrong_ctype = {c.ip: _obs(c.ip, ctype="tor") for c in fam}      # 类型不符
    wrong_src = {c.ip: _obs(c.ip, source="blocklist_de") for c in fam}
    mal = {c.ip: _obs(c.ip, ctype=c.ctype, verdict="malicious") for c in fam}
    assert detect(lambda ip: wrong_ctype[ip])["hits"] == 0
    assert detect(lambda ip: wrong_src[ip])["hits"] == 0
    assert detect(lambda ip: mal[ip])["hits"] == 0


def test_probe_data_dir_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(random, "SystemRandom", _FixedRng)
    CanarySource(tmp_path).rebuild()
    r = probe_data_dir(Path(tmp_path))
    assert r["layer1"]["hits"] == 250
    assert r["layer1"]["verdict"] == "CONFIRMED"
    assert r["layer2"]["invalid"] == 0            # 无假标记 → invalid 必 0


def test_detect_counts_transport_failures():
    """3a:query_fn 返回 None = 该 IP 探测失败(屏蔽/限流),计入 failed、
    不计入 probed;结论仅由 hits 决定(spec §8:如实报告 n/实际探到数)。"""
    fam = canary_family()
    bad = {fam[400].ip, fam[405].ip}      # 失败 IP 取在命中集外
    table = {c.ip: _obs(c.ip, ctype=c.ctype) for c in fam[:60]}

    def q(ip):
        if ip in bad:
            return None                 # transport-failed probe
        return table.get(ip) or []

    r = detect(q)
    assert r["failed"] == 2 and r["probed"] == len(fam) - 2
    assert r["total"] == len(fam) and r["hits"] == 60
    assert r["verdict"] == "PARTIAL"             # verdict 不因 failed 改变


def test_lookup_query_fn_parse_and_per_ip_failures(monkeypatch):
    """3a:_lookup_query_fn 单 IP 传输失败(URLError/非 503 HTTPError/非 JSON)
    → 该 IP 返回 None、不中断其余探测;正常路径扁化 classifications。"""
    import json as _json
    import urllib.error
    import urllib.request
    import scripts.verify_watermark as vw

    body = {"classifications": {"scanner": {"verdict": "suspicious",
                                            "details": [{"source": "sentinel"}]}}}

    class _Resp:
        def __init__(self, raw):
            self._raw = raw

        def read(self):
            return self._raw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=None):
        if url.endswith("/refused"):
            raise urllib.error.URLError("connection refused")
        if url.endswith("/forbidden"):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        if url.endswith("/junk"):
            return _Resp(b"<html>not json</html>")
        return _Resp(_json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    q = vw._lookup_query_fn("http://suspect")
    assert q("1.2.3.4") == [{"source": "sentinel",
                              "classification_type": "scanner",
                              "verdict": "suspicious"}]
    assert q("refused") is None
    assert q("forbidden") is None
    assert q("junk") is None


class _MarkedProbe(IpListSource):
    """层②探针源(复用 tests/core/test_watermark_layer2.py 的 _MarkProbe 模式)。"""
    name = "vprobe"
    category = "threat"
    filename = "vprobe.txt"
    url = ""
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.5


def _build_marked_probe(tmp_path):
    """自适应搜索必中/必不中样本各 2 条(γ∈(0,1) 两类必存在),步长 2
    保证不相邻;写数据文件并 rebuild+load。"""
    import ipaddress
    src = _MarkedProbe(tmp_path)
    base = int(ipaddress.ip_address("45.10.1.0"))
    hits, misses, i = [], [], 0
    while len(hits) < 2 or len(misses) < 2:
        n = base + 2 * i
        (hits if mark_hit(n, n) else misses).append(
            str(ipaddress.ip_address(n)))
        i += 1
    (tmp_path / "vprobe.txt").write_text("\n".join(hits + misses) + "\n")
    src.rebuild()
    src.load()
    return src, hits, misses


def test_probe_data_dir_layer2_confirmed(tmp_path):
    """3d:层②正向路径(此前零覆盖)——带真标记的探针源 → valid/invalid/
    scanned/expected 全量报告,valid>0 且 invalid==0 → CONFIRMED。"""
    src, hits, misses = _build_marked_probe(tmp_path)
    l2 = probe_data_dir(Path(tmp_path))["layer2"]
    assert l2["scanned"] == len(hits) + len(misses)      # 逐证据条目计数
    assert l2["valid"] == len(hits)                       # 每必中样本恰 1 枚自洽标记
    assert l2["invalid"] == 0
    assert l2["verdict"] == "CONFIRMED"


def test_probe_data_dir_layer2_invalid_is_suspicious(tmp_path, monkeypatch):
    """3c:存在不自洽 ingest_ref(伪造标记集)→ SUSPICIOUS,绝不能因
    valid==0 而误报 NOT_DETECTED。"""
    import scripts.verify_watermark as vw
    _build_marked_probe(tmp_path)
    monkeypatch.setattr(vw, "mark_value",
                        lambda s, e: "ir-forged")   # 全部标记读作不自洽
    l2 = probe_data_dir(Path(tmp_path))["layer2"]
    assert l2["valid"] == 0 and l2["invalid"] >= 1
    assert l2["verdict"] == "SUSPICIOUS"
