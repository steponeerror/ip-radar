"""roster 命令与注册完整性(dataplane 前例护栏,2026-09-05)。

两类失败各防一个:
- roster 覆盖不全 / 格式漂移 → 加源流程的域名对照失去意义;
- _sources/ 里存在模块但静默未注册(instantiate 失败只 warning)→
  源存在于目录、缺位于名册,加源流程对它失明。
"""
import importlib
from pathlib import Path

from ipdb._registry import _sources, roster


def test_roster_covers_every_registered_source() -> None:
    lines = roster()
    names = [ln.split(" | ")[0] for ln in lines]
    assert names == [s.name for s in _sources]
    assert len(set(names)) == len(names)


def test_roster_line_shape() -> None:
    for ln in roster():
        cols = ln.split(" | ")
        assert len(cols) in (4, 5), ln
        assert cols[1] in {"geo_asn", "threat", "asset", "other"}, ln
        assert cols[2] != "", ln  # download_host 可为 "-" 但不可空串


def test_roster_lists_multi_file_sublists() -> None:
    row = next(ln for ln in roster() if ln.startswith("dataplane"))
    assert "telnetlogin" in row and "dnsrd" in row  # 正是前例漏掉的信号


def test_every_source_module_class_is_registered() -> None:
    """目录里每个定义了 name+fields 的类都必须出现在注册名单里。

    镜像 _discover_sources 的判定(isinstance type + name/fields attr +
    __module__ 同模块)。实例化失败仅 warning 的静默丢弃在此被拦截。
    """
    registered = {s.name for s in _sources}
    # _sources 是命名空间包(无 __init__.py),从 _registry 同目录定位
    import ipdb._registry as _reg
    pkg_dir = Path(_reg.__file__).parent / "_sources"
    missing = []
    for mod_path in sorted(pkg_dir.glob("*.py")):
        stem = mod_path.stem
        if stem.startswith("_"):
            continue
        mod = importlib.import_module(f"ipdb._sources.{stem}")
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if (isinstance(obj, type)
                    and hasattr(obj, "name") and hasattr(obj, "fields")
                    and obj.__module__ == mod.__name__):
                if getattr(obj, "name", None) not in registered:
                    missing.append(f"{stem}.{attr}")
    assert not missing, f"模块存在但未注册(实例化失败?): {missing}"
