"""IntelMQ classification.type vocabulary + native→IntelMQ mapping helpers.

Governance: add new classification.type values to CLASSIFICATION_TYPES with a
short comment. Per-source `{native: intelmq}` maps live in their own source
module (backend/ipdb/_sources/<source>.py, since #409 2026-11-22 架构评审④)
—— 加源/改源不再触碰本文件;本模块只保留共享词表与归一/计数机械
(normalize / normalize_counted / unmapped_summary)。No separate
YAML/versioning process (YAGNI for this tool's scale).

对照基准(词表版本锚定):RSIT v1003 (machinev1, enisaeu/RSIT-TF) /
IntelMQ develop@bbe452a 2026-04 — 审计 2026-09-05(官方 allowed_values
45 型;本地取子集,方言仅剩 abuse-reports;botnet 已于 P1 2026-09-05
迁往官方型 infected-system)。上游词表改版时重跑对照。
"""
import logging
from collections import Counter

# IntelMQ classification.type subset relevant to IP threat intel. Extensible.

logger = logging.getLogger(__name__)
CLASSIFICATION_TYPES = frozenset({
    "blacklist",            # generic curated blocklist, no subcategory available
    "c2-server",            # command & control
    "malware-distribution", # serves/delivers malware (e.g. ThreatFox payload_delivery)
    "malware",              # malware sample / payload
    "scanner",              # aggressive scanning
    "brute-force",          # credential/protocol brute force (e.g. blocklist_de ssh)
    "phishing",
    "infected-system",      # 被恶意软件感染的主机(botnet drone;
                            # P1 2026-09-05 迁自方言类型 botnet,
                            # RSIT malicious-code.infected-system)
    "exploit",
    "proxy",
    "tor",
    "vulnerable-system",
    "misconfiguration",
    "abuse-reports",
    "spam",
    "ddos",
    # benign② 断言域(#188,2026-10-24):infra_services 良性断言的分类
    # 面标签(服务角色),非威胁词汇 RSIT 子集——良性断言是判断面输入
    # (与指控同场=verdict_conflict),不产 STIX Indicator;注册于此使
    # 本表保持 classification_type 可发值的单一真源。
    "dns",
    "ntp",
    "other",                # fallback for unmappable values
})

# 逐源映射(THREATFOX_MAP / BLOCKLIST_DE_MAP / … 共 15 表)已迁回各自
# 源 module(#409,2026-11-22 架构评审④:加源改动扇出实测 f44f97e8 加
# 3 源动 20 文件,其中分类映射必须改本中央文件)。搬移前后映射内容
# 逐字节一致,由 tests/core/test_source_declared_maps.py 快照钉住;
# 该测试同时绊线本命名空间不得再出现 module 级 dict(逐源映射回中央
# 即红)——新源的映射声明进它自己的源 module,机械车道按传参工作。


_unmapped_warned: set[tuple[int, str]] = set()


def normalize(raw_type, mapping: dict) -> str:
    """Map a source-native category to a CONTROLLED IntelMQ classification.type
    (the cross-source corroboration axis).

    A clearly-mapped value (present in `mapping` AND in the vocabulary) is used
    as-is. Anything else -> "other" (a controlled bucket that still participates
    in corroboration). Raw native values are NOT passed through here — sources
    that want to preserve an unmappable native value stash it in `extra` (see
    ip2proxy._proxy_evidence). This keeps the vocabulary from growing on every
    edge case while keeping the corroboration axis intact.

    绊线(2026-09-05):未命中映射的原生值按 (map,key) 进程级去重告警一次
    ——上游新增/改名分类码(reportedip 59+、dataplane 新信号)当天可见,
    而非无声落入 other。显式映射到 other 的键(REPORTEDIP "28")不告警。
    """
    key = (raw_type or "").strip().lower()
    mapped = mapping.get(key)
    if mapped and mapped in CLASSIFICATION_TYPES:
        return mapped
    if key and mapped is None and (trip := (id(mapping), key)) not in _unmapped_warned:
        _unmapped_warned.add(trip)
        logger.warning("unmapped native value %r -> 'other' "
                       "(upstream may have added/renamed a category)", key)
    return "other"


# ── 未映射键聚合计数车道(#241 tweetfeed 首创,#254 下沉共享)──────────
# 起因:urlhaus 走共享 normalize() 的逐键 WARN 绊线,生产容器重建窗口
# 实测 296 条(2026-10-31 #241 副产物);tweetfeed 同型问题已内联修 (#241,
# PR #255),本节把「计数代替告警 + 末尾一条摘要」下沉为共享件,两源
# 同调,避免第三份同型拷贝。计数集与旧绊线触发集严格一致(键非空且
# mapping 无此键);mapping 命中但值不在词表的键两车道都不告警不计数。

def normalize_counted(raw_type, mapping: dict, unknown: Counter,
                      *, logger=None, label: str = "", hits: str = "") -> str:
    """normalize() 的聚合计数车道:映射判定同语义,未命中键计入 unknown。

    返回值与 normalize() 逐键一致(位等价由 tweetfeed/urlhaus 的镜像测试
    钉住);唯一差异 = 未命中键不走逐键 WARN 绊线,改计入调用方传入的
    unknown Counter——调用方在解析完整遍结束后发一条聚合摘要
    (unmapped_summary),生成器被中途弃置则摘要不发(#241 契约)。
    logger 传入时,每 distinct 键首现发一条 DEBUG 留痕(哲学 1,信息
    不灭失;label/hits 用于消息文案,如 "tweetfeed: first unmapped
    hashtag '#x' this pass")。
    """
    key = (raw_type or "").strip().lower()
    mapped = mapping.get(key)
    if mapped and mapped in CLASSIFICATION_TYPES:
        return mapped
    if key and mapped is None:
        if logger is not None and unknown[key] == 0:
            logger.debug("%s: first unmapped %s %r this pass "
                         "(counting; aggregate summary at end of parse)",
                         label, hits, key)
        unknown[key] += 1
    return "other"


def unmapped_summary(unknown: Counter, *, logger, label: str, hits: str,
                     item: str, top_n: int = 10) -> None:
    """聚合计数摘要(一条 WARN):总命中数 + distinct + Top-N 及计数。

    #241 票面口径:Top-N 默认 10;unknown 为空零噪音不发。消息形如
    "label: N unmapped-{hits} hit(s), D distinct {item}(s) -> 'other'
    (top K: k1=c1, ...) — upstream may have added/renamed {item}s; ..."
    (hits = 被计名词,如 hashtag/tag;item = distinct 键名词,复数取
    item+'s'——tweetfeed 侧两词不同名系沿用 #241 已合文案,测试钉住)。
    """
    if not unknown:
        return
    top = unknown.most_common(top_n)
    logger.warning(
        "%s: %d unmapped-%s hit(s), %d distinct %s(s) -> 'other' "
        "(top %d: %s) — upstream may have added/renamed %ss; "
        "full first-seen trail at DEBUG",
        label, sum(unknown.values()), hits, len(unknown), item, len(top),
        ", ".join(f"{k}={v}" for k, v in top), item)
