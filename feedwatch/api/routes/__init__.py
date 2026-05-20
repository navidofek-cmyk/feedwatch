from .feeds import router as feeds_router
from .articles import router as articles_router
from .actions import router as actions_router

__all__ = ["feeds_router", "articles_router", "actions_router"]
