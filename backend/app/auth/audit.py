"""Audit logging for admin user-management actions.

Records who did what to which account, and when. Events carry only
non-sensitive identifiers (actor id, actor role, target user id, role and
activation transitions). Passwords, password hashes, JWTs, secrets, and any
authentication material are never recorded.

Recorder selection:

- ``DatabaseAdminAuditRecorder``: production default. It is a *marker*
  recorder: the SQLAlchemy user repository writes the audit event row into
  the ``admin_audit_events`` table inside the SAME transaction as the admin
  mutation (via the ``audit_event_factory`` the user-management service
  passes to the repository). If the audit insert fails, the mutation rolls
  back; a successful response always implies a persisted audit record.
  ``record()`` is never called on it — calling it raises, because a
  separate write would break atomicity.
- ``LoggingAdminAuditRecorder``: best-effort JSON log recorder for isolated
  tests/development (not durable).
- ``InMemoryAdminAuditRecorder``: list-backed, primarily for tests.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.models import Role, utc_now

logger = logging.getLogger("app.audit.admin")

EVENT_USER_CREATED = "USER_CREATED"
EVENT_USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
EVENT_USER_ACTIVATED = "USER_ACTIVATED"
EVENT_USER_DEACTIVATED = "USER_DEACTIVATED"

ADMIN_AUDIT_EVENT_TYPES = frozenset(
    {
        EVENT_USER_CREATED,
        EVENT_USER_ROLE_CHANGED,
        EVENT_USER_ACTIVATED,
        EVENT_USER_DEACTIVATED,
    }
)


@dataclass(frozen=True)
class AdminAuditEvent:
    event_id: str
    event_type: str
    actor_id: str
    actor_role: Role
    target_user_id: str
    created_at: datetime
    # Safe, non-secret context only (e.g. from_role/to_role, role).
    detail: dict = field(default_factory=dict)

    def to_safe_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "actor_role": Role(self.actor_role).value,
            "target_user_id": self.target_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "detail": dict(self.detail),
        }


class AdminAuditRecorder(Protocol):
    persists_to_database: bool

    def record(self, event: AdminAuditEvent) -> None: ...


def build_admin_audit_event(
    event_type: str,
    *,
    actor_id: str,
    actor_role: Role,
    target_user_id: str,
    detail: dict | None = None,
) -> AdminAuditEvent:
    if event_type not in ADMIN_AUDIT_EVENT_TYPES:
        raise ValueError("Unsupported admin audit event type.")
    return AdminAuditEvent(
        event_id=f"admin-audit-{uuid.uuid4().hex[:24]}",
        event_type=event_type,
        actor_id=actor_id,
        actor_role=Role(actor_role),
        target_user_id=target_user_id,
        created_at=utc_now(),
        detail=dict(detail or {}),
    )


class DatabaseAdminAuditRecorder:
    """Production recorder marker.

    Audit rows are persisted by the SQLAlchemy repositories inside the same
    database transaction as the admin mutation, so an audit failure rolls
    the mutation back. ``record()`` is never called on this class; if it is,
    the wiring is broken and we fail loudly rather than pretend the event
    was audited.
    """

    persists_to_database = True

    def record(self, event: AdminAuditEvent) -> None:
        raise RuntimeError(
            "DatabaseAdminAuditRecorder events are persisted by the "
            "repository inside the mutation transaction."
        )


class LoggingAdminAuditRecorder:
    """Best-effort JSON log recorder for isolated tests/development."""

    persists_to_database = False

    def record(self, event: AdminAuditEvent) -> None:
        logger.info(
            "admin_audit_event %s",
            json.dumps(event.to_safe_dict(), sort_keys=True),
        )


class InMemoryAdminAuditRecorder:
    """Simple list-backed recorder, primarily for tests and local tooling."""

    persists_to_database = False

    def __init__(self):
        self.events: list[AdminAuditEvent] = []

    def record(self, event: AdminAuditEvent) -> None:
        self.events.append(event)
