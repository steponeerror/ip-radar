// tools/add-tools.mjs — 加源轮编码工具三件 defineTool 化(票 #332 P1;spec
// docs/superpowers/specs/2026-11-11-add-round-reimplementation-bench-design.md 定案 7)。
// #331/#332 裁定对 registry 红线的轮型化修正:「不装内建 CodingTools」红线针对 root/
// 骨架/发现轮面(无人值守运营管线不得有代码执行面);加源轮的**工作本体**就是把源
// 实现进沙箱 worktree,编码工具=该轮型的领域工具闭集,仅加源轮自有会话选装
// (run-add.mjs 创建会话时 extensions=[ADD_TOOLS_EXTENSION];root 面钉 [] 见 entry.mjs)。
// 与发现轮三只同形制:静态 defineTool 注册 + 按 api.conversationId 派发到轮级宿主
// (进程内 Map;崩溃 resume 后宿主缺席=常态,宁少算口径同旧——seeds 只增不补)。
//
// replay 声明逐工具裁(头注纪律同 discovery-tools):
//   write_file = "safe"  同内容重写幂等(崩溃重放至多重写同字节;路径遏制在重放路径同样执行)
//   run_bash   = "unsafe" 任意副作用面,重放=重复执行,宁中断不重放
//   run_pytest = "safe"  沙箱内测试重跑幂等(读数面;缓存写入沙箱内无害)
//
// 沙箱遏制律:write_file/run_pytest 的相对路径一律 resolve 宿主 sandboxRoot 并验
// 「不出根」(前缀判;绝对路径=先归一再判);run_bash 以 sandboxRoot 为 cwd——命令
// 本体不可静态遏制(编码面的既定边界:沙箱目录即边界,spec 定案 7 工作落点=沙箱
// worktree 不碰主检出;主检出防线=CLOSE 相位 sandbox_assert)。
import { execFile as execFileCb } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";
import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "@earendil-works/pi-ai";

const execFileP = promisify(execFileCb);

// replay 声明单源(测试断言同源引用本表)
export const ADD_REPLAY = Object.freeze({ write_file: "safe", run_bash: "unsafe", run_pytest: "safe" });
export const ADD_TOOL_NAMES = Object.freeze(["write_file", "run_bash", "run_pytest"]);

// 轮级编码宿主缓存:key=conversationId(加源轮自有会话,一轮一会话——粒度决策同发现轮,
// 见 tasks/discover-round.mjs 头注)。host={sandboxRoot, python, seeds:[]};seeds=
// 工具登记行({call_id,tool,sc},转录 registry_seed 面单源,与 discovery-host seeds 同形)。
export const addHosts = new Map();

export function ensureAddHost(ctx, conversationId) {
  let host = addHosts.get(conversationId);
  // 同进程多库(测试/程序面)conv id 可碰撞:现宿主绑不同沙箱=属已死世界(其轮已终/目录已清),
// 当前世界接管映射——静默串写沙箱正是沙箱律要防的事故面。同沙箱同宿主=resume/重入,
// seeds 保留(转录增量面 seedMark 连续)。进程崩溃重开=新进程新 Map,零碰撞。
  if (!host || host.sandboxRoot !== path.resolve(ctx.sandboxRoot) || host.python !== ctx.python) {
    host = { sandboxRoot: path.resolve(ctx.sandboxRoot), python: ctx.python, seeds: [] };
    addHosts.set(conversationId, host);
  }
  ctx.addHost = host;
  return host;
}

// 沙箱内路径解析:相对路径 join 根、绝对路径归一,统一验「不出根」;逃逸返回 null。
function insideSandbox(sandboxRoot, p) {
  const root = path.resolve(sandboxRoot);
  let target;
  try { target = path.resolve(root, p ?? ""); } catch { return null; }
  return target === root || target.startsWith(root + path.sep) ? target : null;
}

// 进度行(票 #142 语法,T5 冻结;ENVELOPE.md 契约面):[tool] 参数摘要 + [tool-result] 完成行
const progress = (line) => process.stderr.write(`${line}\n`);
const tailOf = (s, n = 400) => String(s ?? "").split("\n").filter(Boolean).slice(-n).join("\n").slice(0, 4000);

export function addTools() {
  return [
    defineTool({
      name: "write_file",
      label: "加源轮 write_file",
      description: "在轮沙箱内写文本文件(路径相对沙箱根;自动建父目录;逃逸路径=拒绝信封)。实现源文件/逐源测试/分类映射落盘用。",
      annotations: { readOnlyHint: false, idempotentHint: true },
      parameters: Type.Object({
        path: Type.String({ maxLength: 500, description: "相对沙箱根的路径(如 backend/ipdb/_sources/<name>.py)" }),
        content: Type.String({ maxLength: 2_000_000 }),
      }),
      replay: ADD_REPLAY.write_file,
      async execute(args, api) {
        progress(`[tool] write_file(${api.callId}) ${args.path}`);
        const host = addHosts.get(api.conversationId);
        if (!host) {
          progress(`[tool-result] write_file(${api.callId}) fail code=host_missing`);
          return refuse(api.callId, "host_missing", "编码宿主未就绪(会话无轮级宿主——模型相位先建宿主再提交)");
        }
        const target = insideSandbox(host.sandboxRoot, args.path);
        if (!target) {
          progress(`[tool-result] write_file(${api.callId}) fail code=sandbox_escape`);
          host.seeds.push({ call_id: api.callId, tool: "write_file", sc: { ok: false, code: "sandbox_escape", reason: args.path } }); // 拒绝也是回合证据(转录面;宿主在场才可登记)
          return refuse(api.callId, "sandbox_escape", `路径须在沙箱内(相对沙箱根):${args.path}`);
        }
        try {
          fs.mkdirSync(path.dirname(target), { recursive: true });
          fs.writeFileSync(target, args.content);
        } catch (e) {
          progress(`[tool-result] write_file(${api.callId}) fail code=io_error`);
          host.seeds.push({ call_id: api.callId, tool: "write_file", sc: { ok: false, code: "io_error", reason: e.message } });
          return { output: [{ type: "text", text: `[call_id=${api.callId}] 拒绝信封(code=io_error):${e.message}` }], structuredOutput: { ok: false, code: "io_error", reason: e.message } };
        }
        host.seeds.push({ call_id: api.callId, tool: "write_file", sc: { ok: true, path: path.relative(host.sandboxRoot, target), bytes: Buffer.byteLength(args.content) } });
        progress(`[tool-result] write_file(${api.callId}) ok bytes=${Buffer.byteLength(args.content)}`);
        return { output: [{ type: "text", text: `[call_id=${api.callId}] 写入 ${path.relative(host.sandboxRoot, target)}(${Buffer.byteLength(args.content)} 字节)` }], structuredOutput: { ok: true, path: path.relative(host.sandboxRoot, target), bytes: Buffer.byteLength(args.content) } };
      },
    }),
    defineTool({
      name: "run_bash",
      label: "加源轮 run_bash",
      description: "在轮沙箱根内跑 bash 命令(cwd=沙箱根;超时 120s;输出截尾回传)。探活/抓样本/杂务用;跑测试优先 run_pytest。",
      annotations: { readOnlyHint: false, idempotentHint: false },
      parameters: Type.Object({
        command: Type.String({ maxLength: 2000 }),
        timeout_s: Type.Optional(Type.Number({ minimum: 1, maximum: 600 })),
      }),
      replay: ADD_REPLAY.run_bash,
      async execute(args, api) {
        progress(`[tool] run_bash(${api.callId}) ${String(args.command).slice(0, 120)}`);
        const host = addHosts.get(api.conversationId);
        if (!host) {
          progress(`[tool-result] run_bash(${api.callId}) fail code=host_missing`);
          return refuse(api.callId, "host_missing", "编码宿主未就绪(会话无轮级宿主)");
        }
        let r;
        try {
          r = await execFileP("bash", ["-c", args.command], { cwd: host.sandboxRoot, timeout: (args.timeout_s ?? 120) * 1000, maxBuffer: 16 * 1024 * 1024 });
        } catch (e) {
          const rc = typeof e.code === "number" ? e.code : -1;
          const out = tailOf(`${e.stdout ?? ""}\n${e.stderr ?? ""}`);
          host.seeds.push({ call_id: api.callId, tool: "run_bash", sc: { ok: false, rc, tail: out.slice(0, 400) } });
          progress(`[tool-result] run_bash(${api.callId}) rc=${rc}`);
          return { output: [{ type: "text", text: `[call_id=${api.callId}] rc=${rc}\n${out}` }], structuredOutput: { ok: false, rc, tail: out.slice(0, 2000) } };
        }
        host.seeds.push({ call_id: api.callId, tool: "run_bash", sc: { ok: true, rc: 0, tail: tailOf(r.stdout).slice(0, 400) } }); // 成功面真值直书:promisified execFile 成功路径无 code 字段,r.code===0 恒 false(首跑调试判 bug)
        progress(`[tool-result] run_bash(${api.callId}) ok rc=0`);
        return { output: [{ type: "text", text: `[call_id=${api.callId}] rc=0\n${tailOf(r.stdout)}` }], structuredOutput: { ok: true, rc: 0, tail: tailOf(r.stdout).slice(0, 2000) } };
      },
    }),
    defineTool({
      name: "run_pytest",
      label: "加源轮 run_pytest",
      description: "在轮沙箱内跑 pytest(解释器=主检出 venv 绝对路径,cwd 缺省沙箱 backend/;TDD 硬序看红/看绿用)。args 相对 cwd 传给 pytest。",
      annotations: { readOnlyHint: false, idempotentHint: true },
      parameters: Type.Object({
        args: Type.Array(Type.String({ maxLength: 300 }), { maxItems: 20 }),
        cwd: Type.Optional(Type.String({ maxLength: 200, description: "相对沙箱根的工作目录,缺省 backend" })),
      }),
      replay: ADD_REPLAY.run_pytest,
      async execute(args, api) {
        progress(`[tool] run_pytest(${api.callId}) ${args.args.join(" ").slice(0, 120)}`);
        const host = addHosts.get(api.conversationId);
        if (!host) {
          progress(`[tool-result] run_pytest(${api.callId}) fail code=host_missing`);
          return refuse(api.callId, "host_missing", "编码宿主未就绪(会话无轮级宿主)");
        }
        const cwd = insideSandbox(host.sandboxRoot, args.cwd ?? "backend");
        if (!cwd) {
          progress(`[tool-result] run_pytest(${api.callId}) fail code=sandbox_escape`);
          host.seeds.push({ call_id: api.callId, tool: "run_pytest", sc: { ok: false, code: "sandbox_escape", reason: args.cwd } }); // 拒绝也是回合证据(转录面)
          return refuse(api.callId, "sandbox_escape", `cwd 须在沙箱内:${args.cwd}`);
        }
        let r;
        try {
          r = await execFileP(host.python, ["-m", "pytest", ...args.args], { cwd, timeout: 300_000, maxBuffer: 32 * 1024 * 1024 });
        } catch (e) {
          const rc = typeof e.code === "number" ? e.code : -1;
          const out = tailOf(`${e.stdout ?? ""}\n${e.stderr ?? ""}`);
          host.seeds.push({ call_id: api.callId, tool: "run_pytest", sc: { ok: false, rc, tail: out.slice(0, 400) } });
          progress(`[tool-result] run_pytest(${api.callId}) rc=${rc}`);
          return { output: [{ type: "text", text: `[call_id=${api.callId}] pytest rc=${rc}\n${out}` }], structuredOutput: { ok: false, rc, tail: out.slice(0, 2000) } };
        }
        host.seeds.push({ call_id: api.callId, tool: "run_pytest", sc: { ok: true, rc: 0, tail: tailOf(r.stdout).slice(0, 400) } }); // 成功面真值直书:同 run_bash 判 bug
        progress(`[tool-result] run_pytest(${api.callId}) ok rc=0`);
        return { output: [{ type: "text", text: `[call_id=${api.callId}] pytest rc=0\n${tailOf(r.stdout)}` }], structuredOutput: { ok: true, rc: 0, tail: tailOf(r.stdout).slice(0, 2000) } };
      },
    }),
  ];
}

function refuse(callId, code, reason) {
  return { output: [{ type: "text", text: `[call_id=${callId}] 拒绝信封(code=${code}):${reason}` }], structuredOutput: { ok: false, code, reason } };
}
