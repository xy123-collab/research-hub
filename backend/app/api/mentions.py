"""@提及候选检索接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user
from ..models.user import User
from ..services.mentions import candidates

router = APIRouter(tags=["mentions"])


@router.get("/mentions/candidates")
def mention_candidates(q: str = "", scope_type: str = "", scope_id: int | None = None,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回可@对象：我所在的数据集/课题组（可@整组）+ 范围内单个成员（关键词检索名称/ID）。"""
    return candidates(db, user, q=q, scope_type=scope_type, scope_id=scope_id)
