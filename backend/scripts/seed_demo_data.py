#!/usr/bin/env python3
"""Demo data seeder for the BlockLand land registry.

Creates fictional, deterministic demo records using the real application
services and validators so every rule enforced by the API is also enforced
here.

Usage (run from the ``backend`` directory)::

    python scripts/seed_demo_data.py            # dry-run (default)
    python scripts/seed_demo_data.py --apply    # create the demo records

Behaviour notes:

* Dry-run by default. ``--apply`` is required before anything is written.
* Refuses to write when the configured database is not a local/SQLite
  database (for example Neon or a production URL).
* Deterministic record IDs are used; existing records are detected and
  skipped, so re-running is idempotent.
* Never sets ``blockchain_tx_id``; transfers stay in application-level
  statuses only (no fabricated blockchain activity).
"""

import argparse
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine.url import make_url  # noqa: E402

from app import create_app  # noqa: E402
from app.auth.api_service import AuthApiService  # noqa: E402
from app.auth.service import hash_password  # noqa: E402
from app.document_integrity.service import DocumentIntegrityService  # noqa: E402
from app.models import Role  # noqa: E402
from app.persistence.repositories import (  # noqa: E402
    SqlAlchemyDocumentHashRepository,
    SqlAlchemyOwnershipRepository,
    SqlAlchemyParcelRepository,
    SqlAlchemySupportingDocumentRepository,
    SqlAlchemyTransferRepository,
    SqlAlchemyUserRepository,
    repository_bootstrap,
)
from app.registry.services import OwnershipService, ParcelService  # noqa: E402
from app.transfers.services import TransferService  # noqa: E402

# ---------------------------------------------------------------------------
# Demo fixture data (deterministic, fictional)
# ---------------------------------------------------------------------------

ADMIN_NAME = "BlockLand Demo Admin"
ADMIN_EMAIL = "demo.admin@blockland.local"
ADMIN_PASSWORD = "demo-password-2026!"

REGISTRAR_EMAILS = (
    "demo.registrar1@blockland.local",
    "demo.registrar2@blockland.local",
)
OFFICER_EMAILS = ("demo.officer1@blockland.local",)

CITIZEN_NAMES = (
    "Alice Demo",
    "Bob Demo",
    "Carol Demo",
    "Dave Demo",
    "Eve Demo",
)
CITIZEN_EMAILS = (
    "demo.alice@blockland.local",
    "demo.bob@blockland.local",
    "demo.carol@blockland.local",
    "demo.dave@blockland.local",
    "demo.eve@blockland.local",
)

DEMO_PASSWORD = "demo-password-2026!"

# 8 realistic parcels (parcel_id is deterministic; cadastral numbers are
# normalised by the application validators).
DEMO_PARCELS = tuple(
    {
        "parcel_id": f"demo-parcel-{index:02d}",
        "cadastral_number": f"DEMO-{index:04d}",
        "location": f"Lote {index}, Calle Principal, Barrio demonstration",
        "area": Decimal(f"{2 + index}.25"),
        "area_unit": "SQ_METERS",
        "status": "ACTIVE",
    }
    for index in range(1, 9)
)

# Ownership records: one active owner per parcel for the first five parcels.
DEMO_OWNERSHIP_RECORDS = (
    ("demo-ownership-01", "demo-parcel-01", "demo.alice@blockland.local"),
    ("demo-ownership-02", "demo-parcel-02", "demo.bob@blockland.local"),
    ("demo-ownership-03", "demo-parcel-03", "demo.carol@blockland.local"),
    ("demo-ownership-04", "demo-parcel-04", "demo.dave@blockland.local"),
    ("demo-ownership-05", "demo-parcel-05", "demo.eve@blockland.local"),
)

# Transfer requests in different application-supported statuses. The seller
# of each transfer owns 100% of the parcel (enforced by the app).
DEMO_TRANSFERS = (
    ("demo-parcel-01", "demo.alice@blockland.local", "demo.bob@blockland.local", []),
    ("demo-parcel-02", "demo.bob@blockland.local", "demo.alice@blockland.local", ["review"]),
    ("demo-parcel-03", "demo.carol@blockland.local", "demo.dave@blockland.local", ["review", "approve"]),
    ("demo-parcel-04", "demo.dave@blockland.local", "demo.alice@blockland.local", ["review", "reject"]),
    ("demo-parcel-05", "demo.eve@blockland.local", "demo.alice@blockland.local", ["cancel"]),
)


class SeederRefusedError(RuntimeError):
    """Raised when the seeder is pointed at a non-local database."""


# ---------------------------------------------------------------------------
# Safety helpers
# ---------------------------------------------------------------------------

def _is_local_database(uri):
    """Return True for sqlite/local/127.0.0.1-style URIs (host or empty)."""
    if not uri:
        return True
    if uri.startswith("sqlite"):
        return True
    try:
        parsed = make_url(uri)
    except Exception:
        return False
    host = (parsed.host or "").strip().lower()
    return host in ("", "localhost", "127.0.0.1", "::1")


def _refuse_non_local_database(app):
    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not _is_local_database(uri):
        raise SeederRefusedError(
            "Refusing to seed a non-local database: "
            f"{uri.split('@')[-1] if uri else '(no DATABASE_URL configured)'}. "
            "The seeder is intended for local development only; point "
            "DATABASE_URL at a local database and rerun."
        )


# ---------------------------------------------------------------------------
# Seed stages
# ---------------------------------------------------------------------------

def seed_admin(app, apply, report):
    repository = app.config["AUTH_USER_REPOSITORY"]
    existing_admins = repository.list_users(role=Role.ADMIN)
    if any(user.email == ADMIN_EMAIL for user in existing_admins):
        return None
    report["users"] += 1
    if not apply:
        return None
    admin = repository.create_initial_admin(
        name=ADMIN_NAME,
        email=ADMIN_EMAIL,
        password_hash=hash_password(ADMIN_PASSWORD),
    )
    return admin


def seed_privileged_users(app, apply, report):
    service = AuthApiService(app.config["AUTH_USER_REPOSITORY"])
    admin = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(ADMIN_EMAIL)
    admin_id = admin.id if admin is not None else None
    created = []
    specs = [
        (REGISTRAR_EMAILS, Role.REGISTRAR),
        (OFFICER_EMAILS, Role.VERIFICATION_OFFICER),
    ]
    for emails, role in specs:
        for email in emails:
            existing = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(email)
            if existing is not None:
                continue
            report["users"] += 1
            if not apply:
                continue
            result = service.create_admin_user(
                {
                    "name": email.split("@")[0],
                    "email": email,
                    "password": DEMO_PASSWORD,
                    "role": role.value,
                },
                actor_id=admin_id,
                actor_role=Role.ADMIN,
            )
            created.append(result["user"]["id"])
    return created


def seed_citizens(app, apply, report):
    service = AuthApiService(app.config["AUTH_USER_REPOSITORY"])
    repository = app.config["AUTH_USER_REPOSITORY"]
    created = []
    for name, email in zip(CITIZEN_NAMES, CITIZEN_EMAILS):
        if repository.get_user_by_email(email) is not None:
            continue
        report["users"] += 1
        if not apply:
            continue
        service.register(
            {"name": name, "email": email, "password": DEMO_PASSWORD, "role": Role.CITIZEN.value}
        )
        user = repository.get_user_by_email(email)
        created.append(user.id)
    return created


def seed_parcels(app, apply, report):
    service = ParcelService(app.config["PARCEL_REPOSITORY"])
    repository = app.config["PARCEL_REPOSITORY"]
    registrar = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(REGISTRAR_EMAILS[0])
    created = []
    for parcel in DEMO_PARCELS:
        if repository.find_by_id(parcel["parcel_id"]) is not None:
            continue
        report["parcels"] += 1
        if not apply:
            continue
        domain = service.create_parcel(dict(parcel), creator_id=registrar.id if registrar else None)
        created.append(domain.parcel_id)
    return created


def seed_ownerships(app, apply, report):
    service = OwnershipService(
        app.config["OWNERSHIP_REPOSITORY"], app.config["PARCEL_REPOSITORY"]
    )
    repository = app.config["OWNERSHIP_REPOSITORY"]
    created = []
    for ownership_id, parcel_id, owner_email in DEMO_OWNERSHIP_RECORDS:
        if repository.find_by_id(ownership_id) is not None:
            continue
        report["ownerships"] += 1
        if not apply:
            continue
        domain = service.create_ownership(
            {
                "ownership_id": ownership_id,
                "parcel_id": parcel_id,
                "owner_id": app.config["AUTH_USER_REPOSITORY"].get_user_by_email(
                    owner_email
                ).id,
                "share": Decimal("100"),
                "status": "ACTIVE",
            }
        )
        created.append(domain.ownership_id)
    return created


def seed_transfers(app, apply, report):
    service = TransferService(
        app.config["TRANSFER_REPOSITORY"],
        app.config["PARCEL_REPOSITORY"],
        app.config["OWNERSHIP_REPOSITORY"],
        app.config["AUTH_USER_REPOSITORY"],
    )
    repository = app.config["TRANSFER_REPOSITORY"]
    registrar = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(REGISTRAR_EMAILS[0])
    created = []
    for parcel_id, seller_email, buyer_reference, actions in DEMO_TRANSFERS:
        if any(item.parcel_id == parcel_id for item in repository.list_all()):
            continue
        report["transfers"] += 1
        if not apply:
            created.append({"parcel_id": parcel_id, "actions": actions})
            continue
        seller = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(seller_email)
        request = service.submit_transfer(
            seller.id,
            {"parcel_id": parcel_id, "buyer_reference": buyer_reference},
            actor_role=Role.CITIZEN,
        )
        for action in actions:
            if action == "review":
                service.start_review(
                    registrar.id, Role.REGISTRAR, request.request_id, "Demo review"
                )
            elif action == "approve":
                service.approve_request(
                    registrar.id, Role.REGISTRAR, request.request_id, "Demo approval"
                )
            elif action == "reject":
                service.reject_request(
                    registrar.id, Role.REGISTRAR, request.request_id, "Demo rejection"
                )
            elif action == "cancel":
                service.cancel_request(
                    seller.id, Role.CITIZEN, request.request_id, "Demo cancellation"
                )
            else:
                raise ValueError(f"Unknown transfer action: {action}")
        created.append({"parcel_id": parcel_id, "request_id": request.request_id})
    return created


SUPPORTING_DOCS = (
    ("demo-survey-01.pdf", Role.REGISTRAR, "demo.registrar1@blockland.local", "demo-parcel-01"),
    ("demo-survey-02.pdf", Role.VERIFICATION_OFFICER, "demo.officer1@blockland.local", "demo-parcel-02"),
    ("demo-survey-03.pdf", Role.REGISTRAR, "demo.registrar2@blockland.local", "demo-parcel-03"),
    ("demo-survey-05.pdf", Role.REGISTRAR, "demo.registrar1@blockland.local", "demo-parcel-05"),
)


def seed_supporting_documents(app, apply, report):
    service = DocumentIntegrityService(
        app.config["DOCUMENT_HASH_REPOSITORY"],
        app.config["OWNERSHIP_REPOSITORY"],
        app.config["DOCUMENT_SUPPORTING_REPOSITORY"],
        app.config["TRANSFER_REPOSITORY"],
    )
    repository = app.config["DOCUMENT_SUPPORTING_REPOSITORY"]
    created = []
    for name, role, uploaded_by, parcel_id in SUPPORTING_DOCS:
        existing = repository.find_by_name(name, parcel_id) if hasattr(repository, "find_by_name") else None
        if existing is None:
            for record in repository.list_supporting_documents(parcel_id=parcel_id):
                if record.document_name == name:
                    existing = record
                    break
        if existing is not None:
            continue
        report["supporting_documents"] += 1
        if not apply:
            continue
        document = service.upload_supporting_document(
            name,
            f"BlockLand demo supporting document {name}".encode("utf-8"),
            actor_role=role,
            uploaded_by=app.config["AUTH_USER_REPOSITORY"].get_user_by_email(uploaded_by).id,
            parcel_id=parcel_id,
        )
        created.append(document.supporting_document_id)
    return created


def seed_trusted_hashes(app, apply, report):
    service = DocumentIntegrityService(
        app.config["DOCUMENT_HASH_REPOSITORY"],
        app.config["OWNERSHIP_REPOSITORY"],
        app.config["DOCUMENT_SUPPORTING_REPOSITORY"],
        app.config["TRANSFER_REPOSITORY"],
    )
    repository = app.config["DOCUMENT_HASH_REPOSITORY"]
    registrar = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(REGISTRAR_EMAILS[0])
    created = []
    for name, parcel_id in (("demo-survey-01.pdf", "demo-parcel-01"), ("demo-survey-03.pdf", "demo-parcel-03")):
        if repository.find_by_name_and_parcel(name, parcel_id) is not None:
            continue
        report["document_hashes"] += 1
        if not apply:
            continue
        document = service.store_document_hash(
            name,
            f"BlockLand demo baseline hash for {name}".encode("utf-8"),
            uploaded_by=registrar.id,
            parcel_id=parcel_id,
            actor_role=Role.REGISTRAR,
        )
        created.append(document.document_id)
    return created


def seed_verification_history(app, apply, report):
    service = DocumentIntegrityService(
        app.config["DOCUMENT_HASH_REPOSITORY"],
        app.config["OWNERSHIP_REPOSITORY"],
        app.config["DOCUMENT_SUPPORTING_REPOSITORY"],
        app.config["TRANSFER_REPOSITORY"],
    )
    repository = app.config["DOCUMENT_HASH_REPOSITORY"]
    registrar = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(REGISTRAR_EMAILS[0])
    vo = app.config["AUTH_USER_REPOSITORY"].get_user_by_email(OFFICER_EMAILS[0])
    created = []
    for name, parcel_id, matches in (
        ("demo-survey-01.pdf", "demo-parcel-01", True),
        ("demo-survey-03.pdf", "demo-parcel-03", False),
    ):
        document = repository.find_by_name_and_parcel(name, parcel_id)
        if document is None or document.verification_count > 0:
            continue
        report["verifications"] += 1
        if not apply:
            continue
        content = (
            f"BlockLand demo baseline hash for {name}".encode("utf-8")
            if matches
            else f"tampered demo content for {name}".encode("utf-8")
        )
        result = service.verify_document(
            document.document_id, content, actor_id=registrar.id, actor_role=Role.REGISTRAR
        )
        created.append(result.document_id)
        if vo is not None:
            service.verify_document(
                document.document_id,
                content,
                actor_id=vo.id,
                actor_role=Role.VERIFICATION_OFFICER,
            )
            report["verifications"] += 1
    return created


def seed(app=None, *, apply=False):
    """Seed demo data. Returns a report of records created/planned.

    ``app`` may be supplied (useful for tests with a custom database);
    when omitted a fresh ``create_app()`` instance is used.
    """
    if app is None:
        app = create_app()
    _refuse_non_local_database(app)
    with app.app_context():
        repository_bootstrap(app)
        report = {
            "apply": bool(apply),
            "users": 0,
            "parcels": 0,
            "ownerships": 0,
            "transfers": 0,
            "supporting_documents": 0,
            "document_hashes": 0,
            "verifications": 0,
        }
        seed_admin(app, apply, report)
        seed_privileged_users(app, apply, report)
        seed_citizens(app, apply, report)
        seed_parcels(app, apply, report)
        seed_ownerships(app, apply, report)
        seed_transfers(app, apply, report)
        seed_supporting_documents(app, apply, report)
        seed_trusted_hashes(app, apply, report)
        seed_verification_history(app, apply, report)
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually insert the demo records (dry-run by default)",
    )
    args = parser.parse_args(argv)
    report = seed(apply=args.apply)
    action = "Created" if args.apply else "Would create"
    print(f"{action} demo data:")
    for key, value in report.items():
        if key == "apply":
            continue
        print(f"  {key}: {value}")
    if not args.apply:
        print("\nRe-run with --apply to create the records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
