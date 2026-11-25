"""Tests for the BlockLand demo data seeder (backend/scripts/seed_demo_data.py).

The seeder runs against a disposable SQLite database created by the app
fixture. No production or Neon database is used.
"""

import secrets
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import seed_demo_data  # noqa: E402

from app import create_app, db  # noqa: E402
from app.config import Config  # noqa: E402
from app.models import Role, TransferStatus  # noqa: E402
from app.persistence.models import OwnershipModel  # noqa: E402
from app.persistence.repositories import (  # noqa: E402
    SqlAlchemyDocumentHashRepository,
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemySupportingDocumentRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyUserRepository,
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    database_url = "sqlite:///" + str(tmp_path / "seed_demo.db").replace("\\", "/")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", database_url)
    application = create_app()
    application.config.update(
        TESTING=True,
        JWT_SECRET_KEY=secrets.token_urlsafe(32),
        SQLALCHEMY_DATABASE_URI=database_url,
    )
    with application.app_context():
        db.create_all()
        application.config["AUTH_USER_REPOSITORY"] = SqlAlchemyUserRepository()
        application.config["PARCEL_REPOSITORY"] = SqlAlchemyParcelRepository()
        application.config["OWNERSHIP_REPOSITORY"] = SqlAlchemyOwnershipRepository()
        application.config["TRANSFER_REPOSITORY"] = SqlAlchemyTransferRepository()
        application.config["DOCUMENT_HASH_REPOSITORY"] = SqlAlchemyDocumentHashRepository()
        application.config["DOCUMENT_SUPPORTING_REPOSITORY"] = (
            SqlAlchemySupportingDocumentRepository()
        )
    return application


def _report_totals(application):
    with application.app_context():
        user_repo = application.config["AUTH_USER_REPOSITORY"]
        return {
            "users": len(user_repo.list_users()),
            "parcels": len(application.config["PARCEL_REPOSITORY"].list_parcels()),
            "ownerships": db.session.query(OwnershipModel).count(),
            "transfers": len(application.config["TRANSFER_REPOSITORY"].list_all()),
            "supporting_documents": len(
                application.config["DOCUMENT_SUPPORTING_REPOSITORY"]
                .list_supporting_documents()
            ),
            "document_hashes": len(
                application.config["DOCUMENT_HASH_REPOSITORY"].list_document_hashes()
            ),
        }


def test_refuses_remote_database(app):
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "postgresql://user:pw@ep-123.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
    )
    with pytest.raises(seed_demo_data.SeederRefusedError):
        seed_demo_data.seed(app, apply=True)


def test_dry_run_creates_nothing(app):
    report = seed_demo_data.seed(app, apply=False)
    assert report["users"] > 0  # planned only
    assert report["parcels"] >= 8
    assert report["ownerships"] > 0
    assert report["transfers"] > 0
    assert _report_totals(app) == {
        "users": 0,
        "parcels": 0,
        "ownerships": 0,
        "transfers": 0,
        "supporting_documents": 0,
        "document_hashes": 0,
    }


def test_apply_creates_demo_data(app):
    report = seed_demo_data.seed(app, apply=True)
    totals = _report_totals(app)

    assert totals["users"] >= 9  # 1 admin + 2 registrars + 1 VO + 5 citizens
    assert totals["parcels"] >= 8
    assert totals["ownerships"] >= 5
    assert totals["supporting_documents"] >= 4
    assert totals["document_hashes"] >= 2
    assert report["users"] == totals["users"]
    assert report["parcels"] >= 8

    with app.app_context():
        user_repo = app.config["AUTH_USER_REPOSITORY"]
        admin = user_repo.get_user_by_email(seed_demo_data.ADMIN_EMAIL)
        assert admin is not None
        assert admin.role is Role.ADMIN

        transfers = app.config["TRANSFER_REPOSITORY"].list_all()
        statuses = {transfer.status for transfer in transfers}
        assert {
            TransferStatus.SUBMITTED,
            TransferStatus.UNDER_REVIEW,
            TransferStatus.APPROVED,
            TransferStatus.REJECTED,
            TransferStatus.CANCELLED,
        } <= statuses
        assert all(transfer.blockchain_tx_id is None for transfer in transfers)

        hashes = app.config["DOCUMENT_HASH_REPOSITORY"].list_document_hashes()
        assert any(h.verification_count > 0 for h in hashes)


def test_second_apply_is_idempotent(app):
    first = seed_demo_data.seed(app, apply=True)
    totals_after_first = _report_totals(app)
    assert first["users"] == totals_after_first["users"]

    second = seed_demo_data.seed(app, apply=True)
    assert second["users"] == 0
    assert second["parcels"] == 0
    assert second["ownerships"] == 0
    assert second["transfers"] == 0
    assert second["supporting_documents"] == 0
    assert second["document_hashes"] == 0

    assert _report_totals(app) == totals_after_first
