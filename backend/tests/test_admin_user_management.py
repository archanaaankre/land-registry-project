import os
import secrets

import pytest

from app import create_app, db
from app.config import Config
from app.auth.service import create_access_token, hash_password
from app.models import Role
from app.persistence.repositories import SqlAlchemyUserRepository


@pytest.fixture
def app(tmp_path):
    database_url = (
        "sqlite:///" + str(tmp_path / "admin-users.db").replace("\\", "/")
    )
    previous_database_url = os.environ.get("DATABASE_URL")
    previous_config_database_url = Config.SQLALCHEMY_DATABASE_URI
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    try:
        application = create_app()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        Config.SQLALCHEMY_DATABASE_URI = previous_config_database_url
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with application.app_context():
        db.create_all()
        repository = SqlAlchemyUserRepository()
        admin = repository.create_user(
            name="Admin User",
            email="admin@example.com",
            password_hash=hash_password("admin password"),
            role=Role.ADMIN,
        )
        application.config["AUTH_USER_REPOSITORY"] = repository
        application.config["PARCEL_REPOSITORY"] = None
        application.config["TRANSFER_REPOSITORY"] = None
        application.config["OWNERSHIP_REPOSITORY"] = None
    application.config["ADMIN_TEST_USER_ID"] = admin.id
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def bearer(app, user_id, role):
    token = create_access_token(
        user_id, role, app.config["JWT_SECRET_KEY"]
    )
    return {"Authorization": "Bearer " + token}


def make_user(app, email, role, *, is_active=True):
    repository = app.config["AUTH_USER_REPOSITORY"]
    with app.app_context():
        user = repository.create_user(
            name=role.value.title(),
            email=email,
            password_hash=hash_password("valid test password"),
            role=role,
        )
        if not is_active:
            repository.update_user_status(user.id, False)
        return user


def admin_headers(app):
    return bearer(app, app.config["ADMIN_TEST_USER_ID"], Role.ADMIN)


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "POST",
            "/api/admin/users",
            {
                "name": "New Registrar",
                "email": "new-registrar@example.com",
                "password": "a sufficiently long password",
                "role": "REGISTRAR",
            },
        ),
        ("GET", "/api/admin/users", None),
        ("GET", "/api/admin/users/{user_id}", None),
        (
            "PATCH",
            "/api/admin/users/{user_id}/role",
            {"role": "REGISTRAR"},
        ),
        (
            "PATCH",
            "/api/admin/users/{user_id}/status",
            {"is_active": False},
        ),
    ],
)
def test_admin_endpoints_require_authentication(
    app, client, method, path, payload
):
    path = path.format(user_id=app.config["ADMIN_TEST_USER_ID"])

    response = client.open(path, method=method, json=payload)

    assert response.status_code == 401
    assert response.get_json() == {
        "error": {
            "code": "missing_authentication",
            "message": "Authentication is required.",
        }
    }


@pytest.mark.parametrize(
    "role", [Role.CITIZEN, Role.REGISTRAR, Role.VERIFICATION_OFFICER]
)
def test_non_admin_cannot_access_any_admin_endpoint(app, client, role):
    user = make_user(app, role.value.lower() + "@example.com", role)
    headers = bearer(app, user.id, role)
    paths = [
        ("POST", "/api/admin/users", {"name": "New", "email": "new@example.com",
                                      "password": "a secure password",
                                      "role": "REGISTRAR"}),
        ("GET", "/api/admin/users", None),
        ("GET", "/api/admin/users/" + user.id, None),
        ("PATCH", "/api/admin/users/" + user.id + "/role", {"role": "CITIZEN"}),
        ("PATCH", "/api/admin/users/" + user.id + "/status", {"is_active": False}),
    ]

    for method, path, payload in paths:
        response = client.open(
            path,
            method=method,
            json=payload,
            headers=headers,
        )
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("role", ["REGISTRAR", "VERIFICATION_OFFICER"])
def test_admin_can_create_privileged_accounts_without_exposing_hash(
    app, client, role
):
    response = client.post(
        "/api/admin/users",
        headers=admin_headers(app),
        json={
            "name": "New Officer",
            "email": role.lower() + "@example.com",
            "password": "a sufficiently long password",
            "role": role,
        },
    )

    assert response.status_code == 201
    user = response.get_json()["user"]
    assert user["role"] == role
    assert user["is_active"] is True
    assert "password" not in str(response.get_json()).lower()
    assert "hash" not in str(response.get_json()).lower()


@pytest.mark.parametrize("role", ["CITIZEN", "ADMIN", "INVALID"])
def test_admin_user_creation_rejects_disallowed_roles(app, client, role):
    response = client.post(
        "/api/admin/users",
        headers=admin_headers(app),
        json={
            "name": "Not Allowed",
            "email": "not-allowed@example.com",
            "password": "a sufficiently long password",
            "role": role,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "unsupported_role"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"name": " ", "email": "new@example.com", "password": "long enough",
         "role": "REGISTRAR"},
        {"name": "New", "email": "invalid", "password": "long enough",
         "role": "REGISTRAR"},
        {"name": "New", "email": "new@example.com", "password": "short",
         "role": "REGISTRAR"},
    ],
)
def test_admin_user_creation_validates_request_body(app, client, payload):
    response = client.post(
        "/api/admin/users", headers=admin_headers(app), json=payload
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_input"


def test_admin_can_list_users_and_filter_by_role_and_active_status(app, client):
    registrar = make_user(app, "registrar@example.com", Role.REGISTRAR)
    inactive = make_user(
        app, "inactive@example.com", Role.VERIFICATION_OFFICER, is_active=False
    )

    all_users = client.get("/api/admin/users", headers=admin_headers(app))
    by_role = client.get(
        "/api/admin/users?role=REGISTRAR", headers=admin_headers(app)
    )
    by_status = client.get(
        "/api/admin/users?is_active=false", headers=admin_headers(app)
    )

    assert all_users.status_code == 200
    assert {user["id"] for user in all_users.get_json()["items"]} == {
        app.config["ADMIN_TEST_USER_ID"],
        registrar.id,
        inactive.id,
    }
    assert [user["id"] for user in by_role.get_json()["items"]] == [registrar.id]
    assert [user["id"] for user in by_status.get_json()["items"]] == [inactive.id]
    for response in (all_users, by_role, by_status):
        assert "password_hash" not in str(response.get_json())
        assert "hash" not in str(response.get_json()).lower()


@pytest.mark.parametrize(
    "query", ["role=UNKNOWN", "is_active=perhaps"]
)
def test_admin_user_list_rejects_invalid_filters(app, client, query):
    response = client.get(
        "/api/admin/users?" + query, headers=admin_headers(app)
    )

    assert response.status_code == 400


def test_admin_can_get_safe_user_details_and_missing_user_is_404(app, client):
    user = make_user(app, "details@example.com", Role.REGISTRAR)

    response = client.get(
        "/api/admin/users/" + user.id, headers=admin_headers(app)
    )
    missing = client.get(
        "/api/admin/users/missing", headers=admin_headers(app)
    )

    assert response.status_code == 200
    assert response.get_json()["user"] == {
        "id": user.id,
        "name": "Registrar",
        "email": "details@example.com",
        "role": "REGISTRAR",
        "is_active": True,
    }
    assert "hash" not in str(response.get_json()).lower()
    assert missing.status_code == 404


def test_admin_role_change_immediately_updates_old_token_authorization(app, client):
    user = make_user(app, "role-change@example.com", Role.CITIZEN)
    old_headers = bearer(app, user.id, Role.CITIZEN)

    denied_before = client.get("/api/registrar/transfers", headers=old_headers)
    changed = client.patch(
        "/api/admin/users/" + user.id + "/role",
        headers=admin_headers(app),
        json={"role": "REGISTRAR"},
    )
    denied_after = client.get("/api/registrar/transfers", headers=old_headers)

    assert changed.status_code == 200
    assert changed.get_json()["user"]["role"] == "REGISTRAR"
    assert denied_before.status_code == 403
    assert denied_after.status_code == 503


@pytest.mark.parametrize("role", [Role.CITIZEN, Role.REGISTRAR])
def test_admin_cannot_promote_existing_user_to_admin(app, client, role):
    user = make_user(app, role.value.lower() + "-promotion@example.com", role)

    response = client.patch(
        "/api/admin/users/" + user.id + "/role",
        headers=admin_headers(app),
        json={"role": "ADMIN"},
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "admin_promotion_not_allowed"
    assert response.get_json()["error"]["message"] == (
        "Admins cannot promote users to the ADMIN role."
    )
    with app.app_context():
        unchanged_user = app.config["AUTH_USER_REPOSITORY"].get_user_by_id(user.id)
    assert unchanged_user.role is role


def test_admin_deactivation_immediately_blocks_old_token(app, client):
    user = make_user(app, "deactivate@example.com", Role.CITIZEN)
    old_headers = bearer(app, user.id, Role.CITIZEN)

    response = client.patch(
        "/api/admin/users/" + user.id + "/status",
        headers=admin_headers(app),
        json={"is_active": False},
    )
    blocked = client.get("/api/auth/me", headers=old_headers)

    assert response.status_code == 200
    assert response.get_json()["user"]["is_active"] is False
    assert blocked.status_code == 401


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/role", {"role": "CITIZEN"}),
        ("/status", {"is_active": False}),
    ],
)
def test_last_active_admin_cannot_be_demoted_or_deactivated(
    app, client, path, payload
):
    admin_id = app.config["ADMIN_TEST_USER_ID"]

    response = client.patch(
        "/api/admin/users" + "/" + admin_id + path,
        headers=admin_headers(app),
        json=payload,
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"
    with app.app_context():
        admin = app.config["AUTH_USER_REPOSITORY"].get_user_by_id(admin_id)
    assert admin.role is Role.ADMIN
    assert admin.is_active is True


def test_admin_role_update_rejects_invalid_body_and_unknown_user(app, client):
    headers = admin_headers(app)
    invalid = client.patch(
        "/api/admin/users/missing/role", headers=headers, json={"role": "INVALID"}
    )
    malformed = client.patch(
        "/api/admin/users/missing/role", headers=headers, json=[]
    )
    missing = client.patch(
        "/api/admin/users/missing/role", headers=headers, json={"role": "CITIZEN"}
    )

    assert invalid.status_code == 400
    assert malformed.status_code == 400
    assert missing.status_code == 404


def test_admin_status_update_requires_boolean_and_existing_user(app, client):
    headers = admin_headers(app)
    invalid = client.patch(
        "/api/admin/users/missing/status",
        headers=headers,
        json={"is_active": "false"},
    )
    missing = client.patch(
        "/api/admin/users/missing/status",
        headers=headers,
        json={"is_active": False},
    )

    assert invalid.status_code == 400
    assert missing.status_code == 404
