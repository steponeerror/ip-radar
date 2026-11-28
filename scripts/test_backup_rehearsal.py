"""scripts/backup_rehearsal.py 单测(#550 备份恢复演练)。

跑法(仓根,backend venv 解释器): pytest scripts/test_backup_rehearsal.py -q

钉什么(每条想清楚在什么变异下会红):
- families():STRING concat 布局(_sources/_lmdb.py 禁 with_suffix)——
  改成 with_suffix 会把 `.lmdb` 段吃掉,路径形状断言红;
- check_envs():.count 旁证 ↔ env entries 逐族对账,对不上/旁证缺席/纪元
  目录缺席都要具名红——「去掉记录数对账」的变异(票面变异证据③)在
  test_script_reports_count_mismatch 红:夹具故意 .count=2 / env=3,脚本
  输出必须含「≠ env entries」明细,删掉对账步骤该明细消失、断言红;
  「改回 stat() 计数」的变异(评审建议改3)也在同一条红:夹具 env 带
  payloads 命名子库(主库多一条键字面 b"payloads" 的登记记录),stat()
  = 逐键数+1,与 .count 对不上;
- 演练脚本对好夹具的第 1/3 样零失败(check_envs 直接断言)。
第 2 样(真查询)走真镜像,夹具造不出 70 源全绿的 registry——绿证据 =
在真 .eval-prod-data 上实跑一次,输出贴 impl-report(票面要求)。
"""
import struct
import subprocess
import sys
from pathlib import Path

import lmdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backup_rehearsal as br  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "backup_rehearsal.py"


def _make_family(data_dir: Path, name: str, epoch: int, keys: int,
                 count: int | None) -> Path:
    """造一族:<name>.lmdb.<epoch>/ 真 LMDB env(keys 个 4 字节键)+
    <name>.lmdb.ptr + <name>.lmdb.count 旁证(count=None = 不写旁证)。
    env 带 payloads 命名子库并放一条记录(#550 评审建议改3):真写方
    (_sources/_lmdb.py)提交时主库含键字面 b"payloads" 的登记记录,
    .count 同律减 1 —— 夹具同形,「改回 stat() 计数」的变异才会红。"""
    base = data_dir / name
    env_dir = data_dir / f"{name}.{epoch}"
    env = lmdb.open(str(env_dir), map_size=1 << 20, subdir=True, max_dbs=2)
    psub = env.open_db(b"payloads")  # 登记记录落在主库(键字面 b"payloads")
    with env.begin(write=True, db=psub) as txn:
        txn.put(struct.pack(">I", 99_000), struct.pack(">I", 99_001))
    with env.begin(write=True) as txn:
        for i in range(keys):
            txn.put(struct.pack(">I", 10_000 + i), struct.pack(">I", 20_000 + i))
    env.close()
    (data_dir / f"{name}.ptr").write_text(f"{epoch}\n")
    if count is not None:
        (data_dir / f"{name}.count").write_text(f"{count}\n")
    return base


@pytest.fixture()
def good_dir(tmp_path: Path) -> Path:
    """对得上的迷你镜像:v4 族 count=3=entries;v6 族同样平。"""
    _make_family(tmp_path, "alpha.csv.lmdb", epoch=7, keys=3, count=3)
    _make_family(tmp_path, "beta.txt.v6.lmdb", epoch=2, keys=1, count=1)
    return tmp_path


def test_families_string_concat_layout(good_dir: Path):
    """族清单路径形状:base/env/count 全按 STRING concat(.lmdb 段不被
    with_suffix 吃掉),v6 族按 `.v6.lmdb` 结尾识别。"""
    fams = br.families(good_dir)
    assert [f["base"].name for f in fams] == ["alpha.csv.lmdb", "beta.txt.v6.lmdb"]
    alpha = fams[0]
    assert alpha["env_dir"].name == "alpha.csv.lmdb.7"
    assert alpha["count_path"].name == "alpha.csv.lmdb.count"
    assert alpha["v6"] is False and fams[1]["v6"] is True


def test_check_envs_green_when_count_matches(good_dir: Path):
    """对得上:check_envs 零失败,entries 记进族清单(第 1+3 样绿态)。"""
    opened, fails = br.check_envs(good_dir)
    assert fails == []
    assert {f["base"].name: f["entries"] for f in opened} == {
        "alpha.csv.lmdb": 3, "beta.txt.v6.lmdb": 1}


def test_script_reports_count_mismatch(tmp_path: Path):
    """票面变异证据③的判别测试:.count=2 / env entries=3 的夹具,演练脚本
    必须红且输出含「≠ env entries」记录数明细——实现里去掉对账那步,该
    明细消失、本测试红(exit code 不够判别:lookup 腿在夹具上必败,rc 恒 1)。
    全程 subprocess:脚本会把 IP_RADAR_DATA_DIR 指到夹具,不污染本进程。"""
    _make_family(tmp_path, "alpha.csv.lmdb", epoch=7, keys=3, count=2)
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "≠ env entries" in r.stdout, r.stdout
    assert "REHEARSAL fail" in r.stdout


def test_env_dir_absent_is_named_failure(tmp_path: Path):
    """ptr 在场但纪元目录缺席(半截 rsync 形态):具名失败,不静默。"""
    _make_family(tmp_path, "alpha.csv.lmdb", epoch=7, keys=1, count=1)  # 旧纪元仍在
    (tmp_path / "alpha.csv.lmdb.ptr").write_text("9\n")  # ptr 指向缺席的纪元 9
    opened, fails = br.check_envs(tmp_path)
    assert len(fails) == 1 and "纪元目录缺席" in fails[0]
    assert opened == []


def test_missing_data_dir_fails_fast(tmp_path: Path):
    """目录不存在:REHEARSAL fail 退出 1(不进任何核对)。"""
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "nope")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert "数据目录不存在" in r.stdout
