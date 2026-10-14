# backend/test_eval_corpus.py
import json, tempfile, os, random
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
