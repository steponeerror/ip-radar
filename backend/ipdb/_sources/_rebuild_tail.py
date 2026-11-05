"""三条 rebuild 车道末尾共享收尾(issue #291,折并深度=中档票面裁决):
「载入期 infra 过滤+排除记账」与「覆盖数 v4/v6 分流」收成一份,三车道
(A=Source/_source_base.py,B=IpListSource/C=CsvSource/_sources/_base.py)
import 本模块,不再各抄一遍;#310 起五个 bespoke 预扫描源
(tor_exits/abuseipdb/spamhaus/blocklist_de/cn_isp)的手抄 v4/v6 覆盖数
双 genexp 也换用本模块 covered_counts,同形不再各抄。

换装验收留痕(#310):改前改后 5 源 × 69 个 rebuild 产物 sha256 全等
(零漂移),harness 同 rev 两跑 byte-identical 自证
(git_rev=a5c9c1ba,PYTHONHASHSEED=0)。

车道差异按票面裁决保留,勿在此「统一」:
- commit 双形态:A 流式 factory(rebuild_dual_family 调用两次做族分区,
  内存纪律判例)/ B 先物化 records 再 commit_dual_family —— 两个入口
  语义不同(后者含 owner 六态回写),接线维持原样;
- A 车道 covered=Auto 写库循环内统计(免预扫描,流式位点口径),不经
  本模块 covered_counts;B/C 预扫描后经 covered_counts 分流;
- 排除留痕调用点维持各车道原位:A 在提交后(与 bad_fs 告警同点),
  B/C 在提交前(既有顺序)。
"""
from . import _infra_filter
from . import _lmdb as _lmdb_mod   # 经模块属性调 covered_ip_count:保留
# _lmdb 缝可 patch(既有钉子 test_safe_delete_locking 每族恰一次不变量)


class InfraNoiseGate:
    """载入期 infra 噪声排除的记账员(issue #183;#291 过滤+记账收共享)。

    语义与三车道原手抄段逐字等价:
    - enabled = 源显式 opt-in(infra_noise_filter,基类默认 False)+ 总开关
      IP_RADAR_INFRA_NOISE_FILTER(默认开;显式关 = 关过滤重建即复原);
    - blocks(net):net 为已解析 IPv4/IPv6Network;仅 curated 单址精确
      指控命中(宁少算,更大 CIDR 不排 —— 判定单源点在
      _infra_filter.is_infra_noise);
    - excluded 记 str(net) 明文;flush() 经 _infra_filter.log_exclusions
      去重留痕(单/双遍 harvest 的重复记账由 log 端 set 去重吸收)。
    """

    __slots__ = ("name", "enabled", "excluded")

    def __init__(self, source_name: str, infra_noise_filter: bool):
        self.name = source_name
        self.enabled = (bool(infra_noise_filter)
                        and _infra_filter.filter_enabled())
        self.excluded: list[str] = []

    def blocks(self, net) -> bool:
        """命中 curated 单址 → 记账并 True(调用方据此跳过该条记录)。"""
        if self.enabled and _infra_filter.is_infra_noise(net):
            self.excluded.append(str(net))
            return True
        return False

    def flush(self) -> None:
        """排除留痕(审计面:数据文件零改写,关过滤重建即原样回算)。"""
        if self.excluded:
            _infra_filter.log_exclusions(self.name, self.excluded)


def covered_counts(cidr_strs) -> tuple[int, int]:
    """预扫描覆盖数 v4/v6 分流(#291 收共享;B/C 车道口径;#310 起五个
    bespoke 预扫描 rebuild —— tor_exits/abuseipdb/spamhaus/blocklist_de/
    cn_isp —— 的手抄双 genexp 亦折入此处)。

    cidr_strs 须可重复迭代(v4/v6 两遍分流各扫一遍,与原车道两条
    genexp 同内存剖面,零物化;B 传 list、C 传 acc dict)。非法条目由
    covered_ip_count 跳过。A 车道不经此处:流式位点用 covered=Auto 在
    写库循环内统计(_lmdb.rebuild_lmdb,免预扫描)。
    """
    cov4 = _lmdb_mod.covered_ip_count(c for c in cidr_strs if ":" not in c)
    cov6 = _lmdb_mod.covered_ip_count((c for c in cidr_strs if ":" in c),
                                      ip_version=6)
    return cov4, cov6
