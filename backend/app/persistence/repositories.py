import logging
from decimal import Decimal

from sqlalchemy import func, or_, text, update
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app import db
from app.auth.errors import (
    AuthorizationError,
    InvalidInputError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from app.document_integrity.models import DocumentVerificationStatus
from app.models import (
    BlockchainSubmissionStatus,
    OwnershipStatus,
    Role,
    TransferStatus,
    utc_now,
)
from app.persistence.errors import DatabaseUnavailableError
from app.persistence.models import (
    DocumentHashModel,
    OwnershipModel,
    ParcelModel,
    TransferAuditEventModel,
    TransferRequestModel,
    UserModel,
    normalized_cadastral_number_expression,
)
from app.registry.validation import normalize_cadastral_number


def _is_cadastral_number_conflict(error):
    constraint_name = getattr(
        getattr(error.orig, "diag", None), "constraint_name", None
    )
    return (
        constraint_name
        in {
            "uq_parcels_cadastral_number_normalized",
            "uq_parcels_cadastral_number_ascii_whitespace",
        }
        or "uq_parcels_cadastral_number_normalized" in str(error.orig)
        or "uq_parcels_cadastral_number_ascii_whitespace" in str(error.orig)
    )


def _is_active_ownership_conflict(error):
    constraint_name = getattr(
        getattr(error.orig, "diag", None), "constraint_name", None
    )
    return (
        constraint_name == "uq_ownerships_one_active_owner_per_parcel"
        or "uq_ownerships_one_active_owner_per_parcel" in str(error.orig)
        or str(error.orig)
        == "UNIQUE constraint failed: ownerships.parcel_id, ownerships.owner_id"
    )


def _raise_cadastral_number_conflict():
    raise ResourceConflictError(
        "A parcel with this cadastral number already exists."
    ) from None


_logger = logging.getLogger(__name__)


def _commit(*, log_initial_admin_failure=False):
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if _is_cadastral_number_conflict(error):
            _raise_cadastral_number_conflict()
        if _is_active_ownership_conflict(error):
            raise ResourceConflictError(
                "This owner already has an active ownership record for the parcel."
            ) from None
        if log_initial_admin_failure:
            _log_initial_admin_failure(error, "commit")
        raise InvalidInputError("A matching database record already exists.") from None
    except SQLAlchemyError as error:
        db.session.rollback()
        if log_initial_admin_failure:
            _log_initial_admin_failure(error, "commit")
        raise DatabaseUnavailableError() from None


def _query(operation, *, initial_admin_stage=None):
    try:
        return operation()
    except IntegrityError as error:
        db.session.rollback()
        if _is_cadastral_number_conflict(error):
            _raise_cadastral_number_conflict()
        if _is_active_ownership_conflict(error):
            raise ResourceConflictError(
                "This owner already has an active ownership record for the parcel."
            ) from None
        if initial_admin_stage is not None:
            _log_initial_admin_failure(error, initial_admin_stage)
        raise DatabaseUnavailableError() from None
    except OperationalError as error:
        db.session.rollback()
        if initial_admin_stage is not None:
            _log_initial_admin_failure(error, initial_admin_stage)
        raise DatabaseUnavailableError() from None
    except SQLAlchemyError as error:
        db.session.rollback()
        if initial_admin_stage is not None:
            _log_initial_admin_failure(error, initial_admin_stage)
        raise DatabaseUnavailableError() from None


def _log_initial_admin_failure(error, stage):
    original_error = getattr(error, "orig", error)
    sqlstate = getattr(original_error, "sqlstate", None) or getattr(
        original_error, "pgcode", None
    )
    if not isinstance(sqlstate, str):
        sqlstate = None
    _logger.error(
        "Initial Admin database %s failed (exception_type=%s, sqlstate=%s)",
        stage,
        type(error).__name__,
        sqlstate,
    )


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

    def create_initial_admin(self, *, name, email, password_hash):
        if db.engine.dialect.name == "postgresql":
            _query(
                lambda: db.session.execute(
                    text("SELECT pg_advisory_xact_lock(:namespace, :resource)"),
                    {"namespace": 1279345234, "resource": 1},
                ),
                initial_admin_stage="advisory lock",
            )

        existing_admin = _query(
            lambda: UserModel.query.filter_by(role=Role.ADMIN.value).first(),
            initial_admin_stage="Admin lookup",
        )
        if existing_admin is not None:
            db.session.rollback()
            raise ResourceConflictError(
                "An Admin account already exists. No account was created."
            )

        user = UserModel(
            id=_user_id_from_email(email),
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
            role=Role.ADMIN.value,
            is_active=True,
        )
        db.session.add(user)
        _commit(log_initial_admin_failure=True)
        return user.to_domain()

    def get_user_by_email(self, email):
        user = _query(lambda: UserModel.query.filter_by(email=email.strip().lower()).first())
        return user.to_domain() if user is not None else None

    def get_user_by_id(self, user_id):
        user = _query(lambda: db.session.get(UserModel, user_id))
        return user.to_domain() if user is not None else None

    def get_auth_state_by_id(self, user_id):
        """Used by roles_required to re-check role/activation on each request."""
        state = _query(
            lambda: db.session.query(UserModel.is_active, UserModel.role)
            .filter_by(id=user_id)
            .first()
        )
        if state is None:
            return None
        is_active, role = state
        return is_active, Role(role)

    def list_users(self, *, search=None, role=None, is_active=None):
        """Combined listing: Person 2's search plus Person 1's filters."""
        query = UserModel.query
        if search:
            pattern = _like_pattern(search)
            query = query.filter(
                or_(
                    UserModel.name.ilike(pattern, escape="\\"),
                    UserModel.email.ilike(pattern, escape="\\"),
                )
            )
        if role is not None:
            role_value = role.value if hasattr(role, "value") else Role(role).value
            query = query.filter_by(role=role_value)
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        users = _query(
            lambda: query.order_by(UserModel.created_at, UserModel.email).all()
        )
        return [user.to_domain() for user in users]

    def update_user_role(self, user_id, role):
        """Person 1's guarded mutation: protect the last active Admin."""
        active_admins = _query(
            lambda: UserModel.query.filter_by(
                role=Role.ADMIN.value, is_active=True
            )
            .with_for_update()
            .all()
        )
        user = _query(lambda: db.session.get(UserModel, user_id))
        if user is None:
            return None
        if (
            user.role == Role.ADMIN.value
            and user.is_active
            and Role(role) is not Role.ADMIN
            and len(active_admins) <= 1
        ):
            raise ResourceConflictError(
                "The last active Admin cannot be demoted."
            )

        user.role = Role(role).value
        user.updated_at = utc_now()
        _commit()
        return user.to_domain()

    def update_user_status(self, user_id, is_active):
        """Person 1's guarded mutation: protect the last active Admin."""
        active_admins = _query(
            lambda: UserModel.query.filter_by(
                role=Role.ADMIN.value, is_active=True
            )
            .with_for_update()
            .all()
        )
        user = _query(lambda: db.session.get(UserModel, user_id))
        if user is None:
            return None
        if (
            user.role == Role.ADMIN.value
            and user.is_active
            and not is_active
            and len(active_admins) <= 1
        ):
            raise ResourceConflictError(
                "The last active Admin cannot be deactivated."
            )

        user.is_active = is_active
        user.updated_at = utc_now()
        _commit()
        return user.to_domain()

    def update_user_active_status(self, user_id, is_active):
        """Compatibility alias for Person 2's service method name; guarded."""
        return self.update_user_status(user_id, is_active)


def _user_id_from_email(email):
    normalized = email.strip().lower()
    return "user-" + normalized.replace("@", "-").replace(".", "-")[:48]


def _like_pattern(value):
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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

    def search_parcels(
        self,
        *,
        search=None,
        cadastral_number=None,
        location=None,
        status=None,
        page=None,
        page_size=None,
    ):
        query = ParcelModel.query
        if search:
            pattern = _like_pattern(search)
            cadastral_pattern = _like_pattern(normalize_cadastral_number(search))
            query = query.filter(
                or_(
                    normalized_cadastral_number_expression(
                        ParcelModel.cadastral_number
                    ).like(
                        cadastral_pattern, escape="\\"
                    ),
                    ParcelModel.location.ilike(pattern, escape="\\"),
                )
            )
        if cadastral_number:
            query = query.filter(
                normalized_cadastral_number_expression(
                    ParcelModel.cadastral_number
                ).like(
                    _like_pattern(normalize_cadastral_number(cadastral_number)),
                    escape="\\",
                )
            )
        if location:
            query = query.filter(
                ParcelModel.location.ilike(_like_pattern(location), escape="\\")
            )
        if status is not None:
            query = query.filter(ParcelModel.status == status.value)

        ordered = query.order_by(ParcelModel.created_at, ParcelModel.parcel_id)
        if page is None:
            parcels = _query(lambda: ordered.all())
            result = [parcel.to_domain() for parcel in parcels]
            return result, len(result)

        total = _query(lambda: query.order_by(None).count())
        ordered = ordered.offset((page - 1) * page_size).limit(page_size)
        parcels = _query(lambda: ordered.all())
        return [parcel.to_domain() for parcel in parcels], total

    def create_parcel(self, parcel):
        if _query(lambda: db.session.get(ParcelModel, parcel.parcel_id)) is not None:
            raise InvalidInputError("A matching database record already exists.")
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

    def update_parcel(self, parcel_id, updates, *, updated_at):
        values = {
            field: value.value if hasattr(value, "value") else value
            for field, value in updates.items()
        }
        values["updated_at"] = updated_at
        result = _query(
            lambda: db.session.execute(
                update(ParcelModel)
                .where(ParcelModel.parcel_id == parcel_id)
                .values(**values)
            )
        )
        if result.rowcount != 1:
            db.session.rollback()
            raise InvalidInputError("Parcel was not found.", field="parcel_id")
        _commit()
        return self.find_by_id(parcel_id)

    def update_parcel_status(
        self, parcel_id, *, expected_status, status, updated_at
    ):
        result = _query(
            lambda: db.session.execute(
                update(ParcelModel)
                .where(
                    ParcelModel.parcel_id == parcel_id,
                    ParcelModel.status == expected_status.value,
                )
                .values(status=status.value, updated_at=updated_at)
            )
        )
        if result.rowcount != 1:
            db.session.rollback()
            raise ResourceConflictError(
                "The parcel status changed before this update could be saved."
            )
        _commit()
        return self.find_by_id(parcel_id)


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
        try:
            parcel = db.session.execute(
                db.select(ParcelModel)
                .where(ParcelModel.parcel_id == ownership.parcel_id)
                .with_for_update()
            ).scalar_one_or_none()
            if parcel is None:
                raise ResourceNotFoundError("Parcel was not found.")

            owner = db.session.get(UserModel, ownership.owner_id)
            if owner is None:
                raise ResourceNotFoundError("Owner was not found.")
            if owner.role != Role.CITIZEN.value:
                raise InvalidInputError("Ownership must be assigned to a citizen.")

            if ownership.status.value == "ACTIVE":
                existing_owner = db.session.execute(
                    db.select(OwnershipModel.ownership_id).where(
                        OwnershipModel.parcel_id == ownership.parcel_id,
                        OwnershipModel.owner_id == ownership.owner_id,
                        OwnershipModel.status == "ACTIVE",
                    )
                ).first()
                if existing_owner is not None:
                    raise ResourceConflictError(
                        "This owner already has an active ownership record "
                        "for the parcel."
                    )

                active_share = db.session.execute(
                    db.select(
                        func.coalesce(func.sum(OwnershipModel.share), 0)
                    ).where(
                        OwnershipModel.parcel_id == ownership.parcel_id,
                        OwnershipModel.status == "ACTIVE",
                    )
                ).scalar_one()
                if Decimal(str(active_share)) + ownership.share > Decimal("100"):
                    raise ResourceConflictError(
                        "Active ownership shares for a parcel cannot exceed 100%."
                    )

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
        except (InvalidInputError, ResourceConflictError, ResourceNotFoundError):
            db.session.rollback()
            raise
        except SQLAlchemyError as error:
            db.session.rollback()
            if isinstance(error, IntegrityError) and _is_active_ownership_conflict(
                error
            ):
                raise ResourceConflictError(
                    "This owner already has an active ownership record "
                    "for the parcel."
                ) from None
            raise DatabaseUnavailableError() from None

class SqlAlchemyTransferRepository:
    _ACTIVE_STATUSES = {
        "DRAFT",
        "SUBMITTED",
        "UNDER_REVIEW",
        "APPROVED",
        "BLOCKCHAIN_PENDING",
    }

    def _lock_and_validate_eligibility(self, request):
        parcel = db.session.execute(
            db.select(ParcelModel)
            .where(ParcelModel.parcel_id == request.parcel_id)
            .with_for_update()
        ).scalar_one_or_none()
        if parcel is None:
            raise ResourceNotFoundError("Parcel was not found.")
        if parcel.status != "ACTIVE":
            raise ResourceConflictError(
                "Transfers are only allowed for active parcels."
            )

        seller = db.session.get(UserModel, request.seller_id)
        if seller is None or seller.role != Role.CITIZEN.value:
            raise AuthorizationError(
                "The transfer seller must be an existing citizen."
            )

        active_ownerships = db.session.execute(
            db.select(OwnershipModel).where(
                OwnershipModel.parcel_id == request.parcel_id,
                OwnershipModel.status == "ACTIVE",
            )
        ).scalars().all()
        seller_ownerships = [
            ownership
            for ownership in active_ownerships
            if ownership.owner_id == request.seller_id
        ]
        if not seller_ownerships:
            raise AuthorizationError(
                "The seller is not a current owner of this parcel."
            )
        if (
            len(active_ownerships) != 1
            or Decimal(str(seller_ownerships[0].share)) != Decimal("100")
        ):
            raise ResourceConflictError(
                "Partial-share transfers are not supported; the seller must "
                "own 100% of the parcel."
            )

        # Canonical buyer identity is authoritative when present. The stored
        # reference is only consulted for legacy records, so a later email
        # change (or email reuse by another account) can never reassign or
        # invalidate the transfer.
        if request.buyer_id is not None:
            buyer = db.session.get(UserModel, request.buyer_id)
        else:
            buyer_reference = request.buyer_reference.strip()
            if "@" in buyer_reference:
                buyer = db.session.execute(
                    db.select(UserModel).where(
                        func.lower(UserModel.email) == buyer_reference.lower()
                    )
                ).scalar_one_or_none()
            else:
                buyer = db.session.get(UserModel, buyer_reference)
        if buyer is None:
            raise ResourceNotFoundError("The buyer was not found.")
        if buyer.role != Role.CITIZEN.value:
            raise InvalidInputError(
                "The buyer must have the CITIZEN role.",
                field="buyer_reference",
            )
        if buyer.id == request.seller_id:
            raise InvalidInputError(
                "The buyer must be different from the seller.",
                field="buyer_reference",
            )

    def create_request(self, request):
        model = TransferRequestModel(
            request_id=request.request_id,
            parcel_id=request.parcel_id,
            seller_id=request.seller_id,
            buyer_reference=request.buyer_reference,
            buyer_id=request.buyer_id,
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

    def create_request_with_audit(self, request, event):
        try:
            self._lock_and_validate_eligibility(request)

            model = TransferRequestModel(
                request_id=request.request_id,
                parcel_id=request.parcel_id,
                seller_id=request.seller_id,
                buyer_reference=request.buyer_reference,
                buyer_id=request.buyer_id,
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
            # PostgreSQL enforces the audit event's foreign key immediately,
            # and flush order is not guaranteed to place the new transfer
            # first (SQLite never caught this because it does not enforce
            # foreign keys by default). Flush the parent row explicitly so
            # the event always references an existing request.
            db.session.flush()
            db.session.add(_audit_event_model(event))
            db.session.commit()
        except (
            AuthorizationError,
            InvalidInputError,
            ResourceConflictError,
            ResourceNotFoundError,
        ):
            db.session.rollback()
            raise
        except IntegrityError as error:
            db.session.rollback()
            constraint_name = getattr(
                getattr(error.orig, "diag", None), "constraint_name", None
            )
            is_active_transfer_conflict = (
                constraint_name == "uq_transfer_requests_one_active_per_parcel"
                or str(error.orig)
                == "UNIQUE constraint failed: transfer_requests.parcel_id"
            )
            if is_active_transfer_conflict:
                raise ResourceConflictError(
                    "An active transfer request already exists for this parcel."
                ) from None
            raise InvalidInputError(
                "A matching database record already exists."
            ) from None
        except SQLAlchemyError:
            db.session.rollback()
            raise DatabaseUnavailableError() from None
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

    def list_for_buyer_id(self, buyer_id):
        models = _query(
            lambda: TransferRequestModel.query.filter_by(buyer_id=buyer_id)
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

    def list_completed_for_parcel(self, parcel_id):
        models = _query(
            lambda: TransferRequestModel.query.filter_by(
                parcel_id=parcel_id, status=TransferStatus.COMPLETED.value
            )
            .order_by(
                TransferRequestModel.created_at, TransferRequestModel.request_id
            )
            .all()
        )
        return [model.to_domain() for model in models]

    def save_request(self, request):
        model = _query(lambda: db.session.get(TransferRequestModel, request.request_id))
        if model is None:
            raise InvalidInputError("Transfer request was not found.", field="request_id")
        model.parcel_id = request.parcel_id
        model.seller_id = request.seller_id
        model.buyer_reference = request.buyer_reference
        model.buyer_id = request.buyer_id
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

    def save_request_with_audit(self, request, expected_status, event):
        try:
            if request.status in (
                TransferStatus.APPROVED,
                TransferStatus.BLOCKCHAIN_PENDING,
            ):
                self._lock_and_validate_eligibility(request)
            result = db.session.execute(
                update(TransferRequestModel)
                .where(
                    TransferRequestModel.request_id == request.request_id,
                    TransferRequestModel.status == expected_status.value,
                )
                .values(
                    parcel_id=request.parcel_id,
                    seller_id=request.seller_id,
                    buyer_reference=request.buyer_reference,
                    buyer_id=request.buyer_id,
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
                    updated_at=request.updated_at,
                )
            )
            if result.rowcount != 1:
                raise ResourceConflictError(
                    "The transfer request changed before this decision could be saved."
                )
            db.session.add(_audit_event_model(event))
            db.session.commit()
        except (
            AuthorizationError,
            InvalidInputError,
            ResourceConflictError,
            ResourceNotFoundError,
        ):
            db.session.rollback()
            raise
        except IntegrityError:
            db.session.rollback()
            raise InvalidInputError(
                "A matching database record already exists."
            ) from None
        except SQLAlchemyError:
            db.session.rollback()
            raise DatabaseUnavailableError() from None
        return request

    def finalize_ownership(
        self,
        request,
        *,
        expected_status,
        buyer_id,
        buyer_ownership_id,
        event,
    ):
        """Atomically finalize a blockchain-confirmed transfer.

        In one database transaction this locks the parcel row, moves the
        transfer to COMPLETED with compare-and-set semantics (the duplicate
        finalization guard), deactivates the seller's active ownership,
        creates the buyer's active ownership with the preserved share, and
        writes the audit event. Any failure rolls back every change.
        """
        try:
            parcel = db.session.execute(
                db.select(ParcelModel)
                .where(ParcelModel.parcel_id == request.parcel_id)
                .with_for_update()
            ).scalar_one_or_none()
            if parcel is None:
                raise ResourceNotFoundError("Parcel was not found.")
            if parcel.status != "ACTIVE":
                raise ResourceConflictError(
                    "Transfers are only allowed for active parcels."
                )

            result = db.session.execute(
                update(TransferRequestModel)
                .where(
                    TransferRequestModel.request_id == request.request_id,
                    TransferRequestModel.status == expected_status.value,
                )
                .values(
                    status=TransferStatus.COMPLETED.value,
                    blockchain_tx_id=request.blockchain_tx_id,
                    blockchain_status=BlockchainSubmissionStatus.CONFIRMED.value,
                    failure_reason=request.failure_reason,
                    updated_at=request.updated_at,
                )
            )
            if result.rowcount != 1:
                db.session.rollback()
                stored = db.session.get(
                    TransferRequestModel, request.request_id
                )
                if (
                    stored is not None
                    and stored.status == TransferStatus.COMPLETED.value
                    and stored.blockchain_tx_id == request.blockchain_tx_id
                ):
                    # Repeated confirmation notification: already finalized.
                    return stored.to_domain()
                raise ResourceConflictError(
                    "The transfer request changed before ownership could be "
                    "finalized."
                )

            active_ownerships = (
                db.session.execute(
                    db.select(OwnershipModel).where(
                        OwnershipModel.parcel_id == request.parcel_id,
                        OwnershipModel.status == OwnershipStatus.ACTIVE.value,
                    )
                )
                .scalars()
                .all()
            )
            seller_rows = [
                ownership
                for ownership in active_ownerships
                if ownership.owner_id == request.seller_id
            ]
            if not seller_rows:
                raise AuthorizationError(
                    "The seller is not a current owner of this parcel."
                )
            if (
                len(active_ownerships) != 1
                or Decimal(str(seller_rows[0].share)) != Decimal("100")
            ):
                raise ResourceConflictError(
                    "Partial-share transfers are not supported; the seller "
                    "must own 100% of the parcel."
                )
            share = Decimal(str(seller_rows[0].share))

            seller = db.session.get(UserModel, request.seller_id)
            if seller is None or seller.role != Role.CITIZEN.value:
                raise AuthorizationError(
                    "The transfer seller must be an existing citizen."
                )

            buyer = db.session.get(UserModel, buyer_id)
            if buyer is None:
                raise ResourceNotFoundError("The buyer was not found.")
            if buyer.role != Role.CITIZEN.value:
                raise InvalidInputError(
                    "The buyer must have the CITIZEN role.",
                    field="buyer_reference",
                )
            if buyer.id == request.seller_id:
                raise InvalidInputError(
                    "The buyer must be different from the seller.",
                    field="buyer_reference",
                )
            if any(
                ownership.owner_id == buyer.id
                for ownership in active_ownerships
            ):
                raise ResourceConflictError(
                    "This owner already has an active ownership record "
                    "for the parcel."
                )

            deactivated = db.session.execute(
                update(OwnershipModel)
                .where(
                    OwnershipModel.ownership_id == seller_rows[0].ownership_id,
                    OwnershipModel.status == OwnershipStatus.ACTIVE.value,
                )
                .values(
                    status=OwnershipStatus.INACTIVE.value,
                    updated_at=request.updated_at,
                )
            )
            if deactivated.rowcount != 1:
                raise ResourceConflictError(
                    "The seller's ownership changed before finalization "
                    "could be saved."
                )

            db.session.add(
                OwnershipModel(
                    ownership_id=buyer_ownership_id,
                    parcel_id=request.parcel_id,
                    owner_id=buyer.id,
                    share=share,
                    status=OwnershipStatus.ACTIVE.value,
                    created_at=request.updated_at,
                    updated_at=request.updated_at,
                )
            )
            db.session.add(_audit_event_model(event))
            db.session.commit()
        except (
            AuthorizationError,
            InvalidInputError,
            ResourceConflictError,
            ResourceNotFoundError,
        ):
            db.session.rollback()
            raise
        except IntegrityError as error:
            db.session.rollback()
            if _is_active_ownership_conflict(error):
                raise ResourceConflictError(
                    "This owner already has an active ownership record "
                    "for the parcel."
                ) from None
            raise InvalidInputError(
                "A matching database record already exists."
            ) from None
        except SQLAlchemyError:
            db.session.rollback()
            raise DatabaseUnavailableError() from None

        model = db.session.get(TransferRequestModel, request.request_id)
        return model.to_domain() if model is not None else request

    def record_audit_event(self, event):
        model = _audit_event_model(event)
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


def _audit_event_model(event):
    return TransferAuditEventModel(
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
    if app.config.get("DOCUMENT_HASH_REPOSITORY") is None:
        app.config["DOCUMENT_HASH_REPOSITORY"] = SqlAlchemyDocumentHashRepository()
    if app.config.get("BLOCKCHAIN_GATEWAY") is None:
        # Honest default until Person 1 injects the real integration gateway.
        from app.transfers.blockchain import UnavailableBlockchainGateway

        app.config["BLOCKCHAIN_GATEWAY"] = UnavailableBlockchainGateway()


class SqlAlchemyDocumentHashRepository:
    """Persistence layer for stored document hashes."""

    def create_document_hash(self, document_hash):
        model = DocumentHashModel(
            document_id=document_hash.document_id,
            parcel_id=document_hash.parcel_id,
            document_name=document_hash.document_name,
            document_hash=document_hash.document_hash,
            uploaded_by=document_hash.uploaded_by,
            uploaded_at=document_hash.uploaded_at,
            verification_count=document_hash.verification_count,
            last_verified_at=document_hash.last_verified_at,
            last_verification_status=(
                document_hash.last_verification_status.value
                if document_hash.last_verification_status is not None
                else None
            ),
        )
        db.session.add(model)
        _commit()
        return model.to_domain()

    def find_by_id(self, document_id):
        model = _query(lambda: db.session.get(DocumentHashModel, document_id))
        return model.to_domain() if model is not None else None

    def find_by_name_and_parcel(self, document_name, parcel_id):
        query = DocumentHashModel.query.filter_by(
            document_name=document_name.strip(), parcel_id=parcel_id
        )
        model = _query(lambda: query.first())
        return model.to_domain() if model is not None else None

    def increment_verification(self, document_id, verified_at, status):
        result = _query(
            lambda: db.session.execute(
                update(DocumentHashModel)
                .where(DocumentHashModel.document_id == document_id)
                .values(
                    verification_count=DocumentHashModel.verification_count + 1,
                    last_verified_at=verified_at,
                    last_verification_status=status.value,
                )
            )
        )
        if result.rowcount != 1:
            raise ResourceNotFoundError("Document hash was not found.")
        _commit()

    def list_document_hashes(self, *, parcel_id=None):
        query = DocumentHashModel.query
        if parcel_id is not None:
            query = query.filter_by(parcel_id=parcel_id)
        models = _query(
            lambda: query.order_by(DocumentHashModel.uploaded_at.desc()).all()
        )
        return [model.to_domain() for model in models]