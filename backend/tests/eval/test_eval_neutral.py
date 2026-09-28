# backend/tests/eval/test_eval_neutral.py
"""W0 中性层(层2):generate_neutral 纯函数 + neutral_ips.json 静态资产
+ Corpus.neutral 字段(旧 corpus.json 缺键 load 兼容)。"""
import ipaddress
import json
from pathlib import Path

from ipdb._eval.corpus import Corpus, generate_neutral

# 包内静态资产(与 corpus.json 同目录)
_NEUTRAL_ASSET = Path(__file__).resolve().parents[2] / "ipdb" / "_eval" / "neutral_ips.json"


def test_generate_neutral_pure_public_unicast():
    a = generate_neutral(600, 20260928)
    b = generate_neutral(600, 20260928)
    assert len(a) == 600 and len(set(a)) == 600
    assert a == b                       # seed 确定性:两次调用逐项相同
    for ip in a:
        addr = ipaddress.ip_address(ip)
        assert addr.is_global and not addr.is_multicast


def test_corpus_load_with_neutral_field():
    # 资产可加载、恰好 600 条
    data = json.loads(_NEUTRAL_ASSET.read_text())
    assert len(data) == 600
    # all_ips 含 neutral 成员,顺序:candidate + benign + reserved + neutral + benchmark
    c = Corpus(benchmark={"t": ["9.9.9.9"]}, reserved=["7.7.7.7"], neutral=["8.8.8.8"])
    assert c.all_ips() == ["7.7.7.7", "8.8.8.8", "9.9.9.9"]


def test_load_legacy_corpus_without_neutral_key(tmp_path):
    # 旧 corpus.json 无 neutral 键:load 走 dataclass 默认值,不炸
    p = tmp_path / "corpus.json"
    p.write_text(json.dumps(
        {"benchmark": {}, "benign": [], "reserved": [], "candidate_ips": []}))
    c = Corpus.load(p)
    assert c.neutral == []
