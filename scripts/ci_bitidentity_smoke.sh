#!/usr/bin/env bash
# R3-F2①:bench_lookup 位等价自往返 smoke(CI 与本地同款命令)。
# 锚 = GLOSSARY「位等价」:backend/scripts/bench_lookup.py(PYTHONHASHSEED=0
# 下同输入必得位相同输出,未来任何内核重写的迁移合同)。
#
# 合成 tiny 库(审计实证:合成空库开箱即崩,需 ≥1 源最小数据):
#   - ipinfo_lite 2×CIDR → 标量场融合路径(bench IPS 含 1.1.1.1 命中)
#   - binarydefense 2 条指控记录 → classification/merge 融合路径
# → --snapshot 落基线 → --compare 自往返,期待 exit 0 / bit-identical。
# R3-F2②(生产基线数字入库)备案不做:跨 CI runner/生产镜像 bench 数字
# 方差 = flaky 门风险,先立自往返门(B 批计划 Task 3 裁决)。
#
# 用法: scripts/ci_bitidentity_smoke.sh(CI backend job / 本地同款)
# 解释器:PYTHON 环境变量覆盖;缺省 backend/.venv 优先,否则 PATH 的 python。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -n "${PYTHON:-}" ]; then
    PY="$PYTHON"
elif [ -x "$REPO_ROOT/backend/.venv/bin/python" ]; then
    PY="$REPO_ROOT/backend/.venv/bin/python"
else
    PY=python
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DATA="$WORK/data"
mkdir -p "$DATA"

# 合成 tiny 库:复用生产 rebuild_lmdb 构库器(与 backend/tests/conftest.py
# 的 tiny_db fixture 同款形态),不另造 fixture 格式。
"$PY" - "$REPO_ROOT/backend" "$DATA" <<'PYEOF'
import sys
from pathlib import Path

backend, data = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, backend)
from ipdb._sources._lmdb import rebuild_lmdb

envs = []
rebuild_lmdb([                                    # 标量场源:country 融合路径
    ("8.8.8.0/24", {"country_code": "US", "_net": "8.8.8.0/24", "has_asn": False}),
    ("1.1.1.0/24", {"country_code": "AU", "_net": "1.1.1.0/24", "has_asn": False}),
], data / "ipinfo_lite.csv.lmdb", envs.append)
rebuild_lmdb([                                    # 指控源:classification 融合路径
    ("1.2.4.0/24", [{"classification_type": "blacklist", "verdict": "malicious",
                     "reliability": 0.5, "tags": ["binarydefense"]}]),
    ("5.9.182.96/32", [{"classification_type": "bruteforce", "verdict": "suspicious",
                        "reliability": 0.4}]),
], data / "binarydefense_banlist.txt.lmdb", envs.append)
for e in envs:
    e.close()                                     # py-lmdb 同路径双开禁止
print(f"tiny db: {data}")
PYEOF

export IP_RADAR_DATA_DIR="$DATA"
"$PY" "$REPO_ROOT/backend/scripts/bench_lookup.py" --snapshot "$WORK/bench-baseline.json"
"$PY" "$REPO_ROOT/backend/scripts/bench_lookup.py" --compare "$WORK/bench-baseline.json"
echo "bit-identity smoke: PASS(snapshot → compare 自往返零 diff)"
