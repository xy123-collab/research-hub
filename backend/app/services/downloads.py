"""统一下载留痕：数据集版本、处理代码、勘误附件、Skill、帖子附件等所有下载
都写一条 DownloadHistory，供「历史下载」入口跨位置查看（时间 + 文件名 + 位置）。
"""
from __future__ import annotations
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from ..models.notify import DownloadHistory

log = logging.getLogger("downloads")


def log_download(db: Session, *, user_id: int, source: str, file_name: str,
                 dataset_id: int | None = None, location_label: str = "",
                 detail: str = "", link: str = "") -> None:
    """记录一次下载。失败不抛出（不影响下载本身）。"""
    try:
        db.add(DownloadHistory(
            user_id=user_id, source=source, dataset_id=dataset_id,
            location_label=location_label[:200], detail=(detail or "")[:200],
            file_name=(file_name or "")[:200], link=(link or "")[:200],
            downloaded_at=datetime.utcnow()))
    except Exception as e:
        log.warning("下载留痕失败: %s", e)
