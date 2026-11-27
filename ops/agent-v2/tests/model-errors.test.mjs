// model-errors.test.mjs — 票 #490(第四轮评审卡 25)单元面:模型失败面限流分类
// (classifyModelError)+ 并发/退避旋钮取值(maxModelInflight/retryBackoffS)。
// 分类样例出处=2026-11-27 实测报文:429 + 正文 {"code":"1302"}(账户级并发上限,等待重试
// 无效);非 1302 的 429/限流说法=单请求限流(可退避重试)。旋钮 env 直读纪律=只在本模块
// 两个小函数(selftest-contract 对拍面同源);非法值→缺省+一行 stderr 告警。
import test from "node:test";
import assert from "node:assert/strict";
import { classifyModelError, maxModelInflight, retryBackoffS } from "../tasks/model-errors.mjs";

// 捕获 stderr 一行告警(旋钮非法值面;stdout 是信封专线,告警必须走 stderr——断言钉住)
function captureStderr(fn) {
  const lines = [];
  const orig = process.stderr.write;
  process.stderr.write = (chunk) => { lines.push(String(chunk)); return true; };
  try { const v = fn(); return { value: v, lines }; } finally { process.stderr.write = orig; }
}

// ── classifyModelError:三分闭表 ────────────────────────────────────────────────
test("classifyModelError:429+1302=账户级;429 非 1302/限流说法=单请求;其余=null", () => {
  // 实测账户级报文逐字(2026-11-27;formatProviderError "<status>: <body>" 形)
  assert.equal(classifyModelError('429: {"code":"1302","message":"您的账户已达到速率限制，请您控制请求频率"}'), "account_rate_limited");
  // 前缀括号形 "<prefix> (<status>): <body>"(formatProviderError 第二形)也认
  assert.equal(classifyModelError('glm-4.7 (429): {"code":"1302","message":"您的账户已达到速率限制"}'), "account_rate_limited");
  // 单请求限流:429 但正文无 1302
  assert.equal(classifyModelError('429: {"code":"1210","message":"并发other"}'), "rate_limited");
  assert.equal(classifyModelError("429: rate limit exceeded, slow down"), "rate_limited");
  // 无状态码前缀但正文是限流说法(兜底面)
  assert.equal(classifyModelError("Too Many Requests"), "rate_limited");
  // 其余=null(500/普通异常/请求 id 里的数字不误当状态码/空与非字符串)
  assert.equal(classifyModelError("500: internal error"), null);
  assert.equal(classifyModelError("req 4292: upstream hiccup"), null, "请求 id 数字不得误当状态码");
  assert.equal(classifyModelError("model returned no text"), null);
  assert.equal(classifyModelError(""), null);
  assert.equal(classifyModelError(null), null);
  assert.equal(classifyModelError(undefined), null);
  assert.equal(classifyModelError(42), null);
});

// ── 旋钮取值:缺省/合法/非法+告警 ──────────────────────────────────────────────
test("maxModelInflight:未设=2;整数≥1 照用;非法=缺省 2+一行 stderr 告警", () => {
  const prev = process.env.OPS_MODEL_MAX_INFLIGHT;
  try {
    delete process.env.OPS_MODEL_MAX_INFLIGHT;
    assert.equal(captureStderr(maxModelInflight).value, 2, "未设=缺省 2(轮内 2 路,给同账户其他工作留 1 路)");
    process.env.OPS_MODEL_MAX_INFLIGHT = "1";
    assert.equal(captureStderr(maxModelInflight).value, 1);
    process.env.OPS_MODEL_MAX_INFLIGHT = "4";
    assert.equal(captureStderr(maxModelInflight).value, 4);
    for (const bad of ["abc", "0", "-2", "1.5", ""]) {
      process.env.OPS_MODEL_MAX_INFLIGHT = bad;
      const { value, lines } = captureStderr(maxModelInflight);
      assert.equal(value, 2, `非法值 ${JSON.stringify(bad)} → 缺省 2`);
      assert.equal(lines.length, 1, `非法值 ${JSON.stringify(bad)} 恰一行告警`);
      assert.match(lines[0], /OPS_MODEL_MAX_INFLIGHT/);
    }
  } finally {
    if (prev === undefined) delete process.env.OPS_MODEL_MAX_INFLIGHT; else process.env.OPS_MODEL_MAX_INFLIGHT = prev;
  }
});

test("retryBackoffS:未设=30;非负数(含小数/0)照用;非法=缺省 30+一行 stderr 告警", () => {
  const prev = process.env.OPS_MODEL_RETRY_BACKOFF_S;
  try {
    delete process.env.OPS_MODEL_RETRY_BACKOFF_S;
    assert.equal(captureStderr(retryBackoffS).value, 30, "未设=缺省 30(智谱 429 无 Retry-After 读数,票面定值)");
    process.env.OPS_MODEL_RETRY_BACKOFF_S = "0";
    assert.equal(captureStderr(retryBackoffS).value, 0, "0=关掉退避(测试面)");
    process.env.OPS_MODEL_RETRY_BACKOFF_S = "1.5";
    assert.equal(captureStderr(retryBackoffS).value, 1.5, "小数照用(测试面)");
    for (const bad of ["abc", "-1", ""]) {
      process.env.OPS_MODEL_RETRY_BACKOFF_S = bad;
      const { value, lines } = captureStderr(retryBackoffS);
      assert.equal(value, 30, `非法值 ${JSON.stringify(bad)} → 缺省 30`);
      assert.equal(lines.length, 1, `非法值 ${JSON.stringify(bad)} 恰一行告警`);
      assert.match(lines[0], /OPS_MODEL_RETRY_BACKOFF_S/);
    }
  } finally {
    if (prev === undefined) delete process.env.OPS_MODEL_RETRY_BACKOFF_S; else process.env.OPS_MODEL_RETRY_BACKOFF_S = prev;
  }
});
