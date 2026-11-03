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
  (backend/ipdb/_sources/honyport.py:78);该标记语义是「评估面恒禁用」,
  与「非公开源」当前恰好 1:1——若未来出现「评估禁用但仍算公开源」的源,
  本闸会在此处先红,提示拆口径。
- 带钥源数/密钥变量数 = backend/ipdb/_tokens.py 的 MANAGED 冻结映射
  (env var → 消费源名)展平;免钥公开源数 = 公开总数 − 带钥(带钥源全公开)。

实现纪律:stdlib-only(ast/re,秒级,CI backend job 零新依赖);静态解析不导入
ipdb(导入即实例化全部源并加载 .env,非幂等且慢)。已知镜像边界(两向漂移
均朝红、fail-loud,不违宁少算;评审 P2 记录):静态只认类体自有赋值,registry
用 hasattr 含继承——继承其体源类不重写 name/fields 的新增会少算误红;registry
实例化失败即跳过而静态照计——会多算误红。两情形出现时先红,提示拆机制。模式匹配是「宁少算」面:
文档改写后某句不再命中正则 = 该句退出比对(不红);命中而数字错 = 红。
跑法(仓根):python3 scripts/check_source_counts.py   # 退出码 0=绿,1=红并列 file:line
"""
from __future__ import annotations

import argparse
import ast
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
                        counts: dict, path: Path) -> list[str]:
    """锚句之后的第一个表格 = 带钥源表;核对源名集合与逐源 env var 映射。
    合并行(threatfox / urlhaus)按 '/' 拆开对集合。"""
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
                    f"{path.name}:{lineno}: 带钥源 {nm} 的变量应为 `{want}`,"
                    f"表格写的是 `{m.group(1)}`")
            elif not m:
                errors.append(f"{path.name}:{lineno}: 带钥源 {nm} 行缺 env var 反引号列")
    if got_names != set(counts["keyed_names"]):
        miss = set(counts["keyed_names"]) - got_names
        extra = got_names - set(counts["keyed_names"])
        errors.append(
            f"{path.name}: 带钥源表名集不符(缺 {sorted(miss) or '无'} /"
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
    ("MANUAL.md", re.compile(r": (\d+) sources, health"), ("public_total",),
     "公开源总数(截图 alt)"),
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
    ("MANUAL.zh-CN.md", re.compile(r"tab[:：](\d+) 源"), ("public_total",),
     "公开源总数(截图 alt)"),
    ("MANUAL.zh-CN.md", re.compile(r"自带的 (\d+) 个源"), ("public_total",),
     "公开源总数"),
    # CONTEXT.md(词汇表「token 源」条的活计数)
    ("CONTEXT.md", re.compile(r"共 (\d+) key (\d+) 行"),
     ("key_envs", "keyed"), "密钥变量数/带钥源数"),
    # GLOSSARY.md(源底座条的活计数,登记总数口径=含私有源,评审 P2-2)
    ("GLOSSARY.md", re.compile(r"全部 (\d+) 个源"), ("registered",),
     "登记源总数"),
)


def check_doc(path: Path, counts: dict) -> list[str]:
    """单文档比对;返回错误串列表(file:line 前缀)。"""
    errors: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for fname, pattern, expects, what in _CHECKS:
        if fname != path.name:
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
                    errors.append(f"{path.name}:{i}: {what}: 数词「{m.group(g)}」无法解析")
                elif got != actual:
                    errors.append(
                        f"{path.name}:{i}: {what}: 登记表派生 {actual},文档写 {got}"
                        f" —— 原句: {ln.strip()}")
        # 带钥源名集(README 双语的密钥源表 + zh 行内名单)
        if path.name == "README.md":
            errors += _keyed_table_errors(
                lines, re.compile(r"All but (\d+) feeds need zero API keys"),
                counts, path)
        if path.name == "README.zh-CN.md":
            errors += _keyed_table_errors(
                lines, re.compile(r"想开 (\d+) 个密钥源"), counts, path)
            m = re.search(r"想开 (\d+) 个密钥源（([^，）]+)，", "\n".join(lines))
            if m:
                names = {n.strip() for n in m.group(2).split("/") if n.strip()}
                if names != set(counts["keyed_names"]):
                    errors.append(
                        f"{path.name}: 行内带钥源名单不符(期望 {counts['keyed_names']},"
                        f"文档 {sorted(names)})")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CI 源数字闸(ADR 0018 机器比对腿)")
    ap.add_argument("--root", type=Path, default=REPO,
                    help="仓根(默认:脚本所在仓;测试指向 fixture 树)")
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
        errors += check_doc(p, counts)
    if errors:
        print(f"[source-counts] RED — 文档源数字与登记表不符({len(errors)} 处):")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"[source-counts] GREEN — 公开源 {counts['public_total']}"
          f"(免钥 {counts['keyless_public']} / 带钥 {counts['keyed']},"
          f"密钥变量 {len(counts['key_envs'])});eval_excluded"
          f" {counts['eval_excluded']};已核 {len(DOC_FILES)} 份文档")
    return 0


if __name__ == "__main__":
    sys.exit(main())
