# backend/tests/eval/test_eval_reader_multidir.py
"""#453 读写同规:读侧并看 根/monthly/dev 三处,gate/ 不进,只认形状
+ source 键双闸。摆法按工单验收:根目录旧件 + monthly/ 两轮 + dev/ 一份
+ gate/ 一份 + 观测件(leg-status-*/action-block/mirror-manifest/
northstar-*/temporal-* + 一个坏 JSON)。
观测件语义:northstar-<run_id>.json / temporal-<ts>.json 文件名撞逐源
形状但内容无 "source" 键(2026-11-25 本机 monthly/ 实测)——纯形状过滤
会让 read_overview 冒 unknown 行,故有第二道内容闸(出处见 _eval_reader
模块头)。
"""
import json


def _write_report(d, source, at, ts, state):
    """按 report.py 实测 schema 写最小自洽逐源报告(文件名秒级 ts)。"""
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{source}-{at.replace('-', '')}-{ts}.json").write_text(json.dumps({
        "source": source,
        "generated_at": at,
        "verdict": {"state": state, "action": "keep"},
        "metrics": {"MC": {"value": 0.1, "n": 9}},
    }), encoding="utf-8")


def _layout(tmp_path):
    """工单验收摆法:返回 {源: 最新期望 verdict} 供断言。"""
    # 根目录:S37 前平铺旧件(2026-10-01)
    _write_report(tmp_path, "spamhaus", "2026-10-01", "010101",
                  "POSITIVE-UNVERIFIED")
    # monthly/:两轮
    _write_report(tmp_path / "monthly", "spamhaus", "2026-11-01", "010101",
                  "POSITIVE-UNVERIFIED")
    _write_report(tmp_path / "monthly", "spamhaus", "2026-11-25", "010101",
                  "POSITIVE-VERIFIED")
    _write_report(tmp_path / "monthly", "otx", "2026-11-25", "020202",
                  "NEGATIVE-DEPRIORITIZE")
    # dev/:同日更晚 ts → 跨目录最新是这份
    _write_report(tmp_path / "dev", "otx", "2026-11-25", "030303", "MARGINAL")
    # gate/:若读侧误扫,spamhaus 最新会变成这份(GATE-ONLY 独有判别词)
    _write_report(tmp_path / "gate", "spamhaus", "2026-11-30", "010101",
                  "GATE-ONLY")
    # 观测件(monthly/ 实测同款):全部不得当报告
    mon = tmp_path / "monthly"
    (mon / "leg-status-20261125-130220.json").write_text(
        json.dumps({"schema": "leg-status/1", "legs": {}}), encoding="utf-8")
    (mon / "action-block.json").write_text(
        json.dumps({"header": {}, "items": []}), encoding="utf-8")
    (mon / "mirror-manifest.json").write_text(
        json.dumps({"files": 1, "epoch": "e"}), encoding="utf-8")
    # 撞逐源形状但无 source 键的观测件(#453 内容闸的存在理由)
    (mon / "northstar-20261125-125951.json").write_text(
        json.dumps({"kind": "northstar", "generated_at": "2026-11-25"}),
        encoding="utf-8")
    (mon / "temporal-20261101-120000.json").write_text(
        json.dumps({"kind": "temporal", "generated_at": "2026-11-01"}),
        encoding="utf-8")
    # 坏 JSON:形状匹配但半写 → 跳过不炸端点
    (mon / "broken-20261125-000000.json").write_text('{"source": "bro', encoding="utf-8")
    # 模型报告:根 model/ 旧位置但 generated_at 更新(#453 跨目录取最新)
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "model-20261130-000000.json").write_text(
        json.dumps({"kind": "model", "generated_at": "2026-11-30", "w": 30}),
        encoding="utf-8")
    ((mon / "model")).mkdir()
    (mon / "model" / "model-20261125-000000.json").write_text(
        json.dumps({"kind": "model", "generated_at": "2026-11-25", "w": 25}),
        encoding="utf-8")


def test_overview_latest_across_dirs_without_observations(tmp_path, monkeypatch):
    """每源取跨目录最新;gate/ 不出现;观测件/坏件不冒 unknown 等伪源。"""
    from ipdb._eval_reader import read_overview
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    _layout(tmp_path)
    overview = read_overview()
    by = {v["source"]: v for v in overview}
    assert set(by) == {"spamhaus", "otx"}, overview   # 无 unknown/northstar/temporal
    # spamhaus:monthly 11-25 最新(gate 11-30 不得出现)
    assert by["spamhaus"]["verdict"] == "POSITIVE-VERIFIED"
    assert by["spamhaus"]["at"] == "2026-11-25"
    # otx:dev 同日更晚 ts 胜过 monthly
    assert by["otx"]["verdict"] == "MARGINAL"
    assert by["otx"]["at"] == "2026-11-25"


def test_source_history_merges_dirs_sorted(tmp_path, monkeypatch):
    """read_source 历史跨目录合并后升序;gate/ 的记录不进历史。"""
    from ipdb._eval_reader import read_source
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    _layout(tmp_path)
    d = read_source("spamhaus")
    assert d["history"] == [
        {"at": "2026-10-01", "verdict": "POSITIVE-UNVERIFIED"},   # 根目录旧件
        {"at": "2026-11-01", "verdict": "POSITIVE-UNVERIFIED"},   # monthly 前轮
        {"at": "2026-11-25", "verdict": "POSITIVE-VERIFIED"},     # monthly 本轮
    ]
    assert d["latest"]["verdict"]["state"] == "POSITIVE-VERIFIED"
    # otx:monthly 与 dev 同日两轮,ts 升序
    o = read_source("otx")
    assert [(h["at"], h["verdict"]) for h in o["history"]] == [
        ("2026-11-25", "NEGATIVE-DEPRIORITIZE"),
        ("2026-11-25", "MARGINAL"),
    ]
    assert o["latest"]["verdict"]["state"] == "MARGINAL"


def test_read_model_across_model_dirs(tmp_path, monkeypatch):
    """read_model 跨 根/monthly 的 model/ 取 (generated_at, 文件名) 最新;
    monthly/model/ 里能读到,根 model/ 更新时取根的。"""
    from ipdb._eval_reader import read_model
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    _layout(tmp_path)
    assert read_model()["w"] == 30          # 根 model/ 旧件更新 → 取旧位置这份


def test_read_model_monthly_newer_than_root(tmp_path, monkeypatch):
    """生产方向(评审补):根 model/ 是 S37 前的旧件、monthly/model/ 是月轮
    新件 → 取 monthly 的。改前读侧只读根 model/,会取到旧件。"""
    from ipdb._eval_reader import read_model
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    (tmp_path / "model").mkdir()
    (tmp_path / "model" / "model-20261010-000000.json").write_text(
        json.dumps({"kind": "model", "generated_at": "2026-10-10", "w": 10}),
        encoding="utf-8")
    mon = tmp_path / "monthly" / "model"
    mon.mkdir(parents=True)
    (mon / "model-20261125-000000.json").write_text(
        json.dumps({"kind": "model", "generated_at": "2026-11-25", "w": 25}),
        encoding="utf-8")
    assert read_model()["w"] == 25


def test_read_model_monthly_only(tmp_path, monkeypatch):
    """根 model/ 缺席时 monthly/model/ 照样读得到(S37 后唯一写位)。"""
    from ipdb._eval_reader import read_model
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    mon = tmp_path / "monthly" / "model"
    mon.mkdir(parents=True)
    (mon / "model-20261125-000000.json").write_text(
        json.dumps({"kind": "model", "generated_at": "2026-11-25", "w": 25}),
        encoding="utf-8")
    assert read_model()["w"] == 25


def test_empty_and_missing_dirs(tmp_path, monkeypatch):
    """根缺席 → 无话;只有根(无子目录)行为同旧(S37 前平铺兼容)。"""
    from ipdb._eval_reader import read_overview, read_model
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path / "nope"))
    assert read_overview() == []
    assert read_model() is None
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    _write_report(tmp_path, "solo", "2026-09-01", "000000", "MARGINAL")
    assert [v["source"] for v in read_overview()] == ["solo"]
