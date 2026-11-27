"""scripts/review_pack.py 的单测(评审任务书骨架生成器,#512)。

跑法(仓根): python3 -m pytest scripts/test_review_pack.py -q

覆盖(#512 任务书口径):
- 自动槽位数字与 git 一致:任务书里的提交短 sha、受管文件数、+/- 行数
  与 `git diff --numstat` / `git log` 现算值一致;
- reviewed.diff 与 `git diff origin/master...HEAD` 输出逐字节相同;
- 缺槽文件 → 退出码 2 且输出目录里没有新文件(缺槽不落盘);
- 槽文件内容有「<<填」占位 → 退出码 2;
- --check-only 不需要槽文件、不写任何文件。

夹具:tmp_path 里搭一个带真远端(bare 仓)的小 git 仓,push 出真 origin/master,
再 worktree add 一个特性分支提交——与生产用法(基线 origin/master)同构。
"""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_pack as rp  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "review_pack.py"


def git(*args, cwd, binary=False):
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, check=False
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    if binary:
        return proc.stdout
    return proc.stdout.decode("utf-8", "replace")


def run_pack(*argv):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv], capture_output=True, text=True
    )


def write_slot(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """bare 远端 + 主检出(推了 base 提交)+ 特性分支工作树(一个改动提交)。"""
    root = tmp_path_factory.mktemp("reviewpack")
    bare = root / "origin.git"
    git("init", "--bare", "-b", "master", str(bare), cwd=root)
    main = root / "main"
    git("clone", str(bare), str(main), cwd=root)
    git("config", "user.email", "test@example.com", cwd=main)
    git("config", "user.name", "test", cwd=main)
    (main / "a.txt").write_text("line1\nline2\n", encoding="utf-8")
    (main / "sub").mkdir()
    (main / "sub" / "b.txt").write_text("x\n", encoding="utf-8")
    git("add", "-A", cwd=main)
    git("commit", "-m", "base", cwd=main)
    git("push", "origin", "master", cwd=main)
    wt = root / "wt"
    git("worktree", "add", str(wt), "-b", "feature/pack", cwd=main)
    git("config", "user.email", "test@example.com", cwd=wt)
    git("config", "user.name", "test", cwd=wt)
    (wt / "a.txt").write_text("line1\nline2 changed\nline3\n", encoding="utf-8")
    (wt / "c.txt").write_text("new\nfile\n", encoding="utf-8")
    git("add", "-A", cwd=wt)
    git("commit", "-m", "feature change", cwd=wt)
    return SimpleNamespace(root=root, main=main, wt=wt)


def generate(repo, tmp_path, **overrides):
    """正常槽文件跑一遍生成器,返回 (proc, ticket_dir)。

    槽参传字符串=文件内容(写进临时槽文件再传路径);传 Path=现成文件路径
    (可指不存在的路径,测缺失分支)。
    """
    ticket_dir = Path(overrides.pop("ticket_dir", tmp_path / "ticket"))
    slot_paths = {}
    for key, fname, default_text in (
        ("context", "context.md", "这张卡要解决什么:测试。\n"),
        ("evidence", "evidence.md", "门与证据:pytest 全绿。\n"),
        ("questions", "questions.md", "1. 数字对得上吗?\n"),
    ):
        value = overrides.pop(key, default_text)
        slot_paths[key] = str(value) if isinstance(value, Path) else write_slot(tmp_path, fname, value)
    argv = [
        "--worktree", str(repo.wt),
        "--ticket-dir", str(ticket_dir),
        "--ticket", overrides.pop("ticket", "512"),
        "--pr", overrides.pop("pr", "517"),
        "--context", slot_paths["context"],
        "--evidence", slot_paths["evidence"],
        "--questions", slot_paths["questions"],
    ]
    assert not overrides
    return run_pack(*argv), ticket_dir


def expected_counts(repo):
    """numstat 现算:文件数、+ 行、- 行(与生成器同一口径)。"""
    lines = git("diff", "--numstat", "origin/master...HEAD", cwd=repo.wt).splitlines()
    added = deleted = 0
    for line in lines:
        cols = line.split("\t")
        added += int(cols[0]) if cols[0].isdigit() else 0
        deleted += int(cols[1]) if cols[1].isdigit() else 0
    return len(lines), added, deleted


def test_slots_and_diff_match_git(repo, tmp_path):
    proc, ticket_dir = generate(repo, tmp_path)
    assert proc.returncode == 0, proc.stderr
    brief = (ticket_dir / "review-brief.md").read_text(encoding="utf-8")

    # 提交清单:短 sha + 标题与 git log 一致
    commits = git("log", "--no-decorate", "--oneline", "origin/master..HEAD", cwd=repo.wt).splitlines()
    assert len(commits) == 1
    sha, _, title = commits[0].partition(" ")
    assert f"- `{sha}` {title.strip()}" in brief
    assert f"{len(commits)} 个提交" in brief

    # 受管文件数与 +/- 行数与 git diff --numstat 一致
    n_files, added, deleted = expected_counts(repo)
    assert f"{n_files} 个受管文件(+{added} / -{deleted} 行)" in brief

    # 基线短 sha、分支、工作树绝对路径、PR 号
    base_short = git("rev-parse", "--short", "origin/master", cwd=repo.wt).strip()
    assert base_short in brief
    assert "feature/pack" in brief
    assert str(repo.wt.resolve()) in brief
    assert "#512" in brief and "PR #517" in brief

    # diff --stat 摘要进了正文
    stat = git("diff", "--stat", "origin/master...HEAD", cwd=repo.wt).strip()
    assert stat and stat in brief

    # 三节槽文件原文进了任务书
    assert "这张卡要解决什么:测试。" in brief
    assert "门与证据:pytest 全绿。" in brief
    assert "1. 数字对得上吗?" in brief

    # 「输出格式」节逐字 = 脚本常量(= 491 母本)
    assert rp.OUTPUT_FORMAT_SECTION in brief
    assert "## 合并前清单" in brief

    # reviewed.diff 与 git diff 输出逐字节相同
    diff_bytes = git("diff", "origin/master...HEAD", cwd=repo.wt, binary=True)
    assert diff_bytes
    assert (ticket_dir / "reviewed.diff").read_bytes() == diff_bytes


def test_no_pr_omits_pr_slot(repo, tmp_path):
    """不给 --pr:评审对象句里不出现 PR 号(给了才有)。"""
    ticket_dir = tmp_path / "ticket_nopr"
    proc = run_pack(
        "--worktree", str(repo.wt), "--ticket-dir", str(ticket_dir),
        "--ticket", "512",
        "--context", write_slot(tmp_path, "c2.md", "上下文。\n"),
        "--evidence", write_slot(tmp_path, "e2.md", "证据。\n"),
        "--questions", write_slot(tmp_path, "q2.md", "问题。\n"),
    )
    assert proc.returncode == 0
    brief = (ticket_dir / "review-brief.md").read_text(encoding="utf-8")
    assert "PR #" not in brief.split("## 这张卡要解决什么")[0]


def test_missing_slot_exit2_no_files(repo, tmp_path):
    ticket_dir = tmp_path / "ticket_missing"
    proc, _ = generate(repo, tmp_path, ticket_dir=ticket_dir,
                       questions=Path("/nonexistent/questions.md"))
    assert proc.returncode == 2
    assert "--questions" in proc.stderr
    assert "文件不存在" in proc.stderr  # 钉住缺失分支本身,不是别的槽问题顶替
    # 目录里没有新文件(目录本身也不该被建出来)
    assert not ticket_dir.exists() or not any(ticket_dir.iterdir())


def test_empty_slot_exit2(repo, tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("   \n", encoding="utf-8")
    ticket_dir = tmp_path / "ticket_empty"
    proc, _ = generate(repo, tmp_path, ticket_dir=ticket_dir, evidence=empty)
    assert proc.returncode == 2
    assert "--evidence" in proc.stderr
    assert "为空" in proc.stderr  # 钉住空文件分支本身
    assert not ticket_dir.exists() or not any(ticket_dir.iterdir())


def test_placeholder_slot_exit2(repo, tmp_path):
    ticket_dir = tmp_path / "ticket_ph"
    proc, _ = generate(repo, tmp_path, ticket_dir=ticket_dir,
                       context="这张卡要解决什么:<<填这张卡要解决什么>>\n")
    assert proc.returncode == 2
    assert "--context" in proc.stderr
    assert "占位" in proc.stderr  # 钉住占位分支本身(文件存在且非空,只是没填完)
    assert not ticket_dir.exists() or not any(ticket_dir.iterdir())


def test_check_only_prints_slots_writes_nothing(repo, tmp_path):
    ticket_dir = tmp_path / "ticket_check"
    proc = run_pack(
        "--worktree", str(repo.wt), "--ticket-dir", str(ticket_dir),
        "--ticket", "512", "--check-only",
    )
    assert proc.returncode == 0, proc.stderr
    # 不需要槽文件也能打印自动槽位
    base_short = git("rev-parse", "--short", "origin/master", cwd=repo.wt).strip()
    assert f"基线 origin/master: {base_short}" in proc.stdout
    assert "feature/pack" in proc.stdout
    n_files, added, deleted = expected_counts(repo)
    assert f"受管文件数: {n_files}(+{added} / -{deleted} 行)" in proc.stdout
    # 不写任何文件
    assert not ticket_dir.exists()
