#!/usr/bin/env python
# glm-smoke.py — RRSI×GLM 模型面冒烟(票 #325 交付物 4;花钱上界 <¥0.5,单次小调用)。
# 干什么:经 dev/rrsi/domains/ipradar/adapter.py 的 LiteLLM→zai 垫片(与 #322 真实轮
# 四角色将走的同一代码路径)发起一次真实 glm-5.3-flash 调用,提案者角色迷你任务
# (单假设 JSON,非真实搜索轮——真实轮花钱面归 #322)。
# 凭证链(与 ops/agent/models.mjs 同律,零入仓):env ZAI_CODING_CN_API_KEY →
# auth.json(env OPS_AUTH,缺省 ~/.pi/agent/auth.json)的 zai-coding-cn.key。
# 留痕:stdout 摘要 + dev/glm-smoke-<ts>.json(请求/响应/耗时/token;dev/ 不入 git)。
# 用法:dev/rrsi/.venv/bin/python scripts/glm-smoke.py [--repo <ip-radar 检出>]
#   环境要求:RRSI 克隆在 <repo>/dev/rrsi(litellm 已装其 .venv);python3 ≥3.10。
import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RRSI = REPO / "dev" / "rrsi"
DOMAIN = RRSI / "domains" / "ipradar"
sys.path.insert(0, str(DOMAIN))

MODEL_CANDIDATES = ["zai/glm-5.3-flash", "openai/glm-5.3-flash"]  # litellm 原生 zai 目录优先,openai 兼容面兜底
BASE_URL = os.environ.get("ZAI_CODING_CN_BASE_URL",
                          "https://open.bigmodel.cn/api/coding/paas/v4")

PROMPT = (
    "你是 ip-radar 发现管线的提案者。只做一件事:输出一个 JSON 对象,"
    '形如 {"hypothesis": "<一句话:候选宇宙覆盖类改进假设>", '
    '"target": "<ops/agent-v2 内一个模块路径>", "budget": 1}。'
    "不要任何多余文字。"
)
SYSTEM = "你是 ip-radar 发现管线演化轮的提案者,遵守 PATTERNS.md 宪法。"

def resolve_key() -> tuple[str, str]:
    env_key = os.environ.get("ZAI_CODING_CN_API_KEY")
    if env_key:
        return env_key, "env ZAI_CODING_CN_API_KEY"
    auth_path = Path(os.environ.get("OPS_AUTH",
                                    str(Path.home() / ".pi" / "agent" / "auth.json")))
    entry = json.loads(auth_path.read_text())["zai-coding-cn"]
    return entry["key"], f"auth.json {auth_path} → zai-coding-cn.key(ops 凭证链同源)"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(REPO))
    args = ap.parse_args()
    key, key_src = resolve_key()
    os.environ["ZAI_CODING_CN_API_KEY"] = key
    os.environ["RRSI_LLM_BACKEND"] = "litellm-zai"  # 必须先于 adapter import(adapter 装垫片)
    if not DOMAIN.is_dir():
        sys.exit(f"域未接线:{DOMAIN} 缺——先跑 scripts/bootstrap-rrsi.sh")
    import adapter  # noqa: E402  副作用:装 litellm-zai 垫片(rrsi.llm.generate 被替换)
    if not adapter.SHIM_ON:
        sys.exit("垫片未开:RRSI_LLM_BACKEND 须为 litellm-zai")
    import rrsi.llm as rllm  # noqa: E402

    trials, out = [], None
    for mdl in MODEL_CANDIDATES:
        t0 = time.time()
        try:
            text = rllm.generate(PROMPT, system=SYSTEM, json_only=True,
                                 model=mdl, max_tokens=256)
            parsed = json.loads(text)
            trials.append({"model": mdl, "ok": True, "latency_s": round(time.time() - t0, 2)})
            out = (mdl, text, parsed)
            break
        except Exception as e:  # noqa: BLE001
            trials.append({"model": mdl, "ok": False, "latency_s": round(time.time() - t0, 2),
                           "err": repr(e)[:500]})
    if out is None:
        print(json.dumps({"ok": False, "base_url": BASE_URL, "trials": trials},
                         ensure_ascii=False, indent=1))
        return 1
    mdl, text, parsed = out
    record = {
        "ok": True, "ticket": "#325", "when": dt.datetime.now().isoformat(timespec="seconds"),
        "face": "LiteLLM→zai coding cn,经 adapter.py 垫片(rrsi.llm.generate 替换面)",
        "base_url": BASE_URL, "model": mdl,
        "role": "proposer(提案者迷你任务,单假设 JSON;非真实搜索轮)",
        "key_source": key_src, "latency": [t for t in trials if t["model"] == mdl][0]["latency_s"],
        "trials": trials, "response_json": parsed,
    }
    dst = REPO / "dev"
    dst.mkdir(exist_ok=True)
    path = dst / f"glm-smoke-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1))
    print(json.dumps({k: record[k] for k in ("ok", "model", "base_url", "role",
                                             "key_source", "latency", "response_json")},
                     ensure_ascii=False, indent=1))
    print(f"留痕 → {path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
