"""F10 per-IP 快照持久化(jsonl.gz)测试。

快照一律经真实 persist_ip_snapshot 落盘再 load 回读; 断言钉三件事:
roundtrip 无损保序(哲学 1 证据永不灭失)、落盘即 gzip、压缩率 <50%。
"""
import gzip
import json

from ipdb._eval.snapshots import load_ip_snapshot, persist_ip_snapshot


def _payload(conf: float) -> dict:
    """预期形状载荷(classifications/verdict), 结构重复 → 压缩率真实。"""
    cls = {"ssh_bruteforce": {"type": "ssh_bruteforce", "verdict": "malicious",
                              "detected": True, "confidence": conf,
                              "corroborated": False},
           "spam_source": {"type": "spam_source", "verdict": "benign",
                           "detected": False, "confidence": conf / 2,
                           "corroborated": True}}
    verdict = {"verdict": "malicious", "confidence": conf,
               "types": ["ssh_bruteforce"], "is_cdn": False}
    return {"classifications": cls, "verdict": verdict}


def _snapshot(n: int) -> dict:
    return {f"10.0.{i // 256}.{i % 256}": _payload(0.5 + i / 1000)
            for i in range(n)}


def test_roundtrip_preserves_order_and_payload(tmp_path):
    snapshot = _snapshot(3)
    path = persist_ip_snapshot(tmp_path, "run-a", "truth", snapshot)
    assert path == tmp_path / "snapshots" / "run-a" / "truth.jsonl.gz"
    assert path.read_bytes()[:2] == b"\x1f\x8b"  # 落盘即 gzip
    loaded = load_ip_snapshot(path)
    assert loaded == snapshot                       # 无损
    assert list(loaded) == list(snapshot)           # 保序 = 落盘行序
    # 空快照也是合法落盘: 读回 {}
    assert load_ip_snapshot(
        persist_ip_snapshot(tmp_path, "run-a", "neutral", {})) == {}


def test_persist_compression_below_half_of_plain(tmp_path):
    # 钉「持久化=压缩」: 同内容紧凑 jsonl 明文的一半装不下才算过
    snapshot = _snapshot(200)
    path = persist_ip_snapshot(tmp_path, "run-b", "truth", snapshot)
    plain = "".join(
        json.dumps({"ip": ip, **v}, separators=(",", ":")) + "\n"
        for ip, v in snapshot.items()).encode()
    assert path.stat().st_size < 0.5 * len(plain)


def test_unexpected_shape_written_whole_not_filtered(tmp_path):
    # 精简纪律: 形状不符的 dict 整值照写, 不自作额外过滤(有 verdict 单键走精简)
    snapshot = {"1.2.3.4": {"country": {"value": "US"}, "asn": {"asn": 64512}},
                "5.6.7.8": {"verdict": {"verdict": "malicious"}}}
    loaded = load_ip_snapshot(persist_ip_snapshot(tmp_path, "run-c",
                                                  "consensus", snapshot))
    assert loaded == snapshot
    assert list(loaded) == list(snapshot)


def test_half_shaped_payload_written_whole_not_slimmed(tmp_path):
    # 两键齐备才精简: 缺 verdict 的半形状载荷整值照写(country/threat 不被裁)
    snapshot = {"1.2.3.4": {"classifications": {"spam_source": {"type": "spam_source"}},
                            "country": {"value": "US"},
                            "threat": {"verdict": "benign"}}}
    loaded = load_ip_snapshot(persist_ip_snapshot(tmp_path, "run-h", "truth",
                                                  snapshot))
    assert loaded == snapshot            # 整值照写, 宁多存不丢证


def test_persist_deterministic_bytes(tmp_path):
    # mtime=0 + filename="": 同快照两轮落盘字节一致(冻结工件可复现)
    snapshot = _snapshot(5)
    p1 = persist_ip_snapshot(tmp_path, "run-d1", "truth", snapshot)
    p2 = persist_ip_snapshot(tmp_path, "run-d2", "truth", snapshot)
    assert p1.read_bytes() == p2.read_bytes()
