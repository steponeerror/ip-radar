# backend/tests/eval/test_eval_truth_v2_readout.py
"""真值语料 v2 附录读数腿测试(ADR 0017 §4 / issue #261 T2)。

全部离线:语料件直接合成出版(过闸装配是 T1 构建器的事,本腿只消费
出版件/哨兵件);registry 用假 lookup。验收线(issue #261):零持门
三重(无 gating exit 码 / 不进回归族 / 缺件与哨兵态 N/A 不炸不编)+
附录读数与主判定分离(删语料件,主判定读数输出字节不变)。
"""
import json
from pathlib import Path

import pytest

from ipdb._eval.anchors import run_anchors
from ipdb._eval.assets import AssetMeta, fingerprint, save_asset
from ipdb._eval.truth_v2_readout import (
    render_truth_v2_appendix,
    run_truth_v2_readout,
    truth_v2_corpus_readout,
)


@pytest.fixture(autouse=True)
def _pin_env(monkeypatch):
    """T2 评审 P2-1 flake 修:本文件多数测试不经 CLI 直调装配函数,"
    "函数内懒 import __main__ 时才解析 env(import 期 REPORT_DIR 快照)"
    "——ambient IP_RADAR_EVAL_ENV 非法(如空串, 跑过月轮命令的 shell 常"
    "见)时 import 期就 raise, 测试假红。autouse 钉 env(先于函数体内"
    "import 生效), 测试对 shell 环境零依赖。"""
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    monkeypatch.delenv("IP_RADAR_EVAL_DIR", raising=False)

# ── fixtures ─────────────────────────────────────────────────


class _FakeAccuser:
    """蜜罐方法学源(属性旗标即 layered_readout 的排除依据)。"""
    honeypot_methodology = True

    def __init__(self, name):
        self.name = name


class _FakePlain:
    honeypot_methodology = False

    def __init__(self, name):
        self.name = name


class _FakeRegistry:
    """lookup: accusers 表逐 IP 给指控载荷(组级 verdict=malicious,
    layered._accusing_sources 同消费口径);记录 asof 透传。"""

    def __init__(self, accusers: dict[str, list[str]]):
        self.accusers = accusers
        self.sources = [_FakePlain("s1"), _FakePlain("s2"), _FakeAccuser("hp")]
        self.asof_seen = []

    def load_db(self):                     # CLI 面注册表契约(no-op, 离线)
        pass

    def lookup(self, ip, asof=None):
        if asof is not None:
            self.asof_seen.append(asof)
        srcs = self.accusers.get(ip, [])
        if not srcs:
            return {"ip": ip, "classifications": {}}
        return {"ip": ip, "classifications": {"bruteforce": {
            "type": "bruteforce", "verdict": "malicious",
            "verdict_conflict": False, "confidence": 50,
            "details": [{"source": s, "verdict": "malicious"}
                        for s in srcs]}}}


_MEMBERS = ["203.0.113.10", "203.0.113.11", "203.0.113.12",
            "203.0.113.13", "203.0.113.14", "203.0.113.15"]
# A=s1+s2, B=s1+s2+hp, C=s1(独证), D=hp(独证), E=无人, F=s2(独证)
_ACCUSERS = {
    "203.0.113.10": ["s1", "s2"],
    "203.0.113.11": ["s1", "s2", "hp"],
    "203.0.113.12": ["s1"],
    "203.0.113.13": ["hp"],
    "203.0.113.15": ["s2"],
}


def _publish_corpus(out_dir: Path, members=_MEMBERS, version="truthv2-202610"):
    """合成出版 v2 语料件(T1 出版三件的最小面: 本腿只读 ips+meta)。"""
    d = out_dir / "truth-v2" / version
    save_asset(d, members, AssetMeta(
        version=version, kind="truth_v2", fingerprint=fingerprint(members),
        member_count=len(members),
        params={"window_start": "2026-08-04", "window_end": "2026-10-31",
                "window_days": 90},
        eval_env="monthly", created_at="2026-10-31"))
    return d


def _write_sentinel(out_dir: Path, version="truthv2-202610"):
    """合成组件闸哨兵件(T1 status.json 形状的最小面)。"""
    d = out_dir / "truth-v2" / version
    d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({
        "kind": "truth_v2_status", "status": "insufficient",
        "version": version, "eval_env": "monthly",
        "window": {"start": "2026-08-04", "end": "2026-10-31", "days": 90},
        "min_component_ips": 1000,
        "components": {"smallbox": {"member_count": 999,
                                    "gate_passed": False}},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


# ── 1. 出版件读数: θ̂ 试算 + 独有指控 + 全池无指控 ────────────────


def test_published_readout_theta_unique_blindspot(tmp_path):
    out = tmp_path / "out"
    _publish_corpus(out)
    res = run_truth_v2_readout(_FakeRegistry(_ACCUSERS), out_dir=out)
    assert res["status"] == "published"
    assert res["corpus"]["version"] == "truthv2-202610"
    assert res["corpus"]["fingerprint"] == fingerprint(_MEMBERS)
    r = res["readout"]
    assert r["n_members"] == 6 and r["hits"] == 5     # E 无人指控
    assert r["rate"] == pytest.approx(5 / 6)
    # k_all: {0:1(E), 1:3(C/D/F), 2:1(A), 3:1(B)}
    assert r["k_all_hist"] == {"0": 1, "1": 3, "2": 1, "3": 1}
    # k_nonhoneypot(剔 hp): A=2, B=2, C=1, D=0, E=0, F=1
    assert r["k_nonhoneypot_hist"] == {"0": 2, "1": 2, "2": 2}
    assert "hp" in r["honeypot_excluded"]        # 源属性入集 + config 兜底
    # θ̂ 试算: n=指控成员数, k=其中还有他源也指控的; Beta(1,1) 后验均值
    ps = {row["source"]: row for row in r["per_source"]}
    assert ps["s1"] == {"source": "s1", "n": 3, "k": 2,
                        "theta_hat": pytest.approx(3 / 5), "solo": 1}
    assert ps["s2"] == {"source": "s2", "n": 3, "k": 2,
                        "theta_hat": pytest.approx(3 / 5), "solo": 1}
    assert ps["hp"] == {"source": "hp", "n": 2, "k": 1,
                        "theta_hat": pytest.approx(1 / 2), "solo": 1}
    # 池级 θ̂ = (印证≥2 的成员数 + 1) / (命中≥1 的成员数 + 2)
    assert r["theta_hat_pool"] == {
        "n_hits": 5, "n_corroborated": 2,
        "value": pytest.approx(3 / 7)}
    # 独有指控核查: k_all==1 成员归因到唯一指控源;全池无指控成员留证
    assert r["unique_accusations"] == [
        {"ip": "203.0.113.12", "source": "s1"},
        {"ip": "203.0.113.13", "source": "hp"},
        {"ip": "203.0.113.15", "source": "s2"}]
    assert r["blind_spots"] == ["203.0.113.14"]
    # 工件恒落 model/(run_readout 读最新件嵌月报附录)
    arts = list((out / "model").glob("truth-v2-readout-*.json"))
    assert len(arts) == 1
    assert json.loads(arts[0].read_text())["status"] == "published"


def test_corpus_readout_asof_anchored_to_created_at(tmp_path):
    """asof 锚 = 语料 created_at(数据派生日), 同 layered truth 层 T10 律:
    读数可对齐语料时点, 不随引擎现态漂移。"""
    reg = _FakeRegistry(_ACCUSERS)
    truth_v2_corpus_readout(
        reg.lookup, _MEMBERS, sources=reg.sources,
        asof=1779999999.0)
    assert reg.asof_seen and reg.asof_seen[0] == 1779999999.0


def test_pure_readout_function_no_hits_no_fake_theta():
    """零命中(全池无指控)→ 池级 θ̂ None: 无证据≠0.5, 无话不虚构。"""
    reg = _FakeRegistry({})                     # 全部成员无人指控
    r = truth_v2_corpus_readout(reg.lookup, _MEMBERS, sources=reg.sources)
    assert r["hits"] == 0
    assert r["theta_hat_pool"]["value"] is None
    assert r["per_source"] == []                # 无指控源不入表


# ── 2. 渲染: 附录节(出版/N/A 哨兵三分立) ─────────────────────


def test_render_published_appendix_lines(tmp_path):
    out = tmp_path / "out"
    _publish_corpus(out)
    res = run_truth_v2_readout(_FakeRegistry(_ACCUSERS), out_dir=out)
    lines = render_truth_v2_appendix(res)
    text = "\n".join(lines)
    assert lines[0].startswith("## 附录") and "只观测不持门" in lines[0]
    assert "truthv2-202610" in text and fingerprint(_MEMBERS) in text
    assert "Hornet" in text                       # 主判定权仍归 Hornet(ADR 0017 §4)
    assert "5/6" in text and "θ̂" in text          # 命中读数 + 试算口径在场
    assert "s1" in text and "独证" in text and "无指控" in text
    assert "蜜罐" in text                         # k 双报沿用(ADR 0017 §8)


def test_render_sentinel_na_three_distinct_causes(tmp_path):
    """三种缺读数成因各有显式措辞, 读者可区分「没件」「没语料」「没过闸」。"""
    # ① 无 truth-v2-readout 工件(readout 腿装配面)
    assert "N/A" in "\n".join(render_truth_v2_appendix(None))
    assert "无 truth-v2-readout 工件" in "\n".join(render_truth_v2_appendix(None))
    # ② 语料根缺席(构建器从未跑过)
    out = tmp_path / "out"
    res = run_truth_v2_readout(_FakeRegistry(_ACCUSERS), out_dir=out)
    assert res["status"] == "no-corpus"
    t2 = "\n".join(render_truth_v2_appendix(res))
    assert "N/A" in t2 and "--truth-v2" in t2
    # ③ 组件闸哨兵态(999/1000): 引用哨兵件自己的事实, 不虚构读数
    _write_sentinel(out)
    res = run_truth_v2_readout(_FakeRegistry(_ACCUSERS), out_dir=out)
    assert res["status"] == "insufficient"
    t3 = "\n".join(render_truth_v2_appendix(res))
    assert "N/A" in t3 and "999" in t3 and "1000" in t3
    assert "2026-08-04" in t3                    # 哨兵窗界照引
    assert "Hornet" in t3


def test_render_appends_sentinel_version_boundary(tmp_path):
    """哨兵版目录与更新出版版并存 → 读最新版(月度重切后旧哨兵不再遮新语料)。"""
    out = tmp_path / "out"
    _write_sentinel(out, version="truthv2-202609")
    _publish_corpus(out, version="truthv2-202610")
    res = run_truth_v2_readout(_FakeRegistry(_ACCUSERS), out_dir=out)
    assert res["status"] == "published"
    assert res["corpus"]["version"] == "truthv2-202610"


# ── 3. 零持门: 缺件/哨兵态 rc=0;坏语料件照炸(不装假零) ──────────


def test_cli_missing_and_sentinel_rc_zero(tmp_path, monkeypatch, capsys):
    """缺语料件与哨兵态都不许有 gating exit 码(main 正常返回=rc 0);
    工件照写(腿红不持门、工件照写的观测腿律)。"""
    import ipdb._eval.__main__ as M
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "rep"))
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)
    monkeypatch.setattr(M, "_real_registry",
                        lambda: _FakeRegistry(_ACCUSERS))
    # 缺件: 正常返回(无 SystemExit)
    M.main(["--truth-v2-readout"])
    out1 = capsys.readouterr().out
    assert "no-corpus" in out1 and "只观测不持门" in out1
    art1 = list((tmp_path / "rep" / "dev" / "model")
                .glob("truth-v2-readout-*.json"))
    assert len(art1) == 1                         # 缺件也有工件(读数留痕)
    assert json.loads(art1[0].read_text())["status"] == "no-corpus"
    # 哨兵态: 同律 rc 0
    _write_sentinel(tmp_path / "rep" / "dev")
    M.main(["--truth-v2-readout"])
    assert "insufficient" in capsys.readouterr().out
    # 出版: 同律 rc 0
    _publish_corpus(tmp_path / "rep" / "dev")
    M.main(["--truth-v2-readout"])
    out3 = capsys.readouterr().out
    assert "published" in out3 and "θ̂" in out3
    arts = sorted((tmp_path / "rep" / "dev" / "model")
                  .glob("truth-v2-readout-*.json"))
    # 同秒重跑同名覆盖(agg-share/anchors 同族秒级 ts 惯例), 只验终态件
    assert arts and json.loads(arts[-1].read_text())["status"] == "published"


def test_corrupt_published_corpus_fails_loud(tmp_path):
    """出版件被篡改 → load_asset 指纹闸炸(assets 惯例): 坏件≠缺件,
    静默 N/A = 证据灭失。上抛即本腿对坏件的全部立场(假零判例)。"""
    out = tmp_path / "out"
    d = _publish_corpus(out)
    (d / "ips.txt").write_text("203.0.113.99\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        run_truth_v2_readout(_FakeRegistry(_ACCUSERS), out_dir=out)


# ── 4. 附录读数与主判定分离(负例: 删语料件, 主判定字节不变) ────────


def test_anchors_regression_unaffected_by_corpus_presence(tmp_path):
    """不进回归族(行为面): 判定门 --anchors 的纯计算 run_anchors 在
    语料件在场/删除两态下逐字节同值。"""
    out = tmp_path / "out"
    _publish_corpus(out)
    reg = _FakeRegistry(_ACCUSERS)
    with_corpus = run_anchors(reg.lookup)
    import shutil
    shutil.rmtree(out / "truth-v2")
    without = run_anchors(reg.lookup)
    assert with_corpus == without


def test_main_readout_md_bytes_unchanged_by_corpus_deletion(tmp_path):
    """主判定读数输出字节不变(负例验收线): run_readout 只读附录工件、
    永不读 truth-v2 语料件 → 删语料件前后月报逐字节相等。"""
    from test_eval_readout_cli import _FakeRegistry, _build_sources
    from ipdb._eval.__main__ import run_readout
    root = tmp_path
    reg = _FakeRegistry(_build_sources(root))
    _publish_corpus(root / "rep1")
    _publish_corpus(root / "rep2")
    # 两报告目录各先跑附录腿(月轮真实序: 腿先于 readout)
    run_truth_v2_readout(reg, out_dir=root / "rep1")
    run_truth_v2_readout(reg, out_dir=root / "rep2")
    md1, _, _ = run_readout(reg, root / "rep1", assets_dir=root / "assets",
                            keysets_dir=root / "keysets",
                            run_seed=1, run_id="r1")
    # 删除语料件后主判定再跑: 附录工件仍在(腿的读数已留证),
    # run_readout 输出必须字节不变
    import shutil
    shutil.rmtree(root / "rep2" / "truth-v2")
    md2, _, _ = run_readout(reg, root / "rep2", assets_dir=root / "assets",
                            keysets_dir=root / "keysets",
                            run_seed=1, run_id="r1")
    assert md1.read_bytes() == md2.read_bytes()
    text = md1.read_text()
    assert "## 附录" in text and "truthv2-202610" in text   # 附录节真嵌上了


def test_appendix_section_isolated_from_main_verdict_sections(tmp_path):
    """附录读数与主判定分离(结构面): 无附录工件时附录节渲染 N/A,
    且月报主判定部分(附录节之前的全部内容)与有工件时逐字节相同。"""
    from test_eval_readout_cli import _FakeRegistry, _build_sources
    from ipdb._eval.__main__ import run_readout
    root = tmp_path
    reg = _FakeRegistry(_build_sources(root))
    _publish_corpus(root / "rep1")
    run_truth_v2_readout(reg, out_dir=root / "rep1")
    md_with, _, _ = run_readout(reg, root / "rep1",
                                assets_dir=root / "assets",
                                keysets_dir=root / "keysets",
                                run_seed=1, run_id="r1")
    md_without, _, _ = run_readout(reg, root / "rep2",
                                   assets_dir=root / "assets",
                                   keysets_dir=root / "keysets",
                                   run_seed=1, run_id="r1")
    with_text, without_text = md_with.read_text(), md_without.read_text()
    header = next(l for l in with_text.splitlines() if l.startswith("## 附录"))
    # 主判定部分(附录节前)逐字节相同 —— 附录只长在附录节
    assert with_text.split(header)[0] == without_text.split(header)[0]
    assert "truthv2-202610" in with_text
    assert "N/A" in without_text and "无 truth-v2-readout 工件" in without_text


# ── 5. T2 评审 P2-3/P2-5 顺手修(#261 评论末段, #262 T3 承修) ────


def test_k_hist_keys_numeric_order():
    """P2-3: k 直方图键按数值序(非字符串字典序)——"2" 排在 "10" 前
    (layered int 键同口径;渲染与工件可读性)。"""
    # 两个成员: 一个 12 源同指控(k=12), 一个 2 源(k=2) → 键序 ["2","12"]
    accusers = {"203.0.113.10": [f"src{i}" for i in range(12)],
                "203.0.113.11": ["s1", "s2"]}
    r = truth_v2_corpus_readout(_FakeRegistry(accusers).lookup,
                                ["203.0.113.10", "203.0.113.11"],
                                sources=[])
    assert list(r["k_all_hist"]) == ["2", "12"]
    assert list(r["k_nonhoneypot_hist"]) == ["2", "12"]
    # 渲染同行数值序
    assert _fmt_hist_public(r["k_all_hist"]) == "2:1, 12:1"


def _fmt_hist_public(h):
    from ipdb._eval.truth_v2_readout import _fmt_hist
    return _fmt_hist(h)


def test_theta_hat_derived_only_disclosure():
    """P2-5: θ̂/k 印证不剔声明派生簇 —— 派生簇内互证仍计入 k, 计数
    单列披露(derived_only_corroboration, layered F6 同款判定);附录
    渲染带披露行(T3 对照读数喂换卷人裁, 依据行须可同读)。"""
    from ipdb._eval import config
    a, b = sorted(config.LINEAGE_CLUSTERS)[:2]     # 声明派生簇内两源
    accusers = {
        "203.0.113.10": [a, b],        # 全属声明派生簇 → 派生簇独证
        "203.0.113.11": ["s1", "s2"],  # 独立源互证 → 不计
        "203.0.113.12": [a, "s1"],     # 混合(不全属派生簇)→ 不计
    }
    r = truth_v2_corpus_readout(_FakeRegistry(accusers).lookup,
                                ["203.0.113.10", "203.0.113.11",
                                 "203.0.113.12"], sources=[])
    assert r["derived_only_corroboration"] == 1
    # θ̂ 不折减: 派生簇内互证照样计入 k(n=2, k=2)
    ps = {row["source"]: row for row in r["per_source"]}
    assert ps[a]["k"] == 2 and ps[a]["theta_hat"] == pytest.approx(3 / 4)
    lines = "\n".join(render_truth_v2_appendix({
        "status": "published",
        "corpus": {"version": "truthv2-202610",
                   "fingerprint": fingerprint(_MEMBERS),
                   "member_count": 3,
                   "window": {"window_start": "2026-08-04",
                              "window_end": "2026-10-31",
                              "window_days": 90}},
        "readout": r, "artifact": "/tmp/x.json"}))
    assert "派生簇独证 1 个" in lines
    assert "不剔派生簇" in lines
