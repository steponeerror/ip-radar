"""fail2ban action 配置的内嵌 python 片段契约(#521 出海数字统一)。

scripts/fail2ban/ipradar.conf 的 actionban 里有一段 `python3 -c '…'` 单行
片段(见配置注释:fail2ban 把 shell 续行拼成一行,# 注释会吞掉行尾,故
片段内不许写注释)。#521 裁决(2026-11-28):MAL 判定读顶层融合值
d["threat"]["confidence"] 与 d["threat"]["verdict"] —— 与网页 / CSV /
黑名单导出同一个数;不再自算「恶意分类组最大值」(旧口径多类别佐证
不计入,数字系统性偏低)。

本测试把配置里的片段抽出来用子进程真跑(不 mock、不重写),喂样例
payload 钉住:①读的是 threat.confidence(组最大值更大的样例下,输出数
字 = 融合值);②MAL 需 verdict==malicious 且达到阈值;③CDN/服务边缘
分支原样保留;④输出形状 MAL/OK/CDN + 数字不变。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CONF = REPO / "scripts" / "fail2ban" / "ipradar.conf"

# 片段定位:actionban 里 `python3 -c '…' <ipradar_threshold>`,单引号内
# 即片段(配置里该单引号只出现这一对;变了就响亮失败,不静默抽错)。
_SNIPPET_RE = re.compile(r"python3 -c '([^']*)' <ipradar_threshold>")


def _snippet() -> str:
    text = CONF.read_text(encoding="utf-8")
    m = _SNIPPET_RE.search(text)
    assert m, f"{CONF} 里找不到 python3 -c '…' <ipradar_threshold> 片段"
    return m.group(1)


def _run(payload: dict, threshold: int = 70) -> str:
    r = subprocess.run(
        [sys.executable, "-c", _snippet(), str(threshold)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _payload(threat_conf, threat_verdict, groups=None, attrs=None):
    return {
        "threat": {"verdict": threat_verdict, "confidence": threat_conf,
                   "types": [], "is_cdn": False,
                   "first_hand_source_count": 1},
        "classifications": groups or {},
        "attributes": attrs or {},
    }


def test_mal_reads_fused_confidence_not_group_max():
    """钉「读的是 threat.confidence」:组最大值 99 高于融合值 85 —— 输出
    数字必须取融合值。若有人改回「恶意分类组最大值」(变异),本用例红。"""
    groups = {"scanner": {"type": "scanner", "verdict": "malicious",
                          "detected": True, "confidence": 99}}
    out = _run(_payload(85, "malicious", groups=groups))
    assert out == "MAL 85"


def test_mal_requires_malicious_verdict_and_threshold():
    """verdict 非 malicious → OK(哪怕置信度高);verdict malicious 但低于
    阈值 → OK。判定与门限双条件。"""
    assert _run(_payload(95, "suspicious")).startswith("OK ")
    assert _run(_payload(69, "malicious")) == "OK 69"
    assert _run(_payload(70, "malicious")) == "MAL 70"
    assert _run(_payload(85, "malicious"), threshold=80) == "MAL 85"


def test_cdn_and_service_edge_branch_unchanged():
    """CDN / 服务边缘先于 MAL/OK 判定(原样行为,#521 不动这一段)。
    片段只认字符串「cdn」(原样口径;bool True 不触发是现存行为,本测试
    钉现状,不顺手改)。"""
    cdn = _payload(99, "malicious", attrs={
        "is_cdn": [{"source": "ipinfo_lite", "value": "cdn", "native_type": None}]})
    assert _run(cdn).startswith("CDN ")
    svc = _payload(99, "malicious", attrs={
        "service": [{"source": "ip2location", "value": "dns", "native_type": "DNS"}]})
    assert _run(svc).startswith("CDN ")
