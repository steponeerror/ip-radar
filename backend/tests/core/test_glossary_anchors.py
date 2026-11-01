# test_skill_drift.py 的孪生守卫:词条出处(`出处:…`)必须解析到真实代码。
"""GLOSSARY anchor drift guard (one-way): every 出处: anchor a glossary entry
makes must resolve in the codebase. GLOSSARY 定义即教义——词条出处指向死
代码时,这把静默谎言变成红测试(替代纯手工的「随 codegraph init 核对」)。

Extraction domain (出处: 尾段,词条正文里的提及不检):
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
ANCHOR_MARK = "出处:"

_ANCHOR_TOKEN = re.compile(r"([A-Za-z0-9_./]+\.py)(?::(\d+))?(?:\(([^)]*)\))?")
_IS_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 提取器健全性下限: 低于此数说明 GLOSSARY 格式漂移、守卫在空转
MIN_FILE_ANCHORS = 20
MIN_SYMBOL_ANCHORS = 15


def _anchor_zones():
    """每个词条的出处区 = 行内最后一个 `出处:` 之后的尾段。"""
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


def test_glossary_entries_carry_source():
    """每条词条必须带出处(2026-10-31 命名纪律的格式面;ADR 0016)。
    无出处的词条 = 脱离代码的悬空教义(判例:ub-mode 批「结构重复」裸奔 25 天)。
    机检只管这一格式事实;词面是否人话不可机检,归人裁与 review。
    """
    naked = [l[4:l.index('**:', 4)] for l in GLOSSARY.read_text(encoding="utf-8").splitlines()
             if l.startswith('- **') and '**:' in l and '出处' not in l]
    assert not naked, f"entries without 出处: {naked}"


# --- 旧词拒用闸(2026-10-31 用户令;业界对照=Vale reject.txt 模式,证据链
# notes/industry-term-governance-2026-10-31.md)---
# 拒用词表不单独维护——从 GLOSSARY「## 改名对照」旧词列程序化提取(单一真相源):
# 新增一次改名,人裁记一行对照,本闸自动长牙,不存在第二份清单会漏更新。
# 表失效的三层兜底:①提取下限断言(表被删/格式漂移→红,同 MIN_FILE_ANCHORS
# 防线);②GLOSSARY 表头命名规则第④步(改名必须记行;人裁+裁决件即对照行素材);
# ③「有人改名但没记行」机检不可知(测不出没写进表的东西),归审查环,不装假闸。
# 提取诚实边界(与出处锚「只认纯标识符」同款):旧词格按 / + 、切开、剥尾注括号后,
# 仅纯中文≥2字才入拒用表;剥后若为新词子串(如 熔断(尾条)→跨轮熔断)则它是
# 存活词根,不拒——只有整词被换掉的旧词才拒。

_RENAME_SECTION = "## 改名对照"
_RETIRED_SECTION = "## 已退役"
MIN_BANNED_TERMS = 50
_PURE_CJK = re.compile(r"^[\u4e00-\u9fff]{2,}$")
# 合并行旧成员中仍存活的组件名:三层职责线(合一,P5)拆出的三层是活概念,
# 不能因当过独立词条而被拒用
_ALIVE_AFTER_MERGE = {"提示词层", "装配层", "宿主层"}


def _rename_table_rows():
    """改名对照表的 (旧词, 新词) 单元格对。"""
    lines = GLOSSARY.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(_RENAME_SECTION))
    end = next((i for i, l in enumerate(lines[start + 1:], start + 1)
                if l.startswith("## ")), len(lines))
    for l in lines[start + 1:end]:
        if not l.startswith("|"):
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] == "旧词" or set(cells[0]) <= {"-", ":", " "}:
            continue
        yield cells[0], cells[1]


def _banned_terms():
    for old, new in _rename_table_rows():
        for part in re.split(r"[/+、]", old):
            part = re.sub(r"[（(].*$", "", part).strip()   # 剥尾注括号
            if _PURE_CJK.match(part) and part not in new and part not in _ALIVE_AFTER_MERGE:
                yield part


def _living_text(rel: str) -> str:
    """读活文档;GLOSSARY 排除改名对照/已退役两节(旧词只许住那两处)。"""
    path = REPO / rel
    if rel != "GLOSSARY.md":
        return path.read_text(encoding="utf-8")
    living, skip = [], False
    for l in path.read_text(encoding="utf-8").splitlines():
        if l.startswith("## "):
            skip = l.startswith((_RENAME_SECTION, _RETIRED_SECTION))
        if not skip:
            living.append(l)
    return "\n".join(living)


# 活文档扫描面 = 中文文档面。代码标识符/CHANGELOG/notes/ADR 不在内;ops/agent md 面 #259 已改名但未入扫描面（收面前置=先清 ops/agent/fixtures/pipeline/README.md:50 等存旧词文件）
LIVING_DOCS = [
    "GLOSSARY.md", "CONTEXT.md", "NEEDS.md",
    "README.md", "README.zh-CN.md", "MANUAL.md", "MANUAL.zh-CN.md",
] + sorted(str(p.relative_to(REPO)) for p in (REPO / ".pi/skills").rglob("*.md"))


def test_rename_reject_floor():
    """拒用词源健全性:改名对照表必须提取出足量旧词(否则拒用闸空转)。"""
    n = len(set(_banned_terms()))
    assert n >= MIN_BANNED_TERMS, \
        f"only {n} banned terms — 改名对照表 deleted or format drifted"


def test_no_retired_terms_in_living_docs():
    """旧词拒用闸:活文档不得写回改名对照表的旧词(含子串命中)。"""
    banned = sorted(set(_banned_terms()))
    problems = []
    for rel in LIVING_DOCS:
        text = _living_text(rel)
        for term in banned:
            if term in text:
                problems.append(f"{rel}: retired term 「{term}」")
    assert not problems, "\n".join(problems)
