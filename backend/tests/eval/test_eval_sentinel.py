# backend/tests/eval/test_eval_sentinel.py
"""生效性哨兵测试 (Q18 物化流程 / S13 三通道口径)。

契约 (Phase 2 T2):
- sentinel_probe(source, lookup_fn, n=20, *, seed=None): 从候选源自身
  原始文件采样 n 个已知成员, 经 lookup_fn 回查引擎载荷
  (LookupResult.to_dict() 形状, 与 suite/ablation/layered 同约定)。
  - threat 通道: 成员须由本源自身以指控 verdict (∈_ACCUSING,
    malicious/suspicious) 作证 —— 他源抢答=回声不顶替;
    失败探针列明 (not-accused / accused-by-others[...] 两态区分)。
  - asset 通道: 成员须带本源 AssetStatement (payload.attributes
    [axis] 有 source==name, ≥1 声明轴即过, 同源多轴可只陈述子集)。
  - geo_asn: 显式 N/A 标记 (pass=None, 不冒充 False/True, 不查引擎;
    S13: geo_asn 标量轴=非目标)。
  - 采样确定性: 同 seed 同结果; 缺省 seed = stable_seed(source.name)。
- coverage_check(source, keyset): S13 键集型 —— 键集成员经引擎逐源读
  路径 source.query 非空的占比; 空键集 covered=None(空分母不冒充 0)。

全部 fake/stub, 零网络零 DB。
"""
from ipdb._eval.corpus import stable_seed
from ipdb._eval.sentinel import coverage_check, sentinel_probe


def _ips(prefix: str, k: int) -> list[str]:
    return [f"{prefix}{i}" for i in range(1, k + 1)]


def _hit(ctype: str, source: str, verdict: str = "malicious") -> dict:
    """本源/他源指控载荷: 组级与 details 逐源 verdict 均 ∈ _ACCUSING。"""
    return {
        "classifications": {
            ctype: {
                "type": ctype, "verdict": verdict, "detected": True,
                "details": [{"source": source, "verdict": verdict,
                             "reliability": 0.5}],
            }
        },
        "threat": {"verdict": verdict, "confidence": 80, "types": [ctype],
                   "is_cdn": False},
    }


def _miss() -> dict:
    return {"classifications": {},
            "threat": {"verdict": "benign", "confidence": 0, "types": [],
                       "is_cdn": False}}


def _lookup(results: dict):
    def fn(ip):
        return results.get(ip, _miss())
    return fn


class _FakeSource:
    """最小真实源接口: .name/.category/.fields/._path(采样走 corpus 正则
    提取同款)+ .query(coverage_check 逐源读路径替身)。"""

    def __init__(self, name, path, category="threat", fields=(),
                 answers=None):
        self.name = name
        self.category = category
        self.fields = tuple(fields)
        self._path = path
        self._answers = answers or {}

    def query(self, ip):
        return self._answers.get(ip)


def _make_source(tmp_path, name, ips, category="threat", fields=(),
                 answers=None):
    p = tmp_path / f"{name}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(ips) + "\n")
    return _FakeSource(name, p, category, fields, answers)


IPS25 = _ips("45.60.11.", 25)


# ── threat 通道 ────────────────────────────────────────────────


def test_threat_all_accusing_passes_20_of_20(tmp_path):
    src = _make_source(tmp_path, "cand", IPS25)     # 25 候选成员, 采 20
    lk = _lookup({ip: _hit("spam", "cand") for ip in IPS25})
    r = sentinel_probe(src, lk)
    assert r["pass"] is True
    assert r["status"] == "OK" and r["channel"] == "threat"
    assert len(r["probes"]) == 20                   # n=20 缺省, 采样封顶
    assert all(p["expected"] == "accusing" and p["actual"] == "accusing"
               for p in r["probes"])
    assert r["ok"] == 20
    assert r["seed"] == stable_seed("cand")         # 缺省 seed 名派生
    sampled = {p["ip"] for p in r["probes"]}
    assert sampled <= set(IPS25) and len(sampled) == 20   # 无放回去重


def test_threat_partial_failures_listed_individually(tmp_path):
    ips = _ips("45.60.12.", 20)                     # 恰 20, 全被探
    results = {ip: _hit("spam", "cand") for ip in ips}
    results["45.60.12.7"] = _miss()                 # 全静默
    results["45.60.12.11"] = _hit("spam", "firehol")  # 他源回声, 本源缺席
    src = _make_source(tmp_path, "cand", ips)
    r = sentinel_probe(src, _lookup(results))
    assert r["pass"] is False and r["status"] == "FAILED"
    failed = [p for p in r["probes"] if p["actual"] != "accusing"]
    assert {p["ip"] for p in failed} == {"45.60.12.7", "45.60.12.11"}
    by_ip = {p["ip"]: p for p in r["probes"]}
    assert by_ip["45.60.12.7"]["actual"] == "not-accused"
    assert by_ip["45.60.12.11"]["actual"] == "accused-by-others[firehol]"
    assert r["ok"] == 18


# ── asset 通道 ─────────────────────────────────────────────────


def _tor_stmt(source: str) -> dict:
    return {"classifications": {},
            "attributes": {"is_tor": [
                {"source": source, "value": True, "native_type": "RELAY"}]}}


def test_asset_channel_checks_own_statement(tmp_path):
    ips = _ips("45.60.13.", 5)
    src = _make_source(tmp_path, "danmeuk_tor", ips, category="asset",
                       fields=("is_tor",))
    r = sentinel_probe(src, _lookup({ip: _tor_stmt("danmeuk_tor")
                                     for ip in ips}))
    assert r["pass"] is True and r["channel"] == "asset"
    assert all(p["expected"] == "any[is_tor]@danmeuk_tor"
               and p["actual"] == "[is_tor]@danmeuk_tor"
               for p in r["probes"])

    # 他源同轴陈述不顶替: tor_exits 抢答 is_tor, 本源缺席 → 失败且列明
    r2 = sentinel_probe(src, _lookup({ip: _tor_stmt("tor_exits")
                                      for ip in ips}))
    assert r2["pass"] is False
    assert all(p["actual"] == "[]@danmeuk_tor" for p in r2["probes"])


def test_asset_multi_axis_subset_passes(tmp_path):
    # ip2proxy 形态 fields=(is_proxy,is_hosting): 成员只陈述其一即过(≥1 轴)
    ips = _ips("45.60.14.", 5)
    payload = {"classifications": {},
               "attributes": {"is_proxy": [
                   {"source": "ip2proxy", "value": True,
                    "native_type": "PUB"}]}}
    src = _make_source(tmp_path, "ip2proxy", ips, category="asset",
                       fields=("is_proxy", "is_hosting"))
    r = sentinel_probe(src, _lookup({ip: payload for ip in ips}))
    assert r["pass"] is True
    assert r["probes"][0]["expected"] == "any[is_hosting,is_proxy]@ip2proxy"
    assert r["probes"][0]["actual"] == "[is_proxy]@ip2proxy"


# ── geo_asn 通道 (S13 非目标) ──────────────────────────────────


def test_geo_asn_returns_na_marker_without_querying(tmp_path):
    src = _make_source(tmp_path, "iptoasn", IPS25[:3], category="geo_asn")

    def boom(ip):
        raise AssertionError("geo_asn 通道不得回查引擎 (S13 非目标)")

    r = sentinel_probe(src, boom)
    assert r["pass"] is None                 # 显式 N/A, 不冒充 False/True
    assert r["probes"] == [] and r["status"] == "N/A"
    assert "coverage_check" in r["reason"]   # 指路键集型判据


# ── fail-closed 边界 ───────────────────────────────────────────


def test_unknown_category_fails_closed(tmp_path):
    src = _make_source(tmp_path, "weird", IPS25[:3], category="other")
    r = sentinel_probe(src, _lookup({}))
    assert r["pass"] is False and r["status"] == "UNKNOWN-CATEGORY"
    assert r["probes"] == []


def test_no_members_fails_closed(tmp_path):
    src = _FakeSource("ghost", tmp_path / "missing.txt")  # 原始文件缺席
    r = sentinel_probe(src, _lookup({}))
    assert r["pass"] is False and r["probes"] == []
    assert r["status"] == "NO-MEMBERS"


# ── 采样确定性 (接口条款 2) ────────────────────────────────────


def test_sampling_determinism_same_seed_same_result(tmp_path):
    ips = _ips("45.60.15.", 40)              # 40 选 20
    src = _make_source(tmp_path, "cand", ips)
    lk = _lookup({ip: _hit("spam", "cand") for ip in ips})
    a = sentinel_probe(src, lk, seed=1234)
    b = sentinel_probe(src, lk, seed=1234)
    assert [p["ip"] for p in a["probes"]] == [p["ip"] for p in b["probes"]]
    # 缺省 seed(名派生)亦逐次可复算, 且 seed 落结果供报告复算
    d1, d2 = sentinel_probe(src, lk), sentinel_probe(src, lk)
    assert [p["ip"] for p in d1["probes"]] == [p["ip"] for p in d2["probes"]]
    assert d1["seed"] == stable_seed("cand")
    # 异 seed → 采样重排(40 选 20, 撞序概率可忽略)
    c = sentinel_probe(src, lk, seed=99)
    assert [p["ip"] for p in c["probes"]] != [p["ip"] for p in a["probes"]]


# ── coverage_check (S13 键集型) ────────────────────────────────


def test_coverage_check_fraction_and_dedup(tmp_path):
    ips = _ips("45.60.16.", 5)
    answers = {ip: {"is_tor": True} for ip in ips[:3]}   # 3 可回查
    src = _make_source(tmp_path, "danmeuk_tor", ips, category="asset",
                       fields=("is_tor",), answers=answers)
    r = coverage_check(src, ips + ips[:2])               # 带重复成员
    assert r == {"source": "danmeuk_tor", "n": 5, "hits": 3, "covered": 0.6}


def test_coverage_check_empty_keyset_is_none_not_zero(tmp_path):
    src = _make_source(tmp_path, "iptoasn", [], category="geo_asn")
    r = coverage_check(src, [])
    assert r["covered"] is None and r["n"] == 0    # 空分母不冒充 0
