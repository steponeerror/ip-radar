"""DQ-2 count-sidecar invariant: after any rebuild, `.count` == the committed
env's actual main-db key count.

Pre-fix behavior: `.count` was written from the streamed row count (n) or a
caller override (CsvSource 证据数), neither of which equals stored keys when
the feed contains duplicate rows (tor_exits measured 3328 rows vs 1431 keys,
57% inflated) or same-start CIDR collisions (firehol documented ~0.065%).
Post-fix, rebuild_lmdb reads env.stat()["entries"] at commit time — the
sidecar, owner._count and health().record_count all report what is actually
in the store."""
import csv

from ipdb._sources._base import CsvSource, IpListSource
from ipdb._sources._lmdb import (
    PAYLOADS_NAME, count_path, open_env_read, read_ptr, rebuild_lmdb)


class _List(IpListSource):
    name, filename, fields = "t", "t.txt", ("is_malicious",)


class _Multi(IpListSource):
    """tor_exits-shaped: raw lines may repeat the same IP (multi-relay exits)."""
    name, filename, fields = "m", "m.txt", ("is_tor",)


class _Csv(CsvSource):
    name, filename, fields = "c", "c.csv", ("is_malicious",)
    skip_lines = 0

    def parse_row(self, row):
        if len(row) < 2:
            return None
        # second column keeps rows as DISTINCT evidences on the SAME cidr
        return {"_ip": row[0].strip(),
                "extra": {"tag": row[1].strip()},
                "is_malicious": True}


def _env_keys(base, tmp_path):
    epoch = read_ptr(base)
    env = open_env_read(tmp_path / f"{base.name}.{epoch}")
    n = 0
    with env.begin() as txn:          # streaming cursor, no materialization
        for k, _ in txn.cursor():
            if k != PAYLOADS_NAME:     # named-db descriptor key, not data
                n += 1
    stat = env.stat()["entries"] - 1   # minus the payloads descriptor key
    return stat, n


def test_count_sidecar_equals_env_keys_dup_and_same_start(tmp_path):
    """Duplicate lines + same-start CIDR collision must NOT inflate .count."""
    (tmp_path / "m.txt").write_text(
        "9.9.9.9\n9.9.9.9\n9.9.9.9\n10.0.0.0/24\n10.0.0.0/16\n")
    s = _Multi(data_dir=tmp_path)
    ret = s.rebuild()
    base = tmp_path / "m.txt.lmdb"
    stat, cursor = _env_keys(base, tmp_path)
    assert stat == cursor == 2, (stat, cursor)     # 1 dup-collapsed /32 + 1 collided start
    assert count_path(base).read_text().strip() == "2"
    assert ret == 2                                 # rebuild returns key count
    assert s._count == 2
    assert s.health().record_count == 2


def test_rebuild_lmdb_count_from_env_not_rows(tmp_path):
    """Direct rebuild_lmdb: rows offered (4) > keys stored (2); sidecar and
    return value both come from the committed env."""
    base = tmp_path / "t.txt.lmdb"
    records = [("1.2.3.4/32", [{"x": 1}]), ("1.2.3.4/32", [{"x": 2}]),
               ("10.0.0.0/24", [{"x": 3}]), ("10.0.0.0/16", [{"x": 4}])]
    ret = rebuild_lmdb(iter(records), base, lambda e: e.close())
    stat, cursor = _env_keys(base, tmp_path)
    assert stat == cursor == ret == 2
    assert count_path(base).read_text().strip() == "2"


def test_csv_multievidence_cidr_counts_one_key(tmp_path):
    """CsvSource: two distinct evidences on one CIDR merge into a single key;
    the old 证据数 override (count=2) is gone — .count reports 1."""
    with open(tmp_path / "c.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["5.6.7.8", "a"])
        w.writerow(["5.6.7.8", "b"])   # distinct evidence, same CIDR
    s = _Csv(data_dir=tmp_path)
    ret = s.rebuild()
    base = tmp_path / "c.csv.lmdb"
    stat, cursor = _env_keys(base, tmp_path)
    assert stat == cursor == ret == 1
    assert count_path(base).read_text().strip() == "1"
    assert s.health().record_count == 1
    # both evidences still reachable from the single merged record
    evs = s.query("5.6.7.8")
    tags = {e["extra"]["tag"] for e in evs}
    assert tags == {"a", "b"}
