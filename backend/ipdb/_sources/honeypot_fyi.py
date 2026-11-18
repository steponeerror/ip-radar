"""Honeypot.fyi attacker blocklist — Source subclass (streaming rebuild).

honeypot.fyi 运营的多协议蜜罐舰队攻击真值块表(滚动 2024-01-01–Present,
每日刷新)。两列 ``ip, 命中数``(逗号后一空格);2026-11-18 实抓全量
14,086,191 字节 / 807,843 行 census:无表头、无 IPv6、无重复行、零畸形行,
计数域 1–1,603,125(首行即 127.0.0.1 环路自命中,尾行计数=1)。站点自述
累计 ~789K 独立攻击 IP。

URL 勘误(实数据自查改档案,票 #360 允许):dossier 原记
/blocklist.csv,2026-11-18 实测 404;真路径 = 主页 #blocklist 段链接的
/data/blocklist.csv(同日 200 OK,14,086,191 字节)。日日志
/data/YYYY-MM-DD.csv(时间戳+检测类型)刻意不取——与块表同源,双取双计
违「宁少算」。

与 honyport.py(本仓自建蜜罐,ADR 0017 评估面恒禁)无关,两个源两个
数据面,勿混。

许可:无正式许可证(公开发布;about 页联系)——收录依 NEEDS 2026-11-18
用户「都进」裁决立项(issue #360;dossier = researcher dc0a9985,
2026-11-17 实测 last-modified 当日 00:02 GMT)。

蜜罐族对照:siberkapan(r=0.60)/knock_knock(r=0.70,方法论代码公开
= 可审计溢价)。本源方法学页在但检测代码不公开 → siberkapan 档 0.60。
S33 蜜罐旗标(honeypot_methodology)照 siberkapan 先例不声明——那是
eval k_nonhoneypot 语义面,另行裁决,不在本票。

A 系流式(评审 P1-2,2026-11-18):CsvSource 物化 rebuild 路径全量实测
807,843 行峰值 RSS 550MB(19.0s),超 stopforumspam 流式化先例(-246MB
Python 堆,964MB 生产小机)所防的预算面还日更。转 Source+harvest 逐行
yield + single_evidence=True(malicious_ip/stopforumspam 同款):改后同机
全量实测峰值 RSS 192MB(33.3s;-358MB/−65%,耗时升 = 基类 factory 双遍
族分区,既有 CPU 换内存纪律)。census 实测重复键=0(807,843 行恰
807,843 唯一键)→ 流式无损;若 feed 未来出现重复行,insert_network
幂等覆写,不炸但须复查此声明。
"""
import csv
import ipaddress as _ipa
import io
import logging

from .._evidence import Evidence
from .._source_base import Source

logger = logging.getLogger(__name__)


class HoneypotFyiSource(Source):
    name = "honeypot_fyi"
    category = "threat"
    url = "https://honeypot.fyi/data/blocklist.csv"  # 档案 /blocklist.csv 已 404(2026-11-18),见 docstring
    filename = "honeypot_fyi.csv"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 1                       # 日更(researcher 2026-11-17: last-modified 当日 00:02 GMT)
    reliability = 0.60                   # sensor-sourced 蜜罐舰队(siberkapan 同档;无 knock_knock 式公开检测代码)
    authoritative_for = ()               # corroboration only(SM-F1)
    provenance_tier = "A"                # A=官方一手(S21):honeypot.fyi 运营方自有舰队直接发布
    infra_noise_filter = True            # 2026-11-18 全量实测:curated 56 员集∩块表 = 1.0.0.1/1.1.1.1/208.67.222.222/8.8.8.8/9.9.9.9 五址(ADR 0008 事故形)→ 载入期 curated 单址排除(harvest 车道,Source.rebuild 中央接线);全量回算 807,843−5=807,838 对账闭合
    # 流式 rebuild(评审 P1-2):census 重复键=0 → single_evidence 无损
    # (-358MB 峰值 RSS,550→192MB 实测见 docstring;stopforumspam 同款
    # 声明纪律)。基类 factory 被调两次(v4/v6 族分区),harvest 重复
    # 解析是既有模式(CPU 换内存)。
    single_evidence = True

    def harvest(self):
        """逐行 yield ``(ip, Evidence)``。行形 ``<ip>, <hits>``(逗号后
        一空格,实测全量零例外)。

        两列定形:计数列缺席/非整数、IP 不可解析 → 整行跳过(宁少算,
        不猜)。hits = 该 IP 对舰队的攻击命中数,照 ipsum/stopforumspam
        先例进 reporter_count(观测计数槽,非置信度——置信度语义留给
        融合层)。Evidence 三槽与旧 CsvSource parse_row 产物逐键一致
        (字节级一致纪律:to_dict 不含 reliability 等未置槽)。
        """
        with open(self._path, "r", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 2:
                    continue
                try:
                    hits = int(row[1].strip())
                except ValueError:
                    continue
                ip = row[0].strip()
                try:
                    _ipa.ip_address(ip)
                except ValueError:
                    continue
                yield ip, Evidence(
                    classification_type=self.classification_type,
                    verdict=self.verdict,
                    reporter_count=hits)

    def download(self, token=None) -> None:
        """A 系下载契约 = 原始字节直写 _path;scratch 落盘 + 200-OK
        空载/错页守卫(abuseipdb 先例,票 #360)。

        download_file 自身对非 200/截断已抛错,但它把 dest 当提交点——
        故先落 scratch;空体或零有效 ``ip, hits`` 行(Cloudflare 200
        错误页形)在提交前拒绝,既有数据文件字节不动(证据永不灭失,
        旧「失败删好文件」P1 回归 2026-09-28 不复发)。活性探针 = 扫到
        首个两列可解析且 IP 合法的行即收;全量校验是 rebuild 的事,
        守卫只证 payload 是本 feed 而非错误页。
        """
        import os as _os
        from ._download import download_file, redact_url
        self._data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Downloading {self.name}...")
        scratch = self._path.with_name(self._path.name + ".dl")
        try:
            download_file(self.url, scratch, token=token,
                          headers={"User-Agent": "ip-lookup-tool/1.0"})
            raw = scratch.read_bytes()
            if not raw.strip():
                raise RuntimeError(
                    f"Empty response from {redact_url(self.url)}")
            reader = csv.reader(io.StringIO(raw.decode(errors="ignore")))
            for row in reader:
                if len(row) < 2:
                    continue
                try:
                    int(row[1].strip())
                    _ipa.ip_address(row[0].strip())
                except ValueError:
                    continue
                break
            else:
                raise RuntimeError(
                    f"{self.name}: no valid 'ip, hits' rows in response "
                    "(likely a 200-OK error page; existing data file kept)")
            _os.replace(scratch, self._path)
            logger.info(f"Downloaded {self.name}")
        finally:
            scratch.unlink(missing_ok=True)
