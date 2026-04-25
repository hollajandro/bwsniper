"""
Authenticated control-plane endpoints for remote redundant snipe agents.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.schemas import (
    RemoteAgentEventCreate,
    RemoteAgentSyncRequest,
    RemoteAgentSyncResponse,
)
from ..dependencies import get_authenticated_remote_agent
from ..db.models import RemoteAgent
from ..services.remote_agent_service import (
    build_sync_response,
    record_remote_agent_event,
)

router = APIRouter(prefix="/internal/remote-agents", tags=["internal-remote-agents"])


@router.post("/{agent_id}/sync", response_model=RemoteAgentSyncResponse)
def sync_remote_agent(
    agent_id: str,
    body: RemoteAgentSyncRequest,
    agent: RemoteAgent = Depends(get_authenticated_remote_agent),
    db: Session = Depends(get_db),
):
    if agent.id != agent_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return build_sync_response(db, agent, body)


@router.post("/{agent_id}/events", status_code=status.HTTP_204_NO_CONTENT)
def post_remote_agent_event(
    agent_id: str,
    body: RemoteAgentEventCreate,
    agent: RemoteAgent = Depends(get_authenticated_remote_agent),
    db: Session = Depends(get_db),
):
    if agent.id != agent_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    try:
        record_remote_agent_event(db, agent, body)
    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(ex)
        ) from ex
