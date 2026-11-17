import os

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app, db
from app.auth.errors import ResourceConflictError
from app.auth.service import hash_password, verify_password
from app.config import Config
from app.models import Role
from app.persistence.errors import DatabaseUnavailableError
from app.persistence.models import UserModel
from app.persistence.repositories import SqlAlchemyUserRepository, _query


@pytest.fixture
def repository_app(tmp_path):
    database_url = "sqlite:///" + str(tmp_path / "initial-admin.db").replace("\\", "/")
    previous_database_url = os.environ.get("DATABASE_URL")
    previous_config_database_url = Config.SQLALCHEMY_DATABASE_URI
    os.environ["DATABASE_URL"] = database_url
    Config.SQLALCHEMY_DATABASE_URI = database_url
    try:
        app = create_app()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        Config.SQLALCHEMY_DATABASE_URI = previous_config_database_url

    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_initial_admin_is_created_active_with_hashed_password(repository_app):
    with repository_app.app_context():
        user = SqlAlchemyUserRepository().create_initial_admin(
            name="Registry Admin",
            email="admin@example.com",
            password_hash=hash_password("a secure initial password"),
        )

    assert user.role is Role.ADMIN
    assert user.is_active is True
    assert user.password_hash != "a secure initial password"
    assert verify_password(user.password_hash, "a secure initial password")


def test_initial_admin_creation_refuses_any_existing_admin(repository_app):
    repository = SqlAlchemyUserRepository()
    with repository_app.app_context():
        repository.create_user(
            name="Inactive Admin",
            email="existing-admin@example.com",
            password_hash=hash_password("an existing admin password"),
            role=Role.ADMIN,
        )
        repository.create_user(
            name="Active Admin",
            email="active-admin@example.com",
            password_hash=hash_password("another existing admin password"),
            role=Role.ADMIN,
        )
        repository.update_user_status(
            "user-existing-admin-example-com", False
        )

        with pytest.raises(ResourceConflictError):
            repository.create_initial_admin(
                name="Another Admin",
                email="another-admin@example.com",
                password_hash=hash_password("another secure password"),
            )

        assert repository.get_user_by_email("another-admin@example.com") is None


def test_initial_admin_commit_logs_only_exception_type_and_sqlstate(
    repository_app, monkeypatch, caplog
):
    class DriverError(Exception):
        sqlstate = "08006"

    with repository_app.app_context():
        session = db.session()

        def fail_commit():
            raise OperationalError(
                "private SQL statement",
                {"email": "private@example.com", "password": "private-value"},
                DriverError("private driver message"),
            )

        monkeypatch.setattr(session, "commit", fail_commit)

        with pytest.raises(DatabaseUnavailableError):
            SqlAlchemyUserRepository().create_initial_admin(
                name="Private Name",
                email="private@example.com",
                password_hash="private-password-hash",
            )

        assert (
            UserModel.query.filter_by(email="private@example.com").first()
            is None
        )

    assert "exception_type=OperationalError" in caplog.text
    assert "sqlstate=08006" in caplog.text
    assert "private SQL statement" not in caplog.text
    assert "private@example.com" not in caplog.text
    assert "private-value" not in caplog.text
    assert "private driver message" not in caplog.text
    assert "private-password-hash" not in caplog.text


def test_initial_admin_query_failure_logs_stage_and_sqlstate(
    repository_app, caplog
):
    class DriverError(Exception):
        pgcode = "08006"

    with repository_app.app_context():
        def fail_query():
            raise OperationalError(
                "private SQL statement",
                {"email": "private@example.com"},
                DriverError("private driver message"),
            )

        with pytest.raises(DatabaseUnavailableError):
            _query(fail_query, initial_admin_stage="Admin lookup")

    assert "Admin lookup failed" in caplog.text
    assert "exception_type=OperationalError" in caplog.text
    assert "sqlstate=08006" in caplog.text
    assert "private SQL statement" not in caplog.text
    assert "private@example.com" not in caplog.text
    assert "private driver message" not in caplog.text
