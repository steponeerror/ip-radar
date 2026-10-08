"""log-odds 内核纯函数测试(spec 2026-08-29 §3)。数字全部手工推导。

brief 两处算术笔误已修正并留痕:
- 0.0625 = 2^-4 对应 240d(4 个半衰期),365d 实为 2^(-365/60)≈0.0147
- dedup 场景1 注释要求「derived 弱于非 derived」,系数应为 0.59 而非 0.69
"""
import math
from datetime import datetime, timezone

from ipdb._logodds import (
    logit, decay_factor, coefficient, dedup_lineage,
    assertion_confidence, multicategory_posterior,
)


def test_logit_identity_and_clamp():
    assert round(1 / (1 + math.exp(-logit(0.85))) * 100) == 85   # σ(logit(p)) = p
    assert logit(1.0) == logit(0.98)                             # 上界钳制


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
    # 场景3:全是 derived → 全保留
    out = dedup_lineage([("firehol", 0.5), ("ipsum", 0.4)])
    assert len(out) == 2


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
    # greensnow mirrors firehol (containment ≥0.9, spec Part 6): as a derived
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
