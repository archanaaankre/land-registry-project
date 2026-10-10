from flask import Blueprint, current_app, g, jsonify, request

from app.auth.api_service import AuthApiService
from app.auth.decorators import roles_required
from app.auth.errors import InvalidInputError
from app.models import Ownership, Parcel, Role
from app.registry.authorization import OWNERSHIP_READ_ROLES, PARCEL_READ_ROLES
from app.registry.services import OwnershipService, ParcelService

bp = Blueprint("api", __name__, url_prefix="/api")
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _auth_service():
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
    return ParcelService(current_app.config.get("PARCEL_REPOSITORY"))


def _ownership_service():
    return OwnershipService(
        current_app.config.get("OWNERSHIP_REPOSITORY"),
        current_app.config.get("PARCEL_REPOSITORY"),
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


bp.register_blueprint(auth_bp)
