#!/usr/bin/env bash
# probe-egress.sh — agent 外联路由一次性探测(#304②;只读探测,不写仓内任何文件)。
#
# 缘起:Exa/jina 断流每轮被会话重新发现(票 #304 清单 2);「哪些外联通道活着」
# 应是一条命令的事,不靠逐轮重新踩坑。默认清单=agent 研究四通道各取根端点,
# 事实源(2026-11-04 搜仓核得,均嵌套 docs 仓):
#   - notes/ops-agent-golden-standard-research-2026-10-24.md 通道判例
#     (r.jina.ai 对 github 匿名 403→raw.githubusercontent+API 兜底)
#   - notes/anchor-eval-research-2026-10-28.md 获取方式注记
#     (① exa 网页搜索 ② r.jina.ai 网页读取 ③ 本地 curl 直拉 ④ gh/GitHub API)
# 改默认清单须带出处;scripts/test_probe_egress.py 钉死四通道不静默缩水。
#
# 用法:
#   scripts/probe-egress.sh                  # 探默认清单(四通道)
#   scripts/probe-egress.sh URL [URL ...]    # 追加端点(去重保序;须 http(s)://)
#   scripts/probe-egress.sh --list [URL ...] # 只列清单不联网
#   scripts/probe-egress.sh --timeout 15     # 单端点超时秒数(默认 10)
#
# 语义:GET 探测丢 body 只记 HTTP 码+耗时(r.jina.ai 等对 HEAD 有 403 判例,故不用 HEAD);
# 探测件不持门——不可达也是有效观测,退出码恒 0;只有用法错才非 0。

set -euo pipefail

TIMEOUT_S=10
LIST_ONLY=0
ENDPOINTS=(
  "https://exa.ai"
  "https://r.jina.ai"
  "https://api.github.com"
  "https://raw.githubusercontent.com"
)

usage() {
  cat <<'USAGE'
用法:scripts/probe-egress.sh [--list] [--timeout S] [URL ...]
  默认探 agent 外联四通道;URL 追加;--list 只列不联网;--timeout 单端点秒数(默认 10)。
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --list)
      LIST_ONLY=1
      shift
      ;;
    --timeout)
      if [ -z "${2:-}" ]; then
        echo "用法错:--timeout 需要一个秒数参数(如 --timeout 15)" >&2
        exit 2
      fi
      TIMEOUT_S="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*|-*)
      echo "用法错:未知参数 $1(见 --help)" >&2
      exit 2
      ;;
    *)
      case "$1" in
        http://*|https://*) ;;
        *)
          echo "用法错:追加端点须以 http(s):// 开头,得到「$1」(见 --help)" >&2
          exit 2
          ;;
      esac
      ENDPOINTS+=("$1")
      shift
      ;;
  esac
done

# 去重保序(默认清单序在前,追加序在后)
mapfile -t ENDPOINTS < <(printf '%s\n' "${ENDPOINTS[@]}" | awk '!seen[$0]++')

if [ "$LIST_ONLY" -eq 1 ]; then
  printf '%s\n' "${ENDPOINTS[@]}"
  exit 0
fi

printf '%-40s %-8s %s\n' 'ENDPOINT' 'HTTP' '耗时(秒)'
probe_one() {
  local url="$1" meta
  if meta="$(curl -sS -o /dev/null --max-time "$TIMEOUT_S" \
        -w '%{http_code} %{time_total}' "$url" 2>&1)"; then
    printf '%-40s %-8s %s\n' "$url" "${meta% *}" "${meta#* }"
  else
    # 失败时 meta 是 curl 的 stderr 文本;取首行做诊断,宁报不可达不猜状态
    printf '%-40s %-8s %s\n' "$url" '不可达' "${meta%%$'\n'*}(超时上限 ${TIMEOUT_S}s)"
  fi
}
for ep in "${ENDPOINTS[@]}"; do
  probe_one "$ep"
done
