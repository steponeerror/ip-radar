"""CESNET NERD bad_ips_med_conf — IpListSource 子类(binarydefense 模式).

``https://nerd.cesnet.cz/nerd/data/bad_ips_med_conf.txt`` — CESNET NERD
(Network Entity Reputation Database)中等置信(reputation > 0.2)IP 清单,
纯 IP 行 + ``#`` 注释头(含 ``Generated at ... UTC`` 生成时间戳,小时更;
实测 2026-11-22 03:00 UTC 快照 76,103 键 / 1,079,327 字节)。

无差别指控(无 per-IP 行为类型)→ 基类分类 ``blacklist``(词表注释
「no subcategory available」,siberkapan / mirage 空标签同口径)。

回声结构 FLAG(2026-11-22 发现轮,用户裁定立项接受):2026-05-12 起 NERD
reputation 分已并入 DShield + OTX + 公开黑名单,与池内源有覆盖面双计;
dedup_lineage 穿不透聚合层 → 按计算型聚合源低价(reliability 0.60,
provenance_tier C,ipsum/firehol 同档)。

许可未标注(同轮 FLAG,接受);上游礼貌要求:拉取 ≤1 次/小时、整点后
1-5 分钟——本源 stale_days=2 + 调度器下载间隔兜底,未做专门限速(拉取
频率由调度器统一节流,高于小时级)。

注释头的 ``Generated at`` 时间戳在下载路径(parse_raw)解析进 INFO 日志
(新鲜度可见性);数据文件落盘为基类规范化明单(注释行不入库,
IpListSource.download 契约)。
"""
import logging

from ._base import IpListSource

logger = logging.getLogger(__name__)


class NerdMedConfSource(IpListSource):
    name = "nerd_medconf"
    category = "threat"
    url = "https://nerd.cesnet.cz/nerd/data/bad_ips_med_conf.txt"
    filename = "nerd_medconf.txt"
    fields = ("is_malicious",)
    classification_type = "blacklist"
    verdict = "malicious"
    stale_days = 2                        # 小时更;容忍一次错过周期
    reliability = 0.60                    # 计算型聚合源(见 docstring 回声 FLAG)
    authoritative_for = ()
    provenance_tier = "C"                 # C=聚合派生(S21):rep 分含 DShield/OTX/黑名单
    # 载入期排除 infra_services curated 单址集(2026-11-27 #514:1.0.0.1
    # Cloudflare 公共 DNS 被单源误列恶意,唯一指控人即 nerd_medconf;与
    # PR #392 gorkemgun_sgb_blocklist / #450 otx 同一开关,数据文件零改写,
    # 关 IP_RADAR_INFRA_NOISE_FILTER 重建即复原)
    infra_noise_filter = True
    # 未 bump HARVEST_REV(沿 2026-11-25 #450 取舍:不为一个源在 964MB 小机
    # 上做一次全族迁移重建,明账记在 _lmdb.py 挂账注释与 CHANGELOG 部署
    # 注记):存量 nerd_medconf 族是开关关着时建的,调度器不会补建,要到下次
    # 刷新重建才带上这道过滤——按 _scheduler.py 的规则是数据文件时间之后
    # 35–47 小时内的下一个槽位再加排队延迟(更新账本实测三次 35.4–39.6
    # 小时);要立即生效就手动触发一次 nerd_medconf 更新(先下载重写数据
    # 文件,重建才会跑;裸 rebuild 对已收敛的族会被跳过)。

    def parse_raw(self, raw: bytes) -> list[str]:
        """默认解析 + 注释头 ``Generated at`` 时间戳进日志(下载路径内联
        调用;仅首命中行,数据行为零开销)。"""
        for line in raw.decode(errors="ignore").splitlines():
            if line.startswith("#") and "Generated at" in line:
                logger.info("nerd_medconf upstream %s",
                            line.lstrip("# ").strip())
                break
        return super().parse_raw(raw)
