"""log-odds 评分内核(spec 2026-08-29)。

纯函数、零外部依赖;被 _merge.py(标量/威胁)与 _registry.py(asset)消费。
语义:r = 该源单独作证时答对的频率(单源 conf = r);证据随龄指数衰减,
方向不变强度衰减;多类别带背景质量(未观测答案的隐含概率)。
"""
import math
from collections.abc import Iterable
from datetime import datetime, timezone

DEFAULT_HALF_LIFE_DAYS: float = 60.0
# Phase 2 从数据估(MISP §VI 方法);本期空表 = 全类型统一 60d(spec §3.1)
DECAY_OVERRIDES: dict[str, float] = {}
# 谱系去重的派生源集合(R1-F1):种子 = 无 _registry 导入时的兜底;
# _registry 导入时按源 class attr(derived=True)fill-in-place 覆盖
# (clear+update,同 _merge.SOURCE_RELIABILITY 模式——_eval/audit.py 值
# 绑定本对象身份,严禁重新赋值)。新聚合器声明 derived=True 即入谱系
# 去重,无需改中央字面量表。
DERIVED_SOURCES: set[str] = {
    "firehol", "ipsum", "otx", "otx_subscribed", "greensnow", "drb_ra"}
# 谱系锚(DQ-1,审计 2026-10-06;#464 卡2上半改灌装):target → 原创
# 锚元组(一个转载者可转载多个原创)。声明面只在各源类的 republishes
# 属性上(声明旁注实测同场共现率与口径,清单见各源文件旁注,不在此
# 复抄——评审 B8:抄一份漂移一份);此处留空字典只为名字先存在,
# _registry 导入时无条件 clear+update 灌装,任何 import ipdb 之后表
# 内容 = 声明全集(评审 A2:旧两条字面量种子在任何 import 后不可见,
# 且与源类声明同写两处,已删)。重新赋值本名字会让按模块属性读表的
# 一方(_eval/events.py、测试)拿着旧表,只许原位灌装。
# otx/otx_subscribed 互嵌无实测数字,不声明(现状钉死,grill Q2
# 2026-10-11)。判式不变(卡2后半另票):任一锚在场且系数不低于
# target → target 视为回声剔除(宁少算);锚全缺席或更强 → 保留。
LINEAGE_ANCHORS: dict[str, tuple[str, ...]] = {}


def logit(p: float) -> float:
    """ln(p/(1-p));钳 [1e-6, 0.98] 防发散(spec §3.4;下钳 1e-6 与上钳 0.98
    对称,p=0 输入全安全)。"""
    p = min(max(p, 1e-6), 0.98)
    return math.log(p / (1 - p))


def half_life_for(ctype: str | None) -> float:
    return DECAY_OVERRIDES.get(ctype or "", DEFAULT_HALF_LIFE_DAYS)


def decay_factor(age_days: float | None,
                 half_life_days: float = DEFAULT_HALF_LIFE_DAYS) -> float:
    if age_days is None:
        return 1.0
    return 2.0 ** (-age_days / half_life_days)


def parse_first_seen(value) -> datetime | None:
    """ISO 解析 first_seen(Z 后缀容忍,naive 视作 UTC);缺失/不可解析
    → None。打分期(_age_days)与 rebuild 绊线(_source_base)共用同一口径
    ——同一函数,免得两边判法漂移。"""
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _age_days(first_seen, now: datetime | None) -> float | None:
    ts = parse_first_seen(first_seen)
    if ts is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - ts).total_seconds() / 86400.0)


def asof_to_now(asof: float | None) -> datetime | None:
    """F2/S37 时钟锚:asof epoch 秒 → UTC datetime;None → None(=墙钟,
    默认路径逐位不变)。打分期两处 coefficient 消费点(_merge 组级 /
    _types threat 重融合)共用本换算,免得口径漂移(parse_first_seen
    同款纪律)。"""
    if asof is None:
        return None
    return datetime.fromtimestamp(asof, tz=timezone.utc)


def coefficient(r: float, first_seen: str | None, ctype: str | None = None,
                now: datetime | None = None) -> float:
    """证据系数 = logit(r) × 2^(−age/h);符号随证据方向保留(B3)。"""
    age = _age_days(first_seen, now)
    return logit(r) * decay_factor(age, half_life_for(ctype))


def dedup_lineage(coeffs: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """谱系去重(保守近似,spec §3.3):存在非 derived 源时,剔除系数
    不高于最强非 derived 的 derived 源(相等也剔——宁少算勿重算)。
    谱系锚(LINEAGE_ANCHORS)同判式且对纯 derived 组同样生效——锚判式
    在早退判别之前(grill Q2 2026-10-11 前移;此前纯 derived 早退全
    保留,镜像对同一出版方算两票、corroborated 假真):target 在其任一
    锚源在场且锚系数不低于它时同样剔除(锚全缺席或更强 → 保留;
    #464 卡2上半起表由 registry 按 republishes 声明灌装,target 可声明
    多锚,判式逐锚不变)。"""
    non_derived_max = max((c for s, c in coeffs if s not in DERIVED_SOURCES),
                          default=None)
    kept: list[tuple[str, float]] = []
    for s, c in coeffs:
        if (non_derived_max is not None and s in DERIVED_SOURCES
                and c <= non_derived_max):
            continue
        for anchor in LINEAGE_ANCHORS.get(s, ()):
            # 锚在场 = 锚源出现在输入 coeffs(逐前置判别,不看 kept 集合);
            # 多锚(#464)任一在场且不低于 target 即剔(判式不变,宁少算)
            anchor_max = max((c2 for s2, c2 in coeffs if s2 == anchor),
                             default=None)
            if anchor_max is not None and anchor_max >= c:
                break
        else:
            kept.append((s, c))
    return kept


def accuser_pool(entries: Iterable[tuple[str, float, str | None]
                                   | tuple[str, float, str | None, str | None]],
                 ctype: str | None = None, *,
                 now: datetime | None = None) -> list[tuple[str, float]]:
    """指控池核心循环,单源化(issue #244;GLOSSARY「指控池」「k 族」):
    逐源 coefficient(r, first_seen, ctype)×decay 取 max → dedup_lineage,
    排序口径统一 sorted()(2026-10-30 grill Q2 人裁;此前 eval 四份
    sorted、生产 _merge 插入序漂移——统一仅动池列表序,Σ/conf 与
    计数不变,回放闸门把关)。

    entries = (source, reliability, first_seen) 三元组,或携第 4 元
    ctype 的四元组(issue #246 跨组池化:_types.threat_summary 把多个
    指控组的 detail 池进一个池,逐 detail 携所属组 ctype——衰减按
    各证据自己类型的半衰期;第 4 元缺省回退形参 ctype。组内单
    ctype 调用面(_merge/eval 五面)仍走三元组 + ctype 形参)。
    指控章判定(verdict ∈ _ACCUSING)留在调用方执行——判定面各异,
    不许吞:
    ① eval detail 级滤(agg_share/sinkhole_probe/anchor_readouts);
    ② eval 证据级一律调 _eval.accusation.is_accusation,缺 verdict 键
       不算指控(#529,2026-11-28;旧「兑底 malicious」口径已废);
    ③ 生产 _merge voters-else-回退池调用方预滤(纯存档组退回全量
    Σ,决策 5/乙——回退池含非指控观测,不可在本函数再滤);
    ④ 生产 _types.threat_summary 组级 + detail 级双滤(跨组池化)。
    now 非 None = F2/S37 时钟锚(生产 _merge/_types 传 asof;eval
    快照重算走默认墙钟)。
    """
    by_source: dict[str, float] = {}
    for src, r, first_seen, *per_entry in entries:
        c = coefficient(r, first_seen, per_entry[0] if per_entry else ctype,
                        now=now)
        if src not in by_source or c > by_source[src]:
            by_source[src] = c
    return dedup_lineage(sorted(by_source.items()))


def corroborated_after_dedup(deduped: list[tuple[str, float]]) -> bool:
    """印证旗判式单一真源(生产 _merge 与评测重算共用,禁止各算各的):
    谱系去重后的池里「非派生(不在 DERIVED_SOURCES)且系数 > 0」的源
    ≥2 才算印证(工单 #522,2026-11-28 所有者裁丙口径;取代 grill Q2
    2026-10-11「纯 derived 组互证仍算 corroborated」的旧语义——该语义
    此前只披露不改,注明「改语义须另票」,本票即那张票;2026-11-28 评
    审后主会话裁「非零」收窄为「大于 0」:可靠性校准可把系数压到 0.5
    以下为负(dshield 0.01→logit≈-4.6),负系数是对分数的反向贡献,
    不算一票;另衰减半衰 60 天、恰好衰到 0 需约 176 年,实际够不着,
    「> 0」不会误伤正常正票)。三口径全量读数(本票自扫 2026-11-28,
    dev/arch-r4-scan/i522_corrob_pinned.json,含 CIDR):丢旗 65,300
    = 纯派生互证 64,044 + 两个可靠性 0.5 源互证 938 + 一票第一手配
    零系数/派生回声 318;conf≥70 只丢 56。

    挡三类回声 + 一条负系数边(哲学 3「宁少算,回声不是印证」;
    分桶与扫描件 drop_reason 对齐):
    ① 纯派生源(聚合器)互相印证——两个聚合器抄的是同一批上游,
      不是两票(64,044 组);
    ② 零系数源互证/抬旗——可靠性声明 0.5 → logit(0.5)=0 →
      系数恒 0,与钟无关(hookzof/thespeedx/proxyscrape/tweetfeed,
      938 组);
    ③ 恰一个真第一手票,其余是零系数源或派生回声——一票不足两票
      (318 组,conf≥70 的 56 组全在这里)。

    先后关系:入参必须是 dedup_lineage / accuser_pool 的输出(谱系去重
    在前,本判式只做资格过滤,不再去重);conf/Σ 照旧由全池系数算,
    本判式只决定旗,不进置信度(旗是独立字段)。"""
    return sum(1 for s, c in deduped
               if s not in DERIVED_SOURCES and c > 0.0) >= 2


def assertion_confidence(coeffs: list[float]) -> int:
    """σ(Σcoeff) → 0-100;空列表 = 50(中立)。"""
    s = sum(coeffs)
    p = 1.0 / (1.0 + math.exp(-s))
    return round(p * 100)


def multicategory_posterior(s_by_value: dict) -> dict:
    """P(v) = exp(s_v)/(Σ_u exp(s_u) + 1);背景质量 1 = 「未观测答案」
    (spec 审计 A1:否则单源 conf=100,违反单源 conf=r)。"""
    exps = {v: math.exp(s) for v, s in s_by_value.items()}
    total = sum(exps.values()) + 1.0
    return {v: e / total for v, e in exps.items()}
