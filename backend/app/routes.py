from flask import Blueprint, current_app, g, jsonify, request

from app.auth.api_service import AuthApiService
from app.auth.decorators import roles_required
from app.auth.errors import InvalidInputError
from app.models import Ownership, Parcel, Role, TransferRequest
from app.registry.authorization import OWNERSHIP_READ_ROLES, PARCEL_READ_ROLES
from app.registry.services import OwnershipService, ParcelService
from app.persistence.repositories import repository_bootstrap
from app.transfers.authorization import (
    TRANSFER_READ_ROLES,
    TRANSFER_REVIEW_ROLES,
    TRANSFER_SUBMIT_ROLES,
)
from app.transfers.services import TransferService
from app.transfers.validation import validate_request_id, validate_review_decision

bp = Blueprint("api", __name__, url_prefix="/api")
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _auth_service():
    repository_bootstrap(current_app)
    service = current_app.extensions.get("auth_api_service")
    if service is None:
        repository = current_app.config.get("AUTH_USER_REPOSITORY")
        service = AuthApiService(repository)
        current_app.extensions["auth_api_service"] = service
    return service


def _json_body():
    body = request.get_json(silent=True)
    if body is None:
        raise InvalidInputError("A valid JSON request body is required.")
    return body


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
    )


def _parcel_response(parcel: Parcel):
    return {
        "parcel_id": parcel.parcel_id,
        "cadastral_number": parcel.cadastral_number,
        "location": parcel.location,
        "area": str(parcel.area),
        "area_unit": parcel.area_unit.value,
        "status": parcel.status.value,
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


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "land-registry-backend"})


@auth_bp.route("/register", methods=["POST"])
def register():
    result = _auth_service().register(_json_body())
    return jsonify(result), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    return jsonify(_auth_service().login(_json_body()))


@auth_bp.route("/me", methods=["GET"])
@roles_required(Role.CITIZEN, Role.REGISTRAR, Role.ADMIN)
def current_user():
    return jsonify(
        {
            "user": {
                "id": g.current_user_id,
                "role": g.current_user_role.value,
            }
        }
    )


@bp.route("/parcels", methods=["GET"])
@roles_required(*PARCEL_READ_ROLES)
def list_parcels():
    parcels = _parcel_service().list_parcels()
    return jsonify({"items": [_parcel_response(parcel) for parcel in parcels]})


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


def _transfer_response(transfer: TransferRequest):
    return {
        "request_id": transfer.request_id,
        "parcel_id": transfer.parcel_id,
        "seller_id": transfer.seller_id,
        "buyer_reference": transfer.buyer_reference,
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
    reason = None
    if isinstance(body, dict):
        reason = body.get("reason")
    transfer = service.cancel_request(g.current_user_id, request_id, reason)
    return jsonify({"transfer": _transfer_response(transfer)})


@bp.route("/registrar/transfers", methods=["GET"])
@roles_required(*TRANSFER_REVIEW_ROLES)
def list_registrar_transfers():
    service = _transfer_service()
    transfers = service.review_queue(g.current_user_role)
    return jsonify({"items": [_transfer_response(transfer) for transfer in transfers]})


@bp.route("/registrar/transfers/<request_id>/approve", methods=["POST"])
@roles_required(*TRANSFER_REVIEW_ROLES)
def approve_transfer(request_id):
    service = _transfer_service()
    request_id = validate_request_id(request_id)
    body = request.get_json(silent=True)
    reason = None
    if isinstance(body, dict):
        reason = body.get("reason")
    from app.transfers.validation import validate_review_decision

    validated = validate_review_decision({"reason": reason} if reason is not None else {})
    transfer = service.approve_request(
        g.current_user_id, request_id, validated["reason"]
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
        g.current_user_id, request_id, validated["reason"]
    )
    return jsonify({"transfer": _transfer_response(transfer)})


bp.register_blueprint(auth_bp)
