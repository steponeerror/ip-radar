# 票 #149 验收截屏脚本:档案 + 裁决两子 tab 全页(台账统一表/判例行元数据/
# 节头计数/「暂无」空态/裁决包行元数据)。纯前端 mock 面(共享骨架 =
# ops_screenshot_common),不起后端。产出工作树根两工件(不提交,报告
# 路径);--empty 变体另出空态对照图(硬规⑥验收面)。
import sys
from pathlib import Path

from ops_screenshot_common import PKGS, VERSION, build_handle_api, open_admin, serve_dist, sync_playwright

PORT = 4179
EMPTY = "--empty" in sys.argv
SUFFIX = "-empty" if EMPTY else ""
OUT_ARCHIVE = Path(__file__).resolve().parents[1] / f"ops-archive-t149{SUFFIX}.png"
OUT_RULINGS = Path(__file__).resolve().parents[1] / f"ops-rulings-t149{SUFFIX}.png"

# 判例夹具:文件名日期前缀(行相对时间源)+ 无日期名(不显时间对照)
PRECEDENTS = [
    "2026-10-19-ustc-myip-incremental-queue-signoff.md",
    "2026-10-19-threatview-sunset-dead-feed.md",
    "2026-10-18-sblam-s3-honeypot-methodology.md",
    "2026-10-18-firehol-webserver-unsubscribe.md",
    "2026-10-18-cps-snapshot-paradox.md",
    "2026-10-17-cloudzy-asset-axis-hosting.md",
    "2026-10-17-ziyadnz-aggregator-misjudge.md",
]

# 空态变体(--empty):台账仅标题行 + 判例/包全空(硬规⑥对照图);
# 满态变体:判例库七篇 + 裁决包四件(行元数据/计数验收面)
if EMPTY:
    OVERRIDES = {
        "/version": {**VERSION, "current": "g149-mock"},
        "/ops/ledger": {"text": "# 运营轮次台账\n"},
        "/ops/packages": {"packages": []},
        "/ops/precedents": {"precedents": []},
    }
else:
    OVERRIDES = {
        "/version": {**VERSION, "current": "g149-mock"},
        "/ops/packages": {"packages": PKGS},
        "/ops/precedents": {"precedents": PRECEDENTS},
    }
handle_api = build_handle_api(OVERRIDES)

httpd = serve_dist(PORT)
with sync_playwright() as p:
    browser, page = open_admin(p, PORT, handle_api)
    # 档案子 tab:台账表 + 判例库
    page.get_by_role("tab", name="档案").click(timeout=5000)
    page.wait_for_timeout(400)  # 相对时间渲染稳定
    body_text = page.inner_text("body")
    if EMPTY:
        assert "暂无台账记录" in body_text, "台账空态未渲染:" + body_text[:600]
        assert "暂无判例" in body_text, "判例空态未渲染:" + body_text[:600]
        assert "(5)" not in body_text.split("档案", 1)[-1], "空表不应显计数"
    else:
        assert "台账 (5)" in body_text, "台账计数未渲染:" + body_text[:600]
        assert "判例库 (7)" in body_text, "判例计数未渲染:" + body_text[:600]
        assert "天前" in body_text, "判例行相对时间未渲染:" + body_text[:600]
        assert "只读审计面" in body_text, "只读副注未渲染:" + body_text[:600]
        assert "（只读）" not in body_text, "「(只读)」仍在标题"
    page.screenshot(path=str(OUT_ARCHIVE), full_page=True)
    print("saved:", OUT_ARCHIVE)

    # 裁决子 tab:裁决包列表
    page.get_by_role("tab", name="裁决").click(timeout=5000)
    page.wait_for_timeout(400)
    body_text = page.inner_text("body")
    if EMPTY:
        assert "暂无裁决包" in body_text, "裁决包空态未渲染:" + body_text[:600]
    else:
        assert "裁决包 (4)" in body_text, "裁决包计数未渲染:" + body_text[:600]
        assert "小时前" in body_text or "分钟前" in body_text or "天前" in body_text, "包行相对时间未渲染"
    page.screenshot(path=str(OUT_RULINGS), full_page=True)
    print("saved:", OUT_RULINGS)
    browser.close()
httpd.shutdown()
