from app.models import Role

PARCEL_READ_ROLES = (Role.CITIZEN, Role.REGISTRAR, Role.ADMIN)
OWNERSHIP_READ_ROLES = (Role.CITIZEN, Role.REGISTRAR, Role.ADMIN)

# Administrative access is not legal authority to record parcel or ownership changes.
PARCEL_MANAGE_ROLES = (Role.REGISTRAR,)
OWNERSHIP_RECORD_ROLES = (Role.REGISTRAR,)
