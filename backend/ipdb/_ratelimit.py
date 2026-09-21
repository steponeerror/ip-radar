"""slowapi 限流(spec 2026-09-21 §8;Task 7,Q1-B 修正案口径)。

四个桶:
- ANON_BATCH 6/min —— 按远程地址,批量端点(query/upload stream),持合法
  key 时豁免。
- LOOKUP_GET 30/min —— 按远程地址,单查(lookup + stix 共一个预算),持
  key 时豁免。
- KEYED_BATCH 60/min —— 按 api_key_sub,**一个统一桶**横跨全部四个查询
  端点(spec §8 修正案);无 key 时豁免。
- LOGIN 5/min —— 按远程地址。计**所有**尝试而非只计失败:对暴力破解的
  阻尼,计尝试严格优于计失败(失败计数可被"探测性成功登录"绕过),而
  单管理员的交互式登录节奏远碰不到 5/min,语义上无副作用。

双向互斥(exempt_when)机制:四查询端点的 dependencies(api_key_dep,
Task 6)先于端点函数体执行,而 slowapi 包装的就是端点函数本身 ——
exempt_when/_sub_key 读 request.state.api_key_sub 时它已就绪。

三个查询桶用 shared_limit + 固定 scope 字符串:slowapi 默认 key_style="url"
按**具体请求路径**分桶(/api/lookup/1.1.1.1 与 /api/lookup/8.8.8.8 是两个
桶),路径轮换会架空"单查 30/min";固定 scope 使预算按地址/按 key 横跨
路径与端点,才是 spec §8(单查 30、批量 6、每 key 60)的语义。

灭火开关:IP_RADAR_RATELIMIT=0 关闭(默认开)。测试套件经 conftest 的
rate_limit_off autouse fixture 默认关闭;test_ratelimit.py 逐用例重开。
"""
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

ANON_BATCH = "6/minute"    # 匿名批量查询:按 IP
KEYED_BATCH = "60/minute"  # keyed 统一桶:批量 + 单查 + stix
LOOKUP_GET = "30/minute"   # 匿名单查(lookup + stix):按 IP
LOGIN = "5/minute"         # 登录爆破:按 IP,计所有尝试

limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.environ.get("IP_RADAR_RATELIMIT", "1") != "0",
)


def _has_sub(request) -> bool:
    """有效 API key 已通过(Task 6 api_key_dep 设置;匿名请求无该属性)。"""
    return getattr(request.state, "api_key_sub", None) is not None


def _no_sub(request) -> bool:
    """keyed 桶的豁免条件:无 key(与 _has_sub 互斥的另一向)。"""
    return not _has_sub(request)


def _sub_key(request) -> str:
    """keyed 桶的 key = API key subject;常量哨兵防空 key(slowapi 对空
    key 值跳过该 limit 而不报错)。"""
    return getattr(request.state, "api_key_sub", None) or "__anon__"


def anon_batch_limit():
    """匿名批量桶:6/min 按 IP;持合法 key 豁免(双向互斥)。"""
    return limiter.shared_limit(ANON_BATCH, scope="anon_batch",
                                key_func=get_remote_address,
                                exempt_when=_has_sub)


def anon_lookup_limit():
    """匿名单查桶:30/min 按 IP(lookup 与 stix 同一预算);持 key 豁免。"""
    return limiter.shared_limit(LOOKUP_GET, scope="anon_lookup",
                                key_func=get_remote_address,
                                exempt_when=_has_sub)


def keyed_query_limit():
    """keyed 统一桶:60/min 按 key,横跨四个查询端点;无 key 豁免。"""
    return limiter.shared_limit(KEYED_BATCH, scope="keyed_query",
                                key_func=_sub_key, exempt_when=_no_sub)


def login_limit():
    """登录爆破守卫:5/min 按 IP,计所有尝试(包装在 authenticate 之前)。"""
    return limiter.limit(LOGIN)
