"""
backend/app/api/events.py — Recent event log for the authenticated user.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import EventLog, User
from ..dependencies import get_current_user

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(
    limit: int = Query(default=200, ge=1, le=1000),
    login_id: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return recent EventLog entries for the current user, newest first."""
    q = db.query(EventLog).filter(EventLog.user_id == user.id)
    if login_id:
        q = q.filter(EventLog.login_id == login_id)
    events = q.order_by(EventLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": ev.id,
            "login_id": ev.login_id,
            "event_type": ev.event_type,
            "message": ev.message,
            "auction_id": ev.auction_id,
            "timestamp": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev in events
    ]
