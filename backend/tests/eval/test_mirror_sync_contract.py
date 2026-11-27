"""镜像同步契约对拍(#489,第四轮评审第 26 卡):生产数据同步的源路径/
旗标/rc 容忍集只在 backend/ipdb/_eval/gate_mirror.py 定义一份,接入关
(sync_gate_mirror/main 面)与月轮三拉取面经同一份 sync_face 走。

钉四处:
① 生产机地址两边相同:monthly_eval.sh 的 PROD_HOST 字面量 ==
   gate_mirror.PROD_HOST_DEFAULT(原本靠注释互引保鲜,无检查件);
② 月轮脚本除推送面(#453,「推报告上去」不同族,保留手写 rsync)外,
   不得再出现手写 rsync 命令——三个拉取面统一经
   `python -m ipdb._eval mirror-sync` 单源入口;
③ 三面拼出的 rsync 命令逐项断言(旗标主面多 --delete-after、源路径带
   尾斜杠、目标带尾斜杠),远端源路径/容忍集/留痕文案等契约值按字面量钉;
④ mirror-sync CLI 行为:dry-run 只回显退出 0;rc 24 容忍留痕退 0;
   rc 23 拒绝退 1(注入 fake runner,不真跑 rsync、零网络);
⑤ honyport 远端路径在月轮脚本非注释行恰三处(干跑提示/缺席提示/
   ssh 探测,探测留脚本是任务书定的),字面量等于契约常量;
⑥ 主面护栏(返工二-11):目标=根目录拒绝退 2,含 eval-heartbeat 条目
   放行;rsync 起不来(OSError 族)= 一行拒绝不甩栈(返工二-9)。
"""
import re
from pathlib import Path
from types import SimpleNamespace

from ipdb._eval import gate_mirror
from ipdb._eval.__main__ import mirror_sync_cli

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "monthly_eval.sh"


def test_prod_host_same_on_both_sides():
    """生产机地址唯一事实在 Python 镜像契约;月轮那行字面量由对拍钉同值
    (#489 前是两份手写 + 注释互引)。"""
    m = re.search(r'^PROD_HOST="([^"]+)"',
                  SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, f"月轮脚本找不到 PROD_HOST= 行: {SCRIPT}"
    assert m.group(1) == gate_mirror.PROD_HOST_DEFAULT


def test_monthly_pull_faces_have_no_local_rsync():
    """月轮脚本里非注释行的 rsync 只允许出现在推送段(锚 =
    EVAL_PUSH_DST 定义行,恰两行:dry-run 回显 + 实推);拉取面再手写
    就红,报错给出文件与行。唯一放行: honyport dry-run 说明回显行
    (提词文案,不含可执行的 rsync 命令)。"""
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    anchor = next((i for i, ln in enumerate(lines, 1)
                   if ln.startswith("EVAL_PUSH_DST=")), None)
    assert anchor, f"月轮脚本找不到 EVAL_PUSH_DST= 锚(推送段定位失败): {SCRIPT}"
    in_push: list[int] = []
    offenders: list[tuple[int, str]] = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("#") or not re.search(r"\brsync\b", ln):
            continue
        if i >= anchor:
            in_push.append(i)
        elif "实跑时先 ssh 探测远端" in ln:
            pass                       # honyport dry-run 提词行(历史回显文案)
        else:
            offenders.append((i, ln))
    assert not offenders, (
        "月轮脚本拉取面又出现了手写 rsync(应经 mirror-sync 单源入口): "
        + "; ".join(f"{SCRIPT}:{i}: {ln.strip()}" for i, ln in offenders))
    assert len(in_push) == 2, (
        "推送段 rsync 行数变了(应恰为 dry-run 回显+实推两行): "
        + ", ".join(f"line {i}" for i in in_push))


def test_honyport_probe_path_pinned_in_script():
    """honyport 远端路径(返工二-3):脚本非注释行里恰 3 处(干跑提示/
    缺席提示/ssh 探测),且出现的字面量就是契约常量——常量改名而脚本
    不改时这里红,路径漂移不出单源。"""
    needle = gate_mirror.HONYPORT_OUT_DIR          # == "/opt/honyport/out"
    hits = [ln for ln in SCRIPT.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("#") and needle in ln]
    assert len(hits) == 3, (
        f"月轮脚本非注释行里 {needle} 出现 {len(hits)} 次"
        "(应恰 3:干跑提示/缺席提示/ssh 探测):\n" + "\n".join(hits))


def test_three_face_command_items(tmp_path):
    """三面拼出的命令逐项断言:旗标(仅主面 --delete-after)、源路径带
    尾斜杠、目标带尾斜杠——与原月轮三段手写字面量同款;契约值本身按
    字面量钉死(远端路径无处推导,抄自原脚本)。"""
    dst = tmp_path / "d"
    common = ["rsync", "-az", "--partial", "--info=progress2"]
    assert gate_mirror.sync_face("root@h", "main", dst,
                                 dry_run=True)["command"] == [
        "rsync", "-az", "--partial", "--delete-after", "--info=progress2",
        f"root@h:{gate_mirror.PROD_DATA_DIR}/", f"{dst}/"]
    for face, src in (("truth-v2", gate_mirror.TRUTH_V2_CAPTURE_DIR),
                      ("honyport", gate_mirror.HONYPORT_OUT_DIR)):
        assert gate_mirror.sync_face("root@h", face, dst,
                                     dry_run=True)["command"] == [
            *common, f"root@h:{src}/", f"{dst}/"], face
    assert gate_mirror.PROD_DATA_DIR == (
        "/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data")
    assert gate_mirror.TRUTH_V2_CAPTURE_DIR == "/opt/ip-truth-capture"
    assert gate_mirror.HONYPORT_OUT_DIR == "/opt/honyport/out"
    assert gate_mirror.RSYNC_TOLERATED_RCS == frozenset({0, 24})
    assert gate_mirror.RSYNC_FLAGS_NO_DELETE == ["-az", "--partial",
                                                 "--info=progress2"]
    assert gate_mirror.RC24_NOTE == (
        "rsync rc=24(源侧活动文件消失,活镜像可容忍)")


class FakeRunner:
    """mirror-sync CLI 测试替身:不真跑 rsync,rc 可配。"""

    def __init__(self, rc: int):
        self.rc = rc
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]):
        self.calls.append(list(argv))
        return SimpleNamespace(returncode=self.rc, stdout="", stderr="")


def test_cli_dry_run_prints_only(tmp_path, capsys):
    """--dry-run:打印与改前逐字相同的回显行就退出 0,不跑 rsync 不建目录。"""
    dst = tmp_path / "d"
    stub = FakeRunner(0)
    code = mirror_sync_cli(["--host", "root@h", "--face", "main",
                            "--dst", str(dst), "--dry-run"], runner=stub)
    assert code == 0
    assert capsys.readouterr().out == (
        f"==> rsync: root@h:{gate_mirror.PROD_DATA_DIR}/ -> {dst}/\n")
    assert stub.calls == []            # 只回显不执行
    assert not dst.exists()            # dry-run 不建目录


def test_cli_rc24_tolerated_with_note(tmp_path, capsys):
    """rc=24(源侧活文件消失)容忍退 0,留痕行与月轮改前逐字同串。"""
    dst = tmp_path / "d"
    code = mirror_sync_cli(["--host", "root@h", "--face", "truth-v2",
                            "--dst", str(dst)], runner=FakeRunner(24))
    assert code == 0
    captured = capsys.readouterr()
    # 返工二-7:stdout 收成恰两行(回显 + 留痕),不再用 in 宽松判
    assert captured.out.splitlines() == [
        f"==> rsync(truth-v2 快照面): "
        f"root@h:{gate_mirror.TRUTH_V2_CAPTURE_DIR}/ -> {dst}/",
        f"-- {gate_mirror.RC24_NOTE}",
    ]
    assert dst.is_dir()                # 实跑自建目录(时机同旧 mkdir -p)


def test_cli_rc23_rejected_exit_1(tmp_path, capsys):
    """rc=23(非容忍):stderr 拒绝行带面标签,退出码 1;回显行照常走
    stdout(返工二-7)。"""
    dst = tmp_path / "d"
    code = mirror_sync_cli(["--host", "root@h", "--face", "honyport",
                            "--dst", str(dst)],
                           runner=FakeRunner(23))
    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == (
        f"==> rsync(honyport 日 CSV 面): "
        f"root@h:{gate_mirror.HONYPORT_OUT_DIR}/ -> {dst}/\n")
    assert "拒绝: honyport 日 CSV 面 rsync 失败 (rc=23)\n" in captured.err


def test_cli_main_face_rc23_message(tmp_path, capsys):
    """主面拒绝文案与 sync_gate_mirror 历史错误主干一致(reject 从空
    label 推导,返工二-8);回显行走 stdout(返工二-7)。"""
    dst = tmp_path / "d"
    code = mirror_sync_cli(["--face", "main", "--dst", str(dst)],
                           runner=FakeRunner(23))
    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == (
        f"==> rsync: {gate_mirror.PROD_HOST_DEFAULT}:"
        f"{gate_mirror.PROD_DATA_DIR}/ -> {dst}/\n")
    assert "拒绝: rsync 失败 (rc=23)\n" in captured.err


def test_cli_rsync_missing_one_line_rejection(tmp_path, capsys):
    """rsync 不在/起不来(FileNotFoundError 族,返工二-9):stderr 恰一行
    拒绝退 1,不甩 Python 栈;回显行照常先走 stdout。"""
    dst = tmp_path / "d"

    class MissingRunner:
        def __call__(self, argv: list[str]):
            raise FileNotFoundError(2, "No such file or directory", "rsync")

    code = mirror_sync_cli(["--face", "main", "--dst", str(dst)],
                           runner=MissingRunner())
    assert code == 1
    captured = capsys.readouterr()
    assert captured.out == (
        f"==> rsync: {gate_mirror.PROD_HOST_DEFAULT}:"
        f"{gate_mirror.PROD_DATA_DIR}/ -> {dst}/\n")
    err_lines = captured.err.splitlines()
    assert len(err_lines) == 1, captured.err
    assert err_lines[0].startswith("拒绝: rsync 失败(rsync 不在或起不来: ")
    assert "[Errno 2]" in err_lines[0]
    assert "Traceback" not in captured.err
    assert dst.is_dir()        # sync_face 先建目录后调 rsync(mkdir 时机不变)


def test_cli_main_face_guard_rejects_root(tmp_path, capsys):
    """主面护栏(返工二-11):目标解析为根目录 → 拒绝退 2,不回显不跑
    rsync(--delete-after 会把根目录清成镜像)。"""
    stub = FakeRunner(0)
    code = mirror_sync_cli(["--face", "main", "--dst", "/"], runner=stub)
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""             # 护栏在回显之前
    assert "拒绝: 目标目录不像生产卷镜像\n" in captured.err
    assert stub.calls == []               # 拒绝发生在 rsync 之前


def test_cli_main_face_guard_passes_with_heartbeat_entry(tmp_path, capsys):
    """主面护栏放行形(返工二-11):目标已存在、非空、含 eval-heartbeat
    条目 → 判定像生产卷镜像,照常回显并执行。"""
    dst = tmp_path / "d"
    dst.mkdir()
    (dst / "eval-heartbeat").touch()
    stub = FakeRunner(0)
    code = mirror_sync_cli(["--face", "main", "--dst", str(dst)], runner=stub)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert captured.out == (
        f"==> rsync: {gate_mirror.PROD_HOST_DEFAULT}:"
        f"{gate_mirror.PROD_DATA_DIR}/ -> {dst}/\n")
    assert len(stub.calls) == 1
