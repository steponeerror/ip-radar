"""monthly_eval.sh 锚腿级联语义守卫(2026-10-24 终审修单 F4)。

契约(TDD 先行,#193 C5 全腿版,承 2026-10-24 F4 anchors 判例推广):
  ① 任一腿红(model/all/anchors/dsem/audit/temporal/readout)不中止
     后续腿,工件照写留证(证据不灭);
  ② 红态可见三面:运行日志红态行 + 腿级状态件 leg-status-*.json
     (机器可读,报告根)+ 结尾以腿序首个非零 rc 退出(红态外显不吞);
  ③ 心跳照推:腿级红≠缺员,报告族齐全(工件在场)即活;缺员即死
     不变(工件缺席的腿=半途中止=死,不推心跳);
  ④ leg-status-*.json 不得顶替 all 腿工件(报告族 all 模式须排除
     本件,观测件永不触活族门);
  ⑤ mirror-check/rsync 守卫不变(数据面先于读数面,塔缩即止)。

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
    if leg model;     then printf '{"kind":"model"}'      > "$out/model/model-$ts.json"; MODEL_RC="${MODEL_MODE:-0}"; fi
    if leg all;       then if [ "${ALL_SKIP:-0}" != 1 ]; then printf '{"kind":"all"}' > "$out/all-$ts.json"; ALL_RC="${ALL_MODE:-0}"; fi; fi
    if leg agg-share; then printf '{"kind":"agg-share"}'  > "$out/model/agg-share-$ts.json"; fi
    if leg dsem;      then printf '{"kind":"dsem"}'       > "$out/model/dsem-$ts.json"; DSEM_RC="${DSEM_MODE:-0}"; fi
    if leg audit;     then printf '{"kind":"audit"}'      > "$out/model/audit-$ts.json"; AUDIT_RC="${AUDIT_MODE:-0}"; fi
    if leg temporal;  then printf '{"kind":"temporal"}'   > "$out/temporal-$ts.json"; TEMPORAL_RC="${TEMPORAL_MODE:-0}"; fi
    if leg readout;   then printf '# monthly\\n'          > "$out/monthly-$ts.md"
                        printf '{"kind":"northstar"}'     > "$out/northstar-$ts.json"; READOUT_RC="${READOUT_MODE:-0}"; fi
    if leg anchors; then
      # 18/19 红形态:判定门失败也落盘留证(anchors_report 真实形状)
      printf '{"kind":"anchors","n_fail":%s}' "${ANCHORS_MODE:-0}" > "$out/model/anchors-$ts.json"
      ANCHORS_RC="${ANCHORS_MODE:-0}"
    fi
    # future-stamp:stub 秒级跑完,同秒 mtime 会假阴 -newermt(真月轮=分钟级无此界)
    find "$out" -type f -exec touch -d "@$(( $(date +%s) + 2 ))" {} + 2>/dev/null || true
    # 腿 rc 聚合退出(红腿外显自身 rc;#193 各腿不再互断)
    for v in MODEL_RC ALL_RC ANCHORS_RC DSEM_RC AUDIT_RC TEMPORAL_RC READOUT_RC; do
      [ "${!v:-0}" = 0 ] || exit "${!v}"
    done
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
                 anchors_mode: str = "0", dsem_mode: str = "0",
                 model_mode: str = "0", all_mode: str = "0",
                 audit_mode: str = "0", temporal_mode: str = "0",
                 readout_mode: str = "0", all_skip: bool = False,
                 ) -> tuple[int, str]:
    env = dict(os.environ)
    env["PATH"] = f"{stubs}:{env['PATH']}"
    env["EVAL_DATA_DIR"] = str(tmp_path / "data")
    env["HEARTBEAT_MARKER"] = str(tmp_path / "heartbeat-marker")
    env["ANCHORS_MODE"] = anchors_mode
    env["DSEM_MODE"] = dsem_mode
    env["MODEL_MODE"] = model_mode
    env["ALL_MODE"] = all_mode
    env["AUDIT_MODE"] = audit_mode
    env["TEMPORAL_MODE"] = temporal_mode
    env["READOUT_MODE"] = readout_mode
    env["ALL_SKIP"] = "1" if all_skip else "0"
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


def _latest_leg_status(root: Path) -> dict:
    import json as _json
    files = sorted(root.glob("leg-status-*.json"))
    assert files, "leg-status 工件缺席"
    return _json.loads(files[-1].read_text(encoding="utf-8"))


def test_other_leg_failure_does_not_abort_round(tmp_path):
    """#193 C5(F4 判例推广到全腿):dsem 腿红不再断整轮——后续腿照跑、
    月报/北星照产、心跳照推(腿级红≠缺员)、结尾外显 dsem rc、
    leg-status 工件留红。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, anchors_mode="0", dsem_mode="3")
    assert rc == 3, f"腿红须外显自身 rc(3),实得 {rc}\n{out}"
    assert "红态" in out, out
    for leg in ("audit", "temporal", "readout"):
        assert f"==> {leg}:" in out, f"dsem 红中止了后续腿 {leg}\n{out}"
    assert "完成" in out, out
    root = _report_root(repo)
    assert list(root.glob("model/dsem-*.json")), "红腿工件须照写留证"
    assert list(root.glob("monthly-*.md")), "月报须照产"
    leg = _latest_leg_status(root)
    assert leg["legs"]["dsem"] == 3, leg
    assert (tmp_path / "heartbeat-marker").exists(), "腿级红≠缺员,须照推心跳"


def test_multi_red_aggregates_first_nonzero_in_leg_order(tmp_path):
    """双腿红:结尾 rc=腿序(model→all→anchors→…)首个非零;
    leg-status 工件两红全留(机器可读面不丢腿)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path,
                           anchors_mode="1", dsem_mode="2")
    assert rc == 1, f"腿序首个非零=anchors(1),实得 {rc}\n{out}"
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["anchors"] == 1 and leg["legs"]["dsem"] == 2, leg
    assert (tmp_path / "heartbeat-marker").exists(), out


def test_green_round_writes_leg_status_with_all_legs(tmp_path):
    """全绿轮:leg-status 件在(8 腿全 rc=0,readout 定稿件非 null)。
    渲染前件(readout=null 供月报嵌「在飞」)被定稿件覆盖或共存,
    最新件=定稿件。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    leg = _latest_leg_status(_report_root(repo))
    for name in ("model", "all", "anchors", "dsem", "agg-share",
                 "audit", "temporal", "readout"):
        assert leg["legs"][name] == 0, f"{name} 腿绿轮须 rc=0: {leg}"


def test_leg_status_does_not_substitute_all_family(tmp_path):
    """报告族 all 模式须排除 leg-status-*:all 腿工件缺席时,同形状的
    leg-status-<ts>.json 不得顶替逐源 verdict 件满足校验(观测件永不
    触活族门,缺员即死不推心跳)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, all_skip=True)
    assert rc != 0, out
    assert "报告族不齐" in out, out
    assert not (tmp_path / "heartbeat-marker").exists(), "缺员即死不推心跳"


def test_readout_red_still_exits_nonzero_with_artifacts(tmp_path):
    """readout 腿自身红(工件已落):心跳照推、定稿 leg-status 记
    readout rc、结尾外显(单腿红不再静默 35 天,评审D P1-3)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, readout_mode="4")
    assert rc == 4, f"readout 红须外显 rc=4,实得 {rc}\n{out}"
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["readout"] == 4, leg
    assert (tmp_path / "heartbeat-marker").exists(), out


def test_agg_share_leg_in_report_family(tmp_path):
    """agg-share 腿(终审修单 F6):工件落 model/ 子目录并入报告族。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    assert "==> agg-share:" in out, out
    assert list(_report_root(repo).glob("model/agg-share-*.json")), \
        "agg-share 工件缺席=报告族缺员"
