"""log-odds 内核纯函数测试(spec 2026-08-29 §3)。数字全部手工推导。

brief 两处算术笔误已修正并留痕:
- 0.0625 = 2^-4 对应 240d(4 个半衰期),365d 实为 2^(-365/60)≈0.0147
- dedup 场景1 注释要求「derived 弱于非 derived」,系数应为 0.59 而非 0.69
"""
import math
from datetime import datetime, timedelta, timezone

from ipdb._logodds import (
    logit, decay_factor, coefficient, dedup_lineage, accuser_pool,
    assertion_confidence, multicategory_posterior, asof_to_now,
)


def test_logit_identity_and_clamp():
    assert round(1 / (1 + math.exp(-logit(0.85))) * 100) == 85   # σ(logit(p)) = p
    assert logit(1.0) == logit(0.98)                             # 上界钳制


def test_logit_lower_clamp_inputs_safe():
    """p=0/1e-7 不炸:下钳 1e-6 与上钳 0.98 对称(输入域 [0,1] 全安全,
    加固 2026-10-11 PR-1)。"""
    assert math.isfinite(logit(0.0))
    assert math.isfinite(logit(1e-7))
    assert logit(0.0) == logit(1e-6)                             # 钳位锚点


def test_decay_checkpoints():
    # h=60d:30d→0.707,120d→0.25,240d→0.0625(每 60d 减半)
    assert abs(decay_factor(30) - 0.7071) < 1e-3
    assert abs(decay_factor(60) - 0.5) < 1e-9
    assert abs(decay_factor(120) - 0.25) < 1e-9
    assert abs(decay_factor(240) - 0.0625) < 1e-9
    assert decay_factor(None) == 1.0


def test_decay_preserves_sign():
    """B3:衰减作用于系数整体,方向不变。"""
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    fresh = coefficient(0.85, "2026-08-28T00:00:00+00:00", now=now)
    stale = coefficient(0.85, "2024-08-29T00:00:00+00:00", now=now)
    assert fresh > 0 and stale > 0 and stale < fresh


def test_unparseable_first_seen_no_decay():
    assert coefficient(0.7, "not-a-date") == logit(0.7)


def test_dedup_lineage_scenarios():
    # 场景1:derived 弱于非 derived → 被剔除
    out = dedup_lineage([("firehol", 0.59), ("blocklist_de", 0.62)])
    assert [s for s, _ in out] == ["blocklist_de"]
    # 场景2:derived 是最强 → 保留,非 derived 照常
    out = dedup_lineage([("firehol", 0.90), ("a", 0.40), ("b", 0.30)])
    assert sorted(s for s, _ in out) == ["a", "b", "firehol"]
    # 场景2b:derived 恰好相等 → 也剔除(spec §3.3「≥ 即剔」)
    out = dedup_lineage([("firehol", 0.62), ("blocklist_de", 0.62)])
    assert [s for s, _ in out] == ["blocklist_de"]
    # 场景3:全是 derived 且无锚对 → 全保留(锚对在场例外:弱侧回声剔,
    # grill Q2 2026-10-11 翻案,见 test_dedup_lineage_pure_derived_mirror_pair)
    out = dedup_lineage([("firehol", 0.5), ("ipsum", 0.4)])
    assert len(out) == 2


def test_dedup_lineage_pure_derived_mirror_pair():
    """grill Q2 翻案(2026-10-11):谱系锚判式对纯 derived 组同样生效——
    修复前纯 derived 早退全保留,firehol r=.5 + greensnow r=.6(OC=1.0
    镜像对,greensnow 原创内容被 firehol 再发布,包含度 ≥0.9,eval
    谱系簇 2026-09-01)同场时同一出版方算两票、corroborated 假真。
    修后 greensnow 在场且系数不低于 firehol → firehol 剔回声:单票
    (corroborated=len(dedup)≥2 → False),conf=σ(logit(.6))=60=单源 r。
    firehol 系数=logit(.5)·decay≡0,剔它不改任何分数——回放闸门 C2
    退化恒等由构造成立。"""
    gs = coefficient(0.6, None)                     # logit(.6),无龄不衰减
    out = dedup_lineage([("firehol", coefficient(0.5, None)),
                         ("greensnow", gs)])
    assert out == [("greensnow", gs)]               # 单票 → corroborated=False
    assert assertion_confidence([c for _, c in out]) == 60  # conf=单源 r


def test_dedup_lineage_mixed_pool_zero_change():
    """非 derived 在场行为零变(grill Q2 影响面):混合组里 firehol
    本就被「derived ≤ 最强非 derived」剔(0 ≤ logit(.55)),锚判式前移
    不改变保留集——本测试修复前后同绿,是影响面钉子而非红证。"""
    kept = dedup_lineage([("firehol", coefficient(0.5, None)),
                          ("greensnow", coefficient(0.6, None)),
                          ("blocklist_de", coefficient(0.55, None))])
    assert [s for s, _ in kept] == ["greensnow", "blocklist_de"]


def test_dedup_lineage_otx_pair_still_double_vote():
    """otx/otx_subscribed 互嵌无实测数字,不入锚表(grill Q2:无数字
    不入,现状钉死)——纯 derived 双票保持。"""
    out = dedup_lineage([("otx", coefficient(0.5, None)),
                         ("otx_subscribed", coefficient(0.5, None))])
    assert [s for s, _ in out] == ["otx", "otx_subscribed"]


def test_assertion_confidence_numbers():
    assert assertion_confidence([logit(0.85)]) == 85            # 单源 conf = r
    two = assertion_confidence([logit(0.65), logit(0.65)])      # 两独立 0.65
    assert two == 78                                            # σ(2×0.6190)≈0.775
    assert assertion_confidence([]) == 50                       # 无系数→中立


def test_multicategory_background_mass():
    # 单源 0.85 → 85(B1/A1:背景质量修复 softmax 单源 100 的 bug)
    p = multicategory_posterior({"HK": logit(0.85)})
    assert round(p["HK"] * 100) == 85
    # 等权 2:2 → 各 ~44%,背景 ~12%
    s = 2 * logit(0.65)
    p = multicategory_posterior({"HK": s, "US": s})
    assert abs(p["HK"] - p["US"]) < 1e-9
    assert 0.43 < p["HK"] < 0.45
    assert abs(sum(p.values()) - (1 - 1 / (math.exp(s) * 2 + 1))) < 1e-9  # 概率和 < 1


def test_dedup_lineage_greensnow_mirror_dropped():
    # greensnow mirrors firehol (containment ≥0.9, spec 2026-09-02-brief §5.1): as a derived
    # source it must never out-vote its non-derived competitor's ceiling.
    coeffs = [("firehol", 2.0), ("spamhaus", 1.5), ("greensnow", 1.4)]
    assert dedup_lineage(coeffs) == [("firehol", 2.0), ("spamhaus", 1.5)]


def test_dedup_lineage_anchor_scenarios():
    """DQ-1 谱系锚(emerging_threats ⊇ spamhaus DROP,/12 巨块回声审计
    实证):锚在场且系数不低于 target → 剔;缺席/更弱/单独 → 保留。"""
    # 双在场(emerging ≤)→ emerging 剔,spamhaus 保留
    assert dedup_lineage([("spamhaus", 2.2), ("emerging_threats", 1.7)]) == [
        ("spamhaus", 2.2)]
    # 相等也剔(与 derived 同判式,宁少算)
    assert dedup_lineage([("spamhaus", 1.7), ("emerging_threats", 1.7)]) == [
        ("spamhaus", 1.7)]
    # 锚缺席 → emerging 保留(非 derived,照常计票)
    assert dedup_lineage(
        [("emerging_threats", 1.7), ("blocklist_de", 0.6)]) == [
        ("emerging_threats", 1.7), ("blocklist_de", 0.6)]
    # 锚系数更低 → emerging 保留(锚不能压过更强证据)
    assert dedup_lineage(
        [("spamhaus", 1.0), ("emerging_threats", 1.7),
         ("blocklist_de", 0.6)]) == [
        ("spamhaus", 1.0), ("emerging_threats", 1.7), ("blocklist_de", 0.6)]
    # emerging 单独在场 → 保留
    assert dedup_lineage([("emerging_threats", 1.7)]) == [
        ("emerging_threats", 1.7)]


def test_dedup_lineage_drop12_echo_42_208(monkeypatch):
    """「42.208.0.0/12 回声」回归(DQ-1,审计 2026-10-06:firehol/
    spamhaus/emerging 在 42.128/160/208.0.0/12 边界逐位相同,每 IP 白
    得 3 个「独立」证人 rel .5/.85/.9,corroborated≥2 判真,14.9M IP
    受影响)。等新鲜度下系数 = logit(rel):spamhaus 最强、firehol 最弱。
    修复前(锚表空 = 旧行为):firehol 恒剔(derived 弱于最强非
    derived)→ 有效票 3→2,佐证门仍被回声凑满;修复后 emerging 因锚
    在场再剔 → 有效票 1,回声破。"""
    coeffs = [("firehol", logit(0.5)), ("emerging_threats", logit(0.85)),
              ("spamhaus", logit(0.9))]
    monkeypatch.setattr("ipdb._logodds.LINEAGE_ANCHORS", {})
    baseline = dedup_lineage(coeffs)
    assert [s for s, _ in baseline] == ["emerging_threats", "spamhaus"]  # 3→2
    monkeypatch.undo()
    assert dedup_lineage(coeffs) == [("spamhaus", logit(0.9))]  # →1


def test_accuser_pool_max_per_source_and_sorted():
    """同源多条观测只计最强单条断言(spec §3.3 宁少算);输出按源名
    sorted(issue #244 排序口径统一,grill Q2 2026-10-30)。"""
    entries = [
        ("spamhaus", 0.5, None),        # 同源两条,弱者在先
        ("abuseipdb", 0.7, None),
        ("spamhaus", 0.9, None),        # 强者胜出
    ]
    pool = accuser_pool(entries, "blacklist")
    assert pool == [("abuseipdb", logit(0.7)), ("spamhaus", logit(0.9))]


def test_accuser_pool_insertion_order_irrelevant():
    """插入序不影响池内容与序位(生产 _merge 从插入序改 sorted 的
    行为面钉子:仅池列表序变化,集合与逐位系数不变)。"""
    a = [("zeta", 0.8, None), ("alpha", 0.6, None), ("mid", 0.7, None)]
    assert accuser_pool(a, "blacklist") == accuser_pool(reversed(a), "blacklist")
    assert [s for s, _ in accuser_pool(a, "blacklist")] == ["alpha", "mid", "zeta"]


def test_accuser_pool_dedup_integration():
    """derived 弱于最强非 derived → 剔(与直调 dedup_lineage 同判);
    无 first_seen → 不衰减。"""
    pool = accuser_pool(
        [("firehol", 0.5, None), ("spamhaus", 0.9, None)], "blacklist")
    assert pool == [("spamhaus", logit(0.9))]


def test_accuser_pool_now_anchor_passthrough():
    """now(时钟锚 F2/S37)透传 coefficient:同 entries 不同锚刻
    衰减不同;None → 墙钟默认路径同直调。"""
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    fresh = accuser_pool(
        [("s", 0.85, "2026-08-28T00:00:00+00:00")], "blacklist", now=now)
    stale = accuser_pool(
        [("s", 0.85, "2020-08-28T00:00:00+00:00")], "blacklist", now=now)
    assert fresh == [("s", coefficient(0.85, "2026-08-28T00:00:00+00:00", now=now))]
    assert stale[0][1] < fresh[0][1]
    assert accuser_pool([("s", 0.7, "not-a-date")], "blacklist") == \
        [("s", logit(0.7))]


def test_accuser_pool_per_entry_ctype_cross_group(monkeypatch):
    """跨组池化(issue #246,_types.threat_summary 判例):entry 携第 4 元
    ctype,衰减按各证据自己类型的半衰期;第 4 元缺省回退形参 ctype。
    DECAY_OVERRIDES 现为空表(全类型 60d,两路径同值——零行为变更),
    注入 override 后分道:钉语义,不钉空表现状。"""
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    fs = "2026-10-01T00:00:00+00:00"          # 龄 30d
    # 空表现状:跨组两源同 r 同刻,ctype 异名但同半衰期 → 与显式单
    # ctype 直算逐位相同(收编前后零行为变更的护栏)
    assert accuser_pool(
        [("abuseipdb", 0.9, fs, "scanner"), ("threatfox", 0.9, fs, "c2-server")],
        now=now)[0][1] == coefficient(0.9, fs, "scanner", now=now)
    # 注入 scanner 半衰期 600d → 30d 龄仅衰 ~3.4%,显著高于 60d 半衰期
    # 的 0.707 衰减;无 override 的 c2-server 与缺省回退形参的 zeta
    # 同刻同 r 同 h → 系数逐位相同
    monkeypatch.setattr("ipdb._logodds.DECAY_OVERRIDES", {"scanner": 600.0})
    out = accuser_pool(
        [("abuseipdb", 0.9, fs, "scanner"),   # 第 4 元 scanner(600d)
         ("threatfox", 0.9, fs, "c2-server"),  # 第 4 元无 override(60d)
         ("zeta", 0.9, fs)],                   # 缺省回退形参 blacklist(60d)
        "blacklist", now=now)
    assert out == [
        ("abuseipdb", coefficient(0.9, fs, "scanner", now=now)),
        ("threatfox", coefficient(0.9, fs, "c2-server", now=now)),
        ("zeta", coefficient(0.9, fs, "blacklist", now=now)),
    ]
    assert out[0][1] > out[1][1] == out[2][1]


def test_accuser_pool_cross_group_with_asof_anchor():
    """跨组池化 × asof 时钟锚(F2/S37)联合直断——生产 _types.threat_summary
    的调用形态(4 元组 + now=asof_to_now(asof)):锚回拨 → 证据更
    「年轻」→ 系数更高;epoch 秒锚经 asof_to_now 与 datetime 锚同刻
    (生产链路:_types.asof → helper now,月度读数可复现)。"""
    t0 = datetime(2026, 10, 31, tzinfo=timezone.utc)
    fs = "2026-10-01T00:00:00+00:00"
    entries = [("abuseipdb", 0.9, fs, "scanner"),
               ("threatfox", 0.9, fs, "c2-server")]
    fresh = accuser_pool(entries, now=t0)                     # 龄 30d
    past = accuser_pool(entries, now=t0 - timedelta(days=20))  # 锚回拨 20d → 龄 10d
    assert past[0][1] > fresh[0][1]
    assert past == accuser_pool(entries, now=asof_to_now(
        (t0 - timedelta(days=20)).timestamp()))
    assert accuser_pool(entries, now=asof_to_now(t0.timestamp())) == fresh
