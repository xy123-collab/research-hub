"""统一可见范围（发帖 / 项目 / skill 共用）。

四类：public 全平台公开、group 指定课题组成员可见、dataset 指定数据集成员可见、
self 仅作者本人可见。集中在此，供 posts / projects / skills 调用，避免各处重复。
"""
from sqlalchemy.orm import Session
from ..models.extras import ContentScope, CONTENT_SCOPES
from ..models.user import User
from .permissions import is_group_member, is_dataset_member, is_super_admin


def validate_scope(db: Session, scope: str, scope_ref_id, user: User) -> tuple[str, int | None]:
    """校验发布者对所选范围是否有权限，返回规范化后的 (scope, scope_ref_id)。"""
    scope = scope if scope in CONTENT_SCOPES else "public"
    if scope in ("group", "dataset"):
        if not scope_ref_id:
            raise ValueError("该可见范围需选择具体的课题组/数据集")
        ok = (is_group_member(db, scope_ref_id, user) if scope == "group"
              else is_dataset_member(db, scope_ref_id, user))
        if not ok:
            raise ValueError("你不是所选课题组/数据集的成员，无法设为其可见范围")
        return scope, int(scope_ref_id)
    return scope, None


def set_scope(db: Session, content_type: str, content_id: int, scope: str,
              scope_ref_id, user: User) -> ContentScope:
    scope, ref = validate_scope(db, scope, scope_ref_id, user)
    row = db.query(ContentScope).filter_by(content_type=content_type,
                                           content_id=content_id).first()
    if not row:
        row = ContentScope(content_type=content_type, content_id=content_id)
        db.add(row)
    row.scope = scope; row.scope_ref_id = ref
    db.flush()
    return row


def get_scope(db: Session, content_type: str, content_id: int) -> ContentScope | None:
    return db.query(ContentScope).filter_by(content_type=content_type,
                                            content_id=content_id).first()


def scope_visible(db: Session, content_type: str, content_id: int,
                  owner_id: int, user: User) -> bool:
    """当前用户能否看到该内容。无 ContentScope 记录时默认公开（兼容历史数据）。"""
    if owner_id == user.id or is_super_admin(user):
        return True
    row = get_scope(db, content_type, content_id)
    if not row:
        return True
    if row.scope == "public":
        return True
    if row.scope == "self":
        return False
    if row.scope == "group" and row.scope_ref_id:
        return is_group_member(db, row.scope_ref_id, user)
    if row.scope == "dataset" and row.scope_ref_id:
        return is_dataset_member(db, row.scope_ref_id, user)
    return False


def scope_label(scope: str) -> str:
    return {"public": "全平台公开", "group": "课题组成员可见",
            "dataset": "数据集成员可见", "self": "仅自己可见"}.get(scope, scope)
