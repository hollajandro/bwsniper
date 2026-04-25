"""
backend/app/dependencies.py — FastAPI dependency injection.

get_current_user  — extracts JWT from Authorization header, returns User
get_db            — re-exported from database module
"""

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db.database import get_db
from .db.models import RemoteAgent, User
from .services.remote_agent_service import authenticate_remote_agent
from .utils.jwt_utils import decode_token

_bearer = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Validate the access token and return the corresponding User."""
    payload = decode_token(creds.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires the current user to be an administrator."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def get_authenticated_remote_agent(
    agent_id: str,
    x_agent_key: str = Header(..., alias="X-Agent-Key"),
    db: Session = Depends(get_db),
) -> RemoteAgent:
    agent = authenticate_remote_agent(db, agent_id, x_agent_key)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent credentials",
        )
    return agent
