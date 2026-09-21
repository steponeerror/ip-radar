"""SPA fallback: BrowserRouter deep links like /sources must serve index.html on
direct hit / refresh. Without a fallback, StaticFiles(html=True) 404s any path
that isn't a real file (e.g. /sources), so opening or refreshing the Sources
page at /sources breaks with 404."""
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.applications import Starlette

import main


def _hermetic_client(static_root: Path) -> TestClient:
    """Fresh Starlette app serving SpaStaticFiles from a tmp dir — no built
dist/ needed, so these pin the class contract independently of the build."""
    (static_root / "index.html").write_text("INDEX-SHELL")
    (static_root / "admin.html").write_text("ADMIN-SHELL")
    app = Starlette()
    app.mount(
        "/", main.SpaStaticFiles(directory=str(static_root), html=True), name="static"
    )
    return TestClient(app)


def test_client_route_deep_link_serves_index_html():
    client = TestClient(main.app)
    resp = client.get("/sources")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert '<div id="root">' in resp.text


def test_unknown_api_route_still_404s():
    """SPA fallback must not swallow unknown /api/* paths — API clients expect
    a 404, not index.html."""
    client = TestClient(main.app)
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404


def test_real_static_file_served_as_file():
    """Real files (assets, favicon) must still be served with their own
    content type, not collapsed to index.html."""
    client = TestClient(main.app)
    resp = client.get("/favicon.svg")
    assert resp.status_code == 200
    assert not resp.headers["content-type"].startswith("text/html")


def test_extensionless_admin_serves_admin_html(tmp_path: Path):
    """"/admin is a standalone document (MPA entry admin.html), not a hash
    route. Starlette 0.46 html mode resolves only real files and
    dir/index.html — never path+".html" — so SpaStaticFiles must bridge the
    extensionless pretty path to admin.html BEFORE the index.html fallback.
    (Empirically verified against installed starlette: plain StaticFiles 404s
    /admin even when admin.html exists.)"""
    client = _hermetic_client(tmp_path)
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert resp.text == "ADMIN-SHELL"


def test_unknown_path_falls_back_to_index_html(tmp_path: Path):
    """Pretty-path retry must not break the original SPA contract: unknown
    extensionless paths (client-router deep links) still get index.html."""
    client = _hermetic_client(tmp_path)
    resp = client.get("/no-such-page")
    assert resp.status_code == 200
    assert resp.text == "INDEX-SHELL"


def test_api_404_does_not_fall_back(tmp_path: Path):
    """Neither the .html retry nor the SPA fallback may swallow /api/* 404s —
    API clients expect a real 404."""
    client = _hermetic_client(tmp_path)
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.text != "INDEX-SHELL"

