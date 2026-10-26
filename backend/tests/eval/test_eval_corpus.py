# backend/test_eval_corpus.py
import ipaddress, json, tempfile, os, random
from pathlib import Path
from ipdb._eval.corpus import Corpus, sample_source_ips, build_benchmark, stable_seed

class _FakeSource:
    """Stand-in for a source: has _path pointing at a temp raw file."""
    def __init__(self, name, path, classification_type="blacklist"):
        self.name = name
        self._path = Path(path)
        self.classification_type = classification_type

def test_sample_source_ips_extracts_via_regex(tmp_path):
    raw = tmp_path / "feed.txt"
    raw.write_text("# comment\n10.0.0.1\nnot-an-ip\n192.168.1.5\n8.8.8.8\n")
    src = _FakeSource("s", raw)
    ips = sample_source_ips(src, n=10, rng=random.Random(0))
    assert set(ips) <= {"10.0.0.1", "192.168.1.5", "8.8.8.8"}
    assert "not-an-ip" not in ips

def test_corpus_save_load_roundtrip(tmp_path):
    c = Corpus(benchmark={"c2-server": ["1.1.1.1"]}, benign=["8.8.8.8"],
               reserved=["10.0.0.0"], candidate_ips=["2.2.2.2"])
    p = tmp_path / "corpus.json"
    c.save(p)
    loaded = Corpus.load(p)
    assert loaded == c

def test_all_ips_union(tmp_path):
    c = Corpus(benchmark={"a": ["1.1.1.1"], "b": ["2.2.2.2"]}, benign=["8.8.8.8"],
               reserved=["10.0.0.0"], candidate_ips=["3.3.3.3"])
    assert set(c.all_ips()) == {"1.1.1.1", "2.2.2.2", "8.8.8.8", "10.0.0.0", "3.3.3.3"}

def test_build_benchmark_partitions_by_type(tmp_path):
    # one fake source per type, 5 IPs each
    sources = []
    for t in ["c2-server", "phishing"]:
        raw = tmp_path / f"{t}.txt"
        raw.write_text("\n".join(f"10.{i}.{i}.{i}" for i in range(1,6)))
        sources.append(_FakeSource(t, raw, classification_type=t))
    bench = build_benchmark(sources, per_type_n=3, rng=random.Random(0))
    assert set(bench.benchmark.keys()) == {"c2-server", "phishing"}
    assert all(len(v) <= 3 for v in bench.benchmark.values())
    # 固定小名单:strata 恒满(曾为旋钮,现硬编码)
    assert len(bench.benign) == 4 and len(bench.reserved) == 4

def test_sample_source_ips_skips_directory(tmp_path):
    d = tmp_path / "firehol"
    d.mkdir()
    (d / "level1.netset").write_text("1.2.3.4\n5.6.7.8\n")
    src = _FakeSource("firehol", d)            # _path is a directory
    assert sample_source_ips(src, n=10, rng=random.Random(0)) == []


def test_stable_seed_is_deterministic_and_process_independent():
    # same name -> same seed; not hash()-salted
    assert stable_seed("tweetfeed") == stable_seed("tweetfeed")
    assert stable_seed("tweetfeed") != stable_seed("urlhaus")


def test_sample_source_ips_seeded_is_reproducible(tmp_path):
    raw = tmp_path / "big.txt"
    raw.write_text("\n".join(f"10.0.0.{i}" for i in range(1, 201)))  # 200 IPs, sample 100
    src = _FakeSource("cand", raw, "phishing")
    a = sample_source_ips(src, 100, random.Random(stable_seed("cand")))
    b = sample_source_ips(src, 100, random.Random(stable_seed("cand")))
    assert a == b                       # same seed -> same sample
    assert len(a) == 100                # actually subsamples (200 available)


def test_sample_respects_run_seed_over_rng(tmp_path):
    # S36:run_seed 覆盖外部 rng —— 同 run_seed 两次采样同序(外部 rng
    # 不同也同),不同 run_seed 不同序:源策展人无法预测采样序列
    raw = tmp_path / "big.txt"
    raw.write_text("\n".join(f"10.0.0.{i}" for i in range(1, 301)))  # 300 IPs, sample 100
    src = _FakeSource("cand", raw, "phishing")
    a = sample_source_ips(src, 100, random.Random(0), run_seed=42)
    b = sample_source_ips(src, 100, random.Random(1), run_seed=42)  # 外部 rng 被覆盖
    assert a == b
    assert sample_source_ips(src, 100, random.Random(0), run_seed=43) != a


# ── SR-T2 D2: benchmark 装配侧剔除自报段(ADR 0011) ────────────

def test_build_benchmark_excludes_selfdeclared_members_all_strata(tmp_path):
    # ①scanner_ranges 源不入采样宇宙(成员=厂商声明的段本身,非指控观测,
    # 入语料=自证污染);②采样/封顶后逐分层剔自报段成员 —— 其他源采出的
    # 段内 IP 同剔(census 实测 80.2% 扫描器 IP 已在自报段)。逐 IP 判定用
    # ipaddress 独立算(非 apply_scanner_filter 回声,防 tautology)。
    sr_csv = tmp_path / "scanner_ranges.csv"
    sr_csv.write_text("40.124.175.0/24,Stretchoid\n203.0.113.0/24,Xpanse\n")
    sr = _FakeSource("scanner_ranges", sr_csv, classification_type="scanner")
    sw_raw = tmp_path / "sw.txt"
    sw_raw.write_text("40.124.175.29\n203.0.113.5\n198.51.100.7\n192.0.2.9\n")
    sw = _FakeSource("sw_scanners", sw_raw, classification_type="scanner")
    et_raw = tmp_path / "et.txt"
    et_raw.write_text("40.124.175.30\n198.51.100.8\n")
    et = _FakeSource("et", et_raw, classification_type="exploit-traffic")
    bench = build_benchmark([sr, sw, et], per_type_n=10, rng=random.Random(0))
    nets = [ipaddress.ip_network(p) for p in
            ("40.124.175.0/24", "203.0.113.0/24")]
    for ips in bench.benchmark.values():  # 任一分层零自报段成员
        for ip in ips:
            assert not any(ipaddress.ip_address(ip) in n for n in nets), ip
    # 段外成员存活;scanner 分层只余 sw 的段外两个(sr 零贡献)
    assert set(bench.benchmark["scanner"]) == {"198.51.100.7", "192.0.2.9"}
    assert set(bench.benchmark["exploit-traffic"]) == {"198.51.100.8"}


def test_build_benchmark_without_scanner_ranges_source_unchanged(tmp_path):
    # 回归臂:sources 无 scanner_ranges 源 → 行为与现状一致:段内 IP 照旧
    # 入语料(排除器只在自报段源在场时启动,ADR 0011 只接管在场源)
    raw = tmp_path / "sw.txt"
    raw.write_text("40.124.175.29\n198.51.100.7\n")
    src = _FakeSource("sw", raw, classification_type="scanner")
    bench = build_benchmark([src], per_type_n=10, rng=random.Random(0))
    assert set(bench.benchmark["scanner"]) == {"40.124.175.29", "198.51.100.7"}


def test_build_benchmark_scanner_ranges_missing_csv_noop(tmp_path):
    # 回归臂:CSV 缺失(源未下载)→ 源跳过 + 排除器不启动 = 现状
    # (sample_source_ips 对缺文件本就返 [];前缀只从在场 CSV 载入,
    # 不走 D1 的 raise 语义 —— loader 的 raise 是 truth 装配侧契约)
    sr = _FakeSource("scanner_ranges", tmp_path / "nope.csv",
                     classification_type="scanner")
    raw = tmp_path / "sw.txt"
    raw.write_text("40.124.175.29\n198.51.100.7\n")
    sw = _FakeSource("sw", raw, classification_type="scanner")
    bench = build_benchmark([sr, sw], per_type_n=10, rng=random.Random(0))
    assert set(bench.benchmark["scanner"]) == {"40.124.175.29", "198.51.100.7"}


def test_run_for_source_records_run_seed(tmp_path):
    # S36:报告 JSON 顶层 run_seed(缺省=secrets.randbits(64) 显式随机,
    # 不得回退源名派生)+ 采样指纹(被采键集 fingerprint,存 metrics 旁)
    from test_eval_cli import _FakeRegistry, _FakeBenign, _CAND_IPS
    from ipdb._eval.__main__ import run_for_source
    from ipdb._eval.assets import fingerprint

    def _run(out: Path):
        reg = _FakeRegistry()
        reg.sources[0]._path = out / "cand.txt"
        out.mkdir(exist_ok=True)
        reg.sources[0]._path.write_text("\n".join(_CAND_IPS) + "\n")
        return run_for_source("cand", registry=reg, corpus_path=out / "c.json",
                              out_dir=out, benign=_FakeBenign())

    _, js, _ = _run(tmp_path)
    rep = json.loads(Path(js).read_text())
    assert isinstance(rep["run_seed"], int)
    # CORPUS_CANDIDATE_N=100 > 可用 25 → 全集被采,指纹=文件全集指纹
    assert rep["sampling_fingerprint"] == fingerprint(_CAND_IPS)
    _, js2, _ = _run(tmp_path / "r2")
    assert json.loads(Path(js2).read_text())["run_seed"] != rep["run_seed"]  # 缺省显式随机
