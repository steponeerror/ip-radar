// mutation-due.test.mjs — #352 票尾:变异自检月度到期提醒行(health-round RETRO 面)单测。
// 纯函数 mutationCheckDue(env, now) 四态:未见上次运行/未到期/到期/腿坏件跳过取旧件;
// appendMutationCheckDue 写面:retro 件在场补字段,缺席(降级轮)静默不加不炸。
// env 隔离:IP_RADAR_EVAL_DIR 指 tmp 报告根(backend report_dir() 同名 env,不读真树)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { mutationCheckDue, appendMutationCheckDue, MUTATION_LEG_ID, MUTATION_DUE_DAYS } from "../tasks/health-round.mjs";

const seedReport = (dir, name, { generatedAt, legs }) =>
  fs.writeFileSync(path.join(dir, name), JSON.stringify({ generated_at: generatedAt,
    rows: legs.map((ok) => ({ id: ok === null ? "fp-restraint-anchors" : MUTATION_LEG_ID, status: ok === false ? "failure" : "ok" })) }, null, 2) + "\n");

const iso = (now, daysAgo) => new Date(now.getTime() - daysAgo * 86400000).toISOString();

test("未见上次运行:报告根目录缺席 → 首跑即到期,显形不虚构", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mut-due-"));
  const r = mutationCheckDue({ IP_RADAR_EVAL_DIR: tmp }, new Date("2026-11-15T00:00:00Z"));
  assert.equal(r.due, true);
  assert.equal(r.last_run, null);
  assert.match(r.note, /未见上次运行/);
});

test("未到期:最新含变异自检腿 ok 读数的件为上次运行(31 天窗内)", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mut-due-"));
  const dir = path.join(tmp, "monthly", "model");
  fs.mkdirSync(dir, { recursive: true });
  const now = new Date("2026-11-15T00:00:00Z");
  seedReport(dir, "quality-report-20261001-000000.json", { generatedAt: iso(now, 60), legs: [true] });
  seedReport(dir, "quality-report-20261110-000000.json", { generatedAt: iso(now, 5), legs: [true] });
  const r = mutationCheckDue({ IP_RADAR_EVAL_DIR: tmp }, now);
  assert.equal(r.due, false);
  assert.equal(r.last_run, iso(now, 5).slice(0, 10));
  assert.equal(r.window_days, MUTATION_DUE_DAYS);
});

test("到期:上次运行已越 31 天窗 → due=true 带天数读数;边界天(恰 31 天)到点即入(仿 rules_due_review ≤ 今日语义,评审 P2-1)", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mut-due-"));
  const dir = path.join(tmp, "monthly", "model");
  fs.mkdirSync(dir, { recursive: true });
  const now = new Date("2026-11-15T00:00:00Z");
  seedReport(dir, "quality-report-20261001-000000.json", { generatedAt: iso(now, 40), legs: [true] });
  const r = mutationCheckDue({ IP_RADAR_EVAL_DIR: tmp }, now);
  assert.equal(r.due, true);
  assert.equal(r.age_days, 40);
  assert.match(r.note, /月度到期/);
  // 边界:恰 31 天 = 窗尽当日,到点即入(与被仿先例 review_at <= today 同语义)
  const tmpB = fs.mkdtempSync(path.join(os.tmpdir(), "mut-due-"));
  const dirB = path.join(tmpB, "monthly", "model");
  fs.mkdirSync(dirB, { recursive: true });
  seedReport(dirB, "quality-report-20261015-000000.json", { generatedAt: iso(now, 31), legs: [true] });
  const rb = mutationCheckDue({ IP_RADAR_EVAL_DIR: tmpB }, now);
  assert.equal(rb.due, true);
  assert.equal(rb.age_days, 31);
});

test("腿坏件不算上次运行:最新件变异腿 failure/无腿 → 取旧件 ok 读数;全无 → 未见上次运行", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mut-due-"));
  const dir = path.join(tmp, "monthly", "model");
  fs.mkdirSync(dir, { recursive: true });
  const now = new Date("2026-11-15T00:00:00Z");
  seedReport(dir, "quality-report-20261114-000000.json", { generatedAt: iso(now, 1), legs: [false] }); // 崸腿(未验证)
  seedReport(dir, "quality-report-20261113-000000.json", { generatedAt: iso(now, 2), legs: [null] });  // 无变异腿(旧代报告)
  seedReport(dir, "quality-report-20261101-000000.json", { generatedAt: iso(now, 14), legs: [true] });  // ok → 上次运行
  const r = mutationCheckDue({ IP_RADAR_EVAL_DIR: tmp }, now);
  assert.equal(r.due, false);
  assert.equal(r.last_run, iso(now, 14).slice(0, 10));
  fs.rmSync(path.join(dir, "quality-report-20261101-000000.json"));
  const none = mutationCheckDue({ IP_RADAR_EVAL_DIR: tmp }, now);
  assert.equal(none.last_run, null, "坏件/无腿件不得充当上次运行");
});

test("appendMutationCheckDue:retro 件在场补字段(writeJson 同格式);缺席静默不炸", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mut-due-"));
  const prev = process.env.IP_RADAR_EVAL_DIR;
  process.env.IP_RADAR_EVAL_DIR = tmp; // 隔离:不读真树报告根
  try {
    const retroFile = path.join(tmp, "retro.json");
    fs.writeFileSync(retroFile, JSON.stringify({ round_id: "r", candidates: [] }, null, 2) + "\n");
    appendMutationCheckDue({ retroFile });
    const r = JSON.parse(fs.readFileSync(retroFile, "utf8"));
    assert.equal(r.round_id, "r", "既有字段不动");
    assert.ok(r.mutation_check_due && typeof r.mutation_check_due.due === "boolean");
    assert.ok(fs.readFileSync(retroFile, "utf8").endsWith("\n"));
    assert.doesNotThrow(() => appendMutationCheckDue({ retroFile: path.join(tmp, "absent.json") }));
  } finally {
    if (prev === undefined) delete process.env.IP_RADAR_EVAL_DIR; else process.env.IP_RADAR_EVAL_DIR = prev;
  }
});
