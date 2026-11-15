import pytest

from app import create_app
from app.config import Config

HEALTH_OK_BODY = {"status": "ok", "service": "land-registry-backend"}
HEALTH_UNAVAILABLE_BODY = {
    "status": "unavailable",
    "service": "land-registry-backend",
}


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Client factory using an explicit database URL.

    Health now checks the database, so tests must not depend on whatever
    DATABASE_URL the surrounding environment happens to configure. The default
    is a local SQLite file; the SELECT 1 probe needs no tables or migrations.
    """

    def _make_client(database_url=None):
        if database_url is None:
            database_url = "sqlite:///" + str(tmp_path / "health.db").replace(
                "\\", "/"
            )
        monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", database_url)
        app = create_app()
        app.config["TESTING"] = True
        return app.test_client()

    return _make_client


def test_health(make_client):
    response = make_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == HEALTH_OK_BODY


def test_health_reports_database_unavailable_without_internal_details(
    make_client, tmp_path
):
    # A SQLite URL under a directory that does not exist fails to connect the
    # way a stopped database server does, without any network dependency.
    unreachable_url = "sqlite:///" + str(
        tmp_path / "missing-directory" / "absent.db"
    ).replace("\\", "/")

    response = make_client(unreachable_url).get("/api/health")

    assert response.status_code == 503
    assert response.get_json() == HEALTH_UNAVAILABLE_BODY
    # Exact-shape assertion above already forbids extra keys; double-check the
    # raw payload never carries SQL, driver, or exception text.
    body_text = response.get_data(as_text=True)
    for internal_detail in ("SELECT", "sqlite", "Traceback", "OperationalError"):
        assert internal_detail not in body_text


def test_health_allows_local_vite_frontend_origin(make_client):
    response = make_client().get(
        "/api/health", headers={"Origin": "http://localhost:5173"}
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
def test_post_preflight_allows_local_vite_origin_and_required_headers(
    make_client, origin
):
    response = make_client().options(
        "/api/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert set(response.headers["Access-Control-Allow-Methods"].split(", ")) == {
        "GET",
        "POST",
        "PATCH",
        "OPTIONS",
    }
    assert {
        header.strip().lower()
        for header in response.headers["Access-Control-Allow-Headers"].split(",")
    } == {"authorization", "content-type"}


def test_preflight_does_not_allow_unconfigured_origin(make_client):
    response = make_client().options(
        "/api/auth/login",
        headers={
            "Origin": "http://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Methods" not in response.headers
    assert "Access-Control-Allow-Headers" not in response.headers


def test_health_does_not_allow_unconfigured_origin(make_client):
    response = make_client().get("/api/health", headers={"Origin": "http://example.com"})

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
