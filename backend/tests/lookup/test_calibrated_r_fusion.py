"""DM-1 声明 r 生效:lookup 的 threat 观测改表优先(SOURCE_RELIABILITY,
含 _calibrated.json 运行时覆盖)→ 校准后 details.r 与融合置信度即时反映;
表未收录的源回落 payload/class attr 旧链(无校准文件 = 零漂移)。

单源 conf = r 公理(_logodds 断言路径,无背景质量)给本文件精确钉子:
新鲜单源 r=0.70 → conf 70;r=0.01 → conf 1。
"""
import json
from datetime import datetime, timezone, timedelta

import pytest

import ipdb._registry as reg
from ipdb._merge import SOURCE_RELIABILITY
from ipdb._types import SourceHealth


class FakeThreatSource:
    """最小 threat 假源:新鲜证据(first_seen=now,无衰减),r 走 attr。"""

    name: str
    fields = ("is_malicious",)
    authoritative_for = ()

    def __init__(self, name, reliability=0.70):
        self.name = name
        self.reliability = reliability
        self._data = {
            "classification_type": "blacklist",
            "verdict": "malicious",
            "first_seen": datetime.now(timezone.utc).isoformat(),
        }

    def query(self, ip):
        return self._data

    def health(self):
        return SourceHealth(name=self.name, loaded=True, record_count=1,
                            last_updated=None, is_stale=False)


@pytest.fixture(autouse=True)
def _restore_reliability():
    # 全局 dict 污染防护:每条用例前后快照还原(同 test_calibrated_loader)
    snap = dict(SOURCE_RELIABILITY)
    yield
    SOURCE_RELIABILITY.clear()
    SOURCE_RELIABILITY.update(snap)


def _lookup_with(source):
    import pytest as _pytest
    mp = _pytest.MonkeyPatch()
    mp.setattr(reg, "_sources", [source])
    try:
        return reg.lookup("1.2.3.4")
    finally:
        mp.undo()


def test_calibrated_r_drives_threat_details_and_confidence(tmp_path):
    """DM-1:注入 _calibrated.json(dshield 0.7→0.01)→ lookup 的
    details.r == 0.01、conf == 1(而非 class attr 0.70 的 conf 70)。"""
    f = tmp_path / "_calibrated.json"
    f.write_text(json.dumps({"dshield": {"default": 0.01}}))
    reg._apply_calibrated(f)
    assert SOURCE_RELIABILITY["dshield"] == 0.01

    r = _lookup_with(FakeThreatSource("dshield", reliability=0.70))
    ca = r.classifications["blacklist"]
    assert ca.details[0]["reliability"] == 0.01
    assert ca.confidence == 1            # 单源 conf = r(0.01)
    assert ca.sources[0].reliability == 0.01


def test_no_calibrated_file_zero_drift():
    """无校准文件:表值 == class attr(注册表灌装),输出与改前
    payload/attr 旧链逐位一致——details.r == attr、conf == r×100。"""
    SOURCE_RELIABILITY["dshield"] = 0.70     # registry 导入态(表=attr)
    r = _lookup_with(FakeThreatSource("dshield", reliability=0.70))
    ca = r.classifications["blacklist"]
    assert ca.details[0]["reliability"] == 0.70
    assert ca.confidence == 70               # 旧链(payload 缺键→attr)同值


def test_table_miss_falls_back_to_payload_then_attr():
    """表未收录(测试假源等未注册名)→ payload/class attr 旧链兜底。"""
    SOURCE_RELIABILITY.pop("zz_unregistered", None)
    r = _lookup_with(FakeThreatSource("zz_unregistered", reliability=0.60))
    ca = r.classifications["blacklist"]
    assert ca.details[0]["reliability"] == 0.60
    assert ca.confidence == 60


def test_freshness_decay_uses_calibrated_r(tmp_path):
    """衰减链路也吃表值:r=0.01 且 first_seen 30d → 系数按 0.01 衰减,
    conf 远低于按 0.70 计算的旧输出(融合权重即时生效的直接证据)。"""
    f = tmp_path / "_calibrated.json"
    f.write_text(json.dumps({"dshield": {"default": 0.01}}))
    reg._apply_calibrated(f)

    src = FakeThreatSource("dshield", reliability=0.70)
    src._data["first_seen"] = (
        datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    r = _lookup_with(src)
    ca_calibrated = r.classifications["blacklist"]

    SOURCE_RELIABILITY["dshield"] = 0.70   # 还原旧表值重跑(改前行为)
    r2 = _lookup_with(src)
    ca_old = r2.classifications["blacklist"]

    assert ca_calibrated.details[0]["reliability"] == 0.01
    assert ca_old.details[0]["reliability"] == 0.70
    assert ca_calibrated.confidence < ca_old.confidence
