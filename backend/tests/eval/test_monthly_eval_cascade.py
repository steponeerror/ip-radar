"""monthly_eval.sh 锚腿级联语义守卫(2026-10-24 终审修单 F4)。

契约(TDD 先行,#193 C5 全腿版,承 2026-10-24 F4 anchors 判例推广):
  ① 任一腿红(model/all/anchors/dsem/agg-share/sinkhole-probe/
     anchor-readouts/truth-v2/truth-v2-readout/audit/temporal/
     quality-contract/readout)不中止后续腿,工件照写留证(证据不灭);
     quality-contract 的红分两样(#550 评审返工必须改2):rc 2=契约表
     不合法,进结尾聚合退出码(挡轮);行级失败收报告 failures 面,腿
     状态记红但整轮不受影响(rc 只反映「报告产出与否」;contract.py
     :214-217 oracle=none 行是 no-reading 不是失败,腿不会一上来就红);
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
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from ipdb._eval import gate_mirror

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "monthly_eval.sh"
# #489: mirror-sync 交棒真解释器 —— 临时 git 仓只有 scripts/(backend/ 是
# 空目录), 真解释器要从本测试所属检出的 backend/ 才导得到 ipdb(工作树
# 跑 = 测工作树代码, 变异只改 Python 侧时才能红到级联); rsync 仍走 PATH
# 桩(继承自桩的 env)。真解释器绝对路径/该 backend 路径由 _run_monthly
# 注入 env(MIRROR_SYNC_REAL_PY / MIRROR_SYNC_BACKEND_DIR), 桩本体保持静态。
_BACKEND_DIR_FOR_MIRROR_SYNC = Path(__file__).resolve().parents[2]

# #489: mirror-sync 腿交棒真解释器(先记交接文件再 exec; 临时 git 仓
# 没有 backend/, 从 MIRROR_SYNC_BACKEND_DIR 导 ipdb; rsync 仍走 PATH 桩)
PY_STUB = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    # cascade-test stub:按 argv 模拟 ipdb._eval 各腿(工件照写;rc 按 *_MODE)
    # mirror_check 步真脚本不带 IP_RADAR_EVAL_DIR → 该分支不展开工件路径
    # #489: mirror-sync 动作词交棒真解释器 —— 桩只记录交接, 不模拟
    if [[ "$*" == *"mirror-sync"* ]]; then
      printf '%s\\n' "$*" >> "${MIRROR_SYNC_LOG:?}"
      cd "${MIRROR_SYNC_BACKEND_DIR:?}" || exit 9
      # 桩收到的 argv 已含 -m ipdb._eval(mirror_sync() 以 python3 调它),
      # 原样交给真解释器即可, 不得再补一次模块前缀
      exec "${MIRROR_SYNC_REAL_PY:?}" "$@"
    fi
    if [[ "$*" == *"ipdb._eval.mirror_check"* ]]; then exit 0; fi
    # #550 评审返工必须改2:行级失败读数桩 —— 月轮壳以 `python3 - <model目录>
    # <start_s> quality-fail-n` 读本轮 quality-report 的 failures 条数;桩按
    # QUALITY_CONTRACT_FAILURES 环境变量直接回显(与写者桩同源,不解析 JSON)
    if [ "$4" = "quality-fail-n" ]; then
      printf '%s\\n' "${QUALITY_CONTRACT_FAILURES:-0}"
      exit 0
    fi
    # #500 scan_equiv_check.py 调用桩:scan-equiv 腿的 collect/compare 各记
    # 一行「argv|PYTHONHASHSEED=…|IP_RADAR_DATA_DIR=…」到 SCAN_EQUIV_LOG(rsync/ssh 桩同做法),
    # 两步同 asof、同 PYTHONHASHSEED=0 由测试对记录断言;collect 顺带按
    # --out 造出样本体+纪元旁证空文件(真形状,供「比完即删」断言);打印
    # 与真脚本同形的 JSON 尾行(mode 键)供腿侧摘取落 scan-equiv/ 工件;
    # rc 按 SCAN_EQUIV_MODE(collect)/SCAN_EQUIV_COMPARE_MODE(compare)。
    if [[ "$*" == *"scan_equiv_check.py"* ]]; then
      printf '%s|PYTHONHASHSEED=%s|IP_RADAR_DATA_DIR=%s\n' "$*" "${PYTHONHASHSEED:-unset}" "${IP_RADAR_DATA_DIR:-unset}" >> "${SCAN_EQUIV_LOG:?}"
      if [[ "$*" == *" collect "* ]]; then
        re='--out ([^ ]+)'
        [[ "$*" =~ $re ]] && { : > "${BASH_REMATCH[1]}"; : > "${BASH_REMATCH[1]}.head.json"; }
        printf '{"mode": "collect", "asof": 1765000000, "units_scanned": 2, "sampled_single": 2, "sampled_cidr": 0}\n'
        exit "${SCAN_EQUIV_MODE:-0}"
      fi
      # crash 模式=进程死于吐 JSON 前,演练「compare 没吐 JSON」指路(评审返工 5)
      if [ "${SCAN_EQUIV_COMPARE_MODE:-0}" = "crash" ]; then exit 1; fi
      printf '{"mode": "compare", "asof": 1765000000, "sampled": 2, "mismatches": 0}\n'
      exit "${SCAN_EQUIV_COMPARE_MODE:-0}"
    fi
    # #193 腿级状态件写手桩:shell 侧 write_leg_status 经 python3 heredoc
    # 调用(无 -m ipdb._eval);模拟真写手 argv 形状(path 腿 rc ...)落 JSON
    # python3 - args 调用形:$1="-" $2=path —— 守卫查 $2
    if [ "$#" -ge 2 ] && [[ "$2" == *leg-status-*.json ]]; then
      out_doc="$2"; shift 2
      { printf '{"schema":"leg-status/1","legs":{'
        sep=""
        while [ "$#" -ge 2 ]; do
          printf '%s"%s":%s' "$sep" "$1" "$2"
          sep=","
          shift 2
        done
        printf '}}'
      } > "$out_doc"
      exit 0
    fi
    ts="$(date -u +%Y%m%d-%H%M%S)"
    out="${IP_RADAR_EVAL_DIR:?}/monthly"
    mkdir -p "$out/model"
    ARGS="$*"  # 腿判定基准=脚本级 argv(函数内 $* 会遮蔽)
    leg() { case " $ARGS " in *" --$1 "*) return 0;; *) return 1;; esac; }
    if leg model;     then printf '{"kind":"model"}'      > "$out/model/model-$ts.json"; MODEL_RC="${MODEL_MODE:-0}"; fi
    if leg all;       then if [ "${ALL_SKIP:-0}" != 1 ]; then printf '{"kind":"all"}' > "$out/all-$ts.json"; ALL_RC="${ALL_MODE:-0}"; fi; fi
    if leg agg-share; then printf '{"kind":"agg-share"}'  > "$out/model/agg-share-$ts.json"; fi
    if leg sinkhole-probe; then printf '{"kind":"sinkhole_probe"}' > "$out/model/sinkhole-probe-$ts.json"; SINKHOLE_PROBE_RC="${SINKHOLE_PROBE_MODE:-0}"; fi
    if leg anchor-readouts; then
      # 双工件:#233 T4 一腿双写者(anchor-fp+scanner-recall,两件均须本轮
      # 在场);scanner-recall 缺层形状(status=missing)照写照绿=缺层≠0
      printf '{"kind":"clean_anchor_fp"}' > "$out/model/anchor-fp-$ts.json"
      if [ "${ANCHOR_READOUTS_SKIP_RECALL:-0}" != 1 ]; then
        printf '{"kind":"scanner_recall","status":"%s"}' "${ANCHOR_READOUTS_STATUS:-ok}" > "$out/model/scanner-recall-$ts.json"
      fi
      ANCHOR_READOUTS_RC="${ANCHOR_READOUTS_MODE:-0}"
    fi
    if leg truth-v2; then
      # #262 T3 构建腿写者: published/哨兵两态均落摘要件(坏输入崩溃
      # 不落件 = 族缺员即死, 与真实现同语义)
      printf '{"kind":"truth_v2_build"}' > "$out/model/truth-v2-build-$ts.json"
      TRUTH_V2_RC="${TRUTH_V2_MODE:-0}"
    fi
    if leg truth-v2-readout; then
      # #262 T3 读数腿一腿三工件(readout/parallel/swap, 均恒落;
      # anchor-readouts 一腿双工件同律)
      printf '{"kind":"truth_v2_readout"}' > "$out/model/truth-v2-readout-$ts.json"
      printf '{"kind":"truth_v2_parallel"}' > "$out/model/truth-v2-parallel-$ts.json"
      printf '{"kind":"truth_v2_swap_trigger"}' > "$out/model/truth-v2-swap-$ts.json"
      TRUTH_V2_READOUT_RC="${TRUTH_V2_READOUT_MODE:-0}"
    fi
    if leg dsem;      then printf '{"kind":"dsem"}'       > "$out/model/dsem-$ts.json"; DSEM_RC="${DSEM_MODE:-0}"; fi
    if leg audit;     then printf '{"kind":"audit"}'      > "$out/model/audit-$ts.json"; AUDIT_RC="${AUDIT_MODE:-0}"; fi
    if leg temporal;  then printf '{"kind":"temporal"}'   > "$out/temporal-$ts.json"; TEMPORAL_RC="${TEMPORAL_MODE:-0}"; fi
    # #550 quality-contract 腿写者桩:真实现 run_contract 落
    # model/quality-report-<ts>.json(rc 0=报告产出,腿级失败留在报告内);
    # 红形态(契约表不合法 rc=2/崩溃)由 QUALITY_CONTRACT_MODE 模拟;
    # 行级失败条数由 QUALITY_CONTRACT_FAILURES 模拟(failures 数组 N 条,
    # 真实形状 = 报告根 failures 数组;0=全绿报告)
    if leg quality-contract; then
      n="${QUALITY_CONTRACT_FAILURES:-0}"; items=""; sep=""; i=0
      while [ "$i" -lt "$n" ]; do items="$items$sep{\"id\":\"f$i\"}"; sep=","; i=$((i + 1)); done
      printf '{"kind":"quality-report","failures":[%s]}' "$items" > "$out/model/quality-report-$ts.json"
      QUALITY_CONTRACT_RC="${QUALITY_CONTRACT_MODE:-0}"
    fi
    if leg readout;   then printf '# monthly\\n'          > "$out/monthly-$ts.md"
                        printf '{"kind":"northstar"}'     > "$out/northstar-$ts.json"; READOUT_RC="${READOUT_MODE:-0}"; fi
    if leg anchors; then
      # 18/19 红形态:判定门失败也落盘留证(anchors_report 真实形状)
      printf '{"kind":"anchors","n_fail":%s}' "${ANCHORS_MODE:-0}" > "$out/model/anchors-$ts.json"
      ANCHORS_RC="${ANCHORS_MODE:-0}"
    fi
    # future-stamp:stub 秒级跑完,同秒 mtime 会假阴 -newermt(真月轮=分钟级无此界)。
    # 余量 +300s(#377):宿主机时钟 ±10s 级步进回跳会把 +2 余量吞掉 → 工件
    # mtime 落回 START_S 之前 → 报告族假拒「model-*.json 缺员」;分钟级余量 =
    # 真月轮时间尺度的诚实模拟,<300s 时钟回跳全免疫(生产真月轮分钟级
    # 运行天然免疫,生产脚本 -newermt 面无需改动)。
    find "$out" -type f -exec touch -d "@$(( $(date +%s) + 300 ))" {} + 2>/dev/null || true
    # 腿 rc 聚合退出(红腿外显自身 rc;#193 各腿不再互断)
    for v in MODEL_RC ALL_RC ANCHORS_RC DSEM_RC SINKHOLE_PROBE_RC ANCHOR_READOUTS_RC TRUTH_V2_RC TRUTH_V2_READOUT_RC AUDIT_RC TEMPORAL_RC QUALITY_CONTRACT_RC READOUT_RC; do
      [ "${!v:-0}" = 0 ] || exit "${!v}"
    done
    exit 0
    """
)
# #489: 拉取面(镜像/快照/蜜罐 CSV)返回码改由 RSYNC_PULL_MODE 控制
# (缺省 0; 24=源侧活文件消失, 月轮容忍继续; 其余=拒绝), argv 先记
# RSYNC_LOG 供端到端命令对拍, 拉取分支另写一行 stdout 标记
# RSYNC-STUB-OUTPUT 供回显 flush/透屏对拍(返工 P1); 推送面行为不变
# (不记 RSYNC_LOG)。
RSYNC_STUB = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    # cascade-test rsync 桩:拉取面(镜像/快照/蜜罐 CSV)末参是本地路径;
    # 推送面(#453 评估报告推生产卷)末参含 'stub-host:' → 触 PUSH_MARKER,
    # rc 按 RSYNC_PUSH_MODE(推失败形态用)
    last="${@: -1}"
    if [[ "$last" == *:* ]]; then
      if [ "${RSYNC_PUSH_MODE:-0}" != 0 ]; then exit "$RSYNC_PUSH_MODE"; fi
      # #550 评审必须改5:推送清单可断言 —— 把 files-from 清单原文抄进
      # PUSH_LOG(没设=丢 /dev/null,既有用例零感知)
      {
        printf '%s\\n' "rsync $*"
        ff_re='--files-from=([^ ]+)'
        [[ "$*" =~ $ff_re ]] && cat "${BASH_REMATCH[1]}"
        true
      } >> "${PUSH_LOG:-/dev/null}" 2>/dev/null
      touch "${PUSH_MARKER:?}"
      exit 0
    fi
    printf '%s\\n' "rsync $*" >> "${RSYNC_LOG:?}"
    # stdout 标记(返工 P1): CLI 回显 flush 后子进程直写同一管道, 月轮
    # 输出里回显行须排在本标记行之前; capture=True 则标记根本透不进
    # 月轮输出——顺序断言两头都红
    echo "RSYNC-STUB-OUTPUT"
    exit "${RSYNC_PULL_MODE:-0}"
    """
)
# ssh 桩三种调用形: ①honyport 面目录探测(monthly_eval.sh `ssh … test -d
# /opt/honyport/out`, #265)→ rc 1 = 远端目录缺席(哨兵分支, 不心跳);
# ②#453 推送前远端建目录(`ssh … "mkdir -p …"`)→ rc 0 + 触
# SSH_MKDIR_MARKER(留痕:dry-run「不调 ssh」与「推送先建目录」才有标记可断);
# ③生产 volume 心跳推送(printf > …)→ touch 标记文件。(旧桩任何非
# test-d 调用都 touch 标记,会把 mkdir -p 也当心跳 —— 按调用形分派)
# ①的探测 rc 现按 HONYPORT_PROBE_MODE(#489): 缺省 1 = 远端目录缺席
# (哨兵分支, 既有用例行为不变); 0 = 在场 → 走 mirror-sync 拉取(交接用例)。
SSH_STUB = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    if [[ "$*" == *"test -d"* ]]; then exit "${HONYPORT_PROBE_MODE:-1}"; fi
    if [[ "$*" == *"mkdir -p"* ]]; then
      touch "${SSH_MKDIR_MARKER:?}"
      exit 0
    fi
    touch "${HEARTBEAT_MARKER:?}"
    """
)
# date 桩(#468 评审建议改 2a):只拦 ROUND_TS 那一种调用形(-u +%Y%m%dT%H%M%SZ),
# 每调一次返回不同值(计数文件 +1)——桩一轮秒级跑完,真时间戳十二腿必同值,
# 钉不住「一轮只取一次」;假值互异后,实现改成每腿各取一次就是十二个值,
# 断言必红。其余调用形原样透传真 date(脚本 +%s/心跳/腿级状态件与
# python3 桩里的 date 都不受影响)。
DATE_STUB = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    if [ "${1:-}" = "-u" ] && [ "${2:-}" = "+%Y%m%dT%H%M%SZ" ]; then
      f="${DATE_COUNTER:?}"
      n=$(cat "$f" 2>/dev/null || echo 0)
      n=$((n + 1))
      printf '%s' "$n" > "$f"
      printf '20200101T0000%02dZ' "$n"
      exit 0
    fi
    exec /usr/bin/date "$@"
    """
)


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
    for name, body in (("python3", PY_STUB), ("rsync", RSYNC_STUB), ("ssh", SSH_STUB),
                       ("date", DATE_STUB)):
        p = stubs / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
    return stubs


def _run_monthly(repo: Path, stubs: Path, tmp_path: Path, *args: str,
                 anchors_mode: str = "0", dsem_mode: str = "0",
                 model_mode: str = "0", all_mode: str = "0",
                 audit_mode: str = "0", temporal_mode: str = "0",
                 readout_mode: str = "0", all_skip: bool = False,
                 sinkhole_probe_mode: str = "0",
                 anchor_readouts_mode: str = "0",
                 anchor_readouts_status: str = "ok",
                 anchor_readouts_skip_recall: bool = False,
                 truth_v2_mode: str = "0",
                 truth_v2_readout_mode: str = "0",
                 rsync_push_mode: str = "0",
                 scan_equiv_mode: str = "0",
                 scan_equiv_compare_mode: str = "0",
                 scan_equiv_single_every: str = "",
                 quality_contract_mode: str = "0",
                 quality_contract_failures: str = "0",
                 rsync_pull_mode: str = "0",
                 honyport_probe_mode: str = "1",
                 ) -> tuple[int, str]:
    env = dict(os.environ)
    env["PATH"] = f"{stubs}:{env['PATH']}"
    env["EVAL_DATA_DIR"] = str(tmp_path / "data")
    env["HEARTBEAT_MARKER"] = str(tmp_path / "heartbeat-marker")
    env["PUSH_MARKER"] = str(tmp_path / "push-marker")   # #453 推送发生标记
    env["PUSH_LOG"] = str(tmp_path / "push-list.log")   # #550 评审必须改5:推送清单原文(断言 quality-report 在列)
    env["SSH_MKDIR_MARKER"] = str(tmp_path / "ssh-mkdir-marker")   # #453 推送前建目录标记
    env["DATE_COUNTER"] = str(tmp_path / "date-counter")   # #468 date 桩计数文件
    env["RSYNC_PUSH_MODE"] = rsync_push_mode
    env["RSYNC_PULL_MODE"] = rsync_pull_mode          # #489: 拉取面返回码
    env["HONYPORT_PROBE_MODE"] = honyport_probe_mode  # 缺省 1=远端目录缺席
    env["MIRROR_SYNC_LOG"] = str(tmp_path / "mirror-sync.log")  # #489 交接记录
    env["RSYNC_LOG"] = str(tmp_path / "rsync.log")      # #489 端到端命令对拍
    env["MIRROR_SYNC_REAL_PY"] = sys.executable         # #489 交棒真解释器
    env["MIRROR_SYNC_BACKEND_DIR"] = str(_BACKEND_DIR_FOR_MIRROR_SYNC)
    env["ANCHORS_MODE"] = anchors_mode
    env["DSEM_MODE"] = dsem_mode
    env["MODEL_MODE"] = model_mode
    env["ALL_MODE"] = all_mode
    env["AUDIT_MODE"] = audit_mode
    env["TEMPORAL_MODE"] = temporal_mode
    env["READOUT_MODE"] = readout_mode
    env["SINKHOLE_PROBE_MODE"] = sinkhole_probe_mode
    env["ANCHOR_READOUTS_MODE"] = anchor_readouts_mode
    env["ANCHOR_READOUTS_STATUS"] = anchor_readouts_status
    env["ANCHOR_READOUTS_SKIP_RECALL"] = "1" if anchor_readouts_skip_recall else "0"
    env["ALL_SKIP"] = "1" if all_skip else "0"
    env["TRUTH_V2_MODE"] = truth_v2_mode
    env["TRUTH_V2_READOUT_MODE"] = truth_v2_readout_mode
    env["SCAN_EQUIV_MODE"] = scan_equiv_mode          # #500 collect 步 rc
    env["SCAN_EQUIV_COMPARE_MODE"] = scan_equiv_compare_mode  # #500 compare 步 rc
    env["SCAN_EQUIV_LOG"] = str(tmp_path / "scan-equiv-calls.log")  # #500 桩调用记录
    env["QUALITY_CONTRACT_MODE"] = quality_contract_mode          # #550 quality-contract 腿 rc
    env["QUALITY_CONTRACT_FAILURES"] = quality_contract_failures  # #550 行级失败条数(报告 failures 面)
    if scan_equiv_single_every:  # #500 评审返工 7:覆盖抽样密度(校验在脚本侧)
        env["IP_RADAR_SCAN_EQUIV_SINGLE_EVERY"] = scan_equiv_single_every
    env["TMPDIR"] = str(tmp_path)   # #500:样本体落测试临时目录,断言「比完即删」不碰真 /tmp
    r = subprocess.run(["bash", "scripts/monthly_eval.sh", "stub-host", *args],
                       cwd=repo, env=env, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def _report_root(repo: Path) -> Path:
    return repo / "backend" / "data" / "eval" / "monthly"


_LEG_ORDER_RE = re.compile(r"^LEG_ORDER=\(([^)]*)\)", re.MULTILINE)


def _script_leg_order() -> list:
    """从 monthly_eval.sh 里数出 eval 旗标腿清单(LEG_ORDER 单行数组)。
    #500:日志份数断言跟着脚本走,不再写死和脚本对不上的魔数。"""
    m = _LEG_ORDER_RE.search(SCRIPT.read_text(encoding="utf-8"))
    assert m, "monthly_eval.sh 缺 LEG_ORDER 定义"
    return m.group(1).split()


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


def _render_leg_status(leg: dict) -> list:
    """月报渲染(backend/ipdb/_eval/monthly.py render_leg_status)对
    leg-status 的读取面:函数内导入,不在模块顶层把 ipdb 拖进全部
    shell 级用例。"""
    from ipdb._eval.monthly import render_leg_status
    return render_leg_status(leg)


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
    """全绿轮:leg-status 件在(12 旗标腿全 rc=0,非旗标 scan-equiv 亦
    rc=0 且月报渲染能读出,评审返工 8;readout 定稿件非 null)。
    渲染前件(readout=null 供月报嵌「在飞」)被定稿件覆盖或共存,
    最新件=定稿件。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    leg = _latest_leg_status(_report_root(repo))
    for name in ("model", "all", "anchors", "dsem", "agg-share",
                 "sinkhole-probe", "anchor-readouts", "truth-v2",
                 "truth-v2-readout",
                 "audit", "temporal", "quality-contract", "readout"):
        assert leg["legs"][name] == 0, f"{name} 腿绿轮须 rc=0: {leg}"
    assert leg["legs"]["scan-equiv"] == 0, leg  # 评审返工 8:非旗标腿也进腿级状态
    assert any("scan-equiv=rc0" in ln for ln in _render_leg_status(leg)), \
        _render_leg_status(leg)


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


def test_sinkhole_probe_leg_in_report_family(tmp_path):
    """#233 T4(T2 探针)接线:sinkhole-probe 腿进 LEG_ORDER+报告族
    (model/ 工件),腿级状态件 rc=0(只测量不持门,agg-share 同律)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    assert "==> sinkhole-probe:" in out, out
    assert list(_report_root(repo).glob("model/sinkhole-probe-*.json")), \
        "sinkhole-probe 工件缺席=报告族缺员"
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["sinkhole-probe"] == 0, leg


def test_anchor_readouts_leg_in_report_family_two_artifacts(tmp_path):
    """#233 T4(T3 双读数)接线:anchor-readouts 一腿双工件(anchor-fp+
    scanner-recall)均入报告族;scanner-recall 缺层形状(status=missing)
    照写照绿——缺层语义在工件内(缺层≠0,recall=None),腿级 rc 不因
    数据缺层变红(T3 run_anchor_readouts missing 形状的腿级传递)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path,
                           anchor_readouts_status="missing")
    assert rc == 0, out
    assert "==> anchor-readouts:" in out, out
    root = _report_root(repo)
    assert list(root.glob("model/anchor-fp-*.json")), \
        "anchor-fp 工件缺席=报告族缺员"
    sr = list(root.glob("model/scanner-recall-*.json"))
    assert sr, "scanner-recall 工件缺席=报告族缺员"
    assert json.loads(sr[-1].read_text(encoding="utf-8"))["status"] == "missing"
    leg = _latest_leg_status(root)
    assert leg["legs"]["anchor-readouts"] == 0, leg


def test_anchor_readouts_missing_one_artifact_is_family_death(tmp_path):
    """一腿双写者:scanner-recall 缺席(anchor-fp 在场)→ 报告族缺员
    即死,不推心跳(写者身份≠门身份;两件均须本轮在场)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path,
                           anchor_readouts_skip_recall=True)
    assert rc != 0, out
    assert "报告族不齐" in out, out
    assert not (tmp_path / "heartbeat-marker").exists(), "缺员即死不推心跳"


def test_truth_v2_legs_in_report_family(tmp_path):
    """#262 T3 接线(ADR 0017):truth-v2 构建腿(摘要件 published/哨兵
    两态均落)+ 读数腿一腿三工件(readout/parallel/swap 均恒落)入
    LEG_ORDER+报告族;两腿 rc=0(只测量不持门, sinkhole-probe 同律)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    assert "==> truth-v2:" in out, out
    assert "==> truth-v2-readout:" in out, out
    root = _report_root(repo)
    assert list(root.glob("model/truth-v2-build-*.json")), \
        "truth-v2-build 工件缺席=报告族缺员"
    for pat in ("truth-v2-readout-*.json", "truth-v2-parallel-*.json",
                "truth-v2-swap-*.json"):
        assert list(root.glob(f"model/{pat}")), \
            f"{pat} 工件缺席=报告族缺员(一腿三工件缺任一即族缺员)"
    leg = _latest_leg_status(root)
    assert leg["legs"]["truth-v2"] == 0, leg
    assert leg["legs"]["truth-v2-readout"] == 0, leg


def test_truth_v2_leg_red_cascades_like_other_legs(tmp_path):
    """truth-v2 构建腿红(评审环条目 6)同律级联(#193 C5 全腿语义):
    rc=2(工件照写形态)→ 后续腿照跑、leg-status 留红、结尾外显 rc=2、
    报告族齐全照推心跳(腿级红≠缺员)—— 照 sinkhole-probe 同型。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, truth_v2_mode="2")
    assert rc == 2, f"腿红须外显自身 rc(2),实得 {rc}\n{out}"
    assert "红态" in out, out
    for leg in ("truth-v2-readout", "audit", "temporal", "readout"):
        assert f"==> {leg}:" in out, f"truth-v2 红中止了后续腿 {leg}\n{out}"
    assert "完成" in out, out
    root = _report_root(repo)
    assert list(root.glob("model/truth-v2-build-*.json")), "红腿工件须照写留证"
    leg = _latest_leg_status(root)
    assert leg["legs"]["truth-v2"] == 2, leg
    assert (tmp_path / "heartbeat-marker").exists(), "腿级红≠缺员,须照推心跳"


def test_truth_v2_readout_leg_red_cascades_like_other_legs(tmp_path):
    """truth-v2-readout 读数腿红(评审环条目 6)同律: rc=2(三工件照写
    形态)→ 后续腿照跑、结尾外显、心跳照推 —— 观测腿红≠缺员。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, truth_v2_readout_mode="2")
    assert rc == 2, f"腿红须外显自身 rc(2),实得 {rc}\n{out}"
    assert "红态" in out, out
    for leg in ("audit", "temporal", "readout"):
        assert f"==> {leg}:" in out, f"truth-v2-readout 红中止了后续腿 {leg}\n{out}"
    root = _report_root(repo)
    for pat in ("truth-v2-readout-*", "truth-v2-parallel-*",
                "truth-v2-swap-*"):
        assert list(root.glob(f"model/{pat}")), f"红腿 {pat} 工件须照写留证"
    leg = _latest_leg_status(root)
    assert leg["legs"]["truth-v2-readout"] == 2, leg
    assert (tmp_path / "heartbeat-marker").exists(), "腿级红≠缺员,须照推心跳"


def test_sinkhole_probe_red_cascades_like_other_legs(tmp_path):
    """#193 C5 全腿语义对新腿同律(#233 T4):sinkhole-probe 腿红
    (rc=2,工件照写形态)→ 后续腿照跑、leg-status 留红、结尾外显 rc=2、
    报告族齐全照推心跳(腿级红≠缺员)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, sinkhole_probe_mode="2")
    assert rc == 2, f"腿红须外显自身 rc(2),实得 {rc}\n{out}"
    assert "红态" in out, out
    for leg in ("anchor-readouts", "audit", "temporal", "readout"):
        assert f"==> {leg}:" in out, f"sinkhole-probe 红中止了后续腿 {leg}\n{out}"
    assert "完成" in out, out
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["sinkhole-probe"] == 2, leg
    assert (tmp_path / "heartbeat-marker").exists(), "腿级红≠缺员,须照推心跳"


# ── #453:评估报告推送(报告族齐全校验之后、心跳之前)──────────────

def test_eval_report_push_in_green_round(tmp_path):
    """#453:全绿轮把本轮逐源 verdict 件+model/model-*.json 推到生产卷
    (PUSH_MARKER 在=推送发生;rsync 桩按末参含 'stub-host:' 判推方向)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    assert "==> 评估报告推送" in out, out
    assert (tmp_path / "push-marker").exists(), "全绿轮须推评估报告"
    assert (tmp_path / "ssh-mkdir-marker").exists(), "推送前须先在远端建目录"
    assert (tmp_path / "heartbeat-marker").exists(), out


def test_eval_report_push_after_family_check(tmp_path):
    """#453 排序契约:推送在报告族齐全校验之后 —— all 腿工件缺席
    (族缺员即死)时校验先退出,推送与心跳都不得发生。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, all_skip=True)
    assert rc != 0, out
    assert "报告族不齐" in out, out
    assert not (tmp_path / "push-marker").exists(), "推送不得先于报告族校验"
    assert not (tmp_path / "heartbeat-marker").exists(), "缺员即死不推心跳"


def test_eval_report_push_dry_run_prints_but_does_not_push(tmp_path):
    """#453 dry-run:推送只打印将执行的命令,零 ssh/rsync 副作用
    (无推送标记、无心跳标记、零工件)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, "--dry-run")
    assert rc == 0, out
    assert "==> 评估报告推送" in out, out
    assert "[dry-run]" in out, out
    assert not (tmp_path / "push-marker").exists()
    assert not (tmp_path / "heartbeat-marker").exists()
    assert not (tmp_path / "ssh-mkdir-marker").exists(), "dry-run 不得调 ssh"
    assert not _report_root(repo).exists()


def test_eval_report_push_failure_red_but_heartbeat_kept(tmp_path):
    """#453:推送失败=红态外显+结尾以推送 rc 非零退出(经 AGG_RC 同一
    出口);心跳照写 —— 报告族在本机是齐的,生产读不到报告不该连心跳
    健康一起谎报。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, rsync_push_mode="7")
    assert rc == 7, f"推送红须以推送 rc=7 结尾外显,实得 {rc}\n{out}"
    assert "红态" in out and "推送" in out, f"缺推送红态行\n{out}"
    assert (tmp_path / "heartbeat-marker").exists(), "推失败心跳照写"


# ── #468:腿日志落报告目录树(monthly/logs/<腿名>-<UTC 时间戳>.log)──

def test_leg_logs_land_in_report_tree_one_timestamp_per_round(tmp_path):
    """#468:每腿完整输出不再写 /tmp,改落 <报告目录>/monthly/logs/ 下,
    文件名 = <腿名>-<UTC 时间戳>.log(一轮一个时间戳,全部腿共用,
    不覆盖上一轮)。「一轮只取一次」由 date 桩钉住:桩对 ROUND_TS 调用形
    每次返回不同值,只有脚本真的只调一次,全部腿才可能同值;改成每腿
    各取一次就有多个不同值,必红(变异证据见 impl-report-2.md)。
    腿清单从脚本里数(LEG_ORDER + scan-equiv,#500:非旗标腿同样落
    一份腿日志),不再写死魔数。报告目录指到临时仓(不入真仓库);干跑零目录由
    test_bash_syntax_and_dry_run 的「报告根不存在」断言覆盖(logs/ 在其下)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    logs = _report_root(repo) / "logs"
    assert logs.is_dir(), f"腿日志目录缺席\n{out}"
    leg_names = _script_leg_order() + ["scan-equiv"]  # #500:非旗标腿同样落一份腿日志
    assert len(list(logs.iterdir())) == len(leg_names), \
        f"每腿一份日志(LEG_ORDER + scan-equiv),实得 {len(list(logs.iterdir()))} 份\n{out}"
    stamps = set()
    for leg in leg_names:
        # 精确全名匹配(glob 前缀会互撞:truth-v2-* 也吃掉 truth-v2-readout-*)
        found = [p for p in logs.iterdir()
                 if re.fullmatch(rf"{re.escape(leg)}-\d{{8}}T\d{{6}}Z\.log", p.name)]
        assert len(found) == 1, f"{leg} 腿日志须恰一份,实得 {[p.name for p in found]}\n{out}"
        stamps.add(re.search(r"(\d{8}T\d{6}Z)", found[0].name).group(1))
    assert len(stamps) == 1, f"一轮一个时间戳(全部腿共用),实得 {sorted(stamps)}"


# ── #500:scan-equiv 腿(全库扫描↔查询对拍;非 LEG_ORDER 旗标腿)──────

def test_scan_equiv_leg_collect_and_compare_share_asof(tmp_path):
    """#500:scan-equiv 腿真跑两步 python3(collect→compare),两步的
    --asof 相同、PYTHONHASHSEED=0(对拍前提,工具件 docstring)、打同一
    数据目录;缺省抽样密度 --single-every 20 进 argv(评审返工 7)。
    桩子把每次调用的 argv|PYTHONHASHSEED|IP_RADAR_DATA_DIR 记进
    SCAN_EQUIV_LOG(现有 rsync/ssh 桩同做法)。留下的证据 = 两行 JSON
    落 scan-equiv/ + 腿日志;样本体+纪元旁证比完即删(临时目录不残留)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    assert "==> scan-equiv:" in out, out
    calls = (tmp_path / "scan-equiv-calls.log").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(calls) == 2, f"collect+compare 恰两次 python3,实得 {calls}"
    assert " collect " in calls[0] and " compare " in calls[1], calls
    asofs = [re.search(r"--asof (\S+)", c).group(1) for c in calls]
    fields = [dict(kv.split("=", 1) for kv in c.split("|")[1:]) for c in calls]
    assert asofs[0] == asofs[1], f"两步必须同一 asof,实得 {asofs}"
    assert [f["PYTHONHASHSEED"] for f in fields] == ["0", "0"], \
        f"两步必须 PYTHONHASHSEED=0,实得 {fields}"
    want = os.path.realpath(tmp_path / "data")  # 与 _run_monthly 的 EVAL_DATA_DIR 同源
    assert [f["IP_RADAR_DATA_DIR"] for f in fields] == [want, want], \
        f"两步必须打同一数据目录(=EVAL_DATA_DIR),实得 {fields}"
    assert "--single-every 20" in calls[0], calls[0]
    root = _report_root(repo)
    col = sorted(root.glob("scan-equiv/collect-*.json"))
    cmp_ = sorted(root.glob("scan-equiv/compare-*.json"))
    assert col and cmp_, f"两步 JSON 工件缺席: {sorted(p.name for p in root.glob('scan-equiv/*'))}"
    assert '"mode": "collect"' in col[-1].read_text(encoding="utf-8")
    assert '"mode": "compare"' in cmp_[-1].read_text(encoding="utf-8")
    assert not list(tmp_path.glob("scan-equiv-*.jsonl.gz*")), "样本体须比完即删"
    assert list(_report_root(repo).glob("logs/scan-equiv-*.log")), "腿日志缺席"


def test_scan_equiv_dry_run_prints_but_does_not_execute(tmp_path):
    """#500:干跑回显两条命令但零执行(桩子调用记录文件不存在)、零目录
    (scan-equiv/ 与 logs/ 都在报告根下,由报告根不存在覆盖)。"""


# ── #489:拉取面同步收口单源入口(mirror-sync 交棒真解释器)──────────

def _data_dir(tmp_path: Path) -> str:
    return os.path.realpath(tmp_path / "data")   # 与脚本 realpath -m 同值


def test_mirror_sync_handoff_to_real_interpreter(tmp_path):
    """python3 桩把 mirror-sync 交棒真解释器:交接记录恰三条(main/
    truth-v2/honyport;ssh 桩探测放行 = 远端目录在场)。交棒没发生
    (桩没 exec,或把动作词当腿模拟)记录条数/形状即不对。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, honyport_probe_mode="0")
    assert rc == 0, out
    log = (tmp_path / "mirror-sync.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 3, f"mirror-sync 应恰交接三次(三拉取面),实得 {len(log)}\n{out}"
    faces = [re.search(r"--face (\S+)", ln).group(1) for ln in log]
    assert faces == ["main", "truth-v2", "honyport"], faces


def test_dry_run_rsync_lines_identical_to_pre_change(tmp_path):
    """dry-run 三行 ==> rsync… 与改前逐字相同(#489 契约):期望值从
    Python 契约常量拼出(host/data-dir 是 harness 参数,与改前同参数下
    逐字节同形;改前全文留档票目录 dry-run-before.txt 供合并对拍)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, "--dry-run")
    assert rc == 0, out
    assert "==> scan-equiv:" in out, out
    assert not (tmp_path / "scan-equiv-calls.log").exists(), \
        "干跑不得执行 scan_equiv_check"


def test_scan_equiv_red_counts_into_final_status(tmp_path):
    """#500:scan-equiv 腿红(collect rc=1;collect 正常出口只有 0,
    1=判定不一致或进程异常退出)→ 结尾以该 rc 非零退出(持门同
    anchors)、红态行外显;腿级红≠缺员,报告族齐全心跳照推(scan-equiv
    工件不在报告族名单);collect 红不再跑 compare。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, scan_equiv_mode="1")
    assert rc == 1, f"scan-equiv 红(1)须外显为结尾 rc,实得 {rc}\n{out}"
    assert "!! scan-equiv 腿 rc=1" in out, out
    assert (tmp_path / "heartbeat-marker").exists(), "腿级红≠缺员,须照推心跳"
    calls = (tmp_path / "scan-equiv-calls.log").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(calls) == 1, f"collect 红不再跑 compare,实得 {calls}"


def test_scan_equiv_stale_sample_says_rerun(tmp_path):
    """#500:compare rc=2(样本作废:对拍期间有源换了纪元/asof 对不上)
    → 腿红 rc=2 外显,且日志有人话指引「重跑这一轮」。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, scan_equiv_compare_mode="2")
    assert rc == 2, f"样本作废(rc=2)须外显为结尾 rc,实得 {rc}\n{out}"
    assert "重跑这一轮" in out, out
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["scan-equiv"] == 2, leg  # 评审返工 8:红也进腿级状态
    assert any("scan-equiv(rc2)" in ln for ln in _render_leg_status(leg)), \
        _render_leg_status(leg)


def test_scan_equiv_single_every_passthrough(tmp_path):
    """#500 评审返工 7:IP_RADAR_SCAN_EQUIV_SINGLE_EVERY=200 进到
    collect 的 --single-every 200(缺省 20 的断言在同文件首个
    scan-equiv 用例)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path,
                           scan_equiv_single_every="200")
    assert rc == 0, out
    calls = (tmp_path / "scan-equiv-calls.log").read_text(
        encoding="utf-8").strip().splitlines()
    assert "--single-every 200" in calls[0], calls[0]


def test_scan_equiv_single_every_rejects_non_positive(tmp_path):
    """#500 评审返工 5:0 与非数字都被一句人话拒绝、exit 1,且拒绝发生在
    任何腿之前(无调用记录、无报告根)。"""
    for i, bad in enumerate(("0", "abc")):
        sub = tmp_path / f"reject-{bad}"
        sub.mkdir()
        repo = _make_repo(sub)
        stubs = _make_stubs(sub)
        rc, out = _run_monthly(repo, stubs, sub,
                               scan_equiv_single_every=bad)
        assert rc == 1, f"实得 '{bad}' 须拒绝 exit 1,实得 rc={rc}\n{out}"
        assert "须为正整数" in out, out
        assert not (sub / "scan-equiv-calls.log").exists(), \
            "拒绝发生在任何腿之前"
        assert not _report_root(repo).exists(), "拒绝不得建报告根"


def test_scan_equiv_compare_crash_points_at_log(tmp_path):
    """#500 评审返工 5:compare rc=1 且没吐 JSON(桩子 crash 模式=进程死于
    打印前)→ 日志多一句「多半是崩溃,看腿日志」,rc=1 照常持门;
    compare-*.json 空件照落(空文件本身即异常信号)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path,
                           scan_equiv_compare_mode="crash")
    assert rc == 1, out
    assert "多半是崩溃" in out, out
    cmp_ = sorted(_report_root(repo).glob("scan-equiv/compare-*.json"))
    assert cmp_ and cmp_[-1].read_text(encoding="utf-8") == "", cmp_


# ── #550:quality-contract 腿(变异自检+事故回放;入 LEG_ORDER 但不持门)──────

def test_quality_contract_leg_in_leg_order(tmp_path):
    """#550:quality-contract 腿在 LEG_ORDER 里(腿级状态件/红态行迭代
    共用该清单,缺员即静默)且真跑一条 `--quality-contract` 命令,工件
    quality-report-*.json 落 model/(run_contract 真实落件位置)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    assert "quality-contract" in _script_leg_order(), _script_leg_order()
    assert "==> quality-contract:" in out, out
    assert list(_report_root(repo).glob("model/quality-report-*.json")), \
        "quality-report 工件缺席"
    assert list(_report_root(repo).glob("logs/quality-contract-*.log")), \
        "quality-contract 腿日志缺席"


def test_quality_contract_rc2_fails_round(tmp_path):
    """#550 评审必须改2:腿挡轮 —— rc=2(契约表不合法;contract.py:341-343
    仅 ContractError 上抛;:214-217 oracle=none 行是 no-reading 不是失败,
    腿不会一上来就红)进结尾 AGG_RC,整轮失败;后续腿照跑、心跳照推、
    红态可见三面(模块 docstring 契约①「不中止后续腿」不变)。
    变异②=把结尾的挡轮排除加回去,本测试红。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, quality_contract_mode="2")
    assert rc == 2, f"rc=2 须让整轮失败,实得 rc={rc}\n{out}"
    assert "!! quality-contract 腿 rc=2" in out, "红态行缺席\n" + out
    assert "==> readout:" in out, "quality-contract 红中止了 readout\n" + out
    assert "完成" in out, out
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["quality-contract"] == 2, leg
    assert (tmp_path / "heartbeat-marker").exists(), "腿级红≠缺员,须照推心跳"
    # 渲染面读得出红腿(monthly.py render_leg_status 按 legs 字典通用)
    assert any("quality-contract" in ln for ln in _render_leg_status(leg)), \
        _render_leg_status(leg)


def test_quality_contract_row_failures_red_not_round_failure(tmp_path):
    """#550 评审必须改2:行级失败记红 —— 报告 failures 面 N 条
    (QUALITY_CONTRACT_FAILURES 桩)→ CLI rc 仍 0(行级失败收报告不改 rc,
    contract.py:254-257/:341-343),整轮不受影响;但腿级状态记红(0→1)、
    红态行打印条数、月报腿级行可见。变异③=去掉 failures 判定(write_leg_status
    argv 特例与行级红态行),本测试红。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, quality_contract_failures="3")
    assert rc == 0, out
    assert "!! quality-contract 行级失败 3 条" in out, "行级失败红态行缺席\n" + out
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["quality-contract"] == 1, leg
    assert (tmp_path / "heartbeat-marker").exists(), "行级失败≠缺员,须照推心跳"
    assert any("quality-contract" in ln for ln in _render_leg_status(leg)), \
        _render_leg_status(leg)


def test_quality_contract_leg_green_records_zero(tmp_path):
    """#550:quality-contract 腿绿(报告产出且零 failures)→ 腿级状态件记
    rc=0(腿状态进 write_leg_status,日报/月报才读得到)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    leg = _latest_leg_status(_report_root(repo))
    assert leg["legs"]["quality-contract"] == 0, leg


def test_quality_report_in_push_list(tmp_path):
    """#550 评审必须改5:质量报告进推送清单 —— 服务器健康轮
    (ops/agent-v2/tasks/health-round.mjs)读生产卷 model/quality-report-*.json
    判 mutation_check_due,不推则提醒永远「未见上次运行——首跑即到期」。
    rsync 桩把 --files-from 清单原文抄进 PUSH_LOG,断言 quality-report 在列。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    push_log = (tmp_path / "push-list.log").read_text(encoding="utf-8")
    assert re.search(r"^model/quality-report-\d{8}-\d{6}\.json$",
                     push_log, re.M), push_log


def test_pull_rsync_command_matches_python_contract(tmp_path):
    """端到端对拍:级联真跑(bash→CLI→sync_face→rsync)落桩的 argv ==
    Python 契约拼出的命令;旗标另按字面量钉(变异 M1 只改 Python 侧
    旗标时,端到端对拍会跟着一致漂移假绿,判别力在字面量断言)。
    另钉回显 flush/透屏(返工 P1):每个 ==> rsync 回显行须排在对应
    rsync 桩的 stdout 标记之前,且标记行确实透到月轮输出——去 flush
    (块缓冲把回显攒到退出)或 capture=True(吞掉子进程输出)任一变异
    都在这两段断言红。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path)
    assert rc == 0, out
    data = _data_dir(tmp_path)
    got = [ln.split() for ln in
           (tmp_path / "rsync.log").read_text(encoding="utf-8").splitlines()]
    want = [
        gate_mirror.sync_face("stub-host", "main", data,
                              dry_run=True)["command"],
        gate_mirror.sync_face("stub-host", "truth-v2",
                              f"{data}/truth-v2-capture",
                              dry_run=True)["command"],
    ]
    assert got == want, f"rsync argv 端到端对拍失配:\n got={got}\nwant={want}"
    # 旗标字面量钉(主面含 --delete-after,快照面无)
    assert "--partial" in got[0] and "--delete-after" in got[0], got[0]
    assert "--delete-after" not in got[1], got[1]
    # 回显 flush/透屏对拍(返工 P1):回显行先于 rsync 桩 stdout 标记落
    # 管道,标记行数 == 回显行数(缺标记 = 输出被捕获,顺序颠倒 = 没 flush)
    lines = out.splitlines()
    hdr = [i for i, ln in enumerate(lines) if ln.startswith("==> rsync")]
    mark = [i for i, ln in enumerate(lines) if ln == "RSYNC-STUB-OUTPUT"]
    assert len(hdr) == len(mark) == 2, f"回显 {hdr} / 标记 {mark}\n{out}"
    assert all(h < m for h, m in zip(hdr, mark)), (
        "==> rsync 回显行没有先于 rsync 子进程输出落管道"
        "(flush 缺失或输出被捕获):\n" + "\n".join(lines))


def test_pull_rc24_tolerated_round_completes(tmp_path):
    """拉取面 rc=24(源侧活文件消失)月轮照常跑完,留痕行在,心跳照推
    (容忍语义从 bash 三处手写 if 迁到 Python 单源后行为不变)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, rsync_pull_mode="24")
    assert rc == 0, out
    assert "-- rsync rc=24(源侧活动文件消失,活镜像可容忍)" in out, out
    assert "完成" in out, out
    assert (tmp_path / "heartbeat-marker").exists(), out


def test_pull_rc23_rejected_round_aborts(tmp_path):
    """拉取面 rc=23(非容忍)月轮拒绝:退出非零、「拒绝」在日志、拒绝
    发生在读数前(无工件无心跳,缺员即死不变)。"""
    repo = _make_repo(tmp_path)
    stubs = _make_stubs(tmp_path)
    rc, out = _run_monthly(repo, stubs, tmp_path, rsync_pull_mode="23")
    assert rc == 1, f"拉取拒绝须以 rc=1 退出,实得 {rc}\n{out}"
    assert "拒绝: rsync 失败 (rc=23)" in out, out
    assert not (tmp_path / "heartbeat-marker").exists(), "拉取拒绝不得推心跳"
    assert not _report_root(repo).exists(), "拉取拒绝不得进读数"
