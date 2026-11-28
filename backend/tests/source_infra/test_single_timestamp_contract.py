"""单时间源声明契约(#523 裁决 Q27,AST 检查)。

`SourceBase.single_timestamp_means`(取值 first_seen / last_seen)声明
上游唯一时间的含义;声明与写法必须一致:

① 声明 `last_seen` 的源,构造 Evidence 时不得出现 `first_seen=` 关键字
   (时钟按 last_seen 优先,双填 first_seen 会误导读码人,且回放镜像
   两侧键位漂移);
② 其余源不得「只写 last_seen 不写 first_seen」——单时间源必须先在
   类上声明自己是「最近见到」,再改写法(新单时间源漏声明即红)。
   返工评审 5 扩面:类体内(跳过各级 docstring)出现的字符串键用法
   ——字典字面量键、下标 `d["last_seen"]`、`.get("last_seen")` 参数
   ——同样计入:含 last_seen 而全文无 first_seen 也红(盖住
   parse_row 返回字典的取数路径:ziyadnz/sw_threats/f3csystems/
   threatcluster/honyport)。

仍看不见的盲区(docstring 留痕,评审 5 要求点名):`Evidence(**d)`
这种字典展开构造——字典 d 在模块级函数或别的模块拼装时,本测试
不会红;动态拼键(字符串拼接/变量)也不可见;模块级裸 `Evidence(`
构造(现存仅 ip2proxy.py,不带时间)不在类扫描范围。这些靠代码
评审与回放门兜底。
AST 静态检查而非运行时:证据构造是各源 harvest/rebuild 内部的字面量
关键字,静态面就能钉住;失败信息点名文件与类。
"""
import ast
from pathlib import Path

import pytest

SOURCES_DIR = Path(__file__).resolve().parents[2] / "ipdb" / "_sources"


def _source_files():
    # 下划线前缀 = 基础设施模块(_base/_lmdb/_download/...),不是源
    return sorted(p for p in SOURCES_DIR.glob("*.py") if not p.name.startswith("_"))


def _body_without_docstrings(node):
    """跳过模块/类/函数首位的裸字符串(docstring),防注释性提及误触发。"""
    body = node.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return body


def _ts_string_key_uses(cls_node: ast.ClassDef) -> set[str]:
    """类体内(跳过 docstring)对 'first_seen'/'last_seen' 的字符串键
    用法:字典字面量键、下标、函数调用参数(覆盖 .get("last_seen"))。"""
    uses: set[str] = set()

    def visit(stmts):
        for stmt in stmts:
            for child in ast.walk(stmt):
                if (isinstance(child, ast.Constant)
                        and child.value in ("first_seen", "last_seen")):
                    uses.add(child.value)

    for stmt in _body_without_docstrings(cls_node):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visit(_body_without_docstrings(stmt))
        else:
            visit([stmt])
    return uses


def _class_single_timestamp_means(cls_node: ast.ClassDef):
    """类(含继承链本文件内不可见,只看本类字面量)声明的取值;未声明 → None。"""
    for stmt in cls_node.body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if (isinstance(t, ast.Name) and t.id == "single_timestamp_means"
                        and isinstance(stmt.value, ast.Constant)):
                    return stmt.value.value
        elif (isinstance(stmt, ast.AnnAssign)
              and isinstance(stmt.target, ast.Name)
              and stmt.target.id == "single_timestamp_means"
              and stmt.value is not None
              and isinstance(stmt.value, ast.Constant)):
            return stmt.value.value
    return None


def _evidence_calls(cls_node: ast.ClassDef):
    """类体内(含方法/嵌套函数)全部 Evidence(...) 调用的关键字名列表。"""
    out = []
    for node in ast.walk(cls_node):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Evidence"):
            out.append([kw.arg for kw in node.keywords if kw.arg])
    return out


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_single_timestamp_declaration_matches_writes(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for cls_node in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        means = _class_single_timestamp_means(cls_node)
        if means not in ("first_seen", "last_seen", None):
            pytest.fail(
                f"{path.name}:{cls_node.name}: single_timestamp_means={means!r} "
                f"非法(只许 'first_seen' / 'last_seen')")
        key_uses = _ts_string_key_uses(cls_node)
        for kwargs in _evidence_calls(cls_node):
            has_fs, has_ls = "first_seen" in kwargs, "last_seen" in kwargs
            if means == "last_seen" and has_fs:
                pytest.fail(
                    f"{path.name}:{cls_node.name}: 声明 single_timestamp_means="
                    f"'last_seen' 但构造 Evidence 出现 first_seen= 关键字 "
                    f"(#523:单时间「最近见到」源只写 last_seen)")
            if means != "last_seen" and has_ls and not has_fs:
                pytest.fail(
                    f"{path.name}:{cls_node.name}: 构造 Evidence 只写 last_seen "
                    f"不写 first_seen,但类未声明 single_timestamp_means="
                    f"'last_seen'(#523:单时间源必须先声明时间含义)")
        # 返工评审 5:字典路径盖盲(规则 ② 扩面,见模块 docstring)
        if means != "last_seen" and "last_seen" in key_uses \
                and "first_seen" not in key_uses:
            pytest.fail(
                f"{path.name}:{cls_node.name}: 类方法里出现 "
                f"last_seen 字符串键(字典字面量/下标/.get)但全文无 "
                f"first_seen,且未声明 single_timestamp_means='last_seen' "
                f"(#523:只写 last_seen 的源必须先声明时间含义)")
