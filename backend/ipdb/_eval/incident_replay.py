# backend/ipdb/_eval/incident_replay.py
"""事故回放集(ADR 0021 决策5 / #351):五起历史事故固化为机检回放。

每起事故 = 一个合成机制复现夹具(小、自造数据,零外发零网络,不搬
真实 feed 内容;对照 IP 用 TEST-NET 文档段 203.0.113.0/24 合成)+
一条机检断言:当前系统对应防线应抓住该机制。回归保护语义 = 防线若
被改坏(curated 集空/谱系去重拆除/强制放行拆除/版本戳腿拆除),
本模块对应腿读数翻红,质量报告「事故回归」维度可见。

事故清单与出处(provenance 细节见契约表 incident-replay-* 行):
  ① myip_ms 8.8.8.8 误报(2026-10-24,#183/ADR 0008 事故①;评审 P2-1 勘误)
  ② 114DNS 假印证(2026-10-24,cps+ziyadnz 纯 derived 互证,#183)
  ③ cps+ziyadnz 聚合器翻案(2026-10-18,malicious-ip 82.7%/ziyadnz
     44.7% 双翻案——映射推断的「~100% 重叠」被实测排他率推翻)
  ④ peeringdb 429 残局(2026-10-11 demo 机,未加载源任务在队即持
     查询门 503)
  ⑤ reportedip 8.8.8.8 误报(2026-11-15,#347,master 03a76d67 修)

诚实纪律:
- 夹具数据自造(生产事故行只取「机制形状」:IP+指控+单时刻,非原值
  拷贝;对照行全部 203.0.113.x 合成);事故 IP(8.8.8.8/
  114.114.114.114)是防线 curated 集真实成员,必须原样在夹具里才能
  验证防线,与 tests/sources/test_infra_noise_filter.py 同款纪律。
- 已知无门面如实入 known_gap 字段(报告单可见,不发明门):事故②的
  纯 derived 互证 corroborated 语义是 grill Q2 2026-10-11 人裁现状,
  只披露(_eval/agg_share.py)不持门,改语义须另票。
- 腿读数 = {"pass": bool, ...证据明细};runner gate 腿按 pass 持门。
- IP_RADAR_INFRA_NOISE_FILTER 显式关 = 防线被人为关闭,腿红是正确
  信号,不在本模块内强行扳回(不造假绿)。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .._logodds import accuser_pool, assertion_confidence

# 对照合成 IP:TEST-NET-3 文档段(RFC 5737),永非真实指控对象
_CTRL = "203.0.113."

# 事故②/③的纯函数夹具源名:名字即生产注册名(去重按名生效),数值自造
_INDEPENDENT = "binarydefense"          # 非 derived 对照源(r=0.80 自造)


def _chk(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _report(incident: str, mechanism: str, defense: str, checks: list[dict],
            known_gap: str | None = None) -> dict:
    return {"pass": all(c["ok"] for c in checks), "incident": incident,
            "known_gap": known_gap,          # 评审 P2-3:前置防 md 截断
            "mechanism": mechanism, "defense": defense,
            "checks": checks}


# ── 事故①:myip_ms 8.8.8.8 单源误报 ─────────────────────────────────

def replay_myip_ms_8888() -> dict:
    """公共服务解析器被列表源单源指控 → 载入期 infra 排除应消解。

    防线(读码证实):myip_ms.py infra_noise_filter=True(IpListSource
    车道)→ _rebuild_tail.InfraNoiseGate.blocks → _infra_filter.
    is_infra_noise(curated 单址集,真源 _curated_infra.CURATED_CSV,#466 卡
    15 起名单住跨源小模块)。
    """
    from .._sources.myip_ms import MyipMsSource
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # 落盘形状 = download() 安装的归一化产物(parse_raw 输出,裸 IP 行)
        (d / "myip_ms").write_text(f"8.8.8.8\n{_CTRL}21\n", encoding="utf-8")
        s = MyipMsSource(data_dir=d)
        n = s.rebuild()
        checks = [
            _chk("incident_ip_excluded_at_load", n == 1,
                 f"rebuild 键数 {n}(期望 1:8.8.8.8 载入面被排)"),
            _chk("no_accusation_for_incident_ip", not s.query("8.8.8.8"),
                 "查询面 8.8.8.8 无指控证据"),
            _chk("non_infra_accusation_preserved", bool(s.query(f"{_CTRL}21")),
                 "对照合成 IP 指控原样保留(宁少算不扩大)"),
            _chk("raw_file_untouched",
                 "8.8.8.8" in (d / "myip_ms").read_text(encoding="utf-8"),
                 "原始数据文件零改写(证据永不灭失)"),
        ]
    return _report(
        "myip-ms-8888",
        "公共解析器 8.8.8.8 被 myip_ms 单源指控 → 惡意误报(2026-10-24,#183)",
        "infra_noise_filter=True(myip_ms.py)+ _rebuild_tail.InfraNoiseGate"
        " + _infra_filter.curated_infra_addresses(_curated_infra.CURATED_CSV 单真相)",
        checks)


# ── 事故②:114DNS 假印证(cps+ziyadnz 互证) ─────────────────────────

def replay_dns114_false_corroboration() -> dict:
    """两聚合器转载同上游的互证被当独立印证 → 双层防线应抓住。

    载入面:两事故源都 opt-in infra 排除,114.114.114.114 的指控根本
    进不了投影(回声无从形成)。评分面:dedup_lineage 把系数不高于
    最强非 derived 源的聚合器剔掉(派生指控不双计)。
    """
    from .._sources.cps_collected_iocs import CpsCollectedIocsSource
    from .._sources.ziyadnz import ZiyadnzSource
    fs = None                      # first_seen=None → 衰减系数 1.0,纯形状
    pool_alone = accuser_pool([(_INDEPENDENT, 0.80, fs)])
    pool_echo = accuser_pool(
        [(_INDEPENDENT, 0.80, fs),
         ("ziyadnz", 0.55, fs), ("cps_collected_iocs", 0.50, fs)])
    conf_alone = assertion_confidence([c for _, c in pool_alone])
    conf_echo = assertion_confidence([c for _, c in pool_echo])
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "ziyadnz.csv").write_text(
            "ip,type,is_cidr,sources,source_count,category,confidence,"
            "first_seen,last_seen\n"
            "114.114.114.114,ipv4,no,\"RTBH|DROP\",2,spamhaus,50,"
            "2026-10-24,2026-10-24\n"
            f"{_CTRL}23,ipv4,no,\"RTBH\",1,spamhaus,50,"
            "2026-10-24,2026-10-24\n", encoding="utf-8")
        (d / "cps_collected_iocs.txt").write_text(
            f"114.114.114.114\n{_CTRL}24\n", encoding="utf-8")
        zs = ZiyadnzSource(data_dir=d)
        cs = CpsCollectedIocsSource(data_dir=d)
        nz, nc = zs.rebuild(), cs.rebuild()
        checks = [
            _chk("echo_cannot_form_at_load",
                 nz == 1 and nc == 1,
                 f"rebuild 键数 ziyadnz={nz}/cps={nc}(各剩 1 对照键,"
                 "114.114.114.114 双双载入面被排)"),
            _chk("incident_ip_absent_from_both_projections",
                 not zs.query("114.114.114.114")
                 and not cs.query("114.114.114.114"),
                 "两源投影均无 114.114.114.114 指控 → corroborated 无从为真"),
            _chk("scoring_dedup_drops_derived_echo",
                 len(pool_alone) == len(pool_echo) == 1
                 and conf_alone == conf_echo,
                 f"独立票 {len(pool_alone)}→{len(pool_echo)},"
                 f"conf {conf_alone}→{conf_echo}(聚合器派生不双计)"),
            _chk("raw_files_untouched",
                 "114.114.114.114" in (d / "ziyadnz.csv").read_text(
                     encoding="utf-8")
                 and "114.114.114.114" in (d / "cps_collected_iocs.txt")
                 .read_text(encoding="utf-8"),
                 "原始数据文件零改写(证据永不灭失)"),
        ]
    return _report(
        "dns114-false-corroboration",
        "114.114.114.114 被 cps+ziyadnz 互相印证打惡意(2026-10-24,"
        "#183/ADR 0008 事故②)——转载回声被算独立印证",
        "载入面:两源 infra_noise_filter=True(ziyadnz.py/"
        "cps_collected_iocs.py);评分面:_logodds.dedup_lineage"
        "(DERIVED_SOURCES 派生剔除)",
        checks,
        known_gap="纯 derived 组互证仍算 corroborated(grill Q2 2026-10-11 "
        "人裁现状,_merge.py corroborated 判式钉死;无语义门,披露面="
        "_eval/agg_share.py,改语义须另票过回放闸门=改前后同数据重跑比对)")


# ── 事故③:cps+ziyadnz 聚合器翻案(2026-10-18) ──────────────────────

def replay_aggregator_derived_reversal() -> dict:
    """映射推断「聚合器≈纯回声」被实测排他率推翻 → 翻案后的机制防线。

    防线三件:①聚合器运行时入 DERIVED_SOURCES(_registry.
    _apply_derived_sources 按源类 derived=True 灌装,派生不双计由此
    生效);②排他率探针对照闸(对照源池命中不足即 ABORT,不出数字
    ——防假零,2026-10-10 判例);③discover 门表 REJECT 须附实测排他
    数(ops SKILL 治理面,人环节,不可机检,记 provenance)。
    """
    import ipdb._registry  # noqa: F401  # import 即 _apply_derived_sources
    from .. import _logodds
    from . import exclusive as _ex
    derived_now = set(_logodds.DERIVED_SOURCES)
    fs = None
    pool_alone = accuser_pool([(_INDEPENDENT, 0.80, fs)])
    pool_plus = accuser_pool(
        [(_INDEPENDENT, 0.80, fs),
         ("ziyadnz", 0.55, fs), ("cps_collected_iocs", 0.50, fs)])
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "ctrl.txt").write_text(
            "\n".join(f"{_CTRL}{i}" for i in range(1, 21)),
            encoding="utf-8")
        (d / "cand.txt").write_text("203.0.113.99\n", encoding="utf-8")  # 评审 P2-4:统一 TEST-NET-3
        try:
            _ex.run(d / "cand.txt", lambda ip: {"classifications": {}},
                    control_path=d / "ctrl.txt")
            aborted, abort_detail = False, "未 ABORT(出了数字=假零防线拆除)"
        except _ex.ControlAbort:
            aborted, abort_detail = True, "对照闸拒 → 不出排他率数字"
    checks = [
        _chk("aggregators_in_runtime_derived_set",
             {"ziyadnz", "cps_collected_iocs", "malicious_ip"} <= derived_now,
             f"运行时 DERIVED_SOURCES 含双翻案源+malicious_ip"
             f"(共 {len(derived_now)} 员)"),
        _chk("derived_echo_adds_no_independent_vote",
             len(pool_alone) == len(pool_plus) == 1
             and assertion_confidence([c for _, c in pool_alone])
             == assertion_confidence([c for _, c in pool_plus]),
             "聚合器派生指控加入后独立票数与 conf 不变(不双计)"),
        _chk("exclusivity_probe_control_aborts_on_uncovered_pool",
             aborted, abort_detail),
    ]
    return _report(
        "aggregator-derived-reversal",
        "聚合器派生指控被映射推断当独立源计(或被推断当纯回声拒收),"
        "2026-10-18 实测排他率双翻案:malicious-ip 82.7%/ziyadnz 44.7%",
        "_registry._apply_derived_sources(derived=True 灌装)+ _logodds."
        "dedup_lineage + _eval/exclusive.py 对照闸;门表实测律在 ops "
        "discover SKILL(人环节)",
        checks)


# ── 事故④:peeringdb 429 残局(2026-10-11) ──────────────────────────

def replay_peeringdb_429_residue() -> dict:
    """限流残局(未加载源任务在队)持查询门 → 持门必须有界+残局先收敛。

    防线(读码证实):①_coldstart.ColdStartGate.db_ready 的 deadline
    强制放行(窗 1800/1200/900s 按 GB 分档,IP_RADAR_COLD_START_TIMEOUT
    可覆写)——残局在队只会窗内 503,不楔死;②main._catchup_footprint
    缺失=0 排最前(bbae574e 修):0 文件残局源先收敛,覆盖门早清。
    """
    from .._coldstart import REASON_WARMING, ColdStartGate

    class _Clock:
        def __init__(self):
            self.t = 1000.0

        def __call__(self):
            return self.t

    class _Src:
        """最小 registry source 形状:name + health().loaded。"""

        def __init__(self, name, loaded):
            self.name = name
            self.loaded = loaded

        def health(self):
            return self

    clock = _Clock()
    residue = "residue_429"                     # 0 文件、任务卡在队的合成残局源
    gate = ColdStartGate(
        now=clock,
        tasks_active=lambda f=None: f is None or f(residue),
        db_loaded=lambda: True,
        enabled_sources=lambda: [_Src("big1", True), _Src(residue, False)],
        compute_window_sec=lambda: 600)
    held = not gate.db_ready()
    reason = gate.blocking_reason()
    clock.t += 601                              # 越过窗(残局仍在队)
    released = gate.db_ready()

    import main as _main                        # 契约 runner 进程 cwd=backend
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "big.csv").write_bytes(b"x" * 100)
        big = type("BigSrc", (), {"_path": str(d / "big.csv")})()
        missing = type("MissingSrc", (), {"_path": str(d / "none.csv")})()
        ordered = sorted([big, missing], key=_main._catchup_footprint)
        missing_first = ordered[0] is missing
        zero_for_missing = _main._catchup_footprint(missing) == 0
    checks = [
        _chk("residue_task_holds_gate_in_window", held,
             "残局任务在队 → db_ready=False(503 warming;窗内持门是"
             "设计:不出半份净白判定)"),
        _chk("blocking_reason_is_warming", reason == REASON_WARMING,
             f"blocking_reason={reason!r}(跨栈契约字面)"),
        _chk("deadline_force_releases_past_window", released,
             "越窗强制放行——残局不楔死查询(超时即放行)"),
        _chk("catchup_orders_missing_source_first",
             missing_first and zero_for_missing,
             "补账排序缺失源足迹=0 最前(残局源先收敛,覆盖门早清)"),
    ]
    return _report(
        "peeringdb-429-residue",
        "peeringdb 429 限流后 0 文件,任务在队即持查询门 503(2026-10-11 "
        "demo 机实测,bbae574e 整改)",
        "_coldstart.ColdStartGate.db_ready(deadline 强制放行)+ main.py "
        "_catchup_footprint(缺失=0 最先入队)",
        checks)


# ── 事故⑤:reportedip 8.8.8.8(#347,2026-11-15) ────────────────────

def replay_reportedip_8888() -> dict:
    """harvest 车道单时刻单源指控公共解析器 → 接线+版本戳双防线。

    防线(读码证实):①reportedip.py infra_noise_filter=True(Source/
    harvest 车道 InfraNoiseGate,_source_base 接线);②HARVEST_REV=2
    (_lmdb.py,#347 bump):.rev 版本戳 ≠ 当前代码代 → needs_convert
    True → 存量族一次迁移重建,新过滤必然到达既有部署(治「代码演进
    不 bump mtime 的静默休眠」,ADR 0009)。
    """
    from .._sources import _lmdb as _lmdb_mod
    from .._sources.reportedip import ReportedIPSource
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        raw = d / "reportedip.csv"
        # 机制形状=单时刻单源无印证(codes "15;21" 双码同归组),数值自造
        raw.write_text(
            "ip,confidence,categories,last_reported\n"
            '8.8.8.8,77,"15;21","2026-11-13 16:15:58"\n'
            f'{_CTRL}25,77,"15","2026-11-13 16:16:00"\n', encoding="utf-8")
        s = ReportedIPSource(data_dir=d)
        n = s.rebuild()
        base = s._lmdb_base
        rev_now = _lmdb_mod.rev_path(base).read_text(encoding="utf-8").strip()
        _lmdb_mod.rev_path(base).write_text("1", encoding="utf-8")
        stale_forces = _lmdb_mod.needs_convert(raw, base)
        checks = [
            _chk("harvest_lane_excludes_incident_ip", n == 1,
                 f"rebuild 键数 {n}(8.8.8.8 载入面被排)"),
            _chk("no_accusation_for_incident_ip", not s.query("8.8.8.8"),
                 "查询面 8.8.8.8 无指控证据"),
            _chk("non_infra_accusation_preserved", bool(s.query(f"{_CTRL}25")),
                 "对照合成 IP 指控原样保留"),
            _chk("raw_file_untouched",
                 "8.8.8.8" in raw.read_text(encoding="utf-8"),
                 "原始数据文件零改写"),
            _chk("rev_sidecar_matches_current_harvest_rev",
                 rev_now == str(_lmdb_mod.HARVEST_REV),
                 f".rev={rev_now!r} == HARVEST_REV("
                 f"{_lmdb_mod.HARVEST_REV})(#347 bump 到达本族)"),
            _chk("stale_rev_forces_rematerialization", stale_forces,
                 ".rev=1(旧代)→ needs_convert=True:存量族迁移重建,"
                 "新过滤必然到达既有部署"),
        ]
    return _report(
        "reportedip-8888",
        "reportedip 单源单时刻指控 8.8.8.8 → verdict=malicious conf=65"
        "(2026-11-13 观测,2026-11-15 #347 人裁误报,master 03a76d67 修)",
        "reportedip.py infra_noise_filter=True(harvest 车道)+ _lmdb.py "
        "HARVEST_REV=2(#347 bump,.rev 腿强制迁移重建)",
        checks)
