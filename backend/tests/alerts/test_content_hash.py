# backend/tests/alerts/test_content_hash.py — #467:update_events 内容指纹(只记账,不改行为)
"""content_hash 列(存量库就地升级)、content_fingerprint 纯函数、
record_event/observe_update 写新列、observe_update 的 content_hash_of
延迟契约(平时不算指纹)。红线:页面/告警逻辑不读这一列,既有测试零
改动;本文件只钉新增面(循 test_storage.py 的 tmp db + 直读 sqlite
断言惯例)。
"""
import hashlib
import os
import sqlite3
from contextlib import closing

import pytest


@pytest.fixture()
def alerts_db(tmp_path, monkeypatch):
    """逐用例独立 db 文件(循 test_storage.py 同名 fixture)。"""
    p = tmp_path / "alerts.db"
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(p))
    return p


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _hash_rows(db):
    """直读 sqlite:事件行带指纹列(绕开被测 API,断言才独立)。"""
    with closing(sqlite3.connect(str(db))) as conn:
        return conn.execute(
            "SELECT source, at, record_count, content_hash FROM update_events"
            " ORDER BY at, id").fetchall()


def _columns(db, table="update_events"):
    with closing(sqlite3.connect(str(db))) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


# ── 存量库就地升级(#467 验收 1:旧库补列、旧行原样)──

# 升级前的建表语句(02006a69 master 的 _SCHEMA 原样,无 content_hash)
_OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS update_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL, at REAL NOT NULL, record_count INTEGER);
CREATE INDEX IF NOT EXISTS ix_update_events_source_at ON update_events(source, at);
CREATE TABLE IF NOT EXISTS alert_state (
  source TEXT NOT NULL, condition TEXT NOT NULL,
  active_since REAL NOT NULL, last_notified REAL NOT NULL,
  PRIMARY KEY (source, condition));
CREATE TABLE IF NOT EXISTS source_watermark (
  source TEXT PRIMARY KEY, mtime REAL NOT NULL);
"""


def test_legacy_db_upgraded_in_place(tmp_path, monkeypatch):
    """造一个没有 content_hash 列的 alerts.db(按旧建表语句)+ 一行旧数据,
    跑一次初始化(任一存储操作触发工厂)→ 列存在、旧行原样(指纹 NULL)、
    新行可带指纹。"""
    from ipdb import _alerts
    db = tmp_path / "alerts.db"
    with closing(sqlite3.connect(str(db))) as conn:
        conn.executescript(_OLD_SCHEMA)
        conn.execute("INSERT INTO update_events (source, at, record_count)"
                     " VALUES ('legacy', 1.0, 7)")
        conn.commit()
    monkeypatch.setenv("IP_RADAR_ALERTS_DB", str(db))
    _alerts.record_event("otx", at=2.0)   # 首次操作 → 建工厂 → 迁移补列
    assert "content_hash" in _columns(db)
    with closing(sqlite3.connect(str(db))) as conn:
        rows = conn.execute(
            "SELECT source, at, record_count, content_hash FROM update_events"
            " ORDER BY at").fetchall()
    assert rows == [("legacy", 1.0, 7, None), ("otx", 2.0, None, None)]


def test_fresh_db_has_column_and_migration_idempotent(alerts_db):
    """新库建表即含列;二次操作(工厂已在、迁移已跑过)幂等不炸。"""
    from ipdb import _alerts
    _alerts.record_event("otx", at=1.0)
    _alerts.record_event("otx", at=2.0)
    assert "content_hash" in _columns(alerts_db)
    assert len(_hash_rows(alerts_db)) == 2


def test_migration_duplicate_column_swallowed(tmp_path):
    """#472 评审 M-2 钉子:部署后两线程同时首开账本,探到缺列与 ALTER
    之间另一线程已把列加上 → 后到者的 ALTER 报 duplicate column name。
    假连接 PRAGMA 谎报旧 schema、ALTER 透传给已带列的真库,断言迁移
    不抛、列没被加两遍。"""
    from ipdb import _alerts
    db = tmp_path / "alerts.db"
    with closing(sqlite3.connect(str(db))) as conn:
        conn.executescript(_alerts._SCHEMA)          # 新库:content_hash 已在
        conn.commit()
    with closing(sqlite3.connect(str(db))) as real:
        class _RacyConn:
            """PRAGMA 谎报旧 schema(缺列),其余语句透传真连接。"""

            def execute(self, sql):
                if sql.startswith("PRAGMA"):
                    return iter([(0, "id", "", 0, None, 0),
                                 (1, "source", "", 1, None, 1),
                                 (2, "at", "", 1, None, 0),
                                 (3, "record_count", "", 0, None, 0)])
                return real.execute(sql)

        _alerts._migrate_content_hash(_RacyConn())   # 不抛即过
        names = [r[1] for r in real.execute(
            "PRAGMA table_info(update_events)")]
    assert names.count("content_hash") == 1          # 列在,且没被加两遍


# ── content_fingerprint 纯函数(#467 验收 3)──

def test_fingerprint_single_file_is_streamed_sha256(tmp_path):
    from ipdb import _alerts
    f = tmp_path / "data.csv"
    f.write_bytes(b"hello")
    assert _alerts.content_fingerprint([f]) == _sha("hello")


def test_fingerprint_multi_file_combines_sorted_name_and_digest(tmp_path):
    """多文件:自分隔喂入——对排序后的每对「文件名 \\x00 文件sha256」依次
    update 进一个新 sha256;与调用方传入顺序无关。NUL 分隔让文件名边界
    明确(文件名不可能含 NUL 字节)。"""
    from ipdb import _alerts
    a = tmp_path / "a.csv"; a.write_text("1")
    b = tmp_path / "b.csv"; b.write_text("2")
    combined = hashlib.sha256()
    combined.update(b"a.csv\x00" + _sha("1").encode("ascii"))
    combined.update(b"b.csv\x00" + _sha("2").encode("ascii"))
    want = combined.hexdigest()
    assert _alerts.content_fingerprint([a, b]) == want
    assert _alerts.content_fingerprint([b, a]) == want      # 顺序无关


def test_fingerprint_multi_file_sorts_by_name_not_digest(tmp_path):
    """钉「按文件名排」而非按摘要排:互换两文件内容后,期望仍按 a.csv
    在前——实现若改成按摘要排序(key=digest)这条会红(sha256("1")以
    6b 开头 < sha256("2")以 d4 开头,原内容下两种排序恰好同序,互换后
    即不同序)。"""
    from ipdb import _alerts
    a = tmp_path / "a.csv"; b = tmp_path / "b.csv"
    a.write_text("1"); b.write_text("2")
    a.write_text("2"); b.write_text("1")     # 互换内容,文件名不动
    combined = hashlib.sha256()
    combined.update(b"a.csv\x00" + _sha("2").encode("ascii"))
    combined.update(b"b.csv\x00" + _sha("1").encode("ascii"))
    assert _alerts.content_fingerprint([a, b]) == combined.hexdigest()


def test_fingerprint_swap_contents_changes(tmp_path):
    """目录里两个文件互换内容 → 指纹必变(文件名参与拼接;若只对内容
    集合哈希,互换前后会相等,这条就红了)。"""
    from ipdb import _alerts
    a = tmp_path / "a.csv"; b = tmp_path / "b.csv"
    a.write_text("1"); b.write_text("2")
    before = _alerts.content_fingerprint([a, b])
    a.write_text("2"); b.write_text("1")
    after = _alerts.content_fingerprint([a, b])
    assert before != after


def test_fingerprint_missing_or_empty_none(tmp_path):
    """文件读不了/列表为空 → None(宁少算,不硬造);多文件一组里坏一个
    整体 None(一组指纹必须全体可比才有意义)。"""
    from ipdb import _alerts
    assert _alerts.content_fingerprint([]) is None
    assert _alerts.content_fingerprint([tmp_path / "missing.csv"]) is None
    ok = tmp_path / "ok.csv"; ok.write_text("1")
    assert _alerts.content_fingerprint([ok, tmp_path / "gone.csv"]) is None


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root 读文件不受 chmod 000 限制")
def test_fingerprint_permission_denied_none(tmp_path):
    """权限读不了(OSError 族)同归 None(循 test_tokens.py 的 skipif 惯例)。"""
    from ipdb import _alerts
    f = tmp_path / "locked.csv"
    f.write_text("secret")
    f.chmod(0o000)
    assert _alerts.content_fingerprint([f]) is None


# ── record_event / observe_update 写新列(#467 验收 2)──

def test_record_event_writes_hash(alerts_db):
    from ipdb import _alerts
    _alerts.record_event("otx", at=1.0, content_hash="aa")
    _alerts.record_event("otx", at=2.0)          # 缺省 NULL
    assert _hash_rows(alerts_db) == [("otx", 1.0, None, "aa"),
                                     ("otx", 2.0, None, None)]


def test_observe_seed_and_advance_carry_hash(alerts_db):
    """种子与新前进各落一条事件、各算一次指纹并写入;水位照常推进。"""
    from ipdb import _alerts
    calls = []

    def hash_of():
        calls.append(1)
        return "h1"

    assert _alerts.observe_update("otx", 100.0, content_hash_of=hash_of) is True
    assert calls == [1]                          # 种子即新事件:算了一次
    assert _alerts.observe_update(
        "otx", 200.0, record_count=5,
        content_hash_of=lambda: "h2") is True
    assert _hash_rows(alerts_db) == [
        ("otx", 100.0, None, "h1"), ("otx", 200.0, 5, "h2")]


def test_observe_hash_none_event_still_records(alerts_db):
    """指纹函数返回 None(文件读不了,#467 issue 第 4 条)→ 事件照记、
    指纹列 NULL,记账不因指纹缺失而丢。"""
    from ipdb import _alerts
    assert _alerts.observe_update("otx", 100.0,
                                  content_hash_of=lambda: None) is True
    assert _hash_rows(alerts_db) == [("otx", 100.0, None, None)]


def test_observe_no_thunk_old_shape_bit_equivalent(alerts_db):
    """不传 content_hash_of = 旧调用形状:事件照记、指纹 NULL(既有
    调用方/测试位等价);种子分支不消费 record_count(历史语义,
    恒 NULL,循 test_storage.py 的 test_observe_first_seen_seeds...)。"""
    from ipdb import _alerts
    assert _alerts.observe_update("otx", 100.0, record_count=3) is True
    assert _hash_rows(alerts_db) == [("otx", 100.0, None, None)]


def test_observe_thunk_not_called_without_new_event(alerts_db):
    """#467 验收「平时不算指纹」(存储侧):mtime 不推进/回退 → thunk
    一次都不调(传会计数的假函数);存量库首扫只写水位不补种,同样不调。"""
    from ipdb import _alerts
    calls = []

    def counting():
        calls.append(1)
        return "h"

    assert _alerts.observe_update("otx", 100.0, content_hash_of=counting) is True
    assert calls == [1]                          # 种子:恰一次
    assert _alerts.observe_update("otx", 100.0,
                                  content_hash_of=counting) is False
    assert _alerts.observe_update("otx", 50.0,
                                  content_hash_of=counting) is False
    assert _alerts.observe_update("otx", 99.9,
                                  content_hash_of=counting) is False
    _alerts.record_event("old", at=1.0)          # 存量库形状:有事件、零水位
    assert _alerts.observe_update("old", 100.0,
                                  content_hash_of=counting) is False
    assert calls == [1]
