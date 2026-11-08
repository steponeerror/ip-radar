// bench/scan.mjs — 重发现基准票 A(票 #318;spec docs/research/2026-11-07-rediscover-bench-spec.md
// §3.1/§2-Q2①):bench SCAN 变体。候选宇宙=仅 NEEDS.md 行(source_channel=needs),零注册
// 表面(不发 backend/ipdb/_sources 行)——答案躺在注册表里,盲测轮模型不得见(spec Q2:
// 「答案现在躺在模型输入里」即指 registry 面)。相位机/门复用真实面:工件形状=G_SCAN
// 同律(channels 三渠留痕,registry.n=0 与实数自洽;needs 行锚+text 原文面,#208 span
// 门对账律照用)。web 渠道占位维持(Q9:搜索职责在 SHORTLIST 模型驱动三工具,SCAN 保持
// 确定性零网络)。
//
// 实现边界:真实 SCAN(ops/agent/pipeline/steps.mjs SCAN,双面宇宙)属 v1 属主,零改动
// 红线(票面出界)→ needs 面解析在此按旧源逐形重实现(旧 SCAN 内嵌不可 import 的私有
// 段;round-ctx.mjs 私有函数适配重实现同判例),出处逐段标注,对拍以旧源为准。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ARTIFACTS as A } from "../../agent/artifacts.mjs"; // 工件名单源(C1 判例:回放读面禁手抄磁盘名)

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", ".."); // ops/agent-v2/bench → 仓根(3 层,与旧 SCAN 的 AGENT_DIR 推导同落点)

// 缺口行状态闭集(旧 steps.mjs NEEDS_STATUS 逐字:open/候选=缺口,已立项/已闭不入候选宇宙)
const NEEDS_STATUS = ["open", "候选"];

// needs 面行解析(旧 steps.mjs SCAN needsRows 段逐形:cells[1]=需求名列(带 URL 时剥)、
// cells[3]=状态列、URL 取首个 http(s)、行锚 NEEDS.md:L<1-based>、text=原文行快照)。
function needsRowsOf(repoRoot) {
  const rows = [];
  const needsFile = path.join(repoRoot, "NEEDS.md");
  if (!fs.existsSync(needsFile)) return rows;
  const lines = fs.readFileSync(needsFile, "utf8").split("\n");
  for (let i = 0; i < lines.length; i++) {
    const cells = lines[i].split("|").map((c) => c.trim());
    if (cells.length < 5 || !NEEDS_STATUS.includes(cells[3])) continue;
    const url = (cells[1].match(/https?:\/\/\S+/) ?? [null])[0];
    rows.push({ name: cells[1].replace(/https?:\/\/\S+/g, "").replace(/\s+/g, " ").trim() || url,
      url, evidence_ptr: `NEEDS.md:L${i + 1}`, source_channel: "needs", status: cells[3],
      text: lines[i].trim() });
  }
  return rows;
}

// 伪面写盘助手(旧 steps.mjs writeJson 同形:2 空格缩进+尾换行)
const writeJson = (p, o) => fs.writeFileSync(p, JSON.stringify(o, null, 2) + "\n");

// bench SCAN:真面=repo NEEDS.md 现解析;faux 面=罐装 d1-scan.json 滤注册行(span 门使
// 罐装 quote 与原文耦合,罐装宇宙钉死=旧 SCAN faux 缝同律;滤注册行=bench 零注册表面
// 不变量在罐装面同样成立)。返回 undefined(脚本步律:无降级无 skipGate)。
export function benchScan(ctx) {
  if (ctx.modelFace === "faux" && typeof ctx.fixturesDir === "string") {
    const fxPath = path.join(ctx.fixturesDir, A.DISCOVER_SCAN);
    if (fs.existsSync(fxPath)) {
      const fx = JSON.parse(fs.readFileSync(fxPath, "utf8"));
      const needs = (fx.candidates ?? []).filter((c) => c?.source_channel === "needs");
      writeJson(path.join(ctx.dir, A.DISCOVER_SCAN), { round_id: ctx.roundId, generated_at: new Date().toISOString(),
        candidates: needs, channels: benchChannels(needs.length) });
      return;
    }
  }
  const needs = needsRowsOf(REPO_ROOT);
  writeJson(path.join(ctx.dir, A.DISCOVER_SCAN), { round_id: ctx.roundId, generated_at: new Date().toISOString(),
    candidates: needs, channels: benchChannels(needs.length) });
}

// channels 留痕(G_SCAN 同律:registry/needs/web 三渠在场;registry.n 恒 0=零注册表面;
// web 占位同真实 SCAN,Q9 裁决搜索职责在 SHORTLIST)。
const benchChannels = (needsN) => ({
  registry: { status: "ok", n: 0, note: "bench 盲测轮零注册面(spec Q2①:答案表=已接源池,不得入候选宇宙)" },
  needs: { status: "ok", n: needsN },
  web: { status: "placeholder", n: 0, note: "bench 同真实 SCAN:web 渠道占位(Q9:搜索职责在 SHORTLIST 模型驱动三工具;SCAN 确定性零网络)" },
});
