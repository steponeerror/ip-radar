"""探测清单 ops/pipeline-core/feeds.txt 与源登记双向同步门(工单 #456)。

背景(2026-11-26):清单头写着「新增源 / 改源的下载端点 → 同 PR 更新本清单」,
但只靠人记——2026-11-20~22 合并的 7 个加源 PR 没有一个更新过它,71 个登记源
当时只有 52 个在清单。应用内「停更告警」量的是下载管道通不通,量不出上游内容
冻结(#455),运营健康轮这条探测是唯一在看上游冻结的东西,清单漏源 = 该源
上游冻结/失联永不被看见。(它能看出冻结的只有带 Last-Modified 的那些行——
2026-11-26 从生产服务器读响应头,120 行里 63 行带;GitHub 托管的 38 行全不带,
只判可达。清单头写明了这条局限,本测试只管「源在不在清单里」。)

三个方向各防一个:
- 登记 → 清单:加源后忘更新清单(本票的起因,7 个 PR 实证);
- 清单 → 登记:撤源后清单残留行(探测一个已不存在的源,读数永久噪音);
- 豁免表 → 登记:豁免条目是改名后的幽灵(源已改名或撤掉,豁免还在)。

清单口径 = lib.sh extract_feed_urls -t 同一解析(行内 # 后首词,截到首个
非 [a-z0-9_] 字符);两套解析由 test_python_parser_matches_libsh_awk 拿真
awk 对照钉住。豁免表 = 清单头散文「刻意不收录」名单的机读化
(2026-11-26 搬入,honyport 当时漏在散文外,补录缘由见条目)。

加源自动流程怎么过这道门(#456 评审 P1):轮内模型不写清单行(多端点源要人
选代表),所以加源轮的门跳过本文件;add-lift.mjs 在动任何文件之前先跑本文件
(新源不在清单也不在豁免表 = 停下,沙箱原样未动),清单行数变了再同步两处钉数;
人工开的 PR 由 CI 拦。
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from ipdb._registry import _sources

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _REPO_ROOT / "ops" / "pipeline-core" / "feeds.txt"

# 豁免表:已登记但刻意不进探测清单的源 → 缘由(清单头散文「刻意不收录」
# 名单的机读化;新增豁免须同 PR 在清单头分组注释里留一行指回本表)。
# 原则与清单头一致:只豁免「匿名 GET 探不到真数据端点」或「无网络抓取」
# 的源,不豁免任何有常驻数据 URL 的源。
EXEMPT: dict[str, str] = {
    # v2 exports 端点 Auth-Key 是路径段,匿名 404 必伪报不可达(票 #159);
    # 新鲜度由源健康 .last_updated 侧覆盖。
    "threatfox": "v2 exports 端点 Auth-Key 在路径段,匿名 404 伪报不可达(#159)",
    "urlhaus": "v2 exports 端点 Auth-Key 在路径段,匿名 404 伪报不可达(#159)",
    # 月度滚动文件名,无常驻端点。
    "dbip_city": "月度滚动 URL(dbip-city-lite-YYYY-MM.csv.gz),无常驻端点",
    # {token} 模板 URL,匿名不可探。
    "ip2proxy": "{token} 模板 URL,匿名不可探",
    "ipinfo_lite": "{token} 模板 URL,匿名不可探",
    # 内嵌 CSV,无网络抓取。
    "infra_services": "内嵌 CSV,无网络抓取",
    # 自建蜜罐聚合件:download() 走 docker bind mount 本地目录取件,
    # 无上游 URL(#253 url_exempt;ADR 0017)。清单头散文名单当时漏录,
    # 2026-11-26 机读化时补入(#456)。
    "honyport": "自建蜜罐,bind mount 本地取件无上游 URL(#253 url_exempt)",
    # cloud_ranges 微软段 confirmation.aspx 是下载确认页非数据,真实 download.microsoft.com
    # 链接运行时从页内解析,无常驻 URL——这是段级排除,不是豁免:源本身的四家云
    # (AWS/GCP/Oracle/Alibaba)在清单里,所以它不进本表;整源从清单消失时
    # 「登记→清单」检查会红(#456 评审 P2-1)。
}

# extract_feed_urls -t 同口径(lib.sh:263-269 的 awk,逐条对齐):
#   分隔正则「 *# *」只吃空格(制表符不吃);URL 列去首尾空白;
#   标源名 = # 后首段开头连续的 [a-z0-9_],再须满足 ^[a-z0-9_]{1,32}$,
#   否则记为 "-"(消费方回落 host)。
_NAME_HEAD_RE = re.compile(r"[a-z0-9_]*")


def _parse_line(line: str) -> tuple[str, str] | None:
    """一行清单 → (url, 源名或 "-");非数据行(URL 列为空)→ None。"""
    parts = re.split(r" *# *", line, maxsplit=1)
    url = parts[0].strip(" \t")
    if not url:
        return None
    raw = parts[1] if len(parts) > 1 else ""
    src = _NAME_HEAD_RE.match(raw).group(0) if raw else ""
    if not 1 <= len(src) <= 32:
        src = "-"
    return url, src


def _manifest_source_names() -> dict[str, list[int]]:
    """清单解析:源名 → 出现行号列表(报错指路用)。同 lib.sh 口径:
    跳过 ^# 注释行;URL 列(首个 # 前)非空的行才算条目。"""
    names: dict[str, list[int]] = {}
    for lineno, line in enumerate(_MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            continue
        parsed = _parse_line(line)
        if parsed is None:
            continue
        if parsed[1] != "-":
            names.setdefault(parsed[1], []).append(lineno)
    return names


def test_every_manifest_line_names_a_source() -> None:
    """清单每条数据行都必须解析出合法源名(#456 评审 P2-3):没有注解、注解
    首词异形、# 后是制表符的行,健康轮会回落按主机名记,登记↔清单的两个
    方向都看不见它——在这里就红。"""
    bad: dict[int, str] = {}
    for lineno, line in enumerate(_MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            continue
        parsed = _parse_line(line)
        if parsed is not None and parsed[1] == "-":
            bad[lineno] = line
    assert not bad, (
        f"探测清单 ops/pipeline-core/feeds.txt 这些行解析不出源名(健康轮会回落"
        f"按主机名记,同步门也看不见): {bad}。"
        f"补法:在行内 # 后写源名([a-z0-9_],1 到 32 个字符,# 与源名之间用空格)。"
    )


def _python_pairs(text: str) -> set[tuple[str, str]]:
    out = set()
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        parsed = _parse_line(line)
        if parsed is not None:
            out.add(parsed)
    return out


def _awk_pairs(text: str) -> set[tuple[str, str]]:
    """真解析函数:source lib.sh 后跑 extract_feed_urls -t(与生产同一段 awk)。"""
    lib = _REPO_ROOT / "ops" / "pipeline-core" / "lib.sh"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "feeds.txt"
        f.write_text(text, encoding="utf-8")
        r = subprocess.run(
            ["bash", "-c", '. "$1"; AGENT_DIR="$(dirname "$1")"; extract_feed_urls -t "$2"',
             "parity", str(lib), str(f)],
            capture_output=True, text=True, check=True, timeout=120)
    return {tuple(line.split("\t")) for line in r.stdout.splitlines() if line}


@pytest.mark.skipif(shutil.which("bash") is None, reason="需要 bash 跑 lib.sh")
def test_python_parser_matches_libsh_awk() -> None:
    """两套解析同口径的硬证据(#456 评审 P2-3):对真清单和一批刁钻行,
    Python 的 _parse_line 与 lib.sh 的 awk 输出逐对相同。以后任一侧改了
    口径,这里先红。"""
    tricky = "\n".join([
        "# 注释行 https://a/comment # ghost",
        "https://a/x # name",
        "https://a/y #\tname",            # # 后是制表符:awk 出 "-"
        "https://a/z",                      # 无注解
        "https://a/w # Cloud_Ranges",      # 首词异形
        "  https://a/v # ok   ",           # 首尾空白
        "https://a/u # name extra words",  # 多词注解取首词
        "https://a/t # " + "a" * 40,       # 超过 32 字符
        "https://a/s # " + "b" * 32,       # 恰 32 字符
        "",
        "https://a/d # name",               # 重复对(awk sort -u 去重)
    ])
    # 纯空白行("   ")故意不在比对里:lib.sh 的 awk 先判 $1 != "" 再去空白,会把
    # 这样一行输出成空 URL(既有小毛病,清单里现在没有这种行,由下面一条测试
    # 拦着不让它出现);Python 侧按正确行为跳过。两侧对这种行的处理不同,
    # 放进来只会让本测试永久红。
    for text in (_MANIFEST.read_text(encoding="utf-8"), tricky):
        assert _python_pairs(text) == _awk_pairs(text)


def test_manifest_has_no_whitespace_only_lines() -> None:
    """清单里不能有纯空白行:lib.sh 的 awk 会把它输出成一条空 URL(上游
    # 待修,见上);真出现时在这里红,并提醒顺手修 lib.sh。"""
    blank = {n: repr(l) for n, l in enumerate(
        _MANIFEST.read_text(encoding="utf-8").splitlines(), 1) if l and not l.strip()}
    assert not blank, f"探测清单里有纯空白行: {blank}。删掉即可。"


def test_registered_sources_in_manifest_or_exempt() -> None:
    """登记 → 清单:每个已登记源要么在清单,要么在豁免表(带缘由)。"""
    registered = {s.name for s in _sources}
    in_manifest = _manifest_source_names()
    missing = sorted(registered - set(in_manifest) - set(EXEMPT))
    assert not missing, (
        f"{len(missing)} 个已登记源不在探测清单 ops/pipeline-core/feeds.txt,"
        f"也不在豁免表: {missing}。"
        "补法:读该源 backend/ipdb/_sources/<名>.py 的 download(),把真实"
        "数据端点按 '<URL> # <source_name>' 写进 feeds.txt(匿名 GET 可达"
        "才收);确属探不了的(auth 路径段/{token} 模板/无网络抓取),"
        "在 test_feeds_manifest_sync.py 的 EXEMPT 表登记源名和缘由。"
    )


def test_exempt_entries_are_registered_sources() -> None:
    """豁免表条目必须指向真实存在的登记源(防改名后豁免失效成幽灵)。"""
    registered = {s.name for s in _sources}
    ghosts = sorted(set(EXEMPT) - registered)
    assert not ghosts, (
        f"豁免表里的源名不是已登记源: {ghosts}。"
        f"源若已改名/退役,同步更新 test_feeds_manifest_sync.py 的 EXEMPT 表。"
    )


def test_manifest_sources_are_registered() -> None:
    """清单 → 登记:清单里每个源名必须是已登记源(抓撤源后的残留行)。"""
    registered = {s.name for s in _sources}
    stale = {n: ls for n, ls in _manifest_source_names().items() if n not in registered}
    assert not stale, (
        f"探测清单 ops/pipeline-core/feeds.txt 里的源名不是已登记源"
        f"(撤源残留?): {stale}。"
        f"补法:源已退役就删掉对应行;是清单注解拼错就改行内 # 后的源名。"
    )
