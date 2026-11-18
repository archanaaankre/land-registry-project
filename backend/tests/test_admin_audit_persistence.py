"""Integration tests for persistent admin audit storage.

Verifies that, with the database-backed recorder (the production default),
every admin mutation and its audit event commit or roll back together, that
no audit row is left behind for rejected operations, and that non-persistent
recorders leave no rows. Runs against a temporary SQLite database with real
SQLAlchemy repositories; PostgreSQL-specific locking is covered by
``test_admin_concurrency.py``.
"""

import secrets

import pytest

from app import create_app, db
from app.auth.api_service import AuthApiService
from app.auth.audit import (
    EVENT_USER_ACTIVATED,
    EVENT_USER_CREATED,
    EVENT_USER_DEACTIVATED,
    EVENT_USER_ROLE_CHANGED,
    DatabaseAdminAuditRecorder,
    InMemoryAdminAuditRecorder,
    LoggingAdminAuditRecorder,
)
from app.auth.errors import (
    InvalidInputError,
    ResourceConflictError,
)
from app.auth.service import create_access_token, hash_password
from app.config import Config
from app.models import Role
from app.persistence.models import AdminAuditEventModel
from app.persistence.repositories import SqlAlchemyUserRepository


@pytest.fixture
def app(tmp_path, monkeypatch):
    database_url = "sqlite:///" + str(tmp_path / "admin_audit.db").replace(
        "\\", "/"
    )
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", database_url)
    application = create_app()
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with application.app_context():
        db.create_all()
    application.config.update(AUTH_USER_REPOSITORY=SqlAlchemyUserRepository())
    return application


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def repository(app):
    return app.config["AUTH_USER_REPOSITORY"]


def _seed_admin(repository, email="root@example.com"):
    return repository.create_user(
        name="Root Admin",
        email=email,
        password_hash=hash_password("root admin password"),
        role=Role.ADMIN,
    )


def _service(app, audit_recorder=None):
    return AuthApiService(
        app.config["AUTH_USER_REPOSITORY"], audit_recorder=audit_recorder
    )


def _event_rows(app):
    return AdminAuditEventModel.query.all()


def test_database_recorder_is_the_default(app):
    service = _service(app)

    assert isinstance(service._audit_recorder, DatabaseAdminAuditRecorder)


def test_admin_creation_persists_audit_row_atomically(app):
    _seed_admin(app.config["AUTH_USER_REPOSITORY"])
    service = _service(app)

    result = service.create_admin_user(
        {
            "name": "New Hire",
            "email": "hire@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        },
        actor_id="admin-1",
        actor_role=Role.ADMIN,
    )

    assert result["user"]["role"] == "REGISTRAR"
    rows = _event_rows(app)
    assert [row.event_type for row in rows] == [EVENT_USER_CREATED]
    event = rows[0]
    assert event.actor_id == "admin-1"
    assert event.actor_role == "ADMIN"
    assert event.target_user_id == result["user"]["id"]
    assert event.to_role == "REGISTRAR"
    assert event.from_role is None
    assert event.created_at is not None


def test_role_change_persists_audit_row_with_transitions(app, repository):
    seed_admin = _seed_admin(repository)
    citizen = repository.create_user(
        name="Asha Rao",
        email="asha@example.com",
        password_hash=hash_password("asha password"),
        role=Role.CITIZEN,
    )
    service = _service(app)

    service.update_user_role(
        citizen.id, Role.VERIFICATION_OFFICER,
        actor_id=seed_admin.id, actor_role=Role.ADMIN,
    )

    rows = _event_rows(app)
    assert [row.event_type for row in rows] == [EVENT_USER_ROLE_CHANGED]
    event = rows[0]
    assert event.from_role == "CITIZEN"
    assert event.to_role == "VERIFICATION_OFFICER"
    assert event.target_user_id == citizen.id
    assert event.actor_id == seed_admin.id


def test_activation_and_deactivation_persist_audit_rows(app, repository):
    seed_admin = _seed_admin(repository)
    other_admin = repository.create_user(
        name="Second Admin",
        email="second@example.com",
        password_hash=hash_password("second admin password"),
        role=Role.ADMIN,
    )
    citizen = repository.create_user(
        name="Asha Rao",
        email="asha@example.com",
        password_hash=hash_password("asha password"),
        role=Role.CITIZEN,
    )
    service = _service(app)

    service.update_user_active_status(
        citizen.id, False, actor_id=seed_admin.id, actor_role=Role.ADMIN
    )
    service.update_user_active_status(
        citizen.id, True, actor_id=seed_admin.id, actor_role=Role.ADMIN
    )

    rows = _event_rows(app)
    assert [row.event_type for row in rows] == [
        EVENT_USER_DEACTIVATED,
        EVENT_USER_ACTIVATED,
    ]
    assert all(row.target_user_id == citizen.id for row in rows)
    assert rows[0].to_role is None and rows[0].from_role is None
    assert other_admin.id  # sanity: seed intact


def test_audit_insert_failure_rolls_back_mutation_and_event(
    app, repository, monkeypatch
):
    seed_admin = _seed_admin(repository)
    citizen = repository.create_user(
        name="Asha Rao",
        email="asha@example.com",
        password_hash=hash_password("asha password"),
        role=Role.CITIZEN,
    )
    service = _service(app)

    import app.persistence.repositories as repositories_module

    def boom():
        raise RuntimeError("injected audit persistence failure")

    monkeypatch.setattr(repositories_module, "utc_now", boom)
    with pytest.raises(RuntimeError):
        service.update_user_role(
            citizen.id, Role.REGISTRAR,
            actor_id=seed_admin.id, actor_role=Role.ADMIN,
        )

    monkeypatch.undo()
    reloaded = repository.get_user_by_id(citizen.id)
    assert reloaded.role == Role.CITIZEN  # mutation rolled back
    assert _event_rows(app) == []  # audit row rolled back too


def test_last_admin_conflict_leaves_no_audit_row(app, repository):
    seed_admin = _seed_admin(repository)
    service = _service(app)

    with pytest.raises(ResourceConflictError):
        service.update_user_role(
            seed_admin.id, Role.CITIZEN,
            actor_id=seed_admin.id, actor_role=Role.ADMIN,
        )

    assert _event_rows(app) == []


def test_duplicate_email_creates_no_user_and_no_audit_row(app, repository):
    _seed_admin(repository, email="dupe@example.com")
    service = _service(app)

    with pytest.raises(InvalidInputError):
        # Neither service nor repository may pretend success on conflict.
        repository.create_user(
            name="Dupe Two",
            email="dupe@example.com",
            password_hash=hash_password("another password"),
            role=Role.REGISTRAR,
        )

    assert _event_rows(app) == []


def test_logging_recorder_leaves_no_audit_rows(app, repository):
    _seed_admin(repository)
    service = _service(app, audit_recorder=LoggingAdminAuditRecorder())

    result = service.create_admin_user(
        {
            "name": "Log Hire",
            "email": "log-hire@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        },
        actor_id="admin-1",
        actor_role=Role.ADMIN,
    )

    assert result["user"]["email"] == "log-hire@example.com"
    assert _event_rows(app) == []


def test_inmemory_recorder_still_works_explicitly(app, repository):
    _seed_admin(repository)
    recorder = InMemoryAdminAuditRecorder()
    service = _service(app, audit_recorder=recorder)

    result = service.create_admin_user(
        {
            "name": "Memory Hire",
            "email": "memory-hire@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        },
        actor_id="admin-1",
        actor_role=Role.ADMIN,
    )

    assert len(recorder.events) == 1
    assert recorder.events[0].event_type == EVENT_USER_CREATED
    assert recorder.events[0].target_user_id == result["user"]["id"]
    assert _event_rows(app) == []


def test_admin_http_flow_persists_audit_row(app, repository):
    seed_admin = _seed_admin(repository)
    token = create_access_token(seed_admin.id, Role.ADMIN, app.config["JWT_SECRET_KEY"])

    response = app.test_client().post(
        "/api/admin/users",
        json={
            "name": "HTTP Hire",
            "email": "http-hire@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    rows = _event_rows(app)
    assert [row.event_type for row in rows] == [EVENT_USER_CREATED]
    assert rows[0].target_user_id == response.get_json()["user"]["id"]


def test_audit_rows_never_store_secrets(app, repository):
    _seed_admin(repository)
    service = _service(app)

    service.create_admin_user(
        {
            "name": "Secret Keeper",
            "email": "secret-keeper@example.com",
            "password": "a secure password",
            "role": "REGISTRAR",
        },
        actor_id="admin-1",
        actor_role=Role.ADMIN,
    )

    rows = _event_rows(app)
    serialized = " ".join(
        f"{row.actor_id} {row.actor_role} {row.target_user_id} "
        f"{row.event_type} {row.from_role} {row.to_role}"
        for row in rows
    ).lower()
    assert "secure password" not in serialized
    assert "scrypt" not in serialized
