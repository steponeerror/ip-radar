# backend/tests/core/test_glossary_anchors.py 的孪生守卫:词条锚(`锚:…`)必须解析到真实代码。
"""GLOSSARY anchor drift guard (one-way): every 锚: anchor a glossary entry
makes must resolve in the codebase. GLOSSARY 定义即教义——词条锚点指向死
代码时,这把静默谎言变成红测试(替代纯手工的「随 codegraph init 核对」)。

Extraction domain (锚: 尾段,词条正文里的提及不检):
  a) .py file tokens      -> file must exist (candidates: 原样 / backend/ipdb/
                             / backend/ipdb/_sources/ / backend/)
  b) file(symbol) 括注     -> symbol must appear in that file's source
                             (只认纯标识符;带空格/CJK 的注记如「to_dict 弃权
                             特判」不检——那是注释不是代码符号)
  c) file:line 行号        -> 行号本身不查(上方任何插行即漂移,易碎);
                             降级为 file 存在性检查。符号级(b)才是稳定子集
  d) .md 详设路径          -> 不检(本机私有 docs,GLOSSARY 已自带「本机私有」注)
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]          # 仓库根 (GLOSSARY.md 在根)
GLOSSARY = REPO / "GLOSSARY.md"
ANCHOR_MARK = "锚:"

_ANCHOR_TOKEN = re.compile(r"([A-Za-z0-9_./]+\.py)(?::(\d+))?(?:\(([^)]*)\))?")
_IS_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 提取器健全性下限: 低于此数说明 GLOSSARY 格式漂移、守卫在空转
MIN_FILE_ANCHORS = 20
MIN_SYMBOL_ANCHORS = 15


def _anchor_zones():
    """每个词条的锚区 = 行内最后一个 `锚:` 之后的尾段。"""
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        if ANCHOR_MARK in line:
            yield line.rsplit(ANCHOR_MARK, 1)[1]


def _resolve(tok: str):
    """裸文件名按 _sources/_lmdb 实际布局给候选; 根相对路径原样解析。"""
    cands = [tok] if tok.startswith(("backend/", "frontend/", "scripts/", "integrations/")) \
        else [f"backend/ipdb/{tok}", f"backend/ipdb/_sources/{tok}", f"backend/{tok}", tok]
    for c in cands:
        p = REPO / c
        if p.exists():
            return p
    return None


def _file_anchors():
    for zone in _anchor_zones():
        for m in _ANCHOR_TOKEN.finditer(zone):
            yield m.group(1)


def _symbol_anchors():
    """(文件名, 符号) 对: 括注按 /、,; 切分, 只保留纯标识符成员。"""
    for zone in _anchor_zones():
        for m in _ANCHOR_TOKEN.finditer(zone):
            tok, _line, paren = m.groups()
            if not paren:
                continue
            for part in re.split(r"[/、,;]", paren):
                part = part.strip()
                if _IS_IDENT.match(part):
                    yield tok, part


def test_guard_infrastructure_finds_anchors():
    """守卫自身健全性: 提取器必须抓到足量锚点(否则守卫空转)。"""
    files = list(_file_anchors())
    syms = list(_symbol_anchors())
    assert len(set(files)) >= MIN_FILE_ANCHORS, \
        f"only {len(set(files))} file anchors — extractor or GLOSSARY format drifted"
    assert len(set(syms)) >= MIN_SYMBOL_ANCHORS, \
        f"only {len(set(syms))} symbol anchors — extractor or GLOSSARY format drifted"


def test_glossary_anchor_files_exist():
    problems = [f"file not found: {tok}" for tok in sorted(set(_file_anchors()))
                if _resolve(tok) is None]
    assert not problems, "\n".join(problems)


def test_glossary_anchor_symbols_resolve():
    problems = []
    for tok, sym in sorted(set(_symbol_anchors())):
        path = _resolve(tok)
        if path is None:                              # file 级测试已覆盖, 不重复报
            continue
        if sym not in path.read_text(encoding="utf-8", errors="replace"):
            problems.append(f"symbol not in {tok}: {sym}")
    assert not problems, "\n".join(problems)
