# backend/ipdb/_eval/gate_mirror.py
"""gate 镜像管理: 接入关跑前增量同步生产数据镜像并对齐源 epoch (S7+Q11)。

S7 (spec 2026-10-12-eval-loop-hardening-design.md §4.1: 接入关镜像对齐契约
= 每次 gate 跑前比对源 epoch) × Q11 (§3.1: 本地常驻 `.eval-gate-mirror/`
增量镜像, 已 gitignore): gate 跑之前 ①rsync 增量同步生产 volume → 本地
镜像 ②ssh 读远端逐源 epoch ③与镜像逐源比对——失配必须拒跑 (fail-closed:
raise GateMirrorMisalignedError, 绝不降级为警告;gate 由调用方在异常后
不再启动, 测量建言人裁终局)。

rsync 同步契约(#489 起)唯一住在下方常量与 SYNC_FACES: 接入关 main 面与
月轮三拉取面(monthly_eval.sh 经 `python -m ipdb._eval mirror-sync` 调
sync_face)共用一份, 语义出处(原 monthly_eval.sh 手写段, 随收口迁此):
- 源路径 `<host>:/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data/`
  (尾斜杠=拷内容), 旗标 `-az --partial --delete-after --info=progress2`;
- rc=24 (源侧活文件消失——生产 scheduler 随时在重建 LMDB epoch, 旧 epoch
  家族中途消失属常态) 当成功, 其余非零致命: 修法出处 commit 35c64b97
  (首月轮 2026-10-14 实测发现)。

epoch 口径: 口径同 mirror_check._epoch_fingerprint, 逐源展开——该函数把
全部 *.ptr 聚合成单哈希 str (S6 新鲜度哨兵用), 本模块需要逐源
dict[str, str] 供失配具名列源名, 形状不同不强行抽公共。真实纪元标记 =
每源 `<base>.lmdb.ptr` 一行整数 (_sources/_lmdb.py read_ptr);不可读 ptr
记 "?" 不炸 (缺证据≠对齐, 由 check_alignment 的双空守卫兜)。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, Sequence

# 生产 volume 数据目录 (尾斜杠在拼命令时加;原 monthly_eval.sh RSYNC_SRC
# 同源, #489 起源路径只在此定义一次)
PROD_DATA_DIR = "/var/lib/docker/volumes/ip-lookup-tool_ipradar-data/_data"
# truth-v2 周快照采集面 / honyport 蜜罐日 CSV 面(卷外目录, ADR 0017;
# 收口前(8fe7d5a6 的 monthly_eval.sh)字面量, #489 起同在此单源)
TRUTH_V2_CAPTURE_DIR = "/opt/ip-truth-capture"
HONYPORT_OUT_DIR = "/opt/honyport/out"
# 生产机地址唯一缺省(monthly_eval.sh PROD_HOST 同值, 两边由对拍测试钉;
# 原 __main__._PROD_HOST_DEFAULT 第二份已删, #489)
PROD_HOST_DEFAULT = "root@203.88.124.85"

RSYNC_FLAGS = ["-az", "--partial", "--delete-after", "--info=progress2"]
# 快照/蜜罐组件面旗标 = 主面去掉 --delete-after(增量拉取不删本地既有件;
# 收口前 monthly_eval.sh 快照/蜜罐面手写同款, #489 起推导自同一字面量)
RSYNC_FLAGS_NO_DELETE = [f for f in RSYNC_FLAGS if f != "--delete-after"]
# 24 = vanished source files, 活镜像良性可容忍 (monthly_eval.sh, commit 35c64b97)
RSYNC_TOLERATED_RCS = frozenset({0, 24})
# rc 24 留痕文案唯一一份(月轮 mirror-sync 与 sync_gate_mirror 的 note 同串)
RC24_NOTE = "rsync rc=24(源侧活动文件消失,活镜像可容忍)"

# 三个拉取面的同步契约(#489: 源路径/旗标/屏幕标签各定义一次;
# 收口前(8fe7d5a6 的 monthly_eval.sh)三段手写旗标与 rc 判断退役, 月轮经
# mirror-sync CLI 调同一份 sync_face)。reject = `拒绝: <reject> (rc=N)`
# 文案主干, 从 label 推导(评审建议 9: 面名不写两遍, 主面 label 空 →
# `rsync 失败`);label = 回显行 `==> rsync(<label>): …`(空=无标签主面)。
SYNC_FACES = {
    "main": {
        "src": PROD_DATA_DIR,
        "flags": RSYNC_FLAGS,             # 含 --delete-after: 主镜像=镜像语义
        "label": "",
    },
    "truth-v2": {
        "src": TRUTH_V2_CAPTURE_DIR,
        "flags": RSYNC_FLAGS_NO_DELETE,
        "label": "truth-v2 快照面",
    },
    "honyport": {
        "src": HONYPORT_OUT_DIR,
        "flags": RSYNC_FLAGS_NO_DELETE,
        "label": "honyport 日 CSV 面",
    },
}
for _spec in SYNC_FACES.values():
    _spec["reject"] = f"{_spec['label']} rsync 失败".strip()

# 远端逐源 epoch 读取: 每行 `name=value` (printf 名=值);cat 失败记 "?",
# 与本地 OSError → "?" 同口径。经 sort 保证输出序确定。
_REMOTE_EPOCH_SH = (
    'find "{dir}" -name "*.ptr" -type f | sort | '
    'while IFS= read -r f; do printf "%s=%s\\n" "${{f##*/}}" '
    '"$(cat "$f" 2>/dev/null || echo ?)"; done'
)


class GateMirrorMisalignedError(RuntimeError):
    """S7 接入关镜像 epoch 失配: 拒绝跑 gate (fail-closed, 不降级为警告)。"""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    """默认 command runner (subprocess, capture 输出);测试注入 stub 替身。"""
    return subprocess.run(argv, check=False, capture_output=True, text=True)


def _run_passthrough(argv: list[str]) -> subprocess.CompletedProcess:
    """透屏 runner(#489 月轮 mirror-sync 用): rsync 进度直出屏幕不捕获,
    stderr 不进错误尾(屏幕上已可见)。"""
    return subprocess.run(argv, check=False)


def sync_face(prod_host: str, face: str, dst: Path | str, *,
              dry_run: bool = False, capture: bool = True,
              raise_on_fail: bool = True,
              runner: Callable[[list[str]], Any] | None = None,
              exclude: Sequence[str] = ()) -> dict:
    """同步一个生产拉取面(#489 同步契约唯一实现: 拼命令 + 跑 + 判 rc)。

    face ∈ SYNC_FACES(源路径/旗标/拒绝文案全从契约表出, 调用方不再自持);
    dst=本地目录(尾斜杠拼命令时加;实跑前 mkdir -p,dry-run 不落盘)。
    capture=True 输出走 runner 捕获(接入关路径);False 直接透屏(月轮
    要看到进度)。注入 runner 时优先于 capture 选择(测试替身)。
    rc∈RSYNC_TOLERATED_RCS → ok=True(rc=24 附 RC24_NOTE 留痕);其余:
    raise_on_fail 时 raise RuntimeError(f"{reject} (rc=…){stderr 尾}",
    文案与 sync_gate_mirror 历史一致), 否则返回 ok=False 交调用方裁决
    退出码(mirror-sync CLI 据此打拒绝行)。exclude=额外 --exclude 模式
    (preserve 候选豁免由 sync_gate_mirror 组装后传入)。
    """
    spec = SYNC_FACES[face]
    argv = ["rsync", *spec["flags"]]
    argv += [f"--exclude={pat}" for pat in exclude]
    argv += [f"{prod_host}:{spec['src']}/", f"{Path(dst)}/"]
    if dry_run:
        return {"ok": True, "dry_run": True, "rc": None, "command": argv,
                "note": ""}
    Path(dst).mkdir(parents=True, exist_ok=True)
    run = runner or (_run if capture else _run_passthrough)
    proc = run(argv)
    rc = proc.returncode
    if rc not in RSYNC_TOLERATED_RCS:
        if raise_on_fail:
            raise RuntimeError(
                f"{spec['reject']} (rc={rc}){_stderr_tail(proc)}")
        return {"ok": False, "dry_run": False, "rc": rc, "command": argv,
                "note": ""}
    note = RC24_NOTE if rc == 24 else ""
    return {"ok": True, "dry_run": False, "rc": rc, "command": argv,
            "note": note}


def _stderr_tail(proc: Any) -> str:
    err = (getattr(proc, "stderr", "") or "").strip()
    return f": {err[-200:]}" if err else ""


def sync_gate_mirror(prod_host: str, mirror_dir: Path, dry_run: bool = False,
                     *, runner: Callable[[list[str]], Any] | None = None,
                     preserve: str | None = None) -> dict:
    """rsync 增量同步生产 volume → mirror_dir (main 面契约, SYNC_FACES["main"])。

    dry_run 只回显将执行的命令, 不执行不落盘 (monthly_eval.sh --dry-run
    同义);rc∉{0, 24} → raise (fail-closed);rc=24 当成功并留痕 note。
    preserve=候选源名 → --exclude 使其文件既不传输也不被 --delete-after
    清除 (镜像内物化的候选 raw/LMDB/ptr 跨 sync 存活, 候选豁免同口径)。
    #489 起为 sync_face(main 面)薄壳: 旗标/容忍集/留痕文案全部出自
    SYNC_FACES 契约, 本函数只负责接入关自己的 preserve 豁免与返回形状
    (返回形状/RuntimeError 文案与收口前逐字一致, 现有测试不改)。
    """
    exclude: tuple[str, ...] = ()
    if preserve is not None:
        # 排除模式与 check_measurement_alignment 的 `<candidate>.` 前缀豁免
        # 同口径 (review-loop round-1 P0; rsync --exclude 同时豁免传输与
        # --delete —— 无它, --gate 的前置 sync 会删掉镜像内刚物化的候选,
        # gate 变成空候选测量却 S7 全绿)。
        exclude = (preserve, f"{preserve}.*")
    return sync_face(prod_host, "main", mirror_dir, dry_run=dry_run,
                     runner=runner, exclude=exclude)


def epoch_fingerprint(data_dir: Path) -> dict[str, str]:
    """逐源 epoch 映射 `{<ptr 文件名>: 值}`。

    口径同 mirror_check._epoch_fingerprint, 逐源展开 (该处聚合单哈希,
    此处逐源值映射供对齐失配具名);不可读 ptr 记 "?" 不炸。
    """
    out: dict[str, str] = {}
    for p in sorted(Path(data_dir).rglob("*.ptr")):
        try:
            out[p.name] = p.read_text(encoding="utf-8").strip()
        except OSError:
            out[p.name] = "?"
    return out


def check_alignment(mirror_dir: Path, prod_epochs: dict,
                    candidate: str | None = None) -> dict:
    """逐源比对镜像 vs 生产 epoch: 值失配/单侧缺席皆失配, detail 列源名。

    双侧皆无任何 ptr 证据 (路径错/半截同步) → aligned=False: 无证据≠对齐。
    candidate=候选源名 → `<candidate>.` ptr 族不计: 候选新 ptr 只在镜像
    物化侧, 生产快照没有 (gate 物化 carve-out, 口径同
    check_measurement_alignment 与 sync --exclude 保留, review-loop
    round-1 P0 —— 无此豁免, preserve 保住的候选 ptr 会被本函数拒跑)。
    """
    mirror_epochs = epoch_fingerprint(mirror_dir)
    if not mirror_epochs and not prod_epochs:
        return {"aligned": False,
                "detail": "no epoch evidence: 0 ptr sources on mirror and prod"}
    prefix = f"{candidate}." if candidate is not None else None
    bad = []
    compared = 0
    for name in sorted(set(mirror_epochs) | set(prod_epochs)):
        if prefix is not None and name.startswith(prefix):
            continue                     # 候选豁免: 物化侧新 ptr, 生产快照没有
        compared += 1
        mv, pv = mirror_epochs.get(name), prod_epochs.get(name)
        if mv == pv:
            continue
        if mv is None:
            bad.append(f"{name}: mirror missing (prod={pv})")
        elif pv is None:
            bad.append(f"{name}: prod missing (mirror={mv})")
        else:
            bad.append(f"{name}: mirror={mv} prod={pv}")
    if bad:
        return {"aligned": False, "detail": "; ".join(bad)}
    return {"aligned": True, "detail": f"aligned ({compared} sources)"}


def check_measurement_alignment(data_dir: Path, mirror_epochs: dict,
                                candidate: str) -> dict:
    """S7 测量对齐(终审 Issue-1): 测量数据目录 vs 镜像快照逐源 epoch 比对。

    check_alignment 只保证「镜像 ↔ 生产」对齐; 测量真值另查 —— registry
    数据目录(data_dir)逐源 epoch 必须与镜像快照(mirror_epochs, 取
    ensure_gate_mirror 返回的 mirror_epochs)一致, 否则 S7 对测量零约束
    (镜像对齐了, 测的却是本地 dev 数据 = 虚假保证)。失配含 data_dir 缺
    某源 ptr(缺证据≠对齐); 候选豁免: 候选新 ptr 只存在于物化侧, 镜像
    生产快照没有 —— `<candidate>.` ptr 族(materialize_source.sh 物化产物
    同款命名, house style filename==name)整族不计, 兼容 filename≠name
    的老源前缀(如 threatfox.csv.lmdb.ptr); (--gate 前置 sync 现以
    --exclude 同口径保留候选文件, review-loop round-1 P0)双侧皆无 ptr
    证据 → 不对齐(check_alignment 同守卫)。
    """
    data_epochs = epoch_fingerprint(data_dir)
    if not data_epochs and not mirror_epochs:
        return {"aligned": False,
                "detail": "no epoch evidence: 0 ptr sources in data_dir and mirror"}
    prefix = f"{candidate}."
    bad = []
    compared = 0
    for name in sorted(set(data_epochs) | set(mirror_epochs)):
        if name.startswith(prefix):
            continue                     # 候选豁免: 物化侧新 ptr, 生产快照没有
        compared += 1
        dv, mv = data_epochs.get(name), mirror_epochs.get(name)
        if dv == mv:
            continue
        if dv is None:
            bad.append(f"{name}: data_dir missing (mirror={mv})")
        elif mv is None:
            bad.append(f"{name}: mirror missing (data_dir={dv})")
        else:
            bad.append(f"{name}: data_dir={dv} mirror={mv}")
    if bad:
        return {"aligned": False, "detail": "; ".join(bad)}
    return {"aligned": True, "detail": f"aligned ({compared} sources)"}


def _remote_epochs(prod_host: str, *,
                   runner: Callable[[list[str]], Any] | None = None) -> dict[str, str]:
    """ssh 读远端逐源 epoch (`name=value` 行);rc≠0 → raise (fail-closed)。"""
    runner = runner or _run
    proc = runner(["ssh", prod_host, _REMOTE_EPOCH_SH.format(dir=PROD_DATA_DIR)])
    if proc.returncode != 0:
        raise RuntimeError(
            f"ssh 远端 epoch 读取失败 (rc={proc.returncode}){_stderr_tail(proc)}")
    out: dict[str, str] = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, val = line.partition("=")
        out[name] = val
    return out


def ensure_gate_mirror(prod_host: str, mirror_dir: Path, *,
                       runner: Callable[[list[str]], Any] | None = None,
                       preserve: str | None = None) -> dict:
    """gate 前置序: sync → ssh 读远端 epoch → 逐源比对;失配 raise 拒跑。

    返回摘要 dict (sync 结果 + 双侧逐源 epoch + alignment);失配 raise
    GateMirrorMisalignedError (detail 列失配源名), 调用方不得继续跑 gate
    (S7 fail-closed)。preserve=候选源名 透传 sync 豁免与 check_alignment
    候选豁免 (候选物化产物跨 sync 存活且不触发失配拒跑,
    review-loop round-1 P0)。
    """
    sync = sync_gate_mirror(prod_host, mirror_dir, runner=runner,
                            preserve=preserve)
    prod = _remote_epochs(prod_host, runner=runner)
    alignment = check_alignment(mirror_dir, prod, candidate=preserve)
    if not alignment["aligned"]:
        raise GateMirrorMisalignedError(alignment["detail"])
    return {
        "sync": sync,
        "prod_epochs": prod,
        "mirror_epochs": epoch_fingerprint(mirror_dir),
        "alignment": alignment,
    }
