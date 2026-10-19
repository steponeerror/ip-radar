#!/usr/bin/env bash
# selftest.sh — lib.sh 四函数 + 台账/模板/round.sh 骨架断言(T2;不真调 pi,全 fixture 化)
# 设计说明(任务书开放点):PRECEDENTS_DIR / LEDGER_FILE 用环境变量覆盖实现 fixture 隔离
# (lib.sh 落位默认值,一行成本,最简);sandbox_assert 无法用环境隔离出主仓 git 语义,
# 故就地污染本 worktree 的 backend/(touch→断言非零→清理,EXIT trap 兜底)。
set -u
AGENT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$AGENT/../.." && pwd)"

pass=0; fail=0
ok()  { pass=$((pass + 1)); echo "PASS $1"; }
bad() { fail=$((fail + 1)); echo "FAIL $1"; }

TMP="$(mktemp -d)"
FF_SRV_PIDS=()   # T3 http.server fixture 进程(cleanup 兜底杀)
cleanup() { rm -rf "$TMP"; rm -f "$ROOT/backend/.selftest-pollution"; kill "${FF_SRV_PIDS[@]}" 2>/dev/null || true; }
trap cleanup EXIT

# ---- fixture:两条假判例 + 应被排除的 _schema.md ----
FIXDIR="$TMP/precedents"; mkdir -p "$FIXDIR"
cat > "$FIXDIR/2026-01-01-fixture-aggregator.md" <<'EOF'
---
id: 2026-01-01-fixture-aggregator
date: 2026-01-01
subject: fixture — 聚合器候选必须实测排他率
context: >
  候选某聚合器 README 声称聚合的出版方全部已收录,
  推断 ~100% 重叠。
recommendation: REJECT(上游映射推断)。
human_ruling: >
  实测排他率 50.0%(150/300),推翻 REJECT,立项。
reward:
  hard_gates:
    exclusive_rate: "50.0%"
  ruling_agreement: overruled
  production_delta: null
lineage:
  - "fixture"
superseded_by: null
---

正文检索词:聚合器 排他率 回声。
EOF
cat > "$FIXDIR/2026-01-02-fixture-sunset.md" <<'EOF'
---
id: 2026-01-02-fixture-sunset
date: 2026-01-02
subject: fixture — 冻结 feed 判死
context: >
  feed 头 Last-Modified 冻结 240 天,sunset 硬门命中。
recommendation: REJECT(sunset)。
human_ruling: >
  判死(冻结 240 天 ≥ 180 天门线)。
reward:
  hard_gates:
    frozen_days: 240
  ruling_agreement: agreed
  production_delta: null
lineage:
  - "fixture"
superseded_by: null
---

正文检索词:冻结 sunset 死键。
EOF
# _schema.md 含检索词,必须被 inject 排除
echo "schema 说明,含词:排他率" > "$FIXDIR/_schema.md"

# ---- 加载被测(lib.sh 缺失 = RED 门) ----
if [[ ! -f "$AGENT/lib.sh" ]]; then
  echo "FAIL lib.sh 不存在(TDD RED:先跑出失败)"
  exit 1
fi
export PRECEDENTS_DIR="$FIXDIR"
export LEDGER_FILE="$TMP/ledger.md"
# shellcheck source=lib.sh
source "$AGENT/lib.sh"

# ---- 1. inject_precedents ----
OUT="$(inject_precedents 排他率 2>&1)"
[[ "$OUT" == *"2026-01-01-fixture-aggregator.md"* ]]  && ok "inject:命中条目列文件名"  || bad "inject:命中条目列文件名"
[[ "$OUT" == *"context: "* ]]                        && ok "inject:context 摘要行"   || bad "inject:context 摘要行"
[[ "$OUT" == *"human_ruling: "* ]]                   && ok "inject:human_ruling 摘要行" || bad "inject:human_ruling 摘要行"
[[ "$OUT" == *"reward: "* ]]                         && ok "inject:reward 摘要行"    || bad "inject:reward 摘要行"
[[ "$OUT" != *"_schema.md"* ]]                       && ok "inject:排除 _schema.md"  || bad "inject:排除 _schema.md"

OUT="$(inject_precedents 不存在的词xyz 2>&1)"
[[ "$OUT" == *"无判例(检索词: 不存在的词xyz)"* ]]   && ok "inject:零命中显式无判例行" || bad "inject:零命中显式无判例行"

# 真实判例库冒烟(只读):frontmatter 解析对 12 条种子成立。子壳隔离:bash 对
# 「VAR=x 函数调用」的前缀赋值会在函数返回后泄漏到当前 shell(非 POSIX 模式)
OUT="$( (PRECEDENTS_DIR="$ROOT/docs/ops/precedents" inject_precedents 排他率) 2>&1)"
[[ "$OUT" == *"2026-10-18-malicious-ip-mapping-vs-key-overlap.md"* ]] && ok "inject:真实库命中 malicious-ip 判例" || bad "inject:真实库命中 malicious-ip 判例"
[[ "$OUT" == *"ruling_agreement: overruled"* ]]                        && ok "inject:reward 摘要含 ruling_agreement" || bad "inject:reward 摘要含 ruling_agreement"

# ---- 2. verify_cited_precedents ----
PKG_OK="$TMP/pkg-ok.md"
printf '# 裁决包\n\n## 注入判例\n- 2026-01-01-fixture-aggregator.md\n' > "$PKG_OK"
verify_cited_precedents "$PKG_OK" >/dev/null 2>&1 && ok "verify:存在路径通过" || bad "verify:存在路径通过"

PKG_NONE="$TMP/pkg-none.md"
printf '# 裁决包\n\n## 注入判例\n无判例(检索词: xxx)\n' > "$PKG_NONE"
verify_cited_precedents "$PKG_NONE" >/dev/null 2>&1 && ok "verify:无判例节通过" || bad "verify:无判例节通过"

PKG_FAKE="$TMP/pkg-fake.md"
printf '# 裁决包\n\n## 注入判例\n- 9999-01-01-fabricated.md\n' > "$PKG_FAKE"
OUT="$(verify_cited_precedents "$PKG_FAKE" 2>&1)"; RC=$?
[[ $RC -ne 0 ]]                                       && ok "verify:编造路径非零退出" || bad "verify:编造路径非零退出"
[[ "$OUT" == *"9999-01-01-fabricated.md"* ]]          && ok "verify:打印编造路径"    || bad "verify:打印编造路径"

PKG_NOSEC="$TMP/pkg-nosec.md"
printf '# 裁决包\n\n## 建议\n- ACCEPT\n' > "$PKG_NOSEC"
OUT="$(verify_cited_precedents "$PKG_NOSEC" 2>&1)"; RC=$?
[[ $RC -ne 0 ]] && ok "verify:缺注入判例节非零" || bad "verify:缺注入判例节非零"
[[ "$OUT" == *"缺少「注入判例」节"* ]] && ok "verify:缺节报错指明原因" || bad "verify:缺节报错指明原因"

PKG_DOCSPATH="$TMP/pkg-docspath.md"
printf '## 注入判例\n- docs/ops/precedents/2026-10-18-malicious-ip-mapping-vs-key-overlap.md\n' > "$PKG_DOCSPATH"
verify_cited_precedents "$PKG_DOCSPATH" >/dev/null 2>&1 && ok "verify:docs 仓相对路径形式通过" || bad "verify:docs 仓相对路径形式通过"

# ---- 3. ledger_append ----
rm -f "$LEDGER_FILE"
ledger_append health glm-5.3-flash "pi_rc=0 out_len=42" >/dev/null 2>&1
grep -q '^| 日期 | 轮次 | model | 用量 | 备注 |$' "$LEDGER_FILE" && ok "ledger:首建含表头" || bad "ledger:首建含表头"
[[ "$(grep -c '^| 2026-' "$LEDGER_FILE")" == 1 ]] && ok "ledger:首行数据落账" || bad "ledger:首行数据落账"
ledger_append discover default "pi_rc=0 out_len=100" >/dev/null 2>&1
[[ "$(grep -c '^| 日期 | 轮次 | model | 用量 | 备注 |$' "$LEDGER_FILE")" == 1 ]] && ok "ledger:重复追加不重建表头" || bad "ledger:重复追加不重建表头"
[[ "$(grep -c '^| 2026-' "$LEDGER_FILE")" == 2 ]] && ok "ledger:第二行数据落账" || bad "ledger:第二行数据落账"

# ---- 4. sandbox_assert(就地污染本 worktree,EXIT trap 兜底清理) ----
sandbox_assert >/dev/null 2>&1 && ok "sandbox:干净态零退出" || bad "sandbox:干净态零退出"
touch "$ROOT/backend/.selftest-pollution"
OUT="$(sandbox_assert 2>&1)"; RC=$?
[[ $RC -ne 0 ]] && ok "sandbox:污染态非零退出" || bad "sandbox:污染态非零退出"
[[ "$OUT" == *".selftest-pollution"* ]] && ok "sandbox:打印污染清单" || bad "sandbox:打印污染清单"
rm -f "$ROOT/backend/.selftest-pollution"
sandbox_assert >/dev/null 2>&1 && ok "sandbox:清理后恢复零退出" || bad "sandbox:清理后恢复零退出"

# ---- 5. 提示词拆分与语法(T3.5:*-system.md 系统提示化,占位符机制退役) ----
for p in health discover; do
  f="$AGENT/prompts/$p-system.md"
  [[ -f "$f" ]] && ! grep -q '{{' "$f" \
    && ok "prompt:$p-system.md 存在且无占位符" || bad "prompt:$p-system.md 存在且无占位符"
  [[ ! -f "$AGENT/prompts/$p.md" ]] \
    && ok "prompt:旧 $p.md 已改造退役" || bad "prompt:旧 $p.md 已改造退役"
done
bash -n "$AGENT/round.sh" 2>/dev/null && ok "round.sh:bash 语法通过" || bad "round.sh:bash 语法通过"
bash -n "$AGENT/lib.sh" 2>/dev/null && ok "lib.sh:bash 语法通过" || bad "lib.sh:bash 语法通过"

# ---- 5b. T3.5: run_pi 解析器(罐装 JSONL 经 PI_BIN stub,不真调 pi) ----
# 事件形状 = 2026-10-19 真流实测:末个 assistant message_end 携 text+usage+
# stopReason;agent_settled.aborted 为全局中止旗标。四态判定(JSON 模式下 pi
# 不必然非零退出,失败面必须 run_pi 自判)。
PI_STUB="$TMP/pi-stub.sh"
cat > "$PI_STUB" <<'EOF'
#!/usr/bin/env bash
# selftest stub:记录 run_pi 传下的旗标与 stdin,stdout 吐罐装事件流
printf '%s\n' "$*" > "$PI_STUB_ARGS"
cat > "$PI_STUB_STDIN"
cat "$PI_STUB_FIXTURE"
exit "${PI_STUB_RC:-0}"
EOF
chmod +x "$PI_STUB"
# 注意:PI_STUB_FIXTURE 每例重赋,必须在 export 列表里(非导出的普通变量
# 进不了 stub 子进程——首跑 6 FAIL 即此坑,2026-10-19)
export PI_BIN="$PI_STUB" PI_STUB_ARGS="$TMP/pi.args" PI_STUB_STDIN="$TMP/pi.stdin" PI_STUB_FIXTURE=/dev/null PI_STUB_RC=0

# 成功态:双 assistant message_end——文本取末个,用量取全部回合求和(实测每回合
# 重置非累计,2026-10-19 多回合探针 /tmp/jitrl-t35-multiturn.jsonl)
cat > "$TMP/pi-ok.jsonl" <<'EOF'
{"type": "session", "id": "fixture"}
{"type": "message_end", "message": {"role": "system", "content": ""}}
{"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "早轮文本"}], "usage": {"input": 1, "output": 1, "totalTokens": 2, "cost": {"total": 0.0001}}, "stopReason": "stop"}}
{"type": "message_end", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "略"}, {"type": "text", "text": "最终摘要文本"}], "usage": {"input": 10976, "output": 40, "totalTokens": 11144, "cost": {"total": 0.00155936}}, "stopReason": "stop"}}
{"type": "agent_settled", "aborted": false}
EOF
PI_STUB_FIXTURE="$TMP/pi-ok.jsonl"
PI_TEXT=""; PI_USAGE=""
run_pi --no-tools <<<"用户消息内容" 2>/dev/null && ok "run_pi:成功态零退出" || bad "run_pi:成功态零退出"
[[ "${PI_TEXT:-}" == "最终摘要文本" ]] && ok "run_pi:最终文本=末个 assistant" || bad "run_pi:最终文本=末个 assistant"
[[ "${PI_USAGE:-}" == "in=10977 out=41 total=11146 cost=0.00165936" ]] \
  && ok "run_pi:用量四真数=全部 assistant 回合求和(1+10976 等)" || bad "run_pi:用量四真数=全部 assistant 回合求和(1+10976 等)"
grep -q -- '--mode json --no-session --no-extensions --no-tools -- -' "$PI_STUB_ARGS" \
  && ok "run_pi:调用面旗标钉死(json/no-session/no-extensions/-- -)" || bad "run_pi:调用面旗标钉死(json/no-session/no-extensions/-- -)"
grep -q '用户消息内容' "$PI_STUB_STDIN" && ok "run_pi:prompt 经 stdin 传递" || bad "run_pi:prompt 经 stdin 传递"

# 失败三态 + pi 进程非零
cat > "$TMP/pi-stoperr.jsonl" <<'EOF'
{"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "部分文本"}], "usage": {"input": 10, "output": 5, "totalTokens": 15, "cost": {"total": 0.001}}, "stopReason": "error"}}
{"type": "agent_settled", "aborted": false}
EOF
PI_STUB_FIXTURE="$TMP/pi-stoperr.jsonl"
OUT="$(run_pi 2>&1)"; RC=$?
[[ $RC -ne 0 ]] && ok "run_pi:stopReason=error 判失败" || bad "run_pi:stopReason=error 判失败"
[[ "$OUT" == *"stopReason=error"* ]] && ok "run_pi:失败原因含 stopReason" || bad "run_pi:失败原因含 stopReason"

cat > "$TMP/pi-abort.jsonl" <<'EOF'
{"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "文本"}], "usage": {"input": 10, "output": 5, "totalTokens": 15, "cost": {"total": 0.001}}, "stopReason": "stop"}}
{"type": "agent_settled", "aborted": true}
EOF
PI_STUB_FIXTURE="$TMP/pi-abort.jsonl"
OUT="$(run_pi 2>&1)"; RC=$?
[[ $RC -ne 0 ]] && ok "run_pi:agent_settled.aborted 判失败" || bad "run_pi:agent_settled.aborted 判失败"
[[ "$OUT" == *"aborted"* ]] && ok "run_pi:失败原因含 aborted" || bad "run_pi:失败原因含 aborted"

cat > "$TMP/pi-empty.jsonl" <<'EOF'
{"type": "message_end", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "只有思考无正文"}], "usage": {"input": 10, "output": 5, "totalTokens": 15, "cost": {"total": 0.001}}, "stopReason": "stop"}}
{"type": "agent_settled", "aborted": false}
EOF
PI_STUB_FIXTURE="$TMP/pi-empty.jsonl"
OUT="$(run_pi 2>&1)"; RC=$?
[[ $RC -ne 0 ]] && ok "run_pi:空最终文本判失败" || bad "run_pi:空最终文本判失败"
[[ "$OUT" == *"空"* ]] && ok "run_pi:失败原因指明空文本" || bad "run_pi:失败原因指明空文本"

PI_STUB_FIXTURE=/dev/null PI_STUB_RC=1
OUT="$(run_pi 2>&1)"; RC=$?
[[ $RC -ne 0 ]] && ok "run_pi:pi 进程非零退出判失败" || bad "run_pi:pi 进程非零退出判失败"
unset PI_BIN PI_STUB_ARGS PI_STUB_STDIN PI_STUB_FIXTURE PI_STUB_RC

# ---- 6. 真实台账文件(docs 仓 docs/ops/ledger.md 首建表头) ----
grep -q '^| 日期 | 轮次 | model | 用量 | 备注 |$' "$ROOT/docs/ops/ledger.md" 2>/dev/null \
  && ok "ledger:真实台账文件已建表头" || bad "ledger:真实台账文件已建表头"

# ---- 7. T3: feed_freshness / freshness_flags / extract_feed_urls / matrix_summary ----
# fixture:本地 http.server 双目录(冻结 mtime / 活跃 touch;HEAD 由 http.server 原生支持,
# Last-Modified = 文件 mtime)。mtime 拍 epoch 且留 600s 余量,防 179/180 边界因
# 探测耗时跨天抖动。
FF_FR="$TMP/ff-frozen"; FF_AC="$TMP/ff-active"
mkdir -p "$FF_FR" "$FF_AC"
ff_set_age() {  # <days> <file>
  touch -d "@$(( $(date +%s) - $1 * 86400 - 600 ))" "$2"
}
for d in 179 180 200; do echo x > "$FF_FR/f$d.txt"; ff_set_age "$d" "$FF_FR/f$d.txt"; done
echo x > "$FF_AC/live.txt"; touch "$FF_AC/live.txt"

ff_start_server() {  # <dir> → echo <port>;随机端口避撞,起失败重试
  local dir="$1" i j p
  for i in 1 2 3 4 5; do
    p=$(( 20000 + RANDOM % 30000 ))
    python3 -m http.server "$p" --bind 127.0.0.1 --directory "$dir" >/dev/null 2>&1 &
    FF_SRV_PIDS+=($!)
    for j in $(seq 1 30); do
      curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$p/" && { echo "$p"; return 0; }
      sleep 0.1
    done
  done
  return 1
}
ff_closed_port() {  # 找一个确证拒绝连接的端口(UNREACHABLE fixture)
  local p
  while :; do
    p=$(( 20000 + RANDOM % 30000 ))
    curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$p/" && continue
    echo "$p"; return 0
  done
}
FF_FR_PORT=""; FF_AC_PORT=""
FF_FR_PORT="$(ff_start_server "$FF_FR")" && ok "fixture:冻结目录 server 起来" || bad "fixture:冻结目录 server 起来"
FF_AC_PORT="$(ff_start_server "$FF_AC")" && ok "fixture:活跃目录 server 起来" || bad "fixture:活跃目录 server 起来"
FF_CLOSED="$(ff_closed_port)"
furl() { echo "http://127.0.0.1:$1/$2"; }

if [[ -n "$FF_FR_PORT" && -n "$FF_AC_PORT" ]]; then
  FF_TSV="$(feed_freshness "$(furl "$FF_FR_PORT" f179.txt)" "$(furl "$FF_FR_PORT" f180.txt)" \
                     "$(furl "$FF_FR_PORT" f200.txt)" "$(furl "$FF_AC_PORT" live.txt)" \
                     "$(furl "$FF_CLOSED" x)" 2>/dev/null)"
  [[ "$(wc -l <<<"$FF_TSV")" -eq 5 ]] && ok "fresh:行数守恒(并发不丢行)" || bad "fresh:行数守恒(并发不丢行)"
  ff_col() { awk -F'\t' -v u="$1" -v c="$3" '$1==u{print $c}' <<<"$2"; }
  [[ "$(ff_col "$(furl "$FF_FR_PORT" f179.txt)" "$FF_TSV" 3)" == "179" ]] \
    && ok "fresh:179 天边界读数正确" || bad "fresh:179 天边界读数正确"
  [[ "$(ff_col "$(furl "$FF_FR_PORT" f180.txt)" "$FF_TSV" 3)" == "180" ]] \
    && ok "fresh:180 天边界读数正确" || bad "fresh:180 天边界读数正确"
  [[ "$(ff_col "$(furl "$FF_FR_PORT" f200.txt)" "$FF_TSV" 3)" == "200" ]] \
    && ok "fresh:冻结 200 天读数正确" || bad "fresh:冻结 200 天读数正确"
  [[ "$(ff_col "$(furl "$FF_AC_PORT" live.txt)" "$FF_TSV" 3)" == "0" ]] \
    && ok "fresh:活跃源 age=0" || bad "fresh:活跃源 age=0"
  [[ "$(ff_col "$(furl "$FF_AC_PORT" live.txt)" "$FF_TSV" 2)" != "NO-LM" ]] \
    && ok "fresh:活跃行带 Last-Modified" || bad "fresh:活跃行带 Last-Modified"
  [[ "$(ff_col "$(furl "$FF_CLOSED" x)" "$FF_TSV" 3)" == "UNREACHABLE" ]] \
    && ok "fresh:坏端口 URL → UNREACHABLE" || bad "fresh:坏端口 URL → UNREACHABLE"

  FF_FLAGS="$(freshness_flags <<<"$FF_TSV")"
  grep -q "f180.txt" <<<"$FF_FLAGS" && grep -q "死键嫌疑" <<<"$FF_FLAGS" \
    && ok "flags:180 天标死键嫌疑(≥ 门线含 180)" || bad "flags:180 天标死键嫌疑(≥ 门线含 180)"
  grep -q "f200.txt" <<<"$FF_FLAGS" \
    && ok "flags:200 天标死键嫌疑" || bad "flags:200 天标死键嫌疑"
  ! grep -q "f179.txt" <<<"$FF_FLAGS" \
    && ok "flags:179 天不标(边界不越界)" || bad "flags:179 天不标(边界不越界)"
  ! grep -q "live.txt" <<<"$FF_FLAGS" \
    && ok "flags:活跃源不标" || bad "flags:活跃源不标"
  grep -q "不可达" <<<"$FF_FLAGS" && grep -q ":$FF_CLOSED/" <<<"$FF_FLAGS" \
    && ok "flags:坏端口标不可达" || bad "flags:坏端口标不可达"
else
  bad "fixture:http.server 起不来,T3 断言整组失效"
fi

# extract_feed_urls(真实 worktree 只读扫描)
EFU="$(extract_feed_urls 2>/dev/null)"
[[ "$(awk '!/^https:\/\// && !/^http:\/\// {bad=1} END{print bad?1:0}' <<<"$EFU")" == "0" ]] \
  && ok "urls:全部 https?:// 形" || bad "urls:全部 https?:// 形"
grep -qx 'https://www.binarydefense.com/banlist.txt' <<<"$EFU" \
  && ok "urls:含 binarydefense feed URL" || bad "urls:含 binarydefense feed URL"
! grep -q '{' <<<"$EFU" \
  && ok "urls:排除 {token} 模板(ipinfo/ip2location 占位符)" || bad "urls:排除 {token} 模板(ipinfo/ip2location 占位符)"
[[ "$(wc -l <<<"$EFU")" -ge 50 ]] \
  && ok "urls:规模 ≥50(源覆盖面)" || bad "urls:规模 ≥50(源覆盖面)"

# matrix_summary.py(小 fixture;真实读数冒烟归 round.sh health)
MS_FIX="$TMP/ms.json"
cat > "$MS_FIX" <<'EOF'
{"exit_code": 2, "counts": {"violation": 1, "pending": 0, "agreement": 3},
 "layers": {"truth": {"status": "NO-LAYER", "members": 0, "sampled": 0, "notes": ["no-asset"]},
            "infra": {"status": "OK", "members": 5, "sampled": 5}},
 "buckets": {"violation": [{"cell": "infra|malicious|UI", "note": "ruling-confirmed", "evidence": []}],
             "pending": [], "agreement": []}}
EOF
MS_OUT="$(python3 "$AGENT/matrix_summary.py" "$MS_FIX" 2>&1)"
grep -q 'violation=1' <<<"$MS_OUT" && ok "mssum:counts 行" || bad "mssum:counts 行"
grep -q 'infra|malicious|UI' <<<"$MS_OUT" && ok "mssum:violation 格列出" || bad "mssum:violation 格列出"
grep -q 'NO-LAYER' <<<"$MS_OUT" && ok "mssum:层状态含 NO-LAYER" || bad "mssum:层状态含 NO-LAYER"

# ---- 8. T4: pi-agent-core 宿主(node 单测:语义门/负例三发/SSRF/读面/队列幂等;不花 API 不真调网络) ----
if command -v node >/dev/null 2>&1; then
  T4OUT="$(node "$AGENT/selftest-t4.mjs" 2>&1)"; T4RC=$?
  for line in $T4OUT; do :; done  # 占位(下面逐行计数)
  T4PASS_N="$(grep -c '^T4PASS ' <<<"$T4OUT" || true)"
  T4FAIL_N="$(grep -c '^T4FAIL ' <<<"$T4OUT" || true)"
  if (( T4RC == 0 && T4FAIL_N == 0 && T4PASS_N > 0 )); then
    ok "t4:node 单测全绿(${T4PASS_N} 例,含负例三发+语义门)"
  else
    bad "t4:node 单测失败(PASS=${T4PASS_N} FAIL=${T4FAIL_N})"
    printf '%s\n' "$T4OUT" | grep '^T4FAIL' || true
  fi
  # 负例三发逐项点名(验收 c 针脚:三发各自必须在汤)
  grep -q 'T4PASS 负例①' <<<"$T4OUT" && ok "t4:负例①无实测 ENQUEUE 被门挡" || bad "t4:负例①无实测 ENQUEUE 被门挡"
  grep -q 'T4PASS 负例②' <<<"$T4OUT" && ok "t4:负例②失败信封作 evidence 被拒" || bad "t4:负例②失败信封作 evidence 被拒"
  grep -q 'T4PASS 负例③' <<<"$T4OUT" && ok "t4:负例③编造判例路径被闭合校验拦" || bad "t4:负例③编造判例路径被闭合校验拦"
else
  bad "t4:node 不可用(宿主运行前置)"
fi
[[ -f "$AGENT/package.json" ]] && grep -q 'pi-agent-core' "$AGENT/package.json" \
  && ok "t4:package.json 声明 pi-agent-core 依赖" || bad "t4:package.json 声明 pi-agent-core 依赖"
[[ -d "$AGENT/node_modules/@earendil-works/pi-agent-core" ]] \
  && ok "t4:npm install 已落位" || bad "t4:npm install 已落位"
git -C "$ROOT" check-ignore -q "$AGENT/node_modules" \
  && ok "t4:node_modules 已入 .gitignore" || bad "t4:node_modules 已入 .gitignore"
# round.sh 弃用标注(T4 边界:保留文件不删)
grep -q '已弃用' "$AGENT/round.sh" && ok "t4:round.sh 已标弃用(保留)" || bad "t4:round.sh 已标弃用(保留)"
node --check "$AGENT/agent.mjs" 2>/dev/null && node --check "$AGENT/tools.mjs" 2>/dev/null \
  && node --check "$AGENT/models.mjs" 2>/dev/null \
  && ok "t4:agent/tools/models 三模块 node 语法通过" || bad "t4:agent/tools/models 三模块 node 语法通过"

# ---- 9. T4: 提示词条款钉子(谓词表三条/自动入队/信封处置/验证条款;health 信封条款) ----
DISC="$AGENT/prompts/discover-system.md"
grep -q 'sunset_frozen' "$DISC" && grep -q 'mirror_echo' "$DISC" && grep -q 'zero_asset' "$DISC" \
  && ok "prompt:discover 谓词表三条在文" || bad "prompt:discover 谓词表三条在文"
grep -q '0.25' "$DISC" && grep -q 'control_pass' "$DISC" \
  && ok "prompt:discover 自动入队条件在文" || bad "prompt:discover 自动入队条件在文"
grep -q '信封处置' "$DISC" && grep -q '禁止替失败补数' "$DISC" \
  && ok "prompt:discover 信封处置条款在文" || bad "prompt:discover 信封处置条款在文"
grep -q '工具返回验证' "$DISC" \
  && ok "prompt:discover 工具返回验证条款在文" || bad "prompt:discover 工具返回验证条款在文"
grep -q 'health_snapshot' "$AGENT/prompts/health-system.md" && grep -q '信封处置' "$AGENT/prompts/health-system.md" \
  && ok "prompt:health 信封处置条款+快照工具在文" || bad "prompt:health 信封处置条款+快照工具在文"

echo "----"
echo "selftest: PASS=$pass FAIL=$fail"
(( fail == 0 )) || exit 1
exit 0
