"""TweetFeed (Source subclass) — per-row hashtag classification + Principle.

Covers: non-IP rows filtered (noise), per-row classification via TWEETFEED_MAP,
multi-hashtag handling, empty/unmappable → other, tags split by space +
reporter preserved (Convention 1 + preserve-signal);#241 unknown-hashtag
聚合计数摘要(逐键 WARN 消失)。
"""
import logging
from collections import Counter
from pathlib import Path

from ipdb._sources.tweetfeed import TweetFeedSource, _classify_tag

SAMPLE = (
    "2025-07-31 00:00:11,urldna_bot,domain,bad.example.com,#phishing,https://x.com/1\n"
    "2025-07-31 00:10:31,catnap707,ip,172.67.166.60,#phishing,https://x.com/2\n"
    "2025-07-31 01:00:00,res1,ip,1.2.3.4,#C2 #CobaltStrike,https://x.com/3\n"
    "2025-07-31 02:00:00,res2,ip,5.6.7.8,,https://x.com/4\n"                  # empty tag
    "2025-07-31 03:00:00,res3,ip,9.10.11.12,#ransomware,https://x.com/5\n"    # unmappable
)


def test_tweetfeed_filters_nonip_and_classifies_per_row(tmp_path: Path):
    (tmp_path / "tweetfeed.csv").write_text(SAMPLE)
    s = TweetFeedSource(data_dir=tmp_path)
    assert s.rebuild() == 4                        # 4 IP rows; the domain row filtered as noise

    phish = s.query("172.67.166.60")[0]
    assert phish["classification_type"] == "phishing"
    assert phish["tags"] == ["#phishing"]                    # hashtags in tags slot
    assert "native_type" not in phish.get("extra", {})
    assert phish["extra"]["reporter"] == "catnap707"        # preserve-signal
    assert phish["extra"]["tweet_url"] == "https://x.com/2" # enriched: provenance
    assert phish["verdict"] == "malicious"

    c2 = s.query("1.2.3.4")[0]
    assert c2["classification_type"] == "c2-server"         # multi-hashtag, first mapped wins
    assert c2["tags"] == ["#C2", "#CobaltStrike"]         # space-split hashtag list
    assert "native_type" not in c2.get("extra", {})

    empty = s.query("5.6.7.8")[0]
    assert empty["classification_type"] == "other"          # empty tag → other

    unmap = s.query("9.10.11.12")[0]
    assert unmap["classification_type"] == "other"          # unmappable → other
    assert unmap["tags"] == ["#ransomware"]   # raw still preserved
    assert "native_type" not in unmap.get("extra", {})


def test_tweetfeed_botnet_family_tags_map_infected_system(tmp_path: Path):
    """#botnet/#mirai/#mozi → infected-system(IntelMQ 官方型;曾落方言
    botnet,P1 2026-09-05 迁移)。"""
    rows = (
        "2025-07-31 00:00:11,a,ip,1.2.3.4,#botnet,x\n"
        "2025-07-31 00:00:12,b,ip,5.6.7.8,#mirai,x\n"
        "2025-07-31 00:00:13,c,ip,9.10.11.12,#mozi,x\n"
    )
    (tmp_path / "tweetfeed.csv").write_text(rows)
    s = TweetFeedSource(data_dir=tmp_path)
    assert s.rebuild() == 3
    assert s.query("1.2.3.4")[0]["classification_type"] == "infected-system"
    assert s.query("5.6.7.8")[0]["classification_type"] == "infected-system"
    assert s.query("9.10.11.12")[0]["classification_type"] == "infected-system"


def test_tweetfeed_nonip_rows_filtered(tmp_path: Path):
    """domain/url/hash rows must not enter the IP DB (Principle: filter non-IP noise)."""
    (tmp_path / "tweetfeed.csv").write_text(
        "2025-07-31 00:00:11,a,domain,bad.example.com,#phishing,x\n"
        "2025-07-31 00:00:11,a,url,http://bad.example.com/x,#phishing,x\n"
        "2025-07-31 00:00:11,a,sha256,abc123,#phishing,x\n"
        "2025-07-31 00:00:11,a,ip,203.0.113.55,#phishing,x\n"
    )
    s = TweetFeedSource(data_dir=tmp_path)
    assert s.rebuild() == 1                        # only the IP row survives
    assert s.query("203.0.113.55")


def test_tweetfeed_tags_slot_split_by_space(tmp_path):
    header = "date,author,type,ioc,tags,link\n"
    row = ("2025-08-15 00:00:11,urldna_bot,ip,1.2.3.4,"
           "#scam #phishing,https://x.com/s/1\n")
    (tmp_path / "tweetfeed.csv").write_text(header + row)
    s = TweetFeedSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("1.2.3.4")[0]
    assert rec["tags"] == ["#scam", "#phishing"]
    assert "native_categories" not in rec      # 迁移后缺席


def test_tweetfeed_classify_tag_parity_with_normalize():
    """#241 分类位等价:_classify_tag 本地复制 normalize 的映射判定后,
    对同一输入必须产出同一分类(参照 = 改前逐 token 调 normalize 的旧
    循环;含 TWEETFEED_MAP 全键 + 空值/纯空白/大小写/前缀可映射截断
    等边角)。"""
    from ipdb._classification import TWEETFEED_MAP, normalize

    def _old_loop(raw):                      # 改前实现逐字镜像(#241 基线)
        for tag in (raw or "").split():
            ctype = normalize(tag, TWEETFEED_MAP)
            if ctype != "other":
                return ctype
        return "other"

    battery = [
        "#phishing", "#C2 #CobaltStrike", "#c2 #valleyrat", "#valleyrat #c2",
        "", "   ", None, "#ransomware", "#APT #Kimsuky", "#ValleyRAT",
        "#botnet #mirai", "#phishing #ransomware", "#C2",
    ]
    for raw in battery + list(TWEETFEED_MAP):
        assert _classify_tag(raw, Counter()) == _old_loop(raw), raw


def test_tweetfeed_unknown_hashtags_aggregate_into_one_summary(tmp_path, caplog):
    """#241 主体:重建期 unknown hashtag 不再逐键 WARN(normalize 绊线在
    tweetfeed 车道不被触发),解析结束一条聚合摘要 WARN(总命中数 +
    distinct + Top-N 同 tag 合并计数);首现逐 tag DEBUG 留痕;分类结果
    不变。"""
    rows = (
        "2025-07-31 00:00:00,a,ip,1.2.3.4,#valleyrat,https://x.com/1\n"
        "2025-07-31 00:01:00,b,ip,5.6.7.8,#valleyrat #winos,https://x.com/2\n"
        "2025-07-31 00:02:00,c,ip,9.10.11.12,#phishing,https://x.com/3\n"
        "2025-07-31 00:03:00,d,ip,203.0.113.9,#c2 #valleyrat,https://x.com/4\n"
    )
    (tmp_path / "tweetfeed.csv").write_text(rows)
    s = TweetFeedSource(data_dir=tmp_path)
    with caplog.at_level(logging.DEBUG, logger="ipdb"):
        assert s.rebuild() == 4
    # 逐键绊线静默:tweetfeed 解析路径不再产出任何 unmapped WARN
    assert not [r for r in caplog.records
                if r.levelno >= logging.WARNING
                and "unmapped native value" in r.getMessage()]
    warns = [r for r in caplog.records
             if r.levelno == logging.WARNING
             and r.name == "ipdb._sources.tweetfeed"]
    assert len(warns) == 1
    msg = warns[0].getMessage()
    # 总命中 = valleyrat 2 + winos 1 = 3(#c2 行的 valleyrat 在首个可映射
    # tag 之后不被扫描,不计入);distinct = 2;同 tag 跨行合并计数。
    assert "3 unmapped-hashtag hit(s)" in msg
    assert "2 distinct tag(s)" in msg
    assert "#valleyrat=2" in msg
    assert "#winos=1" in msg
    # 首现 DEBUG 留痕:每 distinct tag 恰一条(哲学 1,信息不灭失)
    dbg = [r for r in caplog.records
           if r.levelno == logging.DEBUG
           and r.name == "ipdb._sources.tweetfeed"]
    assert len(dbg) == 2
    # 分类结果不变:unknown 行落 other;首个可映射前缀行落映射型
    assert s.query("1.2.3.4")[0]["classification_type"] == "other"
    assert s.query("5.6.7.8")[0]["classification_type"] == "other"
    assert s.query("203.0.113.9")[0]["classification_type"] == "c2-server"


def test_tweetfeed_unknown_summary_topn_cap_and_ordering(tmp_path, caplog):
    """#241:distinct > Top-N(10)时摘要只列前 10,按计数降序;总数照发。"""
    lines = []
    for i in range(12):                     # t00×12 … t11×1,名次 = i
        lines.extend(
            f"2025-07-31 00:00:00,r,ip,10.{i}.{j}.1,#t{i:02d},x\n"
            for j in range(12 - i))         # 每行独立 IP:rebuild 返回键数=行数
    (tmp_path / "tweetfeed.csv").write_text("".join(lines))
    s = TweetFeedSource(data_dir=tmp_path)
    with caplog.at_level(logging.WARNING, logger="ipdb._sources.tweetfeed"):
        assert s.rebuild() == 78             # 12+11+…+1
    warns = [r for r in caplog.records if r.name == "ipdb._sources.tweetfeed"]
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "78 unmapped-hashtag hit(s)" in msg
    assert "12 distinct tag(s)" in msg
    assert "top 10" in msg
    assert "#t00=12" in msg and "#t09=3" in msg
    assert "#t10=" not in msg and "#t11=" not in msg   # 截断在 N=10
    assert msg.index("#t00=12") < msg.index("#t01=11") < msg.index("#t09=3")


def test_tweetfeed_no_unknown_tags_means_no_summary(tmp_path, caplog):
    """#241:全可映射语料零 unknown → 摘要也不发(零噪音)。"""
    rows = (
        "2025-07-31 00:00:00,a,ip,1.2.3.4,#phishing,x\n"
        "2025-07-31 00:01:00,b,ip,5.6.7.8,#c2 #cobaltstrike,x\n"
    )
    (tmp_path / "tweetfeed.csv").write_text(rows)
    s = TweetFeedSource(data_dir=tmp_path)
    with caplog.at_level(logging.WARNING, logger="ipdb._sources.tweetfeed"):
        assert s.rebuild() == 2
    assert not [r for r in caplog.records
                if r.name == "ipdb._sources.tweetfeed"]
