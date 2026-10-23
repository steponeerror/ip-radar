"""P1 待审条目库(票 #153,TDD 红先行)。

钉住 spec #152 §1 条目库契约(独立真源 = spec 十字段冻结与闭集字面,不从
被测模块导入常量,防套套逻辑):

- 一条一文件:十字段 frontmatter(id/action/args/evidence/impact/rollback/
  dedup_key/severity/cause_group/status)+ 人读摘要正文;文件名日期前缀 +
  item + 内容寻址摘要;
- 幂等不双开:dedup_key=(source, probe_class, error_signature) 语义键,同
  key 在飞(active/snoozed)零写返回既有条目;
- 复开链指:同 key 终态复开 = 新条目 supersedes 指旧条,原条目永不删
  (判例 superseded_by 同思想);
- 状态机:active|snoozed|done|dismissed;终态外迁拒绝;状态变更只改
  frontmatter status 行,正文永不改(哲学①证据不灭失);
- 坏文件显式报错不静默跳过(无证据≠清白);
- 判例 schema 扩展:可选 item_id 缺省合法(旧判例零改动照常通过),
  write_ruling 产物零变化;
- 列表排序:active 先见 → severity 降序 → cause_group 升序 → 新条目先见;
- 路由:GET /api/ops/items 与 /{id} 只读面(admin 门);审阅四键 = T3 面外。
"""

import re
from datetime import date
from pathlib import Path

import pytest
import yaml

# ── 独立真源字面(spec #152 §1)──
TEN_FIELDS = [
    "id", "action", "args", "evidence", "impact",
    "rollback", "dedup_key", "severity", "cause_group", "status",
]
STATUSES = ("active", "snoozed", "done", "dismissed")
SEVERITY_ORDER = ("high", "medium", "low")
DEDUP_KEYS = ("source", "probe_class", "error_signature")
ITEM_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-item-[0-9a-f]{10}\.md$")

SUMMARY = (
    "# 待审:源 spamhaus_drop 连续下载失败\n\n"
    "连续 3 轮 failed,末次 error_code=HTTP 403;建议重试下载,"
    "失败画像与谱系见 evidence。\n"
)


@pytest.fixture
def items():
    """被测模块(RED 相位 = 模块不存在,逐测试失败而非收集错误;P1/P3 同型)。"""
    import ipdb._ops_items as ops_items
    return ops_items


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    """ops 树落 tmp:IP_RADAR_DATA_DIR 指隔离目录,不碰真 data/。"""
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    return tmp_path


def _mk(**over):
    """create_item 参数默认包;dedup 三元组默认 source=spamhaus_drop。"""
    kw = dict(
        source="spamhaus_drop", probe_class="download_failure",
        error_signature="http_403_anonymous",
        action="retry_download", args={"source": "spamhaus_drop"},
        evidence={"consecutive_failures": 3, "error_code": "HTTP 403"},
        impact="spamhaus_drop 数据停更,威胁覆盖面收缩",
        rollback="重新启用/重试下载即可,无不可逆变更",
        severity="high", cause_group="download_failure",
        summary=SUMMARY, today=date(2026, 10, 23),
    )
    kw.update(over)
    return kw


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: 缺 frontmatter 起始围栏"
    end = text.find("\n---\n", 4)
    assert end != -1, f"{path.name}: frontmatter 未闭合"
    return yaml.safe_load(text[4:end])


def _body_text(path: Path) -> str:
    """围栏闭合行 + 空行之后的正文全文（逐字；判例 _render 同款形状）。"""
    text = path.read_text(encoding="utf-8")
    marker = "\n---\n\n"
    end = text.find(marker, 4)
    assert end != -1
    return text[end + len(marker):]


def _item_files(ops_env):
    return sorted((ops_env / "ops" / "items").glob("*.md"))


# ── A. 存储层:create/幂等/复开链指/状态机/排序 ────────────────────────


def test_item_create_ten_fields_and_body(items, ops_env):
    """首产:恰十字段冻结、status=active、id=文件名 stem、正文逐字。"""
    res = items.create_item(**_mk())
    assert res == {"created": True, "item": res["item"], "supersedes": None}
    assert ITEM_NAME_RE.match(f"{res['item']}.md"), res["item"]
    files = _item_files(ops_env)
    assert len(files) == 1 and files[0].stem == res["item"]
    fm = _parse_frontmatter(files[0])
    assert set(fm) == set(TEN_FIELDS), "冻结十字段之外不得私加字段"
    assert fm["id"] == files[0].stem
    assert fm["status"] == "active"
    assert fm["dedup_key"] == {
        "source": "spamhaus_drop", "probe_class": "download_failure",
        "error_signature": "http_403_anonymous"}
    assert fm["args"] == {"source": "spamhaus_drop"}
    assert _body_text(files[0]) == SUMMARY  # 正文 = 人读摘要逐字


def test_item_dedup_same_key_in_flight_no_double_open(items, ops_env):
    """同 key 在飞(active)不双开:二次产条零写、文件字节不变;跨日、
    换 action/args/severity 也一样 —— 幂等键是语义三元组,不是内容。"""
    r1 = items.create_item(**_mk())
    before = [(p.name, p.read_bytes()) for p in _item_files(ops_env)]
    r2 = items.create_item(**_mk(today=date(2026, 10, 24)))
    r3 = items.create_item(**_mk(action="disable_source", severity="low",
                                 today=date(2026, 10, 25)))
    for r in (r2, r3):
        assert r == {"created": False, "item": r1["item"], "supersedes": None}
    assert [(p.name, p.read_bytes()) for p in _item_files(ops_env)] == before


def test_item_dedup_snoozed_counts_in_flight(items, ops_env):
    """snoozed 仍在飞:同 key 不双开(spec「在飞」含稍后态)。"""
    r1 = items.create_item(**_mk())
    items.set_status(r1["item"], "snoozed")
    r2 = items.create_item(**_mk(today=date(2026, 11, 1)))
    assert r2["created"] is False and r2["item"] == r1["item"]
    assert len(_item_files(ops_env)) == 1


def test_item_different_key_opens_second(items, ops_env):
    """不同语义键(换 probe_class)= 不同因,开第二条;不同源同理。"""
    items.create_item(**_mk())
    res = items.create_item(**_mk(probe_class="stale_content",
                                  error_signature="age_gt_2x_refresh",
                                  severity="medium", today=date(2026, 10, 23)))
    assert res["created"] is True
    assert len(_item_files(ops_env)) == 2


def test_item_reopen_after_done_chains_supersedes(items, ops_env):
    """复开链指:done 后同 key 复开 = 新条目 supersedes 指旧条;旧条目
    永不删、status 仍 done;新条目 = 冻结十 + supersedes。"""
    r1 = items.create_item(**_mk())
    items.set_status(r1["item"], "done")
    r2 = items.create_item(**_mk(today=date(2026, 10, 24)))
    assert r2["created"] is True and r2["supersedes"] == r1["item"]
    files = {p.stem: p for p in _item_files(ops_env)}
    assert set(files) == {r1["item"], r2["item"]}, "原条目永不删"
    assert _parse_frontmatter(files[r1["item"]])["status"] == "done"
    fm2 = _parse_frontmatter(files[r2["item"]])
    assert set(fm2) == set(TEN_FIELDS) | {"supersedes"}
    assert fm2["supersedes"] == r1["item"]
    assert fm2["status"] == "active"


def test_item_reopen_after_dismissed_chains_supersedes(items, ops_env):
    """dismissed 终态复开同律:链指旧条,不就地复活。"""
    r1 = items.create_item(**_mk())
    items.set_status(r1["item"], "dismissed")
    r2 = items.create_item(**_mk(today=date(2026, 10, 24)))
    assert r2["created"] is True and r2["supersedes"] == r1["item"]
    assert _parse_frontmatter(
        {p.stem: p for p in _item_files(ops_env)}[r1["item"]])["status"] == "dismissed"


def test_item_reopen_chain_extends_not_collides(items, ops_env):
    """连环复开:第二条在飞期间同 key 仍不双开;第二条终态后第三次复开
    链指第二条(链不繁殖回环)。"""
    r1 = items.create_item(**_mk())
    items.set_status(r1["item"], "done")
    r2 = items.create_item(**_mk(today=date(2026, 10, 24)))
    # r2 在飞:同 key 再产 = 返回 r2
    assert items.create_item(**_mk(today=date(2026, 10, 24)))["item"] == r2["item"]
    items.set_status(r2["item"], "done")
    r3 = items.create_item(**_mk(today=date(2026, 10, 24)))  # 同日连环复开
    assert r3["created"] is True and r3["supersedes"] == r2["item"]
    assert len(_item_files(ops_env)) == 3, "同日连环复开不撞名"


@pytest.mark.parametrize("sig", ["http_403_anonymous", "age_gt_2x_refresh"])
def test_item_same_day_reopen_chain_no_overwrite(items, ops_env, sig):
    """同日三次同 key 事件回归(review Finding 1):latest 须按 mtime 取链头,
    不能按文件名序 —— 同日文件名倒序退化为摘要 hex 序,旧实现下第三次产条
    会链指 r1、摘要与 r2 撞名、静默覆写 r2 终态字节。两组签名各钉一种
    hex 序(http_403_anonymous: D1<D2 旧实现碰巧不炸;age_gt_2x_refresh:
    D1>D2 旧实现必炸 —— 撘 D1=28b5e5a138/D2=bb1d50ccae 与
    D1=c3145a1e68/D2=a679bfe510 实测序)。"""
    r1 = items.create_item(**_mk(error_signature=sig))
    items.set_status(r1["item"], "done")
    r2 = items.create_item(**_mk(error_signature=sig))  # 同日复开一
    items.set_status(r2["item"], "done")
    r3 = items.create_item(**_mk(error_signature=sig))  # 同日复开二
    assert r3["created"] is True and r3["supersedes"] == r2["item"]
    files = {p.stem: p for p in _item_files(ops_env)}
    assert set(files) == {r1["item"], r2["item"], r3["item"]}, \
        "三个事件 = 三份文件,无一被覆写"
    assert _parse_frontmatter(files[r2["item"]])["status"] == "done", \
        "r2 终态字节不被抹(哲学①证据不灭失)"
    assert _parse_frontmatter(files[r1["item"]])["status"] == "done"
    assert _parse_frontmatter(files[r3["item"]])["supersedes"] == r2["item"]


@pytest.mark.parametrize("path", [
    ("active", "snoozed"), ("active", "done"), ("active", "dismissed"),
    ("snoozed", "active"), ("snoozed", "done"), ("snoozed", "dismissed"),
])
def test_item_status_legal_transitions_body_immutable(items, ops_env, path):
    """合法迁移集:审阅四键目标态;只改 frontmatter status 行,正文与
    其余字段字节不变(哲学①证据不灭失)。"""
    old, new = path
    r = items.create_item(**_mk())
    if old == "snoozed":
        items.set_status(r["item"], "snoozed")
    p = {q.stem: q for q in _item_files(ops_env)}[r["item"]]
    before_body = _body_text(p)
    before_fm = _parse_frontmatter(p)
    res = items.set_status(r["item"], new)
    assert res["changed"] is True and res["from"] == old and res["to"] == new
    after_fm = _parse_frontmatter(p)
    after_fm.pop("status"), before_fm.pop("status")
    assert after_fm == before_fm, "除 status 外 frontmatter 逐字不变"
    assert _body_text(p) == before_body, "正文永不改"


@pytest.mark.parametrize("path", [
    ("done", "active"), ("done", "snoozed"), ("done", "dismissed"),
    ("dismissed", "active"), ("dismissed", "snoozed"), ("dismissed", "done"),
])
def test_item_status_terminal_rejected(items, ops_env, path):
    """终态外迁一律拒绝(复开 = 新条目链指,非就地迁移);文件零改动。"""
    old, new = path
    r = items.create_item(**_mk())
    items.set_status(r["item"], old)
    p = {q.stem: q for q in _item_files(ops_env)}[r["item"]]
    before = p.read_bytes()
    with pytest.raises(ValueError, match="非法迁移"):
        items.set_status(r["item"], new)
    assert p.read_bytes() == before


def test_item_same_status_idempotent_zero_write(items, ops_env):
    """同态重置 = 幂等零写(changed=False,字节不变)。"""
    r = items.create_item(**_mk())
    p = {q.stem: q for q in _item_files(ops_env)}[r["item"]]
    before = p.read_bytes()
    res = items.set_status(r["item"], "active")
    assert res == {"item": r["item"], "from": "active", "to": "active",
                   "changed": False}
    assert p.read_bytes() == before


@pytest.mark.parametrize("over", [
    {"severity": "urgent"},                    # 闭集外
    {"evidence": {}},                          # 无证据即无话
    {"args": "source=spamhaus_drop"},          # 非映射
    {"source": "Bad-Source"},                  # 源名形状非法
    {"impact": "  "},                          # 空后果
    {"rollback": ""},                          # 空回滚
    {"summary": ""},                           # 空正文
    {"probe_class": ""},                       # 空键分量
])
def test_item_validation_rejects_before_any_write(items, ops_env, over):
    """校验全在写前:失败 = items/ 零文件(write_ruling 同律)。"""
    with pytest.raises(ValueError):
        items.create_item(**_mk(**over))
    idir = ops_env / "ops" / "items"
    assert not idir.exists() or list(idir.glob("*.md")) == []


def test_item_filename_and_lookup_rejections(items, ops_env):
    """文件名形状/不存在:read_item 拒路径分隔与点前缀(validate_ops_filename
    同律),未知条目显式 404 语义(FileNotFoundError 不伪装空)。"""
    items.create_item(**_mk())
    with pytest.raises(ValueError):
        items.read_item("../evil")
    with pytest.raises(ValueError):
        items.read_item(".hidden")
    with pytest.raises(FileNotFoundError):
        items.read_item("2026-10-23-item-0000000000")
    with pytest.raises(FileNotFoundError):
        items.set_status("2026-10-23-item-0000000000", "done")
    with pytest.raises(ValueError):
        items.set_status("whatever", "not_a_status")  # 闭集外状态先拒


def test_item_corrupt_file_explicit_error(items, ops_env):
    """坏文件显式报错不静默跳过:列表与产条扫描都被拦下(无证据≠清白)。"""
    items.create_item(**_mk())
    idir = ops_env / "ops" / "items"
    (idir / "2026-01-01-item-deadbeef01.md").write_text(
        "---\nid: broken\n---\n缺字段的伪条目\n", encoding="utf-8")
    with pytest.raises(ValueError, match="deadbeef01"):
        items.list_items()
    with pytest.raises(ValueError, match="deadbeef01"):
        items.create_item(**_mk(source="other_src", probe_class="stale_content",
                                error_signature="age_gt_2x_refresh"))


def test_item_list_sorting(items, ops_env):
    """列表序:active 先见 → severity 降序 → cause_group 升序 → 同组新
    条目先见;后随 snoozed/done/dismissed。"""
    a = items.create_item(**_mk(error_signature="k1", cause_group="zz_group"))
    b = items.create_item(**_mk(source="other_src", error_signature="k2",
                                cause_group="aa_group"))
    c = items.create_item(**_mk(source="third_src", error_signature="k3",
                                cause_group="aa_group", severity="low"))
    d = items.create_item(**_mk(source="fourth_src", error_signature="k4",
                                cause_group="aa_group", today=date(2026, 10, 22)))
    e = items.create_item(**_mk(source="fifth_src", error_signature="k5"))
    f = items.create_item(**_mk(source="sixth_src", error_signature="k6"))
    g = items.create_item(**_mk(source="seventh_src", error_signature="k7",
                                severity="low"))
    items.set_status(e["item"], "snoozed")
    items.set_status(f["item"], "done")
    items.set_status(g["item"], "dismissed")
    got = [it["id"] for it in items.list_items()]
    # b/d 同 (active,high,aa_group):b(10-23)新于 d(10-22)先见;
    # a 因 cause_group=zz_group 排 aa_group 之后;c=low 排 high 之后
    assert got == [b["item"], d["item"], a["item"], c["item"],
                   e["item"], f["item"], g["item"]]


def test_item_list_fields_modified(items, ops_env):
    """列表项 = frontmatter 全字段 + modified(ISO-UTC)。"""
    r = items.create_item(**_mk())
    out = items.list_items()
    assert len(out) == 1
    it = out[0]
    assert set(TEN_FIELDS) <= set(it)
    assert it["id"] == r["item"] and it["status"] == "active"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", it["modified"])


# ── B. 判例 schema 扩展(item_id 可选缺省;写回四律零改动)─────────────


def _mk_pkg(ops_env, name="2026-10-20-discover-1030.md"):
    pdir = ops_env / "ops" / "packages"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / name).write_text("# 裁决包\n\n## 建议\n\n- 候选……\n", encoding="utf-8")
    return pdir / name


def test_precedent_validator_item_id_optional():
    """item_id 缺省合法(旧判例零改动照常通过);有则非空字符串;类型坏拒。"""
    import ipdb._ops_store as ops_store
    fm = {
        "id": "x", "date": date(2026, 10, 23), "subject": "s", "context": "c",
        "recommendation": "r", "human_ruling": "h",
        "reward": {"hard_gates": {"package": "ops/packages/p.md"},
                   "ruling_agreement": "agreed", "production_delta": None},
        "lineage": ["ops/packages/p.md"], "superseded_by": None,
    }
    ops_store.validate_precedent_entry(fm)                      # 缺省合法
    fm["item_id"] = "2026-10-23-item-0123456789"
    ops_store.validate_precedent_entry(fm)                      # 携带合法
    for bad in ("", "   ", 123):
        fm["item_id"] = bad
        with pytest.raises(ValueError, match="item_id"):
            ops_store.validate_precedent_entry(fm)


def test_ruling_output_zero_change_no_item_id(ops_env):
    """write_ruling 零改动:产物 frontmatter 无 item_id、往返过校验
    (旧判例文件零改动照常通过的写侧证明)。"""
    import ipdb._ops_store as ops_store
    _mk_pkg(ops_env)
    res = ops_store.write_ruling("2026-10-20-discover-1030.md",
                                 "ENQUEUE a_src — 理由", "agreed",
                                 today=date(2026, 10, 23))
    pfile = ops_env / "ops" / "precedents" / res["precedent"]
    fm = _parse_frontmatter(pfile)
    assert "item_id" not in fm, "write_ruling 不得私加 item_id(T3 才携带)"
    ops_store.validate_precedent_entry(fm)  # 往返解析照常通过


# ── C. 路由层(GET /api/ops/items 只读面;admin 门)─────────────────────


@pytest.fixture
def admin_env(ops_env, auth_env):
    """路由测试面:ops 树 + admin 认证。"""
    return ops_env


def test_items_route_requires_admin(admin_env, auth_client):
    assert auth_client.get("/api/ops/items").status_code == 401
    assert auth_client.get("/api/ops/items/x").status_code == 401


def test_items_route_forbidden_for_non_superuser(admin_env, auth_client):
    import asyncio
    from fastapi_users.password import PasswordHelper
    from ipdb import _auth

    async def _mk_peon():
        async with _auth._session_maker()() as s:
            s.add(_auth.User(email="peon9@ipradar.local",
                             hashed_password=PasswordHelper().hash("peon-pass-123"),
                             is_superuser=False, is_active=True))
            await s.commit()

    asyncio.run(_mk_peon())
    assert auth_client.post("/api/auth/jwt/login", data={
        "username": "peon9@ipradar.local", "password": "peon-pass-123"}).status_code == 204
    assert auth_client.get("/api/ops/items").status_code == 403
    assert auth_client.get("/api/ops/items").json()["error"]["code"] == "forbidden"


def test_items_route_empty_list_is_truth(admin_env, client_as_admin):
    """空库 = 空列表(空是真实态,不 404;_ops_read 同判例)。"""
    r = client_as_admin.get("/api/ops/items")
    assert r.status_code == 200 and r.json() == {"items": []}


def test_items_route_list_sorted_full_fields(admin_env, client_as_admin, items):
    low = items.create_item(**_mk(source="low_src", error_signature="k-low",
                                  severity="low"))
    high = items.create_item(**_mk(source="high_src", error_signature="k-high"))
    r = client_as_admin.get("/api/ops/items")
    assert r.status_code == 200
    got = r.json()["items"]
    assert [it["id"] for it in got] == [high["item"], low["item"]]
    it = got[0]
    for field in TEN_FIELDS:
        assert field in it, f"列表项缺冻结字段 {field}"
    assert it["dedup_key"]["source"] == "high_src"
    assert "modified" in it


def test_items_route_detail_full_text(admin_env, client_as_admin, items):
    r = items.create_item(**_mk())
    resp = client_as_admin.get(f"/api/ops/items/{r['item']}")
    assert resp.status_code == 200
    text = resp.json()["text"]
    assert text == (admin_env / "ops" / "items" / f"{r['item']}.md").read_text(
        encoding="utf-8")
    assert SUMMARY in text


def test_items_route_detail_unknown_404_and_bad_shape_422(
        admin_env, client_as_admin):
    r = client_as_admin.get("/api/ops/items/2026-10-23-item-0000000000")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    r = client_as_admin.get("/api/ops/items/.hidden")
    assert r.status_code == 422
