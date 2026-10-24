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

import pytest

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
    """lookup: 末位 .1 的 IP 被 src_a 指控(malicious); 记录 asof 透传。

    组级 verdict 键是 to_dict 生产契约(_types.py:195): layered._accusing_types
    门控 ca.get("verdict") ∈ _ACCUSING, 缺键 = 该 IP 全组按干净算(评审核)。"""

    def __init__(self, sources):
        self.sources = sources
        self.asof_seen = []

    def lookup(self, ip, asof=None):
        if asof is not None:
            self.asof_seen.append(asof)
        if ip.endswith(".1"):
            return {"ip": ip, "classifications": {"proxy": {
                "type": "proxy",
                "verdict": "malicious",
                "verdict_conflict": False, "confidence": 50,
                "details": [{"source": "src_a", "verdict": "malicious"}]}}}
        return {"ip": ip, "classifications": {}}


def _build_sources(root: Path) -> list:
    """镜像内源文件的最小复刻: 威胁×3(含目录形) + root_servers(明文
    A/AAAA)+ dns_public(sdns stamp, 含 VPN 段内解析器与 v6)+ x4bnet_vpn
    (v4 段 + v6 行)+ cloud_ranges(目录形 aws.json 混 v4/v6)。"""
    a = root / "src_a.txt"
    a.write_text("\n".join(f"10.100.0.{i}" for i in range(1, 41)) + "\n")
    b = root / "src_b.txt"
    b.write_text("\n".join(f"10.101.0.{i}" for i in range(1, 11)) + "\n")
    d = root / "src_dir"  # 目录形威胁源(生产判例 firehol/blocklist_de):
    d.mkdir()             # 键集提取结构性贡献 0, 不入池分母(P1-1)
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
        _FakeSource("src_dir", "threat", d),
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
    # P1-1 池分母: sum(min(PER_SOURCE_N, len(键集))) = 30+10+0 —— 目录形
    # 源的结构性零贡献不入分母(旧口径 30×3=90 恒触池竭假警), 回声收窄
    # (键集实缩)才是该规则的真信号
    assert readout["assembly_stats"]["expected_pool"] == 40
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
    # 语料治理(终审 P1-3): 输入指纹未变 → infra 沿用前轮 run_seed, 指纹
    # 恒定(采样噪声不构成换版); consensus=滚动语料豁免注记 → 全 md 无
    # 换版=趋势重置行
    infra_meta = json.loads((assets / "infra" / "meta.json").read_text())
    assert infra_meta["params"]["run_seed"] == 1
    assert "换版=趋势重置" not in md2.read_text()
    # 云段输入实变 → infra 换新 seed + 指纹变 → 换版行点名 infra 不点
    # consensus(共识侧指纹虽也月月变, 滚动豁免)
    (tmp_path / "cloud_ranges" / "aws.json").write_text(json.dumps({
        "prefixes": [{"ip_prefix": "198.51.100.0/25"},
                     {"ip_prefix": "198.51.100.128/25"}],
        "ipv6_prefixes": []}))
    md3, _, _ = run_readout(reg, rep, assets_dir=assets, keysets_dir=kdir,
                            run_seed=3, run_id="r3")
    assert json.loads((assets / "infra" / "meta.json")
                      .read_text())["params"]["run_seed"] == 3
    reset = [l for l in md3.read_text().splitlines() if "换版=趋势重置" in l]
    assert reset and "infra" in reset[0] and "consensus" not in reset[0]
    assert "滚动语料" in md3.read_text()           # 共识滚动声明行在场


def test_readout_scorecard_oc_wired_from_latest_verdict_jsons(tmp_path):
    assets, kdir, rep = tmp_path / "assets", tmp_path / "keysets", tmp_path / "rep"
    reg = _FakeRegistry(_build_sources(tmp_path))
    rep.mkdir()  # 逐源 verdict JSON 先在, run_readout 才跑(月轮真实序)
    # --all 先于 --readout 落同目录逐源 verdict JSON(report.py 秒级 ts 命名)
    for name, payload in (
            ("src_a-20261001-000000.json",
             {"source": "src_a", "metrics": {"oc": {"value": 0.9, "n": 9}}}),
            ("src_a-20261014-120000.json",
             {"source": "src_a", "metrics": {"oc": {"value": 0.5, "n": 5}}}),
            ("src_b-20261014-120000.json",
             {"source": "src_b", "metrics": {"oc": {"value": 0.25, "n": 4}}})):
        (rep / name).write_text(json.dumps(payload))
    md, _, _ = run_readout(reg, rep, assets_dir=assets, keysets_dir=kdir,
                           run_seed=1, run_id="r1")
    rows = {l.split("|")[1].strip(): l for l in md.read_text().splitlines()
            if l.startswith("| src_")}
    assert "50.0%" in rows["src_a"]    # 每源取最新 ts 文件, 非首份 0.9
    assert "25.0%" in rows["src_b"]    # 冗余度% 列非 N/A(P1-2 接线修复)


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
    # F7 三档行在, 且分子非零: 真值成员 4 个中 10.100.0.1(末位 .1)真被指控
    # → hits=1 → ε=0.00 档 0.2500(组级 verdict 缺位时恒 0.0000, 旧版空过)
    assert "ε=0.00 → 0.2500" in text
    assert "真值层缺" not in text                   # ε 哨兵行不误发
    assert readout["degraded"] is False


# ── 能力轨北星观测件(#185;STANDARD.md E-5, 只观测不持门)──────


class _CorrRegistry(_FakeRegistry):
    """双证人变体: .1 IP 由 src_a+src_b 同时指控 → k_all=2(corroborated);
    两源均非聚合簇(LINEAGE_CLUSTERS 表外)→ derived_only 恒 0
    (corroborated 精度=100%,114DNS 假印证面的反例面)。"""

    def lookup(self, ip, asof=None):
        res = super().lookup(ip, asof=asof)
        if ip.endswith(".1"):
            res["classifications"]["proxy"]["details"].append(
                {"source": "src_b", "verdict": "malicious"})
        return res


def _truth_asset(assets):
    members = ["10.100.0.1", "192.0.2.7"]
    save_asset(assets / "truth", members, AssetMeta(
        version="v-t", kind="truth", fingerprint=fingerprint(members),
        member_count=len(members), params={}, eval_env="monthly",
        created_at="2026-10-01"))


def _anchors_file(rep, name, n_fail):
    """月轮真实序: --anchors 先于 --readout 落 model/anchors-*.json
    (回归轨判定门工件 = 能力轨锚读数的单一真源)。"""
    m = rep / "model"
    m.mkdir(parents=True, exist_ok=True)
    (m / name).write_text(json.dumps(
        {"kind": "anchors", "eval_env": "monthly",
         "generated_at": "2026-10-01", "n_total": 19,
         "failures": [{"ip": f"10.0.0.{i}"} for i in range(n_fail)]}))


def test_readout_writes_northstar_capability_track_record(tmp_path):
    # readout 腿落 northstar-<run_id>.json + monthly-*.md 北星行;
    # 单源 fixture 全部命中 k=1 → corroborated 面零读数 → N/A 不虚构
    assets, kdir, rep = tmp_path / "assets", tmp_path / "keysets", tmp_path / "rep"
    _truth_asset(assets)
    reg = _FakeRegistry(_build_sources(tmp_path))
    _anchors_file(rep, "anchors-20261001-000000.json", 0)
    md, _, _ = run_readout(reg, rep, assets_dir=assets, keysets_dir=kdir,
                           run_seed=1, run_id="r1")
    ns = json.loads((rep / "northstar-r1.json").read_text())
    assert ns["kind"] == "northstar" and ns["run_id"] == "r1"
    assert ns["anchor_green"]["n_total"] == 19
    assert ns["anchor_green"]["rate"] == 1.0
    assert ns["corroborated"]["n"] == 0
    assert ns["corroborated"]["precision"] is None
    text = md.read_text()
    assert "能力轨北星" in text and "只观测不持门" in text
    assert "19/19(100.0%" in text
    assert "零 corroborated 读数" in text
    assert "环比 首轮" in text


def test_readout_northstar_second_round_mom(tmp_path):
    assets, kdir, rep = tmp_path / "assets", tmp_path / "keysets", tmp_path / "rep"
    _truth_asset(assets)
    sources = _build_sources(tmp_path)  # 同 tmp_path 只建一次(mkdir 幂等性)
    _anchors_file(rep, "anchors-20261001-000000.json", 0)
    run_readout(_FakeRegistry(sources), rep,
                assets_dir=assets, keysets_dir=kdir, run_seed=1, run_id="r1")
    _anchors_file(rep, "anchors-20261101-000000.json", 2)
    md2, _, _ = run_readout(_CorrRegistry(sources), rep,
                            assets_dir=assets, keysets_dir=kdir,
                            run_seed=2, run_id="r2")
    ns2 = json.loads((rep / "northstar-r2.json").read_text())
    assert ns2["anchor_green"]["artifact"] == "anchors-20261101-000000.json"
    assert ns2["anchor_green"]["n_fail"] == 2
    assert ns2["anchor_green"]["rate"] == pytest.approx(17 / 19)
    assert ns2["anchor_green_mom_pp"] == pytest.approx((17 / 19 - 1) * 100)
    # 双源变体: 10.101.0.1 必入 consensus 采样面(src_b 键集 10 全采)→
    # corroborated n≥1; 非聚合双源 → derived_only=0 → 精度 100%
    assert ns2["corroborated"]["n"] >= 1
    assert ns2["corroborated"]["derived_only"] == 0
    assert ns2["corroborated"]["precision"] == 1.0
    assert ns2["corroborated_precision_mom_pp"] is None  # r1 轮精度 N/A
    text = md2.read_text()
    assert "17/19(89.5%" in text
    assert "corroborated 精度 100.0%" in text
    assert "环比 -10.5pp" in text
    assert "环比 前轮 N/A" in text
