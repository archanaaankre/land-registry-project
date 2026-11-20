"""Admin audit event persistence and guard integration tests (SQLite)."""

import os
import secrets

import pytest

from app import create_app, db
from app.auth.audit import (
    EVENT_USER_ACTIVATED,
    EVENT_USER_CREATED,
    EVENT_USER_DEACTIVATED,
    EVENT_USER_ROLE_CHANGED,
    DatabaseAdminAuditRecorder,
    build_admin_audit_event,
)
from app.auth.errors import AuthorizationError, ResourceConflictError
from app.auth.user_management import AdminUserService
from app.config import Config
from app.models import Role
from app.persistence.models import AdminAuditEventModel
from app.persistence.repositories import SqlAlchemyUserRepository


@pytest.fixture
def app(tmp_path):
    database_url = (
        "sqlite:///" + str(tmp_path / "admin-audit.db").replace("\\", "/")
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
        application.config["AUTH_USER_REPOSITORY"] = SqlAlchemyUserRepository()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def repository(app):
    return app.config["AUTH_USER_REPOSITORY"]


def _seed_user(repository, email, role):
    return repository.create_user(
        name=role.value.title(),
        email=email,
        password_hash="hashed password",
        role=role,
    )


def _audit_events():
    rows = db.session.execute(db.select(AdminAuditEventModel)).scalars().all()
    return [row.to_domain() for row in rows]


def test_user_management_records_audit_events(app, repository):
    service = AdminUserService(repository)
    with app.app_context():
        admin = _seed_user(repository, "admin@example.com", Role.ADMIN)
        user = _seed_user(repository, "auditee@example.com", Role.REGISTRAR)

        service.update_role(
            user.id,
            {"role": "CITIZEN"},
            actor_id=admin.id,
            actor_role=Role.ADMIN,
        )
        service.update_status(
            user.id,
            {"is_active": False},
            actor_id=admin.id,
            actor_role=Role.ADMIN,
        )
        service.update_status(
            user.id,
            {"is_active": True},
            actor_id=admin.id,
            actor_role=Role.ADMIN,
        )
        events = _audit_events()

    assert {event.event_type for event in events} == {
        EVENT_USER_ROLE_CHANGED,
        EVENT_USER_DEACTIVATED,
        EVENT_USER_ACTIVATED,
    }
    role_changed = next(
        e for e in events if e.event_type == EVENT_USER_ROLE_CHANGED
    )
    assert role_changed.actor_id == admin.id
    assert role_changed.actor_role == Role.ADMIN
    assert role_changed.target_user_id == user.id
    assert role_changed.detail["from_role"] == "REGISTRAR"
    assert role_changed.detail["to_role"] == "CITIZEN"
    for event in events:
        if event.event_type != EVENT_USER_ROLE_CHANGED:
            assert event.actor_id == admin.id
            assert event.target_user_id == user.id


def test_create_user_records_audit_event(app, repository):
    service = AdminUserService(repository)
    with app.app_context():
        admin = _seed_user(repository, "admin@example.com", Role.ADMIN)
        service.create_user(
            {
                "name": "New User",
                "email": "new@example.com",
                "password": "valid test password",
                "role": "REGISTRAR",
            },
            actor_id=admin.id,
            actor_role=Role.ADMIN,
        )
        events = _audit_events()
    assert len(events) == 1
    event = events[0]
    assert event.event_type == EVENT_USER_CREATED
    assert event.actor_id == admin.id
    assert event.actor_role == Role.ADMIN
    assert event.target_user_id == "user-new-example-com"
    assert event.detail["to_role"] == "REGISTRAR"


def test_audit_rows_never_contain_secrets(app, repository):
    service = AdminUserService(repository)
    secret_password = "a very secret password"
    with app.app_context():
        service.create_user(
            {
                "name": "New User",
                "email": "new@example.com",
                "password": secret_password,
                "role": "REGISTRAR",
            },
            actor_id="admin-1",
            actor_role=Role.ADMIN,
        )
        events = _audit_events()
    assert events
    blob = str([event.to_safe_dict() for event in events])
    assert secret_password not in blob
    assert "password_hash" not in blob
    for event in events:
        assert set(event.detail) <= {"from_role", "to_role", "role"}


def test_admin_deactivation_blocked_for_self(app, repository):
    service = AdminUserService(repository)
    with app.app_context():
        admin = _seed_user(repository, "admin@example.com", Role.ADMIN)
        other_admin = _seed_user(repository, "other@example.com", Role.ADMIN)

        # With another active admin present, self-deactivation is blocked.
        with pytest.raises(AuthorizationError):
            service.update_status(
                admin.id,
                {"is_active": False},
                actor_id=admin.id,
                actor_role=Role.ADMIN,
            )
        assert repository.get_user_by_id(admin.id).is_active is True

        # Once it would leave no active admin, the last-active-admin
        # conflict (409) takes precedence.
        service.update_status(
            other_admin.id,
            {"is_active": False},
            actor_id=admin.id,
            actor_role=Role.ADMIN,
        )
        with pytest.raises(ResourceConflictError):
            service.update_status(
                admin.id,
                {"is_active": False},
                actor_id=admin.id,
                actor_role=Role.ADMIN,
            )
        assert repository.get_user_by_id(admin.id).is_active is True


def test_last_active_admin_protection_via_service(app, repository):
    service = AdminUserService(repository)
    with app.app_context():
        admin_a = _seed_user(repository, "a@example.com", Role.ADMIN)
        admin_b = _seed_user(repository, "b@example.com", Role.ADMIN)

        # Self-deactivation is blocked for admins.
        with pytest.raises(AuthorizationError):
            service.update_status(
                admin_a.id,
                {"is_active": False},
                actor_id=admin_a.id,
                actor_role=Role.ADMIN,
            )

        # Deactivate the other admin while admin_a remains (allowed).
        service.update_status(
            admin_b.id,
            {"is_active": False},
            actor_id=admin_a.id,
            actor_role=Role.ADMIN,
        )

        # With only admin_a active, further removal is blocked.
        with pytest.raises(ResourceConflictError):
            service.update_status(
                admin_a.id,
                {"is_active": False},
                actor_id=admin_b.id,
                actor_role=Role.ADMIN,
            )
        with pytest.raises(ResourceConflictError):
            service.update_role(
                admin_a.id,
                {"role": "REGISTRAR"},
                actor_id=admin_b.id,
                actor_role=Role.ADMIN,
            )

        assert repository.get_user_by_id(admin_a.id).is_active is True
        assert repository.get_user_by_id(admin_a.id).role == Role.ADMIN
        assert repository.get_user_by_id(admin_b.id).is_active is False


def test_audit_insert_failure_rolls_back_mutation(app, repository, monkeypatch):
    from app.persistence import repositories as repositories_module

    def _boom(event):
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(repositories_module, "_admin_audit_event_model", _boom)
    service = AdminUserService(repository)
    with app.app_context():
        admin = _seed_user(repository, "admin@example.com", Role.ADMIN)
        user = _seed_user(repository, "auditee@example.com", Role.REGISTRAR)
        with pytest.raises(RuntimeError):
            service.update_role(
                user.id,
                {"role": "CITIZEN"},
                actor_id=admin.id,
                actor_role=Role.ADMIN,
            )
        assert repository.get_user_by_id(user.id).role == Role.REGISTRAR
        assert _audit_events() == []


def test_build_admin_audit_event_rejects_unknown_types():
    with pytest.raises(ValueError):
        build_admin_audit_event(
            "NOT_A_REAL_EVENT",
            actor_id="admin-1",
            actor_role=Role.ADMIN,
            target_user_id="user-1",
        )


def test_database_recorder_is_marker():
    event = build_admin_audit_event(
        EVENT_USER_CREATED,
        actor_id="admin-1",
        actor_role=Role.ADMIN,
        target_user_id="user-1",
    )
    with pytest.raises(RuntimeError):
        DatabaseAdminAuditRecorder().record(event)
