from app.platform.admin_api.router import router
from app.platform.admin_api.executive import router as executive_router

router.include_router(executive_router)

__all__ = ["router"]
