#!/usr/bin/env python3
"""check_source_counts.py — CI 源数字闸(ADR 0018 的机器比对腿,issue retro-batch/t1)。

裁决要点(ADR 0018,docs 仓):登记表是唯一事实源,文档数字由 CI 机器比对。
- 事实源 = backend/ipdb/_sources/ 目录自动发现的源类(镜像 _registry._discover_sources
  的判定:非 _ 前缀模块内、自带 name+fields 类属性赋值的类);
- 现有测试里的钉死数(roster 断言、ops ln 计数、selftest manifest 计数)不归本闸
  管也不改动 —— 它们是防误删源的绊线,本闸只管「文档宣称数 vs 派生实数」;
- GitHub About 是仓外对象,不做机器闸。

口径(与文档实际使用数对齐,口径矛盾的展开与全批决策记录见 docs 仓
reports/retro-p0-batch-2026-11-03.md):
- 公开源总数 = 登记实例数 − eval_excluded=True 的实例数。eval_excluded 是
  honyport 一类「本地自建观测、非公网拉取源」今天唯一的机器可读标记
  (backend/ipdb/_sources/honyport.py:116,行号随二期改动漂移过、以文件内 eval_excluded 实文为准);该标记语义是「评估面恒禁用」,
  与「非公开源」当前恰好 1:1——若未来出现「评估禁用但仍算公开源」的源,
  本闸会在此处先红,提示拆口径。
- 带钥源数/密钥变量数 = backend/ipdb/_tokens.py 的 MANAGED 冻结映射
  (env var → 消费源名)展平;免钥公开源数 = 公开总数 − 带钥(带钥源全公开)。

实现纪律:stdlib-only(ast/re/os,秒级,CI backend job 零新依赖);静态解析不导入
ipdb(导入即实例化全部源并加载 .env,非幂等且慢)。已知镜像边界(两向漂移
均朝红、fail-loud,不违宁少算;评审 P2 记录):静态只认类体自有赋值,registry
用 hasattr 含继承——继承其体源类不重写 name/fields 的新增会少算误红;registry
实例化失败即跳过而静态照计——会多算误红。两情形出现时先红,提示拆机制。模式匹配是「宁少算」面:
文档改写后某句不再命中正则 = 该句退出比对(不红);命中而数字错 = 红。
通扫层(#457,2026-11-26):逐句腿只认手点名文档,换种说法就漏(「29 fused
public feeds」判例)——故在逐句腿之上加一层全面扫:--root 下按后缀(含无后缀
shebang 脚本)收受管文本文件,凡「N sources/feeds / N 个源」字面量,数字必须
等于登记表派生集合 {public_total, registered 总数, keyed, keyless_public,
key_envs 个数} 之一;前缀 ~ / 约 / approximately 的近似数不算。范围不依赖
git(夹具树不是 git 仓),按目录名/路径排除历史记录、夹具与第三方安装面;
例外按「文件+原因」(整档跳过)或「说法+原因」(该说法匹配段从行里剔掉再扫,
同行其余字面量照红)登记,每条必须带原因(卫生闸钉死,防「待查」混入)。
跑法(仓根):python3 scripts/check_source_counts.py   # 退出码 0=绿,1=红并列 file:line
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO / "backend" / "ipdb" / "_sources"
TOKENS_PATH = REPO / "backend" / "ipdb" / "_tokens.py"
DOC_FILES = (
    "README.md",
    "README.zh-CN.md",
    "MANUAL.md",
    "MANUAL.zh-CN.md",
    "CONTEXT.md",
    "GLOSSARY.md",   # 评审 P2-2:源底座条的活计数(登记总数口径)同属漂移面,入闸
    "assets/social-preview.svg",   # #451:图字里的公开源总数(旧 29 漂移判例)
    "integrations/wazuh/README.md",  # #451:集成文档口径同漂移面
    "integrations/wazuh/custom-ipradar",  # #451:集成脚本头注(评审发现:「29 fused public feeds」漏网)
    "scripts/fail2ban/ipradar.conf",  # #451:同上(「fuses 29 public feeds」漏网)
)

# 英文/中文数词(文档里 keyed/keys 有拼写数词形态,如 "The seven keyed sources")
_WORD_NUM_EN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_WORD_NUM_ZH = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _assigned_attrs(cls_node: ast.ClassDef) -> dict[str, object]:
    """类体内直接赋值的字面量属性(镜像 registry 的 hasattr 判定:类体自有
    name+fields 赋值;经继承拿到的属性由基类模块(_ 前缀,不入册)提供)。"""
    out: dict[str, object] = {}
    for stmt in cls_node.body:
        targets: list[ast.expr] = []
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
        for tgt in targets:
            if isinstance(tgt, ast.Name):
                try:
                    out[tgt.id] = ast.literal_eval(stmt.value)
                except ValueError:
                    out[tgt.id] = None   # 非字面量(如 url property 引用)按未知处理
    return out


def derive_counts(sources_dir: Path = SOURCES_DIR,
                  tokens_path: Path = TOKENS_PATH) -> dict:
    """从登记表静态派生源计数。返回 registered/eval_excluded/keyed/key_envs/
    public_total/keyless_public/keyed_names(排序后)。"""
    registered: dict[str, bool] = {}   # name -> eval_excluded
    for mod_path in sorted(sources_dir.glob("*.py")):
        if mod_path.stem.startswith("_"):
            continue
        tree = ast.parse(mod_path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = _assigned_attrs(node)
            if "name" in attrs and "fields" in attrs:
                name = attrs["name"]
                if not isinstance(name, str) or not name:
                    raise ValueError(
                        f"{mod_path.name}:{node.name}: name 非字符串字面量")
                if name in registered:
                    raise ValueError(f"源名重复注册: {name}")
                registered[name] = bool(attrs.get("eval_excluded", False))
    if not registered:
        raise ValueError(f"{sources_dir} 未发现任何源类(自动发现面为空?)")

    # MANAGED 冻结映射(Assign 或 AnnAssign 两种形态都收)
    managed: dict[str, list[str]] = {}
    tok_tree = ast.parse(tokens_path.read_text(encoding="utf-8"))
    for node in tok_tree.body:
        tgt = None
        if isinstance(node, ast.Assign):
            tgt = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            tgt = node.target
        if isinstance(tgt, ast.Name) and tgt.id == "MANAGED":
            managed = ast.literal_eval(node.value)
    if not managed:
        raise ValueError(f"{tokens_path}: 未找到 MANAGED 字面量映射")

    keyed_names = sorted({s for consumers in managed.values() for s in consumers})
    ghosts = [s for s in keyed_names if s not in registered]
    if ghosts:
        raise ValueError(f"MANAGED 指向未注册源(映射过期?): {ghosts}")

    eval_excluded = sorted(n for n, v in registered.items() if v)
    public_names = set(registered) - set(eval_excluded)
    keyed_public = [n for n in keyed_names if n in public_names]
    return {
        "registered": sorted(registered),
        "eval_excluded": eval_excluded,
        "public_total": len(public_names),
        "keyed": len(keyed_names),
        "key_envs": sorted(managed),
        "keyed_names": keyed_names,
        "keyless_public": len(public_names) - len(keyed_public),
        "managed": {v: list(s) for v, s in managed.items()},
    }


def _num(tok: str) -> int | None:
    """'60'/'seven'/'七' → int;认不得返回 None(调用方报「无法解析」。"""
    tok = tok.strip()
    if tok.isdigit():
        return int(tok)
    if tok in _WORD_NUM_EN:
        return _WORD_NUM_EN[tok]
    if tok in _WORD_NUM_ZH:
        return _WORD_NUM_ZH[tok]
    return None


def _expected_var(name: str, managed: dict[str, list[str]]) -> str | None:
    for var, consumers in managed.items():
        if name in consumers:
            return var
    return None


def _keyed_table_errors(lines: list[str], anchor_re: re.Pattern,
                        counts: dict, label: str) -> list[str]:
    """锚句之后的第一个表格 = 带钥源表;核对源名集合与逐源 env var 映射。
    合并行(threatfox / urlhaus)按 '/' 拆开对集合。label=报错前缀(仓根相对路径)。"""
    errors: list[str] = []
    anchor = next((i for i, ln in enumerate(lines) if anchor_re.search(ln)), None)
    if anchor is None:
        return errors   # 锚句改写 = 本子闸退出比对(宁少算)
    table: list[tuple[int, list[str]]] = []
    for i in range(anchor + 1, min(anchor + 40, len(lines))):
        ln = lines[i]
        if ln.startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(cells) >= 2 and not set(cells[0]) <= {"-", ":"} and cells[0] not in ("Source", "源"):
                table.append((i + 1, cells))
        elif table:
            break   # 表格已结束
        elif ln.strip() and not ln.startswith("|"):
            # 锚句与表格间的代码块/正文跳过,继续往后找表
            continue
    got_names: set[str] = set()
    for lineno, cells in table:
        for nm in cells[0].split("/"):
            nm = nm.strip().strip("`*")
            if not nm:
                continue
            got_names.add(nm)
            m = re.match(r"`([A-Z][A-Z0-9_]+)`", cells[1])
            want = _expected_var(nm, counts["managed"])
            if m and want and m.group(1) != want:
                errors.append(
                    f"{label}:{lineno}: 带钥源 {nm} 的变量应为 `{want}`,"
                    f"表格写的是 `{m.group(1)}`")
            elif not m:
                errors.append(f"{label}:{lineno}: 带钥源 {nm} 行缺 env var 反引号列")
    if got_names != set(counts["keyed_names"]):
        miss = set(counts["keyed_names"]) - got_names
        extra = got_names - set(counts["keyed_names"])
        errors.append(
            f"{label}: 带钥源表名集不符(缺 {sorted(miss) or '无'} /"
            f" 多 {sorted(extra) or '无'};期望 {counts['keyed']}:"
            f" {counts['keyed_names']})")
    return errors


# 比对面:每条 = (编译正则, 期望值元组名元组, 错误描述模板)
# 元组名引用 derive_counts() 键;捕获组与元组名一一对应。
_CHECKS: tuple[tuple[str, re.Pattern, tuple[str, ...], str], ...] = (
    # README.md
    ("README.md", re.compile(r"Pull (\d+) public sources"), ("public_total",),
     "公开源总数"),
    ("README.md", re.compile(r"all but the (\d+) keyed sources"), ("keyed",),
     "带钥源数"),
    ("README.md", re.compile(r"All but (\d+) feeds need zero API keys"), ("keyed",),
     "带钥源数"),
    ("README.md", re.compile(r"the (\d+) keyed sources \(they share (\d+) keys"),
     ("keyed", "key_envs"), "带钥源数/密钥变量数"),
    ("README.md", re.compile(r"keyless auto \+ (\d+) keyed"), ("keyed",),
     "带钥源数(mermaid,评审 P2-1 补 zh 孪生腿时同批)"),
    # README.zh-CN.md
    ("README.zh-CN.md", re.compile(r"把 (\d+) 个公开情报源"), ("public_total",),
     "公开源总数"),
    ("README.zh-CN.md", re.compile(r"除 (\d+) 个密钥源"), ("keyed",),
     "带钥源数"),
    ("README.zh-CN.md", re.compile(r"想开 (\d+) 个密钥源（([^，）]+)，共 (\d+) 个密钥"),
     ("keyed", None, "key_envs"), "带钥源数/密钥变量数"),
    ("README.zh-CN.md", re.compile(r"剩下 (\d+) 个 🔑 源"), ("keyed",),
     "带钥源数(尾句,评审 P2-1)"),
    ("README.zh-CN.md", re.compile(r"([0-9一二三四五六七八九十]+)\s*个变量"),
     ("key_envs",), "密钥变量数(数词,评审 P2-1)"),
    ("README.zh-CN.md", re.compile(r"keyless auto \+ (\d+) keyed"), ("keyed",),
     "带钥源数(mermaid,评审 P2-1)"),
    # MANUAL.md
    ("MANUAL.md", re.compile(r"\((\d+) of the (\d+) sources\)"),
     ("keyless_public", "public_total"), "免钥公开源数/公开源总数"),
    ("MANUAL.md", re.compile(r"The ([a-z]+) keyed sources \(.*?([a-z]+) keys"),
     ("keyed", "key_envs"), "带钥源数/密钥变量数(数词)"),
    ("MANUAL.md", re.compile(r"the ([a-z]+) source keys"), ("key_envs",),
     "密钥变量数(数词,评审 P2-1)"),
    ("MANUAL.md", re.compile(r"tab: (\d+) sources"), ("registered",),
     "注册源总数(截图 alt;2026-11-03 修订:Sources 页显示的是注册口径——"
     "公开 + eval_excluded 蜜罐,与 §首启 53-of-60 公开口径并存,ADR 0018 修订)"),
    ("MANUAL.md", re.compile(r"The (\d+) shipped sources"), ("public_total",),
     "公开源总数"),
    ("MANUAL.md", re.compile(r"The ([a-z]+) keyed feeds"), ("keyed",),
     "带钥源数(数词)"),
    # MANUAL.zh-CN.md
    ("MANUAL.zh-CN.md", re.compile(r"（(\d+) 个源中的 (\d+) 个）"),
     ("public_total", "keyless_public"), "公开源总数/免钥公开源数"),
    ("MANUAL.zh-CN.md", re.compile(r"([0-9一二三四五六七八九十]+)\s*个?\s*key\s*源"),
     ("keyed",), "带钥源数(数词)"),
    ("MANUAL.zh-CN.md", re.compile(r"共 (\d+) 个 key[:：]"), ("key_envs",),
     "密钥变量数"),
    ("MANUAL.zh-CN.md", re.compile(r"([0-9一二三四五六七八九十]+)\s*个源密钥"),
     ("key_envs",), "密钥变量数(数词,评审 P2-1)"),
    ("MANUAL.zh-CN.md", re.compile(r"tab[:：](\d+) 源"), ("registered",),
     "注册源总数(截图 alt;2026-11-03 口径同英文版修订)"),
    ("MANUAL.zh-CN.md", re.compile(r"自带的 (\d+) 个源"), ("public_total",),
     "公开源总数"),
    # CONTEXT.md(词汇表「token 源」条的活计数)
    ("CONTEXT.md", re.compile(r"共 (\d+) key (\d+) 行"),
     ("key_envs", "keyed"), "密钥变量数/带钥源数"),
    # GLOSSARY.md(源底座条的活计数,登记总数口径=含私有源,评审 P2-2)
    ("GLOSSARY.md", re.compile(r"全部 (\d+) 个源"), ("registered",),
     "登记源总数"),
    # 子目录文档(fname=仓根相对路径;check_doc 按 rel 匹配,评审 P2 激活钉同读真档)
    ("assets/social-preview.svg", re.compile(r"(\d+) sources, one verdict"),
     ("public_total",), "公开源总数(social preview 图字,#451)"),
    ("integrations/wazuh/README.md", re.compile(r"IPs: (\d+) fused feeds"),
     ("public_total",), "公开源总数(wazuh 集成,#451)"),
    # 集成件头注里的旧写法「N public feeds」/「N fused public feeds」(2026-11-25
    # 评审发现:首版正则「N (public )?(sources|feeds)」匹配不上「N fused public feeds」,
    # 也没扫 scripts/,两处「29」漏网——腿的句式要照真文档写,不照想象写)
    ("scripts/fail2ban/ipradar.conf", re.compile(r"fuses (\d+) public feeds"),
     ("public_total",), "公开源总数(fail2ban 集成头注,#451)"),
    ("integrations/wazuh/custom-ipradar", re.compile(r"(\d+) fused public feeds"),
     ("public_total",), "公开源总数(wazuh 集成脚本头注,#451)"),
)


def check_doc(path: Path, counts: dict, rel: str | None = None) -> list[str]:
    """单文档比对;返回错误串列表(file:line 前缀)。rel=仓根相对路径,供
    子目录文档的按路径比对腿(fname 存「/」时只按 rel 匹配,不按文件名——
    免得根级同名文档(README.md)误吃子目录腿或缺腿;缺省按文件名,兼容根级
    旧腿与只传两参的旧调用面)。"""
    errors: list[str] = []
    rel = rel or path.name
    lines = path.read_text(encoding="utf-8").splitlines()
    for fname, pattern, expects, what in _CHECKS:
        if fname != rel:
            continue
        for i, ln in enumerate(lines, 1):
            m = pattern.search(ln)
            if not m:
                continue
            for g in range(1, len(m.groups()) + 1):
                key = expects[g - 1]
                if key is None:
                    continue   # 名单组(keyed name list),后面单独核
                actual = (len(counts["key_envs"])
                          if key == "key_envs"
                          else len(counts["registered"])
                          if key == "registered"
                          else counts[key])
                got = _num(m.group(g))
                if got is None:
                    errors.append(f"{rel}:{i}: {what}: 数词「{m.group(g)}」无法解析")
                elif got != actual:
                    errors.append(
                        f"{rel}:{i}: {what}: 登记表派生 {actual},文档写 {got}"
                        f" —— 原句: {ln.strip()}")
        # 带钥源名集(README 双语的密钥源表 + zh 行内名单)。只认仓根那两份
        # README(rel 全等):子目录里将来再有同名 README 也不误吃这两条腿。
        if rel == "README.md":
            errors += _keyed_table_errors(
                lines, re.compile(r"All but (\d+) feeds need zero API keys"),
                counts, rel)
        if rel == "README.zh-CN.md":
            errors += _keyed_table_errors(
                lines, re.compile(r"想开 (\d+) 个密钥源"), counts, rel)
            m = re.search(r"想开 (\d+) 个密钥源（([^，）]+)，", "\n".join(lines))
            if m:
                names = {n.strip() for n in m.group(2).split("/") if n.strip()}
                if names != set(counts["keyed_names"]):
                    errors.append(
                        f"{rel}: 行内带钥源名单不符(期望 {counts['keyed_names']},"
                        f"文档 {sorted(names)})")
    return errors


# ── 通扫层(#457)──逐句腿之上的第二层:全部受管文本文件里的源数字面量 ──

# 收刮后缀(文本面);.json 天然受下面 2MB 单文件帽约束:
SCAN_SUFFIXES = frozenset({".md", ".py", ".sh", ".mjs", ".js", ".cjs", ".ts",
                           ".tsx", ".svg", ".conf", ".yml", ".yaml", ".toml",
                           ".txt", ".json"})
SCAN_MAX_BYTES = 2 * 1024 * 1024   # 单文件超过 2MB 跳过并计数(不读大产物)
# 目录排除(名字,任意深度)——逐项原因:
SCAN_EXCLUDE_DIRS = frozenset({
    ".git",             # git 元数据
    "node_modules",     # 第三方依赖安装面
    ".worktrees",       # 并行工作树(其他分支的检出副本)
    "dev",              # 本地 eval 输入/输出(gitignore 兜底,非受管)
    ".venv",             # 本地虚拟环境(第三方库代码)
    "__pycache__",      # 字节码缓存
    ".playwright-mcp",   # 本地浏览器会话快照(gitignore 兜底)
    ".pytest_cache",     # pytest 缓存(实测其自带 README.md 会被当文本收进来)
    ".ruff_cache",       # ruff linter 缓存(生成物,版本号文件会变形状)
})
# 路径排除(仓根相对,精确匹配)——逐项原因:
SCAN_EXCLUDE_PATHS = frozenset({
    "backend/data",   # LMDB 数据存储(生产数据)
    "docs",           # 嵌套私有仓(自己的 git:历史/评审/规格笔记,非本仓受管面)
})
SCAN_EVAL_DIR_PREFIX = ".eval-"   # eval 数据卷映射目录(.eval-prod-data / .eval-gate-mirror)
SCAN_OPS_FIXTURE_DIRS = frozenset({"fixtures", "data"})   # ops 下的测试夹具与基准数据(冻结宇宙)

# 无后缀文件只收 shebang 开头的脚本(integrations/wazuh/custom-ipradar 判例:
# #451 漏网过的集成脚本头注,无扩展名但受管且写源数)。

# 文件级例外:整档跳过。例外之外出现新的字面量即红;卫生闸(exception_table_problems)
# 钉死每条必须带原因、不许「待查」。
SCAN_FILE_EXCEPTIONS: dict[str, str] = {
    "CHANGELOG.md":
        "历史记录:条目数字随当时纪元冻结、永不回改(2026-11-26 通扫实测 15 处历史口径)。",
    "scripts/check_source_counts.py":
        "本闸自身:注释引用旧错句(「29 fused public feeds」「fuses 29 public feeds」)作判例样例。",
    "scripts/test_check_source_counts.py":
        "本闸测试:夹具引用旧错句与改坏句式(「the 6 keyed sources (they share 4 keys」)。",
    "ops/agent-v2/tests/add-lift.test.mjs":
        "ops 加源模板「改数字」函数的单测样例串,数字任意(63/64/60/61/56/65),非源数宣称。",
}

# 说法级例外:该文件内匹配段从行里剔掉再扫(该说法放行,同行其余字面量照红)。
SCAN_PHRASE_EXCEPTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "GLOSSARY.md": (
        (r"≥2 个源被它包含比例",
         "eval「疑似共同上游」算法定义(≥2 是包含比例阈值),非源总数。"),
    ),
    "backend/ipdb/_eval/model.py": (
        (r"2 sources ~fully contained",
         "fountain_suspect 字段注释里的算法阈值(疑似共同上游 ≥2 源),非源总数。"),
    ),
    "backend/tests/core/test_main_routes.py": (
        (r"e\.g\. 27/28 sources",
         "测试注释里的闸覆盖举例数字(e.g. 27/28),非源数宣称。"),
    ),
    "backend/tests/lookup/test_last_seen_chain.py": (
        (r"8 sources already emit",
         "docstring 盘点「哪些源已带 last_seen 字段」的子集计数,口径≠登记表总数。"),
    ),
    "frontend/src/pages/__tests__/SourcesPage.test.tsx": (
        (r"getByText\(/2 sources/\)",
         "前端单测迷你注册表 fixture(2 源 mock)的 UI 文案断言,非登记表口径。"),
    ),
    "ops/agent-v2/bench/add-domain/gen-universe.mjs": (
        (r"sources-redesign",
         "日期+连字复合词「2026-10-17 sources-redesign」被英文正则误读成「17 sources」;事件名,非源数。"),
    ),
    "ops/agent-v2/bench/add-domain/keyless-rules.json": (
        (r"sources-redesign",
         "同上:JSON _doc 引文里的同一日期复合词,非源数。"),
    ),
    "ops/agent-v2/bench/add-domain/SKILL.md": (
        (r"43 个源接入题",
         "加源基准冻结宇宙口径(43 钉死在冻结件 universe.jsonl),非登记表现值。"),
    ),
}

BROAD_EN = re.compile(
    r"(?<![\w.])(\d+)\s+(?:(?:public|fused|fuses|keyed|keyless|registered|shipped)\s+)*(?:sources|feeds)\b")
BROAD_ZH = re.compile(r"(?<![\w.])(\d+)\s*个\s*(?:公开\s*)?(?:情报\s*)?源")
# 近似数前缀(~ / 约 / approximately 直贴数字)不算命中:
APPROX_PREFIX = re.compile(r"(?:~|约|approximately)\s*$")


def exception_table_problems() -> list[str]:
    """例外表卫生闸:每条必须带非空原因、不许「待查」;说法正则必须可编译。"""
    problems: list[str] = []
    for rel, reason in SCAN_FILE_EXCEPTIONS.items():
        if not reason.strip():
            problems.append(f"通扫例外表: {rel} 缺原因(每条例外必须写明为什么放行)")
        elif "待查" in reason:
            problems.append(f"通扫例外表: {rel} 原因含「待查」——例外表不许挂未决条目")
    for rel, entries in SCAN_PHRASE_EXCEPTIONS.items():
        for pat, reason in entries:
            if not reason.strip():
                problems.append(f"通扫例外表: {rel} 说法 {pat!r} 缺原因(每条例外必须写明为什么放行)")
            elif "待查" in reason:
                problems.append(f"通扫例外表: {rel} 说法 {pat!r} 原因含「待查」——例外表不许挂未决条目")
            try:
                re.compile(pat)
            except re.error as e:
                problems.append(f"通扫例外表: {rel} 说法正则编译失败: {e}")
    return problems


def scan_repo(root: Path, counts: dict, *, verbose: bool = False) -> tuple[list[str], dict]:
    """通扫层:--root 下按后缀收受管文本文件,「N sources/feeds / N 个源」字面量的
    数字必须 ∈ 登记表派生集合;近似数与例外表命中放行。返回 (错误列表, 统计)。
    统计键:scanned/skipped_big/skipped_binary/excepted_files/hits/ok/approx。
    verbose=True 时逐条命中打印到 stdout(归类 ok/approx/BAD),供人工对账。"""
    allowed = {counts["public_total"], len(counts["registered"]),
               counts["keyed"], counts["keyless_public"], len(counts["key_envs"])}
    errors: list[str] = []
    stats = {"scanned": 0, "skipped_big": 0, "skipped_binary": 0,
             "excepted_files": 0, "hits": 0, "ok": 0, "approx": 0}
    phrase_res = {rel: [(re.compile(pat), reason) for pat, reason in entries]
                  for rel, entries in SCAN_PHRASE_EXCEPTIONS.items()}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        if rel_dir == ".":
            rel_dir = ""
        keep: list[str] = []
        for d in sorted(dirnames):
            rp = f"{rel_dir}/{d}" if rel_dir else d
            if d in SCAN_EXCLUDE_DIRS or d.startswith(SCAN_EVAL_DIR_PREFIX):
                continue
            if rp in SCAN_EXCLUDE_PATHS:
                continue
            if rel_dir == "ops" and d in SCAN_OPS_FIXTURE_DIRS:
                continue
            keep.append(d)
        dirnames[:] = keep
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = f"{rel_dir}/{fn}" if rel_dir else fn
            suffix = p.suffix.lower()
            if suffix not in SCAN_SUFFIXES:
                if suffix:
                    continue   # 非收刮后缀(图片/二进制产物等,出范围)
                try:           # 无后缀:仅收 shebang 脚本(custom-ipradar 判例)
                    with p.open("rb") as fh:
                        if fh.read(2) != b"#!":
                            continue
                except OSError:
                    continue
            if rel in SCAN_FILE_EXCEPTIONS:
                stats["excepted_files"] += 1
                continue
            try:
                if p.stat().st_size > SCAN_MAX_BYTES:
                    stats["skipped_big"] += 1
                    continue
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                stats["skipped_binary"] += 1
                continue
            stats["scanned"] += 1
            excs = phrase_res.get(rel, ())
            for lineno, raw in enumerate(text.splitlines(), 1):
                line = raw
                for rx, _reason in excs:
                    line = rx.sub("", line)   # 说法级例外:剔匹配段,其余照扫
                for rx in (BROAD_EN, BROAD_ZH):
                    for m in rx.finditer(line):
                        num = int(m.group(1))
                        stats["hits"] += 1
                        where = f"{rel}:{lineno}"
                        if APPROX_PREFIX.search(line[: m.start(1)]):
                            stats["approx"] += 1
                            if verbose:
                                print(f"[scan] approx {where} N={num} | {raw.strip()[:160]}")
                            continue
                        if num in allowed:
                            stats["ok"] += 1
                            if verbose:
                                print(f"[scan] ok     {where} N={num} | {raw.strip()[:160]}")
                            continue
                        errors.append(
                            f"{where}: 源数字面量(通扫): 登记表派生 {sorted(allowed)},"
                            f"文档写 {num} —— 原句: {raw.strip()[:200]}")
                        if verbose:
                            print(f"[scan] BAD    {where} N={num} | {raw.strip()[:160]}")
    return errors, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CI 源数字闸(ADR 0018 机器比对腿)")
    ap.add_argument("--root", type=Path, default=REPO,
                    help="仓根(默认:脚本所在仓;测试指向 fixture 树)")
    ap.add_argument("--scan-verbose", action="store_true",
                    help="通扫层逐条命中打印(文件:行号、数字、归类),供人工对账")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        counts = derive_counts(root / "backend" / "ipdb" / "_sources",
                               root / "backend" / "ipdb" / "_tokens.py")
    except (OSError, ValueError, SyntaxError) as e:
        print(f"[source-counts] 登记表派生失败: {e}", file=sys.stderr)
        return 1
    errors: list[str] = []
    for rel in DOC_FILES:
        p = root / rel
        if not p.exists():
            errors.append(f"{rel}: 扫描面文件缺失(比对面收缩须同步改本闸)")
            continue
        errors += check_doc(p, counts, rel)
    scan_errors, scan_stats = scan_repo(root, counts, verbose=args.scan_verbose)
    errors += scan_errors
    errors += exception_table_problems()
    if errors:
        print(f"[source-counts] RED — 文档源数字与登记表不符({len(errors)} 处):")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"[source-counts] GREEN — 公开源 {counts['public_total']}"
          f"(免钥 {counts['keyless_public']} / 带钥 {counts['keyed']},"
          f"密钥变量 {len(counts['key_envs'])});eval_excluded"
          f" {counts['eval_excluded']};已核 {len(DOC_FILES)} 份文档;通扫"
          f" {scan_stats['scanned']} 份文本文件(整档例外 {scan_stats['excepted_files']}"
          f" / 超大跳过 {scan_stats['skipped_big']} / 非文本跳过"
          f" {scan_stats['skipped_binary']}),源数字面量 {scan_stats['hits']} 处"
          f"(合规 {scan_stats['ok']} / 近似 {scan_stats['approx']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
