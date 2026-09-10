from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.conversations import router as conversations_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.farms import router as farms_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.profiles import router as profiles_router
from app.api.v1.routes.users import router as users_router
from app.api.v1.routes.weather import router as weather_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["authentication"])
api_router.include_router(conversations_router, tags=["conversations"])
api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(profiles_router, tags=["farmer-profile"])
api_router.include_router(farms_router, tags=["farms-and-crops"])
api_router.include_router(users_router, tags=["users"])
api_router.include_router(weather_router, tags=["weather"])
