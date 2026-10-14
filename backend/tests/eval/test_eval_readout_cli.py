# backend/tests/eval/test_eval_readout_cli.py
"""月轮读数管线 CLI 接线(spec §4.2/S26): 只测 WIRING, 不测库件。

库件(四层装配/读数/组合器/键集)各有单测; 本文件断言 run_readout 把
既有件接成一条链: 生产输入提取(镜像内源文件) → 三件套资产 → 键集快照
→ 四层读数(缺 truth = NO-LAYER 哨兵, 报告照发)→ 行动区块/月报落盘
→ action-block.json 逐轮往返(上轮项 CARRIED 机制活)。
"""
import base64
import json
from pathlib import Path

from ipdb._eval.__main__ import run_readout
from ipdb._eval.assets import AssetMeta, fingerprint, save_asset


def _stamp(ip: str) -> str:
    """sdns:// stamp(dns_public._decode_stamp_ip 的可解码形状):
    proto=1 + props u64 LE 0 + varstr(ip)。"""
    raw = bytes([1]) + (0).to_bytes(8, "little") + bytes([len(ip)]) + ip.encode()
    return "sdns://" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


class _FakeSource:
    def __init__(self, name, category, path):
        self.name = name
        self.category = category
        self._path = path

    def query(self, ip):
        return []


class _FakeRegistry:
    """lookup: 末位 .1 的 IP 被 src_a 指控(malicious); 记录 asof 透传。"""

    def __init__(self, sources):
        self.sources = sources
        self.asof_seen = []

    def lookup(self, ip, asof=None):
        if asof is not None:
            self.asof_seen.append(asof)
        if ip.endswith(".1"):
            return {"ip": ip, "classifications": {"proxy": {
                "type": "proxy", "verdict_conflict": False, "confidence": 50,
                "details": [{"source": "src_a", "verdict": "malicious"}]}}}
        return {"ip": ip, "classifications": {}}


def _build_sources(root: Path) -> list:
    """镜像内源文件的最小复刻: 威胁×2 + root_servers(明文 A/AAAA)
    + dns_public(sdns stamp, 含 VPN 段内解析器与 v6) + x4bnet_vpn
    (v4 段 + v6 行) + cloud_ranges(目录形 aws.json 混 v4/v6)。"""
    a = root / "src_a.txt"
    a.write_text("\n".join(f"10.100.0.{i}" for i in range(1, 41)) + "\n")
    b = root / "src_b.txt"
    b.write_text("\n".join(f"10.101.0.{i}" for i in range(1, 11)) + "\n")
    rs = root / "root_servers.cache"
    rs.write_text("A.ROOT-SERVERS.NET.      3600000      A     198.41.0.4\n"
                  "B.ROOT-SERVERS.NET.      3600000      AAAA  2001:500:200::b\n")
    dp = root / "dns_public.md"
    dp.write_text("\n".join(["## sec1", _stamp("192.0.2.53"),
                             _stamp("10.66.0.9"), _stamp("2001:db8::1")]) + "\n")
    vpn = root / "x4bnet_vpn.txt"
    vpn.write_text("10.66.0.0/16\n2a01::/32\n")
    cd = root / "cloud_ranges"
    cd.mkdir()
    (cd / "aws.json").write_text(json.dumps({
        "prefixes": [{"ip_prefix": "203.0.113.0/25"},
                     {"ip_prefix": "203.0.113.128/25"}],
        "ipv6_prefixes": [{"ipv6_prefix": "2600:1f00::/24"}]}))
    return [
        _FakeSource("src_a", "threat", a),
        _FakeSource("src_b", "threat", b),
        _FakeSource("root_servers", "asset", rs),
        _FakeSource("dns_public", "asset", dp),
        _FakeSource("x4bnet_vpn", "asset", vpn),
        _FakeSource("cloud_ranges", "asset", cd),
    ]


def test_readout_first_run_no_truth_layer(tmp_path):
    assets, kdir, rep = tmp_path / "assets", tmp_path / "keysets", tmp_path / "rep"
    reg = _FakeRegistry(_build_sources(tmp_path))
    md, items, readout = run_readout(reg, rep, assets_dir=assets, keysets_dir=kdir,
                                     run_seed=1, run_id="r1")
    assert md == rep / "monthly-r1.md" and md.is_file()
    text = md.read_text()
    assert readout["degraded"] is True            # 缺 truth = 降级但照发
    assert "NO-LAYER" in text and "真值层缺" in text   # 哨兵贯穿(§2.3)
    assert (rep / "snapshots" / "r1").is_dir()    # F10 快照随层落盘
    ab = json.loads((rep / "action-block.json").read_text())
    assert ab["header"]["run_seed"] == 1          # run_seed 全链落 report
    assert ab["items"]
    assert all(set(i) == {"id", "title", "source", "deadline", "status"}
               for i in ab["items"])
    assert any(i["id"].startswith("truth-") and i["status"] == "OPEN"
               for i in ab["items"])              # 缺层 → 规则生成 OPEN 项
    # 生产输入接线: VPN 段内解析器(10.66.0.9)被剔, root+v4 stamp 存活
    infra = json.loads((assets / "infra" / "meta.json").read_text())
    assert infra["params"]["n_resolvers"] == 2
    assert (kdir / "r1" / "src_a.txt.gz").is_file()   # 键集快照逐源落盘


def test_readout_second_run_carries_prev_items(tmp_path):
    assets, kdir, rep = tmp_path / "assets", tmp_path / "keysets", tmp_path / "rep"
    reg = _FakeRegistry(_build_sources(tmp_path))
    _, items1, _ = run_readout(reg, rep, assets_dir=assets, keysets_dir=kdir,
                               run_seed=1, run_id="r1")
    md2, items2, _ = run_readout(reg, rep, assets_dir=assets, keysets_dir=kdir,
                                 run_seed=2, run_id="r2")
    assert (rep / "monthly-r2.md").is_file()
    carried = [i for i in items2 if i.status == "CARRIED"]
    assert carried                                 # 上轮 OPEN 无处置 → CARRIED
    assert {i.id for i in carried} <= {i.id for i in items1}
    ab2 = json.loads((rep / "action-block.json").read_text())
    assert ab2["header"]["run_id"] == "r2"         # header 逐轮覆盖
    # run_seed 变 → 共识层指纹变 → S12/S17 换版=趋势重置警示行
    assert "换版" in md2.read_text()


def test_readout_truth_layer_anchors_asof_and_epsilon(tmp_path):
    assets, kdir, rep = tmp_path / "assets", tmp_path / "keysets", tmp_path / "rep"
    members = ["10.100.0.1", "10.100.0.2", "10.101.0.3", "192.0.2.7"]
    save_asset(assets / "truth", members, AssetMeta(
        version="v-t", kind="truth", fingerprint=fingerprint(members),
        member_count=len(members), params={}, eval_env="monthly",
        created_at="2026-10-01"))                  # ops 侧经 T4 三闸产出, 接线只消费
    reg = _FakeRegistry(_build_sources(tmp_path))
    md, _, readout = run_readout(reg, rep, assets_dir=assets, keysets_dir=kdir,
                                 run_seed=3, run_id="r3")
    assert readout["layers"]["truth"]["status"] == "OK"
    assert reg.asof_seen                           # asof 锚(T10)透传引擎链
    text = md.read_text()
    assert "ε=0.00" in text                        # F7 三档行在
    assert "真值层缺" not in text                   # ε 哨兵行不误发
    assert readout["degraded"] is False
