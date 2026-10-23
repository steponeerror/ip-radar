// pipeline/gates.mjs — 阶段门:每门 =(工件文件集)→{pass,reason} 纯函数 + 求值留痕 gates.json。
// P0 骨架(spec #161;详设 C 稿 §4.3/§2.2)。纪律:
//   门是唯一转移裁判,不信模型自报;reason 必须带数字(「门说覆盖率 0.83 拦了」可在 gates.json 回算);
//   重算秒级,CLOSE 与 replay 全量重跑(自愈:状态文件与工件不一致时以工件+门为准);
//   闭集值集中在 CLOSED_SETS(新增闭集值=spec 变更);字段点解析复用 tools.mjs resolveField(单一解析语义)。
//   P2(#164):在飞面改真读 _ops_items(steps.readInFlightItems 单一解析语义,门与步同源不另起炉灶)。
import fs from "node:fs";
import path from "node:path";
import { resolveField, closureCheck } from "../tools.mjs";
import { normalizeRules, readInFlightItems, inFlightKeys, deepSeeds, RULE_PREDICATES, RULE_ACTIONS } from "./steps.mjs";
import { fullDedupKey } from "./ops-items.mjs"; // 全签同因面(P4 #166;步/门同源)
import { parseItem } from "./ops-items.mjs"; // 条目树读回(单一解析语义)

export const CLOSED_SETS = {
  cause_class: ["frozen_feed", "dead_endpoint", "auth_wall", "rate_limit", "probe_artifact", "matrix_violation", "unknown"], // C稿 §3.2 草案 1
  severity: ["high", "medium", "low"],
  probe_hint: ["reprobe_get", "reprobe_ua", "upstream_check", "none"], // 微探针闭集(P0 预留名;真工具=P4)
  verdict: ["confirmed", "refuted", "unresolved"],
  deep_tool: ["reprobe_get", "reprobe_ua", "upstream_check"], // 微探针闭集(P4 #166;与 probe_hint 同词表减 none;faux 工具面=registry_seed 结构化返回,真 API 不在票面)
  action: ["digest_ignore", "human_ruling", "watch"], // 条目建议动作闭集(P4 #166 裁:confirmed/unresolved→human_ruling 人裁终局;refuted→digest_ignore 低危消化;watch→观察;review_freeze 退役——永不自动执行,建议面恒交人)
};

const j = (p) => { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; } };
const txt = (p) => { try { return fs.readFileSync(p, "utf8"); } catch { return null; } };
const jsonl = (p) => (txt(p) ?? "").split("\n").filter(Boolean).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
const eqSet = (a, b) => JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());
const fail = (reason, inputs, code) => ({ pass: false, reason, inputs, code }); // code 可选:门指定终态码(闭集内,如 closure_check;缺省=定义表 fail.terminal)
const pass = (reason, inputs) => ({ pass: true, reason, inputs });

export const GATES = {
  // G_PROBE:summary 可解析 ∧ urls_n≥30(现 101,清单事实层 feeds.txt)∧ attempted/urls≥0.9 ∧ TSV 行数=attempted_n(C稿 §2.2)
  G_PROBE: (ctx) => {
    const inputs = ["01-probe-summary.json", "01-probe-freshness.tsv"];
    const s = j(path.join(ctx.dir, "01-probe-summary.json"));
    if (!s) return fail("01-probe-summary.json 不可解析", inputs);
    const tsv = txt(path.join(ctx.dir, "01-probe-freshness.tsv"));
    if (tsv === null) return fail("01-probe-freshness.tsv 缺失", inputs);
    const rows = tsv.split("\n").filter(Boolean).length;
    const ratio = s.urls_n ? s.attempted_n / s.urls_n : 0;
    if (!(s.urls_n >= 30)) return fail(`urls_n=${s.urls_n}<30`, inputs);
    if (!(ratio >= 0.9)) return fail(`attempted/urls=${ratio.toFixed(2)}<0.9(attempted_n=${s.attempted_n}/urls_n=${s.urls_n})`, inputs);
    if (rows !== s.attempted_n) return fail(`tsv_rows=${rows}≠attempted_n=${s.attempted_n}`, inputs);
    return pass(`urls_n=${s.urls_n} attempted=${s.attempted_n}(${ratio.toFixed(2)}≥0.9) tsv_rows=${rows} flags=${(s.flags ?? []).length}`, inputs);
  },
  // G_VERIFY:survivors∪suppressed 的 signal_id = probe 旗标全集(穷尽一条不丢)∧ 每条抑制引用规则 id ∈ 规则文件闭集
  G_VERIFY: (ctx) => {
    const inputs = ["01-probe-summary.json", "02-verify-survivors.json", "02-verify-suppressed.json", "02-verify-rules.json|rules/suppressions.json", "items/*.md"];
    const s = j(path.join(ctx.dir, "01-probe-summary.json"));
    const sv = j(path.join(ctx.dir, "02-verify-survivors.json"));
    const sp = j(path.join(ctx.dir, "02-verify-suppressed.json"));
    if (!s || !sv || !sp) return fail("verify 工件不可解析", inputs);
    // #164 审 P2-6(#167 收口):门读轮次时点版规则——VERIFY 步落 02-verify-rules.json
    // 快照;replay --dry(复制原件工件)即审轮次时点版,规则库事后演进不改历史判定。
    // 快照缺席(P5 前旧轮/过渡面)回落现行文件,reason 注记版本漂移风险(宁显式勿哑)。
    const snap = path.join(ctx.dir, "02-verify-rules.json");
    const raw = j(fs.existsSync(snap) ? snap : ctx.rulesFile);
    let rules;
    try { rules = raw ? normalizeRules(raw) : null; } // 闭集校验同源步侧单一实现
    catch { rules = null; }
    if (!rules) return fail("抑制规则库不可解析(规则零命中=空集照常过;文件坏=终态 infra 面)", inputs);
    const flagIds = (s.flags ?? []).map((f) => f.signal_id);
    const partIds = [...(sv.survivors ?? []), ...(sp.suppressed ?? [])].map((x) => x.signal_id);
    if (!eqSet(flagIds, partIds))
      return fail(`分区不穷尽:flags=${flagIds.length}≠survivors∪suppressed=${partIds.length};丢=${flagIds.filter((i) => !partIds.includes(i)).slice(0, 3).join(",")}`, inputs);
    const ruleIds = new Set(rules.rules.map((r) => r.id));
    const flight = inFlightKeys(readInFlightItems(ctx.itemsDir, ctx.state?.replay_of)); // 在飞面重算(与步同源;全签同因,replay 排除原轮自己的产物=回声防线)
    for (const x of sp.suppressed ?? []) {
      if (x.rule_id === "in_flight") {
        if (!flight.has(x.dedup_key)) return fail(`in_flight 抑制全签不在在飞集:${x.dedup_key}(步侧 ${fullDedupKey(x)})`, inputs);
        const ids = flight.get(x.dedup_key) ?? [];
        if (!(x.in_flight_items ?? []).length || (x.in_flight_items ?? []).some((id) => !ids.includes(id)))
          return fail(`in_flight 溯源条目缺席:${x.dedup_key}(工件 ${(x.in_flight_items ?? []).join(",")} vs 在飞 ${ids.join(",")})`, inputs);
        continue;
      }
      if (!ruleIds.has(x.rule_id)) return fail(`抑制引用规则 id 不在闭集:${x.rule_id}`, inputs);
    }
    return pass(`flags=${flagIds.length} 全分区(survivors=${(sv.survivors ?? []).length} suppressed=${(sp.suppressed ?? []).length},规则 v${rules.version} 共${rules.rules.length} 条,在飞源 ${flight.size})`, inputs);
  },
  // G_TRIAGE:schema 过 ∧ 闭集 ∧ 假设覆盖全部幸存 signal_id(一条一假设,吞并即门败);幸存集空=门直过
  G_TRIAGE: (ctx) => {
    const inputs = ["02-verify-survivors.json", "03-triage-hypotheses.json"];
    const sv = j(path.join(ctx.dir, "02-verify-survivors.json"));
    const h = j(path.join(ctx.dir, "03-triage-hypotheses.json"));
    if (!h || !Array.isArray(h.hypotheses)) return fail("03-triage-hypotheses.json 不可解析/缺 hypotheses 数组", inputs);
    const svIds = (sv?.survivors ?? []).map((x) => x.signal_id);
    const hIds = h.hypotheses.map((x) => x.signal_id);
    if (!eqSet(svIds, hIds)) return fail(`假设不穷尽幸存集:survivors=${svIds.length}≠假设=${hIds.length}(一条一假设,吞并/漏签即门败)`, inputs);
    for (const x of h.hypotheses) {
      if (!CLOSED_SETS.cause_class.includes(x.cause_class)) return fail(`cause_class 闭集外:${x.cause_class}(${x.signal_id})`, inputs);
      if (!CLOSED_SETS.severity.includes(x.severity)) return fail(`severity 闭集外:${x.severity}(${x.signal_id})`, inputs);
      if (!CLOSED_SETS.probe_hint.includes(x.probe_hint)) return fail(`probe_hint 闭集外:${x.probe_hint}(${x.signal_id})`, inputs);
      if (x.need_deep === (x.probe_hint === "none")) return fail(`need_deep=${x.need_deep} 与 probe_hint=${x.probe_hint} 矛盾(${x.signal_id})`, inputs);
      if (typeof x.hypothesis !== "string" || !x.hypothesis) return fail(`hypothesis 缺(${x.signal_id};可证伪预测形是必填)`, inputs);
      if (typeof x.need_deep !== "boolean") return fail(`need_deep 非布尔(${x.signal_id})`, inputs); // P3 #165:schema 面
      if (typeof x.one_line !== "string" || !x.one_line) return fail(`one_line 缺(${x.signal_id};≤30 字人读行是必填)`, inputs);
    }
    if (typeof h.digest !== "string" || !h.digest) return fail("digest 缺(输出契约必填:≤3 行信号面貌+深验子集规模)", inputs);
    return pass(`幸存 ${svIds.length} 条一条一假设穷尽;深验子集 ${h.hypotheses.filter((x) => x.need_deep).length};闭集值全这`, inputs);
  },
  // G_DISPATCH:每个 need_deep 假设有 bundle(或入截尾)∧ 预算合计 ≤ 轮预算门
  G_DISPATCH: (ctx) => {
    const inputs = ["03-triage-hypotheses.json", "04-dispatch-bundles.json"];
    const h = j(path.join(ctx.dir, "03-triage-hypotheses.json"));
    const d = j(path.join(ctx.dir, "04-dispatch-bundles.json"));
    if (!d || !Array.isArray(d.bundles)) return fail("04-dispatch-bundles.json 不可解析", inputs);
    const need = (h?.hypotheses ?? []).filter((x) => x.need_deep).map((x) => x.signal_id);
    const got = [...d.bundles.map((b) => b.hid), ...(d.truncated ?? []).map((t) => t.hid)];
    if (!eqSet(need, got)) return fail(`need_deep ${need.length} 条≠bundles∪truncated ${got.length}(截尾也须留痕)`, inputs);
    const sum = d.bundles.reduce((a, b) => a + (b.budget_cny ?? 0), 0);
    if (sum > ctx.budgetCny + 1e-9) return fail(`预算合计 ${sum.toFixed(4)}¥>轮预算 ${ctx.budgetCny}¥`, inputs);
    return pass(`bundles=${d.bundles.length} truncated=${(d.truncated ?? []).length} 预算合计 ${sum.toFixed(4)}¥≤${ctx.budgetCny}¥${d.degraded ? "(降级:severity 截尾)" : ""}`, inputs);
  },
  // G_DEEP:每假设 verdict ∈ 闭集 ∧ evidence 三元组逐字回引本步登记表(A 一律:call_id+field 选择对,宿主回填值)
  G_DEEP: (ctx) => {
    const inputs = ["04-dispatch-bundles.json", "05-deep-verdicts.json", "05-deep-*-transcript.jsonl"];
    const d = j(path.join(ctx.dir, "04-dispatch-bundles.json"));
    const v = j(path.join(ctx.dir, "05-deep-verdicts.json"));
    if (!v || !Array.isArray(v.verdicts)) return fail("05-deep-verdicts.json 不可解析", inputs);
    const need = (d?.bundles ?? []).map((b) => b.hid);
    const got = [...v.verdicts.map((x) => x.hid), ...(v.degraded ?? []).map((x) => x.hid)];
    if (!eqSet(need, got)) return fail(`深验不穷尽 bundle:${need.length}≠${got.length}`, inputs);
    const reg = deepSeeds(ctx.dir); // 登记表重建:各假设 transcript 的 registry_seed 行(P4 faux 工具面;deepConsume 宿主回填同源单一解析)
    const seedN = new Map(); // 微探针计数:transcript → seed 行数(≤3/假设,deep.md 预算段机检面)
    for (const f of fs.readdirSync(ctx.dir).filter((f) => /^05-deep-.*-transcript\.jsonl$/.test(f)))
      seedN.set(f, jsonl(path.join(ctx.dir, f)).filter((r) => r.type === "registry_seed").length);
    for (const [f, n] of seedN) if (n > 3) return fail(`微探针超 3 次/假设:${f} seed=${n}(预算段硬约束)`, inputs);
    for (const r of reg.values()) if (!CLOSED_SETS.deep_tool.includes(r.tool))
      return fail(`登记表工具闭集外:${r.tool}(微探针闭集 reprobe_get/reprobe_ua/upstream_check)`, inputs);
    for (const x of v.verdicts) {
      if (!CLOSED_SETS.verdict.includes(x.verdict)) return fail(`verdict 闭集外:${x.verdict}(${x.hid})`, inputs);
      if (x.verdict !== "unresolved" && !(x.evidence ?? []).length) return fail(`${x.verdict} 无证据腿(${x.hid};confirmed/refuted 必带 evidence)`, inputs);
      const regH = deepSeeds(ctx.dir, x.hid); // 审后修 P2-2:逐假设登记表——邻假设 call_id 不得借道过门(回填按 hid,门同口径)
      for (const e of x.evidence ?? []) {
        const r = regH.get(e.call_id);
        if (!r) return fail(`evidence 引用未知 call_id:${e.call_id}(${x.hid})`, inputs);
        if (r.sc && r.sc.ok === false) return fail(`失败信封禁入 evidence:${e.call_id}(ok:false 是测量故障非读数;留痕在 transcript 不占 evidence)`, inputs);
        const regv = resolveField(r.sc, e.field);
        if (e.value === undefined || regv === undefined)
          return fail(`evidence 三元组缺值:${e.call_id}:${e.field}(宿主回填缺席或 field 不在结构化返回)`, inputs);
        if (regv !== e.value)
          return fail(`evidence 回引不符:${e.call_id}:${e.field}=${JSON.stringify(e.value)}≠登记表 ${JSON.stringify(regv)}(A 一律:复述不符即门败)`, inputs);
      }
    }
    // 空转金轨迹(#162 审 P2-2,裁定①):零 bundle 轮 DEEP 仍须跑一条 canned 回路并留痕 golden_track;
    // 真 bundle 轮不得混入金轨迹(不污染条目面)。金轨迹 verdict 同受闭集/证据腿约束。
    const golden = v.golden_track ?? [];
    for (const g of golden) {
      if (!CLOSED_SETS.verdict.includes(g.verdict)) return fail(`金轨迹 verdict 闭集外:${g.verdict}(${g.hid})`, inputs);
      if (g.verdict !== "unresolved" && !(g.evidence ?? []).length) return fail(`金轨迹 ${g.verdict} 无证据腿(${g.hid})`, inputs);
    }
    if (!need.length && !golden.length) return fail("零 bundle 轮缺空转金轨迹回路(#162 审 P2-2 裁定①)", inputs);
    if (need.length && golden.length) return fail(`金轨迹与真假设同轮(${golden.map((g) => g.hid).join(",")})——金轨迹仅零 need_deep 轮保活`, inputs);
    return pass(`verdicts=${v.verdicts.length} degraded=${(v.degraded ?? []).length} golden=${golden.length};evidence 逐字回引登记表(${reg.size} 腿,全 ∈ 只读闭集)`, inputs);
  },
  // G_ITEMIZE:manifest 计数=rows 对账 ∧ 行穷尽(verdicts∪degraded∪truncated∪未深验)∧ 真条目树
  // 读回一致(文件在场/dedup_key 同签/复开链指)∧ 动作/severity 闭集 ∧ refuted 恒 low(三小裁②)
  G_ITEMIZE: (ctx) => {
    const inputs = ["06-itemize-manifest.json", "02-verify-suppressed.json", "ops-items/*.md"];
    const m = j(path.join(ctx.dir, "06-itemize-manifest.json"));
    if (!m || !Array.isArray(m.rows)) return fail("06-itemize-manifest.json 不可解析/缺 rows(P4 #166:rows=轮内条目面)", inputs);
    for (const k of ["created", "reopened", "deduped", "suppressed"]) if (typeof m[k] !== "number") return fail(`manifest.${k} 非数字`, inputs);
    const tally = { created: 0, reopened: 0, deduped: 0 };
    for (const r of m.rows) {
      if (r.outcome === "created") tally.created += 1;
      else if (r.outcome === "reopened") tally.reopened += 1;
      else if (r.outcome === "deduped") tally.deduped += 1;
      else return fail(`行 outcome 闭集外:${r.outcome}(${r.hid})`, inputs);
    }
    if (tally.created !== m.created || tally.reopened !== m.reopened || tally.deduped !== m.deduped)
      return fail(`计数≠rows 对账:created ${m.created}/${tally.created} reopened ${m.reopened}/${tally.reopened} deduped ${m.deduped}/${tally.deduped}`, inputs);
    const hyps = j(path.join(ctx.dir, "03-triage-hypotheses.json"))?.hypotheses ?? [];
    const dv = j(path.join(ctx.dir, "05-deep-verdicts.json")) ?? { verdicts: [], degraded: [] };
    const want = [...(dv.verdicts ?? []).map((x) => x.hid), ...(dv.degraded ?? []).map((x) => x.hid),
      ...(j(path.join(ctx.dir, "04-dispatch-bundles.json"))?.truncated ?? []).map((x) => x.hid),
      ...hyps.filter((x) => !x.need_deep).map((x) => x.signal_id)];
    if (!eqSet(want, m.rows.map((r) => r.hid))) return fail(`条目行不穷尽:want ${want.length}≠rows ${m.rows.length}(verdicts∪degraded∪truncated∪未深验)`, inputs);
    const seen = new Set();
    for (const r of m.rows) {
      if (!CLOSED_SETS.action.includes(r.suggested_action)) return fail(`suggested_action 闭集外:${r.suggested_action}(${r.hid})`, inputs);
      if (!CLOSED_SETS.severity.includes(r.severity)) return fail(`severity 闭集外:${r.severity}(${r.hid})`, inputs);
      if (r.verdict === "refuted" && r.severity !== "low") return fail(`refuted 须恒 low 消化条目(三小裁②):${r.hid} severity=${r.severity}`, inputs);
      const dk = r.dedup_key ?? {};
      const key = `${dk.source}|${dk.probe_class}|${dk.error_signature}`;
      if (r.outcome !== "deduped" && seen.has(key)) return fail(`同轮同因双开:${key}(${r.hid})`, inputs);
      seen.add(key);
      const p = path.join(ctx.itemsDir, `${r.item_id}.md`);
      if (!fs.existsSync(p)) return fail(`条目文件缺席:${r.item_id}(${r.hid})`, inputs);
      const it = parseItem(fs.readFileSync(p, "utf8"), `${r.item_id}.md`); // 坏文件宁响亮不猜测(parseItem 同口径)
      if (it.dedup_key.source !== dk.source || it.dedup_key.probe_class !== dk.probe_class || it.dedup_key.error_signature !== dk.error_signature)
        return fail(`条目树 dedup_key 与 manifest 行不同签:${r.item_id}(${key})`, inputs);
      if (r.outcome === "reopened" && (it.supersedes ?? null) !== (r.supersedes ?? null)) return fail(`复开链指不符:${r.item_id} 树=${it.supersedes} 行=${r.supersedes}`, inputs);
      if (r.outcome === "created" && it.supersedes && !r.echo) return fail(`created 行携带链指(形状漂移):${r.item_id} supersedes=${it.supersedes}`, inputs);
    }
    const sp = j(path.join(ctx.dir, "02-verify-suppressed.json"));
    if ((sp?.suppressed ?? []).length !== m.suppressed) return fail(`suppressed=${m.suppressed}≠抑制工件 ${(sp?.suppressed ?? []).length}`, inputs);
    return pass(`rows=${m.rows.length} created=${m.created} reopened=${m.reopened} deduped=${m.deduped} suppressed=${m.suppressed};真条目树读回同签,复开链指齐,零同轮双开`, inputs);
  },
  // G_SYNTH:三节齐 ∧ 计数与工件逐字一致(四计数+深验三计数,#162 审 P2-5 抽检面)∧ 判例引用闭合(复用 closureCheck)
  G_SYNTH: (ctx) => {
    const inputs = ["07-synth-report.md", "07-synth-transcript.jsonl", "06-itemize-manifest.json", "05-deep-verdicts.json", "04-dispatch-bundles.json"];
    const report = txt(path.join(ctx.dir, "07-synth-report.md"));
    const m = j(path.join(ctx.dir, "06-itemize-manifest.json"));
    if (report === null) return fail("07-synth-report.md 缺失", inputs);
    if (!m) return fail("06-itemize-manifest.json 不可解析", inputs);
    for (const sec of ["## 注入判例", "## 异常清单", "## 摘要"]) if (!report.includes(sec)) return fail(`三节缺:${sec}`, inputs);
    { // 摘要行数门(审后补 P2:提示词声明「≤10 行(门机检)」,门必须真检)
      const idx = report.indexOf("## 摘要");
      const n = report.slice(idx).trim().split("\n").length - 1;
      if (n > 10) return fail(`摘要超 10 行(实 ${n};契约 ≤10)`, inputs);
    }
    for (const k of ["created", "reopened", "deduped", "suppressed"]) {
      const occ = [...report.matchAll(new RegExp(`\\b${k}=(\\d+)`, "g"))].map((x) => +x[1]);
      if (!occ.length) return fail(`报告缺计数 ${k}=N(契约:摘要行携带四计数)`, inputs);
      if (occ.some((n) => n !== m[k])) return fail(`报告计数不符 manifest:${k} 报告=${[...new Set(occ)].join("/")}(工件=${m[k]})`, inputs);
    }
    // 深验三计数抽检(#162 审 P2-5):报告数字 = verdicts ∪ degraded(重试尽降级)∪ truncated(预算截尾)回算
    const dv = j(path.join(ctx.dir, "05-deep-verdicts.json")) ?? { verdicts: [], degraded: [] };
    const truth = { confirmed: 0, refuted: 0, unresolved: (dv.degraded ?? []).length + (j(path.join(ctx.dir, "04-dispatch-bundles.json"))?.truncated ?? []).length };
    for (const x of dv.verdicts ?? []) if (truth[x.verdict] !== undefined) truth[x.verdict] += 1;
    for (const k of ["confirmed", "refuted", "unresolved"]) {
      const occ = [...report.matchAll(new RegExp(`\\b${k}=(\\d+)`, "g"))].map((x) => +x[1]);
      if (!occ.length) return fail(`报告缺深验计数 ${k}=N(契约:摘要必含深验计数行)`, inputs);
      if (occ.some((n) => n !== truth[k])) return fail(`深验计数不符工件:${k} 报告=${[...new Set(occ)].join("/")}(回算=${truth[k]};verdicts∪degraded∪truncated)`, inputs);
    }
    const head = jsonl(path.join(ctx.dir, "07-synth-transcript.jsonl")).find((l) => l.type === "input");
    const allowed = new Set((head?.meta?.injected ?? []).map((n) => path.basename(n))); // 闭集=预注入(锚选∪检索命中;P0 无轮中检索工具)
    try { closureCheck(report, allowed); } catch (e) { return fail(`判例闭合违例:${e.message}`, inputs, "closure_check"); }
    return pass(`三节齐;四计数+深验三计数与工件逐字一致(confirmed=${truth.confirmed} refuted=${truth.refuted} unresolved=${truth.unresolved});判例引用闭合(注入 ${allowed.size})`, inputs);
  },
  // G_RETRO:retro schema 过 ∧ 台账行读回存在 ∧ sandbox rc=0(rc 由 RETRO 步实测记入 retro 工件);
  // P5 #167:候选确定性检查 schema(match 谓词闭集/动作闭集/证据非空——无证据即无话)与
  // 到点复审清单/通道矛盾清单的形状面。
  G_RETRO: (ctx) => {
    const key = ctx.retroAuditKey; // replay --dry 审原件;重执行审重放自产
    const retroFile = path.join(ctx.opsRoot, "retro", `${key}.json`);
    const inputs = [`retro/${key}.json`, "(ledger)"];
    const r = j(retroFile);
    if (!r) return fail(`retro/${key}.json 不可解析`, inputs);
    if (r.round_id !== key) return fail(`retro.round_id=${r.round_id}≠${key}`, inputs);
    if (!Array.isArray(r.candidates)) return fail("retro.candidates 非数组(候选只产条目,永不自动生效)", inputs);
    for (const c of r.candidates ?? []) {
      if (!c || typeof c !== "object" || !c.match || typeof c.match !== "object") return fail("候选缺 match 对象", inputs);
      const keys = Object.keys(c.match);
      if (!keys.length) return fail(`候选 match 空(谓词闭集 ${RULE_PREDICATES.join("/")})`, inputs);
      for (const k of keys) if (!RULE_PREDICATES.includes(k)) return fail(`候选谓词闭集外:${k}`, inputs);
      if (!RULE_ACTIONS.includes(c.action)) return fail(`候选动作闭集外:${c.action}`, inputs);
      if (typeof c.note !== "string" || !c.note) return fail("候选缺 note(人读理由面)", inputs);
      if (!c.evidence || typeof c.evidence !== "object" || !Object.keys(c.evidence).length) return fail("候选缺证据(无证据即无话)", inputs);
      if (c.item !== undefined && (!c.item || typeof c.item !== "object")) return fail("候选 item 形状非对象(skipped/outcome 二选一)", inputs);
    }
    for (const d of r.rules_due_review ?? []) {
      if (typeof d.id !== "string" || typeof d.hits_n !== "number") return fail(`到点复审行形状非法:${JSON.stringify(d).slice(0, 80)}`, inputs);
    }
    for (const x of r.channel_conflicts ?? []) {
      if (typeof x.rule_id !== "string" || typeof x.dedup_key !== "string" || !Array.isArray(x.in_flight_items)) return fail(`通道矛盾行形状非法:${JSON.stringify(x).slice(0, 80)}`, inputs);
    }
    if (r.sandbox_assert_pass !== true) return fail(`sandbox_assert rc≠0(${r.sandbox_assert_rc})`, inputs);
    const ledger = txt(ctx.ledgerFile);
    if (ledger === null || !ledger.includes(`pipeline:${key}`)) return fail("台账读回缺本轮行", inputs);
    return pass(`retro schema 过(${(r.candidates ?? []).length} 候选,到点复审 ${(r.rules_due_review ?? []).length},通道矛盾 ${(r.channel_conflicts ?? []).length});台账行读回;sandbox rc=0`, inputs);
  },
  // G_CLOSE:信封单行 JSON 落 stdout(书挡门;重放不入 CLOSE)
  G_CLOSE: (ctx) => {
    const inputs = ["(stdout 轮次信封)"];
    if (!ctx.envelope) return fail("信封未组装", inputs);
    const s = JSON.stringify(ctx.envelope);
    if (s.includes("\n")) return fail("信封非单行", inputs);
    if (JSON.parse(s).ok !== ctx.envelope.ok) return fail("信封不可往返解析", inputs);
    return pass(`信封单行 JSON 落 stdout 末行(${s.length} 字节,${ctx.envelope.pipeline?.stages?.length ?? 0} stages)`, inputs);
  },
};

// 求值 + 留痕(gates.json 追加;门自身可审计——哲学:门的判断也能被人审)
export function evalStageGate(def, ctx) {
  const t0 = performance.now();
  const g = GATES[def.gate];
  const r = g ? g(ctx) : { pass: false, reason: `未知门 ${def.gate}(定义表漂移)`, inputs: [] };
  return { stage: def.name, name: def.gate, pass: !!r.pass, reason: r.reason, dur_ms: Math.round(performance.now() - t0), inputs: r.inputs ?? [], ...(r.code ? { code: r.code } : {}) }; // code=门指定终态码(闭集内)
}
export function appendGate(dir, roundId, rec) {
  const p = path.join(dir, "gates.json");
  const cur = j(p) ?? { round_id: roundId, records: [] };
  cur.round_id = roundId;
  cur.records.push(rec);
  const t = `${p}.tmp`;
  fs.writeFileSync(t, JSON.stringify(cur, null, 2) + "\n");
  fs.renameSync(t, p); // 原子写(沿 _ops_store.atomic_write_text 判例)
}
export function appendGateBypass(dir, roundId, def, note) { // 降级旁路留痕(C稿 §2.3:RETRO 降级也过)
  appendGate(dir, roundId, { stage: def.name, name: def.gate, pass: true, reason: `stage degraded(${note}):门旁路`, dur_ms: 0, inputs: [] });
}
