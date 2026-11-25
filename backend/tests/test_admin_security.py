"""Tests for admin user-management hardening.

Covers: role-assignment allowlist, self-deactivation protection,
last-active-admin protection, and admin audit logging. Admin endpoints are
exercised through the HTTP API with an in-memory user repository so existing
route/auth behavior is preserved.
"""

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app import create_app
from app.auth.api_service import AuthApiService
from app.auth.audit import (
    EVENT_USER_ACTIVATED,
    EVENT_USER_CREATED,
    EVENT_USER_DEACTIVATED,
    EVENT_USER_ROLE_CHANGED,
    InMemoryAdminAuditRecorder,
    LoggingAdminAuditRecorder,
)
from app.auth.errors import ResourceConflictError
from app.auth.service import create_access_token
from app.models import Role, User


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY="test-secret-key-for-admin-hardening",
    )
    return application


@pytest.fixture
def repo():
    return InMemoryUserRepository(
        [
            make_user("admin-1", Role.ADMIN, name="Root Admin"),
            make_user("admin-2", Role.ADMIN, name="Second Admin"),
            make_user("citizen-1", Role.CITIZEN, name="Asha Rao"),
            make_user("registrar-1", Role.REGISTRAR, name="Ravi Registrar"),
        ]
    )


@pytest.fixture
def recorder():
    return InMemoryAdminAuditRecorder()


@pytest.fixture
def client(app, repo, recorder):
    app.extensions["auth_api_service"] = AuthApiService(
        repo, audit_recorder=recorder
    )
    return app.test_client()


def make_user(user_id, role, *, name="Test User", is_active=True, email=None):
    now = datetime.now(timezone.utc)
    return User(
        id=user_id,
        email=email or f"{user_id}@example.com",
        password_hash=f"hash-{user_id}",
        role=role,
        name=name,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def admin_token(app, user_id="admin-1", role=Role.ADMIN):
    return create_access_token(user_id, role, app.config["JWT_SECRET_KEY"])


def auth_headers(app, user_id="admin-1", role=Role.ADMIN):
    return {"Authorization": f"Bearer {admin_token(app, user_id, role)}"}


class InMemoryUserRepository:
    """List-backed fake implementing the UserRepository protocol."""

    def __init__(self, users=()):
        self._users = {user.id: user for user in users}
        self.audit_events = []

    def create_user(self, *, name, email, password_hash, role, audit_event_factory=None):
        now = datetime.now(timezone.utc)
        user = User(
            id=f"user-{len(self._users) + 1}",
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
            role=Role(role),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._users[user.id] = user
        if audit_event_factory is not None:
            self.audit_events.append(audit_event_factory(user.id))
        return user

    def get_user_by_email(self, email):
        normalized = email.strip().lower()
        for user in self._users.values():
            if user.email == normalized:
                return user
        return None

    def get_user_by_id(self, user_id):
        return self._users.get(user_id)

    def list_users(self, *, search=None, role=None, is_active=None):
        users = list(self._users.values())
        if search:
            pattern = search.lower()
            users = [
                user
                for user in users
                if pattern in user.name.lower() or pattern in user.email.lower()
            ]
        if role is not None:
            users = [user for user in users if user.role == Role(role)]
        if is_active is not None:
            users = [user for user in users if user.is_active == is_active]
        return sorted(users, key=lambda user: (user.id, user.email))

    def update_user_role(self, user_id, role):
        user = self._users.get(user_id)
        if user is None:
            from app.auth.errors import ResourceNotFoundError

            raise ResourceNotFoundError("User was not found.")
        updated = replace(user, role=Role(role), updated_at=datetime.now(timezone.utc))
        self._users[user_id] = updated
        return updated

    def update_user_role_with_admin_guard(self, user_id, role, audit_event_factory=None):
        from app.auth.errors import ResourceConflictError, ResourceNotFoundError

        user = self._users.get(user_id)
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        if user.role == Role.ADMIN and user.is_active and Role(role) != Role.ADMIN:
            remaining = [
                other
                for other in self._users.values()
                if other.role == Role.ADMIN
                and other.is_active
                and other.id != user.id
            ]
            if not remaining:
                raise ResourceConflictError(
                    "This change would leave the system without an active admin."
                )
        updated = self.update_user_role(user_id, role)
        if audit_event_factory is not None:
            self.audit_events.append(audit_event_factory(user_id))
        return updated

    def update_user_active_status(self, user_id, is_active):
        user = self._users.get(user_id)
        if user is None:
            from app.auth.errors import ResourceNotFoundError

            raise ResourceNotFoundError("User was not found.")
        updated = replace(
            user, is_active=bool(is_active), updated_at=datetime.now(timezone.utc)
        )
        self._users[user_id] = updated
        return updated

    def update_user_active_status_with_admin_guard(self, user_id, is_active, audit_event_factory=None):
        from app.auth.errors import ResourceConflictError, ResourceNotFoundError

        user = self._users.get(user_id)
        if user is None:
            raise ResourceNotFoundError("User was not found.")
        if not is_active and user.role == Role.ADMIN and user.is_active:
            remaining = [
                other
                for other in self._users.values()
                if other.role == Role.ADMIN
                and other.is_active
                and other.id != user.id
            ]
            if not remaining:
                raise ResourceConflictError(
                    "This change would leave the system without an active admin."
                )
        updated = self.update_user_active_status(user_id, is_active)
        if audit_event_factory is not None:
            self.audit_events.append(audit_event_factory(user_id))
        return updated


# --- Role assignment protection -------------------------------------------------


@pytest.mark.parametrize("new_role", ["CITIZEN", "REGISTRAR", "VERIFICATION_OFFICER"])
def test_admin_can_assign_allowlisted_role(app, client, repo, new_role):
    response = client.patch(
        "/api/admin/users/citizen-1/role",
        json={"role": new_role},
        headers=auth_headers(app),
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == new_role
    assert repo.get_user_by_id("citizen-1").role == Role(new_role)


def test_assigning_admin_role_is_forbidden(app, client, repo, recorder):
    response = client.patch(
        "/api/admin/users/citizen-1/role",
        json={"role": "ADMIN"},
        headers=auth_headers(app),
    )

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "admin_promotion_not_allowed"
    assert repo.get_user_by_id("citizen-1").role == Role.CITIZEN
    assert recorder.events == []


def test_creating_user_with_admin_role_is_rejected(app, client, repo, recorder):
    response = client.post(
        "/api/admin/users",
        json={
            "name": "Mallory",
            "email": "mallory@example.com",
            "password": "a secure password",
            "role": "ADMIN",
        },
        headers=auth_headers(app),
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "unsupported_role"
    assert repo.get_user_by_email("mallory@example.com") is None
    assert recorder.events == []


@pytest.mark.parametrize("role", ["REGISTRAR", "VERIFICATION_OFFICER"])
def test_admin_can_create_privileged_users(app, client, recorder, role):
    response = client.post(
        "/api/admin/users",
        json={
            "name": "New Hire",
            "email": "hire@example.com",
            "password": "a secure password",
            "role": role,
        },
        headers=auth_headers(app),
    )

    assert response.status_code == 201
    assert response.get_json()["user"]["role"] == role
    created = [e for e in recorder.events if e.event_type == EVENT_USER_CREATED]
    assert len(created) == 1
    assert created[0].detail == {"role": role}


def test_role_change_to_unknown_user_returns_404(app, client):
    response = client.patch(
        "/api/admin/users/missing-user/role",
        json={"role": "REGISTRAR"},
        headers=auth_headers(app),
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


# --- Self-deactivation protection ------------------------------------------------


def test_admin_cannot_deactivate_own_account(app, client, repo, recorder):
    response = client.patch(
        "/api/admin/users/admin-1/status",
        json={"is_active": False},
        headers=auth_headers(app, "admin-1"),
    )

    assert response.status_code == 403
    assert repo.get_user_by_id("admin-1").is_active is True
    assert recorder.events == []


def test_admin_cannot_deactivate_self_even_with_another_active_admin(
    app, client, repo, recorder
):
    response = client.patch(
        "/api/admin/users/admin-1/status",
        json={"is_active": False},
        headers=auth_headers(app, "admin-1"),
    )

    assert response.status_code == 403
    assert repo.get_user_by_id("admin-1").is_active is True
    assert repo.get_user_by_id("admin-2").is_active is True
    assert recorder.events == []


def test_admin_can_deactivate_another_admin_when_one_remains(
    app, client, repo, recorder
):
    response = client.patch(
        "/api/admin/users/admin-2/status",
        json={"is_active": False},
        headers=auth_headers(app, "admin-1"),
    )

    assert response.status_code == 200
    assert response.get_json()["user"]["is_active"] is False
    assert repo.get_user_by_id("admin-2").is_active is False


# --- Last-active-admin protection -------------------------------------------------


def test_last_active_admin_cannot_demote_self(app, client, repo, recorder):
    repo._users["admin-2"] = replace(repo._users["admin-2"], is_active=False)

    response = client.patch(
        "/api/admin/users/admin-1/role",
        json={"role": "CITIZEN"},
        headers=auth_headers(app, "admin-1"),
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"
    assert repo.get_user_by_id("admin-1").role == Role.ADMIN
    assert recorder.events == []


def test_admin_can_demote_self_when_another_active_admin_remains(
    app, client, repo
):
    response = client.patch(
        "/api/admin/users/admin-1/role",
        json={"role": "REGISTRAR"},
        headers=auth_headers(app, "admin-1"),
    )

    assert response.status_code == 200
    assert repo.get_user_by_id("admin-1").role == Role.REGISTRAR


def test_last_active_admin_cannot_be_deactivated_inactive_actor(
    app, client, repo, recorder
):
    # An inactive admin's JWT still passes the role guard, so the service must
    # independently enforce the last-active-admin rule.
    repo._users["admin-2"] = replace(repo._users["admin-2"], is_active=False)

    response = client.patch(
        "/api/admin/users/admin-1/status",
        json={"is_active": False},
        headers=auth_headers(app, "admin-2"),
    )

    assert response.status_code == 403
    assert repo.get_user_by_id("admin-1").is_active is True
    assert recorder.events == []


def test_last_active_admin_cannot_be_deactivated_service_level(
    app, repo, recorder
):
    repo._users["admin-2"] = replace(repo._users["admin-2"], is_active=False)
    service = AuthApiService(repo, audit_recorder=recorder)

    with pytest.raises(ResourceConflictError):
        service.update_user_active_status(
            "admin-1", False, actor_id="system-actor", actor_role=Role.ADMIN
        )

    assert repo.get_user_by_id("admin-1").is_active is True
    assert recorder.events == []


def test_last_active_admin_cannot_be_demoted_service_level(app, repo, recorder):
    repo._users["admin-2"] = replace(repo._users["admin-2"], is_active=False)
    service = AuthApiService(repo, audit_recorder=recorder)

    with pytest.raises(ResourceConflictError):
        service.update_user_role(
            "admin-1", Role.CITIZEN, actor_id="system-actor", actor_role=Role.ADMIN
        )

    assert repo.get_user_by_id("admin-1").role == Role.ADMIN
    assert recorder.events == []


def test_deactivating_last_active_admin_allowed_when_other_active_admin(
    app, client, repo
):
    # admin-2 deactivates admin-1; admin-2 remains active.
    response = client.patch(
        "/api/admin/users/admin-1/status",
        json={"is_active": False},
        headers=auth_headers(app, "admin-2"),
    )

    assert response.status_code == 200
    assert repo.get_user_by_id("admin-1").is_active is False


def test_reactivated_admin_restores_protection_invariant(app, client, repo):
    client.patch(
        "/api/admin/users/admin-2/status",
        json={"is_active": False},
        headers=auth_headers(app, "admin-1"),
    )
    response = client.patch(
        "/api/admin/users/admin-2/status",
        json={"is_active": True},
        headers=auth_headers(app, "admin-1"),
    )

    assert response.status_code == 200
    assert repo.get_user_by_id("admin-2").is_active is True


# --- Audit logging ----------------------------------------------------------------


def test_admin_actions_record_audit_events(app, client, recorder):
    create_response = client.post(
        "/api/admin/users",
        json={
            "name": "New Hire",
            "email": "hire@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        },
        headers=auth_headers(app),
    )
    assert create_response.status_code == 201
    created_id = create_response.get_json()["user"]["id"]

    client.patch(
        f"/api/admin/users/{created_id}/role",
        json={"role": "VERIFICATION_OFFICER"},
        headers=auth_headers(app),
    )
    client.patch(
        f"/api/admin/users/{created_id}/status",
        json={"is_active": False},
        headers=auth_headers(app),
    )
    client.patch(
        f"/api/admin/users/{created_id}/status",
        json={"is_active": True},
        headers=auth_headers(app),
    )

    event_types = [event.event_type for event in recorder.events]
    assert event_types == [
        EVENT_USER_CREATED,
        EVENT_USER_ROLE_CHANGED,
        EVENT_USER_DEACTIVATED,
        EVENT_USER_ACTIVATED,
    ]

    created, role_changed, deactivated, activated = recorder.events
    assert created.actor_id == "admin-1"
    assert created.actor_role == Role.ADMIN
    assert created.target_user_id == created_id
    assert created.detail == {"role": "REGISTRAR"}

    assert role_changed.detail == {
        "from_role": "REGISTRAR",
        "to_role": "VERIFICATION_OFFICER",
    }
    assert role_changed.target_user_id == created_id

    assert deactivated.detail == {"is_active": False}
    assert activated.detail == {"is_active": True}


def test_audit_events_never_contain_sensitive_data(app, client, recorder):
    client.post(
        "/api/admin/users",
        json={
            "name": "Secret Keeper",
            "email": "secret@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        },
        headers=auth_headers(app),
    )
    created_id = recorder.events[0].target_user_id
    client.patch(
        f"/api/admin/users/{created_id}/role",
        json={"role": "CITIZEN"},
        headers=auth_headers(app),
    )

    serialized = json.dumps(
        [event.to_safe_dict() for event in recorder.events]
    ).lower()
    for forbidden in (
        "a secure password",
        "password",
        "hash",
        "secret@example.com",
        "token",
        "jwt",
        "authorization",
    ):
        assert forbidden not in serialized


def test_logging_recorder_emits_structured_event(app, caplog):
    repo = InMemoryUserRepository([make_user("admin-1", Role.ADMIN)])
    service = AuthApiService(
        repo, audit_recorder=LoggingAdminAuditRecorder()
    )  # logging sink is opt-in for isolated tests/development

    import logging

    with caplog.at_level(logging.INFO, logger="app.audit.admin"):
        service.create_admin_user(
            {
                "name": "Logged Hire",
                "email": "logged@example.com",
                "password": "a secure password",
                "role": "REGISTRAR",
            },
            actor_id="admin-1",
            actor_role=Role.ADMIN,
        )

    audit_lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "app.audit.admin"
    ]
    assert audit_lines, "expected an audit log record"
    payload = json.loads(audit_lines[-1].split(" ", 1)[1])
    assert payload["event_type"] == EVENT_USER_CREATED
    assert payload["actor_id"] == "admin-1"
    assert payload["detail"] == {"role": "REGISTRAR"}
    assert "password" not in audit_lines[-1].lower()
    assert "logged@example.com" not in audit_lines[-1]


def test_no_audit_event_for_noop_changes(app, client, recorder):
    client.patch(
        "/api/admin/users/citizen-1/role",
        json={"role": "CITIZEN"},
        headers=auth_headers(app),
    )
    client.patch(
        "/api/admin/users/citizen-1/status",
        json={"is_active": True},
        headers=auth_headers(app),
    )

    assert recorder.events == []


# --- Existing admin functionality (regression) -------------------------------------


def test_admin_list_users_returns_users_with_timestamps(app, client):
    response = client.get("/api/admin/users", headers=auth_headers(app))

    assert response.status_code == 200
    users = response.get_json()["users"]
    assert {user["id"] for user in users} >= {
        "admin-1",
        "admin-2",
        "citizen-1",
        "registrar-1",
    }
    for user in users:
        assert user["created_at"] is not None
        assert "password" not in user and "password_hash" not in user


def test_admin_list_users_filters_by_role_and_status(app, client):
    response = client.get(
        "/api/admin/users?role=CITIZEN", headers=auth_headers(app)
    )
    assert response.status_code == 200
    assert {user["id"] for user in response.get_json()["users"]} == {"citizen-1"}

    response = client.get(
        "/api/admin/users?is_active=false", headers=auth_headers(app)
    )
    assert response.status_code == 200
    assert response.get_json()["users"] == []


def test_admin_stats_still_works(app, client):
    response = client.get("/api/admin/stats", headers=auth_headers(app))

    assert response.status_code == 200
    body = response.get_json()
    assert body["users"]["total"] == 4
    assert body["users"]["by_role"]["ADMIN"] == 2
    assert body["users"]["by_role"]["CITIZEN"] == 1


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/admin/users", "get"),
        ("/api/admin/users", "post"),
        ("/api/admin/users/citizen-1/role", "patch"),
        ("/api/admin/users/citizen-1/status", "patch"),
        ("/api/admin/stats", "get"),
    ],
)
def test_admin_endpoints_reject_non_admin_roles(app, client, path, method):
    kwargs = {"headers": auth_headers(app, "citizen-1", Role.CITIZEN)}
    if method == "post":
        kwargs["json"] = {
            "name": "Nope",
            "email": "nope@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        }
    elif method == "patch":
        kwargs["json"] = (
            {"role": "REGISTRAR"} if path.endswith("/role") else {"is_active": False}
        )
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_admin_endpoints_reject_missing_token(client):
    response = client.get("/api/admin/users")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "missing_authentication"
