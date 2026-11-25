"""探测清单 ops/pipeline-core/feeds.txt 与源登记双向同步门(工单 #456)。

背景(2026-11-26):清单头写着「新增源 / 改源的下载端点 → 同 PR 更新本清单」,
但只靠人记——2026-11-20~22 合并的 7 个加源 PR 没有一个更新过它,71 个登记源
当时只有 52 个在清单。应用内「停更告警」量的是下载管道通不通,量不出上游内容
冻结(#455),运营健康轮这条探测是唯一在看上游冻结的东西,清单漏源 = 该源
上游冻结/失联永不被看见。

两个方向各防一个:
- 登记 → 清单:加源后忘更新清单(本票的起因,7 个 PR 实证);
- 清单 → 登记:撤源后清单残留行(探测一个已不存在的源,读数永久噪音)。

清单口径 = lib.sh extract_feed_urls -t 同一解析(行内 # 后首词,截到首个
非 [a-z0-9_] 字符);豁免表 = 清单头散文「刻意不收录」名单的机读化
(2026-11-26 搬入,honyport 当时漏在散文外,补录缘由见条目)。
"""
import re
from pathlib import Path

from ipdb._registry import _sources

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _REPO_ROOT / "ops" / "pipeline-core" / "feeds.txt"

# 豁免表:已登记但刻意不进探测清单的源 → 缘由(清单头散文「刻意不收录」
# 名单的机读化;新增豁免须同 PR 在清单头分组注释里留一行指回本表)。
# 原则与清单头一致:只豁免「匿名 GET 探不到真数据端点」或「无网络抓取」
# 的源,不豁免任何有常驻数据 URL 的源。cloud_ranges 主体段(AWS/GCP/
# Oracle/Alibaba)在清单里,豁免只指微软段——在表内是记录性豁免,
# 不掩盖其在清单的事实(两方向检查照常管它)。
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
    # 微软段 confirmation.aspx 是下载确认页非数据,真实 download.microsoft.com
    # 链接运行时从页内解析,无常驻 URL;其余段照常在清单。
    "cloud_ranges": "仅微软段无常驻 URL(确认页+运行时解析),其余段在清单",
}

# extract_feed_urls -t 同口径:行内 # 注释首词,截到首个非 [a-z0-9_] 字符;
# 无注解/异形 → "-"(lib.sh:extract_feed_urls,awk sub 同形)。
_NAME_RE = re.compile(r"[a-z0-9_]{1,32}")


def _manifest_source_names() -> dict[str, list[int]]:
    """清单解析:源名 → 出现行号列表(报错指路用)。同 lib.sh 口径:
    跳过 ^# 注释行;URL 列(首个 # 前)非空的行才算条目。"""
    names: dict[str, list[int]] = {}
    for lineno, line in enumerate(_MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            continue
        url = re.split(r" *#", line, maxsplit=1)[0].strip()
        if not url:
            continue
        m = _NAME_RE.match(line.split("#", 1)[1].strip() if "#" in line else "")
        if m:
            names.setdefault(m.group(0), []).append(lineno)
    return names


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
