"""候选 feed 对池实测排他率探针(2026-10-18 malicious-ip 82.7%/ziyadnz
44.7% 两起翻案用的 /tmp 一次性探针产品化;GLOSSARY「独占贡献」锚)。

协议(逐字 = /tmp 探针,discover 治理日常可调用):
- 阳性对照闸:binarydefense 原始文件前 20 个 bare IP,池命中 ≥18 否则
  ABORT——数据面没信该信的东西,继续跑就是假零/回声(哲学 2 无证据即无话),
  不出任何数字;
- 指控口径:任一 classification detail 的 verdict ∈ _types._ACCUSING
  (单一真源 live 导入,勿硬编码;缺 verdict 键兑底 malicious,layered
  _accusing_sources 同款);排他 = 池内无任何指控 detail;
- 采样 random.Random(seed).shuffle(uniq)[:300],同 seed 逐字节可复现;
- 单个 lookup 失败即抛,不 except-continue(2026-10-10 假零判例)。
"""
import random
from collections import Counter
from pathlib import Path

from .corpus import _IP_RE
from .._types import _ACCUSING

SAMPLE_N = 300
DEFAULT_SEED = 20261018             # 两起翻案探针同 seed,历史数字可逐位复算
CONTROL_N = 20
CONTROL_MIN_HITS = 18
SAMPLE_SHOW = 8


class ControlAbort(RuntimeError):
    """对照闸失败:DB 未正常加载或对照 raw 失位 —— 继续只会出假零。"""


def extract_feed_keys(text: str) -> list[str]:
    """候选键提取(口径同 corpus.sample_source_ips,文件版):_IP_RE 抓
    IP/CIDR token → 剥 mask → v4 → 去重保序。"""
    ips = [t.split("/")[0] for t in _IP_RE.findall(text)]
    ips = [ip for ip in ips if ip.count(".") == 3]
    return list(dict.fromkeys(ips))


def sample_keys(uniq: list[str], seed: int, n: int = SAMPLE_N) -> list[str]:
    """random.Random(seed).shuffle(uniq)[:n] —— 同 seed 同序,不触碰入参。"""
    out = list(uniq)
    random.Random(seed).shuffle(out)
    return out[:n]


def flagged_sources(ip: str, lookup) -> set[str]:
    """池指控源集:任一 classification detail 的 verdict ∈ _ACCUSING,
    归因到 detail.source;lookup 失败原样上抛,绝不吞。"""
    payload = lookup(ip)
    out: set[str] = set()
    for ca in (payload.get("classifications") or {}).values():
        for d in ca.get("details") or ():
            if d.get("verdict", "malicious") in _ACCUSING and d.get("source"):
                out.add(d["source"])
    return out


def control_file_ips(path, n: int = CONTROL_N) -> list[str]:
    """binarydefense 原始文件前 n 个 bare IP(探针同款:剥 # 注释/空行)。"""
    out: list[str] = []
    for ln in Path(path).read_text(errors="ignore").splitlines():
        ip = ln.strip()
        if ip and not ip.startswith("#") and ip.count(".") == 3:
            out.append(ip)
        if len(out) >= n:
            break
    return out


def run(feed_path, lookup, *, control_path, seed: int = DEFAULT_SEED,
        sample_n: int = SAMPLE_N) -> dict:
    """对照闸 → 候选采样 → 逐点查池。人读/--json 共用此返回形状;
    对照失败 → ControlAbort;feed 提取零键 → 炸(空分母不冒充 0)。"""
    ctrl = control_file_ips(control_path)
    hits = sum(1 for ip in ctrl if flagged_sources(ip, lookup))
    if hits < CONTROL_MIN_HITS:
        raise ControlAbort(
            "ABORT: control failed —— 对照源未获池覆盖,数据面未正常加载或"
            "对照 raw 失位;不打印排他率数字")
    uniq = extract_feed_keys(Path(feed_path).read_text(errors="ignore"))
    if not uniq:
        raise ValueError(f"feed 提取零个候选键: {feed_path}")
    sample = sample_keys(uniq, seed, sample_n)
    exclusive: list[str] = []
    cover: Counter = Counter()
    for ip in sample:
        srcs = flagged_sources(ip, lookup)
        if srcs:
            cover.update(srcs)
        else:
            exclusive.append(ip)
    return {
        "feed": str(feed_path),
        "seed": seed,
        "feed_unique_keys": len(uniq),
        "sampled": len(sample),
        "exclusive": len(exclusive),
        "covered": len(sample) - len(exclusive),
        "exclusive_rate": len(exclusive) / len(sample),
        "coverage_sources": dict(cover.most_common()),
        "exclusive_sample": exclusive[:SAMPLE_SHOW],
        "control": {"file": str(control_path), "n": len(ctrl),
                    "hits": hits, "required": CONTROL_MIN_HITS},
    }
