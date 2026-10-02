from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.main import mount_frontend


def _app(tmp_path, with_index=True):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("console.log(1)")
    if with_index:
        (dist / "index.html").write_text("<html>SPA</html>")
    (tmp_path / "secret.txt").write_text("top secret")
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app, mount_frontend(app, dist)


def test_no_index_means_api_only(tmp_path):
    _, mounted = _app(tmp_path, with_index=False)
    assert mounted is False


def test_spa_routes_assets_and_priority(tmp_path):
    app, mounted = _app(tmp_path)
    assert mounted
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}                 # API route keeps priority
    assert "SPA" in c.get("/").text and "SPA" in c.get("/investigator").text
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/v1/unknown").status_code == 404                      # unknown API path is not index.html


def test_path_traversal_is_blocked(tmp_path):
    app, _ = _app(tmp_path)
    c = TestClient(app)
    r = c.get("/..%2fsecret.txt")
    assert "top secret" not in r.text
    assert "top secret" not in c.get("/../secret.txt").text
