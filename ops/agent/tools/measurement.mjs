// tools/measurement.mjs — 测量类工具(硬门数字唯一生产线;铁律③:测量工具恒带
// trace{cmd,rc,artifact})。health_snapshot/fetch_url/gh_search/exclusive_probe/
// matrix_scan_summary = MEASUREMENT_TOOLS 闭集(evidence 语义门只认这五个的结构化
// 返回;闭集常量在 registry.mjs 单源)。CLI 单源(matrixScanCli/anchorSweepCli)与
// 工件序列化(matrixArtifactText)供管线面共用(#163/#182 位等价)。
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { Type } from "@earendil-works/pi-ai";
import { B, DATA_DIR, EVAL_PY, ROOT, FROZEN_DAYS, safeFetch, runLib, artifactPath, execFileP } from "./shared.mjs";
import { envelope, classifyChannelError } from "./envelope.mjs";

// ── matrix 扫描 CLI 单源(P1,#163)───────────────────────────────────────────
// tools.mjs health_snapshot(matrix 腿)与 pipeline/steps.mjs PROBE 共用同一调用路径:
// 位等价=同 EVAL_PY 命令+同解析+同工件序列化(matrixArtifactText);legacy 侧零行为改动
// (runMatrixScan 只剩三分支收编的薄包装)。返回分支:
//   {ok:true, d, rc, cmd}               读数(rc 0/1/2 都是读数,round.sh T3 判例)
//   {ok:false, env, cmd, trace:null}     stdout 带 error 键的失败信封(无 trace,同原语义)
//   {ok:false, env, cmd, trace:{cmd,rc}} 裸失败信封(带 trace)
export async function matrixScanCli() {
  const cmd = `cd backend && IP_RADAR_DATA_DIR=${DATA_DIR} ${EVAL_PY} -m ipdb._eval --matrix-scan --json --assets-dir ${DATA_DIR}/eval/assets`;
  try {
    const { stdout } = await execFileP(EVAL_PY,
      ["-m", "ipdb._eval", "--matrix-scan", "--json", "--assets-dir", `${DATA_DIR}/eval/assets`],
      { cwd: path.join(ROOT, "backend"), env: { ...process.env, IP_RADAR_DATA_DIR: DATA_DIR },
        timeout: B.matrixTimeoutMs, maxBuffer: 32 * 1024 * 1024 });
    const d = JSON.parse(stdout);
    if (d.error) return { ok: false, env: envelope(d.error.code ?? "matrix_failed", d.error.message ?? ""), cmd, trace: null };
    return { ok: true, d, rc: 0, cmd };
  } catch (e) {
    // rc 0/1/2 = 读数(干净/pending/violation,round.sh T3 判例);execFile 对非零退出 reject,
    // 但 stdout 携带带 exit_code 的有效 JSON 时仍是读数不是故障
    try {
      const d = JSON.parse(String(e.stdout ?? ""));
      if (typeof d.exit_code === "number") return { ok: true, d, rc: e.code ?? 0, cmd };
      if (d.error) return { ok: false, env: envelope(d.error.code ?? "matrix_failed", d.error.message ?? ""), cmd, trace: null };
    } catch { /* 裸失败走信封 */ }
    return { ok: false, env: envelope("matrix_failed", String(e.stderr ?? e.message ?? "").slice(0, 300)), cmd, trace: { cmd, rc: e.code ?? 1 } };
  }
}
export const matrixArtifactText = (d) => JSON.stringify(d, null, 1); // matrix 工件序列化单源:legacy <ts>-matrix-scan.json 与管线 01-probe-matrix.json 逐字节同文(#163 位等价)
// ── ops 轮锚巡检 CLI 单源(票 #182;matrixScanCli 同型先例)──────────────
// 面向 python -m ipdb._eval --anchor-sweep --json(求值核=ipdb/_eval/anchors.py
// anchor_sweep;OPS_EVAL_PY/OPS_DATA_DIR 桥=backend _round_env 注入,容器内
// 解释器与数据面=后端查询进程同一套——读数即生产读数,零认证零网络)。
// 返回分支同 matrixScanCli 三形:
//   {ok:true, d, rc:0, cmd}               读数(锚 finding 在场仍 rc 0=读数非故障,
//                                           不持门语义在 CLI 面)
//   {ok:false, env, cmd, trace:null}      stdout 带 error 键的失败信封(load_db 等)
//   {ok:false, env, cmd, trace:{cmd,rc}}  裸失败(通道四码兼容:ENOENT/超时/限流/
//                                           鉴权族过 classifyChannelError 四码;
//                                           gh_error/rg_infra 兑底码是 gh/rg 专属
//                                           不复用于 python 面,兑底归 infra)
export async function anchorSweepCli({ evalPy = EVAL_PY, dataDir = DATA_DIR, timeoutMs = B.anchorSweepTimeoutMs } = {}) {
  const cmd = `cd backend && IP_RADAR_DATA_DIR=${dataDir} ${evalPy} -m ipdb._eval --anchor-sweep --json`;
  try {
    const { stdout } = await execFileP(evalPy,
      ["-m", "ipdb._eval", "--anchor-sweep", "--json"],
      { cwd: path.join(ROOT, "backend"), env: { ...process.env, IP_RADAR_DATA_DIR: dataDir },
        timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024 });
    const d = JSON.parse(stdout);
    if (d.error) return { ok: false, env: envelope(d.error.code ?? "anchor_sweep_failed", d.error.message ?? ""), cmd, trace: null };
    return { ok: true, d, rc: 0, cmd };
  } catch (e) {
    try {
      const d = JSON.parse(String(e.stdout ?? ""));
      if (d.error) return { ok: false, env: envelope(d.error.code ?? "anchor_sweep_failed", d.error.message ?? ""), cmd, trace: null };
    } catch { /* 裸失败走信封 */ }
    const c = classifyChannelError(e, "python");
    if (["channel_missing", "channel_auth", "quota", "transient"].includes(c.code))
      return { ok: false, env: envelope(c.code, c.reason), cmd, trace: { cmd, rc: c.rc } };
    return { ok: false, env: envelope("infra", String(e.stderr ?? e.message ?? "").slice(0, 300)), cmd, trace: { cmd, rc: c.rc } };
  }
}
// ghIssueCreate——开 gh issue(出口只写不动作两写口之一;失败永不抛,分类信封同 gh_search 四码)。
// dryRun=只记将发命令零 spawn(OPS_SWEEP_DRY_RUN 面的执行侧;测试恒 dry-run)。
// 返回:{ok,dry_run,cmd,issue_url(真发成功=gh stdout 末行 URL;否则 null),error?:{code,reason}}。
export async function ghIssueCreate({ title, body, labels = ["needs-triage"] } = {}, { dryRun = false, exec = execFileP, timeoutMs = B.ghTimeoutMs } = {}) {
  const argv = ["issue", "create", "--title", String(title ?? ""), "--body", String(body ?? ""),
    ...labels.flatMap((l) => ["--label", String(l)])];
  const cmd = `gh ${argv.map((a) => (/\s/.test(a) ? `"${a}"` : a)).join(" ")}`;
  if (dryRun) return { ok: true, dry_run: true, cmd, issue_url: null };
  try {
    const { stdout } = await exec("gh", argv, { timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024 });
    return { ok: true, dry_run: false, cmd, issue_url: String(stdout ?? "").trim().split("\n").pop() || null };
  } catch (e) {
    const cls = classifyChannelError(e, "gh");
    return { ok: false, dry_run: false, cmd, issue_url: null, error: { code: cls.code, reason: cls.reason.slice(0, 300) } };
  }
}
export function countFeedKeys(text) { // probe 键量:IPv4 去重(exclusive.py _IP_RE 同口径的 v4 面)
  return new Set(text.match(/(\d{1,3}\.){3}\d{1,3}(\/\d{1,2})?/g)?.map((t) => t.split("/")[0]) ?? []).size;
}

// ── 工具方法(实现零改动,经门面 Object.assign 挂 ToolHost.prototype;方法网
// healthSnapshot→runMatrixScan/matrixFromResult、exclusiveProbe→probeQueue→
// runExclusiveProbe 同文件闭合;宿主态经 this 共享)─────────────────────────
export const measurementMethods = {
  // ── 健康轮唯一工具:零参快照(旗标+计数进上下文,全量落工件;flash 无 search/read)──
  healthSnapshot() {
    return {
      name: "health_snapshot",
      label: "健康快照",
      description: "零参。本地实测:全部源 feed 冻结检测(HEAD/Last-Modified)+ 语义矩阵违例扫描。返回旗标与计数(全量原始读数落工件文件);matrix 失败以嵌套信封呈现,不算轮次失败。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({}),
      outputSchema: Type.Object({
        ok: Type.Boolean(), urls_n: Type.Number(), frozen_n: Type.Number(), near_band_n: Type.Number(),
        unreachable_n: Type.Number(), no_lm_n: Type.Number(), token_required_n: Type.Number(),
        matrix_ok: Type.Boolean(), matrix_exit_code: Type.Number(),
        artifacts: Type.Array(Type.String()),
      }),
      execute: async (callId) => {
        const arts = [];
        try {
          const { stdout: urlOut } = await runLib("extract_feed_urls", [], 120_000);
          const urls = urlOut.split("\n").map((s) => s.trim()).filter(Boolean);
          if (!urls.length) throw Object.assign(new Error("extract_feed_urls 零 URL"), { code: "extract_failed" });
          const { stdout: tsv } = await runLib("feed_freshness", urls, 900_000);
          // TSV 四类读数(P1 T2 修约,spec #152 §2a:401/403 → TOKEN_REQUIRED
          // 需令牌·正常——不算不可达不进 unreachable,与 NO-LM 同待遇只计数;
          // 契约修约判例 2026-10-20:消费方未现=修约非违约)
          const frozen = [], near = [], unreachable = [], noLm = [], tokenReq = [];
          for (const line of tsv.trimEnd().split("\n")) {
            const [url, lm, age] = line.split("\t");
            if (age === "UNREACHABLE") unreachable.push(url);
            else if (age === "TOKEN_REQUIRED") tokenReq.push(url);
            else if (age === "NO-LM") noLm.push(url);
            else {
              const a = +age;
              if (a >= FROZEN_DAYS) frozen.push({ url, last_modified: lm, age_days: a });
              else if (a >= 90) near.push({ url, age_days: a });
            }
          }
          const tsvArt = artifactPath(this.artifactDir, "health-freshness", "tsv");
          fs.writeFileSync(tsvArt, tsv);
          arts.push(tsvArt);
          const matrix = await this.runMatrixScan(arts);
          const st = {
            ok: true, urls_n: urls.length, frozen, frozen_n: frozen.length, near_band: near, near_band_n: near.length,
            unreachable, unreachable_n: unreachable.length, no_lm_n: noLm.length,
            token_required: tokenReq, token_required_n: tokenReq.length,
            matrix_ok: matrix.ok, matrix_exit_code: matrix.exit_code ?? -1,
            matrix: matrix.ok ? matrix : { envelope: matrix }, artifacts: arts,
          };
          const c = [`源 URL ${urls.length};冻结≥${FROZEN_DAYS}天 ${frozen.length};近带(90-179) ${near.length};不可达 ${unreachable.length};NO-LM ${noLm.length};需令牌(401/403) ${tokenReq.length}`,
            ...frozen.map((f) => `- 死键嫌疑·建议复核: ${f.url}(冻结 ${f.age_days} 天;Last-Modified: ${f.last_modified})`),
            ...unreachable.map((u) => `- 不可达·建议复核: ${u}(不可达≠死键)`),
            matrix.ok
              ? [`matrix 读数: exit_code=${matrix.exit_code}(0 干净/1 pending/2 violation) violation=${matrix.counts.violation} pending=${matrix.counts.pending} agreement=${matrix.counts.agreement}`,
                ...Object.entries(matrix.layers).map(([k, v]) => `layer ${k}: ${v.status}${v.notes.length ? `(${v.notes.join(",")})` : ""}`),
                ...matrix.violation_cells.slice(0, 12).map((x) => `violation 格: ${x.cell}${x.note ? `(note: ${x.note})` : ""}`)]
              : [`matrix 测量信封: ${matrix.code}: ${matrix.reason}`].join("\n"),
            `工件: ${arts.join(", ")}`].flat().join("\n");
          return this.finish(callId, "health_snapshot", st, c);
        } catch (e) {
          const env = envelope(e.code ?? "snapshot_failed", e.message);
          return this.finish(callId, "health_snapshot", { ...env, artifacts: arts }, `健康快照失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  },
  fetchUrl() {
    return {
      name: "fetch_url",
      label: "URL 探测",
      description: "只读 GET/HEAD。逐跳 SSRF 防护(私网/环回拒);512KB/15s/每轮≤20 次。返回 status/last_modified/age_days(GET 附样本≤5 行)。age_days 是 sunset 谓词的唯一数据源;HTTP≥400/超时=失败信封(不可达≠死键)。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        url: Type.String({ pattern: "^https?://", maxLength: 500 }),
        method: Type.Optional(Type.Union([Type.Literal("GET"), Type.Literal("HEAD")], { description: "默认 HEAD;GET 取样本" })),
        max_bytes: Type.Optional(Type.Number({ minimum: 256, maximum: 524288 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), url: Type.String(), final_url: Type.String(), status: Type.Number(),
        last_modified: Type.Union([Type.String(), Type.Null()]), age_days: Type.Union([Type.Number(), Type.Null()]),
        bytes: Type.Number(), sample: Type.Array(Type.String()),
      }),
      execute: async (callId, p) => {
        const method = p.method ?? "HEAD";
        try {
          const res = await safeFetch(p.url, { method, maxBytes: p.max_bytes ?? B.fetchBytes, timeoutMs: B.fetchTimeoutMs });
          const lm = res.headers["last-modified"] ?? null;
          const age = lm ? Math.max(0, Math.floor((Date.now() - Date.parse(lm)) / 86_400_000)) : null;
          const sample = method === "GET" && res.body
            ? res.body.toString("utf8").split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 5).map((l) => l.slice(0, 200)) : [];
          const st = {
            ok: true, url: p.url, final_url: res.finalUrl, status: res.status, last_modified: lm,
            age_days: age, bytes: res.bytes, sample, trace: { method, status: res.status },
          };
          const c = `${method} ${p.url} → ${res.status};Last-Modified: ${lm ?? "(无)"};age_days=${age ?? "null"};bytes=${res.bytes}`
            + (sample.length ? `\n样本:\n${sample.join("\n")}` : "");
          return this.finish(callId, "fetch_url", st, c);
        } catch (e) {
          const env = envelope(e.code ?? "network", e.message);
          return this.finish(callId, "fetch_url", { ...env, url: p.url, method }, `URL 探测失败信封:${env.code}: ${env.reason}`);
        }
      },
    };
  },
  ghSearch() {
    const FIELDS = {
      repos: ["fullName", "description", "pushedAt", "updatedAt", "stargazersCount", "language", "isArchived", "size", "url"],
      code: ["path", "repository"],
      commits: ["commit", "repository"],
    };
    const project = (kind, rows) => rows.map((r) => kind === "repos" ? ({
      full_name: r.fullName, description: String(r.description ?? "").slice(0, 120),
      pushed_at: r.pushedAt, updated_at: r.updatedAt, stars: r.stargazersCount,
      language: r.language, archived: r.isArchived, size_kb: r.size, url: r.url,
    }) : kind === "code" ? ({ repo: r.repository?.nameWithOwner, path: r.path })
      : ({ repo: r.repository?.nameWithOwner, sha: String(r.sha ?? "").slice(0, 12), date: r.commit?.committer?.date ?? r.commit?.author?.date ?? null, message: String(r.commit?.message ?? "").split("\n")[0].slice(0, 120) }));
    return {
      name: "gh_search",
      label: "GitHub 检索",
      description: "只读 gh search(子命令白名单仅 search;禁裸 stdout,固定字段投影)。kind=repos(候选仓元数据/size_kb)/code(仓内代码命中;零命中=零资产信号)/commits(出版方活性;注意 commits 检索必须带文本词,纯 qualifier 会报错)。每轮≤15 次。",
      annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
      parameters: Type.Object({
        query: Type.String({ minLength: 1, maxLength: 256 }),
        kind: Type.Union([Type.Literal("repos"), Type.Literal("code"), Type.Literal("commits")]),
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 30 })),
        // page 已移除(通道复验轮修复 2026-10-24):gh 2.103.x search 无 --page 旗(repos/code
        // 实测均拒 unknown flag)——旧 argv 恒拼 --page 故 gh_search 100% 必死,仅因前置通道先死从未暴露。
        // 分页需求由 limit ≤30(预算面)承担。
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), kind: Type.String(), query: Type.String(), total: Type.Number(),
        results: Type.Array(Type.Object({})), trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      execute: async (callId, p) => {
        const argv = ["search", p.kind, p.query, "--json", FIELDS[p.kind].join(","),
          "--limit", String(p.limit ?? 10)];
        const cmd = `gh ${argv.map((a) => /\s/.test(a) ? `"${a}"` : a).join(" ")}`;
        try {
          const { stdout } = await execFileP("gh", argv, { timeout: B.ghTimeoutMs, maxBuffer: 8 * 1024 * 1024 });
          const rows = JSON.parse(stdout);
          const results = project(p.kind, Array.isArray(rows) ? rows : []);
          const st = { ok: true, kind: p.kind, query: p.query, total: results.length, results, trace: { cmd, rc: 0 } };
          const c = `${p.kind} "${p.query}" → ${results.length} 条(字段投影)\n` +
            results.slice(0, 30).map((r) => `- ${JSON.stringify(r)}`).join("\n");
          return this.finish(callId, "gh_search", st, c);
        } catch (e) {
          // PR #177 分类落地(判例 2026-10-24-discover-dual-channel-dead):容器无 gh/
          // 凭证缺失/限流/暂态分四码信封,每码带下一步合法动作;trace.rc 恒 Number
          // (旧 e.code ?? 1 在 ENOENT 时塞字符串违反 outputSchema Number 槽);原 gh_error
          // 兑底兼容保留;成功路径零改动。
          const cls = classifyChannelError(e, "gh");
          const env = envelope(cls.code, cls.reason);
          return this.finish(callId, "gh_search", { ...env, kind: p.kind, query: p.query, trace: { cmd, rc: cls.rc } },
            `gh 检索失败信封:${env.code}:${env.reason}`);
        }
      },
    };
  },
  exclusiveProbe() {
    return {
      name: "exclusive_probe",
      label: "排他率探针",
      description: "候选 feed 实测排他率(唯一硬门数字生产线;阳性对照闸 20 中 ≥18)。仅收 URL(禁文件路径);内部下载(SSRF 逐跳,≤256MB)→ 键量>1M 走体量信封(bitwire OOM 判例,人裁)→ 子进程跑 python -m ipdb._eval --exclusive --json(seed 缺省 20261018)。串行执行;数据面缺失=结构化信封。ENQUEUE 自动入队条件=本工具 exclusive_rate≥0.25 且 control_pass。",
      annotations: { readOnlyHint: true, openWorldHint: true },
      parameters: Type.Object({
        url: Type.String({ pattern: "^https?://", maxLength: 500 }),
        seed: Type.Optional(Type.Number({ minimum: 0, maximum: 99999999 })),
      }),
      outputSchema: Type.Object({
        ok: Type.Boolean(), url: Type.String(), seed: Type.Number(),
        exclusive_rate: Type.Number(), exclusive: Type.Number(), sampled: Type.Number(),
        feed_unique_keys: Type.Number(), control_pass: Type.Boolean(),
        covering_sources: Type.Array(Type.Object({})), artifact: Type.String(),
        trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      // 串行一层(评审 P1 修正):SDK 每工具执行模式 pi-agent-core 1.3.0 AgentTool.
      // executionMode(agent-loop executeToolCalls:批次含 sequential 工具即整批逐个执行,
      // 防 SDK 缺省 parallel 下并发 ≤256MB 下载 + _eval CLI/LMDB 读压)。
      executionMode: "sequential",
      execute: async (callId, p) => this.probeQueue(this.runExclusiveProbe(callId, p)),
    };
  },
  // 串行二层(实例级 promise 链 this.probeChain,非模块级;只序落定,起跑由 execute 立即发生)
  // ——并发防护以一层 executionMode 为准,本链兜底 SDK 批层之外的调用路径(LMDB 读压)。
  probeQueue(task) {
    const run = this.probeChain ?? Promise.resolve();
    this.probeChain = run.then(() => task, () => task);
    return this.probeChain;
  },
  async runExclusiveProbe(callId, p) {
    const seed = p.seed ?? 20261018;
    const tmp = path.join(os.tmpdir(), `ops-probe-${process.pid}-${Date.now()}.txt`);
    try {
      const dl = await safeFetch(p.url, { method: "GET", maxBytes: B.probeBytes, timeoutMs: B.probeDlTimeoutMs });
      const text = dl.body.toString("utf8");
      const keys = countFeedKeys(text);
      if (keys === 0) return this.finish(callId, "exclusive_probe",
        envelope("bad_feed", `feed 提取零个 IPv4 键:${p.url}(空分母不冒充 0)`),
        `探针失败信封:bad_feed: feed 零键`);
      if (keys > B.probeMaxKeys) return this.finish(callId, "exclusive_probe",
        envelope("key_cap", `feed 键量 ${keys} > 上限 ${B.probeMaxKeys}(bitwire 4.58M OOM 判例:过线体量人裁)`),
        `探针失败信封:key_cap: 键量 ${keys} 超限,升级人裁区`);
      fs.writeFileSync(tmp, text);
      const cmd = `cd backend && IP_RADAR_DATA_DIR=${DATA_DIR} ${EVAL_PY} -m ipdb._eval --exclusive <tmp> --json --seed ${seed}`;
      const { stdout, stderr } = await execFileP(EVAL_PY,
        ["-m", "ipdb._eval", "--exclusive", tmp, "--json", "--seed", String(seed)],
        { cwd: path.join(ROOT, "backend"), env: { ...process.env, IP_RADAR_DATA_DIR: DATA_DIR },
          timeout: B.probeCliTimeoutMs, maxBuffer: 32 * 1024 * 1024 });
      const res = JSON.parse(stdout);
      const controlPass = res.control.hits >= res.control.required;
      const art = artifactPath(this.artifactDir, `probe-${new URL(p.url).hostname.replace(/\W+/g, "-")}`, "json");
      fs.writeFileSync(art, JSON.stringify({ trace: { cmd, rc: 0 }, result: res }, null, 1));
      const st = {
        ok: true, url: p.url, seed: res.seed, feed_unique_keys: res.feed_unique_keys,
        sampled: res.sampled, exclusive: res.exclusive, covered: res.covered,
        exclusive_rate: res.exclusive_rate, control: res.control, control_pass: controlPass,
        covering_sources: Object.entries(res.coverage_sources).slice(0, 8).map(([source, n]) => ({ source, n })),
        artifact: art, trace: { cmd, rc: 0 },
      };
      const c = `排他率实测:${res.exclusive}/${res.sampled} = ${(res.exclusive_rate * 100).toFixed(1)}%(seed=${res.seed},feed uniq=${res.feed_unique_keys});`
        + `对照闸 binarydefense ${res.control.hits}/${res.control.n}(需≥${res.control.required},${controlPass ? "过" : "未过"});`
        + `覆盖源:${Object.entries(res.coverage_sources).slice(0, 8).map(([s, n]) => `${s}:${n}`).join(",")};工件:${art}`;
      return this.finish(callId, "exclusive_probe", st, c);
    } catch (e) {
      let env;
      try { // CLI --json 失败信封(control_failed/bad_feed/internal)解析优先
        const j = JSON.parse(String(e.stdout ?? ""));
        env = envelope(j.error?.code ?? "probe_failed", j.error?.message ?? String(e.message));
      } catch { env = envelope(e.code === "ENOENT" ? "data_plane_missing" : "probe_failed", String(e.stderr ?? e.message).slice(0, 300)); }
      return this.finish(callId, "exclusive_probe", { ...env, url: p.url, seed }, `探针失败信封:${env.code}: ${env.reason}`);
    } finally {
      try { fs.rmSync(tmp, { force: true }); } catch { /* 轮末清理兜底 */ }
    }
  },
  async runMatrixScan(arts) { // 单源薄包装(P1,#163):真路径在 matrixScanCli,legacy 返回形状零改动
    const r = await matrixScanCli();
    if (r.ok) return this.matrixFromResult(r.d, r.cmd, arts, r.rc);
    return r.trace ? { ...r.env, trace: r.trace } : r.env;
  },
  matrixFromResult(d, cmd, arts, rc) {
    const art = artifactPath(this.artifactDir, "matrix-scan", "json");
    fs.writeFileSync(art, matrixArtifactText(d));
    arts?.push(art);
    return {
      ok: true, exit_code: d.exit_code, counts: d.counts,
      layers: Object.fromEntries(Object.entries(d.layers).map(([k, v]) => [k, { status: v.status, notes: v.notes ?? [] }])),
      violation_cells: (d.buckets?.violation ?? []).map((c) => ({ cell: c.cell, note: c.note ?? null })),
      artifact: art, trace: { cmd, rc },
    };
  },
  matrixScanSummary() {
    return {
      name: "matrix_scan_summary",
      label: "语义矩阵扫描",
      description: "零参。语义契约矩阵现状扫描(四层取样):exit_code 0/1/2=干净/pending/violation + 逐格违例与层状态。数据面缺失=结构化信封不裸栈。",
      annotations: { readOnlyHint: true, idempotentHint: true },
      parameters: Type.Object({}),
      outputSchema: Type.Object({
        ok: Type.Boolean(), exit_code: Type.Number(), violation_n: Type.Number(),
        counts: Type.Object({}), layers: Type.Object({}), trace: Type.Object({ cmd: Type.String(), rc: Type.Number() }),
      }),
      execute: async (callId) => {
        const r = await this.runMatrixScan();
        if (!r.ok) return this.finish(callId, "matrix_scan_summary", r, `matrix 扫描失败信封:${r.code}: ${r.reason}`);
        this.artifacts.push(r.artifact);
        const c = `exit_code=${r.exit_code}(0 干净/1 pending/2 violation) violation=${r.counts.violation} pending=${r.counts.pending} agreement=${r.counts.agreement}\n`
          + Object.entries(r.layers).map(([k, v]) => `layer ${k}: ${v.status}${v.notes.length ? `(${v.notes.join(",")})` : ""}`).join("\n")
          + (r.violation_cells.length ? `\n违例格:${r.violation_cells.map((x) => x.cell).join(",")}` : "");
        return this.finish(callId, "matrix_scan_summary", { ...r, violation_n: r.counts.violation }, c);
      },
    };
  },
};
