"""scripts/check_source_counts.py 的单测(CI 源数字闸,ADR 0018 机器比对腿)。

跑法(仓根): python3 -m pytest scripts/test_check_source_counts.py -q

覆盖矩阵(任务口径):
- 当前仓绿:真实登记表派生 60/53/7/5 + honyport 口径钉死;真五文档零错误;
- 文档数字被改后红:每条比对腿各造一处 fixture 改坏(副本上改,不动真文件),
  含数字腿、带钥源表名集/变量映射腿、zh 行内名单腿;
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
    assert counts["public_total"] == 60
    assert counts["keyless_public"] == 53
    assert counts["keyed"] == 7
    assert len(counts["key_envs"]) == 5
    assert counts["eval_excluded"] == ["honyport"]   # 口径:公开源 = 登记 − eval_excluded
    assert counts["keyed_names"] == [
        "abuseipdb", "ip2proxy", "ipinfo_lite",
        "otx", "otx_subscribed", "threatfox", "urlhaus"]


def test_real_docs_all_green():
    errors = []
    for rel in csc.DOC_FILES:
        errors += csc.check_doc(REPO / rel, csc.derive_counts())
    assert errors == []


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
    return csc.check_doc(p, counts)


def test_readme_en_total_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "README.md", r"Pull 60 public sources",
                         "Pull 61 public sources")
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
    errs = _mutated_copy(tmp_path, "MANUAL.md", r"\(53 of the 60 sources\)",
                         "(52 of the 61 sources)")
    assert any("免钥公开源数" in e for e in errs)
    assert any("公开源总数" in e for e in errs)


def test_manual_en_word_number_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "MANUAL.md",
                         r"The seven keyed sources", "The six keyed sources")
    assert any("(数词)" in e for e in errs), errs


def test_manual_zh_counts_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "MANUAL.zh-CN.md",
                         r"（60 个源中的 53 个）", "（61 个源中的 54 个）")
    assert len([e for e in errs if "公开源总数" in e or "免钥公开源数" in e]) == 2, errs


def test_manual_zh_word_number_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "MANUAL.zh-CN.md",
                         r"七个 key 源", "六个 key 源")
    assert any("(数词)" in e for e in errs), errs


def test_context_token_entry_flipped_red(tmp_path):
    errs = _mutated_copy(tmp_path, "CONTEXT.md", r"共 5 key 7 行", "共 4 key 5 行")
    assert any("密钥变量数/带钥源数" in e for e in errs), errs


def test_missing_doc_file_fails_loud(tmp_path):
    root = tmp_path / "repo"
    (root / "backend/ipdb/_sources").mkdir(parents=True)
    shutil.copytree(REPO / "backend/ipdb/_sources",
                    root / "backend/ipdb/_sources", dirs_exist_ok=True)
    shutil.copy(REPO / "backend/ipdb/_tokens.py",
                root / "backend/ipdb/_tokens.py")
    for rel in csc.DOC_FILES:
        shutil.copy(REPO / rel, root / rel)
    (root / "CONTEXT.md").unlink()
    assert csc.main(["--root", str(root)]) == 1   # 扫描面收缩必须显式改闸,不许静默
