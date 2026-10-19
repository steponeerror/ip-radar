"""判例库 schema 校验(docs/ops/precedents/)。

钉住计划 T1 契约(docs/superpowers/plans/2026-10-19-jitrl-agent-ops-prototype.md):
frontmatter 四元组齐全 + reward 复合映射永不坍缩成标量(Review Focus 5)。
种子回填(T1 Step 3)下限 12 条在此钉死;后续判例增改保持 GREEN。
"""

from pathlib import Path

import yaml

PRECEDENTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "ops" / "precedents"
SCHEMA_FILE = "_schema.md"
REQUIRED_FIELDS = [
    "id",
    "date",
    "subject",
    "context",
    "recommendation",
    "human_ruling",
    "reward",
    "lineage",
    "superseded_by",
]
REWARD_KEYS = {"hard_gates", "ruling_agreement", "production_delta"}
RULING_AGREEMENT_VALUES = {"agreed", "overruled", "amended", "pending"}
SEED_COUNT = 12  # T1 种子回填下限


def precedent_files():
    if not PRECEDENTS_DIR.is_dir():
        return []
    return sorted(p for p in PRECEDENTS_DIR.glob("*.md") if p.name != SCHEMA_FILE)


def parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: 缺 frontmatter 起始围栏"
    end = text.find("\n---\n", 4)
    assert end != -1, f"{path.name}: frontmatter 未闭合"
    return yaml.safe_load(text[4:end])


def test_seed_backfill_count():
    files = precedent_files()
    assert len(files) >= SEED_COUNT, f"种子判例不足: {len(files)} < {SEED_COUNT}"


def test_precedent_schema():
    """每条判例:字段齐全、reward 三列复合映射、production_delta 未结案恒 null。"""
    files = precedent_files()
    assert files, f"判例目录为空或不存在: {PRECEDENTS_DIR}"
    for path in files:
        fm = parse_frontmatter(path)
        for field in REQUIRED_FIELDS:
            assert field in fm, f"{path.name}: 缺必填字段 {field}"

        reward = fm["reward"]
        assert isinstance(reward, dict), f"{path.name}: reward 必须是映射"
        assert set(reward) == REWARD_KEYS, f"{path.name}: reward 恰含三键,实际 {set(reward)}"

        hard_gates = reward["hard_gates"]
        assert isinstance(hard_gates, dict), f"{path.name}: reward.hard_gates 坍缩成标量"
        assert hard_gates, f"{path.name}: reward.hard_gates 不得为空(硬门数字必带)"

        assert (
            reward["ruling_agreement"] in RULING_AGREEMENT_VALUES
        ), f"{path.name}: ruling_agreement 非法值 {reward['ruling_agreement']!r}"
        # production_delta 未结案不补;30 天写回是独立后续批,永不合成
        assert reward["production_delta"] is None, f"{path.name}: production_delta 一律 null"

        superseded_by = fm["superseded_by"]
        if superseded_by is not None:
            target = PRECEDENTS_DIR / str(superseded_by)
            assert target.is_file(), f"{path.name}: superseded_by 指向不存在文件 {superseded_by}"
