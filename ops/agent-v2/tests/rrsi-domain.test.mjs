// rrsi-domain.test.mjs — RRSI 域结构不变式(票 #325 + #327;adapter.py/SKILL.md/PATTERNS.md/rrsi.json)。
// 域级行为正确性由 bootstrap 门兜底(scripts/bootstrap-rrsi.sh → rrsi pytest + rrsi.py --domain
// ipradar smoke 绿,含 faux 轮+打分真跑);本测试钉的是「提案者宪法的机检面」——宪法文件
// 一旦漂移(丢零漂移红线/丢豁免判例/开放面越界/密钥入仓),演化轮的提案者就失去了护栏,
// 必须红。CI 无 python/rrsi 面,adapter 逻辑不可 import——只做内容断言(与 smoke-glm 判例同律);
// 例外(#325 F1):critic_needles.py 标准库自足,spawn python3 导入断言针形,python3 不可用则 skip。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DOMAIN_DIR = path.resolve(HERE, "..", "bench", "rrsi-domain");

const read = (name) => fs.readFileSync(path.join(DOMAIN_DIR, name), "utf8");

test("rrsi.json 超参钉死:T=25/k=1/每轮 2 候选/delta=0.05 带理由;模型串指 zai glm-5.3-flash 且零密钥", () => {
  const cfg = JSON.parse(read("rrsi.json"));
  assert.equal(cfg.T, 25, "T=25(#322 续跑 2026-11-08:用户令 faster iteration,T 5→10→25,链条 bde8b3d3/69fba439;原 T=5=约 13 轮预算的量级起点)");
  assert.equal(cfg.k, 1, "k=1(每源单轮;bench 轮即一次盲搜,重复试验无新信息)");
  assert.equal(cfg.m, 2, "m=2(每轮 2 候选,#322 裁决)");
  assert.equal(cfg.delta, 0.05, "delta 手设 0.05");
  assert.ok(
    JSON.stringify(cfg).includes("0.025") && JSON.stringify(cfg).includes("噪声"),
    "delta 理由须写进配置(1 题≈0.025 召回粒度,0.05≈2 题噪声带)",
  );
  // 四角色模型串全 glm-5.3-flash(冻结策略/提案者/分析师/审查者,#322 R4 裁决),LiteLLM 形
  assert.ok(cfg.proposer_model?.includes("glm-5.3-flash"), "proposer 模型串");
  assert.ok(cfg.analyst_model?.includes("glm-5.3-flash"), "analyst 模型串");
  assert.ok(cfg.critic_model?.includes("glm-5.3-flash"), "critic 模型串");
  // 密钥零入仓:任何值/注释里都不得出现 api key 形状(env 变量名可以)
  const text = read("rrsi.json");
  assert.ok(!/[0-9a-f]{32,}/i.test(text.replace(/glm[-a-z0-9.]*|bigmodel|anthropic|vertex|terminal-bench|swe-bench/gi, "")), "疑似密钥串入仓");
  assert.ok(!text.includes("ZAI_CODING_CN_API_KEY="), "不得带 key 赋值(裸 env 名引用除外)");
  assert.ok(text.includes("ZAI_CODING_CN_API_KEY"), "api key 走 env 须注名");
});

test("PATTERNS.md 提案者宪法:开放面/零漂移红线/豁免判例/免碰面四节齐备", () => {
  const md = read("PATTERNS.md");
  assert.ok(md.includes("ops/agent") && md.includes("ops/agent-v2"), "开放面=发现管线两目录");
  assert.ok(md.includes("零漂移"), "零漂移红线(真实轮路径行为字节不变,golden 钉)");
  assert.ok(md.includes("golden"), "零漂移红线须指名 golden 守门");
  assert.ok(md.includes("禁词引用"), "行级豁免判例(#308:行尾「禁词引用:原因」)");
  for (const face of ["backend/", "dev/", "docs/", ".worktrees/"]) {
    assert.ok(md.includes(face), `免碰面缺:${face}`);
  }
});

test("SKILL.md 提案者技能:基准世界/奖励口径/编辑纪律三要素在场", () => {
  const md = read("SKILL.md");
  assert.ok(md.includes("召回"), "奖励口径=逐源召回");
  assert.ok(md.includes("盲"), "盲测纪律:答案只在打分时用");
  assert.ok(md.includes("faux") || md.includes("冒烟"), "本票只 faux/冒烟,禁真实搜索轮");
});

test("adapter.py 接线面:三护栏+faux 门+leak 同源针+主检出取数判例,密钥零硬编码", () => {
  const py = read("adapter.py");
  for (const anchor of [
    "run-golden.mjs",           // 护栏①golden
    "npm",                      // 护栏②v2 全套(npm test)
    "leak-check.mjs",           // 护栏③leak gate
    "needs_frozen",             // 考题宇宙输入面 NEEDS.md 冻结门(bench SCAN 真面读它)
    "verification_frozen",      // 验证面冻结门(#327 Q2:评估器不许候选改)
    "EDIT_ALLOWLIST",           // 演化可编面白名单单源(#327 Q1:策略面 43 文件,dev/rrsi Workspace 消费)
    "faux",                     // 本票禁真实搜索轮:缺省 faux,real 须显式 env
    "ZAI_CODING_CN_API_KEY",    // 模型面 env 引用
    "ipdb._registry",           // roster 单源取数面
    "/home/huxiao/dev/pi-ip-lookup-tool/backend/.venv/bin/python", // worktree 判例:主检出解释器
  ]) {
    assert.ok(py.includes(anchor), `adapter.py 缺接线锚:${anchor}`);
  }
  assert.ok(!/[0-9a-f]{32,}/i.test(py.replace(/glm[-a-z0-9.]*|bigmodel|anthropic|vertex/gi, "")), "疑似密钥串入 adapter");
  assert.ok(py.includes("harness_path"), "Domain.harness_path 须显式(开放面单目录)");
});

// ── critic 针形(#325 F1 修复;评审 rrsi-a-review.md P1)──────────────────────
// 旧全等针 `^(?:挤压形)$`(^…$ 一头一尾卡死)对框架 critic.py precheck(对【原始 diff】re.search,无
// MULTILINE、无行折叠)永不命中——考题名硬编码全漏,确定性泄漏筛层形同虚设。
// 本测 spawn python3 导入 critic_needles.buildCriticPatterns(标准库自足,零 RRSI 依赖)
// 验真针形:环视形(不卡整段)+ RAW 原文形 + 假 diff 命中 + 共享基建 host 豁免。
// PYTHONDONTWRITEBYTECODE:防 __pycache__/*.pyc 落进域目录(豁免标记不随编译存活,
// 会误红 leak 面)。
const CRITIC_PROBE_PY = `
import importlib.util, json, re, sys
spec = importlib.util.spec_from_file_location("critic_needles", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
BS, DQ = chr(92), chr(34)
PREFIX = "(?<" + "!" + "[" + BS + "w-])(?:"
SUFFIX = ")(?!" + "[" + BS + "w-])"
rows = [json.loads(l) for l in open(sys.argv[2], encoding="utf-8").read().splitlines()[1:] if l.strip()]
pats = mod.buildCriticPatterns(rows)
joined = chr(10).join(p for p, _ in pats)
rep = {"total": len(pats),
       "anchored": [p for p, _ in pats if p.startswith("^") or p.endswith("$")],
       "infraInPats": {h: (h in joined) for h in tuple(getattr(mod, "SHARED_INFRA_HOSTS", ()))},
       "known": {}, "fakeDiff": {}}
for name in ("binarydefense", "blocklist_de", "urlhaus"): # 禁词引用:考题名作夹具数据(针形断言用,非泄漏)
    pat = next((p for p, w in pats if ("泄漏源 " + name) in w), None)
    rep["known"][name] = {
        "present": pat is not None,
        "nonAnchored": bool(pat) and not pat.startswith("^") and not pat.endswith("$"),
        "lookaround": bool(pat) and pat.startswith(PREFIX) and pat.endswith(SUFFIX),
        "hasRawName": bool(pat) and re.escape(name) in pat}
for d in ("const SRC = " + DQ + "blocklist_de" + DQ + ";", # 禁词引用:假 diff 夹具数据(命中断言用)
          "const FEEDS = [" + DQ + "binarydefense" + DQ + "];"): # 禁词引用:假 diff 夹具数据(命中断言用)
    rep["fakeDiff"][d] = sum(1 for p, _ in pats if re.search(p, d))
print(json.dumps(rep, ensure_ascii=False))
`;

let criticProbe = null;
let criticProbeErr = null;
try {
  criticProbe = JSON.parse(execFileSync(
    process.env.RRSI_TEST_PYTHON ?? "python3",
    ["-c", CRITIC_PROBE_PY, path.join(DOMAIN_DIR, "critic_needles.py"), path.join(DOMAIN_DIR, "data", "split.jsonl")],
    { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } }));
} catch (e) {
  criticProbeErr = e; // python3 面不可用 → skip(smoke-glm 判例;本地/验收跑必绿)
}

test("critic 针形(#325 F1):环视形+RAW 原文形;考题名假 diff 命中;共享基建 host 豁免", { skip: criticProbe ? false : `python3 面不可用(${criticProbeErr?.message})` }, () => {
  assert.equal(criticProbe.total, 53, "每考题一行一针(53 行)");
  assert.deepEqual(criticProbe.anchored, [], "全等形 ^(?:…)$ 一头一尾卡死,对原始 diff re.search 永不命中——禁止复活(#325 F1)");
  for (const [name, k] of Object.entries(criticProbe.known)) {
    assert.ok(k.present, `缺针:${name}`);
    assert.ok(k.nonAnchored, `${name} 针不得卡死整段(禁 ^…$ 形)`);
    assert.ok(k.lookaround, `${name} 针须 (?<![\\w-])(?:…)(?![\\w-]) 环视形`);
    assert.ok(k.hasRawName, `${name} 针须含 RAW 原文名形(挤压形只作附加 alternation)`);
  }
  for (const [diff, hits] of Object.entries(criticProbe.fakeDiff)) {
    assert.ok(hits >= 1, `含考题名的假 diff 须命中至少一针:${diff}`);
  }
  for (const [host, inPats] of Object.entries(criticProbe.infraInPats)) {
    assert.equal(inPats, false, `共享基建 host ${host} 不得入针(候选 diff 合法提及=常态,入针每轮误拦走 repair)`);
  }
});

// —— adapter 门红面(#322 首跑判例 2026-11-08:门红=模型侧不合规,计 0 分不炸跑)——
// adapter.py import 即拉 rrsi 包(site-packages),须 dev/rrsi venv 解释器;CI 无此面 → skip
// (smoke-glm 判例;本地/验收跑必绿)。零网络零花钱:只测纯分类与 score 合成分支。
const ADAPTER_PY = path.join(DOMAIN_DIR, "adapter.py");
let adapterProbe = null;
let adapterProbeErr = null;
try {
  adapterProbe = JSON.parse(execFileSync(
    process.env.RRSI_ADAPTER_PYTHON ?? "/home/huxiao/dev/pi-ip-lookup-tool/dev/rrsi/.venv/bin/python",
    ["-c", `
import importlib.util, json, sys, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("adapter_probe", ${JSON.stringify(ADAPTER_PY)})
m = importlib.util.module_from_spec(spec)
sys.modules["adapter_probe"] = m
spec.loader.exec_module(m)
rep = {}
# ① _last_envelope:末行 JSON 信封;噪声行/无信封 → None
with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
    f.write("noise line\\n{\\\"ok\\\":false,\\\"round\\\":\\\"discover\\\",\\\"error\\\":{\\\"code\\\":\\\"infra\\\",\\\"message\\\":\\\"GATE:SHORTLIST:x\\\"}}\\n")
    lp = Path(f.name)
rep["lastEnv"] = (m._last_envelope(lp) or {}).get("error", {}).get("message", "")
lp.unlink()
with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
    f.write("no json here\\n")
    lp2 = Path(f.name)
rep["noEnv"] = m._last_envelope(lp2)
lp2.unlink()
# ② _is_gate_red
rep["gate"] = m._is_gate_red({"error": {"message": "GATE:SHORTLIST:x"}})
rep["notGate"] = m._is_gate_red({"error": {"message": "model channel_open"}})
rep["none"] = m._is_gate_red(None)
# ③ score() gate-red 合成:gate-red.json 在 → 全任务 0 分 + extra.gate_red + guards 照载
runs = Path(tempfile.mkdtemp())
rid = m._round_id("jobx", 0)
art = m._artifacts_dir(runs, "jobx", 1)
art.mkdir(parents=True)
(art / "gate-red.json").write_text(json.dumps(
    {"code": "gate_red", "envelope": {"error": {"code": "infra", "message": "GATE:SHORTLIST:x"}}}))
per, extra = m.DOMAIN.score(runs, "jobx", ["src_a", "src_b"], 1)
rep["rewards"] = per["src_a"].rewards
rep["recall"] = extra["recall"]
rep["gateRedExtra"] = extra["gate_red"]
rep["unfound"] = extra["unfound"]
print(json.dumps(rep, ensure_ascii=False))
`, ], { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } }));
} catch (e) {
  adapterProbeErr = e; // dev/rrsi venv 面不可用 → skip
}

test("adapter 门红面:_last_envelope 末行信封;GATE: 前缀判门红;score 合成零召回", { skip: adapterProbe ? false : `dev/rrsi venv 面不可用(${adapterProbeErr?.message})` }, () => {
  assert.equal(adapterProbe.lastEnv, "GATE:SHORTLIST:x");
  assert.equal(adapterProbe.noEnv, null);
  assert.equal(adapterProbe.gate, true);
  assert.equal(adapterProbe.notGate, false);
  assert.equal(adapterProbe.none, false);
  assert.deepEqual(adapterProbe.rewards, [0.0]);
  assert.deepEqual(adapterProbe.recall, { found: 0, total: 2, pct: 0.0 });
  assert.equal(adapterProbe.gateRedExtra, "GATE:SHORTLIST:x");
  assert.deepEqual(adapterProbe.unfound, ["src_a", "src_b"]);
});

// —— #327 harness 边界收口:演化编辑白名单(策略面 43 文件)+ 验证面冻结门 ——
// Q1 裁定(推翻 #322 R5 全放开):可编面收窄到策略面 43 文件,read/edit/write 同表;
// Q2 方案 a:验证面(golden/selftest*/fixtures/v2-tests)照常 vendor + git diff 冻结门,
// NEEDS.md 门同律同机——「候选可改给自己打分的测试」从靠模型自觉变靠结构(调研笔记
// docs/notes/ops-tree-as-harness-2026-11-08.md:护栏在候选 worktree 内跑)。
// 探针同 adapter 门红面判例(dev/rrsi venv 导入 adapter;CI 无 python 面 → skip);
// 实现缺失以 hasattr 报告回传:红是真红,skip 只留给环境不可用。
const BOUNDARY_PROBE_PY = `
import importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("adapter_probe", sys.argv[1])
m = importlib.util.module_from_spec(spec)
sys.modules["adapter_probe"] = m
spec.loader.exec_module(m)
rep = {}
# ① 实现在场性(缺=真红非 skip)+ DOMAIN 类属性暴露(dev/rrsi Workspace getattr 消费)
rep["has"] = {n: hasattr(m, n) for n in ("EDIT_ALLOWLIST", "edit_allowed", "_frozen",
                                         "NEEDS_GATE_PATHS", "VERIFICATION_GATE_PATHS")}
rep["domainAttr"] = getattr(m.DOMAIN, "edit_allowlist", None) is getattr(m, "EDIT_ALLOWLIST", None)
if rep["has"]["edit_allowed"]:
    allow = ("ops/agent/pipeline/steps.mjs",
             "ops/agent/prompts/discover-system.md",
             "ops/agent/prompts/discover/shortlist.md",
             "ops/agent/agent.mjs",
             "ops/agent/models.mjs",
             "ops/agent-v2/tools/probes.mjs",
             "ops/agent-v2/tasks/discover-round.mjs",
             "ops/agent-v2/bench/score.mjs",
             "ops/agent-v2/bench/rrsi-domain/adapter.py")
    deny = ("ops/agent/golden/cases.json",
            "ops/agent/selftest-pipeline.mjs",
            "ops/agent/fixtures/pipeline/d1-scan.json",
            "ops/agent-v2/tests/rrsi-domain.test.mjs",
            "ops/agent/package-lock.json",
            "ops/agent-v2/package-lock.json",
            "README.md",
            "ops/agent/pipeline.mjs",
            "ops/agent/tools.mjs",
            "ops/agent-v2/entry.mjs",
            "ops/agent/feeds.txt")
    rep["allow"] = {p: bool(m.edit_allowed(p)) for p in allow}
    rep["deny"] = {p: bool(m.edit_allowed(p)) for p in deny}
    rep["normBackslash"] = bool(m.edit_allowed("ops\\\\agent\\\\prompts\\\\discover-system.md"))
    # 构成计数(source_exts 面,同调研笔记口径;split.jsonl 的 .jsonl 不入)
    exts = {".py", ".txt", ".md", ".json", ".mjs"}
    ops = Path(sys.argv[2])
    files = ["ops/" + str(p.relative_to(ops)) for base in ("agent", "agent-v2")
             for p in (ops / base).rglob("*")
             if p.is_file() and "node_modules" not in p.parts and p.suffix in exts]
    rep["allowlistCount"] = sum(1 for f in files if m.edit_allowed(f))
if all(rep["has"].values()):
    # ② 冻结门红性:临时 git 仓(incumbent 分支 evolve/ipradar)真改文件验门;
    #    四红例各盖一条 pathspec(golden 目录 / selftest* glob / fixtures 深层 / v2 tests)
    d = Path(tempfile.mkdtemp(prefix="gate327-"))
    h = d / "domains" / "ipradar" / "harness"
    for rel, body in (("NEEDS.md", "n\\n"),
                      ("ops/agent/golden/cases.json", "g\\n"),
                      ("ops/agent/selftest-pipeline.mjs", "st\\n"),
                      ("ops/agent/fixtures/pipeline/d1-scan.json", "f\\n"),
                      ("ops/agent-v2/tests/x.test.mjs", "t\\n"),
                      ("ops/agent-v2/bench/leak-check.mjs", "lc\\n"),
                      ("ops/agent-v2/bench/exam-rules.json", "er\\n"),
                      ("ops/agent/prompts/discover-system.md", "p\\n")):
        p = h / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    def git(*a):
        subprocess.run(["git", *a], cwd=d, check=True, capture_output=True, env=env)
    git("init", "-q")
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "incumbent")
    git("branch", "evolve/ipradar")
    def vf():
        return m._frozen(d, m.VERIFICATION_GATE_PATHS)
    def nf():
        return m._frozen(d, m.NEEDS_GATE_PATHS)
    rep["gateClean"] = vf()
    rep["gateRed"] = {}
    for rel in ("ops/agent/golden/cases.json",
                "ops/agent/selftest-pipeline.mjs",
                "ops/agent/fixtures/pipeline/d1-scan.json",
                "ops/agent-v2/tests/x.test.mjs"):
        p = h / rel
        p.write_text(p.read_text() + "touched\\n")
        rep["gateRed"][rel] = vf()
        git("checkout", "-q", "--", ".")
    (h / "ops/agent/prompts/discover-system.md").write_text("p2\\n")
    rep["gatePolicyEditGreen"] = vf()
    git("checkout", "-q", "--", ".")
    (h / "NEEDS.md").write_text("n2\\n")
    rep["gateNeedsOnly"] = [nf(), vf()]
    git("checkout", "-q", "--", ".")
    (h / "ops/agent/golden/cases.json").write_text("g2\\n")
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "cand")
    rep["gateCommittedRed"] = vf()
    git("reset", "-q", "--hard", "evolve/ipradar")
    #    leak gate 执法面(Standards P1 修批,评审 1e9e66fb):两条新 pathspec 各自独立验
    #    「提交态红/清白绿」——逐条 hard reset 隔离,红只归因该文件,不与 golden 红叠加。
    rep["gateLeakEnforce"] = {}
    for rel in ("ops/agent-v2/bench/leak-check.mjs",
                "ops/agent-v2/bench/exam-rules.json"):
        p = h / rel
        p.write_text(p.read_text() + "touched\\n")
        git("add", "-A")
        git("-c", "commit.gpgsign=false", "commit", "-q", "-m",
            "cand-" + Path(rel).name)
        red = vf()
        git("reset", "-q", "--hard", "evolve/ipradar")
        rep["gateLeakEnforce"][rel] = [red, vf()]
# ③ guards() 非补偿执法:receipt 缺 verification_frozen = 不可接受(与 needs_frozen 同律)
from types import SimpleNamespace
ok = {"golden": True, "v2_test": True, "leak_gate": True,
      "needs_frozen": True, "verification_frozen": True}
rep["guardsAllPass"] = m.DOMAIN.guards(None, SimpleNamespace(extra={"guards": dict(ok)}))
rep["guardsMissingNewLeg"] = m.DOMAIN.guards(
    None, SimpleNamespace(extra={"guards": {k: v for k, v in ok.items()
                                            if k != "verification_frozen"}}))
rep["guardsNoReceipt"] = m.DOMAIN.guards(None, SimpleNamespace(extra={}))
print(json.dumps(rep, ensure_ascii=False))
`;

let boundaryProbe = null;
let boundaryProbeErr = null;
try {
  boundaryProbe = JSON.parse(execFileSync(
    process.env.RRSI_ADAPTER_PYTHON ?? "/home/huxiao/dev/pi-ip-lookup-tool/dev/rrsi/.venv/bin/python",
    ["-c", BOUNDARY_PROBE_PY, ADAPTER_PY, path.resolve(HERE, "..", "..")],
    { encoding: "utf8", env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } }));
} catch (e) {
  boundaryProbeErr = e; // dev/rrsi venv 面不可用 → skip(同 adapter 门红面判例)
}

test("adapter 边界收口(#327):白名单 43 文件面 + 验证面冻结门红性 + guards 新腿", { skip: boundaryProbe ? false : `dev/rrsi venv 面不可用(${boundaryProbeErr?.message})` }, () => {
  assert.ok(Object.values(boundaryProbe.has).every(Boolean), `API 缺席(#327 实现面):${JSON.stringify(boundaryProbe.has)}`);
  assert.equal(boundaryProbe.domainAttr, true, "DOMAIN 须类属性暴露 edit_allowlist(dev/rrsi Workspace getattr 消费)");
  for (const [p, v] of Object.entries(boundaryProbe.allow))
    assert.equal(v, true, `白名单内路径须可编:${p}`);
  for (const [p, v] of Object.entries(boundaryProbe.deny))
    assert.equal(v, false, `名单外路径须拒(只读):${p}`);
  assert.equal(boundaryProbe.normBackslash, true, "反斜杠路径须归一(\\ → /)");
  assert.equal(
    boundaryProbe.allowlistCount, 47,
    "策略面构成=47 文件(#327 原裁 43;#333 P2a 加源基准器 add-domain +4:pipeline 11+prompts 9+v2 tools/tasks/bench 25+v1 入口/模型 2;source_exts 计数面;漂移须重裁并同步 EDIT_ALLOWLIST 注释与本测)",
  );
  assert.equal(boundaryProbe.gateClean, true, "净树=冻结完好(rc0)");
  for (const [rel, v] of Object.entries(boundaryProbe.gateRed))
    assert.equal(v, false, `验证面改动须门红:${rel}`);
  assert.equal(boundaryProbe.gatePolicyEditGreen, true, "策略面改动不得触发验证面门(可编面与冻结面正交)");
  assert.deepEqual(
    boundaryProbe.gateNeedsOnly, [false, true],
    "NEEDS.md 改动只红 NEEDS 门、不红验证面门(两门正交)",
  );
  assert.equal(boundaryProbe.gateCommittedRed, false, "提交态改动须仍红(真实路径:候选 commit_path 提交后 guards 才跑)");
  assert.deepEqual(boundaryProbe.guardsAllPass, [], "五腿全过 receipt=可接受");
  assert.ok(
    boundaryProbe.guardsMissingNewLeg.some((s) => s.includes("verification_frozen")),
    "receipt 缺 verification_frozen=不可接受(非补偿执法,#327 与 needs_frozen 同律)",
  );
  assert.ok(boundaryProbe.guardsNoReceipt.length > 0, "无 receipt=不可接受");
});

// —— #327 Standards P1 修批:leak gate 自身执法件入冻结门(评审 1e9e66fb P1)——
// 护栏③在候选 worktree 内跑候选副本 leak-check.mjs;它被 EDIT_ALLOWLIST 的 bench/**
// 放行可编、又不在冻结门 → 候选可把检查器改成恒零命中再往 prompts 注考题名,五腿回执
// 照绿。exam-rules.json 同类利用面:exempt 免考名单是打分面数据(score.mjs 的考题分母
// 由它派生),名单载体留在被告可编面=门上留缝。两文件与验证面同律冻结。
test("验证面冻结门含 leak gate 执法件:leak-check.mjs 提交态红/清白绿(#327 Standards P1)", { skip: boundaryProbe ? false : `dev/rrsi venv 面不可用(${boundaryProbeErr?.message})` }, () => {
  const [red, clean] = boundaryProbe.gateLeakEnforce["ops/agent-v2/bench/leak-check.mjs"];
  assert.equal(red, false, "leak-check.mjs 提交态改动须门红(给自己站岗的面与给自己打分的面同律冻结)");
  assert.equal(clean, true, "reset 回 incumbent 后清白树须门绿(rc0)");
});
test("验证面冻结门含 leak gate 执法件:exam-rules.json 提交态红/清白绿(#327 Standards P1)", { skip: boundaryProbe ? false : `dev/rrsi venv 面不可用(${boundaryProbeErr?.message})` }, () => {
  const [red, clean] = boundaryProbe.gateLeakEnforce["ops/agent-v2/bench/exam-rules.json"];
  assert.equal(red, false, "exam-rules.json 提交态改动须门红(exempt 免考名单=打分面数据,不得留在被告可编面)");
  assert.equal(clean, true, "reset 回 incumbent 后清白树须门绿(rc0)");
});
