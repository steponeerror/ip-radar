# backend/tests/sources/test_stopforumspam.py
"""SFS listed_ip_365_all parsing — total→reporter_count, last_seen passthrough."""
from ipdb._sources.stopforumspam import StopForumSpamSource


def _write(tmp_path, rows):
    import zipfile
    zp = tmp_path / "sfs.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("listed_ip_365_all.txt", "\n".join(rows) + "\n")
    return zp


def test_harvest_maps_total_and_last_seen(tmp_path):
    zp = _write(tmp_path, [
        '"1.2.3.4","71","2026-03-27 01:53:34"',
        '"5.6.7.8","1","2025-11-11 11:22:33"',
    ])
    import zipfile, io
    s = StopForumSpamSource(data_dir=tmp_path)
    s._path.write_bytes(zipfile.ZipFile(zp).read("listed_ip_365_all.txt"))
    pairs = list(s.harvest())
    assert {ip for ip, _ in pairs} == {"1.2.3.4", "5.6.7.8"}
    ev = dict(pairs)["1.2.3.4"]
    assert ev.reporter_count == 71
    assert ev.last_seen == "2026-03-27 01:53:34"
    assert ev.classification_type == "spam"


def test_download_unzips_inner_file(monkeypatch, tmp_path):
    """download() sniffs the PK header and extracts the inner .txt/.csv."""
    import zipfile
    from ipdb._sources import stopforumspam as mod

    zp = tmp_path / "sfs.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("listed_ip_365_all.txt", '"9.9.9.9","3","2026-01-02 03:04:05"\n')
    monkeypatch.setattr(mod, "download_file",
                        lambda url, dest, token=None, **kw: zp.write(dest) if False else _copy(zp, dest))
    s = mod.StopForumSpamSource(data_dir=tmp_path)
    s.download()
    assert s._path.read_bytes() == b'"9.9.9.9","3","2026-01-02 03:04:05"\n'


def _copy(src, dest):
    import shutil
    shutil.copyfile(src, dest)


def test_download_zip_bomb_raises(monkeypatch, tmp_path):
    """Inner file exceeding the hard cap aborts instead of reading into RAM."""
    import zipfile
    from ipdb._sources import stopforumspam as mod

    zp = tmp_path / "sfs.zip"
    bomb = b'"1.2.3.4","1","2026-01-01 00:00:00"\n' * 4096   # ~140 KB
    with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("listed_ip_365_all.txt", bomb)
    monkeypatch.setattr(mod, "download_file", lambda url, dest, token=None, **kw: _copy(zp, dest))
    monkeypatch.setattr(mod.StopForumSpamSource, "MAX_INNER_BYTES", 64 * 1024)
    import pytest
    with pytest.raises(RuntimeError, match="inner file too large"):
        mod.StopForumSpamSource(data_dir=tmp_path).download()


def test_download_empty_response_raises(monkeypatch, tmp_path):
    from ipdb._sources import stopforumspam as mod

    empty = tmp_path / "empty.zip"
    empty.write_bytes(b"")
    monkeypatch.setattr(mod, "download_file", lambda url, dest, token=None, **kw: _copy(empty, dest))
    import pytest
    with pytest.raises(RuntimeError, match="Empty response"):
        mod.StopForumSpamSource(data_dir=tmp_path).download()


def test_load_cleans_legacy_txt_artifacts(tmp_path):
    """D7 renamed filename .txt→.csv; old-name raw file + LMDB base must not linger."""
    (tmp_path / "stopforumspam.txt").write_text("1.2.3.0/24\n")
    old_epoch = tmp_path / "stopforumspam.txt.lmdb.3"
    old_epoch.mkdir()
    (old_epoch / "data.mdb").write_bytes(b"x")
    for side in ("ptr", "count", "cov"):
        (tmp_path / f"stopforumspam.txt.lmdb.{side}").write_text("3")
    from ipdb._sources.stopforumspam import StopForumSpamSource
    StopForumSpamSource(data_dir=tmp_path).load()
    assert not (tmp_path / "stopforumspam.txt").exists()
    assert not old_epoch.exists()
    assert list(tmp_path.glob("stopforumspam.txt.lmdb*")) == []


def test_harvest_fills_first_seen_for_decay(tmp_path):
    """Single-timestamp sources double-fill first_seen (dataplane/reportedip
    precedent) — first_seen drives per-source decay in the log-odds posterior;
    without it a 365-day list never ages."""
    zp = _write(tmp_path, ['"1.2.3.4","71","2026-03-27 01:53:34"'])
    import zipfile
    s = StopForumSpamSource(data_dir=tmp_path)
    s._path.write_bytes(zipfile.ZipFile(zp).read("listed_ip_365_all.txt"))
    ev = dict(s.harvest())["1.2.3.4"]
    assert ev.first_seen == "2026-03-27 01:53:34"
    assert ev.last_seen == "2026-03-27 01:53:34"


def test_download_harvest_rebuild_query_roundtrip(monkeypatch, tmp_path):
    """The bytes from download() must become queryable evidence end to end."""
    zp = _write(tmp_path, [
        '"1.2.3.4","71","2026-03-27 01:53:34"',
        '"5.6.7.8","1","2025-03-01 00:00:00"',
    ])
    import zipfile
    from ipdb._sources import stopforumspam as mod
    monkeypatch.setattr(mod, "download_file", lambda url, dest, token=None, **kw: _copy(zp, dest))
    s = mod.StopForumSpamSource(data_dir=tmp_path)
    s.download()
    s.rebuild()
    rec = s.query("1.2.3.4")[0]
    assert rec["reporter_count"] == 71
    assert rec["last_seen"] == "2026-03-27 01:53:34"
    assert rec["first_seen"] == "2026-03-27 01:53:34"
    assert 0 <= rec["confidence"] <= 100        # graded score persists
    assert s.query("5.6.7.8")[0]["reporter_count"] == 1


def _ago(days: int) -> str:
    import datetime
    return (datetime.datetime.now() - datetime.timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S")


def test_harvest_grades_recent_suspicious_stale_informational(tmp_path):
    """Per-record verdict: last_seen ≤90d → suspicious, older → informational;
    advisory score rides in Evidence.confidence (native_confidence display)."""
    s = StopForumSpamSource(data_dir=tmp_path)
    s._path.write_text(
        f'"1.2.3.4","71","{_ago(10)}"\n'
        f'"5.6.7.8","1","{_ago(200)}"\n')
    evs = dict(s.harvest())
    assert evs["1.2.3.4"].verdict == "suspicious"
    assert evs["5.6.7.8"].verdict == "informational"
    for ev in evs.values():
        assert 0 <= ev.confidence <= 100
    assert evs["1.2.3.4"].confidence > evs["5.6.7.8"].confidence


def test_grade_boundary_and_monotonicity():
    from ipdb._sources.stopforumspam import _grade
    assert _grade(_ago(90), 5)[0] == "suspicious"        # boundary inclusive
    assert _grade(_ago(91), 5)[0] == "informational"
    assert _grade("garbage", 500)[0] == "informational"   # unparseable ts
    assert _grade(None, 500)[0] == "informational"        # missing ts
    fresh_hi, fresh_lo = _grade(_ago(1), 1000)[1], _grade(_ago(1), 1)[1]
    stale_hi, stale_lo = _grade(_ago(300), 1000)[1], _grade(_ago(300), 1)[1]
    assert 0 <= stale_lo < fresh_lo < stale_hi < fresh_hi <= 100


def test_harvest_skips_malformed_rows(tmp_path):
    import zipfile
    s = StopForumSpamSource(data_dir=tmp_path)
    zp = _write(tmp_path, [
        '"1.2.3.4","abc","2026-01-01 00:00:00"',   # non-integer total → skip
        '"2.3.4.5","5"',                            # too short → skip
        '"3.4.5.6","9",""',                         # blank last_seen → None
    ])
    s._path.write_bytes(zipfile.ZipFile(zp).read("listed_ip_365_all.txt"))
    pairs = dict(s.harvest())
    assert set(pairs) == {"3.4.5.6"}
    assert pairs["3.4.5.6"].last_seen is None


def test_single_evidence_dual_path_equivalence(tmp_path):
    """single_evidence=True 流式 rebuild 与 acc 路径产物逐值相等(T4,
    2026-10-11)。声明安全前提 = 全量实测 485,960 行 bucket>1=0(每 IP
    恰一行一证据),故数据集按同形状构造。若 feed 将来出现重复行:count
    仍同(键覆盖归一),但 covered=Auto 按行统计会虚增 .cov,且异证据
    重复会丢前一行 —— 届时撤声明(对照:threatfox 16.8% 键真多证据,
    不可声明)。"""
    ages = [10, 89, 90, 91, 200, 365, None, "not-a-date"]   # 双裁决+边界+缺/坏 ts
    totals = [1, 5, 71, 1000, 12345, 999999]
    n = 300
    ips = [f"10.0.{i % 256}.{1 + i // 256}" for i in range(n)]
    rows = []
    for i, ip in enumerate(ips):
        age = ages[i % len(ages)]
        ts = age if isinstance(age, str) else ("" if age is None else _ago(age))
        rows.append(f'"{ip}","{totals[i % len(totals)]}","{ts}"')
    rows += [
        '"1.2.3.4","abc","2026-01-01 00:00:00"',   # 非整数 total → skip
        '"2.3.4.5","5"',                            # 太短 → skip
        '","9","2026-01-01 00:00:00"',              # 空 IP → skip
    ]
    data = ("\n".join(rows) + "\n").encode()

    dir_acc, dir_stream = tmp_path / "acc", tmp_path / "stream"
    dir_acc.mkdir()
    dir_stream.mkdir()
    s_acc = StopForumSpamSource(data_dir=dir_acc)
    s_acc.single_evidence = False                # 强制 acc 路径(声明前历史行为)
    s_acc._path.write_bytes(data)
    s_acc.rebuild()
    s_stream = StopForumSpamSource(data_dir=dir_stream)   # 类声明:流式路径
    s_stream._path.write_bytes(data)
    s_stream.rebuild()

    assert StopForumSpamSource.single_evidence is True   # 声明本体(防静默回退)
    assert s_stream._count == s_acc._count == n
    assert s_stream._covered_ips == s_acc._covered_ips == n
    assert (dir_stream / "stopforumspam.csv.lmdb.count").read_text().strip() == str(n)
    assert (dir_stream / "stopforumspam.csv.lmdb.cov").read_text().strip() == str(n)
    for ip in ips + ["8.8.8.8", "127.0.0.1"]:            # 命中+双 miss 逐值全等
        assert s_stream.query(ip) == s_acc.query(ip), ip
    # 语义钉子(非纯同构):裁决边界与 reporter_count 真落库
    assert s_stream.query("8.8.8.8") == {}
    assert s_stream.query(ips[0])[0]["classification_type"] == "spam"
    assert s_stream.query(ips[0])[0]["reporter_count"] == 1
    assert s_stream.query(ips[2])[0]["verdict"] == "suspicious"    # 90d 边界含
    assert s_stream.query(ips[3])[0]["verdict"] == "informational"  # 91d 出窗
