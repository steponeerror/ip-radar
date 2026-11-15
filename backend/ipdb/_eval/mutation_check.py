# backend/ipdb/_eval/mutation_check.py
"""变异自检(ADR 0021 决策6 / #352):月度往隔离沙箱种合成缺陷,验证
保底轨门真的会红(防「门静默漏放行」,#183 时代已知答案门死件教训)。

与 #351 事故回放集的分工(ADR 0021 Consequences:回放=历史回归面,
变异=前向自检面,两者都只验门不验数据):
- 回放集(#351)验**数据面防线**:合成夹具复现事故机制,断言防线抓住
  ——测「门该拦的拦没拦」。
- 本模块验**门本身活着**:往沙箱种缺陷 → 跑门 → 门不红 = survived =
  漏放行 finding(人裁,绝不自动改门)。经典变异测试形状(Jia & Harman
  2011 survey):种缺陷 → 跑套 → 杀不掉 = 存活 = 盲区。

注入清单(起步两类,票面已裁;#351 合成夹具手法同源):
  ① 假坏源 ×3
     - key-collapse     键数坍塌(文件截断,字节同步塌缩)
     - accuses-anchor   格式合法内容坏:裸 IP 列表指控净锚 8.8.8.8
     - field-malformed  字段错形:CSV 数值列类型坏,部分行静默丢弃
  ② 错误合并 ×1
     - echo-on-anchor   独立源+派生聚合器双指控净锚(回声未被谱系
       去重即计入独立印证的历史事故②形状)

被测面 = 门判定核原样执行:anchors.run_anchors/_check(锚巡检月轮
判定门核)、mirror_check.check_against_previous(S7 塌缩闸核)。
沙箱 lookup 适配层与差分读数是**夹具约定**(非被测面),诚实纪律:
- 生产 merge 管线(model.py 合并层哑化指控)与绝对阈值接线(failures==0 面)
  不在本被测面内(评审 P2-3):前者由月度生产跑兜底,后者由契约
  fp-restraint-anchors 腿(#349)验 CLI rc 接线
- 适配层只做 source.query → 锚门消费形状的最小映射
  (classifications.{verdict,details}/is_reserved 短路由真模块
  _reserved.is_reserved_addr/attributes={});沙箱宇宙无 tor/hosting
  属性源,健康基线自带这两族锚的夹具性失败——锚门读数 = **差分红**
  (缺陷引入的新失败),绝对红在夹具宇宙恒真无判别力。
- 每变异体建 healthy/mutated 孪生沙箱(成对消夹具噪声,同会话成对
  唯一可信判例);镜像门以 healthy 重build后 manifest 为基线
  (monthly S7 同形:上一轮基线 vs 本轮数据面)。
- 门无读数如实显形(c2 幂等=一次性脚本前提过期;golden 对拍=ops JS
  面,后端注入 runner 不可执行其数据面),不虚构。
- 全部沙箱态在 tempfile.TemporaryDirectory,**种完即清**,永不触
  生产/主检出;零网络;填充 IP 用 RFC 5737 三文档段合成(192.0.2./
  198.51.100./203.0.113.),净锚 8.8.8.8 原样用是被测门(已知答案
  集)的真实成员,#351 同纪律。
- TODO(#352 票尾,人裁后接):月度排程接线(monthly_eval.sh 步 +
  RETRO 检查单提醒行)未做,本模块现由契约 runner func 腿按需执行。

survived 处置红线:开 finding 票人裁,绝不自动改门。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from . import anchors as _anchors
from . import mirror_check

# RFC 5737 文档段前缀(填充合成 IP,非对照对象;762 上限)
_DOC_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.")
_N_IPSUM = 700                     # 填充行数:截断后字节降幅须稳超 S7 的 20% 阈(评审 P2-1:500 时余量 ~6pp 偏薄,700 拉宽页粒度稀释余量)
_N_BD = 200

# 无读数门(票面已知):理由与契约表 consistency-c2-idempotent 行同口径
_C2_NO_READING = (
    "现行载体 = scripts/c2_predicate_gates.py 一次性脚本(#192 时代):"
    "写路径(cp -a 主检出数据面 + rebuild)+ 硬编码绝对路径,不可作沙箱"
    "只读注入面;前提过期(票尾已知)→ 本轮无读数,常驻化待人裁")
_GOLDEN_NO_READING = (
    "golden 对拍门 = ops/agent JS 面(run-golden.mjs,字节等价基线):需 "
    "ops 运行时(gitignored node_modules)与 ops 轮工件,后端 Python 注入"
    " runner 无法在隔离沙箱执行其数据面 → 本轮无读数,跨栈接线待人裁")

GATES_NO_READING = (
    {"gate": "c2-idempotent", "reason": _C2_NO_READING},
    {"gate": "golden-diff", "reason": _GOLDEN_NO_READING},
)


def _doc_ips(n: int) -> list[str]:
    """RFC 5737 三文档段惰性合成 n 个 IPv4(夹具填充,非对照)。"""
    out: list[str] = []
    for p in _DOC_PREFIXES:
        for i in range(1, 255):
            if len(out) >= n:
                return out
            out.append(f"{p}{i}")
    raise ValueError(f"文档段合成 IP 上限 762,请求 {n}")


def _build_universe(d: Path, *, ipsum_rows: list[str],
                    bd_lines: list[str]) -> list:
    """沙箱宇宙:两真实源类(ipsum 派生聚合器 + binarydefense 独立列表,
    均无 infra_noise_filter——缺陷须能到达门面,过滤车道是 #351 回放面)。
    落 raw → 实例化 → rebuild(提交 LMDB 家族 sidecar,manifest 真实形)。
    """
    from .._sources.binarydefense import BinaryDefenseSource
    from .._sources.ipsum import IPsumSource

    d.mkdir(parents=True, exist_ok=True)
    (d / "ipsum.txt").write_text("\n".join(ipsum_rows) + "\n",
                                 encoding="utf-8")
    (d / "binarydefense_banlist.txt").write_text(
        "\n".join(bd_lines) + "\n", encoding="utf-8")
    srcs = [IPsumSource(data_dir=d), BinaryDefenseSource(data_dir=d)]
    counts = {s.name: s.rebuild() for s in srcs}
    return srcs, counts


# ── 沙箱 lookup 适配层(夹具,非被测面;形状 = 锚门消费面)────────────

def _sandbox_lookup(sources):
    from .._reserved import is_reserved_addr
    import ipaddress

    def lookup(ip: str) -> dict:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return {"classifications": {}, "is_reserved": False,
                    "attributes": {}}
        if addr.version == 4 and is_reserved_addr(addr):
            return {"classifications": {}, "is_reserved": True,
                    "attributes": {}}
        classifications: dict = {}
        for s in sources:
            raw = s.query(ip)
            if not raw:
                continue
            for item in (raw if isinstance(raw, list) else [raw]):
                ctype = item.get("classification_type")
                if not ctype:
                    continue
                ca = classifications.setdefault(
                    ctype, {"verdict": item.get("verdict"), "details": []})
                ca["details"].append({
                    "source": s.name,
                    "verdict": item.get("verdict"),
                    "reliability": item.get("reliability")})
        return {"classifications": classifications, "is_reserved": False,
                "attributes": {}}

    return lookup


# ── 门(判定核原样执行;沙箱读数约定见模块 docstring)─────────────────

def _gate_anchors(state: dict) -> tuple[bool, str]:
    """锚巡检门:差分红 = 缺陷引入的新锚失败(夹具宇宙噪声成对消除)。"""
    def fails(sources):
        return {(f["ip"], f["expect"], f["reason"])
                for f in _anchors.run_anchors(_sandbox_lookup(sources))}

    base = fails(state["healthy"]["sources"])
    cur = fails(state["mutated"]["sources"])
    new = cur - base
    joined = "; ".join(f"{ip}({exp}): {why}" for ip, exp, why in sorted(new))
    detail = f"Δfailures={joined}" if joined else "无新失败(与健康基线同)"
    return bool(new), detail


def _gate_mirror_s7(state: dict) -> tuple[bool, str]:
    """镜像 manifest S7 塌缩闸:healthy 重build后 manifest 为基线,突变面
    files/bytes 骤降 >20% = 红。"""
    r = mirror_check.check_against_previous(
        state["mutated"]["dir"], state["manifest_baseline"])
    return (not r["ok"]), r["detail"]


RUNNABLE_GATES = {"anchors": _gate_anchors, "mirror-s7": _gate_mirror_s7}


# ── 变异体模板(每体 = 模板函数,产出孪生沙箱态)──────────────────────

def _state(mid: str, defect: str, mechanism: str, expected_red: dict,
           td: Path, subdir: str, healthy_rows, mutated_rows,
           finding: str | None = None) -> dict:
    """通用孪生态构建:healthy/mutated 两宇宙 + 基线 manifest。"""
    h_dir = td / subdir / "healthy"
    m_dir = td / subdir / "mutated"
    h_srcs, h_counts = _build_universe(h_dir, **healthy_rows)
    baseline = mirror_check.manifest(h_dir)
    m_srcs, m_counts = _build_universe(m_dir, **mutated_rows)
    return {"id": mid, "defect": defect, "mechanism": mechanism,
            "expected_red": expected_red, "finding": finding,
            "healthy": {"dir": h_dir, "sources": h_srcs,
                        "counts": h_counts},
            "mutated": {"dir": m_dir, "sources": m_srcs,
                        "counts": m_counts},
            "manifest_baseline": baseline}


def _mut_key_collapse(td: Path) -> dict:
    """①假坏源·键数坍塌(文件截断形):ipsum raw 500 行截到 10 行,
    字节同步塌缩 → S7 塌缩闸宪章内应红;锚门宪章=误报克制,坍塌非
    误报,应绿(不越权)。"""
    ips = _doc_ips(_N_IPSUM)
    bd = _doc_ips(_N_BD)
    return _state(
        "fake-source-key-collapse", "假坏源①",
        "源文件截断:ipsum 500 行→10 行(rebuild 键同步坍塌),"
        "数据面字节骤降>20% → S7 镜像塌缩闸应红",
        {"mirror-s7": True}, td, "key-collapse",
        healthy_rows={"ipsum_rows": [f"{ip}\t5" for ip in ips],
                      "bd_lines": bd},
        mutated_rows={"ipsum_rows": [f"{ip}\t5" for ip in ips[:10]],
                      "bd_lines": bd})


def _mut_accuses_anchor(td: Path) -> dict:
    """①假坏源·内容坏(格式合法):binarydefense 裸 IP 列表一行换成净锚
    8.8.8.8(无 infra 过滤车道,缺陷可达门面;#183 事故形态)→ 锚门应红;
    字节近恒定 → S7 应绿。"""
    ips = _doc_ips(_N_IPSUM)
    bd = _doc_ips(_N_BD)
    bad_bd = ["8.8.8.8", *bd[1:]]
    return _state(
        "fake-source-accuses-clean-anchor", "假坏源①",
        "格式合法内容坏:裸 IP 列表(binarydefense 车道)混入净锚 "
        "8.8.8.8 指控,载入面无 infra 过滤可拦 → 锚巡检门应红",
        {"anchors": True}, td, "accuses-anchor",
        healthy_rows={"ipsum_rows": [f"{ip}\t5" for ip in ips],
                      "bd_lines": bd},
        mutated_rows={"ipsum_rows": [f"{ip}\t5" for ip in ips],
                      "bd_lines": bad_bd})


def _mut_field_malformed(td: Path) -> dict:
    """①假坏源·字段错形(部分行坏,字节面净变低于阈):ipsum 计数列
    int→'many',parse_row 逐行弃 → rebuild 提交 _N_IPSUM→40% 键(700→280);
    字节面净变远低于 S7 的 20% 阈(LMDB data.mdb 8KB 页粒度收缩,被原始件
    增字节部分抵消),且生产面单源坍塌占总字节份额更小更不可见。宪章捕获者
    =阳性锚召回(#350 未建);全量错形(→0 键)另有载入层零记录守卫
    响亮拒提交(_lmdb.py rebuild_lmdb,实测 RuntimeError keeping old
    epoch),非静默。今日诚实读数:全部可跑门绿 = survived。"""
    ips = _doc_ips(_N_IPSUM)
    bd = _doc_ips(_N_BD)
    malformed = [f"{ip}\tmany" if i % 5 >= 2 else f"{ip}\t5"
                 for i, ip in enumerate(ips)]
    return _state(
        "fake-source-field-malformed", "假坏源①",
        "字段错形:CSV 计数列类型坏(int→'many'),60% 行静默丢弃,"
        "键 500→200 而字节面净变 -7.9% < 20% 阈(data.mdb 8KB 页粒度"
        "收缩被原始件增字节部分抵消)",
        {}, td, "field-malformed",
        healthy_rows={"ipsum_rows": [f"{ip}\t5" for ip in ips],
                      "bd_lines": bd},
        mutated_rows={"ipsum_rows": malformed, "bd_lines": bd},
        finding="字段错形部分坍塌(键 500→200,字节面净变 -7.9%)逃逸"
                "全部可跑门:锚门宪章=误报克制(无新指控)、S7 宪章=数据面"
                "字节骤降 20%(净变低于阈;生产面单源坍塌占总字节份额更"
                "小,总面 20% 阈更不可见)——键级语义坍塌两门皆盲;宪章"
                "捕获者=阳性锚召回(recall-positive-anchors,#350 未建);"
                "全量字段错形(→0 键)被载入层零记录守卫响亮拒提交"
                "(_lmdb.py rebuild_lmdb,留旧证据),非静默漏放行。"
                "处置=开 finding 票人裁(绝不自动改门)")


def _mut_echo_on_anchor(td: Path) -> dict:
    """②错误合并·回声上锚:独立源(binarydefense)与派生聚合器(ipsum,
    derived=True 无 infra 过滤)同指净锚 8.8.8.8——派生回声未被谱系去重
    即计入独立印证(事故②形状)→ 合并投影指控净锚,锚门应红;字节上行
    → S7 应绿。回声独有的信号(独立票数/置信度膨胀)属一致性/对拍面,
    本轮无读数(c2/golden)。"""
    ips = _doc_ips(_N_IPSUM)
    bd = _doc_ips(_N_BD)
    return _state(
        "erroneous-merge-echo-on-clean-anchor", "错误合并②",
        "两源合成数据制造错误合并形:独立源+派生聚合器同指净锚 8.8.8.8,"
        "回声计入独立印证(事故②形状)→ 锚门应红;一致性/对拍门(c2/"
        "golden)宪章内应红但本轮无读数",
        {"anchors": True}, td, "echo-on-anchor",
        healthy_rows={"ipsum_rows": [f"{ip}\t5" for ip in ips],
                      "bd_lines": bd},
        mutated_rows={"ipsum_rows": ["8.8.8.8\t5",
                                     *(f"{ip}\t5" for ip in ips)],
                      "bd_lines": ["8.8.8.8", *bd[1:]]})


MUTATIONS = (_mut_key_collapse, _mut_accuses_anchor, _mut_field_malformed,
             _mut_echo_on_anchor)


# ── 读数语义与 runner ─────────────────────────────────────────────────

def _pair_status(expected_red: bool, red: bool) -> str:
    """(变异体,门)对读数:killed=会红;survived=漏放行(宪章内应红
    而绿,零容忍 finding);green=宪章外绿(门不越权,正常);
    unexpected-red=宪章外红(过敏,留痕观察)。"""
    if expected_red:
        return "killed" if red else "survived"
    return "unexpected-red" if red else "green"


def _finding_text(state: dict, killed_by: list[str]) -> str | None:
    """survived 的 finding 文本:模板自带优先(预分析盲区),否则通用
    生成(门改瞎/盲区被发现时的诚实出口,绝不自动改门)。"""
    if killed_by:
        return None
    if state["finding"]:
        return state["finding"]
    expected = sorted(state["expected_red"]) or ["无(宪章捕获者未建)"]
    return (f"变异体 {state['id']} 未被任何可跑门杀死;宪章内应红门 "
            f"{'、'.join(expected)} 未响 —— 开 finding 票人裁"
            "(绝不自动改门)")


def run_mutation_check() -> dict:
    """种缺陷 → 跑门 → killed/survived 读数;沙箱种完即清。

    返回 JSON-able 读数(契约 runner func 腿消费):matrix=逐(变异体,
    可跑门)对;mutations=变异体级 rollup(killed=任一门红 / survived=
    无门红,附 finding);gates.no_reading=无读数门及理由,绝不虚构。
    本函数不持门、不改门:survived 只产 finding 文本人裁。
    """
    matrix, rollups = [], []
    with tempfile.TemporaryDirectory(prefix="mutation-check-") as td:
        root = Path(td)
        for tpl in MUTATIONS:
            state = tpl(root)
            killed_by = []
            for gate_id, gate_fn in RUNNABLE_GATES.items():
                red, detail = gate_fn(state)
                status = _pair_status(
                    bool(state["expected_red"].get(gate_id)), red)
                if red:
                    killed_by.append(gate_id)
                matrix.append({
                    "mutation": state["id"], "gate": gate_id,
                    "expected_red": bool(
                        state["expected_red"].get(gate_id)),
                    "status": status, "detail": detail})
            rollups.append({
                "id": state["id"], "defect": state["defect"],
                "mechanism": state["mechanism"],
                "keys_healthy": state["healthy"]["counts"],
                "keys_mutated": state["mutated"]["counts"],
                "status": "killed" if killed_by else "survived",
                "killed_by": killed_by,
                "finding": _finding_text(state, killed_by)})
    n_status = {s: sum(1 for m in matrix if m["status"] == s)
                for s in ("killed", "survived", "green", "unexpected-red")}
    survived = [r for r in rollups if r["status"] == "survived"]
    return {
        "kind": "mutation_check",
        "gates": {"runnable": sorted(RUNNABLE_GATES),
                  "no_reading": GATES_NO_READING},
        "matrix": matrix,
        "mutations": rollups,
        "survived_findings": [r["finding"] for r in survived],
        "summary": {"n_mutations": len(rollups),
                    "killed": len(rollups) - len(survived),
                    "survived": len(survived), "pairs": n_status}}
