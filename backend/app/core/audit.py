"""审计中间件辅助 + record_contribution()。总管理员只见动作元数据。"""
from sqlalchemy.orm import Session
from ..models.governance import AuditLog, ContributionEvent


def write_audit(db: Session, user_id, action: str, object_type: str = "",
                object_id="", detail: dict | None = None, ip: str = ""):
    log = AuditLog(user_id=user_id, action=action, object_type=object_type,
                   object_id=str(object_id), detail_json=detail or {}, ip=ip)
    db.add(log)
    db.flush()
    return log


def record_contribution(db: Session, user_id, event_type: str, ref_type: str = "",
                        ref_id="", dataset_id=None, weight: float = 1.0):
    """一切公共投入统一落账（见 5.6 / 6.5）。"""
    ev = ContributionEvent(user_id=user_id, dataset_id=dataset_id, event_type=event_type,
                           ref_type=ref_type, ref_id=str(ref_id), weight=weight)
    db.add(ev)
    db.flush()
    return ev
