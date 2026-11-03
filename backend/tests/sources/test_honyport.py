"""honyport 自建蜜罐观测源(spec 2026-11-02 §2.3,issue #272)。

样例 = §2.1 冻结聚合格式的 verbatim-shaped 件(头 5 注释行 + 列头 +
真实观测行;IP/计数取自主检出 dev/honyport-fixtures/ 两天真件,2026-11-02
榜首 14.112.37.157 MSSQL 11,663 次 / 195.178.110.218 SSH)。覆盖:
- download:目录缺席静默 absent(开发机不受扰);目录在场取最新合法件
  原子拷入;目录在场无合法件 fail-loud(cron 断供可见);
- materialize:列头逐字断言 + generated_at 解析(坏文件 fail-loud);
- 载入侧 30d 硬窗(相对 generated_at 日 = 文件名日):超窗行拒入;
- evidence 形:native_categories=services 列表、last_seen 富槽、
  total_events → extra(route_record 折入),reliability=0.85;
- DQ-2:record_count = env 主库键数。
- 二期 techniques(spec 2026-11-03 §1/§3,issue #282):双件下载、
  extra.techniques 八字段契约、CVE 提取、回声禁令(JSON services
  不整列表出海)、坏件 fail-loud、缺 JSON 容忍、基座缺席不补行。
  真样例锚 2026-11-03 自服务器 /opt/honyport/out 取样(verbatim,
  dev/honyport-fixtures/ 留两真件):109.105.210.2 CVE 件(11-03 件
  逐字,真服务器聚合 CSV 中该 IP 被 scanner 过滤不在基座 —— 测试
  基座构造其 CSV 行以钉合并路径)+ 195.178.110.218 commands 件
  (11-02 件逐字,命令取锚两条)。
"""
import json
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


def test_source_decl_pins():
    """元数据逐字钉(#272 评审 P2-2):stale_days 无测试钉,防规格漂移。"""
    assert HonyportSource.stale_days == 2
    assert HonyportSource.name == "honyport"


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


# ── 二期 techniques JSON(spec 2026-11-03 §1/§3,issue #282)──────

# CVE 件真样例(109.105.210.2,服务器 2026-11-03 件逐字):services 元素
# 「事件id/CVE1,CVE2」形态 —— CVE 提取锚;真服务器聚合 CSV 该 IP 被
# scanner 过滤不在基座,测试基座特构造其行钉合并路径。
_TECH_CVE_ENTRY = {
    "events": 1,
    "first_seen": "2026-11-02T17:10:02.599Z",
    "last_seen": "2026-11-02T17:10:02.599Z",
    "services": ["php2shell-2026/CVE-2026-109618,CVE-2026-109619"],
    "protocols": ["http"],
    "commands": [],
    "statuses": [],
    "actions": ["http_request"],
    "stages": ["probe"],
    "paths": ["/bitsight/internet_census/probe"],
    "user_agents": ["python-requests/2.31.0"],
}

# commands 件真样例(195.178.110.218,服务器 2026-11-02 件,SSH 矿机
# 探测;命令截锚两条,余字段逐字)——「萤罐id/服务」形态锚(beelzebub/ssh)
_TECH_SSH_ENTRY = {
    "events": 481,
    "first_seen": "2026-11-01T09:26:11Z",
    "last_seen": "2026-11-01T13:01:55Z",
    "services": ["beelzebub/ssh"],
    "protocols": ["SSH"],
    "commands": ["/bin/./uname -s -v -n -r -m",
                 "lspci | grep \"3D controller\" | cut -f5- -d ' '"],
    "statuses": ["Start", "Stateless"],
    "actions": [],
    "stages": [],
    "paths": [],
    "user_agents": [],
}

# 基座扩展:AGGREGATE + 109.105.210.2 行(时间戳取 11-03 件,窗口内)
AGGREGATE_TECH = AGGREGATE + (
    "109.105.210.2,2026-11-02T17:10:02Z,2026-11-02T17:10:02Z,http,1\n")


def _techniques_json(ips: dict) -> str:
    return json.dumps({"date": "2026-11-02", "ips": ips},
                      ensure_ascii=False)


def _tech_source(tmp_path: Path,
                 ips: dict | None = None) -> HonyportSource:
    """CSV 基座 + techniques JSON 落 data_dir(模拟 download 后状态)。"""
    s = _source(tmp_path, AGGREGATE_TECH)
    if ips is None:
        ips = {"109.105.210.2": _TECH_CVE_ENTRY,
               "195.178.110.218": _TECH_SSH_ENTRY}
    (tmp_path / "honyport_techniques.json").write_text(
        _techniques_json(ips), encoding="utf-8")
    return s


# ── download 双件(§3:CSV 基座 + techniques JSON 原子拷入)────────


def test_download_copies_latest_techniques_json(tmp_path, monkeypatch):
    """双件下载:CSV 照旧 + 最新合法 techniques JSON(文件名日期挑最新,
    与一期同法)原子拷入 data_dir 稳定名。"""
    good = _techniques_json({"109.105.210.2": _TECH_CVE_ENTRY,
                             "195.178.110.218": _TECH_SSH_ENTRY})
    monkeypatch.setenv(AGGREGATE_DIR_ENV, str(_agg_dir(tmp_path, {
        "honeypot-observed-2026-11-02.csv": AGGREGATE,
        "honeypot_techniques-2026-11-01.json": '{"date": "2026-11-01", "ips": {}}',
        "honeypot_techniques-2026-11-02.json": good,
        "scratch.tmp": "不匹配名样不参与",
    })))
    s = HonyportSource(data_dir=tmp_path)
    s.download()
    assert (tmp_path / "honyport_techniques.json").read_text(
        encoding="utf-8") == good                          # 最新件逐字节
    assert s._path.read_text(encoding="utf-8") == AGGREGATE  # 基座照旧


def test_download_without_techniques_json_phase1_unchanged(
        tmp_path, monkeypatch):
    """有 CSV 无 JSON → 一期行为不变(§3 容忍):不抛、件不落、查询
    evidence 形状与一期逐字节一致。"""
    monkeypatch.setenv(AGGREGATE_DIR_ENV, str(_agg_dir(tmp_path, {
        "honeypot-observed-2026-11-02.csv": AGGREGATE})))
    s = HonyportSource(data_dir=tmp_path)
    s.download()                                           # 不抛
    assert not (tmp_path / "honyport_techniques.json").exists()
    assert s.rebuild() == 4
    assert "techniques" not in s.query("195.178.110.218")[0]["extra"]


def test_download_techniques_without_csv_base_fails_loud(
        tmp_path, monkeypatch):
    """挂载目录只有 JSON 无合法 CSV → 基座缺席 fail-loud(JSON 不救场:
    基座是出海必要条件)。"""
    monkeypatch.setenv(AGGREGATE_DIR_ENV, str(_agg_dir(tmp_path, {
        "honeypot_techniques-2026-11-02.json": _techniques_json({})})))
    s = HonyportSource(data_dir=tmp_path)
    with pytest.raises(RuntimeError, match="no valid honeypot-observed"):
        s.download()


# ── extra.techniques 契约(§3 八字段冻结 + 回声禁令)────────────


def test_query_techniques_cve_shape(tmp_path):
    """CVE 件:八字段冻结集合;cves = 剥事件 id 前缀逗号拆分;回声禁令
    = JSON services 整列表不出海(php2shell-2026 事件 id 也不出海)。"""
    s = _tech_source(tmp_path)
    s.rebuild()
    rec = s.query("109.105.210.2")[0]
    tech = rec["extra"]["techniques"]
    assert set(tech) == {"commands", "user_agents", "cves", "protocols",
                         "statuses", "actions", "stages", "paths"}
    assert tech["cves"] == ["CVE-2026-109618", "CVE-2026-109619"]
    assert tech["user_agents"] == ["python-requests/2.31.0"]
    assert tech["paths"] == ["/bitsight/internet_census/probe"]
    assert tech["actions"] == ["http_request"]
    assert tech["stages"] == ["probe"]
    assert rec["extra"]["total_events"] == 1            # 基座槽不变
    blob = json.dumps(rec, ensure_ascii=False, default=str)
    assert "php2shell-2026" not in blob                 # 回声禁令:services 不出海
    assert '"services"' not in blob                     # 键也不出海


def test_query_techniques_commands_shape(tmp_path):
    """commands 件:命令逐字保留(真样例锚);「萤罐id/服务」形态
    (beelzebub/ssh)不产 CVE;protocols/statuses 原样出海。"""
    s = _tech_source(tmp_path)
    s.rebuild()
    rec = s.query("195.178.110.218")[0]
    tech = rec["extra"]["techniques"]
    assert tech["commands"] == [
        "/bin/./uname -s -v -n -r -m",
        'lspci | grep "3D controller" | cut -f5- -d \' \'']
    assert tech["cves"] == []                           # beelzebub/ssh → 无 CVE 词形
    assert tech["protocols"] == ["SSH"]
    assert tech["statuses"] == ["Start", "Stateless"]
    assert tech["commands"] is not _TECH_SSH_ENTRY["commands"]  # 拷贝非引用
    blob = json.dumps(rec, ensure_ascii=False, default=str)
    assert "beelzebub" not in blob                      # 回声禁令:萤罐 id 不出海


def test_techniques_ip_not_in_csv_base_not_emitted(tmp_path):
    """JSON 有而 CSV 基座无该 IP → 不出海(§3:基座缺席不补行)。"""
    s = _tech_source(tmp_path, ips={"203.0.113.9": dict(_TECH_CVE_ENTRY)})
    assert s.rebuild() == 5                              # 基座行数不变
    assert s.query("203.0.113.9") == {}


def test_csv_ip_without_techniques_entry_shape_unchanged(tmp_path):
    """CSV 有而 JSON 无该 IP → 一期 evidence 形状不变(techniques 键
    整体缺席,不填空 dict)。"""
    s = _tech_source(tmp_path, ips={"195.178.110.218": dict(_TECH_SSH_ENTRY)})
    s.rebuild()
    rec = s.query("14.112.37.157")[0]
    assert rec["extra"] == {"total_events": 11663}      # 一期形状逐字节


# ── 坏 techniques JSON fail-loud(§3 容忍与报错)─────────────────


def test_rebuild_techniques_missing_keys_fails_loud(tmp_path):
    """缺 date / ips 键 = 坏件 fail-loud(格式冻结 §1)。"""
    for bad in ('{"ips": {}}', '{"date": "2026-11-02"}'):
        s = _tech_source(tmp_path)
        (tmp_path / "honyport_techniques.json").write_text(bad)
        with pytest.raises(RuntimeError, match="date/ips"):
            s.rebuild()


@pytest.mark.parametrize("date_value",
                         ["2026-13-45", "not-a-date", "20261102"])
def test_rebuild_techniques_bad_date_fails_loud(tmp_path, date_value):
    """坏日期(非法日历 / 非 YYYY-MM-DD 形)fail-loud;紧缩形 20261102
    也拒 —— 名样即格式,不收 fromisoformat 宽形。"""
    s = _tech_source(tmp_path)
    (tmp_path / "honyport_techniques.json").write_text(
        json.dumps({"date": date_value, "ips": {}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="bad date"):
        s.rebuild()


@pytest.mark.parametrize("mutate", ["drop", "add"])
def test_rebuild_techniques_ip_keyset_drift_fails_loud(tmp_path, mutate):
    """per-IP 键集漂移(缺键/多键)= 坏件 fail-loud(§1 冻结集逐字断言)。"""
    entry = dict(_TECH_CVE_ENTRY)
    if mutate == "drop":
        entry.pop("paths")
    else:
        entry["note"] = "x"
    s = _tech_source(tmp_path, ips={"109.105.210.2": entry})
    with pytest.raises(RuntimeError, match="key set mismatch"):
        s.rebuild()


def test_rebuild_techniques_bad_json_fails_loud(tmp_path):
    s = _tech_source(tmp_path)
    (tmp_path / "honyport_techniques.json").write_text(
        "{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="cannot parse"):
        s.rebuild()


def test_extract_cves_forms():
    """services 两形态:「事件id/CVE 列表」剥前缀逗号拆分(去重保序);
    「萤罐id/服务」与无斜杠元素自然落空(宁少算:同 CVE 不双计)。"""
    extract = HonyportSource._extract_cves
    assert extract(["php2shell-2026/CVE-2026-109618,CVE-2026-109619"]) == [
        "CVE-2026-109618", "CVE-2026-109619"]
    assert extract(["beelzebub/ssh", "mssql"]) == []
    assert extract(["e1/CVE-2026-109618",
                    "e2/CVE-2026-109618"]) == ["CVE-2026-109618"]
