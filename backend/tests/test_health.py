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


def test_health_does_not_allow_unconfigured_origin():
    response = client().get("/api/health", headers={"Origin": "http://example.com"})

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
