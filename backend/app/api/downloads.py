"""历史下载：本人跨数据集与其它位置的下载记录（时间 + 文件名 + 位置）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import timedelta
from ..core.db import get_db
from ..core.permissions import get_current_user
from ..models.user import User
from ..models.notify import DownloadHistory

router = APIRouter(tags=["downloads"])

_SOURCE_LABEL = {
    "dataset_version": "数据集版本", "code": "处理代码",
    "bug_attachment": "勘误附件", "skill": "Skill 协作", "post_attachment": "讨论区附件",
}


def _bj(dt):
    return (dt + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M") if dt else ""


@router.get("/me/downloads")
def my_downloads(dataset_id: int | None = None, source: str | None = None,
                 limit: int = 200, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """我的历史下载。可按数据集或来源筛选。数据集页与个人主页共用同一接口。"""
    q = db.query(DownloadHistory).filter_by(user_id=user.id)
    if dataset_id:
        q = q.filter(DownloadHistory.dataset_id == dataset_id)
    if source:
        q = q.filter(DownloadHistory.source == source)
    rows = q.order_by(DownloadHistory.id.desc()).limit(min(limit, 500)).all()
    return {"items": [{
        "id": r.id, "source": r.source,
        "source_label": _SOURCE_LABEL.get(r.source, r.source),
        "dataset_id": r.dataset_id, "location": r.location_label,
        "detail": r.detail, "file_name": r.file_name, "link": r.link,
        "downloaded_at": _bj(r.downloaded_at),
    } for r in rows], "total": q.count()}
