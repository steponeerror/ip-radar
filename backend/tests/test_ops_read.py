"""P3 ops 只读 API + 导出(票 #135,TDD 红先行)。

钉住产品化批 Task P3 契约:GET packages(列表/详情)、GET ledger、GET precedents
(+kws 检索走 P1 rg_search_precedents)、GET precedents/export.zip(全量判例+台账);
admin 鉴权沿 P2 _ADMIN_DEPS 惯例;_schema.md 非判例(列表/详情/导出判例口径沿
P1:检索排除、导入随目录携带,导出保持库自描述)。

期望值取自冻结件独立真源(T4 台账表头、种子判例字面),不从被测模块导入常量。
"""

import io
import zipfile
from datetime import date, datetime

import pytest

# T4 lib.sh ledger_append 首建表头(逐字;test_ops_store.py 同源)
LEDGER_HEADER = (
    "# 运营轮次台账\n\n"
    "| 日期 | 轮次 | model | 用量 | 备注 |\n"
    "|---|---|---|---|---|\n"
)

PKG_A = "2026-10-19-health-1716.md"
PKG_B = "2026-10-20-discover-1030.md"
PREC_SUNSET = "2026-10-18-a-case.md"
PREC_MIRROR = "2026-10-19-b-case.md"


@pytest.fixture
def reader():
    """被测模块(RED 相位 = 模块不存在,逐测试失败而非收集错误)。"""
    import ipdb._ops_read as ops_read
    return ops_read


@pytest.fixture
def ops_env(tmp_path, monkeypatch):
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(tmp_path))
    return tmp_path


def _seed_tree(ops_env):
    """两包 + 两判例 + _schema.md + 台账一行的最小 ops 树。"""
    import ipdb._ops_store as ops_store
    root = ops_store.init_ops_tree()
    pdir = root / "packages"
    (pdir / PKG_A).write_text("# 健康轮包\nsunset 冻结 1\n", encoding="utf-8")
    (pdir / PKG_B).write_text("# discover 包\nmirror echo 证据\n", encoding="utf-8")
    prec = root / "precedents"
    (prec / PREC_SUNSET).write_text("---\nid: a\n---\nSunset 冻结判死\n", encoding="utf-8")
    (prec / PREC_MIRROR).write_text("---\nid: b\n---\nmirror echo 判例\n", encoding="utf-8")
    (prec / "_schema.md").write_text("# 判例库 schema\nsunset 字样\n", encoding="utf-8")
    ops_store.append_ledger(round_="health", model="glm-5.3-flash", usage="in=1 out=1",
                            note="probe", today=date(2026, 10, 20))
    return root


# ── A. 读助手(_ops_read)───────────────────────────────────────────────


def test_list_packages_meta_desc(reader, ops_env):
    """包列表:仅 *.md、按名倒序(日期前缀名 = 新包先见)、size/modified 齐全;
    非 md 杂物不进列表。"""
    _seed_tree(ops_env)
    (ops_env / "ops" / "packages" / "notes.txt").write_text("x", encoding="utf-8")
    pkgs = reader.list_packages()
    assert [p["name"] for p in pkgs] == [PKG_B, PKG_A]
    for p in pkgs:
        assert p["size"] == (ops_env / "ops" / "packages" / p["name"]).stat().st_size
        datetime.fromisoformat(p["modified"])  # ISO 可解析
        assert p["modified"].endswith(("Z", "+00:00")) or "T" in p["modified"]


def test_read_package_verbatim_and_missing(reader, ops_env):
    _seed_tree(ops_env)
    text = reader.read_package(PKG_B)
    assert text == "# discover 包\nmirror echo 证据\n"
    with pytest.raises(FileNotFoundError):
        reader.read_package("no-such.md")


def test_package_name_shape_rejected(reader, ops_env):
    """纯文件名校验:路径/点前缀一律拒(防逃出 packages/)。"""
    _seed_tree(ops_env)
    for bad in ("../ledger.md", "a/b.md", ".hidden.md", ".."):
        with pytest.raises(ValueError):
            reader.read_package(bad)
        with pytest.raises(ValueError):
            reader.read_precedent(bad)


def test_read_ledger_text_and_empty_tree(reader, ops_env, monkeypatch):
    """台账全文只读;空树(未跑任何轮)返回表头(init 幂等建头,空是真实态)。"""
    _seed_tree(ops_env)
    ledger = reader.read_ledger()
    assert ledger.startswith(LEDGER_HEADER)
    assert "| 2026-10-20 | health |" in ledger
    # 空树:全新数据根(无 ops 目录)也能读(不炸、表头自建)
    monkeypatch.setenv("IP_RADAR_DATA_DIR", str(ops_env / "fresh"))
    assert reader.read_ledger().startswith(LEDGER_HEADER)


def test_list_precedents_excludes_schema(reader, ops_env):
    _seed_tree(ops_env)
    assert reader.list_precedents() == [PREC_MIRROR, PREC_SUNSET]  # 倒序(新先见)


def test_read_precedent_schema_not_a_precedent(reader, ops_env):
    """_schema.md 非判例(详情口径沿 P1 检索/排除口径);真判例逐字读。"""
    _seed_tree(ops_env)
    assert reader.read_precedent(PREC_SUNSET) == "---\nid: a\n---\nSunset 冻结判死\n"
    with pytest.raises(FileNotFoundError):
        reader.read_precedent("_schema.md")
    with pytest.raises(FileNotFoundError):
        reader.read_precedent("no-such.md")


def test_search_precedents_delegates_rg(reader, ops_env):
    """kws 检索走 P1 rg_search_precedents(OR、大小写不敏感、_schema.md 排除)。"""
    _seed_tree(ops_env)
    assert reader.search_precedents(["sunset"]) == [PREC_SUNSET]
    assert reader.search_precedents(["sunset", "mirror"]) == [
        PREC_MIRROR, PREC_SUNSET]


def test_export_zip_contents_full_precedents_and_ledger(reader, ops_env):
    """导出 zip = 全量判例(含 _schema.md,库自描述沿 P1 导入口径)+ 台账;
    确定性:同树两次导出字节一致(固定 zip 时间戳,无损回算)。"""
    _seed_tree(ops_env)
    data = reader.export_zip_bytes()
    assert reader.export_zip_bytes() == data, "导出须确定性可回算"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = sorted(zf.namelist())
        assert names == sorted([
            f"precedents/{PREC_SUNSET}", f"precedents/{PREC_MIRROR}",
            "precedents/_schema.md", "ledger.md",
        ])
        assert zf.read(f"precedents/{PREC_SUNSET}") == (
            ops_env / "ops" / "precedents" / PREC_SUNSET).read_bytes()
        assert zf.read("ledger.md").decode("utf-8").startswith(LEDGER_HEADER)
        assert zf.testzip() is None


def test_export_zip_empty_tree_has_shape(reader, ops_env):
    """空树导出:判例空目录 + 表头台账(zip 形状在,不是 404)。"""
    data = reader.export_zip_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert sorted(zf.namelist()) == ["ledger.md"]
        assert zf.read("ledger.md").decode("utf-8") == LEDGER_HEADER


# ── B. 路由层(GET 端点;鉴权/形状/404)────────────────────────────────


@pytest.fixture
def admin_env(ops_env, auth_env):
    _seed_tree(ops_env)
    return ops_env


def test_read_routes_require_admin(admin_env, auth_client):
    for path in ("/api/ops/packages", "/api/ops/ledger", "/api/ops/precedents",
                 f"/api/ops/packages/{PKG_B}", f"/api/ops/precedents/{PREC_SUNSET}",
                 "/api/ops/precedents/export.zip"):
        r = auth_client.get(path)
        assert r.status_code == 401, f"{path} 不应匿名可达"
        assert r.json()["error"]["code"] == "unauthorized"


def test_packages_route_shape(admin_env, client_as_admin):
    r = client_as_admin.get("/api/ops/packages")
    assert r.status_code == 200
    pkgs = r.json()["packages"]
    assert [p["name"] for p in pkgs] == [PKG_B, PKG_A]
    assert set(pkgs[0]) >= {"name", "size", "modified"}


def test_package_detail_and_404(admin_env, client_as_admin):
    r = client_as_admin.get(f"/api/ops/packages/{PKG_B}")
    assert r.status_code == 200
    assert r.json()["text"] == "# discover 包\nmirror echo 证据\n"
    r404 = client_as_admin.get("/api/ops/packages/no-such.md")
    assert r404.status_code == 404
    assert r404.json()["error"]["code"] == "not_found"


def test_ledger_route_text(admin_env, client_as_admin):
    r = client_as_admin.get("/api/ops/ledger")
    assert r.status_code == 200
    assert r.json()["text"].startswith(LEDGER_HEADER)


def test_precedents_route_list_and_kws_search(admin_env, client_as_admin):
    """无 kws = 全量列表(倒序,_schema.md 排除);kws = rg 检索命中面。"""
    r = client_as_admin.get("/api/ops/precedents")
    assert r.status_code == 200
    assert r.json()["precedents"] == [PREC_MIRROR, PREC_SUNSET]
    rk = client_as_admin.get("/api/ops/precedents?kws=sunset")
    assert rk.status_code == 200
    assert rk.json()["precedents"] == [PREC_SUNSET]
    rk2 = client_as_admin.get("/api/ops/precedents?kws=sunset,mirror")
    assert rk2.json()["precedents"] == [PREC_MIRROR, PREC_SUNSET]
    # 真零命中(rc=1)是合法空,不是错
    assert client_as_admin.get(
        "/api/ops/precedents?kws=不存在的词").json()["precedents"] == []


def test_precedent_detail_schema_404_and_missing(admin_env, client_as_admin):
    r = client_as_admin.get(f"/api/ops/precedents/{PREC_SUNSET}")
    assert r.status_code == 200
    assert r.json()["text"] == "---\nid: a\n---\nSunset 冻结判死\n"
    assert client_as_admin.get(
        "/api/ops/precedents/_schema.md").status_code == 404  # 非判例口径
    r404 = client_as_admin.get("/api/ops/precedents/no-such.md")
    assert r404.status_code == 404
    assert r404.json()["error"]["code"] == "not_found"


def test_precedents_export_zip_route(admin_env, client_as_admin):
    """export.zip 路由:application/zip + attachment;内容 = 全量判例+台账;
    声明序先于 /{name}(export.zip 不被动态段吞)。"""
    r = client_as_admin.get("/api/ops/precedents/export.zip")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    assert "attachment" in r.headers.get("content-disposition", "")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert sorted(zf.namelist()) == sorted([
            f"precedents/{PREC_SUNSET}", f"precedents/{PREC_MIRROR}",
            "precedents/_schema.md", "ledger.md",
        ])
        assert zf.testzip() is None
