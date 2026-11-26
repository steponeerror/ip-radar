"""The 6 source conventions, enforced as tests. If a source violates one, this
file fails — that's the point (catch it before merge, not in production)."""
import time
from pathlib import Path
from ipdb._registry import _sources
from ipdb._classification import CLASSIFICATION_TYPES


def test_every_typed_source_preserves_native_type():
    for s in _sources:
        ctype = getattr(s, "classification_type", None)
        if not ctype:
            continue
        # smoke: the source's get_insert_data/parse_row path must include
        # native_type. We check the declared classification is in vocab and
        # trust the base classes (Task 1.5) wire native_type. Full proof is the
        # round-trip test (2.3).
        assert ctype in CLASSIFICATION_TYPES or ctype == "other", \
            f"{s.name}: classification_type {ctype!r} not in vocab"


def test_staleness_uses_file_mtime():
    """Convention 4: staleness/last_updated derived from the DATA FILE's
    mtime, not in-memory _loaded_at.

    #465 卡16 返工(主会话授权):算法本体已搬进 _sources/_freshness,
    旧巡检(health() 源码含 st_mtime)对谁都恒真、守卫空转。新契约:
    health() 要么自己读文件时间(st_mtime),要么交给基类
    (super().health())或新模块(_freshness)算——三者皆无 = 新鲜度
    另有来路,即红;另锚真正 stat 文件的 newest_mtime 必须出现
    st_mtime(词边界,防函数名 newest_mtime 子串假满足)。
    """
    import inspect
    import re
    from ipdb._sources import _freshness
    assert re.search(r"\bst_mtime\b",
                     inspect.getsource(_freshness.newest_mtime)), \
        "_freshness.newest_mtime 必须读文件修改时间(st_mtime)"
    for s in _sources:
        if not hasattr(s, "_path"):
            continue
        src = inspect.getsource(type(s).health)
        assert ("st_mtime" in src or "super().health()" in src
                or "_freshness" in src), \
            f"{s.name}: health() 必须读文件 mtime 或交给 _freshness/基类算"


def test_sources_read_own_env_not_registry_args():
    """Convention 5: registry instantiates as cls(data_dir=data_dir) only."""
    import inspect
    from ipdb import _registry
    src = inspect.getsource(_registry._discover_sources)
    assert "data_dir=data_dir" in src
    assert "api_key" not in src.lower() and "key=" not in src.replace("data_dir=", "")


def test_filename_matches_name_house_style():
    for s in _sources:
        fn = getattr(s, "filename", None)
        if fn:
            assert s.name in fn or fn.startswith(s.name) or getattr(s, "url", ""), \
                f"{s.name}: filename {fn!r} should match name (house style)"


def test_verdict_is_stable_string():
    for s in _sources:
        v = getattr(s, "verdict", None)
        if v is not None:
            assert v in ("malicious", "suspicious", "benign", "informational"), \
                f"{s.name}: verdict {v!r} not a stable verdict"


def test_unmappable_falls_to_other():
    """Convention 2: normalize() returns 'other' for unmappable values."""
    from ipdb._classification import normalize
    assert normalize("totally_bogus_value_xyz", {}) == "other"
    assert normalize("", {}) == "other"

def test_sources_never_close_readers_in_rebuild():
    """FIX7 回归守卫:rebuild 路径禁止重引入 old_reader 显式 close ——
    查询线程在途 txn 下的 close 是段错误,且失败路径会误杀现役 reader
    (释放交给 CPython refcount,见 Source.rebuild docstring)。
    geolite_city 除外:其 maxminddb 探测 close 是合法的下载期校验。"""
    import ipdb._source_base as sb
    import ipdb._sources._base as b
    src_dir = Path(b.__file__).parent
    offenders = []
    for py in [Path(sb.__file__), Path(b.__file__)] + list(src_dir.glob("*.py")):
        if py.name == "geolite_city.py":
            continue
        text = py.read_text(encoding="utf-8")
        for marker in ("old_reader", "old_reader6"):
            if marker in text:
                offenders.append(f"{py.name}: {marker}")
        if py in (Path(sb.__file__), Path(b.__file__)) and "_reader.close()" in text:
            offenders.append(f"{py.name}: _reader.close()")
    assert not offenders, f"rebuild 路径不得显式 close reader: {offenders}"
