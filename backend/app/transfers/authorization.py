from app.models import Role

TRANSFER_SUBMIT_ROLES = (Role.CITIZEN,)
TRANSFER_READ_ROLES = (Role.CITIZEN, Role.REGISTRAR, Role.ADMIN)
TRANSFER_REVIEW_ROLES = (Role.REGISTRAR,)
# Finalization is never client-driven: only trusted server-side actors may
# trigger it, and the blockchain confirmation itself always comes from the
# gateway, never from the caller.
TRANSFER_FINALIZE_ROLES = (Role.REGISTRAR, Role.ADMIN)