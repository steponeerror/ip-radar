"""scripts/check_source_counts.py 的单测(CI 源数字闸,ADR 0018 机器比对腿)。

跑法(仓根): python3 -m pytest scripts/test_check_source_counts.py -q

覆盖矩阵(任务口径):
- 当前仓绿:真实登记表派生口径钉死(eval_excluded/带钥源名集/密钥变量
  等结构性事实)+ 全部入闸文档零错误;源总数/免钥数随加源漂移,断言改 structural
  (公开=登记−eval_excluded 等),不再写死字面量——2026-11-22 判例:写死 60/53
  的版本在九连加源后静默烂了四天,CI 门一直红;
- 文档数字被改后红:代表性比对腿各造一处 fixture 改坏(副本上改,不动真文件),
  含数字腿、带钥源表名集/变量映射腿、zh 行内名单腿;数字腿的句式从
  derive_counts() 现算(源数漂移不再炸夹具),句式本身悬空由激活腿兜住;
- 腿激活钉死(评审 P2):_CHECKS 每条正则必须在真文档上至少命中一次——
  文档改写致正则悬空时,是激活测试红逼更新正则,不是闸面静默缩水;
- 派生面:合成迷你登记表(eval_excluded 减员、带钥×私源重叠、MANAGED 指向
  未注册源、同名重复注册)fail-loud。
"""
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_source_counts as csc   # noqa: E402

REPO = Path(__file__).resolve().parent.parent


# ── 派生面:真实树 ──────────────────────────────────────────────

def test_derive_real_tree_pins_caliber():
    counts = csc.derive_counts()
    # 结构性口径钉死(变更须有意为之):eval_excluded 名单、带钥源名集、
    # 密钥变量数。源总数/免钥数随加源漂移,只断言口径算式不断言字面量。
    assert counts["eval_excluded"] == ["honyport"]   # 口径:公开源 = 登记 − eval_excluded
    assert counts["keyed"] == 7
    assert len(counts["key_envs"]) == 5
    assert counts["keyed_names"] == [
        "abuseipdb", "ip2proxy", "ipinfo_lite",
        "otx", "otx_subscribed", "threatfox", "urlhaus"]
    assert counts["public_total"] == len(counts["registered"]) - len(counts["eval_excluded"])
    assert counts["keyless_public"] == counts["public_total"] - len(
        [n for n in counts["keyed_names"] if n not in counts["eval_excluded"]])


def test_real_docs_all_green():
    counts = csc.derive_counts()
    errors = []
    for rel in csc.DOC_FILES:
        errors += csc.check_doc(REPO / rel, counts, rel)   # rel=仓根相对路径:子目录腿(svg/wazuh)按路径命中,不只按文件名
    scan_errors, _stats = csc.scan_repo(REPO, counts)   # #457:通扫层同闸(全部受管文本文件的源数字面量)
    assert errors + scan_errors == []


def test_main_exit_zero_on_current_repo():
    assert csc.main([]) == 0


# ── 派生面:合成迷你登记表 ─────────────────────────────────────

def _mini_tree(tmp_path, *, with_eval_excluded=True, keyed_private=False):
    src = tmp_path / "backend/ipdb/_sources"
    src.mkdir(parents=True)
    (src / "_base.py").write_text("class Source:\n    pass\n")
    (src / "alpha.py").write_text(
        "class Alpha:\n    name = 'alpha'\n    fields = ('city',)\n")
    (src / "beta.py").write_text(
        "class Beta:\n    name = 'beta'\n    fields = ('is_malicious',)\n"
        + ("    eval_excluded = True\n" if with_eval_excluded else ""))
    (src / "gamma.py").write_text(
        "class Gamma:\n    name = 'gamma'\n    fields = ('is_proxy',)\n")
    names = ["gamma"] + (["beta"] if keyed_private else [])
    tokens = tmp_path / "backend/ipdb/_tokens.py"
    tokens.write_text(
        "MANAGED: dict[str, list[str]] = {\n"
        f"    'G_KEY': {names!r},\n"
        "}\n")
    return src, tokens


def test_derive_synthetic(tmp_path):
    src, tokens = _mini_tree(tmp_path)
    c = csc.derive_counts(src, tokens)
    assert c["registered"] == ["alpha", "beta", "gamma"]
    assert c["public_total"] == 2          # beta eval_excluded 不入公开口径
    assert c["keyed"] == 1
    assert c["keyless_public"] == 1


def test_derive_keyed_eval_excluded_overlap(tmp_path):
    """带钥源同时 eval_excluded → 免钥公开数只扣公开侧的带钥源。"""
    src, tokens = _mini_tree(tmp_path, keyed_private=True)
    c = csc.derive_counts(src, tokens)
    assert c["public_total"] == 2
    assert c["keyed"] == 2                 # keyed 名单 = MANAGED 全展平(gamma+beta)
    assert c["keyless_public"] == 1        # 公开侧带钥只 gamma;beta 不在公开侧


def test_derive_managed_ghost_fails_loud(tmp_path):
    src, tokens = _mini_tree(tmp_path)
    tokens.write_text("MANAGED = {'G_KEY': ['ghost']}\n")
    with pytest.raises(ValueError, match="未注册源"):
        csc.derive_counts(src, tokens)


def test_derive_duplicate_name_fails_loud(tmp_path):
    src, tokens = _mini_tree(tmp_path)
    (src / "dup.py").write_text(
        "class Dup:\n    name = 'alpha'\n    fields = ('x',)\n")
    with pytest.raises(ValueError, match="重复注册"):
        csc.derive_counts(src, tokens)


# ── 比对面:改坏必红(fixture 副本,不动真文件) ─────────────────

def _mutated_copy(tmp_path, rel, pattern, repl, counts=None):
    """真文档副本上做一处替换,返回 check_doc 错误列表。"""
    counts = counts or csc.derive_counts()
    text = (REPO / rel).read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=1)
    assert n == 1, f"fixture 替换未命中: {rel} {pattern}"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new, encoding="utf-8")
    return csc.check_doc(p, counts, rel)   # rel=仓根相对路径:子目录文档的腿按路径命中(不传则静默全跳)


def test_readme_en_total_flipped_red(tmp_path):
    c = csc.derive_counts()
    errs = _mutated_copy(tmp_path, "README.md",
                         rf"Pull {c['public_total']} public sources",
                         f"Pull {c['public_total'] + 1} public sources")
    assert any(":1:" in e or "公开源总数" in e for e in errs), errs


def test_readme_en_keyed_and_keys_flipped_red(tmp_path):
    errs = _mutated_copy(
        tmp_path, "README.md",
        r"the 7 keyed sources \(they share 5 keys",
        "the 6 keyed sources (they share 4 keys")
    assert any("带钥源数" in e for e in errs), errs
    assert any("密钥变量数" in e for e in errs), errs


def test_readme_keyed_table_row_dropped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "README.md",
                         r"\| threatfox / urlhaus \| `ABUSECH_AUTH_KEY`[^|]*\|[^|]*\|\n",
                         "")
    assert any("带钥源表名集不符" in e for e in errs), errs


def test_readme_keyed_table_var_drift_red(tmp_path):
    errs = _mutated_copy(tmp_path, "README.md",
                         r"\| abuseipdb \| `ABUSEIPDB_API_KEY`",
                         "| abuseipdb | `STALE_KEY`")
    assert any("变量应为" in e for e in errs), errs


def test_readme_zh_inline_name_list_drift_red(tmp_path):
    errs = _mutated_copy(
        tmp_path, "README.zh-CN.md",
        r"ipinfo_lite / abuseipdb / otx / otx_subscribed /",
        "ipinfo_lite / abuseipdb / otx /")
    assert any("行内带钥源名单" in e for e in errs), errs


def test_manual_en_fraction_flipped_red(tmp_path):
    c = csc.derive_counts()
    errs = _mutated_copy(
        tmp_path, "MANUAL.md",
        rf"\({c['keyless_public']} of the {c['public_total']} sources\)",
        f"({c['keyless_public'] - 1} of the {c['public_total'] + 1} sources)")
    assert any("免钥公开源数" in e for e in errs)
    assert any("公开源总数" in e for e in errs)


def test_manual_en_word_number_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "MANUAL.md",
                         r"The seven keyed sources", "The six keyed sources")
    assert any("(数词)" in e for e in errs), errs


def test_manual_zh_counts_flipped_red(tmp_path):
    c = csc.derive_counts()
    errs = _mutated_copy(
        tmp_path, "MANUAL.zh-CN.md",
        rf"（{c['public_total']} 个源中的 {c['keyless_public']} 个）",
        f"（{c['public_total'] + 1} 个源中的 {c['keyless_public'] - 1} 个）")
    assert len([e for e in errs if "公开源总数" in e or "免钥公开源数" in e]) == 2, errs


def test_manual_zh_word_number_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "MANUAL.zh-CN.md",
                         r"七个 key 源", "六个 key 源")
    assert any("(数词)" in e for e in errs), errs


def test_context_token_entry_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "CONTEXT.md", r"共 5 key 7 行", "共 4 key 5 行")
    assert any("密钥变量数/带钥源数" in e for e in errs), errs


# ── 通扫层(#457):全部受管文本文件里的源数字面量 ─────────────

def _fixture_root(tmp_path):
    """真仓受管面最小副本:登记表 + 全部 DOC_FILES(子目录腿要父目录)。"""
    root = tmp_path / "repo"
    (root / "backend/ipdb/_sources").mkdir(parents=True)
    shutil.copytree(REPO / "backend/ipdb/_sources",
                    root / "backend/ipdb/_sources", dirs_exist_ok=True)
    shutil.copy(REPO / "backend/ipdb/_tokens.py",
                root / "backend/ipdb/_tokens.py")
    for rel in csc.DOC_FILES:
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)   # 子目录腿(svg/wazuh)需父目录
        shutil.copy(REPO / rel, dst)
    return root


def _fixture_counts(root):
    return csc.derive_counts(root / "backend/ipdb/_sources",
                             root / "backend/ipdb/_tokens.py")


def test_scan_svg_digit_flip_red_on_both_layers(tmp_path):
    """#457 验收:svg 的 70 改回 29 → 旧腿与通扫都红(各至少一条)。"""
    root = _fixture_root(tmp_path)
    c = _fixture_counts(root)
    svg = root / "assets/social-preview.svg"
    text = svg.read_text(encoding="utf-8")
    assert f"{c['public_total']} sources" in text
    svg.write_text(text.replace(f"{c['public_total']} sources", "29 sources"),
                   encoding="utf-8")
    doc_errs = csc.check_doc(svg, c, "assets/social-preview.svg")
    assert any("公开源总数" in e for e in doc_errs), doc_errs   # 旧腿
    scan_errs, _stats = csc.scan_repo(root, c)
    assert any(e.startswith("assets/social-preview.svg:") and "通扫" in e
               for e in scan_errs), scan_errs   # 通扫层
    assert csc.main(["--root", str(root)]) == 1


def test_scan_new_unlisted_file_wrong_number_red(tmp_path):
    """#457 验收:不在任何名单的新文件写错数 → 红,报出该文件(#451 漏网形状)。"""
    root = _fixture_root(tmp_path)
    new = root / "integrations/newtool/README.md"
    new.parent.mkdir(parents=True)
    new.write_text("ipradar ships 29 fused public feeds for your SIEM.\n",
                   encoding="utf-8")
    errs, _stats = csc.scan_repo(root, _fixture_counts(root))
    assert any(e.startswith("integrations/newtool/README.md:") for e in errs), errs
    assert csc.main(["--root", str(root)]) == 1


def test_scan_new_unlisted_file_derived_number_green(tmp_path):
    """#457 验收:同一新文件写登记表派生数 → 绿。"""
    root = _fixture_root(tmp_path)
    c = _fixture_counts(root)
    new = root / "integrations/newtool/README.md"
    new.parent.mkdir(parents=True)
    new.write_text(f"ipradar ships {c['public_total']} fused public feeds"
                   " for your SIEM.\n", encoding="utf-8")
    errs, stats = csc.scan_repo(root, c)
    assert errs == [], errs
    assert stats["hits"] >= 1   # 新文件的合规命中计入(夹具真文档另有自己的命中)
    assert csc.main(["--root", str(root)]) == 0


def test_scan_approx_numbers_not_hits(tmp_path):
    """#457 验收:近似数(~ / 约 前缀)不算命中,数字与派生集无关也绿——
    用 99 自证:若近似规则失效,99 ∉ 派生集必红。"""
    root = _fixture_root(tmp_path)
    base = csc.scan_repo(root, _fixture_counts(root))[1]["approx"]   # 夹具真文档自带的近似命中(ziyadnz 等)
    new = root / "integrations/newtool/README.md"
    new.parent.mkdir(parents=True)
    new.write_text("aggregates ~10 public feeds per day\n"
                   "把约 10 个公开源聚成清单\n"
                   "~99 public feeds reported\n"
                   "约 99 个公开源被聚合\n", encoding="utf-8")
    errs, stats = csc.scan_repo(root, _fixture_counts(root))
    assert errs == [], errs
    assert stats["approx"] == base + 4   # 新文件恰好 4 处:英文两处 + 中文两处,中文正则坏了这里就少 2


def test_scan_phrase_exception_excises_only_the_phrase(tmp_path):
    """说法级例外只剔该说法的匹配段:同一行里其余字面量照红。
    例外说法和错数放同一行——实现若退化成「含例外说法的整行跳过」,这里就不报了。"""
    root = _fixture_root(tmp_path)
    base = csc.scan_repo(root, _fixture_counts(root))[1]["excised"]   # 夹具里 GLOSSARY 自带的一处
    model = root / "backend/ipdb/_eval/model.py"   # 路径在说法级例外表里
    model.parent.mkdir(parents=True)
    model.write_text(
        "fountain_suspect: bool = False  # >=2 sources ~fully contained (was 37 sources)\n",
        encoding="utf-8")
    errs, stats = csc.scan_repo(root, _fixture_counts(root))
    assert len(errs) == 1 and errs[0].startswith("backend/ipdb/_eval/model.py:1:") \
        and "文档写 37" in errs[0], errs
    assert stats["excised"] == base + 1   # 被例外剔掉的段有计数,不从输出里消失


def test_scan_zh_literal_shebang_script_and_build_output(tmp_path):
    r"""三条规则各有一个「改坏会红」的钉,外加日期复合词的根治:
    - backend/ 下新 .md 写「29 个公开情报源」→ 红(钉住中文正则,和 backend/ 没被排除);
    - integrations/newtool/custom-tool(无后缀、首行 #!)写「29 fused public feeds」→ 红
      (#451 漏网的就是这种集成脚本的头注);
    - frontend/dist/app.js(构建产物)写「29 sources」→ 不报(CI 在门步前把 frontend-dist 产物
      下载到这里,第三方打包结果不是本仓文档);
    - 「2026-10-17 sources-redesign」不被读成「17 sources」(靠正则里的 (?<!\d-),不走例外表)。"""
    root = _fixture_root(tmp_path)
    (root / "backend/tests").mkdir(parents=True)
    (root / "backend/tests/notes.md").write_text("本项目现在汇 29 个公开情报源。\n", encoding="utf-8")
    tool = root / "integrations/newtool/custom-tool"
    tool.parent.mkdir(parents=True)
    tool.write_text("#!/bin/sh\n# ships 29 fused public feeds\n", encoding="utf-8")
    (root / "frontend/dist").mkdir(parents=True)
    (root / "frontend/dist/app.js").write_text("var s = '29 sources';\n", encoding="utf-8")
    (root / "integrations/newtool/HISTORY.md").write_text(
        "since 2026-10-17 sources-redesign the pool grew\n", encoding="utf-8")
    errs, _stats = csc.scan_repo(root, _fixture_counts(root))
    assert sorted(e.split(":")[0] for e in errs) == [
        "backend/tests/notes.md", "integrations/newtool/custom-tool"], errs
    assert all("文档写 29" in e for e in errs), errs


def test_scan_zh_keyed_modifier(tmp_path):
    """中文正则认「N 个密钥源 / N 个 key 源 / N 个数据源」:写对绿,写错红。"""
    root = _fixture_root(tmp_path)
    c = _fixture_counts(root)
    doc = root / "integrations/newtool/README.zh-CN.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(f"要开 {c['keyed']} 个密钥源,先把 {c['keyed']} 个 key 源的密钥写进 .env;"
                   f"另有 {c['keyless_public']} 个数据源免密钥。\n", encoding="utf-8")
    assert csc.scan_repo(root, c) == ([], csc.scan_repo(root, c)[1])
    doc.write_text(doc.read_text(encoding="utf-8").replace(
        f"{c['keyed']} 个密钥源", f"{c['keyed'] + 1} 个密钥源"), encoding="utf-8")
    errs, _stats = csc.scan_repo(root, c)
    assert len(errs) == 1 and errs[0].startswith("integrations/newtool/README.zh-CN.md:1:") \
        and f"文档写 {c['keyed'] + 1}" in errs[0], errs


def test_exception_table_hygiene(monkeypatch):
    """例外表卫生闸:缺原因 / 含「待查」/ 正则编不过即红(防未决条目混入)。"""
    assert csc.exception_table_problems() == []
    monkeypatch.setattr(csc, "SCAN_FILE_EXCEPTIONS",
                        {**csc.SCAN_FILE_EXCEPTIONS, "somewhere/doc.md": ""})
    assert any("缺原因" in p for p in csc.exception_table_problems())
    monkeypatch.setattr(csc, "SCAN_FILE_EXCEPTIONS",
                        {**csc.SCAN_FILE_EXCEPTIONS, "somewhere/doc.md": "待查"})
    assert any("待查" in p for p in csc.exception_table_problems())
    monkeypatch.setattr(
        csc, "SCAN_PHRASE_EXCEPTIONS",
        {**csc.SCAN_PHRASE_EXCEPTIONS, "somewhere/doc.md": ((r"\\d+ sources", ""),)})
    assert any("缺原因" in p for p in csc.exception_table_problems())
    monkeypatch.setattr(
        csc, "SCAN_PHRASE_EXCEPTIONS",
        {**csc.SCAN_PHRASE_EXCEPTIONS, "somewhere/doc.md": ((r"[unclosed", "有原因"),)})
    assert any("编译失败" in p for p in csc.exception_table_problems())   # 正则要真编不过才走到这条分支


def test_main_red_on_hygiene_problem(monkeypatch, capsys):
    """例外表有卫生问题时 main() 必须红(即使扫描本身全绿),并单列标题——
    2026-11-26 监督者折入评审意见时把 return 1 挪错过一次:有扫描错误、没卫生问题时
    竟然落到 GREEN。这条测试钉住两条出口都通向红。"""
    monkeypatch.setattr(csc, "SCAN_FILE_EXCEPTIONS",
                        {**csc.SCAN_FILE_EXCEPTIONS, "somewhere/doc.md": ""})
    assert csc.main([]) == 1
    out = capsys.readouterr().out
    assert "通扫例外表卫生问题(1 处)" in out and "GREEN" not in out, out[-400:]
    assert "文档源数字与登记表不符" not in out, out[-400:]   # 扫描本身没有错,不套那个标题


def test_exception_targets_exist_on_real_repo():
    """例外表指向的文件必须在真仓在场(防过期条目静默挂表)。"""
    for rel in csc.SCAN_FILE_EXCEPTIONS:
        assert (REPO / rel).is_file(), rel
    for rel, entries in csc.SCAN_PHRASE_EXCEPTIONS.items():
        assert (REPO / rel).is_file(), rel
        text = (REPO / rel).read_text(encoding="utf-8")
        for pat, _reason in entries:
            assert re.search(pat, text), f"说法级例外已失活(文件里不再命中):{rel} {pat!r}" \
                "——原文改掉后要把这条例外删掉,免得它悄悄放过以后新写的句子"


def test_missing_doc_file_fails_loud(tmp_path):
    root = _fixture_root(tmp_path)
    (root / "CONTEXT.md").unlink()
    assert csc.main(["--root", str(root)]) == 1   # 扫描面收缩必须显式改闸,不许静默


def test_new_legs_zh_tail_mermaid_var_red(tmp_path):
    """评审 P2-1 增补腿:zh 尾句 7 🔑、mermaid 7 keyed、五个变量(数词)。"""
    errs = _mutated_copy(tmp_path, "README.zh-CN.md", r"剩下 7 个 🔑 源",
                         "剩下 6 个 🔑 源")
    assert any("尾句" in e for e in errs), errs
    errs = _mutated_copy(tmp_path, "README.zh-CN.md", r"keyless auto \+ 7 keyed",
                         "keyless auto + 8 keyed")
    assert any("mermaid" in e for e in errs), errs
    errs = _mutated_copy(tmp_path, "README.zh-CN.md", "五个变量", "四个变量")
    assert any("密钥变量数(数词" in e for e in errs), errs


def test_new_legs_manual_key_envs_word_red(tmp_path):
    """评审 P2-1 增补腿:MANUAL 双语 five source keys / 五个源密钥(数词)。"""
    errs = _mutated_copy(tmp_path, "MANUAL.md", "the five source keys",
                         "the six source keys")
    assert any("密钥变量数(数词" in e for e in errs), errs
    errs = _mutated_copy(tmp_path, "MANUAL.zh-CN.md", "五个源密钥", "六个源密钥")
    assert any("密钥变量数(数词" in e for e in errs), errs


def test_new_leg_glossary_registered_total_red(tmp_path):
    """评审 P2-2 增补腿:GLOSSARY 源底座条活计数(登记总数口径,含私有源)。"""
    c = csc.derive_counts()
    errs = _mutated_copy(tmp_path, "GLOSSARY.md",
                         rf"全部 {len(c['registered'])} 个源",
                         f"全部 {len(c['registered']) - 1} 个源")
    assert any("登记源总数" in e for e in errs), errs


def test_all_check_legs_active_on_real_docs():
    """评审 P2:激活钉死——_CHECKS 每条 (文件, 正则) 必须在真文档至少命中一次。

    没有它,文档改写致某条正则悬空时闸面会静默缩水(宁少算=失配退出比对),
    test_real_docs_all_green 在「激活」与「悬空」两态下都绿,无法区分。"""
    for fname, pattern, _expects, _what in csc._CHECKS:
        text = (REPO / fname).read_text(encoding="utf-8")
        assert any(pattern.search(ln) for ln in text.splitlines()), (
            f"{fname} 的比对腿已悬空(正则 {pattern.pattern!r} 在真文档零命中)——"
            f"文档已改写,请更新该腿或其期望")


@pytest.mark.parametrize("rel", [
    "assets/social-preview.svg",
    "integrations/wazuh/README.md",
    "integrations/wazuh/custom-ipradar",
    "scripts/fail2ban/ipradar.conf",
])
def test_subdir_doc_total_flipped_red(tmp_path, rel):
    """子目录文档的公开源总数腿真会咬(2026-11-25 #451 评审记录 4)。

    这四条腿按仓根相对路径分派。首版 test_real_docs_all_green 没把 rel 传给
    check_doc,子目录腿被静默跳过而测试照绿——所以每条腿都要有一个「改坏
    必红」的夹具,报错前缀也必须是仓根相对路径(否则看不出是哪个目录的
    README)。句式从 _CHECKS 现取,源数漂移不炸夹具。"""
    c = csc.derive_counts()
    legs = [pat for fname, pat, _e, _w in csc._CHECKS if fname == rel]
    assert len(legs) == 1, (rel, legs)
    text = (REPO / rel).read_text(encoding="utf-8")
    m = next(leg.search(ln) for leg in legs for ln in text.splitlines()
             if leg.search(ln))
    old = m.group(0)
    new = old.replace(m.group(1), str(c["public_total"] + 1), 1)
    assert new != old
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    errs = csc.check_doc(p, c, rel)
    assert len(errs) == 1 and errs[0].startswith(rel + ":"), errs
    assert f"登记表派生 {c['public_total']},文档写 {c['public_total'] + 1}" in errs[0]


# ── 源表层(2026-11-26 收尾):README 双语源表名单对登记表 ─────────────

def _fixture_source_row(root, rel, name):
    """夹具 README 源表层里「| name |」那一行(聚合源行名后带 `*`)。只在源表层里找:
    README 顶部的带钥源表也有以 `| otx |` 这类带钥源名开头的行。"""
    p = root / rel
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    heading = dict(csc.README_SOURCE_SECTIONS)[rel]
    start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
    hit = [i for i, ln in enumerate(lines) if i > start
           and re.match(rf"\| {name}( `\*`)? \|", ln)]
    assert len(hit) == 1, (rel, name, hit)
    return p, lines, hit[0]


def test_readme_source_tables_match_registry_on_real_repo():
    """两份 README 的源表名单 == 公开源集合(登记 − eval_excluded)。"""
    assert csc.check_readme_tables(REPO, csc.derive_counts()) == []


def test_readme_source_table_row_dropped_red(tmp_path):
    """源表少一行(2026-11-25 量出的漏法:计数句全对、表里没补行)→ 红,报出缺的源名;main 也红。"""
    root = _fixture_root(tmp_path)
    p, lines, i = _fixture_source_row(root, "README.md", "echelon")
    p.write_text("".join(lines[:i] + lines[i + 1:]), encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and errs[0].startswith("README.md:"), errs
    assert "缺 ['echelon']" in errs[0] and "多 无" in errs[0], errs
    assert csc.main(["--root", str(root)]) == 1


def test_readme_source_table_unknown_name_red(tmp_path):
    """源表多出一个登记表里没有的名字 → 红,「多」带行号(要去那一行改)。"""
    root = _fixture_root(tmp_path)
    p, lines, i = _fixture_source_row(root, "README.zh-CN.md", "echelon")
    lines[i] = lines[i].replace("| echelon |", "| ghost_source |", 1)
    p.write_text("".join(lines), encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and errs[0].startswith("README.zh-CN.md:"), errs
    assert "缺 ['echelon']" in errs[0], errs
    assert f"多 ['ghost_source(第 {i + 1} 行)']" in errs[0], errs
    assert csc.main(["--root", str(root)]) == 1


def test_readme_source_table_private_source_listed_red(tmp_path):
    """eval_excluded 的私有源(honyport)写进公开源表 → 红:公开源 = 登记 − eval_excluded 的口径钉。"""
    root = _fixture_root(tmp_path)
    p, lines, i = _fixture_source_row(root, "README.md", "nerd_medconf")
    lines.insert(i, "| honyport | local | private observation source | |\n")
    p.write_text("".join(lines), encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and "多 ['honyport(第 " in errs[0] and "缺 无" in errs[0], errs


def test_readme_source_table_duplicate_row_red(tmp_path):
    """同一源在表里出现两次 → 红(加源流程重跑把行加两遍的形状)。"""
    root = _fixture_root(tmp_path)
    p, lines, i = _fixture_source_row(root, "README.md", "nerd_medconf")
    lines.insert(i, lines[i])
    p.write_text("".join(lines), encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and "重复出现的源 ['nerd_medconf']" in errs[0], errs


def test_readme_source_table_section_or_header_rewritten_fails_loud(tmp_path):
    """标题被改写、或节里混进一张非源表 → 这一层不静默退出:名单比对一退出,缺行就永远看不见。"""
    root = _fixture_root(tmp_path)
    p = root / "README.md"
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace("## Data Sources & Acknowledgments", "## Sources & Thanks"),
                 encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and errs[0].startswith("README.md:") and "找不到二级标题" in errs[0], errs
    assert csc.main(["--root", str(root)]) == 1
    p.write_text(text.replace("## Development",
                              "| Key | Meaning |\n|---|---|\n| x | y |\n\n## Development"),
                 encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and "表头不是「Source / 源」" in errs[0], errs
    p.write_text(text, encoding="utf-8")   # 还原:下一种情形从不带那张表的版本开始
    # 首格不是源名形状(带了说明文字)同样报错:名单比对不带着读不懂的行往下走
    p2, lines2, j = _fixture_source_row(root, "README.md", "nerd_medconf")
    lines2[j] = lines2[j].replace("| nerd_medconf |", "| nerd_medconf (paid tier) |", 1)
    p2.write_text("".join(lines2), encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and f"第 {j + 1} 行首格" in errs[0] and "不是源名形状" in errs[0], errs


def test_readme_source_table_empty_first_cell_red(tmp_path):
    """首格为空的表行不静默跳过:既不计也不报就等于放走一行(本层「不静默」的说法要成立)。"""
    root = _fixture_root(tmp_path)
    p, lines, i = _fixture_source_row(root, "README.md", "nerd_medconf")
    lines[i] = lines[i].replace("| nerd_medconf |", "|  |", 1)
    p.write_text("".join(lines), encoding="utf-8")
    errs = csc.check_readme_tables(root, _fixture_counts(root))
    assert len(errs) == 1 and f"第 {i + 1} 行首格「」不是源名形状" in errs[0], errs


def test_readme_source_table_scope_ends_at_next_h2(tmp_path):
    """下一个二级标题之后的表不归这一层管:在「## Development」之后放一张非源表,仍绿。
    (实现里收口的那个 break 删掉就红——两份 README 的节后今天没有表行,别的测试钉不住它。)"""
    root = _fixture_root(tmp_path)
    p = root / "README.md"
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace(
        "## Development", "## Development\n\n| Key | Meaning |\n|---|---|\n| x | y |\n"),
        encoding="utf-8")
    assert csc.check_readme_tables(root, _fixture_counts(root)) == []


def test_readme_source_table_ignores_fenced_block_and_reads_indented_rows(tmp_path):
    """节里的三反引号围栏内含表行 → 不算表;行首缩进两个空格的源表行 → 照收。"""
    root = _fixture_root(tmp_path)
    p = root / "README.md"
    text = p.read_text(encoding="utf-8")
    p.write_text(text.replace(
        "### Geo & ASN",
        "```\n| Key | Meaning |\n|---|---|\n| x | y |\n```\n\n### Geo & ASN"),
        encoding="utf-8")
    assert csc.check_readme_tables(root, _fixture_counts(root)) == []
    p, lines, i = _fixture_source_row(root, "README.md", "nerd_medconf")
    lines[i] = "  " + lines[i]
    p.write_text("".join(lines), encoding="utf-8")
    assert csc.check_readme_tables(root, _fixture_counts(root)) == []


def test_missing_readme_is_reported_not_raised(tmp_path, capsys):
    """README 缺失:本层报一条错、main 红——不让 FileNotFoundError 穿出去只剩 traceback。"""
    root = _fixture_root(tmp_path)
    (root / "README.zh-CN.md").unlink()
    assert csc.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "README.zh-CN.md: 源表层退出比对失败" in out, out[-600:]
