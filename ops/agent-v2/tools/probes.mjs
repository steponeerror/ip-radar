// tools/probes.mjs — 微探针三件套 v2 工具面(票 #228;spec 定案 2:工具随迁 defineTool 化,
// 实现零复制经旧 mkMicroprobeHost,不做第二实现)。
// 形状:registry 装的是三只**静态** ToolRegistration(defineTool;模型可见的参数/输出
// schema 面);执行期按 api.conversationId 派发到「绑定的宿主」——DEEP 每假设一个宿主
// (旧口径:逐假设新上下文+每假设 ≤3 预算+轮次级 dup registry),由 tasks/model-round.mjs
// 在 submit 前绑定(进程内 Map;崩溃重启重绑=计数清零,宁少算口径同旧 resume)。
// 未绑定会话调用 → isError 拒绝信封(健康轮 TRIAGE/SYNTH 无探针面,旧 tools=[] 同义)。
// replay 声明(逐工具裁,票面清单入报告):三只全 = "unsafe"(真网络探测,重放重发=
// 出网动作;structuredContent 是读数快照不是可重放输入)。纯读类工具(T3 判例库检索等)
// 才标 safe——本文件无 safe 面。
// registry 红线(票 #225/#228):不装内建 CodingTools——本文件只进这三只,tests/scaffold 钉死。
import { defineTool } from "@earendil-works/pi-durable";
import { mkMicroprobeHost } from "../../agent/pipeline/microprobes.mjs"; // 零复制:工具实现/预算闸/dup 闸/登记行全在旧宿主
import { safeFetch } from "../../agent/tools.mjs"; // 缺省传输层(真网络;与旧 microprobes.mjs 同源同拼)

// 模板宿主:只为取三只工具的静态元数据(name/label/annotations/parameters/outputSchema),
// fetchImpl 永不触发(budget:0 = 任何执行都会被预算闸拒,双保险)。
const TEMPLATE = mkMicroprobeHost({ budget: 0, dupRegistry: new Map(), fetchImpl: async () => { throw new Error("模板宿主不可执行"); } });

// 每会话绑定面:convId → host(旧 faux.mjs runRealStep 的 probes 单例位;v2 经
// bindProbeHost 由模型轮任务在 submit 前绑定)。seeds 读面:host.seeds(chronological
// {call_id,tool,sc})——旧 transcript registry_seed 行同源,不经 entry 解析(结构化输出
// 不入 transcript,种子必从宿主内存取,t1-notes 结论)。
const BOUND = new Map();
export function bindProbeHost(convId, opts = {}) {
  const host = mkMicroprobeHost({
    fetchImpl: opts.fetchImpl ?? safeFetch,
    budget: opts.budget ?? 3,
    dupRegistry: opts.dupRegistry ?? new Map(),
    dupLimit: opts.dupLimit ?? 3,
  });
  BOUND.set(convId, host);
  return host;
}
export function boundProbeHost(convId) { return BOUND.get(convId) ?? null; }
export function unbindProbeHost(convId) { BOUND.delete(convId); }

// 静态壳 → 绑定宿主派发。旧 execute(callId, p) → {content, structuredContent};
// v2 ToolRegistration execute(args, api) → {output, structuredOutput, isError?}。
const wrap = (templateTool) => defineTool({
  name: templateTool.name,
  label: templateTool.label,
  description: templateTool.description,
  annotations: templateTool.annotations,
  parameters: templateTool.parameters,
  replay: "unsafe", // 显式声明(缺省即 unsafe;这里钉字面=评审面可见)
  structuredOutputSchema: templateTool.outputSchema,
  async execute(args, api) {
    const host = boundProbeHost(api.conversationId);
    const tool = host?.tools.find((t) => t.name === templateTool.name);
    if (!tool)
      return { isError: true, output: `[call_id=${api.callId}] 拒绝信封:本会话未绑定微探针宿主(非 DEEP 假设面)。`, structuredOutput: { ok: false, code: "channel_missing", reason: "本会话未绑定微探针宿主(非 DEEP 假设面)" } };
    const r = await tool.execute(api.callId, args); // 预算闸/dup 闸/登记行全在旧宿主内(零复制)
    return { output: r.content, structuredOutput: r.structuredContent }; // 失败信封也是合法返回(ok:false 结构化面),不算 isError
  },
});

export const OPS_PROBE_TOOLS = TEMPLATE.tools.map(wrap);
