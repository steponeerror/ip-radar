#!/usr/bin/env node
// domains.mjs — 自演化循环域适配器表(票 #356 骨架 v1:接口域配置化,首接 add-domain)。
//
// 驱动器(run-round.mjs)对域的全部依赖收口在本表:工作指令(SKILL.md,提案者装载)、
// 演化集考题(冻结宇宙单源)、考题卡落位、trial 接线器(候选/冠军两面的跑批目标)、
// 三护栏命令、矿掘器、保护名单(候选面 diff 面闸的执法表,delta 复审 P1)。新域
// (rrsi-domain / health)接线 = 在本表加一项,驱动器零改动(票面「明确不做:rrsi/health
// 域接线(接口留出,域配置化)」——留的就是这张表)。适配器是数据+薄函数,不 import
// 任务/管线重件(防环;重件由驱动器按 rel 路径 spawn);例外=resolveAddPython(#357:
// 纯函数零重依赖,护栏② python 解析与驱动器/提案者面单源)。
import path from "node:path";
import { loadUniverse } from "../add-domain/score.mjs"; // 冻结宇宙单源(frozen 闸内建)
import { resolveAddPython } from "../../run-add.mjs"; // python 解析单源(#357:护栏自含,不依赖服务单元 IPDB_PYTHON)

// ── 保护名单(#356 P1-1 + delta 复审 P1):候选面 diff 不得触的路径,驱动器侧 diff
// 面闸(diffFaceGateTouched)的执法表——按域声明(adapter.protectedFaces),缺省并集
// = 五前缀 + 三执法链单件。为什么:无人值守失去人审 diff 兜底,而 trial 接线器与
// 钥匙打分是从候选树装载的(spawnTrialCli --repo faceRepo、scoreQuestion/score.mjs、
// run-trial 缺省宇宙 bench/add-domain/data/universe.jsonl 全读候选树)——提案者改
// 判分面/测试面即可自判 gained;三单件(delta P1)是同一执法链上「护栏在候选树
// cwd 跑候选副本」的三条中和路:护栏②跑的是候选树 bench/leak-check.mjs、其名单解析
// parseRoster 来自候选树 bench/roster.mjs(改空返回=零针装绿;run-trial.mjs 的
// checkRoundDiffLeak 同 import 此件)、护栏① npm test 读候选树 ops/agent-v2/package.json
// 的 scripts.test(改 no-op 即绿)。条目是 git pathspec:目录前缀=子树全量(含删除
// 与改名出的旧路径),文件级精确路径=单件(别用目录前缀误伤同目录开放面)。──
export const EVOLVE_PROTECTED_FACES = Object.freeze([
  "backend", // 答案本体:源实现+钥匙测试跑在候选树内(分母与实现面)
  "ops/agent-v2/tests", // 裁判测试面(npm test 护栏的判据来源;提案者不可改不可删)
  "ops/agent-v2/fixtures", // 测试夹具(含 evolve 罐装回合——提案者会话面)
  "ops/agent-v2/bench/add-domain", // 判分/接线面:score.mjs、run-trial.mjs、build-sandbox.mjs、data/universe.jsonl 及域内执法件
  "ops/agent-v2/bench/evolution", // 驱动器自身判分与记账面:judge/ledger/state/run-round/exits/domains——提案者同样不可触
  "ops/agent-v2/bench/leak-check.mjs", // 护栏②副本:leak 闸跑候选树此件(文件级;bench/ 其余是开放面)
  "ops/agent-v2/bench/roster.mjs", // 名单解析单源:leak-check 与 score 共用 parseRoster(改空返回=零针/零答案装绿)
  "ops/agent-v2/package.json", // 护栏①脚本面:npm test 读候选树 scripts.test(改 no-op 即绿)
]);

// add-domain 适配:考题 = universe split=evolve 面(25 题;heldout 是终局验收面,
// 演化循环不碰——盲测纪律);考题卡 = dev 侧生成物(gen-exam-cards.mjs 产物,env
// EVOLVE_CARDS_DIR 覆写,缺省主检出 dev/bench-add-domain/cards-v2 = 手动演化线在用面);
// trial = 候选/冠军面各自的 run-trial.mjs(--repo 同面,面=提示词/工具/任务接线整体)。
export const EVOLUTION_DOMAINS = Object.freeze({
  "add-domain": {
    skillRel: path.join("ops", "agent-v2", "bench", "add-domain", "SKILL.md"), // 提案者工作指令(驱动器检出面;候选改的是开放面内容,循环指令以驱动器侧为稳态单源)
    trialRunnerRel: path.join("ops", "agent-v2", "bench", "add-domain", "run-trial.mjs"),
    protectedFaces: EVOLVE_PROTECTED_FACES, // 域显式声明保护名单(delta P1:接线新域防忘——漏声明=diff 面闸 usage 红,不静默绿)
    evolveQuestions(universePath) {
      return loadUniverse(universePath).filter((r) => r.split === "evolve").map((r) => r.name);
    },
    cardsDir(mainRoot, env = process.env) {
      return env.EVOLVE_CARDS_DIR ? path.resolve(env.EVOLVE_CARDS_DIR) : path.join(mainRoot, "dev", "bench-add-domain", "cards-v2");
    },
    guardrails(worktree, env = process.env) {
      const cwd = path.join(worktree, "ops", "agent-v2");
      return [
        { name: "v2 全套(npm test)", cmd: ["npm", "test"], cwd, timeoutMs: 30 * 60_000 },
        // #357:泄漏闸名单取数须用主检出 venv 解释器(候选 worktree 无 venv、系统
        // python 无 ipdb → rc=2 假红;11-03 判例:主检出解释器+cwd 切 worktree/backend,
        // leak-check --python 即此形)。resolveAddPython 与驱动器提案者面(run-round.mjs)
        // 同源,OPS_ADD_PYTHON 显式优先、缺省主检出 venv——不依赖服务单元设 IPDB_PYTHON。
        { name: "泄漏闸(leak-check)", cmd: ["node", "bench/leak-check.mjs", "--python", resolveAddPython(env)], cwd, timeoutMs: 10 * 60_000 },
        { name: "faux 冒烟(add-trial 全链)", cmd: ["node", "--test", "tests/add-trial.test.mjs"], cwd, timeoutMs: 15 * 60_000 },
      ];
    },
  },
});

export function evolutionDomainOf(name) {
  const adapter = EVOLUTION_DOMAINS[name];
  if (!adapter)
    throw Object.assign(new Error(`域未接线:${name}(已接线:${Object.keys(EVOLUTION_DOMAINS).join(", ")};rrsi/health 见票 #356 留位)`), { usage: true });
  return adapter;
}
