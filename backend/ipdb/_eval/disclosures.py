"""R10 混杂披露生成器 (spec §7): 每份读数报告必列十二条混杂。

十二条 = spec §7 冻结清单逐条转录(正源 docs/superpowers/specs/
2026-10-12-eval-loop-hardening-design.md §7), 语义一字不漏, 顺序恒
①-⑫。机器可填槽按现口径写死: ② v4-only 恒 True(语料无 v6)、
③ 分档指针=快照 ctype_mix、⑨ 分子口径注记(F10 子读数可回算);
readout/metas 参数留给后续逐轮填充, 现不消费(不发明新填充)。
extra 只追加在尾部, 永不替换/重排十二条(spec §7 硬门: 披露不可裁剪)。
"""
from __future__ import annotations

from .assets import AssetMeta

REQUIRED_CONFOUNDS: tuple[str, ...] = (
    "①真值层语料公开可被整抄(MC/纠错/k_nonhoneypot 奖励高包含度;三变体:整抄/亚采样/同种群有机收集)",
    "②v4-only 口径=True",
    "③网络构成/ASN 集中度分档=见快照 ctype_mix",
    "④出口段身份(VPN/Tor,纠错检验分子分层注记)",
    "⑤/24 簇相关(重抽样单元=/24 块 bootstrap)",
    "⑥rir 闸启用后真值层分配年龄构成左移(7.56% 基线不可比)",
    "⑦同上游多派生双票通道(otx/otx_subscribed 互嵌现状)",
    "⑧锚/基线读数环境口径(10-10 镜像 ip2proxy 存量)",
    "⑨真值层命中分子=IP 级分子;ctype 错配仍计,ctype 匹配子读数可由 F10 快照回算",
    "⑩中性层=未验证阴性",
    "⑪短记忆/滚动窗行为源纠错检验结构性偏低",
    "⑫地域分层(S15)",
)


def render_disclosures(readout: dict, metas: dict[str, AssetMeta],
                       extra: list[str] | None = None) -> list[str]:
    """渲染十二条必列混杂行 + 尾部追加 extra(不覆盖不重排, spec §7)。"""
    return [*REQUIRED_CONFOUNDS, *(extra or [])]
