"""三套词表的机读对拍(#451 卡 12,第四轮架构评审落地)。

评审结论:三套词表各自只有一处机读全集,其余各处派生或手抄,且已经漂过
一次——后端 2026-10-24 加 dns/ntp 两个分类类型,前端 CLASS_KEYS 没跟,
手抄覆盖清单照样绿;任务状态徽章文案缺 running。本文件把三处
「真源 → 消费面」钉成对拍,任一侧单独改动即红:

1. 任务状态:backend/ipdb/_tasks.py 状态机的字面量写点(字段默认/构造
   实参/直写/_set_state 转移)↔ frontend/src/api.ts TaskState.state 联合
   + admin.tasks.state.* 双语文案键。前端侧另由 BatchPanel.tsx 的
   按 TaskState 全枚举的文案键表在编译期钉一半。
2. 分类类型:ipdb._classification.CLASSIFICATION_TYPES ↔ threatDisplay.ts
   CLASS_KEYS(normalize 的 - → _ 形态;方言遗留键豁免见
   _CLASS_KEY_LEGACY)。
3. 评估判词:ipdb._eval.verdict._ACTION 键集(assess() 每条返回路径都经
   它取 action,新增判词漏项当场 KeyError,故它是判词全集的机读锚)↔
   SourcesPage.tsx 消费的 sources.eval.* 文案键(键名 = state 小写、
   - 换 _,两份 locale 都要齐)。

前端文件一律读本仓源码文本/JSON(先例 test_glossary_anchors.py 从仓根读
GLOSSARY.md;路径锚 __file__,worktree/主检出各自自洽)。正则命中失败时
断言消息带文件与期望形状,不许提取器空转绿(健全性下限同先例 MIN_*)。
"""
import json
import re
from pathlib import Path

from ipdb._classification import CLASSIFICATION_TYPES

REPO = Path(__file__).resolve().parents[3]  # 仓库根(先例 test_glossary_anchors.py)

API_TS = REPO / "frontend/src/api.ts"
TASKS_PY = REPO / "backend/ipdb/_tasks.py"
OPS_ROUNDS_PY = REPO / "backend/ipdb/_ops_rounds.py"
THREAT_DISPLAY_TS = REPO / "frontend/src/components/threatDisplay.ts"
SOURCES_PAGE_TSX = REPO / "frontend/src/pages/SourcesPage.tsx"
LOCALE_PATHS = {
    "en": REPO / "frontend/src/i18n/locales/en.json",
    "zh-CN": REPO / "frontend/src/i18n/locales/zh-CN.json",
}


def _locales() -> dict[str, dict[str, str]]:
    return {loc: json.loads(p.read_text(encoding="utf-8")) for loc, p in LOCALE_PATHS.items()}


# --- 1. 任务状态 ----------------------------------------------------------

# 后端状态机写点(注释枚举行会漂,只认字面量写点):
#   state: str = "X"      dataclass 字段默认(Task.queued;Batch.running
#                         同形并入,running 本就是任务态,无害)
#   state="X"             Task(...) 构造实参(ops 轮占道 running)
#   task.state = "X"      cancel 直写(\b 圈定 task.,不把 b.state 混进来)
#   _set_state(task, "X"  调度器唯一转移点
#   finish_ops_round(id, "X")  ops 轮收口(backend/ipdb/_ops_rounds.py 的实参;
#                         2026-11-26 评审 3.1 补,此前只经这条路进入的新态两侧都漏)
_BACKEND_STATE_RES = (
    re.compile(r'state: str = "([a-z]+)"'),
    re.compile(r'\bstate="([a-z]+)"'),
    re.compile(r'\btask\.state\s*=\s*"([a-z]+)"'),
    re.compile(r'_set_state\(task,\s*"([a-z]+)"'),
)
_OPS_ROUND_STATE_RE = re.compile(r'finish_ops_round\(\s*[^,]+,\s*"([a-z]+)"')


def _backend_task_states() -> set[str]:
    src = TASKS_PY.read_text(encoding="utf-8")
    states: set[str] = set()
    for pat in _BACKEND_STATE_RES:
        states |= set(pat.findall(src))
    # ops 轮收口的实参状态(_ops_rounds.py):变量写点,上面的正则抓不到
    ops_src = OPS_ROUNDS_PY.read_text(encoding="utf-8")
    states |= set(_OPS_ROUND_STATE_RE.findall(ops_src))
    # 提取器健全性下限(先例 test_glossary_anchors MIN_*):写点正则空转时
    # 这里先红,而不是让下方对拍因双空集而假绿。
    assert len(states) >= 5, (
        f"_tasks.py 状态写点提取到 {sorted(states)},低于健全性下限——"
        "状态机写点形状变了,test_vocab_contract 的提取正则要跟"
    )
    return states


def _frontend_task_states() -> set[str]:
    src = API_TS.read_text(encoding="utf-8")
    m = re.search(r"export interface TaskState \{[^}]*\}", src, re.S)
    assert m, "frontend/src/api.ts 里找不到 export interface TaskState { … } 块"
    sm = re.search(r"^\s*state:\s*([^;]+);", m.group(0), re.M)
    assert sm, "api.ts TaskState 块里找不到 state: 行(联合类型被改形?)"
    fe = set(re.findall(r'"([a-z]+)"', sm.group(1)))
    line = src[: m.start()].count("\n") + 1
    assert fe, f"api.ts:{line} TaskState.state 联合里提取不到状态字面量"
    return fe


def test_task_states_backend_machine_matches_frontend_union():
    be, fe = _backend_task_states(), _frontend_task_states()
    assert be == fe, (
        "任务状态词表漂移(#451 卡 12 对拍):"
        f"后端多出 {sorted(be - fe)}(frontend/src/api.ts TaskState 联合要跟,"
        "BatchPanel STATE_LABEL_KEYS 与 admin.tasks.state.* 双语键同批补);"
        f"前端多出 {sorted(fe - be)}(_tasks.py 状态机已无此态,前端联合该清)"
    )


def test_task_state_badge_copy_bilingual_complete():
    fe = _frontend_task_states()
    missing = sorted(
        f"{loc}: admin.tasks.state.{s}"
        for loc, d in _locales().items()
        for s in fe
        if f"admin.tasks.state.{s}" not in d
    )
    assert not missing, f"任务状态徽章文案缺键(#451 卡 12):{missing}"


# --- 2. 分类类型 ----------------------------------------------------------

# CLASS_KEYS 里后端 CLASSIFICATION_TYPES 今天没有对应类型的三键,对拍豁免:
#   botnet_cc / hosting / vpn  历史展示键,来处没查到裁定记录(实现报告
#              §五.3)。后端的方言型是 botnet;资产面的 is_hosting / is_vpn
#              走 asset.* 文案,不经 classLabel。清这三键属展示改动,另开票。
#              这张表只放行「前端比后端多出来的键」(对拍是单向的),不许拿来藏漂移。
_CLASS_KEY_LEGACY = frozenset({"botnet_cc", "hosting", "vpn"})


def _frontend_class_keys() -> set[str]:
    src = THREAT_DISPLAY_TS.read_text(encoding="utf-8")
    m = re.search(r"const CLASS_KEYS[^=]*=\s*\{(.*?)\n\};", src, re.S)
    assert m, "threatDisplay.ts 里找不到 const CLASS_KEYS … = { … }; 块"
    # 键有两种写法:带引号("c2_server")与裸标识符(botnet_cc),都要认;
    # 字符类含数字(c2_server 里有个 2)。
    keys = set(re.findall(r'"?([a-z0-9_]+)"?\s*:\s*"class\.', m.group(1)))
    line = src[: m.start()].count("\n") + 1
    assert keys, f"threatDisplay.ts:{line} CLASS_KEYS 块里提取不到键(表形状变了?)"
    return keys


def test_classification_types_frontend_class_keys_match_backend():
    be = {t.replace("-", "_") for t in CLASSIFICATION_TYPES}
    fe_all = _frontend_class_keys()
    assert len(be) >= 15, (
        f"CLASSIFICATION_TYPES 提取到 {sorted(be)},低于健全性下限——"
        "词表形状变了,test_vocab_contract 的对拍要跟"
    )
    assert be <= fe_all, (
        "分类类型词表漂移(#451 卡 12 对拍):"
        f"前端缺键 {sorted(be - fe_all)}(threatDisplay.ts CLASS_KEYS 要跟"
        "CLASSIFICATION_TYPES,class.* 双语文案同批补)"
    )
    assert fe_all - be <= _CLASS_KEY_LEGACY, (
        "分类类型词表漂移(#451 卡 12 对拍):"
        f"前端多出 {sorted(fe_all - be - _CLASS_KEY_LEGACY)}"
        "(后端已删该型,CLASS_KEYS 与 i18n 文案一起清;_CLASS_KEY_LEGACY 只收上面"
        "三个历史展示键,要新增豁免先补裁定记录)"
    )


# --- 3. 评估判词 ----------------------------------------------------------

# 前端键名派生规则(SourcesPage.tsx,一字面量锚):
#   t("sources.eval." + s.eval.verdict.toLowerCase().replace(/-/g, "_"))
# 测试按同一规则重算后端判词的期望键;规则行若改形,下方锚断言带行号报红。
_VERDICT_KEY_PREFIX = "sources.eval."
# 非判词键:W4 NO-DATA 徽标的折叠提示文案,同前缀但不是判词。
_VERDICT_NON_STATE_KEYS = frozenset({"sources.eval.noDataTitle"})


def test_eval_verdicts_frontend_copy_table_matches_backend():
    # 私有导入有先例(test_eval_api.py 对 _eval_reader._dir):_ACTION 是
    # assess() 全部返回路径取 action 的查找表,键集 ≡ 判词全集的机读锚。
    from ipdb._eval.verdict import _ACTION

    be = {v.lower().replace("-", "_") for v in _ACTION}
    assert len(be) >= 5, (
        f"verdict._ACTION 键集提取到 {sorted(be)},低于健全性下限——"
        "判词全集形状变了,test_vocab_contract 的对拍要跟"
    )

    src = SOURCES_PAGE_TSX.read_text(encoding="utf-8")
    anchor = '"sources.eval." + s.eval.verdict.toLowerCase().replace(/-/g, "_")'
    assert anchor in src, (
        "SourcesPage.tsx 里找不到判词键名派生模板 "
        f'({anchor!r})——判词文案消费面改形,本测试的键名换算要跟'
    )

    for loc, d in _locales().items():
        fe = {
            k.removeprefix(_VERDICT_KEY_PREFIX)
            for k in d
            if k.startswith(_VERDICT_KEY_PREFIX) and k not in _VERDICT_NON_STATE_KEYS
        }
        assert fe == be, (
            f"评估判词文案表漂移(#451 卡 12 对拍,{loc}):"
            f"前端缺键 {sorted(be - fe)}(sources.eval.* 要跟 _eval/verdict.py,"
            "两份 locale 同批补);"
            f"前端多出 {sorted(fe - be)}"
            "(verdict.py 已无这个判词,就把文案键一起清;如果是同前缀下的非判词键,"
            "登记进 _VERDICT_NON_STATE_KEYS)"
        )
