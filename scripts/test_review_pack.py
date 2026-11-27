"""scripts/review_pack.py 的单测(评审任务书骨架生成器,#512)。

跑法(仓根): python3 -m pytest scripts/test_review_pack.py -q

覆盖(#512 任务书 + 评审返工任务书口径):
- 自动槽位数字与 git 一致:任务书里的提交短 sha(git log)、受管文件数、+/- 行数
  (numstat 现算,二进制计入文件数不计行数)与现算值一致;
- 「基线」= 分叉点(git merge-base origin/master HEAD),不是 origin/master 尖端;
  master 往前走后任务书写明「之后 master 前进到 …」(夹具让 master 真的前进一步,
  钉住三点 diff 语义——夹具里 master 从不动时三点退化成两点,任何用例都不红);
- reviewed.diff 与 `git diff origin/master...HEAD` 输出逐字节相同;
- 缺槽/未提供/空槽/读不出(非 UTF-8)→ 退出码 2 且输出目录里没有新文件;
- 槽文件内容有「<<填」占位 → 退出码 2;
- --check-only 不需要槽文件和 --ticket-dir、不写任何文件;
- --base 传父分支名时只算叠上去的提交(叠分支场景);
- 工作树有未提交改动时 stderr 告警、任务书带提示句。

夹具:tmp_path 里搭一个带真远端(bare 仓)的小 git 仓,push 出真 origin/master,
worktree add 一个特性分支提交,然后在主检出 master 上再前进一步并 push——
与生产用法(基线 origin/master,master 会漂)同构。
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
    return proc.stdout.decode("utf-8", "replace").strip()


def run_pack(*argv):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv], capture_output=True, text=True
    )


def write_slot(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def fork_short_of(repo):
    """分叉点短 sha = 生成器「基线」槽应打的值(不是 origin/master 尖端)。"""
    full = git("merge-base", "origin/master", "HEAD", cwd=repo.wt).strip()
    return git("rev-parse", "--short", full, cwd=repo.wt).strip()


def expected_counts(repo):
    """numstat 现算:文件数、+ 行、- 行(与生成器同一口径;二进制计入文件数不计行数)。"""
    lines = git("diff", "--numstat", "origin/master...HEAD", cwd=repo.wt).splitlines()
    added = deleted = 0
    for line in lines:
        cols = line.split("\t")
        added += int(cols[0]) if cols[0].isdigit() else 0
        deleted += int(cols[1]) if cols[1].isdigit() else 0
    return len(lines), added, deleted


def configure(repo_path):
    git("config", "user.email", "test@example.com", cwd=repo_path)
    git("config", "user.name", "test", cwd=repo_path)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """bare 远端 + 主检出(base 提交→push)+ 特性分支工作树(1 提交)+ master 前进一步。"""
    root = tmp_path_factory.mktemp("reviewpack")
    bare = root / "origin.git"
    git("init", "--bare", "-b", "master", str(bare), cwd=root)
    main = root / "main"
    git("clone", str(bare), str(main), cwd=root)
    configure(main)
    (main / "a.txt").write_text("line1\nline2\n", encoding="utf-8")
    (main / "sub").mkdir()
    (main / "sub" / "b.txt").write_text("x\n", encoding="utf-8")
    git("add", "-A", cwd=main)
    git("commit", "-m", "base", cwd=main)
    git("push", "origin", "master", cwd=main)
    wt = root / "wt"
    git("worktree", "add", str(wt), "-b", "feature/pack", cwd=main)
    configure(wt)
    (wt / "a.txt").write_text("line1\nline2 changed\nline3\n", encoding="utf-8")
    (wt / "c.txt").write_text("new\nfile\n", encoding="utf-8")
    (wt / "bin.dat").write_bytes(b"\x00\xff")  # 二进制:numstat 两列为「-」
    git("add", "-A", cwd=wt)
    git("commit", "-m", "feature change", cwd=wt)
    # master 往前走一步并 push:origin/master 尖端从此 ≠ 分叉点
    (main / "sub" / "b.txt").write_text("x\nmaster advanced\n", encoding="utf-8")
    git("add", "-A", cwd=main)
    git("commit", "-m", "advance master", cwd=main)
    git("push", "origin", "master", cwd=main)
    return SimpleNamespace(root=root, main=main, wt=wt)


def generate(repo, tmp_path, **overrides):
    """正常槽文件跑一遍生成器,返回 (proc, ticket_dir)。

    槽参传字符串=文件内容(写进临时槽文件再传路径);传 Path=现成文件路径
    (可指不存在或读不出的文件,测缺失/读不出分支)。
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


def test_slots_and_diff_match_git(repo, tmp_path):
    proc, ticket_dir = generate(repo, tmp_path)
    assert proc.returncode == 0, proc.stderr
    brief = (ticket_dir / "review-brief.md").read_text(encoding="utf-8")

    # 提交清单:短 sha + 标题与 git log 一致(origin/master..HEAD 只含特性提交)
    commits = git("log", "--no-decorate", "--oneline", "origin/master..HEAD", cwd=repo.wt).splitlines()
    assert len(commits) == 1
    sha, _, title = commits[0].partition(" ")
    assert f"- `{sha}` {title.strip()}" in brief
    assert f"{len(commits)} 个提交" in brief

    # 受管文件数与 +/- 行数与 git diff --numstat 一致(a.txt +2/−1、c.txt +2、bin.dat 二进制)
    n_files, added, deleted = expected_counts(repo)
    assert (n_files, added, deleted) == (3, 4, 1)  # 夹具口径自检
    assert f"{n_files} 个受管文件(+{added} / -{deleted} 行)" in brief

    # 「基线」= 分叉点,不是 origin/master 尖端;master 前进句在场
    fork = fork_short_of(repo)
    tip = git("rev-parse", "--short", "origin/master", cwd=repo.wt).strip()
    assert fork != tip, "夹具自检:master 必须已前进"
    assert f"基线 master `{fork}`" in brief
    assert f"之后 master 前进到 `{tip}`,多 1 个提交" in brief

    # 分支、工作树与主检出绝对路径、PR 号
    assert "feature/pack" in brief
    assert str(repo.wt.resolve()) in brief
    assert str(repo.main) in brief
    assert "#512" in brief and "PR #517" in brief

    # diff --stat 摘要进了正文,二进制文件在列
    stat = git("diff", "--stat", "origin/master...HEAD", cwd=repo.wt).strip()
    assert stat and stat in brief
    assert "bin.dat" in brief

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


def test_flag_not_provided_exit2(repo, tmp_path):
    """不给 --questions 这个参数:退出 2、stderr 含「未提供」(#512 评审建议 2)。"""
    ticket_dir = tmp_path / "ticket_noflag"
    proc = run_pack(
        "--worktree", str(repo.wt), "--ticket-dir", str(ticket_dir),
        "--ticket", "512",
        "--context", write_slot(tmp_path, "c4.md", "上下文。\n"),
        "--evidence", write_slot(tmp_path, "e4.md", "证据。\n"),
    )
    assert proc.returncode == 2
    assert "--questions" in proc.stderr
    assert "未提供" in proc.stderr
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


def test_unreadable_slot_exit2(repo, tmp_path):
    """非 UTF-8 的槽文件:按「读不出」退出 2,不出堆栈(#512 评审建议 7)。"""
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\x80\x81\x82")
    ticket_dir = tmp_path / "ticket_unreadable"
    proc, _ = generate(repo, tmp_path, ticket_dir=ticket_dir, evidence=bad)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert "--evidence" in proc.stderr
    assert "读不出" in proc.stderr
    assert not ticket_dir.exists() or not any(ticket_dir.iterdir())


def test_placeholder_slot_exit2(repo, tmp_path):
    ticket_dir = tmp_path / "ticket_ph"
    proc, _ = generate(repo, tmp_path, ticket_dir=ticket_dir,
                       context="这张卡要解决什么:<<填这张卡要解决什么>>\n")
    assert proc.returncode == 2
    assert "--context" in proc.stderr
    assert "占位" in proc.stderr  # 钉住占位分支本身(文件存在且非空,只是没填完)
    assert not ticket_dir.exists() or not any(ticket_dir.iterdir())


def test_missing_ticket_dir_exit2(repo, tmp_path):
    """真生成时缺 --ticket-dir:走槽问题退出 2(#512 评审建议 4)。"""
    proc = run_pack(
        "--worktree", str(repo.wt), "--ticket", "512",
        "--context", write_slot(tmp_path, "c6.md", "上下文。\n"),
        "--evidence", write_slot(tmp_path, "e6.md", "证据。\n"),
        "--questions", write_slot(tmp_path, "q6.md", "问题。\n"),
    )
    assert proc.returncode == 2
    assert "--ticket-dir" in proc.stderr


def test_check_only_prints_slots_writes_nothing(repo, tmp_path):
    """--check-only 不需要 --ticket-dir 与槽文件,不写任何文件。"""
    proc = run_pack("--worktree", str(repo.wt), "--ticket", "512", "--check-only")
    assert proc.returncode == 0, proc.stderr
    # 基线打的是分叉点,且 master 前进句在场
    fork = fork_short_of(repo)
    tip = git("rev-parse", "--short", "origin/master", cwd=repo.wt).strip()
    assert f"基线 origin/master(分叉点): {fork}" in proc.stdout
    assert f"master 尖端: {tip}(分叉点之后多 1 个提交)" in proc.stdout
    assert "feature/pack" in proc.stdout
    n_files, added, deleted = expected_counts(repo)
    assert f"受管文件数: {n_files}(+{added} / -{deleted} 行)" in proc.stdout


def test_dirty_worktree_warns(repo, tmp_path):
    """工作树有未提交改动:stderr 告警 + 任务书带提示句;diff 口径不含它(建议 5)。"""
    stray = repo.wt / "stray.txt"
    stray.write_text("uncommitted\n", encoding="utf-8")
    try:
        ticket_dir = tmp_path / "ticket_dirty"
        proc, _ = generate(repo, tmp_path, ticket_dir=ticket_dir)
        assert proc.returncode == 0, proc.stderr
        assert "1 个未提交改动" in proc.stderr
        brief = (ticket_dir / "review-brief.md").read_text(encoding="utf-8")
        assert "工作树有 1 个未提交改动,不在 reviewed.diff 里" in brief
        n_files, added, deleted = expected_counts(repo)
        assert f"{n_files} 个受管文件(+{added} / -{deleted} 行)" in brief
    finally:
        stray.unlink()


def test_base_param_stacked_branch(repo, tmp_path):
    """--base 传父分支名:只算叠上去的提交,分叉点=父分支尖端,无「前进」句(建议 6)。"""
    wt2 = repo.root / "wt2"
    git("worktree", "add", "-b", "feature/stack", str(wt2), "feature/pack", cwd=repo.main)
    try:
        configure(wt2)
        (wt2 / "d.txt").write_text("stacked\n", encoding="utf-8")
        git("add", "-A", cwd=wt2)
        git("commit", "-m", "stack commit", cwd=wt2)
        ticket_dir = tmp_path / "ticket_base"
        proc = run_pack(
            "--worktree", str(wt2), "--ticket-dir", str(ticket_dir),
            "--ticket", "512", "--base", "feature/pack",
            "--context", write_slot(tmp_path, "c7.md", "上下文。\n"),
            "--evidence", write_slot(tmp_path, "e7.md", "证据。\n"),
            "--questions", write_slot(tmp_path, "q7.md", "问题。\n"),
        )
        assert proc.returncode == 0, proc.stderr
        brief = (ticket_dir / "review-brief.md").read_text(encoding="utf-8")
        assert "1 个提交" in brief
        assert "stack commit" in brief
        assert "1 个受管文件(+1 / -0 行)" in brief
        pack_tip = git("rev-parse", "--short", "feature/pack", cwd=repo.main).strip()
        assert f"基线 feature/pack `{pack_tip}`" in brief
        assert "之后" not in brief  # 分叉点=基线尖端,没有前进句
    finally:
        git("worktree", "remove", str(wt2), cwd=repo.main)
        git("branch", "-D", "feature/stack", cwd=repo.main)
