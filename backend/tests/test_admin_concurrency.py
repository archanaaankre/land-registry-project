"""PostgreSQL concurrency tests for last-active-admin protection.

These tests race two simultaneous admin-removing mutations (deactivation or
demotion) against a real, disposable PostgreSQL server (``pgserver``), so
genuine row locks and transactional rollback are exercised. The suite is
skipped when ``pgserver`` is unavailable; SQLite is never treated as a
substitute. Each test uses its own ``CREATE DATABASE`` inside the disposable
server instance, so no development database is ever touched.
"""

import os
import shutil
import tempfile
import threading
import uuid
from types import SimpleNamespace

import pytest

pgserver = pytest.importorskip(
    "pgserver",
    reason="pgserver provides the disposable PostgreSQL test server "
    "(pip install pgserver); without it PostgreSQL concurrency remains "
    "unverified and this module must not silently fall back to SQLite.",
)

import psycopg2

from app import create_app, db
from app.auth.api_service import AuthApiService
from app.auth.audit import InMemoryAdminAuditRecorder
from app.auth.errors import (
    AuthError,
    ResourceConflictError,
)
from app.auth.service import hash_password
from app.config import Config
from app.models import Role
from app.persistence.repositories import SqlAlchemyUserRepository


@pytest.fixture(scope="session")
def postgres_server():
    """One isolated embedded PostgreSQL server for the whole module."""
    base = os.path.join(tempfile.gettempdir(), "opencode")
    os.makedirs(base, exist_ok=True)
    datadir = os.path.join(base, "pg_admin_" + uuid.uuid4().hex[:8])
    server = pgserver.get_server(datadir)
    try:
        yield server
    finally:
        server.cleanup()
        shutil.rmtree(datadir, ignore_errors=True)


@pytest.fixture
def pg_app(postgres_server):
    """A fresh application bound to a unique database on that server."""
    dbname = "admin_concurrency_" + uuid.uuid4().hex[:12]
    admin = psycopg2.connect(postgres_server.get_uri())
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        admin.close()
    database_url = postgres_server.get_uri().rsplit("/", 1)[0] + "/" + dbname

    original_env_url = os.environ.get("DATABASE_URL")
    original_config_url = Config.SQLALCHEMY_DATABASE_URI
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    try:
        app = create_app()
        app.config.update(
            TESTING=True,
            JWT_SECRET_KEY="test-admin-concurrency-secret",
            SQLALCHEMY_DATABASE_URI=database_url,
        )
        with app.app_context():
            db.create_all()
        app.config.update(AUTH_USER_REPOSITORY=SqlAlchemyUserRepository())
        yield app
    finally:
        if original_env_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_env_url
        Config.SQLALCHEMY_DATABASE_URI = original_config_url
        with app.app_context():
            db.engine.dispose()


def _seed_two_admins(app):
    """Create exactly two active admins; returns (admin_a, admin_b)."""
    user_repository = app.config["AUTH_USER_REPOSITORY"]
    with app.app_context():
        admin_a = user_repository.create_user(
            name="Admin A",
            email="admin-a@example.com",
            password_hash=hash_password("admin a password"),
            role=Role.ADMIN,
        )
        admin_b = user_repository.create_user(
            name="Admin B",
            email="admin-b@example.com",
            password_hash=hash_password("admin b password"),
            role=Role.ADMIN,
        )
    return admin_a, admin_b


def _active_admins(app):
    user_repository = app.config["AUTH_USER_REPOSITORY"]
    with app.app_context():
        return user_repository.list_users(role=Role.ADMIN, is_active=True)


def _race(app, *operations):
    """Run operations in parallel threads and collect their outcomes."""
    barrier = threading.Barrier(len(operations))
    results = [None] * len(operations)

    def _run(index, operation):
        with app.app_context():
            try:
                barrier.wait(timeout=15)
            except threading.BrokenBarrierError as error:  # pragma: no cover
                results[index] = ("unexpected", error)
                return
            try:
                results[index] = ("ok", operation())
            except AuthError as error:
                results[index] = ("error", error)
            except Exception as error:  # pragma: no cover - surfaced below
                results[index] = ("unexpected", error)

    threads = [
        threading.Thread(target=_run, args=(index, operation))
        for index, operation in enumerate(operations)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), (
        "a concurrent operation deadlocked"
    )
    assert all(result is not None for result in results), (
        "a concurrent operation produced no result"
    )
    return results


def _classify(results):
    ok = [value for kind, value in results if kind == "ok"]
    errors = [value for kind, value in results if kind == "error"]
    unexpected = [value for kind, value in results if kind == "unexpected"]
    assert unexpected == [], f"unexpected errors: {unexpected!r}"
    return ok, errors


def test_concurrent_deactivation_of_last_two_admins(pg_app):
    admin_a, admin_b = _seed_two_admins(pg_app)
    repository = pg_app.config["AUTH_USER_REPOSITORY"]
    recorder = InMemoryAdminAuditRecorder()

    def deactivate(target_id, actor_id):
        service = AuthApiService(repository, audit_recorder=recorder)
        return service.update_user_active_status(
            target_id, False, actor_id=actor_id, actor_role=Role.ADMIN
        )

    results = _race(
        pg_app,
        lambda: deactivate(admin_a.id, actor_id=admin_b.id),
        lambda: deactivate(admin_b.id, actor_id=admin_a.id),
    )

    ok, errors = _classify(results)
    assert len(ok) == 1, f"exactly one deactivation must succeed, got {results!r}"
    assert len(errors) == 1
    assert isinstance(errors[0], ResourceConflictError)
    assert _active_admins(pg_app) != [], "an active admin must remain"
    assert len(_active_admins(pg_app)) == 1
    # The rejected mutation recorded no audit event; the winner did.
    assert len(recorder.events) == 1
    assert recorder.events[0].event_type == "USER_DEACTIVATED"


def test_concurrent_demotion_of_last_two_admins(pg_app):
    admin_a, admin_b = _seed_two_admins(pg_app)
    repository = pg_app.config["AUTH_USER_REPOSITORY"]
    recorder = InMemoryAdminAuditRecorder()

    def demote(target_id, actor_id):
        service = AuthApiService(repository, audit_recorder=recorder)
        return service.update_user_role(
            target_id, Role.CITIZEN, actor_id=actor_id, actor_role=Role.ADMIN
        )

    results = _race(
        pg_app,
        lambda: demote(admin_a.id, actor_id=admin_b.id),
        lambda: demote(admin_b.id, actor_id=admin_a.id),
    )

    ok, errors = _classify(results)
    assert len(ok) == 1, f"exactly one demotion must succeed, got {results!r}"
    assert len(errors) == 1
    assert isinstance(errors[0], ResourceConflictError)
    assert len(_active_admins(pg_app)) == 1
    assert len(recorder.events) == 1
    assert recorder.events[0].event_type == "USER_ROLE_CHANGED"


def test_concurrent_deactivate_and_demote_of_last_two_admins(pg_app):
    admin_a, admin_b = _seed_two_admins(pg_app)
    repository = pg_app.config["AUTH_USER_REPOSITORY"]
    recorder = InMemoryAdminAuditRecorder()

    def deactivate(target_id, actor_id):
        service = AuthApiService(repository, audit_recorder=recorder)
        return service.update_user_active_status(
            target_id, False, actor_id=actor_id, actor_role=Role.ADMIN
        )

    def demote(target_id, actor_id):
        service = AuthApiService(repository, audit_recorder=recorder)
        return service.update_user_role(
            target_id, Role.CITIZEN, actor_id=actor_id, actor_role=Role.ADMIN
        )

    results = _race(
        pg_app,
        lambda: deactivate(admin_a.id, actor_id=admin_b.id),
        lambda: demote(admin_b.id, actor_id=admin_a.id),
    )

    ok, errors = _classify(results)
    assert len(ok) == 1, f"exactly one operation must succeed, got {results!r}"
    assert len(errors) == 1
    assert isinstance(errors[0], ResourceConflictError)
    assert len(_active_admins(pg_app)) == 1
    assert len(recorder.events) == 1


def test_guarded_mutation_rollback_preserves_row(pg_app):
    repository = pg_app.config["AUTH_USER_REPOSITORY"]
    with pg_app.app_context():
        admin_a = repository.create_user(
            name="Lone Admin",
            email="lone-admin@example.com",
            password_hash=hash_password("lone admin password"),
            role=Role.ADMIN,
        )
        with pytest.raises(ResourceConflictError):
            repository.update_user_active_status_with_admin_guard(
                admin_a.id, False
            )

        user_repository = pg_app.config["AUTH_USER_REPOSITORY"]
        lone = user_repository.get_user_by_id(admin_a.id)
        assert lone.is_active is True
        assert lone.role == Role.ADMIN


def test_guarded_mutation_failure_rolls_back_completely(pg_app, monkeypatch):
    """An injected mid-transaction failure rolls the whole mutation back."""
    repository = pg_app.config["AUTH_USER_REPOSITORY"]
    with pg_app.app_context():
        admin_a = repository.create_user(
            name="Admin A",
            email="rollback-a@example.com",
            password_hash=hash_password("rollback a password"),
            role=Role.ADMIN,
        )
        admin_b = repository.create_user(
            name="Admin B",
            email="rollback-b@example.com",
            password_hash=hash_password("rollback b password"),
            role=Role.ADMIN,
        )

        import app.persistence.repositories as repositories_module

        def boom():
            raise RuntimeError("injected mid-transaction failure")

        monkeypatch.setattr(repositories_module, "utc_now", boom)
        with pytest.raises(RuntimeError):
            repository.update_user_role_with_admin_guard(admin_a.id, Role.CITIZEN)

        # The failed transaction left no partial change and a usable session.
        lone = repository.get_user_by_id(admin_a.id)
        other = repository.get_user_by_id(admin_b.id)
        assert lone.role == Role.ADMIN and lone.is_active is True
        assert other.role == Role.ADMIN and other.is_active is True
