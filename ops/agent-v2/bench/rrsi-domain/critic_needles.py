# critic_needles.py — 考题针(critic_patterns)构造(#325 F1 修复;评审 rrsi-a-review.md P1)。
# 标准库自足、零 RRSI 依赖:adapter.py 从这里取(单一真源),tests/rrsi-domain.test.mjs
# spawn python3 直接导入断言针形(CI/本地无 RRSI 面亦可测,smoke-glm 条件 skip 判例)。
import re

# 共享基建 host 显式豁免(#325 F1 裁决):多源共用的代码托管/CDN host 不进 critic 针。
# 候选 diff 合法提及 github API/端点是常态(拉取/发布/检索都走它),进针 = 每轮误拦
# 走 repair;考题名字针与源专属 host 针已足够强。豁免 = host 本身与其父域一并不入针。
SHARED_INFRA_HOSTS = {
    "github.com",                 # 禁词引用:考题针豁免词汇表(#325 F1 共享基建裁决),非泄漏
    "raw.githubusercontent.com",  # 禁词引用:同上——多源共用 raw 面,进针必每轮误拦
    "cdn.jsdelivr.net",           # 禁词引用:同上——公共 CDN
}

def squeeze(text: str) -> str:
    """小写+剔除非字母数字——与 bench/leak-check.mjs squeeze 同折叠(数据面同源)。"""
    return re.sub(r"[^a-z0-9]", "", text.lower())

def buildCriticPatterns(rows):
    """考题针(critic_patterns)。

    框架 critic.py precheck 对【原始 diff】re.search(无 MULTILINE、无行折叠)——旧
    旧形 `^(?:挤压形)$` 一头一尾卡死,要求整段 diff 恰等于一个针才命中——考题名硬编码永远漏(F1)。
    故针形 = 环视形,不卡头尾(上游先例 dev/rrsi/domains/coding/adapter.py 的
    `(?<![\\w-])name(?![\\w-])`):RAW 原文形(name/host/≥3 段剥一段的父域,同
    leak-check.mjs buildNeedles 的折叠规则数据面)+ 挤压形附加 alternation。环视取
    [\\w-] 边界:考题名作为更长标识符/URL 段的子串不误伤(如源 x 与源 x_extra 各有
    各的针,x 针不打中 x_extra 文本)。"""
    pats = []
    for r in rows:
        alts = [r["name"], squeeze(r["name"])]
        host = r.get("host")
        if host and host != "-" and host not in SHARED_INFRA_HOSTS:
            alts += [host, squeeze(host)]
            labels = host.split(".")
            if len(labels) >= 3:
                parent = ".".join(labels[1:])
                if parent not in SHARED_INFRA_HOSTS:
                    alts += [parent, squeeze(parent)]
        body = "|".join(re.escape(a) for a in dict.fromkeys(filter(None, alts)))
        pats.append((rf"(?<![\w-])(?:{body})(?![\w-])",
                     f"考题针:泄漏源 {r['name']} 的名字/下载域名"))
    return pats
