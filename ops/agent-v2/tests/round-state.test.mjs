// round-state.test.mjs — #408 终态回写单源契约面(ops/agent-v2/tasks/round-state.mjs)。
// 钉三律:①盘上件为底=字段集稳定(discover 镜像 patch 只改值);②幂等——updated_at
// 保盘值不写新时钟,崩溃重入 CLOSE(=新鲜 ctx 重建、新鲜 in-memory 时钟)重写字节级
// 不变(报告件「无时钟入文」同标准);③镜像写败不掷错(v2 真源=checkpoint,终态 commit
// 在后;写败改判 failed 才是真话反转——头注判例)。round 级接线面由 discover-round /
// health-e2e 两 E2E 钉,本文件只钉单源契约。#415 加第四律:属主校验——discover/add 失败/中止
// 出口的镜像写(writeOwnedRoundState)只落本任务的轮目录;轮级接线面由 discover-round /
// add-round E2E 钉。中止包装(writeAbortRoundState)单源契约同在本文件:轮级红→绿证据在
// discover-round E2E「中止镜像写尽力不掷错」。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { writeTerminalRoundState, writeOwnedRoundState, writeAbortRoundState } from "../tasks/round-state.mjs";

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

// ── #415 属主校验:discover/add 失败/中止出口的镜像写只落本任务的轮目录 ──────────────
// 判据=建轮守卫(bootstrapRoundDir)同律:checkpoint 已提交相位,或盘上镜像=本轮自家建轮骨架。
test("#415 属主校验:已提交相位/自家建轮骨架=写终态;未建轮/异物树/同 id 旧轮终态件=不写(不改判别轮终态)", () => {
  const tmp = tmpDir();
  try {
    const ownedCtxOf = (dir, state) => ({ dir, roundId: state.round_id, state: { ...state }, log: () => {} }); // 真实 ctx 形(ctxShape/add buildCtx 带顶层 roundId;ctxOf 未带)
    const fileOf = (d) => path.join(d, "state.json");
    const textOf = (d) => fs.readFileSync(fileOf(d), "utf8");
    const seed = (d, mirror) => { fs.mkdirSync(d, { recursive: true }); fs.writeFileSync(fileOf(d), JSON.stringify(mirror, null, 2) + "\n"); return textOf(d); };
    const skel = { ...MIRROR, stages: [] }; // 建轮骨架形(bootstrap 落;首相位未提交)
    // ① checkpoint 已提交相位(stages 非空)=属主:写 failed;盘上件为底=只改 status 值
    const a = path.join(tmp, "a");
    seed(a, MIRROR);
    writeOwnedRoundState(ownedCtxOf(a, MIRROR), "failed");
    const wa = JSON.parse(textOf(a));
    assert.equal(wa.status, "failed");
    assert.equal(wa.updated_at, MIRROR.updated_at, "updated_at 保盘值(终态写无时钟)");
    assert.deepEqual(Object.keys(wa), Object.keys(MIRROR), "字段集稳定(不加 stage 键)");
    // ② 自家建轮骨架(checkpoint 零相位提交 + 盘上同轮 stages 空)=属主:首相位步抛也要写终态
    const b = path.join(tmp, "b");
    seed(b, skel);
    writeOwnedRoundState(ownedCtxOf(b, skel), "failed");
    const wb = JSON.parse(textOf(b));
    assert.equal(wb.status, "failed", "自家骨架不得停在 running(轮已终态失败)");
    assert.deepEqual(wb.stages, [], "零相位提交:stages 空不造名");
    // ③ 未建轮(无盘上件、零相位提交):不凭空造件
    const c = path.join(tmp, "c");
    fs.mkdirSync(c);
    writeOwnedRoundState(ownedCtxOf(c, skel), "failed");
    assert.equal(fs.existsSync(fileOf(c)), false, "未过建轮守卫的出口不得凭空造轮目录镜像");
    // ④ 同 id 旧轮终态件(盘上 stages 非空、checkpoint 零相位提交=异物任务撞轮目录):不改判
    const d = path.join(tmp, "d");
    const done = { ...MIRROR, status: "done", stages: [...MIRROR.stages, "MEASURE", "ENQUEUE", "RETRO", "CLOSE"] };
    const before = seed(d, done);
    writeOwnedRoundState(ownedCtxOf(d, skel), "failed");
    assert.equal(textOf(d), before, "异物任务的失败出口不得把别轮 done 改判(字节不变)");
    // ⑤ 异物树(盘上 round_id 不符):同上不写
    const e = path.join(tmp, "e");
    const other = seed(e, { ...skel, round_id: "2026-11-22-0501-discover" });
    writeOwnedRoundState(ownedCtxOf(e, skel), "failed");
    assert.equal(textOf(e), other);
    // ⑥ 中止出口同门同形:状态词透传(outcome 同词 aborted);重写字节级不变
    const f = path.join(tmp, "f");
    seed(f, MIRROR);
    writeOwnedRoundState(ownedCtxOf(f, { ...MIRROR, updated_at: "2026-11-22T08:00:00.000Z" }), "aborted");
    const f1 = textOf(f);
    writeOwnedRoundState(ownedCtxOf(f, { ...MIRROR, updated_at: "2026-11-22T09:00:00.000Z" }), "aborted");
    assert.equal(textOf(f), f1, "中止出口重写字节级一致(崩溃落在镜像写与终态 commit 之间重入)");
    assert.equal(JSON.parse(f1).status, "aborted");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

// ── #415 中止包装:abort handler 里的镜像写(含 ctx 重建)整体不掷错 ──────────────────
// 根由=abort handler 裸抛时框架把任务判 faulted、aborted outcome 丢失(pi-durable 1.4.0
// 实测);轮级红→绿证据在 discover-round.test.mjs「中止镜像写尽力不掷错」(abort 相位 ctx
// 重建抛的真实调用链)。本测只钉包装件契约:抛被吞+留注记、正常写照落。
test("#415 writeAbortRoundState:写函数抛不外抛且留 stderr 注记;正常写经它照落盘、零注记", () => {
  const tmp = tmpDir();
  const notes = [];
  const realWrite = process.stderr.write;
  process.stderr.write = (chunk) => { notes.push(String(chunk)); return true; };
  try {
    assert.doesNotThrow(() => writeAbortRoundState(() => { throw Object.assign(new Error("ctx 重建炸"), { usage: true }); }));
    assert.equal(notes.length, 1);
    assert.match(notes[0], /中止镜像写败:ctx 重建炸/);
    // 正常路:包装不改写入语义
    const dir = path.join(tmp, "rounds", "r1");
    fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, "state.json");
    fs.writeFileSync(file, JSON.stringify(MIRROR, null, 2) + "\n");
    writeAbortRoundState(() => writeTerminalRoundState(ctxOf(dir, MIRROR), { status: "aborted" }));
    assert.equal(JSON.parse(fs.readFileSync(file, "utf8")).status, "aborted");
    assert.equal(notes.length, 1, "正常写零注记");
  } finally { process.stderr.write = realWrite; fs.rmSync(tmp, { recursive: true, force: true }); }
});
