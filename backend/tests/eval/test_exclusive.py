# backend/tests/eval/test_exclusive.py
"""--exclusive 排他率探针测试(exclusive-governance Task 1,2026-10-18)。

契约(task-1-brief.md,协议逐字 = /tmp 翻案探针):
- 提取:_IP_RE 抓 token → 剥 CIDR mask → v4 → 去重保序;
- 采样确定性:同 seed 同序(random.Random(seed).shuffle),封顶 n;
- 阳性对照闸:对照前 20 bare IP 池命中 <18 → exit 2,消息含
  "ABORT: control failed" 且不出任何数字;
- CLI wiring 冒烟:monkeypatch 数据面(lookup/load_db/_sources),
  零依赖真 data/;lookup 失败即抛(2026-10-10 假零判例,不 except-continue)。

全部 fake/stub,零网络零 DB。
"""
import json
from types import SimpleNamespace

import pytest

from ipdb._eval.__main__ import main
from ipdb._eval.exclusive import (DEFAULT_SEED, ControlAbort, extract_feed_keys,
                                  run, sample_keys)


@pytest.fixture(autouse=True)
def _restore_projection_pin():
    """CLI 探针把 InfraServicesSource._sync_projection 置 no-op 是进程级
    class 补丁;不还原会跨文件污染同进程后续投影测试(pytest 单进程,
    eval < sources 字母序)。"""
    from ipdb._sources.infra_services import InfraServicesSource
    orig = InfraServicesSource._sync_projection
    yield
    InfraServicesSource._sync_projection = orig


def _payload(ip: str, sources: list[str]) -> dict:
    """to_dict 形状指控载荷;sources 空 = 池静默(排他)。"""
    if not sources:
        return {"ip": ip, "classifications": {}}
    return {"ip": ip, "classifications": {"blacklist": {
        "type": "blacklist", "verdict": "malicious", "detected": True,
        "details": [{"source": s, "verdict": "malicious",
                     "reliability": 0.5} for s in sources]}}}


class _Result:
    """_real_registry().lookup 包装层调 .to_dict() —— 假 LookupResult。"""
    def __init__(self, payload):
        self._p = payload
    def to_dict(self):
        return self._p


def _install_plane(monkeypatch, tmp_path, *, covered_control: bool):
    """monkeypatch 数据面三件:_sources(只挂 binarydefense raw 路径)、
    load_db、lookup(对照按 covered_control 命中;feed 仅 .1/.2 被覆盖)。"""
    import ipdb._registry as reg
    ctrl = tmp_path / "binarydefense_banlist.txt"
    ctrl.write_text("# banlist header\n"
                    + "\n".join(f"192.0.2.{i}" for i in range(1, 21)) + "\n")
    feed = tmp_path / "feed.txt"
    feed.write_text("203.0.113.1\n203.0.113.2\n203.0.113.1\n"
                    "203.0.113.0/24\n# trailing comment\n")
    monkeypatch.setattr(reg, "_sources",
                        [SimpleNamespace(name="binarydefense", _path=ctrl)])
    monkeypatch.setattr(reg, "load_db", lambda: None)

    def fake_lookup(ip, allowed_sources=None, *, asof=None):
        if ip.startswith("192.0.2."):
            srcs = ["binarydefense"] if covered_control else []
        else:
            srcs = ["cisa"] if ip in ("203.0.113.1", "203.0.113.2") else []
        return _Result(_payload(ip, srcs))

    monkeypatch.setattr(reg, "lookup", fake_lookup)
    return feed


def test_extract_feed_keys_cidr_dedupe_junk():
    text = ("# comment\n1.2.3.4\n1.2.3.4/24\n1.2.3.4\n"
            "not-an-ip junk line\n5.6.7.0/8 other text 203.0.113.9\n")
    assert extract_feed_keys(text) == ["1.2.3.4", "5.6.7.0", "203.0.113.9"]


def test_sample_keys_same_seed_same_order():
    uniq = [f"203.0.113.{i}" for i in range(1, 51)]
    a, b = sample_keys(uniq, DEFAULT_SEED), sample_keys(uniq, DEFAULT_SEED)
    assert a == b
    assert a != uniq                      # seed 真生效(非原样返回)
    assert a != sample_keys(uniq, DEFAULT_SEED + 1)   # 异 seed 异序
    assert sorted(a) == sorted(uniq)      # 同元素重排


def test_sample_keys_caps_at_n():
    uniq = [f"198.51.100.{i}" for i in range(400)]
    assert len(sample_keys(uniq, DEFAULT_SEED)) == 300


def test_cli_exclusive_smoke_json(monkeypatch, tmp_path, capsys):
    feed = _install_plane(monkeypatch, tmp_path, covered_control=True)
    main(["--exclusive", str(feed), "--json"])
    res = json.loads(capsys.readouterr().out)
    # .1/.2 去重 + .0(剥 /24 mask)= 3 唯一键;.1/.2 被 cisa 覆盖
    assert res["feed_unique_keys"] == 3
    assert res["sampled"] == 3
    assert res["exclusive"] == 1 and res["covered"] == 2
    assert res["exclusive_rate"] == pytest.approx(1 / 3)
    assert res["coverage_sources"] == {"cisa": 2}
    assert res["exclusive_sample"] == ["203.0.113.0"]
    assert res["seed"] == DEFAULT_SEED
    assert res["control"]["hits"] == 20


def test_cli_control_abort_json_exit2(monkeypatch, tmp_path, capsys):
    feed = _install_plane(monkeypatch, tmp_path, covered_control=False)
    with pytest.raises(SystemExit) as ei:
        main(["--exclusive", str(feed), "--json"])
    assert ei.value.code == 2
    msg = json.loads(capsys.readouterr().out)["error"]["message"]
    assert "ABORT: control failed" in msg
    assert not any(ch.isdigit() for ch in msg)   # 不出数字


def test_cli_control_abort_stderr_nonjson(monkeypatch, tmp_path, capsys):
    feed = _install_plane(monkeypatch, tmp_path, covered_control=False)
    with pytest.raises(SystemExit) as ei:
        main(["--exclusive", str(feed)])
    assert ei.value.code == 2
    assert "ABORT: control failed" in capsys.readouterr().err


def test_cli_empty_feed_json_envelope_exit2(monkeypatch, tmp_path, capsys):
    """空 feed --json 必须走信封退出,不裸 ValueError 栈(spec §5.2;评审
    Important-1 2026-10-18)。abort 族 rc=2;消息含 feed 路径可有数字
    (no-digit 约束只及对照闸)。"""
    feed = _install_plane(monkeypatch, tmp_path, covered_control=True)
    feed.write_text("# comment only\nnot-an-ip line\n")
    with pytest.raises(SystemExit) as ei:
        main(["--exclusive", str(feed), "--json"])
    assert ei.value.code == 2
    err = json.loads(capsys.readouterr().out)["error"]
    assert err["code"] == "bad_feed"
    assert "零个候选键" in err["message"]


def test_cli_empty_feed_stderr_nonjson(monkeypatch, tmp_path, capsys):
    """同一空 feed 非 json:清洁 stderr 单行 + exit 2,不裸栈。"""
    feed = _install_plane(monkeypatch, tmp_path, covered_control=True)
    feed.write_text("# comment only\n")
    with pytest.raises(SystemExit) as ei:
        main(["--exclusive", str(feed)])
    assert ei.value.code == 2
    assert "零个候选键" in capsys.readouterr().err


def test_run_same_seed_reproducible(tmp_path):
    ctrl = tmp_path / "bd.txt"
    ctrl.write_text("\n".join(f"192.0.2.{i}" for i in range(1, 21)))
    feed = tmp_path / "feed.txt"
    feed.write_text("\n".join(f"203.0.113.{i}" for i in range(1, 40)))

    def lookup(ip, asof=None):
        if ip.startswith("192.0.2."):       # 对照 20 IP 全覆盖(闸过)
            return _payload(ip, ["binarydefense"])
        tail = int(ip.rsplit(".", 1)[1])
        return _payload(ip, ["x"] if tail % 2 else [])

    a = run(feed, lookup, control_path=ctrl, seed=7)
    assert a == run(feed, lookup, control_path=ctrl, seed=7)
    assert a["exclusive_sample"] != run(
        feed, lookup, control_path=ctrl, seed=8)["exclusive_sample"]


def test_lookup_failure_raises(tmp_path):
    ctrl = tmp_path / "bd.txt"
    ctrl.write_text("\n".join(f"192.0.2.{i}" for i in range(1, 21)))
    feed = tmp_path / "feed.txt"
    feed.write_text("203.0.113.1\n")

    def boom(ip):
        raise RuntimeError("db gone")

    with pytest.raises(RuntimeError):
        run(feed, boom, control_path=ctrl)
    with pytest.raises(ControlAbort):
        run(feed, lambda ip: _payload(ip, []), control_path=ctrl)
