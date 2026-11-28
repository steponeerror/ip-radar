#!/usr/bin/env python3
"""备份恢复演练(#550):拿一份月轮镜像当数据目录,只读起一次真实查询,核对三样。

背景(#550 / 调研 #549 表第 19 行):月轮 scripts/monthly_eval.sh 每月把生产
数据卷 rsync 到本机 `.eval-prod-data`(经 backend/ipdb/_eval/gate_mirror.py
SYNC_FACES 三面),这是全项目唯一的备份,但在本脚本之前没有任何地方把它叫
备份,也从未验证过能从它恢复。本脚本 = 恢复演练:证明「镜像目录当
IP_RADAR_DATA_DIR 起一个只读查询进程」这条恢复路是通的。

核对三样(票面口径,逐条落 `REHEARSAL ok|fail` 尾行,退出码 0/1):
  1. 镜像清单里的源都能打开:每个 `<base>.lmdb.ptr` 指向的当前纪元 env
     只读打开成功(lmdb.open readonly,open_env_read 同参;真查询路径另由
     第 2 样覆盖:registry.load_db 后逐源查 load_error)。
  2. 随机抽 N(缺省 20)个地址查得到结果:从各源 v4 主库键空间 set_range
     随机抽地址(键=4 字节大端 start_ip,见 _sources/_lmdb.py 布局注释),
     ipdb._registry.load_db() 后逐个 lookup——查不抛异常即过(留证据计数:
     其中多少条带证人)。
  3. 旁证文件 `.lmdb.count` 的记录数和清单对得上:每族 .count 旁证
     (= commit 时从主库 entries 回写的键数,DQ-2)与 LMDB env 主库
     entries 实数逐一相等。注:mirror-manifest.json 只有全库 files/bytes,
     无逐源记录数,故「清单」口径 = 每族 .count 旁证 ↔ env 实数。

用法(解释器必须带 lmdb,即 backend venv):
  backend/.venv/bin/python scripts/backup_rehearsal.py <镜像目录> \
      [--samples 20] [--seed 20261128]
只读纪律:全程 IP_RADAR_POOL_CHILD=1(防 Source.load 的 cleanup_stale 删
镜像旧纪元,scripts/fusion_replay_gate.py 文件头同款),不写镜像目录。

测试:scripts/test_backup_rehearsal.py(夹具=手工造的迷你数据目录;变异
证据③=去掉第 3 样核对后,对不上的夹具不再红)。
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import random
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SEED = 20261128          # 固定 seed:同镜像重跑抽到同一组地址(可复现)

import lmdb  # noqa: E402  (backend venv;用法行见模块 docstring)


def families(data_dir: Path) -> list[dict]:
    """扫 `<base>.lmdb.ptr` 得源族清单(base 如 `abuseipdb.txt.lmdb`,
    v6 族 base 以 `.v6.lmdb` 结尾)。epoch/计数文件路径均按 STRING concat
    布局(_sources/_lmdb.py,禁 with_suffix)。"""
    out = []
    for ptr in sorted(data_dir.rglob("*.lmdb.ptr")):
        base = ptr.parent / ptr.name[:-len(".ptr")]
        out.append({
            "base": base,
            "ptr": ptr,
            "env_dir": Path(f"{base}.{ptr.read_text().strip()}"),
            "count_path": Path(f"{base}.count"),
            "v6": base.name.endswith(".v6.lmdb"),
        })
    return out


def open_readonly(env_dir: Path):
    """查询侧同参只读打开(readonly + lock=False + readahead=False,
    _lmdb.open_env_read 同款;演练不注册句柄表,用完即关)。"""
    return lmdb.open(str(env_dir), readonly=True, lock=False, subdir=True,
                     readahead=False, max_dbs=2)   # pidx + payloads sub-dbs


def check_envs(data_dir: Path) -> tuple[list[dict], list[str]]:
    """第 1+3 样:逐族打开当前纪元 env,env 主库 entries 与 .count 旁证对账。
    返回 (带 entries 的族清单, 失败明细)。ptr 不可读/纪元目录缺席/env 打不开
    /count 旁证缺席或对不上,都是失败项(无证据≠清白)。"""
    fails: list[str] = []
    opened: list[dict] = []
    for fam in families(data_dir):
        label = fam["base"].relative_to(data_dir).as_posix()
        try:
            epoch = fam["ptr"].read_text().strip()
        except OSError as e:
            fails.append(f"{label}: ptr 不可读({e})")
            continue
        if not fam["env_dir"].is_dir():
            fails.append(f"{label}: 纪元目录缺席(ptr={epoch})")
            continue
        try:
            env = open_readonly(fam["env_dir"])
        except lmdb.Error as e:
            fails.append(f"{label}: env 打不开({e})")
            continue
        try:
            entries = env.stat()["entries"]
        finally:
            env.close()
        opened.append({**fam, "entries": entries})
        try:
            counted = int(fam["count_path"].read_text().strip())
        except (OSError, ValueError):
            fails.append(f"{label}: .count 旁证缺席/不可读(entries={entries})")
            continue
        if counted != entries:
            fails.append(f"{label}: .count={counted} ≠ env entries={entries}"
                         "(记录数对不上)")
    return opened, fails


def lookup_probe(data_dir: Path, samples: int, seed: int) -> list[str]:
    """第 2 样:镜像当数据目录只读起真实查询(load_db + 逐源 load_error 检查
    + 随机抽地址 lookup)。返回失败明细(空=过)。须在设好 IP_RADAR_DATA_DIR
    后由 main 调用(import ipdb 前置,数据目录单一真源)。"""
    os.environ.setdefault("IP_RADAR_POOL_CHILD", "1")  # 防 cleanup_stale 删镜像旧纪元
    os.environ["IP_RADAR_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(REPO / "backend"))
    import ipdb._registry as registry  # noqa: PLC0415  (env 设好后才能 import)

    fails: list[str] = []
    registry.load_db()
    broken = [s.name for s in registry._sources
              if getattr(s, "load_error", None)]
    if broken:
        fails.append(f"load_db 后 {len(broken)} 源 load_error: "
                     f"{', '.join(sorted(broken)[:8])}"
                     f"{'…' if len(broken) > 8 else ''}")

    # 抽样池:打开第 1 样里健康的 v4 族,从键空间随机抽(键=4 字节大端
    # start_ip;set_range 到随机 4 字节取首个 ≥ 键 = 均匀覆盖键空间的抽法)
    opened, _ = check_envs(data_dir)
    v4 = [f for f in opened if not f["v6"] and f["entries"] > 0]
    if not v4:
        return fails + ["抽样池空:无健康 v4 族可抽地址"]
    rng = random.Random(seed)
    picked: list[str] = []
    for i in range(samples):
        fam = v4[i % len(v4)]
        env = open_readonly(fam["env_dir"])
        try:
            with env.begin() as txn:
                cur = txn.cursor()
                want = struct.pack(">I", rng.getrandbits(32))
                if not cur.set_range(want) or not cur.key():
                    cur.first()
                key = cur.key()
        finally:
            env.close()
        if len(key) != 4:
            continue  # v4 族里混进异常键长:跳过不猜,样本数由实抽数报
        picked.append(str(ipaddress.ip_address(key)))

    ok_n = with_evidence = 0
    for ip in picked:
        try:
            res = registry.lookup(ip)
        except Exception as e:  # noqa: BLE001  (演练面:任何异常都是恢复路不通)
            fails.append(f"lookup({ip}) 抛异常: {type(e).__name__}: {e}")
            continue
        if res.error is not None:
            fails.append(f"lookup({ip}) 返回错误: {res.error}")
            continue
        ok_n += 1
        if res.classifications or res.attributes:
            with_evidence += 1
    if ok_n < samples:
        fails.append(f"lookup 成功 {ok_n}/{samples}(须全过)")
    print(f"-- lookup 抽样(seed={seed}): {ok_n}/{len(picked)} 成功,"
          f"其中 {with_evidence} 条带证人/陈述")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description="备份恢复演练(#550;镜像目录只读)")
    ap.add_argument("data_dir", type=Path, help="镜像数据目录(如 .eval-prod-data)")
    ap.add_argument("--samples", type=int, default=20, help="抽查处数(缺省 20)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help=f"抽样 seed(缺省 {DEFAULT_SEED},可复现)")
    args = ap.parse_args()
    data_dir = args.data_dir.resolve()
    if not data_dir.is_dir():
        print(f"REHEARSAL fail: 数据目录不存在: {data_dir}")
        return 1

    print(f"==> 演练数据目录: {data_dir}(只读;IP_RADAR_POOL_CHILD=1)")
    fams = families(data_dir)
    print(f"==> 源族(ptr 在场): {len(fams)} 族(v6 {sum(f['v6'] for f in fams)})")

    # os.environ 先于一切 ipdb import(数据目录单一真源);check_envs 不依赖
    # ipdb,lookup_probe 内部才 import。
    os.environ.setdefault("IP_RADAR_POOL_CHILD", "1")
    os.environ["IP_RADAR_DATA_DIR"] = str(data_dir)
    _, env_fails = check_envs(data_dir)
    for f in env_fails:
        print(f"  FAIL {f}")
    fails = list(env_fails)

    fails += lookup_probe(data_dir, args.samples, args.seed)

    if fails:
        print(f"REHEARSAL fail({len(fails)} 项不达标):")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"REHEARSAL ok: {len(fams)} 族 env 全开、.count 对账全平、"
          f"lookup {args.samples} 抽查全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
