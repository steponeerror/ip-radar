"""P2 e2e:健康轮真跑(node + 真模型 flash,成本 ~$0.001;票 #134 验收
「本地 e2e:健康轮真跑(flash),包+台账落本地 ops 树」)。

skip 门(不满足即 SKIP,绝不 mock 冒充真跑——任务书纪律):
- node 在 PATH(P5 镜像形态;后端 CI runner 无 node);
- zai 凭证可得:ZAI_CODING_CN_API_KEY env 或 agent 侧 models.mjs 三层 upsert
  的 stored credential(~/.pi/agent/auth.json,仓库现有配置惯例)。

真跑链路 = 生产 spawn 路径(无 IP_RADAR_OPS_AGENT_CMD 覆盖):ops 树落 tmp、
真 node 拉 ops/agent/agent.mjs、真 glm-5.3-flash、包/台账经 lib.sh 落 ops 树。
断言面(桥可见的独立真源,不解析信封内部再自证):
- 轮次信封 ok=true(stdout 单行 JSON,成功面);
- 包文件落 <ops_root>/packages/(裁④);
- 台账行落 <ops_root>/ledger.md(agent 侧 lib.sh 记账:model=glm-5.3-flash,
  usage 含 cost>0——九裁决 9 每轮记账)。
"""

import json
import os
import shutil
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def _zai_available() -> bool:
    if os.environ.get("ZAI_CODING_CN_API_KEY", "").strip():
        return True
    auth = Path.home() / ".pi" / "agent" / "auth.json"
    if not auth.exists():
        return False
    try:
        return "zai-coding-cn" in json.loads(auth.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False


pytestmark = [
    pytest.mark.skipif(shutil.which("node") is None,
                       reason="node 不在 PATH(后端 CI runner 无 node;P5 镜像形态才有)"),
    pytest.mark.skipif(not _zai_available(),
                       reason="zai 凭证不可得(env ZAI_CODING_CN_API_KEY 或 ~/.pi/agent/auth.json)"
                              "——任务书:不可得即停,不许 mock 冒充真跑"),
]


@pytest.fixture
def rounds():
    import ipdb._ops_rounds as ops_rounds
    return ops_rounds


def test_health_round_real_run(rounds, tmp_path, monkeypatch):
    """真跑一发健康轮(flash);包+台账落 tmp ops 树。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    assert not os.environ.get("IP_RADAR_OPS_AGENT_CMD"), "e2e 不得覆盖 agent 命令"
    logs: list[str] = []
    result = rounds.spawn_round("health", "对全部离线源做一次健康体检,给出冻结/死键/不可达快照",
                                on_log=logs.append)
    # 轮次信封(成功面;失败面让断言输出完整信封便于诊断)
    assert result.get("ok") is True, result
    pkg = Path(result["pkg"])
    assert pkg.is_file(), f"裁决包未落盘: {pkg}"
    assert pkg.parent == (tmp_path / "ops" / "packages").resolve() or \
        str(tmp_path) in str(pkg), f"包不在 ops 树: {pkg}"
    # 台账:agent 侧 lib.sh 已记(桥成功路径零追加,恰一行)
    ledger = (tmp_path / "ops" / "ledger.md").read_text(encoding="utf-8")
    rows = [ln for ln in ledger.splitlines() if ln.startswith("| 2")]
    assert len(rows) == 1, ledger
    assert "glm-5.3-flash" in rows[0]
    assert "cost=" in rows[0]
    # stderr 进度行透传(契约面:[turn]/[tool] 行)
    assert any(ln.startswith("[turn") for ln in logs), logs
    # usage 面(信封;provider 实报)
    assert result["usage"]["totalTokens"] > 0, result["usage"]
