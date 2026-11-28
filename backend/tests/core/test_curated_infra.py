"""_curated_infra 名单单真源钉子(#466,架构评审第四轮卡 15;返工 2026-11-26)。

四样钉死(评审 Finding 2/3 + 主会话裁决):
- 名单文本只住一个文件:rows() 产出的整行针(f"{ip},{svc},{provider}",
  2026-11-26 时为 56 个;2026-11-28 #439 扩员 Quad9 六址后为 62 个)逐个在
  backend/ipdb 的 *.py 里字节搜,每个只能
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


def test_quad9_expansion_439():
    """#439(2026-11-28 裁决):名单扩员 Quad9 两档六地址,巡检锚弃 9.9.9.4
    换官方 Unsecured 两员。变异面:①锚表回填 9.9.9.4 → 末条断言红
    (selftest.sh §14 锚集对拍哨同批红:py↔JS 单源镜像漂移);
    ②名单删 9.9.9.11 行 → 计数断言红(61≠62;整行针随名单自动走,
    test_roster_text_lives_in_exactly_one_file 不会红——针从 rows() 生成,
    源删行针同删,test_infra_services 的 48/14 族计数钉同批红)。
    出处 https://quad9.net/service/service-addresses-and-features/
    (2026-11-28 核)。"""
    ips = {ip for ip, _svc, _provider in rows()}
    assert len(ips) == 62, f"名单 62 员(#439 后),实际 {len(ips)}"
    assert {"9.9.9.10", "149.112.112.10", "9.9.9.11", "149.112.112.11",
            "2620:fe::11", "2620:fe::fe:11"} <= ips, "Quad9 两档六地址缺员"
    from ipdb._eval.anchors import ANCHORS
    anchor_ips = {ip for ip, _k in ANCHORS}
    assert "9.9.9.4" not in anchor_ips, "9.9.9.4 无官方出处,不得回填锚表"
    assert {"9.9.9.10", "149.112.112.10"} <= anchor_ips, "Unsecured 两锚缺员"
