from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import db
from app.models import (
    AreaUnit,
    BlockchainSubmissionStatus,
    OwnershipStatus,
    ParcelStatus,
    Role,
    TransferStatus,
    utc_now,
)


class UserModel(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("role IN ('CITIZEN','REGISTRAR','ADMIN')", name="users_role"),
    )

    def to_domain(self):
        from app.models import User

        return User(
            id=self.id,
            name=self.name,
            email=self.email,
            password_hash=self.password_hash,
            role=Role(self.role),
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