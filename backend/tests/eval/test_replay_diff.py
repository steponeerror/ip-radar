# backend/tests/eval/test_replay_diff.py — replay_diff 快照脚本纯函数测试
import pytest

from ipdb._eval.replay_diff import main, sample_ips, snapshot_entry


class _FakeSource:
    def __init__(self, name, classification_type=None):
        self.name = name
        self.classification_type = classification_type


class _FakeRegistry:
    def __init__(self, sources):
        self.sources = sources


# ── snapshot_entry:每 IP 的可比视图 ──

def test_snapshot_entry_scalars_picks_confidence():
    r = {"country": {"value": "HK", "confidence": 93},
         "asn": {"value": 4760, "confidence": 70},
         "as_name": {"value": "HKT", "confidence": 50},
         "city": {"value": "X", "confidence": 10}}          # city 不入视图
    e = snapshot_entry(r)
    assert e["scalars"] == {"country": 93, "asn": 70, "as_name": 50}


def test_snapshot_entry_classifications_counts_distinct_sources():
    r = {"classifications": {"c2-server": {
        "verdict": "malicious", "confidence": 88,
        "details": [
            {"source": "a", "first_seen": "2026-01-02T00:00:00+00:00"},
            {"source": "a", "first_seen": "2026-03-04T00:00:00+00:00"},  # 同源去重
            {"source": "b", "first_seen": "2026-02-01T00:00:00+00:00"},
            {"source": "c"},                                     # 无 first_seen
        ]}}}
    e = snapshot_entry(r)
    c = e["classifications"]["c2-server"]
    assert c["conf"] == 88
    assert c["verdict"] == "malicious"
    assert c["n_sources"] == 3                                   # {a, b, c}
    assert c["min_first_seen"] == "2026-01-02T00:00:00+00:00"
    assert c["max_first_seen"] == "2026-03-04T00:00:00+00:00"


def test_snapshot_entry_no_first_seen_gives_none():
    r = {"classifications": {"spam": {
        "verdict": "suspicious", "confidence": 40,
        "details": [{"source": "x"}, {"source": "y"}]}}}
    c = snapshot_entry(r)["classifications"]["spam"]
    assert c["min_first_seen"] is None
    assert c["n_sources"] == 2


def test_snapshot_entry_empty_classifications():
    e = snapshot_entry({})
    assert e == {"scalars": {}, "classifications": {}}


# ── sample_ips:corpus 全量 + 分类源 5 抽样,稳定去重 ──

def test_sample_ips_skips_non_classification_sources(monkeypatch, tmp_path):
    raw = tmp_path / "feed.txt"
    raw.write_text("10.0.0.1\n10.0.0.2\n10.0.0.3\n10.0.0.4\n10.0.0.5\n10.0.0.6\n")
    with_cls = _FakeSource("cls", classification_type="blacklist")
    with_cls._path = raw
    (tmp_path / "corpus.json").write_text(
        '{"benchmark": {}, "benign": ["8.8.8.8"], "reserved": [], "candidate_ips": []}')
    monkeypatch.setattr("ipdb._eval.replay_diff.CORPUS_PATH", tmp_path / "corpus.json")
    plain = _FakeSource("plain")            # 无 classification_type → 不抽样
    ips = sample_ips(_FakeRegistry([with_cls, plain]))
    assert ips[0] == "8.8.8.8"              # corpus 全量在前
    assert len(ips) == 6                    # 1 corpus + 5 源抽样
    assert set(ips[1:]) <= {f"10.0.0.{i}" for i in range(1, 7)}
    assert len(set(ips)) == len(ips)        # 去重


def test_sample_ips_dedups_corpus_and_samples(monkeypatch, tmp_path):
    raw = tmp_path / "feed.txt"
    raw.write_text("8.8.8.8\n10.0.0.1\n")
    with_cls = _FakeSource("cls", classification_type="blacklist")
    with_cls._path = raw
    (tmp_path / "corpus.json").write_text(
        '{"benchmark": {}, "benign": ["8.8.8.8", "8.8.8.8"], "reserved": [], "candidate_ips": []}')
    monkeypatch.setattr("ipdb._eval.replay_diff.CORPUS_PATH", tmp_path / "corpus.json")
    ips = sample_ips(_FakeRegistry([with_cls]))
    assert sorted(ips) == ["10.0.0.1", "8.8.8.8"]   # 跨层去重(顺序由种子洗牌决定)


# ── CLI 最小门 ──

def test_main_requires_a_mode():
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2


# ── check_directional:方向断言(spec §9,审计修正 A2 的限定条件)──

from datetime import datetime, timedelta, timezone

from ipdb._eval.replay_diff import check_directional


def _days_ago(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")


def test_single_fresh_within_two_points():
    old = {"scalars": {}, "classifications": {"spam": {"conf": 85,
        "n_sources": 1, "min_first_seen": _days_ago(3)}}}
    new = {"scalars": {}, "classifications": {"spam": {"conf": 85,
        "n_sources": 1, "min_first_seen": _days_ago(3)}}}
    assert check_directional(old, new) == []


def test_single_fresh_violation_flagged():
    old = {"scalars": {}, "classifications": {"spam": {"conf": 85,
        "n_sources": 1, "min_first_seen": _days_ago(3)}}}
    new = {"scalars": {}, "classifications": {"spam": {"conf": 70,
        "n_sources": 1, "min_first_seen": _days_ago(3)}}}
    assert len(check_directional(old, new)) == 1


def test_multi_fresh_must_not_drop():
    old = {"scalars": {}, "classifications": {"spam": {"conf": 70,
        "n_sources": 3, "min_first_seen": _days_ago(10)}}}
    new = {"scalars": {}, "classifications": {"spam": {"conf": 69,
        "n_sources": 3, "min_first_seen": _days_ago(10)}}}
    assert len(check_directional(old, new)) == 1


def test_multi_fresh_floor_band_skipped():
    # 裁决 2026-08-29:old=80 是旧 Admiralty Confirmed floor(max(mean,80))的产物,
    # 诚实均值 65–67 不是 not-drop 的合法参照 → 该断言族跳过 old≥80 的组
    old = {"scalars": {}, "classifications": {"spam": {"conf": 80,
        "n_sources": 3, "min_first_seen": _days_ago(10)}}}
    new = {"scalars": {}, "classifications": {"spam": {"conf": 76,
        "n_sources": 3, "min_first_seen": _days_ago(10)}}}
    assert check_directional(old, new) == []


def test_stale_converges_neutral():
    old = {"scalars": {}, "classifications": {"c2-server": {"conf": 20,
        "n_sources": 2, "min_first_seen": _days_ago(400)}}}
    new = {"scalars": {}, "classifications": {"c2-server": {"conf": 52,
        "n_sources": 2, "min_first_seen": _days_ago(400),
        "max_first_seen": _days_ago(390)}}}
    assert check_directional(old, new) == []


def test_stale_by_freshest_still_enforced():
    # 组内最新 obs(当前侧 max)也已陈旧 → 收敛中立仍强制执行
    old = {"scalars": {}, "classifications": {"c2-server": {"conf": 20,
        "n_sources": 2, "min_first_seen": _days_ago(400)}}}
    new = {"scalars": {}, "classifications": {"c2-server": {"conf": 70,
        "n_sources": 2, "min_first_seen": _days_ago(400),
        "max_first_seen": _days_ago(390)}}}
    assert len(check_directional(old, new)) == 1


def test_stale_mixed_age_with_fresh_obs_skipped():
    # 裁决 2026-08-29:陈旧触发改用组内最新 obs;任一新鲜观测在(当前侧 max=3d),
    # 组即不陈旧,不得断言收敛(旧侧 min=400d 是最老 obs,不充任陈旧证据)
    old = {"scalars": {}, "classifications": {"c2-server": {"conf": 85,
        "n_sources": 1, "min_first_seen": _days_ago(400)}}}
    new = {"scalars": {}, "classifications": {"c2-server": {"conf": 70,
        "n_sources": 1, "min_first_seen": _days_ago(400),
        "max_first_seen": _days_ago(3)}}}
    assert check_directional(old, new) == []


def test_as_name_single_source_direction():
    old = {"scalars": {"as_name": 50}, "classifications": {}}
    new = {"scalars": {"as_name": 85}, "classifications": {}}
    assert check_directional(old, new) == []
