# backend/ipdb/_eval/keysets.py
"""月度逐源键集快照 + 长记忆列表推导(S23)。

长记忆列表 = 在任一在册源键集中持续在场 ≥min_days 的 IP(供真值层
描述性切分 S9/F5)。哲学 3「宁少算」: 段必须终止于最新快照, 缺席/断月
即断连, 不插值补月; 缺证据 ≠ 清白更 ≠ 连续。

键集枚举复用 corpus.sample_source_ips 同源提取法(eval 包唯一真实路径:
Source 不暴露键迭代 API, 逐源原始文件正则抽 IP/CIDR token、去 mask、
去重、排序)。
"""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .corpus import _IP_RE


def _source_ips(source) -> list[str]:
    """逐源当前键集: 原始文件 IP token 去重排序(与 sample_source_ips 同款提取)。"""
    path = getattr(source, "_path", None)
    if not path or not Path(path).is_file():
        return []
    tokens = _IP_RE.findall(Path(path).read_text(errors="ignore"))
    ips = {t.split("/")[0] for t in tokens}          # strip CIDR mask
    ips = {ip for ip in ips if ip.count(".") == 3}
    return sorted(ips)


def export_source_keysets(sources, out_dir: Path, run_id: str,
                          corpus_fingerprint: str | None = None,
                          now: float | None = None) -> Path:
    """落一轮快照到 <out_dir>/<run_id>/, 返回 run 目录。

    逐源 <source>.txt.gz(mtime=0 确定性 gzip: 同键集字节可复现, 冻结工件
    同款要求)+ meta.json: run_id/日期/corpus_version_fingerprint
    (S22 长记忆冻结时点绑语料版本, 缺省记 null)/逐源 count。
    """
    run_dir = Path(out_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for s in sources:
        ips = _source_ips(s)
        counts[s.name] = len(ips)
        data = ("\n".join(ips) + "\n").encode() if ips else b""
        with open(run_dir / f"{s.name}.txt.gz", "wb") as f:
            # filename="" 头部不嵌源文件名: 同键集字节可复现与源名无关
            with gzip.GzipFile(filename="", fileobj=f, mode="wb",
                               mtime=0) as gz:
                gz.write(data)
    ts = datetime.now(timezone.utc).timestamp() if now is None else now
    meta = {
        "run_id": run_id,
        "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
        "corpus_version_fingerprint": corpus_fingerprint,
        "counts": counts,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return run_dir


def long_memory_ips(keyset_dir: Path, min_days: int = 90,
                    max_gap_days: int = 45) -> set[str]:
    """扫 <keyset_dir> 下全部 run(按各自 meta.json 日期排序)推导长记忆列表。

    保守三连: 段终止于最新快照日期 ∧ 末−首 ≥ min_days ∧ 段内相邻在场日
    间隔全 ≤ max_gap_days(缺席造成的缺口超限即断段)。在场 = 该轮任一源
    键集含此 IP(逐轮并集)。日历用天级差值, 不用自然月。
    """
    kd = Path(keyset_dir)
    if not kd.is_dir():
        return set()
    runs: list[tuple[int, set[str]]] = []
    for run_dir in sorted(kd.iterdir()):
        meta_p = run_dir / "meta.json"
        if not run_dir.is_dir() or not meta_p.is_file():
            continue
        meta = json.loads(meta_p.read_text())  # 坏 json → 直接炸, 不静默缩水
        ips: set[str] = set()
        for gz_p in run_dir.glob("*.txt.gz"):
            with gzip.open(gz_p, "rt") as gz:
                ips.update(line for line in gz.read().splitlines() if line)
        runs.append((date.fromisoformat(meta["date"]).toordinal(), ips))
    if not runs:
        return set()
    runs.sort(key=lambda r: r[0])
    latest = runs[-1][0]
    presence: dict[str, list[int]] = {}
    for d, ips in runs:                 # runs 已按日期升序 → 逐 IP 日期升序
        for ip in ips:
            presence.setdefault(ip, []).append(d)
    out: set[str] = set()
    for ip, days in presence.items():
        if days[-1] != latest:          # 末见 ≠ 最新快照 → 出局(宁少算)
            continue
        first = days[-1]
        for later, earlier in zip(reversed(days[1:]), reversed(days[:-1])):
            if later - earlier > max_gap_days:   # 断月缺口超限 → 段在此截断
                break
            first = earlier
        if latest - first >= min_days:
            out.add(ip)
    return out
