from flask import Blueprint, current_app, g, jsonify, request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.auth.api_service import AuthApiService
from app.auth.decorators import roles_required
from app.auth.errors import (
    AuthorizationError,
    InvalidInputError,
    PayloadTooLargeError,
    ResourceNotFoundError,
)
from app.auth.user_management import AdminUserService
from app.document_integrity.service import DocumentIntegrityService
from app.models import Ownership, Parcel, Role, TransferRequest
from app.registry.authorization import (
    OWNERSHIP_READ_ROLES,
    OWNERSHIP_RECORD_ROLES,
    PARCEL_MANAGE_ROLES,
    PARCEL_READ_ROLES,
)
from app.registry.merkle import (
    generate_proof,
    merkle_root,
    sorted_leaves,
    verify_merkle_proof,
)
from app.registry.services import OwnershipService, ParcelService
from app.registry.validation import validate_identifier, validate_parcel_search_data
from app.persistence.repositories import repository_bootstrap
from app.transfers.authorization import (
    TRANSFER_READ_ROLES,
    TRANSFER_REVIEW_ROLES,
    TRANSFER_SUBMIT_ROLES,
)
from app.transfers.services import TransferService
from app.transfers.validation import (
    validate_request_id,
    validate_review_decision,
)

bp = Blueprint("api", __name__, url_prefix="/api")
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
document_bp = Blueprint("document", __name__, url_prefix="/documents")


def _auth_service():
    repository_bootstrap(current_app)
    service = current_app.extensions.get("auth_api_service")
    if service is None:
        repository = current_app.config.get("AUTH_USER_REPOSITORY")
        service = AuthApiService(repository)
        current_app.extensions["auth_api_service"] = service
    return service


def _admin_user_service():
    repository_bootstrap(current_app)
    repository = current_app.config.get("AUTH_USER_REPOSITORY")
    if repository is None:
        from app.auth.errors import AuthenticationUnavailableError

        raise AuthenticationUnavailableError()
    return AdminUserService(repository)


def _json_body():
    body = request.get_json(silent=True)
    if body is None:
        raise InvalidInputError("A valid JSON request body is required.")
    return body


def _admin_service():
    return _auth_service()


def _document_service():
    repository_bootstrap(current_app)
    return DocumentIntegrityService(
        current_app.config.get("DOCUMENT_HASH_REPOSITORY"),
        current_app.config.get("OWNERSHIP_REPOSITORY"),
        supporting_document_repository=current_app.config.get(
            "DOCUMENT_SUPPORTING_REPOSITORY"
        ),
        transfer_repository=current_app.config.get("TRANSFER_REPOSITORY"),
    )


def _read_uploaded_document(uploaded_file):
    """Read an uploaded document in bounded chunks.

    The size cap is enforced while streaming so an oversized upload never has
    to be materialised in memory first. Oversized requests receive the same
    structured AuthError JSON response as other API failures.
    """
    max_bytes = current_app.config.get("MAX_DOCUMENT_UPLOAD_BYTES", 10 * 1024 * 1024)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        max_bytes = 10 * 1024 * 1024

    chunks = []
    total = 0
    while True:
        chunk = uploaded_file.stream.read(min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError()
        chunks.append(chunk)
    return b"".join(chunks)


def _user_response(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


def _parcel_service():
    repository_bootstrap(current_app)
    return ParcelService(current_app.config.get("PARCEL_REPOSITORY"))


def _ownership_service():
    repository_bootstrap(current_app)
    return OwnershipService(
        current_app.config.get("OWNERSHIP_REPOSITORY"),
        current_app.config.get("PARCEL_REPOSITORY"),
    )


def _transfer_service():
    repository_bootstrap(current_app)
    return TransferService(
        current_app.config.get("TRANSFER_REPOSITORY"),
        current_app.config.get("PARCEL_REPOSITORY"),
        current_app.config.get("OWNERSHIP_REPOSITORY"),
        current_app.config.get("AUTH_USER_REPOSITORY"),
        blockchain_gateway=current_app.config.get("BLOCKCHAIN_GATEWAY"),
    )


def _parcel_response(parcel: Parcel):
    return {
        "parcel_id": parcel.parcel_id,
        "cadastral_number": parcel.cadastral_number,
        "location": parcel.location,
        "area": str(parcel.area),
        "area_unit": parcel.area_unit.value,
        "status": parcel.status.value,
        "created_by": parcel.created_by,
        "created_at": parcel.created_at.isoformat(),
        "updated_at": parcel.updated_at.isoformat(),
    }


def _ownership_response(ownership: Ownership):
    return {
        "ownership_id": ownership.ownership_id,
        "parcel_id": ownership.parcel_id,
        "owner_id": ownership.owner_id,
        "share": str(ownership.share),
        "status": ownership.status.value,
        "created_at": ownership.created_at.isoformat(),
        "updated_at": ownership.updated_at.isoformat(),
    }


def _database_available():
    """Confirm the configured database answers a trivial query.

    Returns a plain boolean so the health response can never leak connection
    details, SQL, or exception text.
    """
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        return False
    return True


@bp.route("/health", methods=["GET"])
def health():
    if not _database_available():
        return (
            jsonify({"status": "unavailable", "service": "land-registry-backend"}),
            503,
        )
    return jsonify({"status": "ok", "service": "land-registry-backend"})


@auth_bp.route("/register", methods=["POST"])
def register():
    result = _auth_service().register(_json_body())
    return jsonify(result), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    return jsonify(_auth_service().login(_json_body()))


@auth_bp.route("/me", methods=["GET"])
@roles_required(
    Role.CITIZEN,
    Role.REGISTRAR,
    Role.VERIFICATION_OFFICER,
    Role.ADMIN,
)
def current_user():
    repository = current_app.config.get("AUTH_USER_REPOSITORY")
    if repository is not None:
        user = repository.get_user_by_id(g.current_user_id)
        if user is not None and not user.is_active:
            raise AuthorizationError("Account is deactivated.")
    return jsonify(
        {
            "user": {
                "id": g.current_user_id,
                "role": g.current_user_role.value,
            }
        }
    )


def _validate_admin_role_filter(value):
    if value is None:
        return None
    try:
        return Role(value)
    except (TypeError, ValueError):
        raise InvalidInputError("Unsupported role.", field="role")


def _validate_admin_active_filter(value):
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise InvalidInputError("is_active must be 'true' or 'false'.", field="is_active")


@bp.route("/admin/users", methods=["POST"])
@roles_required(Role.ADMIN)
def create_admin_user():
    result = _admin_service().create_admin_user(
        _json_body(), actor_id=g.current_user_id, actor_role=g.current_user_role
    )
    return jsonify(result), 201


@bp.route("/admin/users", methods=["GET"])
@roles_required(Role.ADMIN)
def list_admin_users():
    users = _admin_service().list_users(
        search=request.args.get("search"),
        role=_validate_admin_role_filter(request.args.get("role")),
        is_active=_validate_admin_active_filter(request.args.get("is_active")),
    )
    payload = [_user_response(user) for user in users]
    return jsonify({"users": payload, "items": payload})


def _admin_safe_user(user):
    """Safe user view for Admin detail responses (no timestamps)."""
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
    }


@bp.route("/admin/users/<user_id>", methods=["GET"])
@roles_required(Role.ADMIN)
def get_admin_user(user_id):
    return jsonify({"user": _admin_safe_user(_admin_service().get_user(user_id))})


@bp.route("/admin/users/<user_id>/role", methods=["PATCH"])
@roles_required(Role.ADMIN)
def update_admin_user_role(user_id):
    body = _json_body()
    if "role" not in body:
        raise InvalidInputError("Required fields are missing: role.", field="role")
    user = _admin_service().update_user_role(
        user_id,
        body["role"],
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
    )
    return jsonify({"user": _user_response(user)})


@bp.route("/admin/users/<user_id>/status", methods=["PATCH"])
@roles_required(Role.ADMIN)
def update_admin_user_status(user_id):
    body = _json_body()
    if "is_active" not in body:
        raise InvalidInputError(
            "Required fields are missing: is_active.", field="is_active"
        )
    if not isinstance(body["is_active"], bool):
        raise InvalidInputError("is_active must be a boolean.", field="is_active")
    user = _admin_service().update_user_active_status(
        user_id,
        body["is_active"],
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
    )
    return jsonify({"user": _user_response(user)})


@bp.route("/parcels", methods=["GET"])
@roles_required(*PARCEL_READ_ROLES)
def list_parcels():
    filters, pagination_requested = validate_parcel_search_data(request.args)
    if not filters:
        parcels = _parcel_service().list_parcels()
        return jsonify({"items": [_parcel_response(parcel) for parcel in parcels]})

    parcels, total = _parcel_service().search_parcels(**filters)
    response = {"items": [_parcel_response(parcel) for parcel in parcels]}
    if pagination_requested:
        page = filters["page"]
        page_size = filters["page_size"]
        response["pagination"] = {
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": (total + page_size - 1) // page_size,
        }
    return jsonify(response)


@bp.route("/parcels", methods=["POST"])
@roles_required(*PARCEL_MANAGE_ROLES)
def create_parcel():
    parcel = _parcel_service().create_parcel(
        _json_body(), creator_id=g.current_user_id
    )
    return jsonify({"parcel": _parcel_response(parcel)}), 201


@bp.route("/parcels/<parcel_id>", methods=["PATCH"])
@roles_required(*PARCEL_MANAGE_ROLES)
def update_parcel(parcel_id):
    parcel = _parcel_service().update_parcel(parcel_id, _json_body())
    return jsonify({"parcel": _parcel_response(parcel)})


@bp.route("/parcels/<parcel_id>/status", methods=["PATCH"])
@roles_required(*PARCEL_MANAGE_ROLES)
def update_parcel_status(parcel_id):
    body = _json_body()
    if not isinstance(body, dict) or set(body) != {"status"}:
        raise InvalidInputError("Request body must contain only status.")
    parcel = _parcel_service().update_status(parcel_id, body["status"])
    return jsonify({"parcel": _parcel_response(parcel)})


@bp.route("/parcels/<parcel_id>", methods=["GET"])
@roles_required(*PARCEL_READ_ROLES)
def get_parcel(parcel_id):
    parcel = _parcel_service().get_parcel(parcel_id)
    return jsonify({"parcel": _parcel_response(parcel)})


@bp.route("/parcels/<parcel_id>/ownership", methods=["GET"])
@roles_required(*OWNERSHIP_READ_ROLES)
def list_parcel_ownership(parcel_id):
    records = _ownership_service().list_for_parcel(parcel_id)
    return jsonify({"items": [_ownership_response(record) for record in records]})


@bp.route("/parcels/<parcel_id>/ownership/current", methods=["GET"])
@roles_required(*OWNERSHIP_READ_ROLES)
def list_current_parcel_ownership(parcel_id):
    records = _ownership_service().list_current_for_parcel(parcel_id)
    return jsonify({"items": [_ownership_response(record) for record in records]})


@bp.route("/parcels/<parcel_id>/ownership/history", methods=["GET"])
@roles_required(*OWNERSHIP_READ_ROLES)
def list_parcel_ownership_history(parcel_id):
    records = _ownership_service().list_history_for_parcel(parcel_id)
    return jsonify({"items": [_ownership_response(record) for record in records]})


@bp.route("/parcels/<parcel_id>/ownership/events", methods=["GET"])
@roles_required(*OWNERSHIP_READ_ROLES)
def list_parcel_ownership_events(parcel_id):
    """Traceable provenance of finalized transfers for a parcel."""
    events = _transfer_service().list_ownership_events(parcel_id)
    return jsonify({"items": events})


@bp.route("/ownership", methods=["POST"])
@roles_required(*OWNERSHIP_RECORD_ROLES)
def create_ownership():
    ownership = _ownership_service().create_ownership(_json_body())
    return jsonify({"ownership": _ownership_response(ownership)}), 201


@bp.route("/ownership/<ownership_id>", methods=["GET"])
@roles_required(*OWNERSHIP_READ_ROLES)
def get_ownership(ownership_id):
    ownership = _ownership_service().get_ownership(ownership_id)
    return jsonify({"ownership": _ownership_response(ownership)})


def _merkle_leaf_state(parcel_id):
    """Return (sorted leaves, ordered records) for a parcel's ownership rows."""
    records = _ownership_service().list_for_parcel(parcel_id)
    ordered = sorted(records, key=lambda record: record.ownership_id)
    return sorted_leaves(records), ordered


def _find_ownership_index(ordered, ownership_id):
    for index, record in enumerate(ordered):
        if record.ownership_id == ownership_id:
            return index
    return None


@bp.route("/parcels/<parcel_id>/ownership/merkle-root", methods=["GET"])
@roles_required(*OWNERSHIP_READ_ROLES)
def get_parcel_ownership_merkle_root(parcel_id):
    leaves, _ordered = _merkle_leaf_state(parcel_id)
    return jsonify(
        {
            "parcel_id": parcel_id,
            "merkle_root": merkle_root(leaves),
            "ownership_count": len(leaves),
        }
    )


@bp.route("/parcels/<parcel_id>/ownership/proofs", methods=["POST"])
@roles_required(*OWNERSHIP_READ_ROLES)
def get_ownership_merkle_proof(parcel_id):
    body = _json_body()
    if not isinstance(body, dict):
        raise InvalidInputError("A valid JSON request body is required.")
    if not isinstance(body.get("ownership_id"), str):
        raise InvalidInputError("Required fields are missing: ownership_id.")
    ownership_id = validate_identifier(body["ownership_id"], "ownership_id")
    leaves, ordered = _merkle_leaf_state(parcel_id)
    index = _find_ownership_index(ordered, ownership_id)
    if index is None:
        raise ResourceNotFoundError("Ownership was not found.")
    return jsonify(
        {
            "parcel_id": parcel_id,
            "merkle_root": merkle_root(leaves),
            "ownership_id": ownership_id,
            "leaf": leaves[index],
            "leaf_index": index,
            "proof": generate_proof(leaves, index),
        }
    )


@bp.route("/parcels/<parcel_id>/ownership/proof-verify", methods=["POST"])
@roles_required(*OWNERSHIP_READ_ROLES)
def verify_ownership_merkle_proof(parcel_id):
    body = _json_body()
    if not isinstance(body, dict):
        raise InvalidInputError("A valid JSON request body is required.")
    if not isinstance(body.get("ownership_id"), str):
        raise InvalidInputError("Required fields are missing: ownership_id.")
    ownership_id = validate_identifier(body["ownership_id"], "ownership_id")
    leaves, ordered = _merkle_leaf_state(parcel_id)
    index = _find_ownership_index(ordered, ownership_id)
    if index is None:
        raise ResourceNotFoundError("Ownership was not found.")
    proof = body.get("proof")
    if not isinstance(proof, list):
        raise InvalidInputError(
            "Invalid proof: expected a list of {hash, side} steps."
        )
    for step in proof:
        if not isinstance(step, dict):
            raise InvalidInputError("Invalid proof: steps must be objects.")
        if not isinstance(step.get("hash"), str) or len(step["hash"]) != 64:
            raise InvalidInputError(
                "Invalid proof: each step requires a 64-character hex hash."
            )
        if step.get("side") not in ("left", "right"):
            raise InvalidInputError(
                "Invalid proof: each step requires side to be 'left' or 'right'."
            )
        if any(c not in "0123456789abcdef" for c in step["hash"]):
            raise InvalidInputError("Invalid proof: hash must be lowercase hex.")
    root = merkle_root(leaves)
    valid = verify_merkle_proof(root, leaves[index], proof)
    response = {
        "valid": valid,
        "merkle_root": root,
        "parcel_id": parcel_id,
        "ownership_id": ownership_id,
        "leaf_index": index,
    }
    if not valid:
        response["reason"] = "Merkle root mismatch."
    return jsonify(response)


def _transfer_response(transfer: TransferRequest):
    return {
        "request_id": transfer.request_id,
        "parcel_id": transfer.parcel_id,
        "seller_id": transfer.seller_id,
        "buyer_reference": transfer.buyer_reference,
        "buyer_id": transfer.buyer_id,
        "status": transfer.status.value,
        "reviewer_id": transfer.reviewer_id,
        "review_reason": transfer.review_reason,
        "reviewed_at": transfer.reviewed_at.isoformat()
        if transfer.reviewed_at is not None
        else None,
        "blockchain_tx_id": transfer.blockchain_tx_id,
        "blockchain_status": transfer.blockchain_status.value
        if transfer.blockchain_status is not None
        else None,
        "failure_reason": transfer.failure_reason,
        "created_at": transfer.created_at.isoformat(),
        "updated_at": transfer.updated_at.isoformat(),
    }


def _audit_response(event):
    return {
        "event_id": event.event_id,
        "request_id": event.request_id,
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "actor_role": event.actor_role.value,
        "from_status": event.from_status.value if event.from_status is not None else None,
        "to_status": event.to_status.value,
        "reason": event.reason,
        "created_at": event.created_at.isoformat(),
    }


@bp.route("/transfers", methods=["POST"])
@roles_required(*TRANSFER_SUBMIT_ROLES)
def create_transfer():
    service = _transfer_service()
    payload = _json_body()
    role = g.current_user_role
    transfer = service.submit_transfer(
        g.current_user_id, payload, actor_role=role
    )
    return jsonify({"transfer": _transfer_response(transfer)}), 201


@bp.route("/transfers", methods=["GET"])
@roles_required(*TRANSFER_READ_ROLES)
def list_transfers():
    service = _transfer_service()
    transfers = service.list_for_actor(g.current_user_id, g.current_user_role)
    return jsonify({"items": [_transfer_response(transfer) for transfer in transfers]})


@bp.route("/transfers/<request_id>", methods=["GET"])
@roles_required(*TRANSFER_READ_ROLES)
def get_transfer(request_id):
    service = _transfer_service()
    request_id = validate_request_id(request_id)
    transfer = service.get_request(
        g.current_user_id, g.current_user_role, request_id
    )
    audit_events = service.list_audit_events(
        g.current_user_id, g.current_user_role, request_id
    )
    return jsonify(
        {
            "transfer": _transfer_response(transfer),
            "history": [_audit_response(event) for event in audit_events],
        }
    )


@bp.route("/transfers/<request_id>/cancel", methods=["POST"])
@roles_required(*TRANSFER_READ_ROLES)
def cancel_transfer(request_id):
    service = _transfer_service()
    request_id = validate_request_id(request_id)
    body = request.get_json(silent=True)
    validated = validate_review_decision(body if body is not None else {})
    transfer = service.cancel_request(
        g.current_user_id, g.current_user_role, request_id, validated["reason"]
    )
    return jsonify({"transfer": _transfer_response(transfer)})


@bp.route("/registrar/transfers", methods=["GET"])
@roles_required(*TRANSFER_REVIEW_ROLES)
def list_registrar_transfers():
    service = _transfer_service()
    transfers = service.review_queue(g.current_user_role)
    return jsonify({"items": [_transfer_response(transfer) for transfer in transfers]})


@bp.route("/registrar/transfers/<request_id>/review", methods=["POST"])
@roles_required(*TRANSFER_REVIEW_ROLES)
def start_transfer_review(request_id):
    service = _transfer_service()
    request_id = validate_request_id(request_id)
    body = request.get_json(silent=True)
    validated = validate_review_decision(body if body is not None else {})
    transfer = service.start_review(
        g.current_user_id, g.current_user_role, request_id, validated["reason"]
    )
    return jsonify({"transfer": _transfer_response(transfer)})


@bp.route("/registrar/transfers/<request_id>/approve", methods=["POST"])
@roles_required(*TRANSFER_REVIEW_ROLES)
def approve_transfer(request_id):
    service = _transfer_service()
    request_id = validate_request_id(request_id)
    body = request.get_json(silent=True)
    validated = validate_review_decision(body if body is not None else {})
    transfer = service.approve_request(
        g.current_user_id, g.current_user_role, request_id, validated["reason"]
    )
    return jsonify({"transfer": _transfer_response(transfer)})


@bp.route("/registrar/transfers/<request_id>/reject", methods=["POST"])
@roles_required(*TRANSFER_REVIEW_ROLES)
def reject_transfer(request_id):
    service = _transfer_service()
    request_id = validate_request_id(request_id)
    body = _json_body()
    validated = validate_review_decision(body, require_reason=True)
    transfer = service.reject_request(
        g.current_user_id, g.current_user_role, request_id, validated["reason"]
    )
    return jsonify({"transfer": _transfer_response(transfer)})


@bp.route(
    "/registrar/transfers/<request_id>/blockchain/submit", methods=["POST"]
)
@roles_required(*TRANSFER_REVIEW_ROLES)
def submit_transfer_to_blockchain(request_id):
    """Submit an approved transfer through the blockchain gateway.

    This only starts submission; it never confirms a transaction and never
    changes ownership. Confirmation is processed server-side by
    TransferService.finalize_transfer() using the trusted gateway.
    """
    service = _transfer_service()
    request_id = validate_request_id(request_id)
    transfer = service.submit_to_blockchain(
        g.current_user_id, g.current_user_role, request_id
    )
    return jsonify({"transfer": _transfer_response(transfer)})


# Single Admin user-management API is defined above on `bp` (Person 1's
# guarded implementation). Person 2's duplicate /admin/users routes were
# removed; only the statistics endpoint is retained here.
@bp.route("/admin/stats", methods=["GET"])
@roles_required(Role.ADMIN)
def admin_stats():
    service = _admin_service()
    users = service.list_users()
    user_counts = {}
    for role in Role:
        user_counts[role.value] = sum(1 for u in users if u.role == role)
    active_users = sum(1 for u in users if u.is_active)
    inactive_users = sum(1 for u in users if not u.is_active)

    parcel_repository = current_app.config.get("PARCEL_REPOSITORY")
    transfer_repository = current_app.config.get("TRANSFER_REPOSITORY")

    parcel_count = 0
    if parcel_repository is not None:
        parcels = parcel_repository.list_parcels()
        parcel_count = len(parcels)

    transfer_count = 0
    if transfer_repository is not None:
        transfers = transfer_repository.list_all()
        transfer_count = len(transfers)

    return jsonify({
        "users": {
            "total": len(users),
            "active": active_users,
            "inactive": inactive_users,
            "by_role": user_counts,
        },
        "parcels": {"total": parcel_count},
        "transfers": {"total": transfer_count},
    })


def _supporting_document_response(document):
    return {
        "supporting_document_id": document.supporting_document_id,
        "document_name": document.document_name,
        "document_hash": document.document_hash,
        "parcel_id": document.parcel_id,
        "transfer_request_id": document.transfer_request_id,
        "content_type": document.content_type,
        "uploaded_by": document.uploaded_by,
        "uploaded_at": document.uploaded_at.isoformat(),
    }


@document_bp.route("/upload", methods=["POST"])
@roles_required(Role.REGISTRAR, Role.VERIFICATION_OFFICER, Role.CITIZEN)
def upload_supporting_document():
    """Persist a supporting document without creating a trusted baseline.

    Accepts multipart/form-data with:
    - document: the file to persist
    - document_name: human-readable name
    - parcel_id: optional parcel association
    - transfer_request_id: optional transfer request association
    - content_type: optional validated client-declared content type
    """
    service = _document_service()
    if "document" not in request.files:
        raise InvalidInputError("A document file is required.", field="document")
    uploaded_file = request.files["document"]
    if uploaded_file.filename == "":
        raise InvalidInputError("A document file is required.", field="document")
    document_name = request.form.get("document_name", "")
    if not document_name:
        raise InvalidInputError("A document name is required.", field="document_name")
    document_content = _read_uploaded_document(uploaded_file)
    document = service.upload_supporting_document(
        document_name=document_name,
        document_content=document_content,
        parcel_id=request.form.get("parcel_id") or None,
        transfer_request_id=request.form.get("transfer_request_id") or None,
        content_type=request.form.get("content_type") or uploaded_file.content_type,
        uploaded_by=g.current_user_id,
        actor_role=g.current_user_role,
    )
    upload = _supporting_document_response(document)
    upload["calculated_hash"] = document.document_hash
    return jsonify({"upload": upload})


@document_bp.route("/hash", methods=["POST"])
@roles_required(Role.REGISTRAR)
def store_document_hash():
    """Calculate and store the trusted SHA-256 hash of a document.

    Expects a multipart/form-data request with:
    - document: the file to hash
    - document_name: human-readable name of the document
    - parcel_id: optional parcel ID the document relates to
    """
    service = _document_service()
    if "document" not in request.files:
        raise InvalidInputError(
            "A document file is required.", field="document"
        )
    uploaded_file = request.files["document"]
    if uploaded_file.filename == "":
        raise InvalidInputError(
            "A document file is required.", field="document"
        )
    document_name = request.form.get("document_name", "")
    if not document_name:
        raise InvalidInputError(
            "A document name is required.", field="document_name"
        )
    parcel_id = request.form.get("parcel_id") or None
    document_content = _read_uploaded_document(uploaded_file)
    document = service.store_document_hash(
        document_name=document_name,
        document_content=document_content,
        uploaded_by=g.current_user_id,
        parcel_id=parcel_id,
        actor_role=g.current_user_role,
    )
    return jsonify({
        "document": {
            "document_id": document.document_id,
            "document_name": document.document_name,
            "document_hash": document.document_hash,
            "parcel_id": document.parcel_id,
            "uploaded_by": document.uploaded_by,
            "uploaded_at": document.uploaded_at.isoformat(),
            "verification_count": document.verification_count,
        }
    }), 201


@document_bp.route("/<document_id>/verify", methods=["POST"])
@roles_required(Role.CITIZEN, Role.REGISTRAR, Role.ADMIN, Role.VERIFICATION_OFFICER)
def verify_document(document_id):
    """Verify a document against its trusted stored SHA-256 hash.

    Expects a multipart/form-data request with:
    - document: the file to verify
    """
    service = _document_service()
    if "document" not in request.files:
        raise InvalidInputError(
            "A document file is required.", field="document"
        )
    uploaded_file = request.files["document"]
    document_content = _read_uploaded_document(uploaded_file)
    result = service.verify_document(
        document_id,
        document_content,
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
    )
    return jsonify({
        "verification": {
            "document_id": result.document_id,
            "document_name": result.document_name,
            "document_hash": result.document_hash,
            "calculated_hash": result.calculated_hash,
            "status": result.status.value,
            "match": result.match,
            "verified_at": result.verified_at.isoformat(),
            "parcel_id": result.parcel_id,
            "failure_reason": result.failure_reason,
        }
    })


@document_bp.route("", methods=["GET"])
@roles_required(Role.CITIZEN, Role.REGISTRAR, Role.ADMIN, Role.VERIFICATION_OFFICER)
def list_document_hashes():
    """List stored document hashes, optionally filtered by parcel."""
    service = _document_service()
    parcel_id = request.args.get("parcel_id") or None
    documents = service.get_verification_history(
        parcel_id=parcel_id,
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
    )
    return jsonify({
        "documents": [
            {
                "document_id": d.document_id,
                "document_name": d.document_name,
                "document_hash": d.document_hash,
                "parcel_id": d.parcel_id,
                "uploaded_by": d.uploaded_by,
                "uploaded_at": d.uploaded_at.isoformat(),
                "verification_count": d.verification_count,
                "last_verified_at": (
                    d.last_verified_at.isoformat()
                    if d.last_verified_at is not None
                    else None
                ),
                "last_verification_status": (
                    d.last_verification_status.value
                    if d.last_verification_status is not None
                    else None
                ),
            }
            for d in documents
        ]
    })


@document_bp.route("/<document_id>", methods=["GET"])
@roles_required(Role.CITIZEN, Role.REGISTRAR, Role.ADMIN, Role.VERIFICATION_OFFICER)
def get_document_hash(document_id):
    """Get a single stored document hash by ID."""
    service = _document_service()
    document = service.get_document_hash(
        document_id,
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
    )
    if document is None:
        raise ResourceNotFoundError("Document hash was not found.")
    return jsonify({
        "document": {
            "document_id": document.document_id,
            "document_name": document.document_name,
            "document_hash": document.document_hash,
            "parcel_id": document.parcel_id,
            "uploaded_by": document.uploaded_by,
            "uploaded_at": document.uploaded_at.isoformat(),
            "verification_count": document.verification_count,
            "last_verified_at": (
                document.last_verified_at.isoformat()
                if document.last_verified_at is not None
                else None
            ),
            "last_verification_status": (
                document.last_verification_status.value
                if document.last_verification_status is not None
                else None
            ),
        }
    })


@document_bp.route("/supporting", methods=["GET"])
@roles_required(Role.CITIZEN, Role.REGISTRAR, Role.ADMIN, Role.VERIFICATION_OFFICER)
def list_supporting_documents():
    """List supporting documents visible to the actor, optionally by parcel."""
    service = _document_service()
    documents = service.list_supporting_documents(
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
        parcel_id=request.args.get("parcel_id") or None,
    )
    return jsonify(
        {"documents": [_supporting_document_response(doc) for doc in documents]}
    )


@document_bp.route("/supporting/<supporting_document_id>", methods=["GET"])
@roles_required(Role.CITIZEN, Role.REGISTRAR, Role.ADMIN, Role.VERIFICATION_OFFICER)
def get_supporting_document(supporting_document_id):
    """Get a single supporting document's metadata by ID."""
    service = _document_service()
    document = service.get_supporting_document(
        supporting_document_id,
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
    )
    if document is None:
        raise ResourceNotFoundError("Supporting document was not found.")
    return jsonify({"document": _supporting_document_response(document)})


@document_bp.route(
    "/supporting/<supporting_document_id>/download", methods=["GET"]
)
@roles_required(Role.CITIZEN, Role.REGISTRAR, Role.ADMIN, Role.VERIFICATION_OFFICER)
def download_supporting_document(supporting_document_id):
    """Download the stored content of a supporting document."""
    service = _document_service()
    document = service.get_supporting_document(
        supporting_document_id,
        actor_id=g.current_user_id,
        actor_role=g.current_user_role,
    )
    if document is None:
        raise ResourceNotFoundError("Supporting document was not found.")
    filename = f"{document.supporting_document_id}.bin"
    return Response(
        document.data,
        mimetype=document.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


bp.register_blueprint(auth_bp)
bp.register_blueprint(admin_bp)
bp.register_blueprint(document_bp)
