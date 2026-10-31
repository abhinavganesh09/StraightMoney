"""
audit.py — Helper to persist immutable audit log entries.
"""

import json
from typing import Any, Optional

from sqlalchemy.orm import Session

from models import AuditLog


def log(
    db: Session,
    *,
    actor: str,
    action: str,
    campaign_id: Optional[int] = None,
    invoice_id: Optional[int] = None,
    detail: Optional[Any] = None,
) -> AuditLog:
    """
    Create and commit an AuditLog row.

    Args:
        db:          Active SQLAlchemy session.
        actor:       Human-readable actor label (e.g., "system", "verifier:alice").
        action:      Short action string (e.g., "invoice.submitted", "payout.triggered").
        campaign_id: Optional campaign context.
        invoice_id:  Optional invoice context.
        detail:      Extra context — dict (JSON-serialised) or plain string.

    Returns:
        The persisted AuditLog instance.
    """
    if isinstance(detail, dict):
        detail_str: Optional[str] = json.dumps(detail)
    elif detail is not None:
        detail_str = str(detail)
    else:
        detail_str = None

    entry = AuditLog(
        actor=actor,
        action=action,
        campaign_id=campaign_id,
        invoice_id=invoice_id,
        detail=detail_str,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
