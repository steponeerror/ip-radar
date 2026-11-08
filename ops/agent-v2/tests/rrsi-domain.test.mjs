// rrsi-domain.test.mjs — RRSI 域四件套结构不变式(票 #325;adapter.py/SKILL.md/PATTERNS.md/rrsi.json)。
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

test("rrsi.json 超参钉死:T=5/k=1/每轮 2 候选/delta=0.05 带理由;模型串指 zai glm-5.3-flash 且零密钥", () => {
  const cfg = JSON.parse(read("rrsi.json"));
  assert.equal(cfg.T, 5, "T=5(#322 裁决:约 13 轮预算 → 演化 5 轮留出 8 轮的量级起点)");
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
for name in ("binarydefense", "blocklist_de", "urlhaus"):
    pat = next((p for p, w in pats if ("泄漏源 " + name) in w), None)
    rep["known"][name] = {
        "present": pat is not None,
        "nonAnchored": bool(pat) and not pat.startswith("^") and not pat.endswith("$"),
        "lookaround": bool(pat) and pat.startswith(PREFIX) and pat.endswith(SUFFIX),
        "hasRawName": bool(pat) and re.escape(name) in pat}
for d in ("const SRC = " + DQ + "blocklist_de" + DQ + ";",
          "const FEEDS = [" + DQ + "binarydefense" + DQ + "];"):
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
