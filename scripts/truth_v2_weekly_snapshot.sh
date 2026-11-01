#!/bin/sh
# ip-radar 真值层 v2 · T0 周快照采集器(ADR 0017 / docs/research/2026-11-01-truth-layer-v2-spec.md)
# 部署位:203.88.124.85:/opt/ip-truth-capture/weekly_snapshot.sh,周日 04:17 cron。
# 每周把 auth.log 全部轮转里的攻击源 IP 固化到 snapshots/,防 logrotate 两周丢史。
# 服务端只做尽力清洗(剔 Accepted 登录源 + ops_allowlist);语料构建器(T1)
# 会再走完整清洗链,本件只需同输入可复算。
# 本文件是服务器脚本的仓内正本(可复算凭据);服务器上是同一份的拷贝。
set -eu
OUT=/opt/ip-truth-capture/snapshots
ALLOW=/opt/ip-truth-capture/ops_allowlist.txt
mkdir -p "$OUT"; touch "$ALLOW"
TS=$(date +%Y-%m-%dT%H:%M:%S%z)
SPAN=$(zcat -f /var/log/auth.log* 2>/dev/null | sed -n '1p' | awk '{print $1,$2}')
F="$OUT/$(date +%Y-%m-%d).csv"
BODY=$(mktemp)
zcat -f /var/log/auth.log* 2>/dev/null | awk '
  /Failed password|Invalid user|maximum authentication attempts/ {
    if (match($0, /from ([0-9]{1,3}\.){3}[0-9]{1,3}/)) {
      ip = substr($0, RSTART+5, RLENGTH-5); atk[ip]++
    }
  }
  /Accepted (password|publickey)/ {
    if (match($0, /from ([0-9]{1,3}\.){3}[0-9]{1,3}/)) {
      ops[substr($0, RSTART+5, RLENGTH-5)] = 1
    }
  }
  END {
    for (ip in atk) if (!(ip in ops)) print ip "," atk[ip]
  }' > "$BODY.raw"
grep -vxF -f "$ALLOW" "$BODY.raw" > "$BODY" || true
{
  echo "# ip-radar truth-v2 weekly snapshot"
  echo "# captured_at=$TS log_span_head=\"$SPAN\" host=$(hostname)"
  echo "# method=auth.log* {Failed password|Invalid user|max-auth} minus {Accepted login} sources minus ops_allowlist"
  echo "ip,attempts"
  sort -t, -k2,2 -rn "$BODY"
} > "$F"
rm -f "$BODY" "$BODY.raw"
echo "wrote $F ($(grep -cvc '^#' "$F") data lines)"
