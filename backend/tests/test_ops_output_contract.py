"""ops 跨目录产出契约对拍门(票 #413;架构评审候选⑤——ADR 0008 四层漏的那一层,不动金标层)。

契约:轮 CLOSE 后,UI 读面必有本轮报告件。#403(2026-10-24→11-22 静默断供)证明金标
只护 `rounds/<id>/` 轮目录树;「轮关必产出 UI 可读包」是**跨目录**契约——轮侧经后端桥
(`_ops_rounds._round_env` 注入 `DOCS_ROOT = ops_root().parent`)写
`<DOCS_ROOT>/ops/packages/`,UI 侧读 `ops_root()/packages/*.md`(`_ops_read.list_packages`,
即 GET /api/ops/packages 的函数体)。桥挪走,两侧各自全绿;引擎 CLOSE 漏写,只有 node 侧 selftest 在它自选的 opsRoot 下
会红——后端/UI 读面都无感(既有测试:
桥单测只断言 env 键值;selftest / agent-v2 测试断言的是测试**自己指定**的 opsRoot 下
有件),用户点开却看不到报告。

本门两条硬律(缺一即退化为又一侧的自证):
1. **真走桥**:经产品 `spawn_round` 拉起真 node 子进程——argv / cwd / env 全出自产品
   代码(`_agent_argv` / `_REPO_ROOT` / `_spawn_env` = 白名单 ∘ `_round_env`)。子进程的
   DOCS_ROOT 族只许来自桥:ambient 三名被指到诱饵目录(见 bridge_sandbox),测试里没有
   任何一处把 DOCS_ROOT 指向 `$IP_RADAR_DATA_DIR`。
2. **用 UI 读面函数断言**:`list_packages()` 出现按报告件命名契约(`reportNameOf`:
   `<date>-<type>-<HHMM>.md`)由本轮 round_id 推出的件,`read_package()` 读得到且正文含
   本轮 round_id。

引擎与模型面:被测宿主 = UI 健康轮缺省命令 `ops/pipeline-core/pipeline.mjs`(#412 后桥
直连)。相对缺省 argv 的唯一偏离 = 经 `IP_RADAR_OPS_AGENT_CMD` 测试缝多带 `--fixtures`
(faux 模型面:零网络零花费,秒级;canned 回合 = 仓内 `fixtures/pipeline`)。不带
`--fixtures` 即真 provider(花钱、要凭证)——不是本门的被测面,真模型 E2E 另有
test_ops_rounds_e2e.py。

沙箱世界(全在 tmp_path):curl 替身(`feed_freshness` 走 PATH;冻结三锚点 = 仓内
`fixtures/pipeline/README.md` 配对契约)+ 判例与抑制规则两件夹具(同 README:SYNTH
canned 报告引用 `2026-06-01-golden-aggregator.md`,CLOSE 的 verify_cited_precedents
必须找得到它;R1 抑制规则配对 canned 假设数)。求值 CLI 不打桩:桥注入
`OPS_EVAL_PY = 本解释器`、`OPS_DATA_DIR = 空数据目录` → 矩阵真跑(空库)、锚巡检因库
未加载而降级旁路(ANCHOR_SWEEP degraded,轮仍成功;本门守的是 CLOSE 后的产出面,
不是巡检读数)。

本门的已知红因(诊断随断言输出):①引擎 CLOSE 漏写报告件;②桥断——DOCS_ROOT 不再
= `ops_root().parent`,报告件落到别处;③运营树 backend/ 或 frontend/ 有未提交改动
→ 轮内 `sandbox_assert` 红线判轮失败(sandbox_violation;引擎按设计,先提交再跑)。

未覆盖(如实):发现轮引擎 `agent.mjs`(只有真模型面,CLI 无 faux 缝;它自写包、不走
writeRoundReport)、agent-v2 两任务的 CLOSE(既有 node 测试各断言 packages 下有件:
agent-v2/tests/discover-round.test.mjs、health-e2e.test.mjs;生产 cron 直拉 v2,不经
后端桥)、resume 路径(与首轮同一 finishClose 调用点)。
"""

import json
import os
import re
import shlex
import shutil
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

# ── 冻结件期望值(独立真源,逐字;不从被测模块导入,防套套逻辑)──
# spawn 契约 health argv(GLOSSARY「spawn 契约」;test_ops_rounds.py 同源抄录):本门经
# IP_RADAR_OPS_AGENT_CMD 测试缝换上的 shim = 同一命令体 + --fixtures(pipeline.mjs 的
# faux 模型面只认这个旗标,无 env 开关;canned 回合目录 = 仓内 fixtures/pipeline)。
HEALTH_CMD_BODY = "node --max-old-space-size=256 ops/pipeline-core/pipeline.mjs"
PIPELINE_FIXTURES = "ops/pipeline-core/fixtures/pipeline"
ROUND_INPUT = "对全部离线源做一次健康体检,给出冻结/死键/不可达快照"
# 报告件命名契约(ops/pipeline-core/pipeline/round-report.mjs reportNameOf):
# <date>-<HHMM>-health → <date>-health-<HHMM>.md
_ROUND_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2})-(\d{4})-health")

# shim:桥追加的 <round_type> <input_text> 两位经 $1/$2 原样进引擎 CLI(与缺省 argv 逐位
# 对应;相对 cwd = 仓根,桥的 Popen cwd)。用 bash 包一层只为把两位位置参数显式接进去。
FAUX_PIPELINE_SHIM = f"""#!/usr/bin/env bash
exec {HEALTH_CMD_BODY} "$1" --fixtures {PIPELINE_FIXTURES} "$2"
"""

# curl 替身(golden stubCurl / selftest 同型):三冻结锚点 + 其余新鲜,零网络。时间确定性 =
# UTC 日界截断(#163 位等价判例):同 UTC 日内 Last-Modified 恒定且 age_days 恒 = d。
_CURL_STUB = r"""#!/usr/bin/env bash
url="${@: -1}"
d=30
case "$url" in
  *cinsscore*) d=220 ;;
  *binarydefense*) d=210 ;;
  *dshield*) d=200 ;;
esac
printf 'HTTP/1.1 200 OK\r\nLast-Modified: %s\r\nContent-Length: 4\r\n\r\n' "$(date -u -d "@$(( $(date +%s) / 86400 * 86400 - d * 86400 ))" '+%a, %d %b %Y %H:%M:%S GMT')"
exit 0
"""

# 判例夹具(fixtures/pipeline/README「判例树 fixture」:SYNTH canned 报告引用它,CLOSE 的
# verify_cited_precedents 找不到即门红)
_PRECEDENT_NAME = "2026-06-01-golden-aggregator.md"
_PRECEDENT_FIXTURE = """---
id: 2026-06-01-golden-aggregator
date: 2026-06-01
subject: fixture — 聚合器候选必须实测排他率
context: >
  聚合器形状候选,上游映射推断重叠不可信。
human_ruling: >
  实测排他率 50.0%,推翻 REJECT,立项。
reward:
  hard_gates:
    exclusive_rate: "50.0%"
  ruling_agreement: overruled
---

正文检索词:聚合器 排他率 回声 冻结 违例。
"""

# 抑制规则夹具(README「抑制规则 fixture」:R1 压掉 dshield 冻结读数 → 幸存 2 = canned 假设数)
_SUPPRESSIONS_FIXTURE = {
    "version": 1,
    "rules": [{
        "id": "R1", "adopted": "2026-10-24", "adopted_via": "item-fixture",
        "match": {"bucket": "frozen", "url_shape": "*dshield.org*"},
        "action": "suppress", "note": "fixture:dshield 冻结读数为已知探测伪迹",
        "review_at": "2027-01-24",
    }],
}

# 供给面(可跳过)vs 仓内受控文件(路径漂移要当场红,不许静默跳过——#412 终审 P1 判例):
# node/bash/git/rg/flock = 引擎 CLI 与其 shell 步的外部供给;ops/node_modules =
# gitignored 安装件(CI 的 backend job 不装,缺则跳过;frontend job 有,由那里持门跑——
# ci.yml「Ops output-contract gate」步)。本测试不走 env_dep:faux 面零网络
# 零凭证零花费,不符合 pytest.ini 对 env_dep 的定义。
pytestmark = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("node", "bash", "git", "rg", "flock"))
    or not (REPO_ROOT / "ops" / "node_modules").is_dir(),
    reason="供给面缺位:node/bash/git/rg/flock 或 ops/node_modules(worktree 用 "
           "scripts/worktree-prep.sh 拷齐;CI 的 backend job 不装,frontend job 持门跑)",
)


@pytest.fixture
def rounds():
    """被测模块(轮侧:spawn_round = 后端桥)。"""
    import ipdb._ops_rounds as ops_rounds
    return ops_rounds


@pytest.fixture
def reader():
    """UI 读面模块(GET /api/ops/packages 与 /api/ops/packages/{name} 的函数体)。"""
    import ipdb._ops_read as ops_read
    return ops_read


def _seed_ops_tree(ops_dir):
    """往一棵 ops 树播种判例 + 抑制规则两件夹具(README 配对契约;树目录一并建齐)。"""
    for sub in ("precedents", "rules", "packages"):
        (ops_dir / sub).mkdir(parents=True, exist_ok=True)
    (ops_dir / "precedents" / _PRECEDENT_NAME).write_text(_PRECEDENT_FIXTURE, encoding="utf-8")
    (ops_dir / "rules" / "suppressions.json").write_text(
        json.dumps(_SUPPRESSIONS_FIXTURE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def bridge_sandbox(tmp_path, tmp_path_factory, monkeypatch):
    """隔离 ops 树 + 零网络/零外发世界 + faux 面 shim;返回 stderr 行收集器(list)。"""
    import ipdb._ops_store as ops_store

    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))   # UI 读根 = <tmp>/ops
    # 运营者 shell 的 OPS_*/PI_*/模型 key/出口凭证一律不进沙箱(spawn 白名单会透传它们)
    for name in list(os.environ):
        if name.startswith(("OPS_", "PI_")) or name in (
                "ZAI_CODING_CN_API_KEY", "JINA_API_KEY", "GH_TOKEN", "IP_RADAR_ALERT_URLS"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("OPS_SWEEP_DRY_RUN", "1")             # finding 出口恒 dry-run(零外发)
    # 诱饵:ambient DOCS_ROOT 族三名指向一棵**不是 UI 读根、也不在 $IP_RADAR_DATA_DIR 之下**
    # 的树。桥在工作 → 三名全被 _round_env 覆盖,诱饵不生效;桥断(不注入 / 注错目录)→
    # 轮写进诱饵树,UI 读面空 → 本门红,且断供现场不落进仓内 docs/(主检出 docs/ 是嵌套
    # 判例真源仓)。诱饵树同样播种两件夹具:让「桥断」呈现为 #403 式静默断供(轮全绿
    # 收口、件落别处、UI 读面空),而不是轮在 TRIAGE 早死——本门要抓的正是前者。
    decoy = tmp_path_factory.mktemp("ambient-decoy")
    monkeypatch.setenv("DOCS_ROOT", str(decoy))
    monkeypatch.setenv("PRECEDENTS_DIR", str(decoy / "ops" / "precedents"))
    monkeypatch.setenv("LEDGER_FILE", str(decoy / "ops" / "ledger.md"))

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    curl = stubs / "curl"
    curl.write_text(_CURL_STUB, encoding="utf-8")
    curl.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}")

    _seed_ops_tree(ops_store.ops_root())
    _seed_ops_tree(decoy / "ops")

    shim = tmp_path / "faux-pipeline.sh"
    shim.write_text(FAUX_PIPELINE_SHIM, encoding="utf-8")
    monkeypatch.setenv("IP_RADAR_OPS_AGENT_CMD", f"bash {shlex.quote(str(shim))}")
    return []


def _diagnose(head, result, logs, reader, rounds):
    """红面诊断(只在失败路径调用):信封 + 桥注入值对拍 UI 读根 + 读面/诱饵清单 + stderr 尾。"""
    import ipdb._ops_store as ops_store

    lines = [head, f"轮次信封: {json.dumps(result, ensure_ascii=False)[:1200]}"]
    err = result.get("error")
    if isinstance(err, dict) and err.get("code") == "sandbox_violation":
        lines.append("提示: 运营树 backend/ 或 frontend/ 有未提交改动 —— 轮内 sandbox_assert "
                     "红线按设计判轮失败(非产出契约缺陷);先提交再跑。")
    try:
        bridge_docs_root = rounds._spawn_env().get("DOCS_ROOT")
    except Exception as e:  # 诊断面尽力而为(如 agent 配置坏文件)
        bridge_docs_root = f"(读取失败: {e!r})"
    ui_root = ops_store.ops_root()
    lines.append(f"桥注入子进程 DOCS_ROOT = {bridge_docs_root!r};UI 读面根 ops_root() = "
                 f"{str(ui_root)!r}(契约: DOCS_ROOT == ops_root().parent)")
    lines.append(f"UI 读面 list_packages() = {[p['name'] for p in reader.list_packages()]}")
    decoy_packages = Path(os.environ.get("DOCS_ROOT", "")) / "ops" / "packages"
    decoy_names = sorted(p.name for p in decoy_packages.glob("*.md")) if decoy_packages.is_dir() else []
    lines.append(f"诱饵 ambient DOCS_ROOT 下 packages = {decoy_names}(非空 = 桥断,报告件落错树)")
    lines.append("stderr 尾: " + " | ".join(logs[-12:]))
    return "\n".join(lines)


def test_health_round_close_publishes_report_to_ui_read_face(bridge_sandbox, rounds, reader):
    """UI 健康轮经后端桥真跑到 CLOSE → UI 读面 list_packages/read_package 必有本轮报告件。"""
    logs = bridge_sandbox
    # shim 诚实性:它只许比产品缺省命令体多一个 --fixtures——缺省 argv 改版而 shim 没跟,
    # 本门测的就不再是 UI 健康轮的真宿主命令(当场红,不许静默漂移)。
    assert " ".join(rounds._DEFAULT_HEALTH_CMD) == HEALTH_CMD_BODY, (
        "spawn 契约 health 缺省命令已改版,shim(HEALTH_CMD_BODY)须同步:"
        f"{rounds._DEFAULT_HEALTH_CMD!r}")
    assert reader.list_packages() == [], "沙箱起点必须零报告件(否则在场断言空洞)"

    result = rounds.spawn_round("health", ROUND_INPUT, on_log=logs.append)

    stages = (result.get("pipeline") or {}).get("stages") or []
    closed = bool(stages) and stages[-1]["name"] == "CLOSE" and stages[-1]["status"] == "done"
    if result.get("ok") is not True or not closed:
        pytest.fail(_diagnose("轮未走到 CLOSE 成功(门的前提不成立;非产出契约本身的红)",
                              result, logs, reader, rounds))
    round_id = result["pipeline"]["round_id"]
    m = _ROUND_ID_RE.fullmatch(round_id)
    if m is None:
        pytest.fail(f"round_id 形状非 <date>-<HHMM>-health: {round_id!r}")
    expected = f"{m[1]}-health-{m[2]}.md"   # reportNameOf 命名契约(独立真源抄录)
    published = [p["name"] for p in reader.list_packages()]
    if expected not in published:
        pytest.fail(_diagnose(f"轮已 CLOSE 成功,但 UI 读面缺本轮报告件(期望 {expected})",
                              result, logs, reader, rounds))
    body = reader.read_package(expected)
    assert round_id in body, (
        f"UI 读面读到的 {expected} 不含本轮 round_id {round_id!r}(件与本轮不同源)")
