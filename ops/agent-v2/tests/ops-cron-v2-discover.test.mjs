// ops-cron-v2-discover.test.mjs — deploy/ops-cron-v2-discover.sh 冻结面(#367 发现轮定频)。
// 同 ops-cron-v2.test.mjs 三断言组 cron 入口律(#364 切流件同构)+ 发现轮差异面:
// ①双预检跳过语义(auth.json 缺位=明确跳过 exit 0 下窗自愈,旧 ops-cron 409 判例
//   直跑形;agent-config 缺 model_discover=同判例——run-discover real 面无缺省
//   resolve,裸跑落用法错 exit 2,缺配置不带病跑)②env 面逐键白名单(#364 裁定
//   同判例:OPS_MODEL_DISCOVER 注入;发现轮面不注 OPS_MODEL_HEALTH;unset 仅管理
//   密钥;GH_TOKEN/IP_RADAR_ALERT_URLS 继承=finding 出口契约员(GH_TOKEN 自 #384 起亦为
//   发现轮 ENQUEUE 开票出口契约员);OPS_SWEEP_DRY_RUN
//   不设)③退出码透传(信封面 ENVELOPE.md 0/1/2/3;月帽拒启 budget_monthly 亦落
//   1——超帽拒启在 run-discover 准入面,cron 面透传不重裁,钉在 budget-parity)。
// bash 面零 docker 依赖:PATH 注入 mock docker(录 argv+剥 exec 头后真执行内层
// sh -c)+ stub node(录终态 env/argv+罐装 rc)——wrapper→docker exec→内层→node
// 全链真跑,仅容器与文件系统两环替身;内层双预检/agent-config 现读/export/unset
// 均行为面可断言(沙盒同 ops-cron-v2.test.mjs)。
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const HERE = import.meta.dirname;
const REPO = path.resolve(HERE, "..", "..", "..");
const SCRIPT = path.join(REPO, "deploy", "ops-cron-v2-discover.sh");

// 沙盒:mock bin(docker/node)+ 假 ops 树;run() 跑 wrapper 一次并收三面证据
// (wrapper stdout/stderr、docker argv 录、node 终态 env/argv 录)。
function sandbox() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ops-cron-v2-disc-"));
  const bin = path.join(tmp, "bin");
  fs.mkdirSync(bin);
  // mock docker:录全 argv;MOCK_DOCKER_RC 非空=罐装退出码不执行内层(容器失联
  // 面);否则剥「exec <container>」头后执行余下 argv(=sh -c 内层),进程链
  // env 透传即 docker exec 继承语义的替身。
  fs.writeFileSync(path.join(bin, "docker"), `#!/bin/sh
printf '%s\\n' "$*" >> "\${MOCK_DOCKER_LOG:?}"
echo x >> "\${MOCK_DOCKER_CALLS:?}"
if [ -n "\${MOCK_DOCKER_RC:-}" ]; then exit "$MOCK_DOCKER_RC"; fi
[ "$1" = "exec" ] || exit 64
shift 2
exec "$@"
`);
  // stub node:录内层终态 env(argv 面即内层 exec node 时的进程面)+ argv;罐装 rc
  fs.writeFileSync(path.join(bin, "node"), `#!/bin/sh
env > "\${STUB_NODE_ENV:?}"
printf '%s' "$*" > "\${STUB_NODE_ARGV:?}"
exit "\${STUB_NODE_RC:-0}"
`);
  fs.chmodSync(path.join(bin, "docker"), 0o755);
  fs.chmodSync(path.join(bin, "node"), 0o755);
  const run = (extraEnv = {}) => {
    const log = path.join(tmp, "docker.log");
    const calls = path.join(tmp, "docker.calls");
    const nenv = path.join(tmp, "node.env");
    const nargv = path.join(tmp, "node.argv");
    for (const f of [log, calls, nenv, nargv]) fs.rmSync(f, { force: true });
    const r = spawnSync("bash", [SCRIPT], {
      encoding: "utf8",
      env: {
        ...process.env,
        PATH: `${bin}:${process.env.PATH}`,
        MOCK_DOCKER_LOG: log, MOCK_DOCKER_CALLS: calls,
        STUB_NODE_ENV: nenv, STUB_NODE_ARGV: nargv,
        ...extraEnv,
      },
    });
    return {
      rc: r.status, out: `${r.stdout}${r.stderr}`,
      dockerLog: () => (fs.existsSync(log) ? fs.readFileSync(log, "utf8") : ""),
      dockerCalls: () => (fs.existsSync(calls) ? fs.readFileSync(calls, "utf8").trimEnd().split("\n") : []),
      nodeEnvFile: nenv,
      nodeArgv: () => fs.readFileSync(nargv, "utf8"),
      tmp,
    };
  };
  return { tmp, run };
}
const parseEnv = (t) => Object.fromEntries(t.trimEnd().split("\n").map((l) => {
  const i = l.indexOf("=");
  return [l.slice(0, i), l.slice(i + 1)];
}));
// 假生产 ops 树:auth.json 在位+agent-config 双模型配置(发现轮面=prov-beta/m-discover;
// model_health 在场=钉「发现轮面不注 OPS_MODEL_HEALTH」非缺件假绿)。
function seededWorld(sb) {
  const ops = path.join(sb.tmp, "ops");
  fs.mkdirSync(ops, { recursive: true });
  fs.writeFileSync(path.join(ops, "auth.json"), "{}\n");
  fs.writeFileSync(path.join(ops, "agent-config.json"), JSON.stringify({ model_health: "prov-alpha/m-health", model_discover: "prov-beta/m-discover" }) + "\n");
  return { ops, env: { OPS_V2_OPS_ROOT: ops, OPS_V2_APP_ROOT: REPO } };
}

test("语法面:bash -n 通过", () => {
  const r = spawnSync("bash", ["-n", SCRIPT], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
});

test("凭证预检跳过(旧 ops-cron 409 判例直跑形):auth.json 缺位 → exit 0+跳过留痕,零轮启动", () => {
  const sb = sandbox();
  try {
    const emptyOps = path.join(sb.tmp, "empty-ops");
    fs.mkdirSync(emptyOps); // 无 auth.json
    const r = sb.run({ OPS_V2_OPS_ROOT: emptyOps, OPS_V2_APP_ROOT: REPO });
    assert.equal(r.rc, 0, r.out);
    assert.match(r.out, /ops-cron-v2: 触发 v2 生产发现轮/);
    assert.match(r.out, /生产 auth\.json 未物化,本轮跳过,下窗自愈/);
    assert.ok(!fs.existsSync(r.nodeEnvFile), "跳过=不到 node 面");
    assert.equal(r.dockerCalls().length, 1, "docker 恰一次");
  } finally { fs.rmSync(sb.tmp, { recursive: true, force: true }); }
});

test("模型预检跳过(#367):agent-config 缺 model_discover → exit 0+明确跳过留痕,零轮启动(real 面须显式 --model,不带病跑)", () => {
  const sb = sandbox();
  try {
    const ops = path.join(sb.tmp, "ops-no-model");
    fs.mkdirSync(ops, { recursive: true });
    fs.writeFileSync(path.join(ops, "auth.json"), "{}\n");
    fs.writeFileSync(path.join(ops, "agent-config.json"), JSON.stringify({ model_health: "prov-alpha/m-health" }) + "\n"); // 缺 model_discover
    const r = sb.run({ OPS_V2_OPS_ROOT: ops, OPS_V2_APP_ROOT: REPO });
    assert.equal(r.rc, 0, r.out);
    assert.match(r.out, /agent-config 缺 model_discover,发现轮明确跳过,下窗自愈/);
    assert.ok(!fs.existsSync(r.nodeEnvFile), "跳过=不到 node 面(裸跑会落用法错 exit 2)");
    assert.equal(r.dockerCalls().length, 1, "docker 恰一次");
  } finally { fs.rmSync(sb.tmp, { recursive: true, force: true }); }
});

test("env 面逐键白名单(#364 裁定同判例):设生产世界键+OPS_MODEL_DISCOVER 注入、unset 仅管理密钥、GH_TOKEN/ALERT_URLS 继承、零 dry-run、发现轮面不注 OPS_MODEL_HEALTH;启动面=run-discover+UTC 轮 id+显式 --model", () => {
  const sb = sandbox();
  try {
    const w = seededWorld(sb);
    const r = sb.run({ ...w.env,
      IP_RADAR_ADMIN_PASSWORD: "sekrit-admin", IP_RADAR_API_JWT_SECRET: "sekrit-jwt",
      GH_TOKEN: "ghp_testtoken", IP_RADAR_ALERT_URLS: "lark://dummy" });
    assert.equal(r.rc, 0, r.out);
    assert.match(r.out, /v2 生产发现轮/);
    const env = parseEnv(fs.readFileSync(r.nodeEnvFile, "utf8"));
    // 设:生产世界接线(v1 桥 _round_env 同源)
    assert.equal(env.DOCS_ROOT, sb.tmp, "DOCS_ROOT=ops 根的父(str(root.parent) 同律)");
    assert.equal(env.OPS_AUTH, path.join(w.ops, "auth.json"));
    assert.equal(env.PI_CODING_AGENT_DIR, w.ops, "v1 桥同键(web-search.json 路由面)");
    assert.equal(env.OPS_DATA_DIR, "/app/data");
    assert.equal(env.LANG, "C.UTF-8");
    assert.ok(env.OPS_EVAL_PY.includes("python3"), "OPS_EVAL_PY=容器 python3");
    assert.equal(env.OPS_MODEL_DISCOVER, "prov-beta/m-discover", "agent-config 现读注入");
    // unset:仅管理密钥(C4 判例;测试面注入后内层 unset 生效)
    assert.ok(!("IP_RADAR_ADMIN_PASSWORD" in env), "管理密钥不带进模型进程");
    assert.ok(!("IP_RADAR_API_JWT_SECRET" in env));
    // 继承不摘:finding 出口契约员+#384 发现轮开票出口契约员(与 v1 C4 白名单 _SPAWN_ENV_EXACT 同面)
    assert.equal(env.GH_TOKEN, "ghp_testtoken");
    assert.equal(env.IP_RADAR_ALERT_URLS, "lark://dummy");
    // 不设:影子零外发栈摘除=出口生产语义真开
    assert.ok(!("OPS_SWEEP_DRY_RUN" in env), "生产不设 dry-run");
    // 发现轮面不注 OPS_MODEL_HEALTH(agent-config 在场也不注——discover 面单模型)
    assert.ok(!("OPS_MODEL_HEALTH" in env));
    // 月帽独立键不设=用 run-discover 侧缺省 ¥20(#367;cron 面不重裁准入)
    assert.ok(!("OPS_DISCOVER_MONTHLY_CAP_CNY" in env), "月帽键由容器 env 覆写面持有,cron 不设");
    // 启动面:run-discover.mjs + UTC 轮 id 序列形 + real 面显式 --model
    assert.match(r.nodeArgv(), /--max-old-space-size=256 ops\/agent-v2\/run-discover\.mjs \d{4}-\d{2}-\d{2}-\d{4}-discover --model prov-beta\/m-discover$/);
    assert.match(r.dockerLog(), /^exec ip-lookup-tool-ipradar-1 sh -c /, "缺省容器名");
  } finally { fs.rmSync(sb.tmp, { recursive: true, force: true }); }
});

test("容器名 override:OPS_V2_CONTAINER 透传 docker exec 首参", () => {
  const sb = sandbox();
  try {
    const w = seededWorld(sb);
    const r = sb.run({ ...w.env, OPS_V2_CONTAINER: "mock-container-xyz" });
    assert.equal(r.rc, 0, r.out);
    assert.match(r.dockerLog(), /^exec mock-container-xyz sh -c /);
  } finally { fs.rmSync(sb.tmp, { recursive: true, force: true }); }
});

test("退出码透传(ENVELOPE.md 信封面):node rc=1 → wrapper rc=1+留痕(月帽拒启 budget_monthly 同码);docker exec 失联 rc=127 同透传", () => {
  const sb = sandbox();
  try {
    const w = seededWorld(sb);
    const r1 = sb.run({ ...w.env, STUB_NODE_RC: "1" });
    assert.equal(r1.rc, 1, r1.out);
    assert.match(r1.out, /v2 发现轮退出码 1\(信封语义见 ENVELOPE\.md/);
    const r2 = sb.run({ ...w.env, MOCK_DOCKER_RC: "127" }); // 容器失联面:内层不执行
    assert.equal(r2.rc, 127, r2.out);
    assert.match(r2.out, /v2 发现轮退出码 127/);
    assert.ok(!fs.existsSync(r2.nodeEnvFile), "exec 失败零 node 面");
  } finally { fs.rmSync(sb.tmp, { recursive: true, force: true }); }
});
