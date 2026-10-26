// 工件名表单源(#202 C1 / spec C1;#207 T1 扩双管线):轮目录工件名的唯一真源(健康轮+发现轮)。
// 为什么:gates.mjs(inputs 声明/读面)、steps.mjs(写出面)、selftest-pipeline.mjs(清单面)三层
// 曾各持手抄字符串(同名字符串 ~70 处),漂移即静默错位;单源后漂移由闭包哨
// (selftest「工件名表单源」测)双向拦截:名表加项不更新写出面=红;步面新写工件不入表=红。
// 红线:磁盘工件文件名逐字节冻结(位等价判例)——本表改值=改磁盘名,须过重放/位等价双门。
// 范围:轮目录(ctx.dir)固定名 + 逐假设 DEEP 参数族;retro/<round>.json(ctx.opsRoot 级)、
// breaker.json(opsRoot 级)、state.json 之外的 opsRoot 面不在本表(见 #201 C1-C3 分工)。

// 18 个固定工件名 = 一个完整跑毕的健康轮(VERIFY 两分支都写 02-verify-rules.json)必有的固定面。
export const ARTIFACTS = Object.freeze({
  PROBE_FRESHNESS_TSV: "01-probe-freshness.tsv",
  PROBE_MATRIX: "01-probe-matrix.json",
  PROBE_SUMMARY: "01-probe-summary.json",
  VERIFY_RULES: "02-verify-rules.json",
  VERIFY_SURVIVORS: "02-verify-survivors.json",
  VERIFY_SUPPRESSED: "02-verify-suppressed.json",
  TRIAGE_HYPOTHESES: "03-triage-hypotheses.json",
  TRIAGE_TRANSCRIPT: "03-triage-transcript.jsonl",
  DISPATCH_BUNDLES: "04-dispatch-bundles.json",
  DEEP_VERDICTS: "05-deep-verdicts.json",
  ITEMIZE_MANIFEST: "06-itemize-manifest.json",
  SYNTH_REPORT: "07-synth-report.md",
  SYNTH_TRANSCRIPT: "07-synth-transcript.jsonl",
  ANCHOR_SWEEP: "08-anchor-sweep.json",
  ANCHOR_SWEEP_EXITS: "08-anchor-sweep-exits.json",
  BUDGET: "09-budget.json",
  GATES: "gates.json",
  STATE: "state.json",
  // 发现轮四步工件(#207 T1;spec /tmp/discover-pipeline-spec.md T1 节):
  // d1 候选宇宙快照/ d2 模型结构化候选/ d3 确定性测量/ d4 入队留痕。
  // d2-shortlist-transcript.jsonl 是步侧产物不入名表(faux.mjs transcriptName 同 health TRIAGE_TRANSCRIPT 面:名表=轮目录固定业务面,transcript 由步面管)。
  DISCOVER_SCAN: "d1-scan.json",
  DISCOVER_SHORTLIST: "d2-shortlist.json",
  DISCOVER_MEASURE: "d3-measure.json",
  DISCOVER_ENQUEUE: "d4-enqueue.json",
});

// 名表闭包面(清单遍历/闭包哨差集都用它;禁止 Object.keys 当名字用)。全量 22 名。
export const ARTIFACT_NAMES = Object.freeze(Object.values(ARTIFACTS));

// 轮型固定面派生(#207 T1):闭包哨/门对拍按轮型取面,不拿全量 22 名错拍他轮目录。
const DISCOVER_FIXED = ["DISCOVER_SCAN", "DISCOVER_SHORTLIST", "DISCOVER_MEASURE", "DISCOVER_ENQUEUE"];
export const HEALTH_ARTIFACT_NAMES = Object.freeze(ARTIFACT_NAMES.filter((n) => !DISCOVER_FIXED.some((k) => ARTIFACTS[k] === n))); // 健康轮 18 固定名(位等价:与 #202 C1 表逐字节同)
export const discoverArtifactNames = () => DISCOVER_FIXED.map((k) => ARTIFACTS[k]).concat([ARTIFACTS.BUDGET, ARTIFACTS.GATES, ARTIFACTS.STATE]); // 发现轮 7 固定名(d1-d4+09/gates/state)

// 发现轮 SHORTLIST transcript 名(#217 T3.5):real/faux 同名;不入 ARTIFACTS 固定表(表=健康轮 18 名
// 位等价冻结面)也不入 discoverArtifactNames(闭包哨测试以额外名单独钉)。单源理由:faux.mjs
// transcriptName(写出面)与 discovery-host.mjs replayDiscoverSeeds(CLOSE 回放读面)共用,
// 两处手抄=回放读不到留痕。字节冻结(磁盘名位等价判例同固定表)。
export const DISCOVER_SHORTLIST_TRANSCRIPT = "d2-shortlist-transcript.jsonl";

// 逐假设 DEEP 参数族:名字由假设 slug 拼出(slug=hidSlug(url)),不入固定表。
export const deepArtifactName = (slug) => `05-deep-${slug}.json`;
export const deepTranscriptName = (slug) => `05-deep-${slug}-transcript.jsonl`;
// 参数族枚举/匹配面(gates G_DEEP 巡检、steps deepSeeds 过滤、闭包哨差集判定)。
export const DEEP_ARTIFACT_RE = /^05-deep-.*\.json$/; // 注意:05-deep-verdicts.json 也命中(固定表先行扣除)
export const DEEP_TRANSCRIPT_RE = /^05-deep-.*-transcript\.jsonl$/;
export const DEEP_TRANSCRIPT_GLOB = "05-deep-*-transcript.jsonl"; // 参数族通配标签(仅 gates inputs 声明面;非单文件名)
