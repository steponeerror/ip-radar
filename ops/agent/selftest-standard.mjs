#!/usr/bin/env node
// selftest-standard.mjs — 门挂点核对器(standard-check.mjs)单测(#181;TDD RED 先行)。
// 全例纯内存 fixture(DI 注入 exists/readFile),零依赖零网络;机检语义=票 #181:
//   ①条文(#### X-n)缺门挂点字段/空挂点值 → FAIL ②挂点路径不存在(死锚)→ FAIL
//   ③挂点 path#fragment 片段不在文件内 → FAIL ④原语组成 token 不在原语表(伪条目)→ FAIL
//   ⑤建议区条目必须显式「类:建议」⑥条文体(#### X-n)不得进建议区
//   ⑦原语表计数/状态词表/重名 ⑧金标条目同受门挂点律 ⑨docs/(嵌套仓)不得作门挂点(CI 缺席判例)
// 输出契约:STDPASS/STDFAIL 行 + 末行 selftest-standard: PASS=n FAIL=m(同 T4 形)。

import { checkStandard } from "./standard-check.mjs";

let pass = 0;
let fail = 0;
const ok = (name) => { pass += 1; console.log(`STDPASS ${name}`); };
const bad = (name, why) => { fail += 1; console.log(`STDFAIL ${name}${why ? ` — ${why}` : ""}`); };

// ---- fixture 环境:内存文件系统 ----
const mkFs = (files) => ({
  exists: (p) => Object.prototype.hasOwnProperty.call(files, p),
  readFile: (p) => (Object.prototype.hasOwnProperty.call(files, p) ? files[p] : null),
});

// 合成有效典章(最小四层;primitiveCount 用 opts 覆写为 2)
const VALID_DOC = `# STANDARD.md — 合成有效样例

## 一、原语层(22 词)

| # | 原语 | 2026 出处 | 内部状态 | 内部锚 / 补课 |
|---|---|---|---|---|
| P1 | 谱系去重 | swarm tax 2026-05 | 已有 | backend/ipdb/_logodds.py |
| P2 | 金标集 | Anthropic 2026-01 | 已有 | ops/agent/golden/cases.json |

## 二、条文层(首批两维)

### 评估回归维(E)

#### E-1 合成头条
- 主张:先写失败评测再动 agent。
- 原语组成:金标集;谱系去重
- 门挂点:ops/agent/golden/run-golden.mjs;ops/agent/pipeline.mjs#HEALTH_PIPELINE
- 判例链:web.dev 2026-01-29;ADR 0008

### 开发过程维(D)

#### D-1 合成开发条
- 主张:门全机检,留痕可回算。
- 原语组成:谱系去重
- 门挂点:ops/agent/gates.mjs
- 判例链:promptfoo 2026-10-02

## 三、门挂点层

挂口族:CI/selftest/ops 轮门。

## 四、金标层(首批)

#### G-1 合成金标
- 主张:8.8.8.8 判 clean。
- 原语组成:金标集
- 门挂点:backend/ipdb/_eval/anchors.py
- 判例链:ADR 0008 决策3

## 五、建议区(无门挂点,显式标类)

- 类:建议 OTel 投影——轮信封外发词汇对齐(补课后转正)。
`;

const VALID_FILES = {
  "ops/agent/golden/run-golden.mjs": "export {}",
  "ops/agent/pipeline.mjs": "export const HEALTH_PIPELINE = [];",
  "ops/agent/gates.mjs": "export {}",
  "backend/ipdb/_eval/anchors.py": "ANCHORS = []",
};

// ---- 断言助手 ----
const run = (doc, files = {}, opts = {}) =>
  checkStandard(doc, { root: "/repo", primitiveCount: 2, ...mkFs({ ...VALID_FILES, ...files }), ...opts });

const expectPass = (name, doc, files, opts) => {
  const r = run(doc, files, opts);
  const fails = r.results.filter((x) => !x.ok);
  if (r.exitCode === 0 && fails.length === 0) ok(name);
  else bad(name, `意外 FAIL:${fails.map((f) => f.msg).join(" | ")}`);
};

const expectFail = (name, doc, keyword, files, opts) => {
  const r = run(doc, files, opts);
  const hit = r.results.find((x) => !x.ok && x.msg.includes(keyword));
  if (r.exitCode !== 0 && hit) ok(name);
  else bad(name, `应产出含「${keyword}」的 FAIL,实得 exit=${r.exitCode}:${r.results.filter((x) => !x.ok).map((f) => f.msg).join(" | ") || "(无失败项)"}`);
};

// ---- 1. 绿样例:有效典章全过 ----
expectPass("合成有效典章全绿(四层齐/挂点活/建议标类)", VALID_DOC);

// ---- 2. 空挂点:门挂点字段值为空 ----
expectFail(
  "空挂点条目被拒(门挂点值空)", 
  VALID_DOC.replace("门挂点:ops/agent/golden/run-golden.mjs;ops/agent/pipeline.mjs#HEALTH_PIPELINE", "门挂点:"),
  "空挂点",
);

// ---- 3. 缺门挂点字段:整行被删 ----
expectFail(
  "缺门挂点字段被拒(条文无门=伪标准形态)", 
  VALID_DOC.replace("- 门挂点:ops/agent/golden/run-golden.mjs;ops/agent/pipeline.mjs#HEALTH_PIPELINE\n", ""),
  "缺门挂点",
);

// ---- 4. 死锚:指向不存在的文件 ----
expectFail(
  "死锚挂点被拒(文件不存在)", 
  VALID_DOC.replace("ops/agent/gates.mjs", "ops/agent/never-lands.mjs"),
  "死锚",
);

// ---- 5. 死锚fragment:文件在但片段不在 ----
expectFail(
  "死锚fragment被拒(文件在而锚词不在)", 
  VALID_DOC.replace("ops/agent/pipeline.mjs#HEALTH_PIPELINE", "ops/agent/pipeline.mjs#NO_SUCH_CONST"),
  "fragment",
);

// ---- 6. 伪条目:原语组成含表外 token ----
expectFail(
  "伪条目被拒(原语组成表外词)", 
  VALID_DOC.replace("原语组成:金标集;谱系去重", "原语组成:金标集;未铸原语"),
  "伪条目",
);

// ---- 7. 建议未标类 ----
expectFail(
  "建议区未标类被拒(无门挂点必须显式「类:建议」)", 
  VALID_DOC.replace("- 类:建议 OTel 投影——轮信封外发词汇对齐(补课后转正)。", "- OTel 投影——轮信封外发词汇对齐。"),
  "类:建议",
);

// ---- 8. 条文体进建议区 ----
expectFail(
  "条文体混入建议区被拒(挂不上门不得称条文)", 
  VALID_DOC.replace(
    "- 类:建议 OTel 投影——轮信封外发词汇对齐(补课后转正)。",
    "#### E-9 藏进建议区的伪条文\n- 主张:绕过门挂点。\n- 原语组成:金标集\n- 判例链:无",
  ),
  "建议区",
);

// ---- 9. 原语计数不符(v0 闭集 22;合成样例注入 3 行对 2) ----
expectFail(
  "原语计数闭集被钉(22 词 v0 冻结;缺行被拒)", 
  VALID_DOC.replace("| P2 | 金标集 | Anthropic 2026-01 | 已有 | ops/agent/golden/cases.json |", ""),
  "原语计数",
);

// ---- 10. 状态词表外 ----
expectFail(
  "原语状态词表被钉(已有/半缺/缺之外被拒)", 
  VALID_DOC.replace("| P2 | 金标集 | Anthropic 2026-01 | 已有 |", "| P2 | 金标集 | Anthropic 2026-01 | 想要 |"),
  "状态",
);

// ---- 11. 原语重名 ----
expectFail(
  "原语重名被拒(一词一义)", 
  VALID_DOC.replace("| P2 | 金标集 |", "| P2 | 谱系去重 |"),
  "重名",
);

// ---- 12. 金标缺门挂点(金标层同受门挂点律) ----
expectFail(
  "金标条目缺门挂点被拒", 
  VALID_DOC.replace("- 门挂点:backend/ipdb/_eval/anchors.py\n- 判例链:ADR 0008 决策3", "- 判例链:ADR 0008 决策3"),
  "G-1",
);

// ---- 13. docs/(嵌套仓)作门挂点:CI checkout 缺席判例 ----
expectFail(
  "嵌套 docs 仓路径作门挂点被拒(CI 缺席判例)", 
  VALID_DOC.replace("ops/agent/gates.mjs", "docs/adr/0008-golden-standard-four-layer.md"),
  "docs/",
);

// ---- 14. 缺节:建议区整节被删 ----
expectFail(
  "必备节缺失被拒(建议区不得静默消失)", 
  VALID_DOC.replace("## 五、建议区(无门挂点,显式标类)\n\n- 类:建议 OTel 投影——轮信封外发词汇对齐(补课后转正)。\n", ""),
  "建议区",
);

// ---- 15. fragment 命中且建议不按条文计:反向确认(绿样例已含,此处点名) ----
{
  const r = run(VALID_DOC);
  const nArticles = r.counts.articles;
  const nAdvice = r.counts.advice;
  if (nArticles === 3 && nAdvice === 1) ok("计数面:条文3(2条文+1金标)/建议1,建议不冒充条文");
  else bad(`计数面:条文3/建议1,实得条文=${nArticles} 建议=${nAdvice}`);
}

console.log(`selftest-standard: PASS=${pass} FAIL=${fail}`);
process.exit(fail === 0 ? 0 : 1);
