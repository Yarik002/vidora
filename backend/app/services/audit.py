import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def audit(
    session: AsyncSession,
    action: str,
    *,
    actor_id: uuid.UUID | None,
    entity_type: str | None = None,
    entity_id: Any = None,
    ip: str | None = None,
    **details: Any,
) -> None:
    """Adds an audit record to the current transaction (committed together with the change)."""
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            ip=ip,
            details={k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in details.items()},
        )
    )
