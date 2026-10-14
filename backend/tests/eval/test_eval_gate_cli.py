# backend/tests/eval/test_eval_gate_cli.py
"""CLI 接线 smoke(T9): --gate/--canary/--sentinel 子命令 —— 只测接线不测库件。

库件(gate/canary/sentinel/gate_mirror)各有单测;本文件 fake reg + stub
runner 断言 CLI 面(零网络零真 DB):
- 参数解析与报告产出(gate-*/canary-* 落 base/gate 命名空间);
- 镜像前置序(S7): ensure_gate_mirror 先于 run_gate,参数从 env 读;失配 →
  rc=3 拒跑且不产 gate 报告(fail-closed);
- EVAL_ENV=gate 强制(S37): 未设 → CLI 钉 gate(报告目录/嵌套 stratum 件
  标签随钉, 进程内退出还原);显式 monthly/dev → fail-loud 拒跑且不触镜像;
- 退出码契约: sentinel pass=True→0 / pass=False→1 / N/A(geo_asn)→0+N/A
  说明行 + coverage_check 信息行(materialize_source.sh 透传本 rc);canary
  all_match=False → rc≠0 但报告照写;
- run_seed 纪律照 T2: CLI 可显式传(--run-seed), 缺省名派生稳定。
"""
import json
import os
from pathlib import Path

import pytest

import ipdb._eval.__main__ as M
import ipdb._eval.gate_mirror as gm
from ipdb._eval.corpus import stable_seed
from ipdb._eval.gate_mirror import GateMirrorMisalignedError

_CAND_IPS = [f"10.99.0.{i}" for i in range(1, 31)]   # ≥ N_FLOOR, 25 成员足采 20
_GS = [f"10.77.0.{i}" for i in range(1, 26)]         # greensnow 判例成员
_TF = [f"10.78.0.{i}" for i in range(1, 26)]         # threatfox 判例成员


class _FakeSource:
    """真 .name/.category/.fields/._path/.query/.health —— sentinel 采样与
    coverage_check、canary 探针、gate 键集/健康读的链上真源对象契约
    (test_eval_gate/_sentinel 同款最小面)。"""

    def __init__(self, name, path, category="threat", fields=(), answers=None,
                 rc=1000):
        self.name = name
        self.category = category
        self.fields = tuple(fields)
        self._path = path
        self._answers = answers if answers is not None else {}
        self._rc = rc

    def query(self, ip):
        return self._answers.get(ip)      # None = 不可回查(coverage_check 口径)

    def health(self):
        from types import SimpleNamespace
        return SimpleNamespace(record_count=self._rc, is_stale=False)


class _FakeRegistry:
    """指控布局 {源名: IP 集}: 启停可见(gate 消融/canary 复跑同一 toggle
    语义);载荷 = to_dict 生产契约(metrics 读 sources[], layered 读组级
    verdict+details[])。lookup 可注入替身(geo_asn 零查询证明)。"""

    def __init__(self, sources, accusing=None, lookup=None):
        self.sources = sources
        self._accusing = accusing or {}
        self._lookup = lookup
        self.disabled = set()

    def lookup(self, ip):
        if self._lookup is not None:
            return self._lookup(ip)
        acc = [s.name for s in self.sources if s.name not in self.disabled
               and ip in self._accusing.get(s.name, ())]
        if not acc:
            return {"ip": ip, "classifications": {}}
        return {"ip": ip, "classifications": {"phishing": {
            "type": "phishing", "verdict": "malicious", "verdict_conflict": False,
            "confidence": 50,
            "details": [{"source": s, "verdict": "malicious"} for s in acc],
            "sources": [{"source": s} for s in acc]}}}

    def toggle(self, name, enabled):
        self.disabled = ((self.disabled - {name}) if enabled
                         else (self.disabled | {name}))

    def load_db(self):
        pass


class _FakeBenign:
    """离线假 checker(run_for_source 同款 DI, 免真 warninglists 加载)。"""

    def overall_hit_pct(self, ips):
        return 0.0

    def hit_pct(self, ips):
        return {}


def _src_file(tmp_path, name, ips):
    p = tmp_path / f"{name}.txt"
    p.write_text("\n".join(ips) + "\n")
    return p


def _gate_env(tmp_path, monkeypatch):
    """CLI 运行环境: 报告根 tmp(IP_RADAR_EVAL_DIR → base/gate), EVAL_ENV
    未设 —— CLI 须自钉 gate(S37);真镜像/真 registry 全替身化。"""
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    monkeypatch.delenv("IP_RADAR_EVAL_ENV", raising=False)


def _stub_mirror(monkeypatch, misaligned=False):
    """ensure_gate_mirror 替身: 记录(prod_host, mirror_dir) 调用序;
    misaligned=True 时 raise(S7 fail-closed 路径)。"""
    calls = []

    def stub(prod_host, mirror_dir, **kw):
        calls.append((prod_host, Path(mirror_dir)))
        if misaligned:
            raise GateMirrorMisalignedError("cand.lmdb.ptr: mirror=1 prod=2")
        return {"alignment": {"aligned": True, "detail": "aligned"}}

    monkeypatch.setattr(gm, "ensure_gate_mirror", stub)
    return calls


def _patch_registry(monkeypatch, reg):
    monkeypatch.setattr(M, "_real_registry", lambda: reg)
    monkeypatch.setattr(M, "BenignChecker", lambda: _FakeBenign())


# ── --gate ─────────────────────────────────────────────────────


def test_gate_cli_mirror_then_report(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    calls = _stub_mirror(monkeypatch)
    # 镜像参数从 env 读(决策 1: 不发明新配置面)
    monkeypatch.setenv("IP_RADAR_GATE_PROD_HOST", "root@stub")
    monkeypatch.setenv("IP_RADAR_GATE_MIRROR_DIR", str(tmp_path / "mirror"))
    reg = _FakeRegistry(
        [_FakeSource("cand", _src_file(tmp_path, "cand", _CAND_IPS))],
        {"cand": set(_CAND_IPS)})
    _patch_registry(monkeypatch, reg)
    assets = tmp_path / "assets"          # 空资产根 → 四层 NO-LAYER 哨兵(报告照发)
    M.main(["--gate", "cand", "--run-seed", "7", "--assets-dir", str(assets)])
    # 镜像前置恰一次, 参数 = env 解析值
    assert calls == [("root@stub", tmp_path / "mirror")]
    out = tmp_path / "gate"               # env 钉 → call-time report_dir() = base/gate
    md = next(out.glob("gate-cand-*.md"))
    payload = json.loads(next(out.glob("gate-cand-*.json")).read_text())
    assert payload["eval_env"] == "gate" and payload["run_seed"] == 7
    assert payload["deltas"]["truth"] is None       # NO-LAYER 哨兵透传(缺层≠0 层)
    nested = json.loads(next(out.glob("cand-*.json")).read_text())
    assert nested["eval_env"] == "gate"             # 嵌套 stratum 件不串 dev
    stdout = capsys.readouterr().out
    assert "verdict=" in stdout and str(md) in stdout
    assert os.environ.get("IP_RADAR_EVAL_ENV") is None   # 进程内钉退出还原


def test_gate_cli_mirror_misaligned_refuses(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    _stub_mirror(monkeypatch, misaligned=True)
    reg = _FakeRegistry(
        [_FakeSource("cand", _src_file(tmp_path, "cand", _CAND_IPS))])
    _patch_registry(monkeypatch, reg)
    with pytest.raises(SystemExit) as e:
        M.main(["--gate", "cand"])
    assert e.value.code == 3              # rc=3 = 镜像前置族(与通用 rc=1 区分)
    assert not (tmp_path / "gate").exists()   # fail-closed: gate 根本没跑
    err = capsys.readouterr().err
    assert "S7" in err and "拒跑" in err
    with pytest.raises(SystemExit) as e2:  # --json: stdout JSON 信封 + 同 rc(§5.2)
        M.main(["--gate", "cand", "--json"])
    assert e2.value.code == 3
    env = json.loads(capsys.readouterr().out)
    assert env["error"]["code"] == "gate_mirror_misaligned"


def test_gate_cli_env_mislabel_fails_loud_before_mirror(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "monthly")   # 显式错位 → 拒跑
    calls = _stub_mirror(monkeypatch)
    _patch_registry(monkeypatch, _FakeRegistry([]))
    with pytest.raises(SystemExit) as e:
        M.main(["--gate", "cand"])
    assert e.value.code == 1
    assert calls == []                    # env 错位先拒, 不触镜像(零网络副作用)
    assert not (tmp_path / "gate").exists()


# ── --canary ───────────────────────────────────────────────────


def _canary_reg(tmp_path, takeover=True):
    """greensnow 结构性零布局: firehol(谱系锚顶班源)恒指控同一集 ——
    greensnow 关掉 → firehol 顶班 → 舰队命中集 ON/OFF 不变(takeover=False
    即撤顶班 → fleet_hit_delta≠0 → 判例失配)。"""
    srcs = [_FakeSource("greensnow", _src_file(tmp_path, "greensnow", _GS)),
            _FakeSource("threatfox", _src_file(tmp_path, "threatfox", _TF))]
    accusing = {"greensnow": set(_GS), "threatfox": set(_TF)}
    if takeover:
        srcs.append(_FakeSource("firehol", _src_file(tmp_path, "firehol", _GS)))
        accusing["firehol"] = set(_GS)
    return _FakeRegistry(srcs, accusing)


def test_canary_cli_all_match_exit_zero(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, _canary_reg(tmp_path))
    with pytest.raises(SystemExit) as e:
        M.main(["--canary"])
    assert e.value.code == 0
    assert next((tmp_path / "gate").glob("canary-*.md")).is_file()
    stdout = capsys.readouterr().out
    assert "all_match=True" in stdout and "2/2 判例复现" in stdout


def test_canary_cli_mismatch_exit_nonzero_report_written(
        tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, _canary_reg(tmp_path, takeover=False))
    with pytest.raises(SystemExit) as e:
        M.main(["--canary"])
    assert e.value.code == 1              # 告警可见(rc≠0);报告照写(证据不灭)
    assert next((tmp_path / "gate").glob("canary-*.md")).is_file()
    stdout = capsys.readouterr().out
    assert "all_match=False" in stdout and "流程腐化告警" in stdout


def test_canary_cli_env_mislabel_fails_loud(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_EVAL_DIR", str(tmp_path))
    monkeypatch.setenv("IP_RADAR_EVAL_ENV", "dev")      # 显式错位 → 拒跑
    _patch_registry(monkeypatch, _canary_reg(tmp_path))
    with pytest.raises(SystemExit) as e:
        M.main(["--canary"])
    assert e.value.code == 1
    assert not (tmp_path / "gate").exists()


# ── --sentinel ─────────────────────────────────────────────────


def test_sentinel_cli_pass_exit_zero(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    reg = _FakeRegistry(
        [_FakeSource("cand", _src_file(tmp_path, "cand", _CAND_IPS))],
        {"cand": set(_CAND_IPS)})
    _patch_registry(monkeypatch, reg)
    with pytest.raises(SystemExit) as e:
        M.main(["--sentinel", "cand"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "pass=True" in out and "20/20" in out
    assert f"seed={stable_seed('cand')}" in out   # 缺省 seed 名派生稳定(T2 纪律)


def test_sentinel_cli_fail_exit_one_lists_probes(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    reg = _FakeRegistry(                 # 25 成员仅 15 可指控 → 采 20 必有失配
        [_FakeSource("cand", _src_file(tmp_path, "cand", _CAND_IPS))],
        {"cand": set(_CAND_IPS[:15])})
    _patch_registry(monkeypatch, reg)
    with pytest.raises(SystemExit) as e:
        M.main(["--sentinel", "cand"])
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "pass=False" in out and "FAIL" in out and "not-accused" in out


def test_sentinel_cli_geo_asn_na_exit_zero_with_coverage(
        tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)

    def boom(ip):
        raise AssertionError("geo_asn 通道不得回查融合引擎(S13 非目标)")

    ips = [f"10.66.0.{i}" for i in range(1, 6)]
    src = _FakeSource("iptoasn", _src_file(tmp_path, "iptoasn", ips),
                      category="geo_asn",
                      answers={ip: {"asn": 64512} for ip in ips})
    _patch_registry(monkeypatch, _FakeRegistry([src], lookup=boom))
    with pytest.raises(SystemExit) as e:
        M.main(["--sentinel", "iptoasn"])
    assert e.value.code == 0              # N/A ≠ 失败: rc 0 + 说明行
    out = capsys.readouterr().out
    assert "status=N/A" in out
    assert "coverage_check" in out and "100.00%" in out   # 键集口径信息行


def test_sentinel_cli_run_seed_passthrough(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    reg = _FakeRegistry(
        [_FakeSource("cand", _src_file(tmp_path, "cand", _CAND_IPS))],
        {"cand": set(_CAND_IPS)})
    _patch_registry(monkeypatch, reg)
    with pytest.raises(SystemExit) as e:
        M.main(["--sentinel", "cand", "--run-seed", "1234"])
    assert e.value.code == 0
    assert "seed=1234" in capsys.readouterr().out   # run 级 seed CLI 可显式传


def test_sentinel_cli_json_envelope(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    reg = _FakeRegistry(
        [_FakeSource("cand", _src_file(tmp_path, "cand", _CAND_IPS))],
        {"cand": set(_CAND_IPS)})
    _patch_registry(monkeypatch, reg)
    with pytest.raises(SystemExit) as e:
        M.main(["--sentinel", "cand", "--json"])
    assert e.value.code == 0
    payload = json.loads(capsys.readouterr().out)   # stdout 恰一 JSON 对象
    assert payload["pass"] is True and payload["channel"] == "threat"
    assert "coverage_check" in payload              # N/A 分派键恒在(缺省 null)


def test_sentinel_cli_unknown_source(tmp_path, monkeypatch, capsys):
    _gate_env(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, _FakeRegistry([]))
    with pytest.raises(SystemExit) as e:
        M.main(["--sentinel", "zzz_no_such"])
    assert e.value.code == 2
    assert "no source named" in capsys.readouterr().err
