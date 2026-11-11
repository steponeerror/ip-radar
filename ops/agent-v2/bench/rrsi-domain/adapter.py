# 票 #325 [rrsi-a]:ip-radar 盲测重发现基准的 RRSI 域适配器。
# Apache-2.0 RRSI(google-research/rrsi)以 domains/<name>/adapter.py 导出 DOMAIN 实例
# 接线;本文件入仓于 ops/agent-v2/bench/rrsi-domain/,由 scripts/bootstrap-rrsi.sh 拷进
# dev/rrsi/domains/ipradar/(dev/ 不入 git,放置规范 2026-10-28)。
#
# 域语义(裁决链:#322 票面 + docs 仓 research/2026-11-07-rediscover-bench-spec.md + ADR 0020):
#   任务 x = 考题源(61 roster − 8 免考 = 53;ops/agent-v2/bench/exam-rules.json 免考面);
#   trial  = 一次盲搜轮(ops/agent-v2/bench/run-bench.mjs,沙箱 dev/bench-rediscover/<roundId>/);
#   奖励 r(x, τ) = score.mjs 四层匹配命中该源 = 1,未命中 = 0(逐源 0/1);
#   门红轮 = 该轮零召回(gate-red.json 标记:模型侧引用不合规被 G_* 拒=适应度信号,
#   非 infra 崩溃——rrsi 把崩溃标 infra 等人手 reevaluate,演化断链;#322 首跑判例);
#   劈分   = data/split.jsonl 冻结件(40 演化/13 留出,tests/rrsi-split.test.mjs 钉不变式);
#   S      = 召回率。#322 验收四行数 = H0/终版 × 演化/留出。
#
# 本票(#325)红线:不跑任何真实搜索轮——run() 缺省 faux(--fixtures 罐装,零网络零花费);
# real 是 #322 的花钱面,须显式 env IPRADAR_BENCH_MODE=real 才放行(模型面缺省=四角色同款 glm-5.3-flash,R4 裁决)。
#
# 三护栏(golden + v2 全套 + leak gate;过不了不进花钱评估):smoke() 全跑,run() 复跑
# 落 guards.json 回执,score() 载入 extra,guards() 非补偿执法——回执缺失=不可接受。
# 冻结门(#327):NEEDS.md(考题宇宙)与验证面(golden/selftest*/fixtures/v2-tests
# +leak gate 执法件 leak-check.mjs/exam-rules.json,Standards P1 修批)两道 git diff
# 对 incumbent 分支必为空——评估器不许候选改;演化可编面另表
# EDIT_ALLOWLIST(策略面 47 文件,#327 Q1 推翻 #322 R5 全放开)。
import fnmatch
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent))  # RRSI 仓根(domains/<name>/ → 仓根)
sys.path.insert(0, str(HERE))                      # 域目录(critic_needles 同目录模块)
from rrsi.domain import Domain       # noqa: E402
from rrsi.evaluate import TaskResult  # noqa: E402

CFG = json.loads((HERE / "rrsi.json").read_text())

# ── 取数面定位 ──────────────────────────────────────────────────────────────
# ip-radar 主检出:答案真源(backend roster)与 v2 node_modules 家都在主检出,不在
# dev/rrsi 克隆里。解析序:env IPRADAR_REPO → 自本文件向上找同时含 ops/agent-v2 与
# backend 的目录(入仓源位置 ops/agent-v2/bench/rrsi-domain/ 与拷贝位置 dev/rrsi/
# domains/ipradar/、RRSI worktree 内拷贝三种摆位都能命中)。
def _find_ipradar_repo() -> Path:
    env = os.environ.get("IPRADAR_REPO")
    if env:
        return Path(env).resolve()
    d = HERE
    for _ in range(12):
        d = d.parent
        if (d / "ops" / "agent-v2").is_dir() and (d / "backend").is_dir():
            return d.resolve()
    raise SystemExit("ipradar 仓定位失败:设 env IPRADAR_REPO=<ip-radar 主检出绝对路径>")

IPRADAR = _find_ipradar_repo()
# worktree 判例(AGENTS.md 2026-11-03):worktree 无 venv,backend 解释器用主检出绝对路径
BENCH_PYTHON = os.environ.get("IPRADAR_BENCH_PYTHON",
                              "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python")

# ── 演化可编面白名单(票 #327 Q1 裁定 2026-11-08;推翻 #322 R5「开放面 v1+v2 全放开」)──
# 主仓=声明与单源;dev/rrsi Workspace 以 getattr(domain, "edit_allowlist", None) 消费
# (read/edit/write 三动作同表,越名单即拒)。fnmatch 语义:* 跨目录分隔符;路径相对
# harness 根。构成=策略面 47 文件(#327 原裁 43;#333 P2a 加源基准器 add-domain +4:
# gen-universe/build-sandbox/score 三 .mjs + keyless-rules.json。调研笔记
# docs/notes/ops-tree-as-harness-2026-11-08.md:验证/环境/文档面 72% 是演化不该碰的):
#   ops/agent/pipeline/** 11 + ops/agent/prompts/** 9
#   + ops/agent-v2/{tools,tasks,bench}/** 25 + ops/agent/{agent.mjs,models.mjs} 2
# 其余(v1 根散件/验证面/环境面/文档面)一律只读;验证面另有 _guardrails 冻结门,
# 不靠本表拒绝。名单外输入 fail-closed(edit_allowed 返回 False)。
# 双匹配器互指(Spec 轴 P2-1):运行时真身是 dev/rrsi rrsi/propose.py _allowed(同一张
# 表消费;语义微差:彼侧多剥 harness 目录名前缀、少反斜杠归一,分歧方向均为拒;改 glob
# 时两侧同改)。
EDIT_ALLOWLIST = (
    "ops/agent/pipeline/**",
    "ops/agent/prompts/**",
    "ops/agent-v2/tools/**",
    "ops/agent-v2/tasks/**",
    "ops/agent-v2/bench/**",
    "ops/agent/agent.mjs",
    "ops/agent/models.mjs",
)

def edit_allowed(rel) -> bool:
    """路径(相对 harness 根)是否落在演化可编白名单内;反斜杠归一 /,fnmatch 语义,
    名单外 fail-closed。"""
    r = str(rel).replace("\\", "/").lstrip("/")
    return any(fnmatch.fnmatch(r, p) for p in EDIT_ALLOWLIST)

# ── 冻结劈分(答案分发面;名单漂移由 tests/rrsi-split.test.mjs 红)────────────
def _load_split():
    lines = (HERE / "data" / "split.jsonl").read_text().splitlines()
    rows = [json.loads(l) for l in lines[1:] if l.strip()]
    meta = json.loads(lines[0])
    assert meta["frozen"] is True, "split.jsonl 未冻结:重劈须重走 #322 裁决"
    return meta, rows

_SPLIT_META, _ROWS = _load_split()

# ── 考题针(critic_patterns):构造单源在 critic_needles.py(#325 F1 抽出,标准库自足 ──
# 可测)。数据面与 bench/leak-check.mjs buildNeedles 同源 = 同一份 split.jsonl + 同一
# 折叠规则(名字/host/≥3 段剥一段父域);匹配面各异:leak 闸折行做子串,critic.py
# precheck 对【原始 diff】re.search(无 MULTILINE 无行折叠)——针形见 critic_needles.py。
from critic_needles import buildCriticPatterns  # noqa: E402

def _ensure_backend_link(root: Path) -> None:
    """harness/backend → 主检出 backend 的符号链接 + git exclude 双保险。
    golden 健康例的 matrix/锚探针 spawn 在 cwd=<ROOT>/backend 跑 `-m ipdb._eval`
    (ops/agent/tools/measurement.mjs:59),vendored harness 缺 backend/ 会 ENOENT;
    链到主检出 backend=与主检出 golden 同读数面(只读探针,零漂移)。exclude
    (common dir,全 worktree 共享)保 symlink 绝不进候选提交(commit_path 的
    `git add -A` 遵 exclude)。"""
    link = (root / "domains" / "ipradar" / "harness") / "backend"
    if not os.path.lexists(link):
        link.symlink_to(IPRADAR / "backend")
    r = _run(["git", "rev-parse", "--git-common-dir"], cwd=root, check=False)
    if r.returncode != 0:
        return
    common = Path(r.stdout.strip())
    if not common.is_absolute():
        common = root / common
    excl = common / "info" / "exclude"
    excl.parent.mkdir(parents=True, exist_ok=True)
    marker = "domains/ipradar/harness/backend"
    body = excl.read_text() if excl.exists() else ""
    if marker not in body.splitlines():
        with open(excl, "a") as f:
            f.write(f"\n# rrsi ipradar 域:候选 worktree 的 backend 探针链接(绝不入提交)\n{marker}\n")


def _run(cmd, cwd, env=None, timeout=1800, check=True, log=None):
    """跑子进程;log=Path 时 stdout/stderr 追加落盘(留痕)。"""
    e = {**os.environ, **(env or {})}
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as lf:
            r = subprocess.run(cmd, cwd=str(cwd), env=e, stdout=lf,
                               stderr=subprocess.STDOUT, timeout=timeout)
    else:
        r = subprocess.run(cmd, cwd=str(cwd), env=e, capture_output=True,
                           text=True, timeout=timeout)
    if check and r.returncode != 0:
        tail = "" if log is not None else (r.stdout + r.stderr)[-1500:]
        raise RuntimeError(f"{cmd[:3]}... rc={r.returncode} in {cwd}\n{tail}")
    return r

def _last_envelope(log_path: Path):
    """log 尾部最后一个 JSON 错误信封(run-bench CLI stdout 末行,ENVELOPE.md 冻结面)。
    日志追加写,取末尾最后一个含 error 键的 JSON 行;无则 None。"""
    try:
        lines = Path(log_path).read_text(errors="replace").splitlines()
    except OSError:
        return None
    for ln in reversed(lines):
        s = ln.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                v = json.loads(s)
            except json.JSONDecodeError:
                continue
            if isinstance(v, dict) and "error" in v:
                return v
    return None


def _is_gate_red(envelope) -> bool:
    """门红判:信封 error.message 以 GATE: 开头(discover-round.mjs:226/307 单源拼
    `GATE:<门名>:` 前缀)=模型侧产物被拒,非 infra。"""
    msg = (envelope or {}).get("error", {}).get("message", "")
    return isinstance(msg, str) and msg.startswith("GATE:")


def _harness_tree_id(root: Path) -> str:
    """候选 worktree HEAD 的 harness 子树 tree id(domains/ipradar/harness)——同代码同 id。
    沙箱根按它分目录:重跑同一化身=复用沙箱走 durable replay(零新模型调用);换了化身
    (harness 被演化编辑)=新沙箱,旧轮不会错挂(#322 首跑后续:heldout 重评须随冠军新代码
    重跑,不能重放旧冠军的轮)。10 位十六进制。"""
    r = _run(["git", "rev-parse", "HEAD:domains/ipradar/harness"], cwd=root)
    return r.stdout.strip()[:10]


def _bench_root_for(runs_dir: Path, job: str) -> Path:
    """job → 沙箱根:优先 .jobmap 指针(_bench_round 写);缺席兑底旧路径(旧跑/smoke)。"""
    jm = Path(runs_dir) / "bench" / ".jobmap" / job
    if jm.exists():
        return Path(jm.read_text().strip())
    return Path(runs_dir) / "bench" / job


def _round_id(job: str, trial: int = 0) -> str:
    """job → 确定性轮 id(形状律 YYYY-MM-DD-HHMM-discover(-r\\d+);同 job 重跑复用同
    沙箱=run-bench resume 语义)。trial 序编进字节序,保 k>1 时各试次独立沙箱。"""
    n = int.from_bytes(f"{job}#t{trial}".encode(), "big")
    return f"2000-01-01-0000-discover-r{n}"

def _artifacts_dir(runs_dir: Path, job: str, k: int) -> Path:
    """score.mjs 的工件目录:<benchRoot>/<roundId>/rounds/<roundId>/(run-bench 落件形状,
    tests/bench-round.test.mjs CLI 冒烟钉)。k>1 取末试次(打分输入=最终轮)。沙箱根经
    _bench_root_for 解析(化身后缀 + jobmap,2026-11-08 判例)。"""
    rid = _round_id(job, k - 1)
    return _bench_root_for(Path(runs_dir), job) / rid / "rounds" / rid

def _roster_dump(runs_dir: Path) -> Path:
    """roster dump 单源取数:`python -m ipdb._registry --roster`(score/leak 同源);
    落 <runs>/roster.txt 复用。答案真源=主检出 backend,不随候选漂移。"""
    p = Path(runs_dir) / "roster.txt"
    if not p.exists():
        r = _run([BENCH_PYTHON, "-m", "ipdb._registry", "--roster"],
                 cwd=IPRADAR / "backend")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(r.stdout)
    return p

# ── 冻结门(#327:两道门同律同机;git pathspec 语义实测 2026-11-08:* 跨目录、目录递归、
# 对 ref 的 diff 工作树+已提交改动均可见、pathspec 无匹配 rc0 不误报)──────────────
NEEDS_GATE_PATHS = ("domains/ipradar/harness/NEEDS.md",)
# 验证面=给自己打分的面(golden 基线 / selftest / pipeline+precedents 夹具 / v2 测试)。
# Standards P1 修批(#327,评审 1e9e66fb):验证面四类之外,leak gate 自身执法件同律
# 冻结——检查器 leak-check.mjs(护栏③在候选 worktree 内跑候选副本,可编不改门=
# 候选恒零命中后往 prompts 注考题名照拿回执)+ exam-rules.json(exempt 免考名单=
# 打分面数据:score.mjs 考题分母由它派生,名单载体留在被告可编面=门上留缝)。
# 「给自己打分的面」含给自己站岗的面。
VERIFICATION_GATE_PATHS = (
    "domains/ipradar/harness/ops/agent/golden",
    "domains/ipradar/harness/ops/agent/selftest*",
    "domains/ipradar/harness/ops/agent/fixtures",
    "domains/ipradar/harness/ops/agent-v2/tests",
    "domains/ipradar/harness/ops/agent-v2/bench/leak-check.mjs",
    "domains/ipradar/harness/ops/agent-v2/bench/exam-rules.json",
)

def _frozen(root: Path, paths: tuple[str, ...]) -> bool:
    """git diff --quiet evolve/ipradar -- <paths>:True=面未被候选改动(冻结完好)。
    工作树与已提交(commit_path)改动对 incumbent 分支均可见;红由调用方判语义。"""
    r = _run(["git", "diff", "--quiet", "evolve/ipradar", "--", *paths],
             cwd=root, check=False)
    return r.returncode == 0

def _guardrails(root: Path, runs_dir: Path, log_dir: Path) -> dict:
    """三护栏(票面:golden + v2 全套 + leak gate;候选 worktree 内跑,主检出 venv 判例)。
    任一红即整门红——过不了的候选不进花钱评估(smoke 拦)也不可接受(guards 拦)。"""
    h = (root / "domains" / "ipradar" / "harness").resolve()
    agent, agent_v2 = h / "ops" / "agent", h / "ops" / "agent-v2"
    out = {}
    _ensure_backend_link(root)
    # node_modules 幂等装配(候选 worktree 无 untracked;判改动可装=候选自身能力)
    for d in (agent, agent_v2):
        if not (d / "node_modules").is_dir():
            _run(["npm", "ci", "--no-fund", "--no-audit"], cwd=d,
                 log=log_dir / "npm-ci.log", timeout=900)
    # ① golden:ops/agent/golden/run-golden.mjs(faux 层零花费,真 agent 回路对拍)
    _run(["node", "golden/run-golden.mjs"], cwd=agent, log=log_dir / "golden.log")
    out["golden"] = True
    # ② v2 全套:npm test(基线 97 面 + 劈分/域结构不变式)
    _run(["npm", "test"], cwd=agent_v2, log=log_dir / "v2-test.log")
    out["v2_test"] = True
    # NEEDS.md 冻结门:考题宇宙输入面(bench SCAN 真面读它;真台账本就合法提及已交付
    # 源名,故不用 leak 针扫原文,而用 git diff 对 incumbent 冻结——候选增改一行即红)
    if not _frozen(root, NEEDS_GATE_PATHS):
        raise RuntimeError("NEEDS.md 被候选改动:考题宇宙输入面冻结(bench 沙箱读它作"
                           "候选宇宙,改它=注入考题提示)")
    out["needs_frozen"] = True
    # 验证面冻结门(#327 Q2 方案 a):golden/selftest*/fixtures/v2-tests 照常 vendor,
    # 但对 incumbent 的 git diff 必须为空——护栏在候选 worktree 内跑,测试面可编=
    # 候选可改给自己打分的分(test-edit 洞);从「靠模型自觉」变「靠结构」。NEEDS 同律。
    if not _frozen(root, VERIFICATION_GATE_PATHS):
        raise RuntimeError("验证面被候选改动:评估器冻结(golden/selftest*/fixtures/"
                           "v2-tests+leak gate 执法件(leak-check.mjs/exam-rules.json)"
                           "对 evolve/ipradar 的 git diff 须为空,票 #327 Q2+Standards P1)")
    out["verification_frozen"] = True
    # ③ leak gate:默认面 exit 0(考题针零命中;行级豁免「禁词引用:原因」判例 #308)。
    # roster 经 --roster-file 注入(worktree 无 backend/,spawn 面断)
    _run(["node", "bench/leak-check.mjs", "--roster-file",
          str(_roster_dump(runs_dir))], cwd=agent_v2, log=log_dir / "leak.log")
    out["leak_gate"] = True
    return out


class IpRadarDomain(Domain):
    name = "ipradar"
    # harness=发现管线两目录镜像(ops/agent + ops/agent-v2,#322 裁决;#327 Q2 起验证面
    # 照常 vendor 但落冻结门)。框架只认单目录 → bootstrap 把两目录 vendored 进
    # harness/ops/,harness 即「仓根镜像」单目录;PATTERNS.md 限定免碰面(真实轮路径
    # 零漂移红线)。tree hash 只盖 vendoring 面,域文件/RRSI 核心的提交不误报为
    # harness 变化(gitops.py 语义)。
    harness_path = "harness"
    # 演化可编面白名单(#327 Q1,推翻 #322 R5 全放开):策略面 47 文件,read/edit/
    # write 三动作同表,名单外只读;dev/rrsi Workspace 以 getattr 消费本属性,
    # 语义/构成见 EDIT_ALLOWLIST 注释。
    edit_allowlist = EDIT_ALLOWLIST
    source_exts = {".py", ".txt", ".md", ".json", ".mjs"}
    critic_patterns = buildCriticPatterns(_ROWS)
    component_signals = [
        ("prompt",        [r"prompts[/\\]", r"shortlist", r"SYSTEM_PROMPT", r"提示词"]),
        ("scan",          [r"bench[/\\]scan\.mjs", r"candidate_universe", r"候选宇宙"]),
        ("shortlist",     [r"discover-round\.mjs", r"d2-shortlist", r"SHORTLIST"]),
        ("budget",        [r"budget-guard", r"admitRound", r"月帽"]),
        ("model_face",    [r"models\.mjs", r"glm-", r"zai"]),
        ("scoring",       [r"bench[/\\]score\.mjs", r"buildAnswerTable", r"四层"]),
        ("leak_gate",     [r"leak-check", r"buildNeedles", r"禁词引用"]),
        ("scaffold",      [r"entry\.mjs", r"registry\.mjs", r"checkpoint"]),
    ]
    briefs = {
        "analyst": (
            "域:ip-radar 情报源盲测重发现基准。一次 trial = 发现管线一轮盲搜"
            "(SCAN→SHORTLIST→CLOSE 截断相位,沙箱 opsRoot,绝不触碰真实运营面);"
            "每任务的证据 = d2-shortlist.json 候选 + score.mjs 四层匹配报告"
            "(完整 URL→发布者域名→名字归一→别名表)。未命中源按「无证据≠清白」"
            "读法分析:候选全空=检索面问题;候选在场但层落空=归一/域名/别名层问题;"
            "免考源命中(exemptHits)只留痕不入分。类别三轴:threat/geo_asn/asset。"
        ),
        "digester": (
            "摘要每源任务:类别、命中层(L1-L4)、经由候选与渠道、未命中时的候选邻域。"
            "重点标出跨源共模(如 github 家族按 repo 路径段区分的误并、域名归一差一步)。"
        ),
        "proposer": (
            "域:ip-radar 盲测重发现基准——用基准轮(沙箱,faux 或真实 GLM)度量发现管线的"
            "搜索与召回能力,奖励=逐源 0/1 召回。开放面=策略面 47 文件白名单(七条 glob:"
            "pipeline/prompts/v2 tools+tasks+bench/v1 入口与模型),名单外一律只读,"
            "验证面另有冻结门;约束读 PATTERNS.md(零漂移红线:真实轮路径行为字节不变,"
            "golden 钉;考题名/域名禁入提示词与代码;编辑预算须可归因)。提升召回的"
            "合法杠杆:候选宇宙覆盖、检索词策略、短名单聚合与去重、四层匹配上下游的"
            "对齐——不是把答案写进提示词。"
        ),
        "critic": (
            "域:ip-radar 盲测重发现基准。审查候选 diff:①考题泄漏(critic_patterns = 53 源"
            "名字/域名原文针,环视形(不卡整段、词边界内即命中);数据面与 leak gate 同源);②真实轮零漂移红线破坏(golden/护栏会红,直接"
            "拒绝);③答案硬编码/特判(对具体源名打补丁=benchmark 专属拟合);④沙箱纪律"
            "(沙箱外落件/读真实运营面台账)。宁严勿松。"
        ),
    }

    # ---- task sets ---------------------------------------------------------
    def evolve_ids(self) -> list[str]:
        return [r["name"] for r in _ROWS if r["set"] == "evolve"]

    def heldout_ids(self) -> list[str]:
        return [r["name"] for r in _ROWS if r["set"] == "heldout"]

    def smoke_ids(self, incumbent_per_task=None) -> list[str]:
        # 三类别各取首名(轻量活性面;faux 轮零网络,ids 只影响罐装候选量)
        ids, seen = [], set()
        for r in _ROWS:
            if r["set"] == "evolve" and r["category"] not in seen:
                ids.append(r["name"])
                seen.add(r["category"])
        return ids

    # ---- Evaluate ----------------------------------------------------------
    def _bench_round(self, root: Path, runs_dir: Path, job: str, ids: list[str], k: int,
                     log_prefix: str) -> Path:
        """起 k 个试次的 bench 轮(faux 缺省;real=#322 花钱面,须显式 env)。返回工件目录。"""
        harness = (root / "domains" / "ipradar" / "harness").resolve()
        agent_v2 = harness / "ops" / "agent-v2"
        mode = os.environ.get("IPRADAR_BENCH_MODE", "faux")
        log_dir = Path(runs_dir) / "logs"
        # 环境先于首轮:backend 探针链接 + node_modules 幂等装配(baseline 的 wt/incumbent
        # 是新 worktree,不预先装配首轮就 ERR_MODULE_NOT_FOUND——#322 首跑踩坑二补入)
        _ensure_backend_link(root)
        for _d in (harness / "ops" / "agent", harness / "ops" / "agent-v2"):
            if not (_d / "node_modules").is_dir():
                _run(["npm", "ci", "--no-fund", "--no-audit"], cwd=_d,
                     log=log_dir / "npm-ci.log", timeout=900)
        sha = _harness_tree_id(root)
        bench_root = Path(runs_dir) / "bench" / f"{job}-{sha}"
        # jobmap 先写后跑:score/load_trial 经 _bench_root_for 找根;轮中崩溃也留指路。
        jm = Path(runs_dir) / "bench" / ".jobmap" / job
        jm.parent.mkdir(parents=True, exist_ok=True)
        jm.write_text(str(bench_root) + "\n")
        env = {"OPS_BENCH_ROOT": str(bench_root),
               # DOCS_ROOT 防御性指沙箱(v2 测试同律:真实 docs 树零触碰)
               "DOCS_ROOT": str(Path(runs_dir) / "docs-ro" / job)}
        flags = []
        if mode == "real":
            # #322 R4 裁决:四角色(含冻结搜索策略)全 glm-5.3-flash——与生产 discover 的
            # glm-5.3 不同面,跨模型迁移有论文先例;env IPRADAR_BENCH_MODEL 可覆盖复裁。
            flags += ["--model", os.environ.get("IPRADAR_BENCH_MODEL",
                                                "zai-coding-cn/glm-5.3-flash")]
        else:
            flags += ["--fixtures", str(harness / "ops" / "agent" / "fixtures" / "pipeline")]
        for trial in range(k):
            rid = _round_id(job, trial)
            logf = log_dir / f"{log_prefix or job}.log"
            r = _run(["node", "bench/run-bench.mjs", rid, *flags], cwd=agent_v2,
                     env=env, log=logf, check=False)
            if r.returncode == 0:
                continue
            # 门红=模型侧引用不合规被 G_* 拒(适应度信号):落 gate-red.json 标记计 0 分续跑,
            # 不炸评估(rrsi 把崩溃标 infra 等人手 reevaluate,演化断链);非门红面才 raise。
            envelope = _last_envelope(logf)
            if _is_gate_red(envelope):
                red = Path(runs_dir) / "bench" / job / rid / "rounds" / rid / "gate-red.json"
                red.parent.mkdir(parents=True, exist_ok=True)
                red.write_text(json.dumps({"code": "gate_red", "envelope": envelope},
                                          ensure_ascii=False, indent=1) + "\n")
                continue
            tail = ""
            try:
                tail = logf.read_text(errors="replace")[-1500:]
            except OSError:
                pass
            raise RuntimeError(
                f"node bench/run-bench.mjs {rid} rc={r.returncode} in {agent_v2}\n{tail}")
        return _artifacts_dir(runs_dir, job, k)

    def run(self, root, runs_dir, job, ids, k, log_prefix=""):
        root, runs_dir = Path(root), Path(runs_dir)
        # jobs/<job> 目录预建(上游 loop.Run 只建到 jobs/ 一层,EvalResult.save 不 mkdir——
        # #322 首跑判例:基准轮全绿后在 ev.save 栽 FileNotFoundError)。
        (runs_dir / "jobs" / job).mkdir(parents=True, exist_ok=True)
        art = self._bench_round(root, runs_dir, job, ids, k, log_prefix)
        # 三护栏复跑落回执:score 载入 extra,guards 非补偿执法(回执缺失=不可接受)。
        self._write_guards_receipt(root, runs_dir, job, art)

    def _write_guards_receipt(self, root: Path, runs_dir: Path, job: str, art: Path):
        g = _guardrails(root, runs_dir, Path(runs_dir) / "logs" / "guards" / job)
        art.mkdir(parents=True, exist_ok=True)
        (art / "guards.json").write_text(json.dumps(g, ensure_ascii=False, indent=1))

    def score(self, runs_dir, job, ids, k):
        art = _artifacts_dir(Path(runs_dir), job, k)
        # 门红轮=零召回(轮产物被拒,无 admissible 短清单;宁拒勿假)。k>1 时标记只落
        # 被拒试次目录,本分支覆盖末试次被拒(rrsi.json k=1);guards 回执照常载入。
        red = art / "gate-red.json"
        guards_receipt = None
        gp = art / "guards.json"
        if gp.exists():
            guards_receipt = json.loads(gp.read_text())
        if red.exists():
            env = json.loads(red.read_text())
            msg = str(env.get("envelope", {}).get("error", {}).get("message", ""))[:200]
            report_md = art / "report.md"
            report_md.write_text(
                "# gate red(轮产物被拒,计零召回)\n\n" + json.dumps(env, ensure_ascii=False, indent=1) + "\n")
            per = {t: TaskResult(rewards=[0.0] * k, tokens=[None] * k, missing=0,
                                 extra={"gate_red": True}) for t in ids}
            extra = {"recall": {"found": 0, "total": len(ids), "pct": 0.0},
                     "unfound": list(ids), "new_candidates": 0, "gate_red": msg,
                     "guards": guards_receipt,
                     "guards_ok": bool(guards_receipt and all(guards_receipt.values())),
                     "report_md": str(report_md)}
            return per, extra
        # score.mjs:答案表机械派生(主检出 backend roster,候选不可染指)+ 确定性门
        log = Path(runs_dir) / "logs" / f"{job}-score.log"
        _run(["node", "bench/score.mjs", str(art), "--python", BENCH_PYTHON,
              "--backend", str(IPRADAR / "backend")],
             cwd=IPRADAR / "ops" / "agent-v2", log=log)
        report = json.loads((art / "report.json").read_text())
        found = {f["answer"]: f for f in report.get("found", [])}
        guards_receipt = None
        gp = art / "guards.json"
        if gp.exists():
            guards_receipt = json.loads(gp.read_text())
        per = {}
        for t in ids:
            f = found.get(t)
            per[t] = TaskResult(
                rewards=[1.0 if f else 0.0] * k,
                tokens=[None] * k,
                missing=0,
                extra={} if not f else {"layer": f["layer"],
                                        "via": f["via"]["name"]},
            )
        extra = {
            "recall": report["recall"],
            "unfound": [u["name"] for u in report.get("unfound", [])],
            "new_candidates": len(report.get("newCandidates", [])),
            "guards": guards_receipt,
            "guards_ok": bool(guards_receipt and all(guards_receipt.values())),
            "report_md": str(art / "report.md"),
        }
        return per, extra

    def guards(self, incumbent, candidate) -> list[str]:
        out = []
        g = (candidate.extra or {}).get("guards") or {}
        for leg in ("golden", "v2_test", "leak_gate", "needs_frozen", "verification_frozen"):
            if g.get(leg) is not True:
                out.append(f"guardrail {leg} has no passing receipt "
                           f"(三护栏+冻结面(NEEDS.md/验证面)全过才可接受,票 #325/#327)")
        return out

    # ---- evidence ----------------------------------------------------------
    def load_trial(self, runs_dir, job, task_id, trial):
        art = _artifacts_dir(Path(runs_dir), job, trial + 1)
        report = json.loads((art / "report.json").read_text())
        row = next((r for r in _ROWS if r["name"] == task_id), {})
        f = next((x for x in report.get("found", []) if x["answer"] == task_id), None)
        md = (art / "report.md").read_text() if (art / "report.md").exists() else ""
        return {"task": {"id": task_id, "category": row.get("category"),
                         "host": row.get("host")},
                "found": f, "report_md": md, "recall": report.get("recall"),
                "new_candidates": report.get("newCandidates", []),
                "trial": trial, "job": job}

    def render_trace(self, rec, detail=False):
        t, f = rec.get("task") or {}, rec.get("found")
        head = (f"{t.get('id')} [{t.get('category')}] host={t.get('host')} | "
                f"{'命中 L%d via %s' % (f['layer'], f['via']['name']) if f else '未搜到'}"
                f" | 召回 {rec.get('recall')}")
        if not detail:
            return head
        body = rec.get("report_md") or ""
        return head + "\n" + body[:4000]

    def task_row(self, task_id, rec, tr):
        t, f = rec.get("task") or {}, rec.get("found")
        hit = f"hit L{f['layer']} via {f['via']['name']}" if f else "MISS"
        return (f"{task_id} | {t.get('category')} | {hit} | mean={tr.mean:.2f} | "
                f"new_cands={len(rec.get('new_candidates') or [])}")

    # ---- gates -------------------------------------------------------------
    def smoke(self, root, runs_dir, job, ids):
        root, runs_dir = Path(root), Path(runs_dir)
        try:
            g = _guardrails(root, runs_dir, Path(runs_dir) / "logs" / "smoke" / job)
        except Exception as e:  # noqa: BLE001
            return False, {"stage": "guardrails", "err": repr(e)[:1200]}
        try:
            art = self._bench_round(root, runs_dir, job, ids, 1, job)
            self._write_guards_receipt(root, runs_dir, job, art)
            per, extra = self.score(runs_dir, job, ids, 1)
        except Exception as e:  # noqa: BLE001
            return False, {"stage": "faux_round", "err": repr(e)[:1200]}
        missing = sum(tr.missing for tr in per.values())
        ok = missing == 0 and (art / "report.json").exists() and extra["guards_ok"]
        return ok, {"stage": "done", "smoke_ids": ids, "missing": missing,
                    "recall": extra["recall"], "guards": g,
                    "report": str(art / "report.md")}


DOMAIN = IpRadarDomain()

# ── GLM 垫片(rrsi 核心 llm.py 原生只认 AnthropicVertex;四角色 GLM 面经此接线)──
# env RRSI_LLM_BACKEND=litellm-zai 开启(缺省关=原行为):generate() 改走 LiteLLM
# openai 兼容面 → zai coding cn 端点;模型串取 rrsi.json(*_model),base_url/api_key
# 走 env ZAI_CODING_CN_BASE_URL(缺省 https://open.bigmodel.cn/api/coding/paas/v4)/
# ZAI_CODING_CN_API_KEY(auth.json 凭证店同源,ops/agent/models.mjs 判例)。
# scripts/glm-smoke.py 经此面真调一次(票 #325 冒烟留痕)。
def _shim_log(msg: str) -> None:
    """垫片尝试日志(append RRSI_SHIM_LOG 或 runs/litellm-shim.log;每次尝试一行,排查
    挂死/空回不再盲等——判例 2026-11-08:round0 analyst 挂 28min 零可观测)。"""
    try:
        import time as _t
        p = Path(os.environ.get("RRSI_SHIM_LOG") or "runs/litellm-shim.log")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(f"{_t.strftime('%H:%M:%S')} {msg}\n")
    except Exception:  # noqa: BLE001 - 日志面尽力而为
        pass


def _zai_api_key() -> str:
    """zai 凭据:env ZAI_CODING_CN_API_KEY 优先;缺席兑底凭据店 ~/.pi/agent/auth.json
    的 zai-coding-cn 键(判例 #304-⑤:GLM 凭据只此一家,不设第二真源)。driver 进程
    通常不带该 env——垫片自取,免得每个调用方都得配。"""
    k = os.environ.get("ZAI_CODING_CN_API_KEY")
    if k:
        return k
    try:
        auth = json.loads((Path.home() / ".pi" / "agent" / "auth.json").read_text())
        return str(auth.get("zai-coding-cn", {}).get("key", ""))
    except Exception:  # noqa: BLE001 - 兑底失败=空串,litellm 会报缺凭证(如实)
        return ""


def _install_litellm_shim() -> bool:
    if os.environ.get("RRSI_LLM_BACKEND") != "litellm-zai":
        return False
    import litellm  # 延迟导入:仅 real 角色面需要
    import rrsi.llm as rllm

    def generate(prompt, system=None, max_retries=6, json_only=False, model=None,
                 max_tokens=4000, cache_prefix=None):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        if cache_prefix:
            msgs.append({"role": "system", "content": cache_prefix})
        msgs.append({"role": "user", "content": prompt})
        mdl = model or CFG.get("proposer_model")
        _shim_log(f"start model={mdl} prompt={len(prompt)}ch sys={len(system or '')}ch json_only={json_only}")
        last = None
        # 硬墙钟(判例 2026-11-08:endpoint 对个别请求滴流挂死,read 超时不触发,单请求
        # 28min+ 0.1% CPU;线程隔离 + future 墙钟强断,被弃线程自然消亡不阻塞重试链)。
        import concurrent.futures as _cf
        import time as _time
        _pool = _cf.ThreadPoolExecutor(max_workers=1)
        for i in range(max_retries):
            t0 = _time.monotonic()
            try:
                fut = _pool.submit(
                    litellm.completion,
                    model=mdl, messages=msgs, max_tokens=max_tokens,
                    timeout=300,  # 单请求上限(双保险)
                    # 关思考(实测 2026-11-08:同一 analyst 提示词,开思考滴流生成 >300s 零 content;
                    # 关后 141s finish=stop 正常 JSON。四角色都是 JSON 执行器,思考纯烧时)
                    extra_body={"thinking": {"type": "disabled"}},
                    base_url=os.environ.get(
                        "ZAI_CODING_CN_BASE_URL",
                        "https://open.bigmodel.cn/api/coding/paas/v4"),
                    api_key=_zai_api_key())
                # 墙钟随提示词大小自适应(#322 首跑判例:170KB+ 会话端点偶发滴流,
                # 330s 太紧掐死慢而活的回包;小提示词维持 330s 防挂死)
                _wall = 600 if len(prompt) >= 100_000 else 330
                rsp = fut.result(timeout=_wall)
                txt = rsp.choices[0].message.content or ""
                if txt.strip():
                    _shim_log(f"ok attempt={i} {_time.monotonic()-t0:.1f}s resp={len(txt)}ch")
                    return rllm.extract_json(txt) if json_only else txt
                _shim_log(f"empty attempt={i} {_time.monotonic()-t0:.1f}s")
                last = RuntimeError("empty response")  # 空回=重试(上游同律;编码端点偶发空 content)
            except Exception as e:  # noqa: BLE001
                _shim_log(f"err attempt={i} {_time.monotonic()-t0:.1f}s {e!r}"[:220])
                last = e
                _time.sleep(min(2 ** i, 30))
        raise RuntimeError(f"litellm-zai generate 失败({mdl}):{last!r}")

    _orig = getattr(rllm, "_vertex_generate_original", None) or rllm.generate
    rllm._vertex_generate_original = _orig
    rllm.generate = generate
    # 直绑面补丁(#322 首跑判例):analyst/propose 等 `from .llm import generate` 在本垫片
    # 安装前已 import,名字绑在原 Vertex 实现上——round0 analyst 即 ZeroDivisionError
    # (无 GCP 项目,÷0)。凡已载入 rrsi.* 子模块里 generate 绑定原函数的,一并改指垫片。
    import sys as _sys
    for _n, _m in list(_sys.modules.items()):
        if _n.startswith("rrsi") and getattr(_m, "generate", None) is _orig:
            _m.generate = generate
    return True

SHIM_ON = _install_litellm_shim()
