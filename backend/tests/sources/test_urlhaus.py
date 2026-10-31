"""URLhaus (Source subclass) — URL→IP extraction + per-row classification + Principle.

Covers: domain-host rows dropped (noise), IP-host extraction, infected-system
mapping (mirai/Mozi/hajime = infected drone hosts), malware-distribution base
for the rest, native_type + reporter + url_status preserved (Convention 1 +
preserve-signal), comment block skipped.
"""
from pathlib import Path

import pytest

from ipdb._sources.urlhaus import URLhausSource

SAMPLE = (
    "##### urlhaus header #####\n"
    "# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n"
    '"1","2026-07-30 11:54:23","http://61.54.253.89:37352/bin.sh","online","2026-07-30 11:54:23","malware_download","32-bit,elf,mips,Mozi","x","geenensp"\n'
    '"2","2026-07-30 11:54:23","http://1.2.3.4/x","online","2026-07-30 11:54:23","malware_download","CoinMiner","x","rep"\n'
    '"3","2026-07-30 11:54:23","http://bad.example.com/x","online","2026-07-30 11:54:23","malware_download","mirai","x","rep"\n'
    '"4","2026-07-30 11:54:23","http://5.6.7.8/y","online","2026-07-30 11:54:23","malware_download","None","x","rep"\n'
    '"5","2026-07-30 11:54:23","http://9.10.11.12/z","online","2026-07-30 11:54:23","malware_download","elf,hajime","x","rep"\n'
)


def test_urlhaus_drops_domain_hosts_and_classifies(tmp_path: Path):
    (tmp_path / "urlhaus.csv").write_text(SAMPLE)
    s = URLhausSource(data_dir=tmp_path)
    assert s.rebuild() == 4                    # rows 1,2,4,5 (IP-host); row 3 domain dropped

    bot = s.query("61.54.253.89")[0]        # Mozi tag
    assert bot["classification_type"] == "infected-system"
    assert bot.get("tags", []) == []   # Mozi 命中进 malware_name，噪音被滤
    assert bot["extra"]["reporter"] == "geenensp"
    assert bot["malware_name"] == "Mozi"                          # enriched: matched family
    assert bot.get("last_seen") == "2026-07-30T11:54:23"          # enriched: last_online recency

    hajime = s.query("9.10.11.12")[0]       # hajime tag
    assert hajime["classification_type"] == "infected-system"

    miner = s.query("1.2.3.4")[0]           # CoinMiner → base
    assert miner["classification_type"] == "malware-distribution"
    assert miner["tags"] == ["CoinMiner"]

    none_tags = s.query("5.6.7.8")[0]       # "None" tags → base
    assert none_tags["classification_type"] == "malware-distribution"
    assert none_tags["extra"]["url_status"] == "online"            # recency signal preserved


def test_urlhaus_domain_rows_not_in_db(tmp_path: Path):
    """A domain-host URL must not contribute its (non-IP) host — IP tool."""
    (tmp_path / "urlhaus.csv").write_text(
        '# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n'
        '"1","2026-07-30","http://bad.example.com/x","online","2026-07-30","malware_download","mirai","x","r"\n'
        '"2","2026-07-30","http://203.0.113.7/x","online","2026-07-30","malware_download","mirai","x","r"\n'
    )
    s = URLhausSource(data_dir=tmp_path)
    assert s.rebuild() == 1                    # only the IP-host row survives
    assert s.query("203.0.113.7")


def test_urlhaus_native_categories_filters_noise_and_excludes_matched_family(tmp_path: Path):
    """Native categories: split tags, filter arch noise, exclude matched family."""
    (tmp_path / "urlhaus.csv").write_text(
        '# "dateadded","url","url_status","last_online","threat","tags","urlhaus_link","reporter"\n'
        '"1","2026-08-01","http://1.2.3.4/x","online","2026-08-05","malware_download","32-bit,elf,mips,Mozi","u1","r1"\n'
        '"2","2026-08-01","http://5.6.7.8/y","online","2026-08-05","malware_download","mirai,TrickBot","u2","r2"\n'
        '"3","2026-08-01","http://9.10.11.12/z","online","2026-08-05","malware_download","","u3","r3"\n'
    )
    s = URLhausSource(data_dir=tmp_path)
    s.rebuild()

    # Row 1: Mozi matched, noise filtered, threat in native_categories
    one = {e["classification_type"]: e for e in s.query("1.2.3.4")}
    assert one["infected-system"]["malware_name"] == "Mozi"
    assert one["infected-system"].get("native_categories", []) == ["malware_download"]  # threat column value
    assert one["infected-system"].get("tags", []) == []  # Mozi 命中被排除进 malware_name，噪音被滤
    assert "native_type" not in (one["infected-system"].get("extra") or {})

    # Row 2: mirai matched, TrickBot preserved in tags
    two = {e["classification_type"]: e for e in s.query("5.6.7.8")}
    assert two["infected-system"]["malware_name"] == "mirai"
    assert two["infected-system"]["tags"] == ["TrickBot"]  # other family preserved in tags
    assert two["infected-system"]["native_categories"] == ["malware_download"]  # threat column value

    # Row 3: empty tags → empty tags, threat in native_categories
    three = {e["classification_type"]: e for e in s.query("9.10.11.12")}
    assert three["malware-distribution"].get("tags", []) == []   # empty tags → empty
    assert three["malware-distribution"].get("native_categories", []) == ["malware_download"]  # threat column value
    assert three["malware-distribution"].get("malware_name") in (None, "")


def test_urlhaus_threat_column_drives_classification(tmp_path):
    """threat=credential_phishing → phishing，优先于 tags。"""
    (tmp_path / "urlhaus.csv").write_text(
        '# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n'
        '"1","2026-08-01","http://1.2.3.4/x","online","2026-08-05","credential_phishing","Pikabot","u","r"\n'
    )
    s = URLhausSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("1.2.3.4")[0]
    assert rec["classification_type"] == "phishing"
    assert rec["native_categories"] == ["credential_phishing"]   # raw 威胁原值
    assert rec["tags"] == ["Pikabot"]                            # 未命中家族 → tags 槽
    assert "tags_raw" not in rec.get("extra", {})                # 冗余 raw 串已删


def test_urlhaus_threat_unmappable_falls_back_to_tags(tmp_path):
    """threat=malware_download 无可映射值 → tags 兜底（Mozi → infected-system）。"""
    (tmp_path / "urlhaus.csv").write_text(
        '# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n'
        '"1","2026-08-01","http://1.2.3.4/x","online","2026-08-05","malware_download","Mozi","u","r"\n'
        '"2","2026-08-01","http://5.6.7.8/y","online","2026-08-05","malware_download","None","u","r"\n'
    )
    s = URLhausSource(data_dir=tmp_path)
    s.rebuild()
    one = s.query("1.2.3.4")[0]
    assert one["classification_type"] == "infected-system"
    assert one["malware_name"] == "Mozi"
    assert one["native_categories"] == ["malware_download"]
    two = s.query("5.6.7.8")[0]
    assert two["classification_type"] == "malware-distribution"  # tags 也无可映射 → 本底
    assert two["native_categories"] == ["malware_download"]


def test_urlhaus_stores_case_link(tmp_path):
    """row[7] urlhaus_link 列 → extra.urlhaus_link 溯源链接。"""
    (tmp_path / "urlhaus.csv").write_text(
        '# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n'
        '"1","2026-08-01","http://1.2.3.4/x","online","2026-08-05","malware_download","None",'
        '"https://urlhaus.abuse.ch/url/3907816/","rep"\n'
    )
    s = URLhausSource(data_dir=tmp_path)
    s.rebuild()
    rec = s.query("1.2.3.4")[0]
    assert rec["extra"]["urlhaus_link"] == "https://urlhaus.abuse.ch/url/3907816/"
    assert rec["extra"]["reporter"] == "rep"          # 既有键不受影响


# ── v2 认证端点迁移(票 #159,2026-10-23)──────────────────────────────
# 旧匿名出口 https://urlhaus.abuse.ch/downloads/csv_online/ 2026-10-22 起 410;
# 迁 https://urlhaus-api.abuse.ch/v2/files/exports/<KEY>/online.csv(online =
# 旧 csv_online 语义,active only),Auth-Key 在 URL 路径段 → secret 打码。

_KEY = "TESTKEY123"
_KEYED_URL = f"https://urlhaus-api.abuse.ch/v2/files/exports/{_KEY}/online.csv"


def _fake_urlopen(body: bytes, seen: list, *, final_url: str | None = None,
                  content_length: int | None = None):
    """urlopen 替身:seen 收集每次请求的 full_url;final_url ≠ None 模拟
    重定向落点;content_length > len(body) 模拟传输层截断。"""

    class _Resp:
        def __init__(self):
            self._pos = 0
            self.headers = (
                {"Content-Length": str(content_length)} if content_length else {})

        def geturl(self):
            return final_url or seen[-1]

        def read(self, n=-1):
            if n is None or n < 0:
                n = len(body)
            data = body[self._pos:self._pos + n]
            self._pos += len(data)
            return data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=120):
        seen.append(req.full_url)
        return _Resp()

    return fake


class TestURLhausAuthExport:
    def test_download_requires_auth_key(self, tmp_path: Path, monkeypatch):
        """缺 ABUSECH_AUTH_KEY → download() 报 RuntimeError 明文(票 #159:
        __init__ 缺省空串,不炸 import/构建;下载时才拦)。"""
        monkeypatch.delenv("ABUSECH_AUTH_KEY", raising=False)
        s = URLhausSource(data_dir=tmp_path)
        with pytest.raises(RuntimeError, match="ABUSECH_AUTH_KEY"):
            s.download()

    def test_download_uses_keyed_url_and_installs_csv(self, tmp_path: Path, monkeypatch):
        """keyed URL 只在 download() 内拼;url class attr 保持无 key 占位;
        下载体经守卫后原子落地 urlhaus.csv,scratch 清理。"""
        monkeypatch.setenv("ABUSECH_AUTH_KEY", _KEY)
        seen: list[str] = []
        monkeypatch.setattr(
            "urllib.request.urlopen", _fake_urlopen(SAMPLE.encode(), seen))
        s = URLhausSource(data_dir=tmp_path)
        s.download()
        assert seen == [_KEYED_URL]
        assert s.url == "https://urlhaus-api.abuse.ch/v2/files/exports/online.csv"
        assert _KEY not in s.url
        assert (tmp_path / "urlhaus.csv").read_text() == SAMPLE
        assert not (tmp_path / "urlhaus.csv.dl").exists()

    def test_download_rejects_200_ok_bad_body_keeps_old_evidence(self, tmp_path: Path, monkeypatch):
        """200-OK-坏体守卫(Phase 3 step 8 惯例):v2 错误页也是 200;既非 #
        注释块亦无 id,dateadded 列头 → RuntimeError,旧证据不灭失。"""
        monkeypatch.setenv("ABUSECH_AUTH_KEY", _KEY)
        old = b"# previous-good-evidence\n"
        (tmp_path / "urlhaus.csv").write_bytes(old)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _fake_urlopen(b"<html>login required</html>", []))
        s = URLhausSource(data_dir=tmp_path)
        with pytest.raises(RuntimeError, match="urlhaus payload"):
            s.download()
        assert (tmp_path / "urlhaus.csv").read_bytes() == old
        assert not (tmp_path / "urlhaus.csv.dl").exists()

    def test_download_redirect_warning_masks_key(self, tmp_path: Path, monkeypatch, caplog):
        """重定向绊线警告串里 keyed URL 打码:key 不入日志,*** 代位
        (票 #159 P0);正常体仍照常落地。"""
        import logging as _logging
        monkeypatch.setenv("ABUSECH_AUTH_KEY", _KEY)
        monkeypatch.setattr(
            "urllib.request.urlopen",
            _fake_urlopen(SAMPLE.encode(), [],
                          final_url=f"https://mirror.example/dl/{_KEY}/online.csv"))
        s = URLhausSource(data_dir=tmp_path)
        with caplog.at_level(_logging.WARNING, logger="ipdb._sources._download"):
            s.download()
        hits = [r for r in caplog.records if "redirected" in r.message]
        assert len(hits) == 1
        msg = hits[0].getMessage()
        assert _KEY not in msg
        assert "***" in msg
        assert (tmp_path / "urlhaus.csv").read_text() == SAMPLE


# ── #254 未映射键聚合计数(接 #241 tweetfeed 模式,经共享 normalize_counted/
# unmapped_summary 下沉;分类返回值位等价,详见镜像测试)──────────


def _row(rid: int, ip: str, threat: str, tags: str) -> str:
    return (f'"{rid}","2026-08-01","http://{ip}/p","online",'
            f'"2026-08-05","{threat}","{tags}","u","r"\n')


def test_urlhaus_unknown_keys_aggregate_into_one_summary(tmp_path, caplog):
    """#254 主体:重建期未映射键(tags token + 无可映射 threat 值)不再
    逐键 WARN(normalize 绊线在 urlhaus 车道不被触发),解析结束一条聚合
    摘要 WARN(总命中 + distinct + Top-N 同键合并计数);首现 DEBUG 留痕;
    分类结果不变。计数集 = 旧绊线触发集:malware_download 这类设计内
    兜底值旧实现本就 WARN(每行一次),新实现照计不丢观测面。"""
    import logging
    (tmp_path / "urlhaus.csv").write_text(
        "# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n"
        + _row(1, "1.2.3.4", "malware_download", "32-bit,elf,Mozi")   # 32-bit/elf 计,Mozi 映射截断
        + _row(2, "5.6.7.8", "malware_download", "CoinMiner")          # CoinMiner + threat 计
        + _row(3, "9.10.11.12", "credential_phishing", "mirai")       # 全可映射,零计数
        + _row(4, "203.0.113.9", "", ""))                            # 空键不计
    s = URLhausSource(data_dir=tmp_path)
    with caplog.at_level(logging.DEBUG, logger="ipdb"):
        assert s.rebuild() == 4
    # 逐键绊线静默:urlhaus 解析路径不再产出任何 unmapped WARN
    assert not [r for r in caplog.records
                if r.levelno >= logging.WARNING
                and "unmapped native value" in r.getMessage()]
    warns = [r for r in caplog.records
             if r.levelno == logging.WARNING
             and r.name == "ipdb._sources.urlhaus"]
    assert len(warns) == 1
    msg = warns[0].getMessage()
    # 总命中 = 32-bit 1 + elf 1 + coinminer 1 + malware_download 2(两行
    # threat 同键合并)= 5;distinct = 4。
    assert "5 unmapped-tag hit(s)" in msg
    assert "4 distinct tag(s)" in msg
    assert "malware_download=2" in msg
    # 首现 DEBUG 留痕:每 distinct 键恰一条(哲学 1,信息不灭失)
    dbg = [r for r in caplog.records
           if r.levelno == logging.DEBUG
           and r.name == "ipdb._sources.urlhaus"]
    assert len(dbg) == 4
    # 分类结果不变(位等价的行为面)
    assert s.query("1.2.3.4")[0]["classification_type"] == "infected-system"
    assert s.query("5.6.7.8")[0]["classification_type"] == "malware-distribution"
    assert s.query("9.10.11.12")[0]["classification_type"] == "phishing"
    assert s.query("203.0.113.9")[0]["classification_type"] == "malware-distribution"


def test_urlhaus_unknown_summary_topn_cap_and_ordering(tmp_path, caplog):
    """#254:distinct > Top-N(10)时摘要只列前 10,按计数降序;总数照发。"""
    import logging
    lines = ["# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n"]
    n = 0
    for i in range(12):                     # fam00×12 … fam11×1,名次 = i
        for j in range(12 - i):
            n += 1
            lines.append(_row(n, f"10.{i}.{j}.1", "", f"fam{i:02d}"))
    (tmp_path / "urlhaus.csv").write_text("".join(lines))
    s = URLhausSource(data_dir=tmp_path)
    with caplog.at_level(logging.WARNING, logger="ipdb._sources.urlhaus"):
        assert s.rebuild() == 78             # 12+11+…+1
    warns = [r for r in caplog.records if r.name == "ipdb._sources.urlhaus"]
    assert len(warns) == 1
    msg = warns[0].getMessage()
    assert "78 unmapped-tag hit(s)" in msg
    assert "12 distinct tag(s)" in msg
    assert "top 10" in msg
    assert "fam00=12" in msg and "fam09=3" in msg
    assert "fam10=" not in msg and "fam11=" not in msg   # 截断在 N=10
    assert msg.index("fam00=12") < msg.index("fam01=11") < msg.index("fam09=3")


def test_urlhaus_no_unknown_keys_means_no_summary(tmp_path, caplog):
    """#254:全可映射语料(tags+threat 双路)零未映射 → 摘要也不发。"""
    import logging
    (tmp_path / "urlhaus.csv").write_text(
        "# id,dateadded,url,url_status,last_online,threat,tags,urlhaus_link,reporter\n"
        + _row(1, "1.2.3.4", "credential_phishing", "mirai")
        + _row(2, "5.6.7.8", "credential_phishing", "hajime")
    )
    s = URLhausSource(data_dir=tmp_path)
    with caplog.at_level(logging.WARNING, logger="ipdb._sources.urlhaus"):
        assert s.rebuild() == 2
    assert not [r for r in caplog.records
                if r.name == "ipdb._sources.urlhaus"]


def test_urlhaus_classify_parity_with_normalize():
    """#254 分类位等价:_classify 走共享 normalize_counted 后,对同一输入
    必须产出与旧「逐 token 调 normalize()」实现一致的 (ctype, tok)
    (含 URLHAUS_MAP 全键 + 空值/none/大小写/前后缀未映射 token/逗号
    空档等边角;malware_name 保留原大写)。"""
    from collections import Counter
    from ipdb._classification import URLHAUS_MAP, normalize
    from ipdb._sources.urlhaus import _classify

    def _old_classify(tags_raw):             # 改前实现逐字镜像(#254 基线)
        for tag in (tags_raw or "").split(","):
            tok = tag.strip()
            key = tok.lower()
            if not key or key == "none":
                continue
            ctype = normalize(key, URLHAUS_MAP)
            if ctype != "other":
                return ctype, tok
        return "malware-distribution", None

    battery = [
        "", "   ", None, "mirai", "Mozi", "HAJIME", "32-bit,elf,mips,Mozi",
        "None", "none,NONE", "mirai,TrickBot", " UnknownFam ", "elf,hajime",
        ",,", " Mozi ", "CoinMiner", "telekopye,phishing-view",
    ]
    for raw in battery + [",".join(URLHAUS_MAP)]:
        assert _classify(raw, Counter()) == _old_classify(raw), raw
