"""honyport 自建蜜罐观测源(spec 2026-11-02 §2.3,issue #272)。

样例 = §2.1 冻结聚合格式的 verbatim-shaped 件(头 4 注释行 + 列头 +
真实观测行;IP/计数取自主检出 dev/honyport-fixtures/ 两天真件,2026-11-02
榜首 14.112.37.157 MSSQL 11,663 次 / 195.178.110.218 SSH)。覆盖:
- download:目录缺席静默 absent(开发机不受扰);目录在场取最新合法件
  原子拷入;目录在场无合法件 fail-loud(cron 断供可见);
- materialize:列头逐字断言 + generated_at 解析(坏文件 fail-loud);
- 载入侧 30d 硬窗(相对 generated_at 日 = 文件名日):超窗行拒入;
- evidence 形:native_categories=services 列表、last_seen 富槽、
  total_events → extra(route_record 折入),reliability=0.85;
- DQ-2:record_count = env 主库键数。
"""
from pathlib import Path

import pytest

from ipdb._sources.honyport import AGGREGATE_DIR_ENV, HonyportSource

# §2.1 verbatim-shaped 聚合件(生成日=文件名日 2026-11-02)
AGGREGATE = (
    "# generated_at=2026-11-02T03:10:00+08:00\n"
    "# window_days=30\n"
    "# source_files=2\n"
    "# scanner_filtered=0\n"
    "# allowlist_filtered=0\n"
    "ip,first_seen,last_seen,services,total_events\n"
    "14.112.37.157,2026-11-01T17:28:32Z,2026-11-01T17:53:43Z,mssql,11663\n"
    "190.145.231.14,2026-11-01T10:42:12Z,2026-11-01T10:42:44Z,mssql,58\n"
    "195.178.110.218,2026-11-01T09:26:11Z,2026-11-01T13:01:55Z,ssh,962\n"
    "27.46.88.18,2026-11-01T21:28:12Z,2026-11-01T21:28:37Z,mssql;ssh,97\n"
)

# 窗口边界件:anchor=2026-11-02 → [2026-10-04, 2026-11-02] 入,更早拒。
# 10.0.0.4 = 29d 前(边界内保留);10.0.0.3 = 30d 前(超窗拒入)。
WINDOW = (
    "# generated_at=2026-11-02T03:10:00+08:00\n"
    "# window_days=30\n"
    "# source_files=1\n"
    "# scanner_filtered=0\n"
    "# allowlist_filtered=0\n"
    "ip,first_seen,last_seen,services,total_events\n"
    "10.0.0.2,2026-11-02T00:00:00Z,2026-11-02T00:00:00Z,ssh,1\n"
    "10.0.0.4,2026-10-04T00:00:00Z,2026-10-04T00:00:00Z,ssh,2\n"
    "10.0.0.3,2026-10-03T00:00:00Z,2026-10-03T00:00:00Z,ssh,3\n"
)


def _agg_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    d = tmp_path / "aggregate"
    d.mkdir()
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def _source(tmp_path: Path, csv_text: str | None = AGGREGATE) -> HonyportSource:
    if csv_text is not None:
        (tmp_path / "honyport_observed.csv").write_text(
            csv_text, encoding="utf-8")
    return HonyportSource(data_dir=tmp_path)


# ── download(本地挂载目录取件,不走 HTTP)──────────────────────


def test_download_dir_absent_silent_absent(tmp_path, monkeypatch):
    """目录缺席 → 静默跳过报 absent:不抛、不落文件(私有源遮蔽先例,
    开发机无挂载不受扰——零失败任务噪声)。"""
    monkeypatch.setenv(AGGREGATE_DIR_ENV, str(tmp_path / "no-such-dir"))
    s = HonyportSource(data_dir=tmp_path)
    s.download()                                    # 不抛 = 静默跳过
    assert not s._path.exists()                     # absent:无数据文件
    h = s.health()
    assert h.loaded is False and h.record_count == 0


def test_download_copies_latest_valid_file(tmp_path, monkeypatch):
    """取最新合法件(按文件名日期,非 mtime)原子拷入 data_dir 缺省名。"""
    monkeypatch.setenv(AGGREGATE_DIR_ENV, str(_agg_dir(tmp_path, {
        "honeypot-observed-2026-11-01.csv": AGGREGATE.replace("11663", "1"),
        "honeypot-observed-2026-11-02.csv": AGGREGATE,
        "scratch.tmp": "junk,不匹配名样不参与",
    })))
    s = HonyportSource(data_dir=tmp_path)
    s.download()
    assert s._path.read_text(encoding="utf-8") == AGGREGATE   # 最新件逐字节


def test_download_dir_present_no_valid_file_fails_loud(tmp_path, monkeypatch):
    """目录在场但无合法件 → fail-loud(服务器侧 cron 断供必须可见)。"""
    monkeypatch.setenv(AGGREGATE_DIR_ENV, str(_agg_dir(tmp_path, {
        "not-the-pattern.csv": AGGREGATE})))
    s = HonyportSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="no valid honeypot-observed"):
        s.download()


# ── materialize(坏文件 fail-loud + 30d 硬窗)───────────────────


def test_rebuild_bad_column_header_fails_loud(tmp_path):
    """列头漂移 = 坏文件:fail-loud 拒载(加列=断粮,§2.1 冻结契约)。"""
    bad = AGGREGATE.replace(
        "ip,first_seen,last_seen,services,total_events",
        "ip,first_seen,last_seen,services,total_events,note")
    s = _source(tmp_path, bad)
    with pytest.raises(RuntimeError, match="bad column header"):
        s.rebuild()


def test_rebuild_missing_generated_at_fails_loud(tmp_path):
    s = _source(tmp_path, AGGREGATE.replace(
        "# generated_at=2026-11-02T03:10:00+08:00\n", ""))
    with pytest.raises(RuntimeError, match="generated_at"):
        s.rebuild()


def test_rebuild_rejects_over_window_keeps_boundary(tmp_path):
    """30d 硬窗(相对 generated_at 日):[−29d, 0] 入,30d 前拒入;
    验收 §6-3:超窗行 rebuild 后无证。"""
    s = _source(tmp_path, WINDOW)
    assert s.rebuild() == 2                          # 10.0.0.2 + 10.0.0.4
    assert s.query("10.0.0.3") == {}                 # 超窗拒入
    assert s.query("10.0.0.4")[0]["last_seen"] == "2026-10-04T00:00:00Z"


@pytest.mark.parametrize("row", [
    "1.2.3.4,2026-11-01T00:00:00Z,2026-11-01T00:00:00Z,ssh",     # 列数缺
    "1.2.3.4,2026-11-01T00:00:00Z,2026-11-01T00:00:00Z,ssh,1,x",  # 列数多
    "not-an-ip,2026-11-01T00:00:00Z,2026-11-01T00:00:00Z,ssh,1",  # 坏 IP
    "2001:db8::1,2026-11-01T00:00:00Z,2026-11-01T00:00:00Z,ssh,1",  # 非 v4
    "1.2.3.4,not-a-time,2026-11-01T00:00:00Z,ssh,1",              # 坏时间戳
    "1.2.3.4,2026-11-01T00:00:00Z,not-a-time,ssh,1",
    "1.2.3.4,2026-11-01T00:00:00Z,2026-11-01T00:00:00Z,ssh,x",    # 坏计数
])
def test_parse_row_structural_failures_fail_loud(tmp_path, row):
    """结构坏行 raise(坏文件 fail-loud,不静默缩水;§2.3 materialize)。"""
    s = _source(tmp_path, None)
    s._window_anchor = None     # 直测行级契约,绕过 rebuild 前置
    with pytest.raises(ValueError):
        s.parse_row(row.split(","))


# ── evidence 形(查询出证)────────────────────────────────────


def test_query_evidence_shape(tmp_path):
    """验收 §6-1 基面:已知攻击 IP 出证,字段与聚合文件逐项一致。"""
    s = _source(tmp_path)
    s.rebuild()
    rec = s.query("195.178.110.218")[0]
    assert rec["classification_type"] == "scanner"   # sensor 观测槽(turris 判例)
    assert rec["verdict"] == "malicious"
    assert rec["reliability"] == 0.85
    assert rec["native_categories"] == ["ssh"]
    assert rec["first_seen"] == "2026-11-01T09:26:11Z"
    assert rec["last_seen"] == "2026-11-01T13:01:55Z"
    assert rec["extra"]["total_events"] == 962       # 「共 X 次」展示锚


def test_query_multi_service_list(tmp_path):
    s = _source(tmp_path)
    s.rebuild()
    rec = s.query("27.46.88.18")[0]
    assert rec["native_categories"] == ["mssql", "ssh"]   # ';' 拆列表


def test_rebuild_counts_keys_dq2(tmp_path):
    s = _source(tmp_path)
    assert s.rebuild() == 4
    assert s.health().record_count == 4               # DQ-2:env 键数


def test_rebuild_no_file_returns_zero(tmp_path):
    """无数据文件(dev 机 absent)rebuild=0,不炸(基类契约保持)。"""
    s = HonyportSource(data_dir=tmp_path)
    assert s.rebuild() == 0
