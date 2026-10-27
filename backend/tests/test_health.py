import pytest

from app import create_app


def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_health():
    c = client()
    response = c.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "land-registry-backend"}


def test_health_allows_local_vite_frontend_origin():
    response = client().get(
        "/api/health", headers={"Origin": "http://localhost:5173"}
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
def test_post_preflight_allows_local_vite_origin_and_required_headers(origin):
    response = client().options(
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
        "OPTIONS",
    }
    assert {
        header.strip().lower()
        for header in response.headers["Access-Control-Allow-Headers"].split(",")
    } == {"authorization", "content-type"}


def test_preflight_does_not_allow_unconfigured_origin():
    response = client().options(
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


def test_health_does_not_allow_unconfigured_origin():
    response = client().get("/api/health", headers={"Origin": "http://example.com"})

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
