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


def _declares_infra_noise_filter(cls: ast.ClassDef) -> bool:
    """类体里有带值的 `infra_noise_filter = ...`(纯赋值,或带值的注解赋值)。
    只写注解不带值(`infra_noise_filter: bool`)不算:运行时没有这个属性,
    源实际继承基类缺省,正是契约不许的情形。"""
    for st in cls.body:
        if isinstance(st, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "infra_noise_filter"
                for t in st.targets):
            return True
        if (isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)
                and st.target.id == "infra_noise_filter" and st.value is not None):
            return True
    return False


def _registered_classes():
    """(文件名, 类名, 行号, 是否声明 infra_noise_filter)——登记判据与
    _discover_sources 对齐:模块内定义、类体自带 name 与 fields。"""
    found = []
    for p in sorted(SOURCES_DIR.glob("*.py")):
        if p.stem.startswith("_"):        # 私有基类/工具模块不登记
            continue
        tree = ast.parse(p.read_bytes())   # 让解析器按 UTF-8 读(源文件带中文注释)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = _class_attrs(node)
            if "name" in attrs and "fields" in attrs:
                found.append((p.name, node.name, node.lineno,
                              _declares_infra_noise_filter(node)))
    return found


def test_every_registered_source_declares_infra_noise_filter():
    missing = [f"{fname}:{lineno}:{cls}" for fname, cls, lineno, declared
               in _registered_classes() if not declared]
    assert not missing, (
        "infra_noise_filter 契约(#531)违反:以下源类类体缺带值的显式声明"
        "(不许继承基类缺省)——想开写 infra_noise_filter = True;要关写 "
        "infra_noise_filter = False 并注明理由(只写注解不算声明):"
        + ", ".join(missing))


def test_ast_registration_matches_runtime_discovery():
    """登记判据漂移哨兵:AST 面找到的登记类集合与运行时发现集合一致
    (#531 时点 71)。判据变了(name/fields 之外的新登记途径)这里红。
    不关日志:某个源 __init__ 抛错被跳过时,原因只在那条 warning 里。"""
    import ipdb._registry as reg
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        runtime = {type(s).__name__ for s in reg._discover_sources(Path(td))}
    ast_found = {cls for _, cls, _, _ in _registered_classes()}
    assert ast_found == runtime, (
        f"AST 登记判据与 _discover_sources 不一致:仅 AST 有 "
        f"{sorted(ast_found - runtime)},仅运行时有 {sorted(runtime - ast_found)}")
