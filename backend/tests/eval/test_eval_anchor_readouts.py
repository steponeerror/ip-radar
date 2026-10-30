# backend/tests/eval/test_eval_anchor_readouts.py
"""锚读数族 v0 两读数(#233 交付块3,ADR 0013)。

Seam = 纯函数面(lookup 载荷 → 读数结构)+ 段成员采样装配;载荷用生产
to_dict 形状(classifications/details,agg_share 测试同款)。统计真源 =
二项尾概率代数定义(Clopper & Pearson 1934),与 beta_ppf 实现互为独立
验证,禁镜像实现。
"""
import ipaddress
import json
from math import comb
from types import SimpleNamespace

from ipdb._eval.anchor_readouts import (
    clean_anchor_fp,
    clopper_pearson,
    run_anchor_readouts,
    sample_segment_members,
    scanner_recall,
)
from ipdb._eval.corpus import stable_seed


def _payload(groups):
    """生产 to_dict 形状最小载荷:groups = [(ctype, verdict, corroborated,
    [(source, reliability, verdict), ...]), ...]。"""
    classifications = {}
    for ctype, verdict, corr, voters in groups:
        classifications[ctype] = {
            "type": ctype, "verdict": verdict, "detected": True,
            "confidence": 55, "corroborated": corr,
            "verdict_conflict": False,
            "details": [{"source": s, "reliability": r, "verdict": v}
                        for s, r, v in voters],
        }
    return {"ip": "x", "classifications": classifications,
            "is_reserved": False, "attributes": {}}


# ── 统计:Clopper-Pearson 精确界(独立真源 = 二项代数) ──────────────

def _binom_cdf(k, n, p):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i)
               for i in range(k + 1))


def test_clopper_pearson_matches_binomial_tail_definition():
    """CP 界由二项尾概率定义:θ_L 使 P(X≤k-1)=1-α/2,θ_U 使 P(X≤k)=α/2
    (Clopper & Pearson 1934)。beta_ppf 路线须满足代数定义(非实现自证)。
    两参数化 = 两读数真值形状:(3,22) 手算例 +(241,300) 真数据首读数
    (t3-artifacts scanner-recall 2026-10-28,k_hit/n_probe 原值钉测)。"""
    lo, hi = clopper_pearson(3, 22)
    assert abs(_binom_cdf(2, 22, lo) - 0.975) < 1e-6
    assert abs(_binom_cdf(3, 22, hi) - 0.025) < 1e-6
    lo, hi = clopper_pearson(241, 300)
    assert abs(_binom_cdf(240, 300, lo) - 0.975) < 1e-6
    assert abs(_binom_cdf(241, 300, hi) - 0.025) < 1e-6
    # 与真数据首读数工件逐位对拍(漂移即 beta_ppf/clopper 算术回归)
    assert abs(lo - 0.753777191) < 1e-8
    assert abs(hi - 0.846784997) < 1e-8


def test_clopper_pearson_degenerate_closed_forms():
    """退化支闭式:k=0 → lo=0、零事件上界 1-(α/2)^(1/n);k=n → hi=1、
    lo=(α/2)^(1/n)(Beta(1,n)/Beta(n,1) CDF 闭式,独立于实现);
    n=0 → (None, None)(零读数≠0,model.ci 同款纪律)。"""
    lo0, hi0 = clopper_pearson(0, 22)
    assert lo0 == 0.0
    assert abs(hi0 - (1 - 0.025 ** (1 / 22))) < 1e-9
    lon, hin = clopper_pearson(22, 22)
    assert hin == 1.0
    assert abs(lon - 0.025 ** (1 / 22)) < 1e-9
    assert clopper_pearson(0, 0) == (None, None)


# ── 读数A:干净锚误报率 ────────────────────────────────────────────

# 活体首例(T1 预检门 2026-10-28 实测:k.root=193.0.14.129 被
# cps_collected_iocs 指控,verdict=malicious confidence=50;ADR 0008 发现
# 固化——照常入表,人裁终局)。本读数的第一个真样本,钉住报告形状。
_KROOT_PAYLOAD = _payload([("blacklist", "malicious", False, [
    ("cps_collected_iocs", 0.50, "malicious"),
])])


def test_clean_anchor_fp_kroot_live_sample_pinned():
    anchors = [("193.0.14.129", "clean"), ("8.8.8.8", "clean"),
               ("1.1.1.1", "clean")]

    def lk(ip):
        return (_KROOT_PAYLOAD if ip == "193.0.14.129"
                else {"classifications": {}, "is_reserved": False})

    res = clean_anchor_fp(lk, anchors)
    assert res["n"] == 3 and res["k"] == 1
    assert res["fp_rate"] == 1 / 3
    hit = res["accused"][0]
    assert hit["ip"] == "193.0.14.129" and hit["expect"] == "clean"
    assert hit["accusers"] == ["cps_collected_iocs"]
    # 无损红线:原始指控 detail(三元组)原样留痕;pool 是 dedup 后读数
    raw = hit["groups"][0]["raw_accusers"]
    assert raw == [{"source": "cps_collected_iocs", "reliability": 0.50,
                    "verdict": "malicious"}]
    assert hit["groups"][0]["pool"] == ["cps_collected_iocs"]
    # census 随件:N 全量(非采样)+ 成员清单可回算
    assert res["members"] == ["193.0.14.129", "8.8.8.8", "1.1.1.1"]
    # 零事件上界仅 k==0 有值(k>0 → None,消费面注记字段)
    assert res["zero_event_upper_95"] is None


def test_clean_anchor_fp_lineage_dedup_keeps_raw_evidence():
    """指控池单源化先例(_logodds.accuser_pool,issue #244):同源
    max 系数 → dedup_lineage,禁裸
    detail.source。谱系锚回声(spamhaus→emerging_threats)不双计(宁少算,
    回声不是印证),原始证据仍无损留痕。"""
    anchored = _payload([("blacklist", "malicious", True, [
        ("spamhaus", 0.90, "malicious"),
        ("emerging_threats", 0.80, "malicious"),
    ])])
    res = clean_anchor_fp(lambda ip: anchored, [("8.8.8.8", "clean")])
    hit = res["accused"][0]
    assert hit["accusers"] == ["spamhaus"]            # 回声已剔,不双计
    assert [d["source"] for d in hit["groups"][0]["raw_accusers"]] == \
        ["spamhaus", "emerging_threats"]              # 原始面无损


def test_clean_anchor_fp_zero_event_exact_bound():
    lk = lambda ip: {"classifications": {}, "is_reserved": False}
    res = clean_anchor_fp(lk, [("8.8.8.8", "clean"), ("1.1.1.1", "clean")])
    assert res["k"] == 0 and res["fp_rate"] == 0.0
    assert res["cp95"]["lo"] == 0.0
    assert abs(res["cp95"]["hi"] - (1 - 0.025 ** 0.5)) < 1e-9
    assert abs(res["zero_event_upper_95"] - (1 - 0.025 ** 0.5)) < 1e-9
    assert res["accused"] == []


def test_clean_anchor_fp_census_is_clean_expectation_only():
    """census 分母 = 全部 expect=clean 锚(谓词限定锚:其他谓词的锚不进
    本读数);N 全量非采样(锚集本身就小,ADR 0013 census 纪律)。"""
    lk = lambda ip: {"classifications": {}, "is_reserved": False}
    res = clean_anchor_fp(lk, [("10.0.0.1", "reserved"),
                               ("185.220.101.1", "tor"),
                               ("52.95.116.115", "hosting"),
                               ("8.8.8.8", "clean")])
    assert res["n"] == 1 and res["members"] == ["8.8.8.8"]


# ── 读数B:扫描锚召回 ──────────────────────────────────────────────

def _scanner_payload(hit_sources):
    """scanner 自报段成员载荷:scanner 组自带 scanner_ranges 自证回声 +
    (可选)行为源指控票(指控票才是召回分子)。"""
    voters = [("scanner_ranges", 0.90, "malicious")] + list(hit_sources)
    return _payload([("scanner", "malicious", True, voters)])


def test_scanner_recall_leaveout_self_echo():
    """leave-out:scanner_ranges 自证不进分子(票 #233 验收:自证不进
    分子)。与 ADR 0011 真值层全排除刻意不对称——这里只排自回声,测的
    是指控池对已知扫描器的召回(ADR 0013);self_echo 留痕供审计。"""
    lk = lambda ip: _scanner_payload([("sw_scanners", 0.75, "malicious"),
                                      ("binarydefense", 0.70, "malicious")])
    res = scanner_recall(lk, ["162.142.148.0/24"], n=4)
    assert res["n_probe"] == 4 and res["k_hit"] == 4
    assert res["recall"] == 1.0
    m = res["members"][0]
    assert m["hit"] is True and m["self_echo"] is True
    assert m["accusers"] == ["binarydefense", "sw_scanners"]  # leave-out 后
    assert res["n_self_echo"] == 4
    assert res["leave_out"] == "scanner_ranges"
    assert res["census"]["membership_check"] == "pass"


def test_scanner_recall_self_echo_only_is_miss():
    """仅自证(行为源缺席)= 召回盲区证据,不计命中(宁少算)。"""
    lk = lambda ip: _scanner_payload([])
    res = scanner_recall(lk, ["162.142.148.0/24"], n=4)
    assert res["k_hit"] == 0 and res["recall"] == 0.0
    assert res["members"][0]["hit"] is False
    assert res["members"][0]["accusers"] == []
    assert res["members"][0]["self_echo"] is True


def test_scanner_recall_mixed_hits_consistent():
    """奇偶分票:k_hit 与 per-成员命中明细逐条一致(明细留痕可回算)。"""
    def lk(ip):
        last = int(ip.rsplit(".", 1)[1])
        if last % 2 == 0:
            return _scanner_payload([("sw_scanners", 0.75, "malicious")])
        return _scanner_payload([])

    res = scanner_recall(lk, ["162.142.148.0/24"], n=4)
    hits = sum(1 for m in res["members"] if m["hit"])
    assert res["k_hit"] == hits
    assert res["recall"] == hits / 4
    for m in res["members"]:
        assert set(m) == {"ip", "hit", "self_echo", "accusers"}


def test_scanner_recall_zero_probe_is_none_not_zero():
    """零读数≠0(空真值层 → recall None,与 model.ci n=0 同款纪律)。"""
    res = scanner_recall(lambda ip: {}, [])
    assert res["n_probe"] == 0 and res["recall"] is None
    assert res["cp95"]["lo"] is None and res["cp95"]["hi"] is None


# ── 段成员采样:census 纪律 ────────────────────────────────────────

def test_sample_segment_members_census_discipline():
    """census 随件(N/seed/成员清单)+ 同 seed 逐字节可复算 + 成员判定
    独立真源(ipaddress 直判,非实现自证)。坏 token 与 v6 计数不静默。"""
    prefixes = ["162.142.148.0/24", "198.51.100.7",   # v4:/24 + 裸 IP(/32)
                "2001:db8::/32",                       # v6:计数,不入采样面
                "not-a-cidr"]                          # 坏 token:计数
    a = sample_segment_members(prefixes, n=50)
    b = sample_segment_members(prefixes, n=50)
    assert a["probes"] == b["probes"]                  # 同 seed 可复算
    assert a["n_prefixes"] == 4 and a["n_v4"] == 2
    assert a["n_v6"] == 1 and a["n_bad"] == 1
    assert a["v4_covered_addresses"] == 256 + 1
    assert len(a["probes"]) == 50
    nets = [ipaddress.ip_network(p, strict=False)
            for p in ("162.142.148.0/24", "198.51.100.7")]
    assert all(any(ipaddress.ip_address(ip) in n for n in nets)
               for ip in a["probes"])                  # 成员判定独立真源
    assert a["seed"] == stable_seed("scanner_ranges")  # per-source 纪律
    assert a["membership_check"] == "pass"


def test_sample_segment_members_zero_v4_universe():
    res = sample_segment_members(["2001:db8::/32"], n=10)
    assert res["probes"] == [] and res["v4_covered_addresses"] == 0


# ── 装配与 CLI ────────────────────────────────────────────────────

def test_run_anchor_readouts_writes_two_artifacts(tmp_path):
    csv = tmp_path / "scanner_ranges.csv"
    csv.write_text("162.142.148.0/24,Censys\n")
    src = SimpleNamespace(name="scanner_ranges", _path=csv)
    net = ipaddress.ip_network("162.142.148.0/24")

    def lk(ip):
        if ip == "193.0.14.129":
            return _KROOT_PAYLOAD
        if ipaddress.ip_address(ip) in net:
            return _scanner_payload([("sw_scanners", 0.75, "malicious")])
        return {"classifications": {}, "is_reserved": False}

    reg = SimpleNamespace(lookup=lk, sources=[src])
    res = run_anchor_readouts(reg, out_dir=tmp_path, eval_env="dev")
    assert res["clean_anchor_fp"]["k"] == 1            # k.root 活体样本
    assert res["scanner_recall"]["recall"] == 1.0
    fp_files = list((tmp_path / "model").glob("anchor-fp-*.json"))
    sr_files = list((tmp_path / "model").glob("scanner-recall-*.json"))
    assert len(fp_files) == 1 and len(sr_files) == 1
    fp = json.loads(fp_files[0].read_text())
    sr = json.loads(sr_files[0].read_text())
    assert fp["kind"] == "clean_anchor_fp" and fp["eval_env"] == "dev"
    assert sr["kind"] == "scanner_recall" and sr["status"] == "ok"
    assert sr["census"]["probes"] or sr["n_probe"] == 0


def test_run_anchor_readouts_missing_csv_explicit_layer(tmp_path):
    """scanner_ranges CSV 缺失 = 显式缺层不报 0(票 #233 验收:零数据=
    显式缺层);读数面照常返回(缺层是数据条件,非操作失败)。"""
    src = SimpleNamespace(name="scanner_ranges",
                          _path=tmp_path / "missing.csv")
    reg = SimpleNamespace(lookup=lambda ip: {"classifications": {}},
                          sources=[src])
    res = run_anchor_readouts(reg, out_dir=tmp_path, eval_env="dev")
    sr = res["scanner_recall"]
    assert sr["status"] == "missing" and sr["recall"] is None
    assert sr["n_probe"] == 0
    # schema 稳定:missing 形状与 ok 形状同键集(census/members 占位),
    # 消费面(月轮腿/报告面)按键取值不 KeyError(缺省不出节纪律)
    assert sr["zero_event_upper_95"] is None and sr["cp95"]["lo"] is None
    assert list((tmp_path / "model").glob("scanner-recall-*.json"))


def test_anchor_readouts_cli_exit_zero(monkeypatch, capsys, tmp_path):
    """CLI 腿:--anchor-readouts 只测量不持门(main 正常 return = rc 0),
    --json stdout = 双读数组合;工件落 model/(anchors/agg-share 报告族
    同形)。"""
    import ipdb._eval.__main__ as M
    csv = tmp_path / "scanner_ranges.csv"
    csv.write_text("162.142.148.0/24,Censys\n")
    reg = SimpleNamespace(
        load_db=lambda: None,
        lookup=lambda ip: {"classifications": {}, "is_reserved": False},
        sources=[SimpleNamespace(name="scanner_ranges", _path=csv)])
    monkeypatch.setattr(M, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(M, "_real_registry", lambda: reg)
    M.main(["--anchor-readouts", "--json"])           # 不 SystemExit
    out = json.loads(capsys.readouterr().out)
    assert out["clean_anchor_fp"]["k"] == 0
    assert out["scanner_recall"]["status"] == "ok"
    kinds = {f.name.split("-20")[0]
             for f in (tmp_path / "model").glob("*.json")}
    assert kinds == {"anchor-fp", "scanner-recall"}
