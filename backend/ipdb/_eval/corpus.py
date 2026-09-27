# backend/ipdb/_eval/corpus.py
"""Stratified eval corpus: frozen benchmark (per-type malicious + benign +
reserved) + a frozen neutral stratum (W0 layer 2) + a dynamic candidate
stratum. The frozen part is a curated asset tracked in git for
reproducibility; the candidate stratum is sampled fresh per evaluation.
"""
import hashlib
import json
import random
import re
from dataclasses import dataclass, field, asdict
from ipaddress import IPv4Address

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d+)?\b")


@dataclass
class Corpus:
    benchmark: dict[str, list[str]] = field(default_factory=dict)  # type -> ips
    benign: list[str] = field(default_factory=list)
    reserved: list[str] = field(default_factory=list)
    neutral: list[str] = field(default_factory=list)  # W0 中性公网层(静态资产 neutral_ips.json)
    candidate_ips: list[str] = field(default_factory=list)

    def all_ips(self) -> list[str]:
        out = list(self.candidate_ips) + list(self.benign) + list(self.reserved)
        out.extend(self.neutral)           # 中性层在 benchmark 之前
        for ips in self.benchmark.values():
            out.extend(ips)
        # de-dup preserving order
        seen, dedup = set(), []
        for ip in out:
            if ip not in seen:
                seen.add(ip); dedup.append(ip)
        return dedup

    def save(self, path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path) -> "Corpus":
        # 只收 dataclass 已知键:旧 corpus.json 缺 neutral 键走默认值,
        # 未来多余键也不炸
        d = json.loads(path.read_text())
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def stable_seed(name: str) -> int:
    """Process-independent int seed from a name (hash() is PYTHONHASHSEED-salted)."""
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big")


def generate_neutral(n: int = 600, seed: int = 20260928) -> list[str]:
    """均匀拒绝采样 n 个公网单播 IPv4(纯函数;固定 seed 跨进程可复现,
    seed = 计划批准日 20260928)。产出一次性固化为 neutral_ips.json 静态资产,
    运行期不再重新采样(W0 中性层必须逐轮恒定)。"""
    rng = random.Random(seed)
    out: list[str] = []
    seen: set[str] = set()
    while len(out) < n:
        addr = IPv4Address(rng.getrandbits(32))
        # is_global 已排除私网/回环/链路本地/文档段;组播与保留段双保险
        if not addr.is_global or addr.is_multicast or addr.is_reserved:
            continue
        ip = str(addr)
        if ip not in seen:
            seen.add(ip); out.append(ip)
    return out


def sample_source_ips(source, n: int, rng: random.Random | None = None) -> list[str]:
    """Archetype-agnostic: regex-extract IP/CIDR tokens from the source's raw
    file and sample n (without replacement, capped at available)."""
    rng = rng or random.Random()
    if not getattr(source, "_path", None) or not source._path.is_file():
        return []
    tokens = _IP_RE.findall(source._path.read_text(errors="ignore"))
    ips = [t.split("/")[0] for t in tokens]            # strip CIDR mask
    ips = [ip for ip in ips if ip.count(".") == 3]
    uniq = list(dict.fromkeys(ips))
    rng.shuffle(uniq)
    return uniq[:n]


def build_benchmark(sources, per_type_n: int,
                    rng: random.Random | None = None) -> Corpus:
    """Seed the frozen benchmark by sampling per-type IPs from threat sources.

    `sources` are baseline sources (candidate excluded). Each threat source
    contributes IPs bucketed by its classification_type. benign/reserved
    strata are the small known lists below (fixed; grow the lists, not knobs).
    """
    rng = rng or random.Random()
    bench: dict[str, list[str]] = {}
    for s in sources:
        ctype = getattr(s, "classification_type", None)
        if not ctype:
            continue
        ips = sample_source_ips(s, per_type_n, rng)
        bench.setdefault(ctype, []).extend(ips)
    # cap each stratum
    for k in list(bench.keys()):
        rng.shuffle(bench[k])
        bench[k] = bench[k][:per_type_n]
    return Corpus(
        benchmark=bench,
        benign=["8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222"],
        reserved=["10.0.0.1", "127.0.0.1", "192.168.1.1", "172.16.0.1"],
    )
