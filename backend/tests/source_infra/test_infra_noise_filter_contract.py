"""元数据契约(#531 裁决 2026-11-28):每个登记的源类必须在类体里显式
声明 ``infra_noise_filter``,不许继承缺省。

背景:基类缺省已翻为 True(新接入的源默认打开载入期基础设施过滤);
存量源行为不变靠 61 个显式 False + 10 个事故源显式 True 钉住。谁新加源
忘了声明,这里红(启动面 _registry._discover_sources 不查这条——缺省
继承不炸,只有契约测试能把「忘了写」变成可见失败)。

AST 面检查(不 import,数类体里自己的赋值):登记判据与
_registry._discover_sources 同款(类体自带 name+fields 赋值)。
"""
import ast
from pathlib import Path

SOURCES_DIR = Path(__file__).resolve().parents[2] / "ipdb" / "_sources"


def _class_attrs(cls: ast.ClassDef) -> set[str]:
    """类体里自己声明的属性名(纯赋值 + 注解赋值)。"""
    names: set[str] = set()
    for st in cls.body:
        if isinstance(st, ast.Assign):
            names |= {t.id for t in st.targets if isinstance(t, ast.Name)}
        elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
            names.add(st.target.id)
    return names


def _registered_classes():
    """(文件名, 类名, 是否声明 infra_noise_filter)——登记判据与
    _discover_sources 对齐:模块内定义、类体自带 name 与 fields。"""
    found = []
    for p in sorted(SOURCES_DIR.glob("*.py")):
        if p.stem.startswith("_"):        # 私有基类/工具模块不登记
            continue
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = _class_attrs(node)
            if "name" in attrs and "fields" in attrs:
                found.append((p.name, node.name,
                              "infra_noise_filter" in attrs))
    return found


def test_every_registered_source_declares_infra_noise_filter():
    missing = [f"{fname}:{cls}" for fname, cls, declared
               in _registered_classes() if not declared]
    assert not missing, (
        "infra_noise_filter 契约(#531)违反:以下源类类体缺显式声明"
        "(不许继承基类缺省)——新源缺省开,要关必须显式写 "
        "infra_noise_filter = False 并注明理由:"
        + ", ".join(missing))


def test_registered_class_count_unchanged():
    """登记判据漂移哨兵:AST 面找到的登记类数与运行时发现数一致
    (#531 时点 71)。判据变了(name/fields 之外的新登记途径)这里红。"""
    import ipdb._registry as reg
    import logging
    logging.disable(logging.CRITICAL)
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            runtime = {type(s).__name__ for s in
                       reg._discover_sources(Path(td))}
    finally:
        logging.disable(logging.NOTSET)
    ast_found = {cls for _, cls, _ in _registered_classes()}
    assert ast_found == runtime, (
        f"AST 登记判据与 _discover_sources 不一致:仅 AST 有 "
        f"{sorted(ast_found - runtime)},仅运行时有 {sorted(runtime - ast_found)}")
