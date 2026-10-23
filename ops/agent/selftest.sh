#!/usr/bin/env bash
# selftest.sh — lib.sh 函数族 + 台账/模板断言(T2 起;不真调 pi,全 fixture 化)
# 设计说明(任务书开放点):PRECEDENTS_DIR / LEDGER_FILE 用环境变量覆盖实现 fixture 隔离
# (lib.sh 落位默认值,一行成本,最简);sandbox_assert 无法用环境隔离出主仓 git 语义,
# 故就地污染本 worktree 的 backend/(touch→断言非零→清理,EXIT trap 兜底)。
set -u
AGENT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$AGENT/../.." && pwd)"

pass=0; fail=0
ok()  { pass=$((pass + 1)); echo "PASS $1"; }
bad() { fail=$((fail + 1)); echo "FAIL $1"; }
# 嵌套 docs 仓缺席守卫(T2;test_precedent_schema.py 同型):CI checkout 无 docs/(嵌套
# 独立仓,主仓 .gitignore 排除)→ 显式 SKIP 行并计 PASS,不是静默跳过;本地/worktree
# (docs 符号链接在)仍真跑守真章。守卫模式照 §10 供给守卫的「前置条件不满足」形。
# reason 可选第二参(缺省=docs 缺席;§10/§11 供给缺席同用此计数形,Info-3,T3 统一)。
skipok() { pass=$((pass + 1)); echo "SKIP $1: ${2:-嵌套 docs 仓缺席(CI checkout 判例,test_precedent_schema.py 同型)}"; }

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
# 「VAR=x 函数调用」的前缀赋值会在函数返回后泄漏到当前 shell(非 POSIX 模式)。
# docs 符号链接缺席(CI checkout)→ SKIP 显式计 PASS(T2 守卫,理由见 skipok 注释)。
if [[ -d "$ROOT/docs/ops/precedents" ]]; then
  OUT="$( (PRECEDENTS_DIR="$ROOT/docs/ops/precedents" inject_precedents 排他率) 2>&1)"
  [[ "$OUT" == *"2026-10-18-malicious-ip-mapping-vs-key-overlap.md"* ]] && ok "inject:真实库命中 malicious-ip 判例" || bad "inject:真实库命中 malicious-ip 判例"
  [[ "$OUT" == *"ruling_agreement: overruled"* ]]                        && ok "inject:reward 摘要含 ruling_agreement" || bad "inject:reward 摘要含 ruling_agreement"
else
  skipok "inject:真实库命中 malicious-ip 判例"
  skipok "inject:reward 摘要含 ruling_agreement"
fi

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

# docs 仓相对路径形:引真实判例文件(经 $ROOT/<相对路径> 解析,依赖 docs 符号链接在);
# 缺席 → SKIP 显式计 PASS(T2 守卫,brief 漏列此处的同型补齐,偏离记录待 review)
if [[ -f "$ROOT/docs/ops/precedents/2026-10-18-malicious-ip-mapping-vs-key-overlap.md" ]]; then
  PKG_DOCSPATH="$TMP/pkg-docspath.md"
  printf '## 注入判例\n- docs/ops/precedents/2026-10-18-malicious-ip-mapping-vs-key-overlap.md\n' > "$PKG_DOCSPATH"
  verify_cited_precedents "$PKG_DOCSPATH" >/dev/null 2>&1 && ok "verify:docs 仓相对路径形式通过" || bad "verify:docs 仓相对路径形式通过"
else
  skipok "verify:docs 仓相对路径形式通过"
fi

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
bash -n "$AGENT/lib.sh" 2>/dev/null && ok "lib.sh:bash 语法通过" || bad "lib.sh:bash 语法通过"

# ---- 6. 真实台账文件(docs 仓 docs/ops/ledger.md 首建表头;缺席 → SKIP 显式计 PASS,T2 守卫) ----
if [[ -f "$ROOT/docs/ops/ledger.md" ]]; then
  grep -q '^| 日期 | 轮次 | model | 用量 | 备注 |$' "$ROOT/docs/ops/ledger.md" 2>/dev/null \
    && ok "ledger:真实台账文件已建表头" || bad "ledger:真实台账文件已建表头"
else
  skipok "ledger:真实台账文件已建表头"
fi

# ---- 7. T3: feed_freshness / freshness_flags / extract_feed_urls ----
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

# extract_feed_urls(真实清单 ops/agent/feeds.txt;2026-10-23 事实层重构)
EFU="$(extract_feed_urls 2>/dev/null)"
[[ "$(awk '!/^https:\/\// && !/^http:\/\// {bad=1} END{print bad?1:0}' <<<"$EFU")" == "0" ]] \
  && ok "urls:全部 https?:// 形" || bad "urls:全部 https?:// 形"
grep -qx 'https://www.binarydefense.com/banlist.txt' <<<"$EFU" \
  && ok "urls:含 binarydefense feed URL" || bad "urls:含 binarydefense feed URL"
! grep -q '{' <<<"$EFU" \
  && ok "urls:排除 {token} 模板(ipinfo/ip2location 占位符)" || bad "urls:排除 {token} 模板(ipinfo/ip2location 占位符)"
[[ "$(wc -l <<<"$EFU")" -ge 50 ]] \
  && ok "urls:规模 ≥50(源覆盖面)" || bad "urls:规模 ≥50(源覆盖面)"
# 清单基线防漂移(2026-10-23 事实层重构随建):低于基线 = 清单被误删段;
# 源退役等合法缩量须同 PR 显式下调基线并说明缘由,不许无声缩水。
EFU_BASELINE=101
[[ "$(wc -l <<<"$EFU")" -ge "$EFU_BASELINE" ]] \
  && ok "urls:清单条数 ≥ 基线 $EFU_BASELINE(防漂移)" || bad "urls:清单条数 ≥ 基线 $EFU_BASELINE(防漂移)"
! grep -qv '^https://' <<<"$EFU" \
  && ok "urls:清单全 https(防劣质增量,审后补 P2-2)" || bad "urls:清单全 https(防劣质增量,审后补 P2-2)"

# ---- 7b. P1 T2 降噪三刀(spec #152 §2,票 #154):TOKEN_REQUIRED 分类 / raw 重试 / URL 排除面 ----
# 排除面真树断言:清单人工维护,排除面=清单内容本身;以下钉住历史事故/噪音
# 形状(2026-10-23 事故 + P1 T2 实证)永不经清单编辑回流。
! grep -q 'abuseipdb.com/account' <<<"$EFU" \
  && ok "urls:排除账号页 /account(事故形状不回流)" || bad "urls:排除账号页 /account(事故形状不回流)"
! grep -q 'confirmation.aspx' <<<"$EFU" \
  && ok "urls:排除微软下载确认页(事故形状不回流)" || bad "urls:排除微软下载确认页(事故形状不回流)"
! grep -qxE 'https://dataplane\.org/?' <<<"$EFU" \
  && ok "urls:排除 dataplane 首页(冻结 291 天伪报事故形状)" || bad "urls:排除 dataplane 首页(冻结 291 天伪报事故形状)"
! grep -q 'v2/files/exports' <<<"$EFU" \
  && ok "urls:排除 abuse.ch key 占位形状(匿名 404 伪报不可达)" || bad "urls:排除 abuse.ch key 占位形状(匿名 404 伪报不可达)"
! grep -qE '^https://raw\.githubusercontent\.com/.*/$' <<<"$EFU" \
  && ok "urls:raw.githubusercontent 无尾斜杠截断形(多行拼接事故形状)" || bad "urls:raw.githubusercontent 无尾斜杠截断形(多行拼接事故形状)"

# 清单解析面 fixture(^# 全注释行/行内 # 后剥除/空行跳过/首列即 URL):
EFU_MAN="$TMP/efu-manifest.txt"
cat > "$EFU_MAN" <<'FIXEOF'
# 分组头:https://fixture.example/comment-only.txt
https://fixture.example/code-feed.txt # source_a

https://fixture.example/accounts.json # source_b(行内注释含 https://fixture.example/trailing.txt,只取首列)
FIXEOF
EFU_FIX="$(extract_feed_urls "$EFU_MAN" 2>/dev/null)"
grep -qx 'https://fixture.example/code-feed.txt' <<<"$EFU_FIX" \
  && ok "urls:清单 URL 保留(fixture)" || bad "urls:清单 URL 保留(fixture)"
grep -qx 'https://fixture.example/accounts.json' <<<"$EFU_FIX" \
  && ok "urls:accounts.json 正常收录(fixture)" || bad "urls:accounts.json 正常收录(fixture)"
! grep -q 'comment-only' <<<"$EFU_FIX" \
  && ok "urls:^# 全注释行排除(fixture)" || bad "urls:^# 全注释行排除(fixture)"
! grep -q 'trailing' <<<"$EFU_FIX" \
  && ok "urls:行内 # 后内容剥除(fixture)" || bad "urls:行内 # 后内容剥除(fixture)"
[[ -z "$(grep '^$' <<<"$EFU_FIX")" ]] \
  && ok "urls:空行不产出行(fixture)" || bad "urls:空行不产出行(fixture)"
# stub curl(golden/run-golden.mjs stubCurl 判例同型:PATH 前置传输层替身,
# 头形对齐 _ff_code 解析);子Shell隔离 PATH,不污染上方真实 http.server 断言。
# 计数文件按 URL 哈希分铺——重试用例断言 curl 恰被调 3 次(raw)/2 次(非 raw)。
STUB_DIR="$TMP/t2-stubs"; STUB_CNT="$TMP/t2-cnt"
mkdir -p "$STUB_DIR" "$STUB_CNT"
export STUB_CNT   # stub 是独立进程,计数目录须经环境传导(PATH 同理由子Shell export)
cat > "$STUB_DIR/curl" <<'STUBEOF'
#!/usr/bin/env bash
# P1 T2 selftest stub:curl 传输层替身。末参=URL;tokenwall→403(鉴权墙);
# flaky→前两次 500 第三次起 200(瞬时失败);其余→404(确定性失败)。
url="${@: -1}"
key="$(printf '%s' "$url" | tr -cd 'a-zA-Z0-9' | tail -c 24)"
n=$(( $(cat "$STUB_CNT/$key" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$STUB_CNT/$key"
case "$url" in
  *tokenwall*)
    printf 'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n'; exit 0 ;;
  *flaky*)
    if (( n <= 2 )); then
      printf 'HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n'
    else
      printf 'HTTP/1.1 200 OK\r\nLast-Modified: %s\r\nContent-Length: 4\r\n\r\n' \
        "$(date -u '+%a, %d %b %Y %H:%M:%S GMT')"
    fi
    exit 0 ;;
esac
printf 'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n'
STUBEOF
chmod +x "$STUB_DIR/curl"

# 降噪刀一:401/403 → TOKEN_REQUIRED(需令牌·正常),不算 UNREACHABLE 不进异常旗标
T2_TOK="$( (export PATH="$STUB_DIR:$PATH"; _ff_probe 'https://api.tokenwall.example/feed.txt') 2>/dev/null)"
[[ "$(awk -F'\t' '{print $3}' <<<"$T2_TOK")" == "TOKEN_REQUIRED" ]] \
  && ok "probe:403 → TOKEN_REQUIRED(需令牌·正常)" || bad "probe:403 → TOKEN_REQUIRED(需令牌·正常)"
! grep -qE '(不可达|死键)' <<<"$(freshness_flags <<<"$T2_TOK")" \
  && ok "flags:TOKEN_REQUIRED 不进异常旗标(与 NO-LM 同待遇)" || bad "flags:TOKEN_REQUIRED 不进异常旗标(与 NO-LM 同待遇)"
T2_TOK_N="$( (export PATH="$STUB_DIR:$PATH"; cat "$STUB_CNT/$(printf '%s' 'https://api.tokenwall.example/feed.txt' | tr -cd 'a-zA-Z0-9' | tail -c 24)") 2>/dev/null)"
[[ "$T2_TOK_N" == 2 ]] \
  && ok "probe:鉴权墙不重试(HEAD+Range 恰 2 次)" || bad "probe:鉴权墙不重试(HEAD+Range 恰 2 次,实得 $T2_TOK_N)"

# 降噪刀三:raw.github 瞬时失败重试一轮再判;非 raw / 确定性失败不重试
T2_RAW="$( (export PATH="$STUB_DIR:$PATH"; _ff_probe 'https://raw.githubusercontent.com/flaky-org/feed.txt') 2>/dev/null)"
[[ "$(awk -F'\t' '{print $3}' <<<"$T2_RAW")" =~ ^[0-9]+$ ]] \
  && ok "probe:raw 前两连 500 重试后拿到读数(降噪刀三)" || bad "probe:raw 前两连 500 重试后拿到读数(降噪刀三)"
T2_RAW_N="$( (export PATH="$STUB_DIR:$PATH"; cat "$STUB_CNT/$(printf '%s' 'https://raw.githubusercontent.com/flaky-org/feed.txt' | tr -cd 'a-zA-Z0-9' | tail -c 24)") 2>/dev/null)"
[[ "$T2_RAW_N" == 3 ]] \
  && ok "probe:raw 重试恰多一轮(3 次 curl)" || bad "probe:raw 重试恰多一轮(3 次 curl,实得 $T2_RAW_N)"
T2_NORAW="$( (export PATH="$STUB_DIR:$PATH"; _ff_probe 'https://flaky-host.example/feed.txt') 2>/dev/null)"
[[ "$(awk -F'\t' '{print $3}' <<<"$T2_NORAW")" == "UNREACHABLE" ]] \
  && ok "probe:非 raw 同样两连 500 → UNREACHABLE(不重试)" || bad "probe:非 raw 同样两连 500 → UNREACHABLE(不重试)"
T2_NORAW_N="$( (export PATH="$STUB_DIR:$PATH"; cat "$STUB_CNT/$(printf '%s' 'https://flaky-host.example/feed.txt' | tr -cd 'a-zA-Z0-9' | tail -c 24)") 2>/dev/null)"
[[ "$T2_NORAW_N" == 2 ]] \
  && ok "probe:非 raw 恰 2 次 curl(重试仅限 raw.github)" || bad "probe:非 raw 恰 2 次 curl(重试仅限 raw.github,实得 $T2_NORAW_N)"
T2_404="$( (export PATH="$STUB_DIR:$PATH"; _ff_probe 'https://raw.githubusercontent.com/gone-org/feed.txt') 2>/dev/null)"
[[ "$(awk -F'\t' '{print $3}' <<<"$T2_404")" == "UNREACHABLE" ]] \
  && ok "probe:raw 确定性 404 不重试直判 UNREACHABLE" || bad "probe:raw 确定性 404 不重试直判 UNREACHABLE"
T2_404_N="$( (export PATH="$STUB_DIR:$PATH"; cat "$STUB_CNT/$(printf '%s' 'https://raw.githubusercontent.com/gone-org/feed.txt' | tr -cd 'a-zA-Z0-9' | tail -c 24)") 2>/dev/null)"
[[ "$T2_404_N" == 2 ]] \
  && ok "probe:raw 404 恰 2 次 curl(瞬时门不含 4xx)" || bad "probe:raw 404 恰 2 次 curl(瞬时门不含 4xx,实得 $T2_404_N)"

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

# ---- 10. T6: 金轨迹集(faux provider 跑真回路:Agent 循环+语义门+收口四件;不花 API) ----
# 真模型用例=smoke 层单列,仅 --smoke 手跑,本钩子永不触发(计划书 Task 6 Step 2)。
# 供给检查:node+依赖缺供则显式 SKIP 计 PASS(Info-3,T3 与 T2 守卫统一计数形;CI 侧由 npm ci 保证供给)。
if command -v node >/dev/null 2>&1 && [[ -d "$AGENT/node_modules/@earendil-works/pi-agent-core" ]] \
   && command -v rg >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  GOLDOUT="$(node "$AGENT/golden/run-golden.mjs" 2>&1)"; GOLDRC=$?
  GP_N="$(grep -c '^GOLDENPASS ' <<<"$GOLDOUT" || true)"
  GF_N="$(grep -c '^GOLDENFAIL ' <<<"$GOLDOUT" || true)"
  if (( GOLDRC == 0 && GF_N == 0 && GP_N >= 8 )); then
    ok "golden:faux 用例集全绿(${GP_N} 例,布尔判据)"
  else
    bad "golden:faux 用例集失败(PASS=${GP_N} FAIL=${GF_N})"
    printf '%s\n' "$GOLDOUT" | grep -E '^(GOLDENFAIL|  )' || true
  fi
  # 分类点名(冻结面:正例×2/负例三发/边界×2;smoke 层隔离面)
  grep -q 'GOLDENPASS health_summary_format' <<<"$GOLDOUT" \
    && ok "golden:正例①健康快照摘要格式+near_band 179/180 边界" || bad "golden:正例①健康快照摘要格式+near_band 179/180 边界"
  grep -q 'GOLDENPASS discover_predicate_hit' <<<"$GOLDOUT" \
    && ok "golden:正例②discover 谓词命中路径(门放行入队)" || bad "golden:正例②discover 谓词命中路径(门放行入队)"
  grep -q 'GOLDENPASS discover_midround_search_citation' <<<"$GOLDOUT" \
    && ok "golden:正例③轮中 search_precedents 命中引用放行(闭集=预注入∪本会话命中,活时并集;neg3 拒侧反面)" \
    || bad "golden:正例③轮中 search_precedents 命中引用放行(闭集=预注入∪本会话命中,活时并集;neg3 拒侧反面)"
  grep -q 'GOLDENPASS neg1_enqueue_without_measurement' <<<"$GOLDOUT" \
    && ok "golden:负例①无实测 ENQUEUE 被门挡零写队列" || bad "golden:负例①无实测 ENQUEUE 被门挡零写队列"
  grep -q 'GOLDENPASS neg2_failed_envelope_as_evidence' <<<"$GOLDOUT" \
    && ok "golden:负例②失败信封入 evidence 被拒" || bad "golden:负例②失败信封入 evidence 被拒"
  grep -q 'GOLDENPASS neg3_fabricated_precedent_citation' <<<"$GOLDOUT" \
    && ok "golden:负例③编造判例引用被闭合校验拦(轮次失败+台账已记账)" || bad "golden:负例③编造判例引用被闭合校验拦(轮次失败+台账已记账)"
  grep -q 'GOLDENPASS boundary_enqueue_rate_24_9' <<<"$GOLDOUT" && grep -q 'GOLDENPASS boundary_enqueue_rate_25_0' <<<"$GOLDOUT" \
    && ok "golden:边界排他 24.9 拒/25.0 入(门线两侧)" || bad "golden:边界排他 24.9 拒/25.0 入(门线两侧)"
  ! grep -qE 'GOLDENPASS smoke_' <<<"$GOLDOUT" \
    && ok "golden:smoke 真模型层零触发(冒烟层隔离面)" || bad "golden:smoke 真模型层零触发(冒烟层隔离面)"
  node --check "$AGENT/golden/run-golden.mjs" 2>/dev/null \
    && ok "golden:runner node 语法通过" || bad "golden:runner node 语法通过"
  node -e 'JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"))' "$AGENT/golden/cases.json" 2>/dev/null \
    && ok "golden:用例集 json 可解析" || bad "golden:用例集 json 可解析"
else
  skipok "golden:金轨迹集" "供给缺(node/node_modules/rg/git)——CI 由 npm ci 保证"
fi

# ---- 11. Task 1: spawn 契约(表对拍/in-process faux main/真 spawn 冒烟;零 API) ----
if command -v node >/dev/null 2>&1 && [[ -d "$AGENT/node_modules/@earendil-works/pi-agent-core" ]] \
   && command -v rg >/dev/null 2>&1 && command -v git >/dev/null 2>&1; then
  CTOUT="$(node "$AGENT/selftest-contract.mjs" 2>&1)"; CTRC=$?
  CTPASS_N="$(grep -c '^CONTRACTPASS ' <<<"$CTOUT" || true)"
  CTFAIL_N="$(grep -c '^CONTRACTFAIL ' <<<"$CTOUT" || true)"
  if (( CTRC == 0 && CTFAIL_N == 0 && CTPASS_N > 0 )); then
    ok "contract:三层测试全绿(${CTPASS_N} 例)"
  else
    bad "contract:三层测试失败(PASS=${CTPASS_N} FAIL=${CTFAIL_N})"
    printf '%s\n' "$CTOUT" | grep '^CONTRACTFAIL' || true
  fi
  # 分层点名(规格 §8 验收面)
  grep -q 'CONTRACTPASS 表对拍:表内每项真被读' <<<"$CTOUT" \
    && ok "contract:env 表双向对拍(SPAWN_CONTRACT_ENV ↔ 生产文件真读)" || bad "contract:env 表双向对拍(SPAWN_CONTRACT_ENV ↔ 生产文件真读)"
  grep -q 'CONTRACTPASS in-process:成功轮 stdout 单行 JSON' <<<"$CTOUT" \
    && ok "contract:成功轮轮次信封(stdout 单行 JSON 逐字段)" || bad "contract:成功轮轮次信封(stdout 单行 JSON 逐字段)"
  grep -q 'CONTRACTPASS in-process:失败轮 model_face' <<<"$CTOUT" \
    && ok "contract:失败轮信封(code=model_face/empty_text,pkg 缺席)" || bad "contract:失败轮信封(code=model_face/empty_text,pkg 缺席)"
  grep -q 'CONTRACTPASS spawn:badround' <<<"$CTOUT" \
    && ok "contract:真 spawn 冒烟(badround exit1+bad_round;用法错 exit2 无 JSON)" || bad "contract:真 spawn 冒烟(badround exit1+bad_round;用法错 exit2 无 JSON)"
  node --check "$AGENT/selftest-contract.mjs" 2>/dev/null \
    && ok "contract:runner node 语法通过" || bad "contract:runner node 语法通过"
else
  skipok "contract:spawn 契约三层测试" "供给缺(node/node_modules/rg/git)——CI 由 npm ci 保证"
fi

echo "----"
echo "selftest: PASS=$pass FAIL=$fail"
(( fail == 0 )) || exit 1
exit 0
