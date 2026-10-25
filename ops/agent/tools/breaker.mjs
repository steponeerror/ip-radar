// breaker.mjs — 跨轮通道熔断器(#199 交付B;STANDARD.md P16;GLOSSARY「跨轮熔断」)
// 状态面=DOCS_ROOT/ops/breaker.json(跨轮持久;原子写=tmp+renameSync,_ops_store 判例)。
// 通道粒度=恰五员(工具名即通道名);计数码闭集=恰三员(宁少算:transient/gh_error/
// io_error/http_error/network 属暂态/IO 抖动,不构成通道死亡证据,不计入——铁律③)。
// 状态文件损坏/缺失=fail-closed 重置为闭路(空态)不炸轮:证据坏=无证据,不开断(铁律②)。
// 留痕:opened/reopened/recovered 三转移写台账行(ledger_append,写败不抛=appendRefusalTrace
// 判例)+状态文件内 events 环(≤20,RETRO 可回读面)。
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { DOCS_ROOT } from "./shared.mjs";

// 通道闭集(spec #199 交付B:恰五员;探针三件 probe_head/reprobe_get/reprobe_ua 不属通道面)
export const BREAKER_CHANNELS = ["fetch_url", "gh_search", "rss_parse", "web_read", "web_search"];
// 计数码闭集(spec #199 交付B:恰三员;部署级/账号级持久证据才计入熔断)
export const BREAKER_COUNTED_CODES = ["channel_auth", "channel_missing", "quota"];
export const BREAKER_STATE_VOCAB = ["closed", "open", "half_open"];
const TRANSITIONS = ["opened", "reopened", "recovered"]; // 台账/RETRO 留痕面(恰三转移)

// 旋钮读面(校验同 budget.readKnob 判例:非负有限,非法={usage:true} 由调用方转用法错;
// threshold=0=禁用熔断,同 OPS_PIPELINE_DUP_CALL_LIMIT=0 停用判例——自决,记录 B-REPORT。
// 字面点式读=spawn 契约扫描器收录形(selftest-contract 对拍:每个 OPS_* 读取 ∈ 表))
const readKnob = (name, raw, fallback) => {
  if (raw === undefined || raw === "") return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) throw Object.assign(new Error(`${name} 非法:${raw}(须非负数)`), { usage: true });
  return n;
};
export function readBreakerKnobs(env = process.env) {
  return {
    threshold: readKnob("OPS_BREAKER_THRESHOLD", env?.OPS_BREAKER_THRESHOLD ?? process.env.OPS_BREAKER_THRESHOLD, 3), // 连续计数码失败次数→开断
    cooldownS: readKnob("OPS_BREAKER_COOLDOWN_S", env?.OPS_BREAKER_COOLDOWN_S ?? process.env.OPS_BREAKER_COOLDOWN_S, 21600), // 6h 冷却;重开=新整窗,无指数退避(spec:冷却不变)
  };
}

export const emptyBreakerState = () => ({ version: 1, channels: {}, events: [] });
const channelOf = (state, name) => state.channels[name] ?? { state: "closed", consec: 0 };
const cloneState = (state) => JSON.parse(JSON.stringify(state));

// fail-closed 解析:任何形状偏离→null(调用方重置空闭路态;宁少算:坏文件不开断也不炸轮)
export function parseBreakerState(text) {
  let s;
  try { s = JSON.parse(text); } catch { return null; }
  if (!s || typeof s !== "object" || s.version !== 1 || !s.channels || typeof s.channels !== "object") return null;
  for (const [name, ch] of Object.entries(s.channels)) {
    if (!BREAKER_CHANNELS.includes(name)) return null;
    if (!BREAKER_STATE_VOCAB.includes(ch?.state)) return null;
    if (!Number.isInteger(ch.consec) || ch.consec < 0) return null;
    if (ch.opened_at !== undefined && ch.opened_at !== null && !Number.isFinite(ch.opened_at)) return null;
  }
  if (s.events !== undefined && !Array.isArray(s.events)) return null;
  return s;
}

// 纯核判读:closed→allow;open 且冷却未到→block;open 且冷却已到→probe(半开探活恰一次);
// half_open→block(探活在飞,余量闭——防并发第二调用蹭探活名额)。
export function verdictFor(state, name, nowMs, { threshold, cooldownS }) {
  if (threshold <= 0) return { action: "allow", channel: name }; // 禁用
  const ch = channelOf(state, name);
  if (ch.state === "closed") return { action: "allow", channel: name };
  if (ch.state === "half_open") return { action: "block", channel: name, probe_in_flight: true };
  const elapsedMs = nowMs - (ch.opened_at ?? 0);
  if (elapsedMs >= cooldownS * 1000) return { action: "probe", channel: name };
  return { action: "block", channel: name, retryAfterS: Math.max(1, Math.ceil((cooldownS * 1000 - elapsedMs) / 1000)) };
}

// open→half_open(探活放行前同步落盘;耗掉唯一名额)
export function grantProbe(state, name, nowMs) {
  const s = cloneState(state);
  s.channels[name] = { ...channelOf(s, name), state: "half_open", probe_at: nowMs };
  return s;
}

const pushEvent = (state, ev) => { state.events = [...(state.events ?? []), ev].slice(-20); }; // RETRO 回读环(≤20)

// 纯核结算:成功清零(半开→恢复闭路);计数码失败累连续(threshold 次开断;半开失败→重开新整窗);
// 非计数码失败不改状态——唯一例外:半开探活名额已耗而失败非计数码→退回 open 原 opened_at
// (暂态不算通道死亡;下个冷却窗自动再探,宁少算且不困死)。changed=false 时调用方零写。
export function applyResult(state, name, { ok, code }, nowMs, { threshold, cooldownS }) {
  const s = cloneState(state);
  const ch = channelOf(s, name);
  if (threshold <= 0) return { state: s, transition: null, changed: false };
  if (ok) {
    if (ch.state === "closed" && ch.consec === 0) return { state: s, transition: null, changed: false };
    s.channels[name] = { state: "closed", consec: 0, opened_at: null, probe_at: null, last_code: code ?? null };
    if (ch.state !== "closed") pushEvent(s, { at: nowMs, transition: "recovered", channel: name, code: code ?? null });
    return { state: s, transition: "recovered", changed: true };
  }
  const counted = BREAKER_COUNTED_CODES.includes(code);
  if (!counted) {
    if (ch.state === "half_open") {
      s.channels[name] = { ...ch, state: "open" };
      return { state: s, transition: null, changed: true };
    }
    return { state: s, transition: null, changed: false };
  }
  const consec = (ch.state === "closed" ? ch.consec : 0) + 1; // 开断/重开后续算(半开名额=新证据链)
  if (ch.state === "closed" && consec < threshold) {
    s.channels[name] = { ...ch, consec, last_code: code };
    return { state: s, transition: null, changed: true };
  }
  const transition = ch.state === "closed" ? "opened" : "reopened"; // open 途中 counted 失败=防防御重开
  s.channels[name] = { state: "open", consec, opened_at: nowMs, last_code: code };
  pushEvent(s, { at: nowMs, transition, channel: name, code, consec });
  return { state: s, transition, changed: true };
}

// 观察快照(09-budget.json readings.breaker 面;闭集五员恒全列,缺省闭路)
export const breakerSnapshot = (state, knobs) => ({
  threshold: knobs.threshold, cooldown_s: knobs.cooldownS,
  channels: Object.fromEntries(BREAKER_CHANNELS.map((n) => {
    const ch = channelOf(state, n);
    return [n, { state: ch.state, consec: ch.consec, opened_at: ch.opened_at ?? null }];
  })),
});

const LIBSH = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "lib.sh"); // ops/agent/lib.sh(steps.mjs sh()/budget.mjs appendRefusalTrace 同形)
const docsRootOf = (env) => env?.DOCS_ROOT ?? process.env.DOCS_ROOT ?? DOCS_ROOT;

// 有态壳:每次操作重读状态文件(跨进程可见,last-write-wins;轮内频度低,同步 fs 足够——自决)。
export function mkBreaker({ file, env, round = "discover", ledgerFile: ledgerOpt, knobs: knobsOpt, log = () => {} } = {}) {
  const e = env ?? process.env;
  const filePath = file ?? path.join(docsRootOf(e), "ops", "breaker.json");
  const knobs = knobsOpt ?? readBreakerKnobs(e); // 构造期读=轮次调用期(同 dupLimit 判例);调用方已轮始校验可注入
  const ledgerFile = ledgerOpt ?? e.LEDGER_FILE ?? process.env.LEDGER_FILE ?? path.join(docsRootOf(e), "ops", "ledger.md");
  const now = () => Date.now();
  const load = () => {
    try { return parseBreakerState(fs.readFileSync(filePath, "utf8")) ?? emptyBreakerState(); }
    catch { return emptyBreakerState(); }
  };
  const persist = (state) => {
    try {
      fs.mkdirSync(path.dirname(filePath), { recursive: true }); // 生产首轮自动建目录/文件(CHANGELOG 注记)
      const tmp = `${filePath}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify(state, null, 2) + "\n");
      fs.renameSync(tmp, filePath);
      return true;
    } catch (err) { log(`breaker 状态写败(不炸轮,宁少算续用内存态):${err.message}`); return false; }
  };
  const ledgerNote = (transition, name, code, consec) => { // 三转移写台账(写败不抛,appendRefusalTrace 判例)
    try {
      execFileSync("bash", ["-c", '. "$0"; ledger_append "$@"', LIBSH, round, "—", "—",
        `breaker_${transition} channel=${name} code=${code ?? "ok"} consec=${consec ?? 0}(OPS_BREAKER_THRESHOLD=${knobs.threshold})`],
        { env: { ...process.env, ...e, LEDGER_FILE: ledgerFile }, stdio: "ignore" });
    } catch (err) { log(`breaker 台账留痕写败(不炸轮):${err.message}`); }
  };
  return {
    file: filePath, knobs,
    verdict(name) {
      if (!BREAKER_CHANNELS.includes(name) || knobs.threshold <= 0) return { action: "allow", channel: name };
      const st = load();
      const v = verdictFor(st, name, now(), knobs);
      if (v.action === "probe") persist(grantProbe(st, name, now())); // 名额授予即落盘(并发第二调用见 half_open=block)
      return v;
    },
    record(name, res) {
      if (!BREAKER_CHANNELS.includes(name) || knobs.threshold <= 0) return null;
      const st = load();
      const { state, transition, changed } = applyResult(st, name, res, now(), knobs);
      if (changed) persist(state);
      if (TRANSITIONS.includes(transition))
        ledgerNote(transition, name, res.code, state.channels[name]?.consec);
      return transition;
    },
    snapshot() { return { file: filePath, ...breakerSnapshot(load(), knobs) }; }, // 只读观察面(回声律:不造文件)
  };
}
