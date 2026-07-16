from fastapi import APIRouter
from . import (auth, users, groups, charters, datasets, bugs, code,
               posts, workspaces, skills, verify, admin, notifications,
               notify_prefs, mentions, downloads)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(groups.router)
api_router.include_router(charters.router)
api_router.include_router(datasets.router)
api_router.include_router(bugs.router)
api_router.include_router(code.router)
api_router.include_router(posts.router)
api_router.include_router(workspaces.router)
api_router.include_router(skills.router)
api_router.include_router(verify.router)
api_router.include_router(admin.router)
api_router.include_router(notifications.router)
api_router.include_router(notify_prefs.router)
api_router.include_router(mentions.router)
api_router.include_router(downloads.router)
