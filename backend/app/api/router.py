"""
backend/app/api/router.py — Mount all API sub-routers.
"""

from fastapi import APIRouter

from . import auth, logins, snipes, auctions, history, cart, settings, events, websocket, admin
from .watchlist import router as watchlist_router
from .price_compare import router as price_compare_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(logins.router)
api_router.include_router(snipes.router)
api_router.include_router(auctions.router)
api_router.include_router(history.router)
api_router.include_router(cart.router)
api_router.include_router(settings.router)
api_router.include_router(events.router)
api_router.include_router(watchlist_router)
api_router.include_router(price_compare_router)

# WebSocket lives outside /api prefix (at /ws)
ws_router = websocket.router
