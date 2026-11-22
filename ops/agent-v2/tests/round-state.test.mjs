// round-state.test.mjs — #408 终态回写单源契约面(ops/agent-v2/tasks/round-state.mjs)。
// 钉三律:①盘上件为底=字段集稳定(discover 镜像 patch 只改值);②幂等——updated_at
// 保盘值不写新时钟,崩溃重入 CLOSE(=新鲜 ctx 重建、新鲜 in-memory 时钟)重写字节级
// 不变(报告件「无时钟入文」同标准);③镜像写败不掷错(v2 真源=checkpoint,终态 commit
// 在后;写败改判 failed 才是真话反转——头注判例)。round 级接线面由 discover-round /
// health-e2e 两 E2E 钉,本文件只钉单源契约。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { writeTerminalRoundState } from "../tasks/round-state.mjs";

const tmpDir = () => fs.mkdtempSync(path.join(os.tmpdir(), "v2-round-state-"));
const MIRROR = { // discover v2 镜像同形(buildCtx state 面;bootstrap/advance 落)
  schema: 1, round_id: "2026-11-22-0500-discover", type: "discover", pipeline_mode: "pipeline",
  status: "running", stages: ["SCAN", "SHORTLIST"], budget_cny: 0.05, budget_knobs: { a: 1 },
  fixtures_dir: null, model_face: "faux", prompt_hashes: {}, started_at: "2026-11-22T05:00:00.000Z",
  updated_at: "2026-11-22T05:01:00.000Z", resume_count: 0, replay_of: null, monthly_admission: null,
};
const ctxOf = (dir, state) => ({ dir, state: { ...state }, log: () => {} });

test("#408 盘上件为底:patch 只改 status/stages 值,updated_at 保盘值(不加字段不改钟)", () => {
  const tmp = tmpDir();
  try {
    fs.writeFileSync(path.join(tmp, "state.json"), JSON.stringify(MIRROR, null, 2) + "\n");
    const ok = writeTerminalRoundState(ctxOf(tmp, MIRROR), { status: "done", stages: ["SCAN", "SHORTLIST", "MEASURE", "ENQUEUE", "RETRO", "CLOSE"] });
    assert.equal(ok, true);
    const next = JSON.parse(fs.readFileSync(path.join(tmp, "state.json"), "utf8"));
    assert.equal(next.status, "done");
    assert.equal(next.updated_at, MIRROR.updated_at, "updated_at 保盘值(镜像推进钟不动=终态写无时钟)");
    assert.deepEqual(Object.keys(next), Object.keys(MIRROR), "字段集稳定(只改值不加键)");
    assert.equal(next.stages.length, 6);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("#408 幂等:重复 CLOSE 字节级不变(重入=新鲜 ctx 重建,updated_at 时钟各异)", () => {
  const tmp = tmpDir();
  try {
    fs.writeFileSync(path.join(tmp, "state.json"), JSON.stringify(MIRROR, null, 2) + "\n");
    // 两次独立调用模拟崩溃重入 close:各自 buildCtx/rebuildRoundCtx 现读新钟
    const a = writeTerminalRoundState(ctxOf(tmp, { ...MIRROR, updated_at: "2026-11-22T06:00:00.000Z" }), { status: "done", stages: ["SCAN", "CLOSE"] });
    const b1 = fs.readFileSync(path.join(tmp, "state.json"), "utf8");
    const b = writeTerminalRoundState(ctxOf(tmp, { ...MIRROR, updated_at: "2026-11-22T07:30:00.000Z" }), { status: "done", stages: ["SCAN", "CLOSE"] });
    const b2 = fs.readFileSync(path.join(tmp, "state.json"), "utf8");
    assert.ok(a && b);
    assert.equal(b2, b1, "重复 CLOSE 重写字节级一致(#408 票面幂等律)");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("#408 无盘上件(health 首写):以 ctx.state 全形起底;stage/stages 覆写;再写仍幂等", () => {
  const tmp = tmpDir();
  try {
    const healthState = { ...MIRROR, type: "health", pipeline_mode: "pidurable", stage: "CLOSE",
      stages: [{ name: "RETRO", status: "done", attempts: 1, dur_ms: 3, usage: null }, { name: "CLOSE", status: "done", attempts: 1, dur_ms: 0, usage: null }] };
    const ctx = ctxOf(tmp, healthState);
    assert.equal(writeTerminalRoundState(ctx, { status: "done" }), true);
    const first = fs.readFileSync(path.join(tmp, "state.json"), "utf8");
    const st = JSON.parse(first);
    assert.equal(st.status, "done");
    assert.equal(st.stage, "CLOSE");
    assert.equal(st.stages[1].name, "CLOSE", "健康面 stages=全记录形(rebuildRoundCtx ctx.state)");
    // 重入(新鲜 ctx、新鲜钟):盘上件为底 → 字节不变
    writeTerminalRoundState(ctxOf(tmp, { ...healthState, updated_at: "2026-11-22T09:00:00.000Z" }), { status: "done" });
    assert.equal(fs.readFileSync(path.join(tmp, "state.json"), "utf8"), first);
    // 失败书挡覆写:stage=FAILED(v1 failStage 对)
    writeTerminalRoundState(ctx, { status: "failed", stage: "FAILED" });
    const fin = JSON.parse(fs.readFileSync(path.join(tmp, "state.json"), "utf8"));
    assert.equal(fin.status, "failed");
    assert.equal(fin.stage, "FAILED");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("#408 镜像写败不掷错:只返 false(真源=checkpoint;终态写败改判 failed=真话反转,头注判例)", () => {
  const tmp = tmpDir();
  try {
    const dir = path.join(tmp, "rounds", "r1"); // 未 mkdir → 写败路径
    const ok = writeTerminalRoundState(ctxOf(dir, MIRROR), { status: "done" });
    assert.equal(ok, false);
    assert.equal(fs.existsSync(path.join(dir, "state.json")), false);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
