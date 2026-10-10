"""LMDB base 唯一性护栏(P1 热修,2026-10-10)。

事故:peeringdb/rir_delegated 都没声明 `filename`,基类推导
`_lmdb_base = data_dir / f"{self.filename}.lmdb"` 落到同一 `.lmdb` ——
两源共享同一个 LMDB 库,后重建者覆盖前者(生产实测:peeringdb 报
rir 的 263,718 计数,IX 数据被踩)。每源 tmp_path 隔离的测试对此天生
失明,本护栏在注册表层断言唯一性。
"""
import ipdb._registry as reg


def test_every_source_lmdb_base_unique_and_named():
    bases4: dict[str, str] = {}
    bases6: dict[str, str] = {}
    for s in reg._sources:
        b4 = str(getattr(s, "_lmdb_base", None) or "")
        b6 = str(getattr(s, "_lmdb6_base", None) or "")
        assert b4 and b6, (
            f"{s.name}: empty _lmdb_base — `filename` not declared and "
            f"base not overridden (shares the degenerate `.lmdb` base)")
        # base 名必须携带源自身身份(不得是裸 `.lmdb`/目录本身)
        assert s.name in b4 or (getattr(s, "filename", "") and s.filename in b4), (
            f"{s.name}: _lmdb_base {b4!r} does not carry this source's identity")
        assert b4 not in bases4, (
            f"{s.name}: _lmdb_base {b4!r} already used by {bases4[b4]} "
            f"(cross-source env collision — last rebuilder wins)")
        assert b6 not in bases6, (
            f"{s.name}: _lmdb6_base {b6!r} already used by {bases6[b6]}")
        bases4[b4] = s.name
        bases6[b6] = s.name
