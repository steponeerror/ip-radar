"""_curated_infra 名单单真源钉子(#466,架构评审第四轮卡 15;返工 2026-11-26)。

四样钉死(评审 Finding 2/3 + 主会话裁决):
- 名单文本只住一个文件:rows() 产出的整行针(f"{ip},{svc},{provider}",
  2026-11-26 时为 56 个)逐个在 backend/ipdb 的 *.py 里字节搜,每个只能
  命中 _curated_infra.py——抄第二份、漏一行、换一行都翻红;#439 改名单
  时针自动跟着名单走,不用再挑。只扫 *.py 的原因:__pycache__ 里的 .pyc
  是本模块自己的字节码,必然含针,不算「第二份」。
- infra_services._DATA is CURATED_CSV:「同一对象,不是第二份」
  (infra_services.py 的核心声明)从注释变成被测行为。
- 两套读法相等:addresses() 与 rows() 推导出的集合逐项相同——csv.reader
  与 split 两条解析从此不可能悄悄分叉。
- 往返一致:rows() 与 download 物化出的 data/ csv 回读逐项相同
  (rows() docstring 里那句声明的证据,#466 返工补)。
"""
import csv
import io
import ipaddress
from pathlib import Path

import ipdb._sources.infra_services as infra_services_mod
from ipdb._curated_infra import CURATED_CSV, addresses, rows


def test_roster_text_lives_in_exactly_one_file():
    """每个整行针在 backend/ipdb 的 *.py 里都只命中 _curated_infra.py。"""
    ipdb_root = Path(__file__).resolve().parents[2] / "ipdb"
    needles = [f"{ip},{svc},{provider}".encode()
               for ip, svc, provider in rows()]
    assert needles, "名单非空(空名单钉子空转)"
    hits: dict[bytes, set[Path]] = {}
    for p in sorted(ipdb_root.rglob("*.py")):
        data = p.read_bytes()
        for needle in needles:
            if needle in data:
                hits.setdefault(needle, set()).add(p)
    expected = {ipdb_root / "_curated_infra.py"}
    offenders = {n: sorted(map(str, ps)) for n, ps in hits.items()
                 if ps != expected}
    missing = [n for n in needles if n not in hits]
    assert not offenders and not missing, \
        f"offenders={offenders} missing={len(missing)}"


def test_same_object_not_a_second_copy():
    """infra_services._DATA is CURATED_CSV:同一对象,不是第二份。"""
    assert infra_services_mod._DATA is CURATED_CSV


def test_two_readers_agree():
    """addresses() 与 rows() 推导的集合逐项相同(两套解析不分叉)。"""
    assert addresses() == frozenset(
        ipaddress.ip_network(ip, strict=False)
        for ip, _svc, _provider in rows())


def test_rows_roundtrip_matches_materialized_csv(tmp_path):
    """rows() 与物化 csv 的回读逐项一致(投影同步 → 读回比对)。"""
    from ipdb._sources.infra_services import InfraServicesSource
    s = InfraServicesSource(data_dir=tmp_path)
    s.load()                    # 投影同步:csv 缺失即从 CURATED_CSV 物化
    materialized = [tuple(r) for r in csv.reader(io.StringIO(
        (tmp_path / "infra_services.csv").read_text(encoding="utf-8")))
        if r]
    assert rows() == materialized
