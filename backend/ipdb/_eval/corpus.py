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

# SR-T2 D2(#213 / ADR 0011): benchmark 装配侧剔除自报段 —— 取表走
# layer_builders.scanner_ranges_prefixes(原始 CSV 直读), 段匹配复用
# truth_layer.apply_scanner_filter; import 方向 corpus → truth_layer/
# layer_builders 单向无环(两模块均只 import .assets)。
from .layer_builders import scanner_ranges_prefixes
from .truth_layer import apply_scanner_filter

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


def _source_raw_text(source) -> str | None:
    """源原始文本统一提取件(2026-11-22 评审 P1 下沉):目录源
    (archetypes §3c:firehol/blocklist_de/echelon)拼接目录内全部常规
    文件;文件源读单文件;缺路径/异径返 None。哨兵语料采样、月轮键集
    快照、other 分布探针三处共用以消除各自 is_file() 守卫对目录源的
    静默空转(gate 候选键集排除 0/0 判例)。"""
    path = getattr(source, "_path", None)
    if not path:
        return None
    if path.is_dir():
        return "\n".join(p.read_text(errors="ignore")
                          for p in sorted(path.iterdir()) if p.is_file())
    if path.is_file():
        return path.read_text(errors="ignore")
    return None


def sample_source_ips(source, n: int, rng: random.Random | None = None,
                      run_seed: int | None = None) -> list[str]:
    """Archetype-agnostic: regex-extract IP/CIDR tokens from the source's raw
    file and sample n (without replacement, capped at available).
    run_seed(S36)非 None 时覆盖 rng:run 级采样不随源名/文件内容可预测。
    目录源(archetypes §3c:firehol/blocklist_de/echelon)经
    _source_raw_text 拼接目录内全部常规文件(哨兵/语料采样对目录源同样
    生效,2026-11-22 echelon 首个目录源过哨兵时补;此前目录源在此返
    NO-MEMBERS)。"""
    if run_seed is not None:
        rng = random.Random(run_seed)   # run 级 seed 优先于外部 rng(S36 反定向策展)
    rng = rng or random.Random()
    text = _source_raw_text(source)
    if text is None:
        return []
    tokens = _IP_RE.findall(text)
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

    ADR 0011 装配侧剔除(#213): scanner_ranges 源不入采样宇宙(成员=
    厂商自报的段本身, 非指控观测, 入语料=自证污染); 其 CSV 在场时,
    采样/封顶后对 benchmark 每个分层过一遍自报段前缀 —— 其他 scanner
    源采出的段内 IP 同剔(census 2026-10-26 实测 80.2% 扫描器 IP 已在
    自报段)。宁少算不回补; v6 前缀值域与 v4 永不重叠, 混排安全
    (truth_layer.apply_scanner_filter)。无 scanner_ranges 源或其 CSV
    缺失 → 行为与现状逐位一致(排除器不启动)。benign/reserved 是固定
    小名单非采样面, 不动。
    """
    rng = rng or random.Random()
    bench: dict[str, list[str]] = {}
    selfdecl: list[str] = []
    for s in sources:
        if getattr(s, "eval_excluded", False):
            # 恒禁用源不入采样宇宙(spec 2026-11-02 §3:honyport 观测同
            # 时是真值语料组件,入语料=同源双用自证;与下方 scanner_ranges
            # 剔除同哲学的装配侧闸,保护库式调用方)
            continue
        if getattr(s, "self_declared_ranges", False):
            # 自报段源按声明识别(#409:scanner_ranges 声明 self_declared_ranges,
            # 此前按源名字符串匹配;同型新源声明即入,本文件不改):
            # 排除前缀只从在场 CSV 载入(缺文件=无排除=现状; D1 loader 的
            # raise 语义属 truth 装配侧, 这里 is_file 前置走 noop 分支)
            path = getattr(s, "_path", None)
            if path is not None and path.is_file():
                selfdecl = scanner_ranges_prefixes(path)
            continue
        ctype = getattr(s, "classification_type", None)
        if not ctype:
            continue
        ips = sample_source_ips(s, per_type_n, rng)
        bench.setdefault(ctype, []).extend(ips)
    # cap each stratum
    for k in list(bench.keys()):
        rng.shuffle(bench[k])
        bench[k] = bench[k][:per_type_n]
    if selfdecl:
        for k in list(bench.keys()):
            bench[k], _dropped = apply_scanner_filter(bench[k], selfdecl)
    return Corpus(
        benchmark=bench,
        benign=["8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222"],
        reserved=["10.0.0.1", "127.0.0.1", "192.168.1.1", "172.16.0.1"],
    )
