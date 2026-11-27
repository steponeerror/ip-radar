#!/usr/bin/env python3
"""review_pack.py — 评审任务书骨架生成器(#512,第四轮架构评审卡 34)。

为什么(#512 工单):每张票的评审任务书 review-brief.md 里,开头句、评审对象句、
输出格式节是逐字照抄的(18 份里「你没有 shell」17 份、输出格式节三份逐字全同),
而新教训句只传到 2 份——骨架收进本脚本当单一来源,三节人写内容读槽文件拼入。

用法:
    git fetch origin master        # 基线取 origin/master,先刷新
    python3 scripts/review_pack.py \
        --worktree .worktrees/<名> --ticket-dir <目录> --ticket <工单号> [--pr <PR号>] \
        --context <这张卡要解决什么.md> --evidence <门与证据.md> --questions <问题清单.md>

产出(写进 --ticket-dir):
    review-brief.md  评审任务书(自动槽位已填,三节为槽文件原文)
    reviewed.diff    git diff origin/master...HEAD 的原样字节

纪律:
    - 三个槽文件任一缺失、为空、或内容还有「<<填」占位 → 打印缺哪个,退出码 2,
      不写任何文件(校验全部在前、落盘全部在后;宁少算:半份任务书不发评审)。
    - --check-only 只打印自动槽位,不写文件(给主会话核对用)。
    - 只用标准库 + git 命令,不加第三方依赖。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_REF = "origin/master"
PLACEHOLDER = "<<填"  # 任务书模板的未填占位标记;生成时槽文件里不许残留

# 「输出格式」节逐字取自既有任务书的版本
# (docs/reports/2026-11-26-arch-r4-landing/491-卡7-A家族下载保证/review-brief.md,
# #512 任务书指定它为抄写母本;docs 嵌套仓不入主仓,故在此存常量副本)。
OUTPUT_FORMAT_SECTION = """## 输出格式

写到输出文件。开头一行结论,三选一:可直接合并 / 修后可合 / 要重做。然后分四节:必须改(每条:文件:行、问题、改法)、建议改、记一笔、你核过没问题的(逐条列)。每条都要有文件:行作证据;拿不准的写「拿不准」,不要猜。"""

MERGE_CHECKLIST_SECTION = """## 合并前清单

- 更新日志:Unreleased 对应节补中英各一条(条目缩进两个空格),中文在前英文在后。
- PR 正文:要自动关工单就写关闭词(如 `Closes #<工单号>`);不关的写明。
- CI:六个 job 全绿后再请人看。"""


def run_git(worktree: Path, *args: str, binary: bool = False):
    """在工作树的仓里跑一条 git 命令;失败打印 stderr 并退出 1(2 留给槽文件问题)。"""
    proc = subprocess.run(
        ["git", "-C", str(worktree), *args], capture_output=True
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        print(f"git {' '.join(args)} 失败:{detail}", file=sys.stderr)
        raise SystemExit(1)
    if binary:
        return proc.stdout
    return proc.stdout.decode("utf-8", "replace").strip()


def collect_auto_slots(worktree: Path) -> dict:
    """自动槽位一次算齐:分支、基线、提交清单、numstat 计数、diff 字节、路径、时间。"""
    branch = run_git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    base_short = run_git(worktree, "rev-parse", "--short", BASE_REF)
    main_checkout = Path(
        run_git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ).parent
    numstat = run_git(worktree, "diff", "--numstat", f"{BASE_REF}...HEAD")
    n_files = added = deleted = 0
    for line in numstat.splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        n_files += 1
        # 二进制文件的 numstat 两列是「-」:计入文件数,不计行数(宁少算)
        added += int(cols[0]) if cols[0].isdigit() else 0
        deleted += int(cols[1]) if cols[1].isdigit() else 0
    commits: list[tuple[str, str]] = []
    for line in run_git(
        worktree, "log", "--no-decorate", "--oneline", f"{BASE_REF}..HEAD"
    ).splitlines():
        if line.strip():
            sha, _, title = line.partition(" ")
            commits.append((sha, title.strip()))
    stat = run_git(worktree, "diff", "--stat", f"{BASE_REF}...HEAD")
    diff_bytes = run_git(worktree, "diff", f"{BASE_REF}...HEAD", binary=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "branch": branch,
        "base_short": base_short,
        "main_checkout": main_checkout,
        "worktree": worktree.resolve(),
        "commits": commits,
        "n_files": n_files,
        "added": added,
        "deleted": deleted,
        "stat": stat,
        "diff_bytes": diff_bytes,
        "now": now,
    }


def read_slot_file(path: Path | None, flag: str, label: str, problems: list[str]) -> str:
    """读一个槽文件;未给/缺失/为空/含未填占位都记入 problems(调用方统一退出 2)。"""
    if path is None:
        problems.append(f"{label}({flag})未提供")
        return ""
    if not path.is_file():
        problems.append(f"{label}({flag})文件不存在:{path}")
        return ""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        problems.append(f"{label}({flag})文件为空:{path}")
        return ""
    if PLACEHOLDER in text:
        problems.append(f"{label}({flag})内容还有未填占位「{PLACEHOLDER}」:{path}")
    return text


def render_brief(
    slots: dict,
    ticket: str,
    pr: str | None,
    context: str,
    evidence: str,
    questions: str,
) -> str:
    pr_part = f"PR #{pr}(草稿)," if pr else ""
    commit_lines = "\n".join(
        f"- `{sha}` {title}" for sha, title in slots["commits"]
    ) or "(基线上没有提交)"
    stat_block = slots["stat"] or "(diff 为空)"
    head = (
        f"# #{ticket} 评审任务书(分支 {slots['branch']})\n"
        "\n"
        f"本文件由 `scripts/review_pack.py` 生成(工单 #{ticket},"
        f"生成时间 {slots['now']})。骨架文案单一来源在该脚本;"
        "「这张卡要解决什么」「门与证据」「请回答的问题」三节分别是"
        " `--context` / `--evidence` / `--questions` 槽文件的原文。\n"
        "\n"
        "你没有 shell:直接读文件。改后的文件在工作树 "
        f"`{slots['worktree']}`,改前的在主检出 `{slots['main_checkout']}`(master)。"
        "主检出下有多个工作树时,codegraph 可能把工作树里的同名文件当当前源码返回,"
        "行号以你读到的文件为准。\n"
        "\n"
        "## 评审对象\n"
        "\n"
        f"评审对象:{pr_part}分支 `{slots['branch']}`"
        f"(基线 master `{slots['base_short']}`),{len(slots['commits'])} 个提交,"
        f"{slots['n_files']} 个受管文件(+{slots['added']} / -{slots['deleted']} 行)。"
        f"同目录的 `reviewed.diff` 是完整改动"
        f"(`git diff {BASE_REF}...HEAD` 原样字节)。\n"
        "\n"
        "### 提交清单\n"
        "\n"
        f"{commit_lines}\n"
        "\n"
        "### diff --stat\n"
        "\n"
        "```text\n"
        f"{stat_block}\n"
        "```\n"
    )
    parts = [
        head,
        "## 这张卡要解决什么\n\n" + context.strip("\n"),
        "## 门与证据(实现者跑的;你核对说法和代码是否一致)\n\n" + evidence.strip("\n"),
        "## 请回答的问题\n\n" + questions.strip("\n"),
        OUTPUT_FORMAT_SECTION,
        MERGE_CHECKLIST_SECTION,
    ]
    return "\n\n".join(parts) + "\n"


def print_check_only(ticket: str, pr: str | None, slots: dict) -> None:
    """--check-only:只打印自动槽位,不读槽文件、不写任何文件。"""
    print(f"工单号: {ticket}")
    print(f"PR 号: {('#' + pr) if pr else '(未给)'}")
    print(f"分支: {slots['branch']}")
    print(f"基线 {BASE_REF}: {slots['base_short']}")
    print(f"工作树: {slots['worktree']}")
    print(f"主检出: {slots['main_checkout']}")
    print(f"受管文件数: {slots['n_files']}(+{slots['added']} / -{slots['deleted']} 行)")
    print("提交清单:")
    for sha, title in slots["commits"]:
        print(f"  - {sha} {title}")
    print(f"生成时间(UTC): {slots['now']}")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成评审任务书骨架 review-brief.md(基线 origin/master,头为工作树 HEAD)",
    )
    parser.add_argument("--worktree", required=True, help="工作树目录(在其中跑 git 取槽位与 diff)")
    parser.add_argument("--ticket-dir", required=True, help="输出目录(写 review-brief.md 与 reviewed.diff)")
    parser.add_argument("--ticket", required=True, help="工单号(如 512)")
    parser.add_argument("--pr", default=None, help="PR 号;给了才在评审对象句里出现")
    # 三个槽文件在 argparse 层不 required:--check-only 不需要它们;
    # 真生成时缺任何一个 → 槽问题校验统一报,退出码 2。
    parser.add_argument("--context", default=None, help="「这张卡要解决什么」槽文件(md)")
    parser.add_argument("--evidence", default=None, help="「门与证据」槽文件(md)")
    parser.add_argument("--questions", default=None, help="「请回答的问题」槽文件(md)")
    parser.add_argument(
        "--check-only", action="store_true",
        help="只打印自动槽位,不读槽文件、不写任何文件",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    worktree = Path(args.worktree).resolve()
    if not worktree.is_dir():
        print(f"--worktree 目录不存在:{worktree}", file=sys.stderr)
        return 1
    slots = collect_auto_slots(worktree)
    if args.check_only:
        print_check_only(args.ticket, args.pr, slots)
        return 0
    # 校验全部在前:任一槽有问题就整体不落盘(退出码 2)
    problems: list[str] = []
    context = read_slot_file(
        Path(args.context) if args.context else None,
        "--context", "「这张卡要解决什么」", problems)
    evidence = read_slot_file(
        Path(args.evidence) if args.evidence else None,
        "--evidence", "「门与证据」", problems)
    questions = read_slot_file(
        Path(args.questions) if args.questions else None,
        "--questions", "「请回答的问题」", problems)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        print(f"共 {len(problems)} 个槽文件问题,不写任何文件", file=sys.stderr)
        return 2
    brief = render_brief(slots, args.ticket, args.pr, context, evidence, questions)
    ticket_dir = Path(args.ticket_dir)
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / "reviewed.diff").write_bytes(slots["diff_bytes"])
    (ticket_dir / "review-brief.md").write_text(brief, encoding="utf-8")
    print(f"已写出 {ticket_dir / 'review-brief.md'}")
    print(f"已写出 {ticket_dir / 'reviewed.diff'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
