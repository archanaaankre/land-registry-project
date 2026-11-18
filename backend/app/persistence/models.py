from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    literal_column,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import db
from app.document_integrity.models import DocumentVerificationStatus
from app.models import (
    AreaUnit,
    BlockchainSubmissionStatus,
    OwnershipStatus,
    ParcelStatus,
    Role,
    TransferStatus,
    utc_now,
)

_CADASTRAL_EDGE_WHITESPACE = literal_column("' \t\n\r\v\f'")


def normalized_cadastral_number_expression(column):
    return func.upper(
        func.ltrim(
            func.rtrim(column, _CADASTRAL_EDGE_WHITESPACE),
            _CADASTRAL_EDGE_WHITESPACE,
        )
    )


class UserModel(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')", name="users_role"),
    )

    def to_domain(self):
        from app.models import User

        return User(
            id=self.id,
            name=self.name,
            email=self.email,
            password_hash=self.password_hash,
            role=Role(self.role),
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ParcelModel(db.Model):
    __tablename__ = "parcels"

    parcel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cadastral_number: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(500), nullable=False)
    area: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    area_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "uq_parcels_cadastral_number_ascii_whitespace",
            normalized_cadastral_number_expression(cadastral_number),
            unique=True,
        ),
        CheckConstraint(
            "area_unit IN ('SQ_METERS','HECTARES','ACRES')",
            name="parcels_area_unit",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','DISPUTED')",
            name="parcels_status",
        ),
    )

    def to_domain(self):
        from app.models import Parcel

        return Parcel(
            parcel_id=self.parcel_id,
            cadastral_number=self.cadastral_number,
            location=self.location,
            area=Decimal(str(self.area)),
            area_unit=AreaUnit(self.area_unit),
            status=ParcelStatus(self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
            created_by=self.created_by,
        )


class OwnershipModel(db.Model):
    __tablename__ = "ownerships"

    ownership_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parcel_id: Mapped[str] = mapped_column(String(64), ForeignKey("parcels.parcel_id"), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id"), nullable=False, index=True)
    share: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "uq_ownerships_one_active_owner_per_parcel",
            "parcel_id",
            "owner_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        CheckConstraint(
            "share > 0 AND share <= 100",
            name="ownerships_share",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE','DISPUTED')",
            name="ownerships_status",
        ),
    )

    def to_domain(self):
        from app.models import Ownership

        return Ownership(
            ownership_id=self.ownership_id,
            parcel_id=self.parcel_id,
            owner_id=self.owner_id,
            share=Decimal(str(self.share)),
            status=OwnershipStatus(self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class TransferRequestModel(db.Model):
    __tablename__ = "transfer_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parcel_id: Mapped[str] = mapped_column(String(64), ForeignKey("parcels.parcel_id"), nullable=False, index=True)
    seller_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id"), nullable=False, index=True)
    buyer_reference: Mapped[str] = mapped_column(String(254), nullable=False)
    # Canonical buyer identity; nullable only for legacy rows that predate
    # this column (see the migration proposal for Person 1).
    buyer_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id"), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blockchain_tx_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    blockchain_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "uq_transfer_requests_one_active_per_parcel",
            "parcel_id",
            unique=True,
            postgresql_where=text(
                "status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','APPROVED','BLOCKCHAIN_PENDING')"
            ),
            sqlite_where=text(
                "status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','APPROVED','BLOCKCHAIN_PENDING')"
            ),
        ),
    )

    def to_domain(self):
        from app.models import TransferRequest

        return TransferRequest(
            request_id=self.request_id,
            parcel_id=self.parcel_id,
            seller_id=self.seller_id,
            buyer_reference=self.buyer_reference,
            buyer_id=self.buyer_id,
            status=TransferStatus(self.status),
            created_at=self.created_at,
            updated_at=self.updated_at,
            reviewer_id=self.reviewer_id,
            review_reason=self.review_reason,
            reviewed_at=self.reviewed_at,
            blockchain_tx_id=self.blockchain_tx_id,
            blockchain_status=(
                BlockchainSubmissionStatus(self.blockchain_status)
                if self.blockchain_status is not None
                else None
            ),
            failure_reason=self.failure_reason,
        )


class TransferAuditEventModel(db.Model):
    __tablename__ = "transfer_audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("transfer_requests.request_id"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    def to_domain(self):
        from app.models import TransferAuditEvent

        return TransferAuditEvent(
            event_id=self.event_id,
            request_id=self.request_id,
            actor_id=self.actor_id or "",
            actor_role=__import__("app.models", fromlist=["Role"]).Role(self.actor_role),
            event_type=self.event_type,
            from_status=(
                TransferStatus(self.from_status) if self.from_status is not None else None
            ),
            to_status=TransferStatus(self.to_status),
            reason=self.reason,
            created_at=self.created_at,
        )


class AdminAuditEventModel(db.Model):
    """Durable audit trail for admin user-management actions.

    Rows are written by the SQLAlchemy user repository inside the same
    transaction as the admin mutation. FKs use ON DELETE SET NULL so
    deleting a user preserves historical audit records (with actor/target
    ids nulled, never with personal data fabricated).
    """

    __tablename__ = "admin_audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    target_user_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('USER_CREATED','USER_ROLE_CHANGED','USER_ACTIVATED','USER_DEACTIVATED')",
            name="admin_audit_events_event_type",
        ),
        CheckConstraint(
            "actor_role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')",
            name="admin_audit_events_actor_role",
        ),
        CheckConstraint(
            "from_role IS NULL OR from_role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')",
            name="admin_audit_events_from_role",
        ),
        CheckConstraint(
            "to_role IS NULL OR to_role IN ('CITIZEN','REGISTRAR','ADMIN','VERIFICATION_OFFICER')",
            name="admin_audit_events_to_role",
        ),
    )

    def to_domain(self):
        from app.auth.audit import AdminAuditEvent

        detail = {}
        if self.from_role is not None:
            detail["from_role"] = self.from_role
        if self.to_role is not None:
            detail["to_role"] = self.to_role
        return AdminAuditEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            actor_id=self.actor_id or "",
            actor_role=Role(self.actor_role),
            target_user_id=self.target_user_id or "",
            created_at=self.created_at,
            detail=detail,
        )


class DocumentHashModel(db.Model):
    """Stored trusted SHA-256 hashes of documents for integrity verification."""

    __tablename__ = "document_hashes"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parcel_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("parcels.parcel_id"), nullable=True, index=True
    )
    document_name: Mapped[str] = mapped_column(String(200), nullable=False)
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id"), nullable=False, index=True
    )
    uploaded_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    verification_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_verified_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_verification_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_document_hashes_name_per_parcel",
            "document_name",
            "parcel_id",
            unique=True,
            postgresql_where=text("parcel_id IS NOT NULL"),
            sqlite_where=text("parcel_id IS NOT NULL"),
        ),
    )

    def to_domain(self):
        from app.document_integrity.models import DocumentHash

        return DocumentHash(
            document_id=self.document_id,
            parcel_id=self.parcel_id,
            document_name=self.document_name,
            document_hash=self.document_hash,
            uploaded_by=self.uploaded_by,
            uploaded_at=self.uploaded_at,
            verification_count=self.verification_count,
            last_verified_at=self.last_verified_at,
            last_verification_status=(
                DocumentVerificationStatus(self.last_verification_status)
                if self.last_verification_status is not None
                else None
            ),
        )