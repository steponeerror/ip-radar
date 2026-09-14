"""Layer-2 watermark hook tests (spec §5.3) — real rebuild round-trip."""
import ipaddress
from pathlib import Path

import pytest

from ipdb._watermark import mark_hit, mark_value
from ipdb._sources._base import IpListSource


class _MarkProbe(IpListSource):
    name = "markprobe"
    category = "threat"
    filename = "markprobe.txt"
    url = ""
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1
    reliability = 0.5


def _build_probe(tmp_path: Path) -> tuple[_MarkProbe, str, str]:
    """确定性搜索一个命中与一个未命中的 /32——γ∈(0,1) 保证两类必存在,
    自适应扫描避免对固定窗口的偶然性依赖。"""
    src = _MarkProbe(tmp_path)
    base = int(ipaddress.ip_address("45.10.1.0"))
    hit_ip = miss_ip = None
    i = 0
    while hit_ip is None or miss_ip is None:
        ip = str(ipaddress.ip_address(base + i))
        if mark_hit(base + i, base + i):
            hit_ip = hit_ip or ip
        else:
            miss_ip = miss_ip or ip
        i += 1
    (tmp_path / "markprobe.txt").write_text(f"{hit_ip}\n{miss_ip}\n")
    return src, hit_ip, miss_ip


def test_layer2_marks_exactly_selected_records(tmp_path):
    src, hit_ip, miss_ip = _build_probe(tmp_path)
    src.rebuild()
    src.load()
    hit_ev = src.query(hit_ip)[0]
    s = int(ipaddress.ip_address(hit_ip))
    assert hit_ev["extra"]["ingest_ref"] == mark_value(s, s)
    # 未选中的记录零标记、无 extra
    miss_ev = src.query(miss_ip)[0]
    assert "extra" not in miss_ev or "ingest_ref" not in miss_ev.get("extra", {})
    # 判定值零触碰
    assert hit_ev["verdict"] == "malicious"
    assert hit_ev["classification_type"] == "blacklist"
    assert hit_ev["reliability"] == 0.5


def test_layer2_failure_is_loud(tmp_path, monkeypatch):
    """标记函数异常必须让 rebuild 失败——静默无标记是安全失败。"""
    import ipdb._sources._lmdb as lm
    def boom(s, e):
        raise RuntimeError("wm hook broken")
    monkeypatch.setattr(lm, "mark_hit", boom)
    src, _, _ = _build_probe(tmp_path)
    with pytest.raises(RuntimeError, match="wm hook broken"):
        src.rebuild()
