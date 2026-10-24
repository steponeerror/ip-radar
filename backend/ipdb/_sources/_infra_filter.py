"""载入期基础设施噪声过滤(issue #183;ADR 0008 8.8.8.8/114DNS 事故整改)。

事故:myip_ms(8.8.8.8)/ziyadnz+cps(114.114.114.114 假印证)把公认公共
基础设施打成惡意。哲学 = ADR 0001 ip2proxy 资产弃权同族:「是基础设施」
是属性不是滥用指控;判例在册 = _eval/verdict.py MIXED 杠杆第一项
「tighten the source's load-time noise filter」。

纪律(证据永不灭失):
- 原始数据文件零改写 —— 排除只发生在载入(rebuild)面,LMDB 是投影;
- 排除集 = 显式 curated 集(真源 infra_services._DATA,单真相不复制第二
  份;绝不查 infra_services 的 LMDB——本地纪元可落后于 csv,勘察 §4 判例);
- 开关 IP_RADAR_INFRA_NOISE_FILTER(默认开;"0"/"false"/"no"/"off" 关)
  ——关过滤重建即原样回算复原;
- 排除计数与被排条目进 rebuild 日志(审计面)。

宁少算:仅排除对 curated 单址的精确指控;含 infra IP 的更大 CIDR 是不同
断言,不排(同源重复/派生不会被双算,也不会被扩大化清除)。
"""
import ipaddress
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

ENV_SWITCH = "IP_RADAR_INFRA_NOISE_FILTER"
_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def filter_enabled() -> bool:
    """载入期过滤总开关,调用时读 env(子进程车道 env 继承,测试可切换)。
    默认开 = 整改即生效;显式关 = 关过滤重建即复原原摄取。"""
    return os.environ.get(ENV_SWITCH, "1").strip().lower() not in _OFF_VALUES


@lru_cache(maxsize=1)
def curated_infra_addresses() -> frozenset:
    """curated 公共基础设施单址集(真源 = infra_services._DATA;_DATA 是
    唯一真相源,data/ 下 csv 是其物化投影,LMDB 更是投影的投影)。"""
    from .infra_services import _DATA
    out = set()
    for row in _DATA.strip().splitlines():
        ip = row.split(",", 1)[0].strip()
        if ip:
            out.add(ipaddress.ip_network(ip, strict=False))
    return frozenset(out)


def is_infra_noise(net) -> bool:
    """单址网络恰好命中 curated 集 → True(宁少算:更大 CIDR 不排)。"""
    if net.num_addresses != 1:
        return False
    return net in curated_infra_addresses()


def log_exclusions(source_name: str, excluded: list[str]) -> None:
    """排除留痕:去重后的计数 + 被排条目明文(条目集 ≤ curated 集规模,
    恒小,全量列出)。此日志即排除面审计面:关过滤重建可复原,数据文件
    原样可回算。"""
    uniq = sorted(set(excluded))
    logger.info("infra noise filter: %s excluded %d curated-infra entries "
                "at load (data file untouched; %s=0 + rebuild restores): %s",
                source_name, len(uniq), ENV_SWITCH, ", ".join(uniq))
