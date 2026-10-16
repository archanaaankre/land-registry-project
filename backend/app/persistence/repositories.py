from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app import db
from app.auth.errors import InvalidInputError
from app.models import Role
from app.persistence.errors import DatabaseUnavailableError
from app.persistence.models import (
    OwnershipModel,
    ParcelModel,
    TransferAuditEventModel,
    TransferRequestModel,
    UserModel,
)


def _commit():
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise InvalidInputError("A matching database record already exists.") from None
    except SQLAlchemyError as error:
        db.session.rollback()
        raise DatabaseUnavailableError() from None


def _query(operation):
    try:
        return operation()
    except OperationalError as error:
        db.session.rollback()
        raise DatabaseUnavailableError() from None
    except SQLAlchemyError as error:
        db.session.rollback()
        raise DatabaseUnavailableError() from None


class SqlAlchemyUserRepository:
    def create_user(self, *, name, email, password_hash, role):
        user = UserModel(
            id=_user_id_from_email(email),
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
            role=role.value if hasattr(role, "value") else str(role),
        )
        db.session.add(user)
        _commit()
        return user.to_domain()

    def get_user_by_email(self, email):
        user = _query(lambda: UserModel.query.filter_by(email=email.strip().lower()).first())
        return user.to_domain() if user is not None else None

    def get_user_by_id(self, user_id):
        user = _query(lambda: db.session.get(UserModel, user_id))
        return user.to_domain() if user is not None else None


def _user_id_from_email(email):
    normalized = email.strip().lower()
    return "user-" + normalized.replace("@", "-").replace(".", "-")[:48]


class SqlAlchemyParcelRepository:
    def find_by_id(self, parcel_id):
        parcel = _query(lambda: db.session.get(ParcelModel, parcel_id))
        return parcel.to_domain() if parcel is not None else None

    def list_parcels(self):
        parcels = _query(
            lambda: ParcelModel.query.order_by(
                ParcelModel.created_at, ParcelModel.parcel_id
            ).all()
        )
        return [parcel.to_domain() for parcel in parcels]

    def create_parcel(self, parcel):
        model = ParcelModel(
            parcel_id=parcel.parcel_id,
            cadastral_number=parcel.cadastral_number,
            location=parcel.location,
            area=parcel.area,
            area_unit=parcel.area_unit.value,
            status=parcel.status.value,
            created_by=getattr(parcel, "created_by", None),
            created_at=parcel.created_at,
            updated_at=parcel.updated_at,
        )
        db.session.add(model)
        _commit()
        return model.to_domain()


class SqlAlchemyOwnershipRepository:
    def find_by_id(self, ownership_id):
        ownership = _query(lambda: db.session.get(OwnershipModel, ownership_id))
        return ownership.to_domain() if ownership is not None else None

    def list_for_parcel(self, parcel_id):
        records = _query(
            lambda: OwnershipModel.query.filter_by(parcel_id=parcel_id)
            .order_by(OwnershipModel.created_at, OwnershipModel.ownership_id)
            .all()
        )
        return [record.to_domain() for record in records]

    def create_ownership(self, ownership):
        model = OwnershipModel(
            ownership_id=ownership.ownership_id,
            parcel_id=ownership.parcel_id,
            owner_id=ownership.owner_id,
            share=ownership.share,
            status=ownership.status.value,
            created_at=ownership.created_at,
            updated_at=ownership.updated_at,
        )
        db.session.add(model)
        _commit()
        return model.to_domain()

    def update_ownership(self, ownership):
        model = _query(lambda: db.session.get(OwnershipModel, ownership.ownership_id))
        if model is None:
            raise InvalidInputError("Ownership record was not found.", field="ownership_id")
        model.parcel_id = ownership.parcel_id
        model.owner_id = ownership.owner_id
        model.share = ownership.share
        model.status = ownership.status.value
        model.updated_at = ownership.updated_at
        _commit()
        return model.to_domain()


class SqlAlchemyTransferRepository:
    _ACTIVE_STATUSES = {
        "DRAFT",
        "SUBMITTED",
        "UNDER_REVIEW",
        "APPROVED",
        "BLOCKCHAIN_PENDING",
    }

    def create_request(self, request):
        model = TransferRequestModel(
            request_id=request.request_id,
            parcel_id=request.parcel_id,
            seller_id=request.seller_id,
            buyer_reference=request.buyer_reference,
            status=request.status.value,
            reviewer_id=request.reviewer_id,
            review_reason=request.review_reason,
            reviewed_at=request.reviewed_at,
            blockchain_tx_id=request.blockchain_tx_id,
            blockchain_status=(
                request.blockchain_status.value
                if request.blockchain_status is not None
                else None
            ),
            failure_reason=request.failure_reason,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )
        db.session.add(model)
        _commit()
        return model.to_domain()

    def find_by_id(self, request_id):
        model = _query(lambda: db.session.get(TransferRequestModel, request_id))
        return model.to_domain() if model is not None else None

    def list_for_seller(self, seller_id):
        models = _query(
            lambda: TransferRequestModel.query.filter_by(seller_id=seller_id)
            .order_by(TransferRequestModel.created_at, TransferRequestModel.request_id)
            .all()
        )
        return [model.to_domain() for model in models]

    def list_for_buyer_reference(self, buyer_reference):
        models = _query(
            lambda: TransferRequestModel.query.filter_by(buyer_reference=buyer_reference)
            .order_by(TransferRequestModel.created_at, TransferRequestModel.request_id)
            .all()
        )
        return [model.to_domain() for model in models]

    def list_pending_for_review(self):
        models = _query(
            lambda: TransferRequestModel.query.filter(
                TransferRequestModel.status.in_(["SUBMITTED", "UNDER_REVIEW"])
            )
            .order_by(TransferRequestModel.created_at, TransferRequestModel.request_id)
            .all()
        )
        return [model.to_domain() for model in models]

    def list_all(self):
        models = _query(
            lambda: TransferRequestModel.query.order_by(
                TransferRequestModel.created_at, TransferRequestModel.request_id
            ).all()
        )
        return [model.to_domain() for model in models]

    def find_active_for_parcel(self, parcel_id):
        model = _query(
            lambda: TransferRequestModel.query.filter_by(parcel_id=parcel_id)
            .filter(TransferRequestModel.status.in_(self._ACTIVE_STATUSES))
            .order_by(TransferRequestModel.created_at.desc())
            .first()
        )
        return model.to_domain() if model is not None else None

    def save_request(self, request):
        model = _query(lambda: db.session.get(TransferRequestModel, request.request_id))
        if model is None:
            raise InvalidInputError("Transfer request was not found.", field="request_id")
        model.parcel_id = request.parcel_id
        model.seller_id = request.seller_id
        model.buyer_reference = request.buyer_reference
        model.status = request.status.value
        model.reviewer_id = request.reviewer_id
        model.review_reason = request.review_reason
        model.reviewed_at = request.reviewed_at
        model.blockchain_tx_id = request.blockchain_tx_id
        model.blockchain_status = (
            request.blockchain_status.value
            if request.blockchain_status is not None
            else None
        )
        model.failure_reason = request.failure_reason
        model.created_at = request.created_at
        model.updated_at = request.updated_at
        _commit()
        return model.to_domain()

    def record_audit_event(self, event):
        model = TransferAuditEventModel(
            event_id=event.event_id,
            request_id=event.request_id,
            actor_id=event.actor_id or None,
            actor_role=event.actor_role.value,
            event_type=event.event_type,
            from_status=event.from_status.value if event.from_status is not None else None,
            to_status=event.to_status.value,
            reason=event.reason,
            created_at=event.created_at,
        )
        db.session.add(model)
        _commit()
        return event

    def list_audit_events(self, request_id):
        models = _query(
            lambda: TransferAuditEventModel.query.filter_by(request_id=request_id)
            .order_by(TransferAuditEventModel.created_at, TransferAuditEventModel.event_id)
            .all()
        )
        domain_events = []
        for model in models:
            from app.models import TransferAuditEvent, TransferStatus
            from app.models import Role

            domain_events.append(
                TransferAuditEvent(
                    event_id=model.event_id,
                    request_id=model.request_id,
                    actor_id=model.actor_id or "",
                    actor_role=Role(model.actor_role),
                    event_type=model.event_type,
                    from_status=(
                        TransferStatus(model.from_status)
                        if model.from_status is not None
                        else None
                    ),
                    to_status=TransferStatus(model.to_status),
                    reason=model.reason,
                    created_at=model.created_at,
                )
            )
        return domain_events


def repository_bootstrap(app):
    if app.testing:
        return
    if app.config.get("AUTH_USER_REPOSITORY") is None:
        app.config["AUTH_USER_REPOSITORY"] = SqlAlchemyUserRepository()
    if app.config.get("PARCEL_REPOSITORY") is None:
        app.config["PARCEL_REPOSITORY"] = SqlAlchemyParcelRepository()
    if app.config.get("OWNERSHIP_REPOSITORY") is None:
        app.config["OWNERSHIP_REPOSITORY"] = SqlAlchemyOwnershipRepository()
    if app.config.get("TRANSFER_REPOSITORY") is None:
        app.config["TRANSFER_REPOSITORY"] = SqlAlchemyTransferRepository()