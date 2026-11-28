"""same-start 碰撞绊线(grill Q5,2026-10-11;#480 起改口径)。

绊线 = rebuild 写循环内同 start 异 end 相邻对 WARNING。#480 起同起点
碰撞不再是丢失事故——_flush 写前只留前缀最长的一条,绊线降为信息性
(标记将被过滤裁决的碰撞组);全量(含非相邻对)审计走
scripts/audit_same_start.py(同样信息性)。
"""
import logging

from ipdb._sources._lmdb import rebuild_lmdb

BASE_NAME = "tripwire-test.txt.lmdb"
EV = [{"is_malicious": True}]


def _rebuild(tmp_path, cidrs):
    return rebuild_lmdb(
        [(c, EV) for c in cidrs], tmp_path / BASE_NAME,
        reader_setter=lambda env: None)


def _same_start_warnings(caplog):
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and "[same-start]" in r.getMessage()]


def test_same_start_pair_warns_with_both_cidrs_and_base(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="ipdb._sources._lmdb")
    # 碰撞组归并为单键:同 start 只剩前缀最长的一条(#480 裁决)
    assert _rebuild(tmp_path, ["10.0.0.0/24", "10.0.0.0/16"]) == 1
    warns = _same_start_warnings(caplog)
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "10.0.0.0/24" in msg and "10.0.0.0/16" in msg
    assert BASE_NAME in msg


def test_same_start_reversed_order_also_warns(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="ipdb._sources._lmdb")
    assert _rebuild(tmp_path, ["10.0.0.0/16", "10.0.0.0/24"]) == 1
    warns = _same_start_warnings(caplog)
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "10.0.0.0/16" in msg and "10.0.0.0/24" in msg


def test_disjoint_records_no_warning(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="ipdb._sources._lmdb")
    assert _rebuild(tmp_path, ["10.0.0.0/24", "10.1.0.0/16"]) == 2
    assert _same_start_warnings(caplog) == []


def test_identical_duplicate_cidr_no_warning(tmp_path, caplog):
    # 同 start 同 end = 同键无害去重,不是碰撞(绊线只在异 end 时触发)
    caplog.set_level(logging.WARNING, logger="ipdb._sources._lmdb")
    assert _rebuild(tmp_path, ["10.0.0.0/24", "10.0.0.0/24"]) == 1
    assert _same_start_warnings(caplog) == []
