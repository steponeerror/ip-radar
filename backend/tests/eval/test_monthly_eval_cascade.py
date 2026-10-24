"""monthly_eval.sh 锚腿级联语义守卫(2026-10-24 终审修单 F4)。

契约(TDD 先行):--anchors 腿=回归轨判定门,失败 rc=1 时——
  ① 工件照写(anchors-*.json 落盘留证,证据不灭);
  ② 后续腿照跑(dsem/audit/temporal/readout),月报+北星照产;
  ③ 红态可见:运行日志红态行 + 脚本以捕获 rc 退出(红态外显不吞);
  ④ 其余腿 set -e 语义不变:非 anchors 腿失败仍立即中止(缺员即死,
     不推心跳,「回归红态记录不等于管线中止」只对 anchors 判定腿生效)。

守护对象是 bash 级联形状,不是 eval 数值——数值面归 test_eval_anchors.py。
harness 全密闭:临时 git 仓(master+clean 过守卫)+ PATH 桩(python3/rsync/
ssh);python3 桩按 argv 模拟各腿(anchors 按 ANCHORS_MODE 决定 rc,失败也
照写工件=anchors_report 真实形状);ssh 桩以标记文件记录心跳推送。
"""
import os
import subprocess
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "monthly_eval.sh"

PY_STUB = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    # cascade-test stub:按 argv 模拟 ipdb._eval 各腿(工件照写;rc 按 *_MODE)
    # mirror_check 步真脚本不带 IP_RADAR_EVAL_DIR → 该分支不展开工件路径
    if [[ "$*" == *"ipdb._eval.mirror_check"* ]]; then exit 0; fi
    ts="$(date -u +%Y%m%d-%H%M%S)"
    out="${IP_RADAR_EVAL_DIR:?}/monthly"
    mkdir -p "$out/model"
    ARGS="$*"  # 腿判定基准=脚本级 argv(函数内 $* 会遮蔽)
    leg() { case " $ARGS " in *" --$1 "*) return 0;; *) return 1;; esac; }
    if leg model;     then printf '{"kind":"model"}'      > "$out/model/model-$ts.json"; fi
    if leg all;       then printf '{"kind":"all"}'        > "$out/all-$ts.json"; fi
    if leg agg-share; then printf '{"kind":"agg-share"}'  > "$out/model/agg-share-$ts.json"; fi
    if leg dsem;      then printf '{"kind":"dsem"}'       > "$out/model/dsem-$ts.json"; DSEM_RC="${DSEM_MODE:-0}"; fi
    if leg audit;     then printf '{"kind":"audit"}'      > "$out/model/audit-$ts.json"; fi
    if leg temporal;  then printf '{"kind":"temporal"}'   > "$out/temporal-$ts.json"; fi
    if leg readout;   then printf '# monthly\\n'          > "$out/monthly-$ts.md"
                        printf '{"kind":"northstar"}'     > "$out/northstar-$ts.json"; fi
    if leg anchors; then
      # 18/19 红形态:判定门失败也落盘留证(anchors_report 真实形状)
      printf '{"kind":"anchors","n_fail":%s}' "${ANCHORS_MODE:-0}" > "$out/model/anchors-$ts.json"
      ANCHORS_RC="${ANCHORS_MODE:-0}"
    fi
    # future-stamp:stub 秒级跑完,同秒 mtime 会假阴 -newermt(真月轮=分钟级无此界)
    find "$out" -type f -exec touch -d "@$(( $(date +%s) + 2 ))" {} + 2>/dev/null || true
    [ "${ANCHORS_RC:-0}" = 0 ] || exit 1
    [ "${DSEM_RC:-0}" = 0 ] || exit 1
    exit 0
    """
)
RSYNC_STUB = "#!/usr/bin/env bash\nexit 0\n"
SSH_STUB = '#!/usr/bin/env bash\ntouch "${HEARTBEAT_MARKER:?}"\n'


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "backend").mkdir()
    (repo / "scripts" / "monthly_eval.sh").write_text(
        SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    run = subprocess.run(["git", "init", "-q", "-b", "master"], cwd=repo)
    assert run.returncode == 0, "git init -b master 失败(git<2.28?)"
    for k, v in (("user.email", "t@example.com"), ("user.name", "t")):
        subprocess.run(["git", "config", k, v], cwd=repo, check=True)
    (repo / "seed.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


def _make_stubs(tmp_path: Path) -> Path:
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("python3", PY_STUB), ("rsync", RSYNC_STUB), ("ssh", SSH_STUB)):
        p = stubs / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
    return stubs


def _run_monthly(repo: Path, stubs: Path, tmp_path: Path, *args: str,
                 anchors_mode: str = "0", dsem_mode: str = "0") -> tuple[int, str]:
    env = dict(os.environ)
    env["PATH"] = f"{stubs}:{env['PATH']}"
    env["EVAL_DATA_DIR"] = str(tmp_path / "data")
    env["HEARTBEAT_MARKER"] = str(tmp_path / "heartbeat-marker")
    env["ANCHORS_MODE"] = anchors_mode
    env["DSEM_MODE"] = dsem_mode
    r = subprocess.run(["bash", "scripts/monthly_eval.sh", "stub-host", *args],
                       cwd=repo, env=env, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def _report_root(repo: Path) -> Path:
    return repo / "backend" / "data" / "eval" / "monthly"


def test_bash_syntax_and_dry_run(tmp_path):
    """bash -n 语法 + --dry-run:只回显不执行,零工件零心跳。"""
    r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, f"bash -n 失败: {r.stderr}"
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, "--dry-run")
    assert rc == 0, out
    assert "==> readout:" in out          # 全腿命令面回显
    assert "[dry-run] 跳过 ssh" in out
    assert not _report_root(repo).exists()          # 零工件
    assert not (tmp_path / "heartbeat-marker").exists()  # 零心跳


def test_anchors_red_does_not_block_subsequent_legs(tmp_path):
    """锚腿 18/19 红形态:后续腿全跑、月报+北星+心跳照产、rc=1 红态外显。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, anchors_mode="1")
    assert rc == 1, f"锚红必须以 rc=1 退出(红态外显),实得 {rc}\n{out}"
    # 红态可见:运行日志显式红态行(回归红态记录≠管线中止)
    assert "红态" in out, out
    # 后续腿全跑(级联不因锚红中止)
    for leg in ("dsem", "audit", "temporal", "readout"):
        assert f"==> {leg}:" in out, f"锚红中止了后续腿 {leg}\n{out}"
    assert "完成" in out, out
    root = _report_root(repo)
    assert list(root.glob("model/anchors-*.json")), "锚红工件须照写留证"
    assert list(root.glob("monthly-*.md")), "月报须照产"
    assert list(root.glob("northstar-*.json")), "北星须照产"
    assert (tmp_path / "heartbeat-marker").exists(), "报告族齐全须照推心跳"


def test_anchors_green_round_exits_zero(tmp_path):
    """锚全绿:整轮 rc=0(红态只在真红时外显)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, anchors_mode="0")
    assert rc == 0, out
    assert (tmp_path / "heartbeat-marker").exists()
    assert list(_report_root(repo).glob("monthly-*.md"))


def test_other_leg_failure_still_aborts(tmp_path):
    """set -e 对其余腿不变:dsem 失败仍立即中止,readout/心跳不发生。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, anchors_mode="0", dsem_mode="1")
    assert rc != 0, out
    assert "==> temporal:" not in out, "非锚腿失败不得级联后续腿"
    assert "==> readout:" not in out
    assert "完成" not in out
    assert not (tmp_path / "heartbeat-marker").exists(), "半途中止不得推心跳"


def test_agg_share_leg_in_report_family(tmp_path):
    """agg-share 腿(终审修单 F6):工件落 model/ 子目录并入报告族。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    assert "==> agg-share:" in out, out
    assert list(_report_root(repo).glob("model/agg-share-*.json")), \
        "agg-share 工件缺席=报告族缺员"
