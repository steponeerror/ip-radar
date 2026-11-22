# backend/tests/core/test_source_declared_maps.py
"""逐源分类映射的声明面测试(#409,架构评审④)。

验收契约(issue #409):
1. `_classification.py` 只剩机械(词表 + normalize/normalize_counted/
   unmapped_summary)——模块命名空间里不允许再出现任何 dict 实例
   (逐源映射按源名新增 dict 的模式即红);
2. 全部映射表住在各自源 module,内容与搬移前逐字节一致
   (快照件 source_declared_maps.snapshot.json = 搬移前从
   ipdb._classification 生成的独立记录,搬移丢键/改值当场红);
3. 「接入面」:新源接入 = 源 module 声明映射 + 计数绊线,零中央文件
   改动(反证:架构评审实测 f44f97e8 加 3 源扇出 20 文件,其中分类
   映射必须改 _classification.py——本票后该文件不在加源改动面上)。

行为不变式:映射内容来自搬移前快照,既有分类测试除 import 点外
零改动即全绿 = 分类输出等价的活证据。
"""
import json
from collections import Counter
from importlib import import_module
from pathlib import Path

import ipdb._classification as classification
from ipdb._classification import (
    CLASSIFICATION_TYPES, normalize, normalize_counted, unmapped_summary,
)

# 搬移落点声明表:map 名 → 源 module。新源带新映射时在此登记一行,
# 快照断言即覆盖它(快照件同步再生成,见文件尾注)。
DECLARED_MAP_HOMES = {
    "THREATFOX_MAP": "ipdb._sources.threatfox",
    "BLOCKLIST_DE_MAP": "ipdb._sources.blocklist_de",
    "PROXY_MAP": "ipdb._sources.ip2proxy",   # ADR 0001 空表回归绊线
    "OTX_PROTOCOL_MAP": "ipdb._sources.otx",
    "OTX_SUBSCRIBED_ROLE_MAP": "ipdb._sources.otx_subscribed",
    "TWEETFEED_MAP": "ipdb._sources.tweetfeed",
    "URLHAUS_MAP": "ipdb._sources.urlhaus",
    "URLHAUS_THREAT_MAP": "ipdb._sources.urlhaus",
    "DATAPLANE_MAP": "ipdb._sources.dataplane",
    "REPORTEDIP_MAP": "ipdb._sources.reportedip",
    "REPORTEDIP_CODE_THEMATIC": "ipdb._sources.reportedip",
    "SW_THREATS_MAP": "ipdb._sources.sw_threats",
    "MIRAGE_MAP": "ipdb._sources.mirage_feed",
    "ECHELON_MAP": "ipdb._sources.echelon",
    "NETUA_MAP": "ipdb._sources.blocklist_netua",
}


def _declared_maps() -> dict[str, dict]:
    """从各自源 module 取映射(落点错/未定义 → ImportError 当场红)。"""
    homes: dict[str, dict] = {}
    for map_name, module_name in DECLARED_MAP_HOMES.items():
        homes[map_name] = dict(getattr(import_module(module_name), map_name))
    return homes


def test_classification_surface_is_mechanical_only():
    """"_classification 只留机械:模块命名空间不得有任何 dict 实例。

    逐源映射再被加回中央命名空间(任何名目的 module 级 dict)即红——
    接入面回归的绊线(#409 验收 1)。
    """
    module_dicts = {name for name, val in vars(classification).items()
                    if isinstance(val, dict)}
    assert module_dicts == set(), (
        f"_classification 混入逐源/任意 dict:{sorted(module_dicts)} "
        "(映射表应住在各自源 module,#409)")
    # 机械件齐备:词表 + 三函数(既有测试/源模块的全部消费面)
    assert isinstance(classification.CLASSIFICATION_TYPES, frozenset)
    for fn in ("normalize", "normalize_counted", "unmapped_summary"):
        assert callable(getattr(classification, fn)), fn


def test_declared_maps_match_pre_move_snapshot():
    """映射内容与搬移前逐字节一致(快照 = 搬移前从 _classification 生成)。

    掉键/改值/落点错 ImportError 都当场红;新源登记新映射时同步再生成
    快照(python -c 见断言消息内的生成说明)并连同落点表一起提交。
    """
    fixture = json.loads(
        (Path(__file__).parent / "source_declared_maps.snapshot.json")
        .read_text(encoding="utf-8"))
    homes = _declared_maps()
    assert homes == fixture, (
        "逐源映射与搬移前快照不一致——若为有意变更,须在票内说明并用"
        " ipdb._classification 旧表的搬移前生成法重新生成快照")


def test_declared_maps_values_inside_vocab():
    """映射值(除 REPORTEDIP_CODE_THEMATIC)必须全在受控词表内。

    REPORTEDIP_CODE_THEMATIC 例外:code→官方分类「名」表(供
    native_categories 渲染),不是 classification.type 映射,值域
    天然在词表外(其 IntelMQ 映射在 REPORTEDIP_MAP,同受本断言管)。
    """
    for map_name, table in _declared_maps().items():
        if map_name == "REPORTEDIP_CODE_THEMATIC":
            continue
        outside = {v for v in table.values() if v not in CLASSIFICATION_TYPES}
        assert not outside, f"{map_name} 词表外值:{sorted(outside)}"


def test_new_source_onboards_via_declaration_only():
    """接入面证明(#409 验收 3):新源 = 源 module 声明 + 计数绊线。

    新源在自己的 module 里声明映射(零注册步骤、零中央文件改动),
    机械三车道(归一/计数/摘要)按传参即可用;声明错值被词表闸拦下,
    不进运行时分类。反证:f44f97e8 加 3 源扇出 20 文件的时代,分类
    映射必须进 _classification.py 中央命名空间——本测试钉住该面已收敛。
    """
    new_source_map = {                 # 模拟新源 module 内的声明
        "zombie": "infected-system",
        "bogus-slot": "not-a-type",    # 词表外——必须被机械闸拦下
    }
    assert normalize("  ZOMBIE ", new_source_map) == "infected-system"
    assert normalize("unknown-native", new_source_map) == "other"
    assert normalize("bogus-slot", new_source_map) == "other"  # 词表闸
    unknown: Counter = Counter()
    assert normalize_counted("unknown-native", new_source_map, unknown) == "other"
    assert unknown == Counter({"unknown-native": 1})
    unmapped_summary(unknown, logger=__import__("logging").getLogger(
        "test_source_declared_maps"), label="newsrc", hits="tag",
        item="tag")  # 摘要车道对声明面映射同样零注册可用
