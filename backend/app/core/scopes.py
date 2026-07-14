"""统一可见范围（发帖 / 项目 / skill 共用）。

四类：public 全平台公开、group 指定课题组成员可见、dataset 指定数据集成员可见、
self 仅作者本人可见。其中 group / dataset 支持一次选择「多个」课题组/数据集：
只要用户是其中任意一个的成员即可见。集中在此，供 posts / projects / skills 调用。
"""
from sqlalchemy.orm import Session
from ..models.extras import ContentScope, CONTENT_SCOPES
from ..models.user import User
from .permissions import is_group_member, is_dataset_member, is_super_admin


def _norm_ids(scope_ref_ids) -> list[int]:
    """把 [1,2] 或 "1,2,3" 规范成 int 列表。"""
    if scope_ref_ids is None:
        return []
    if isinstance(scope_ref_ids, str):
        parts = [p.strip() for p in scope_ref_ids.split(",")]
    else:
        parts = list(scope_ref_ids)
    out = []
    for p in parts:
        try:
            v = int(p)
            if v and v not in out:
                out.append(v)
        except (TypeError, ValueError):
            continue
    return out


def validate_scope(db: Session, scope: str, scope_ref_ids, user: User) -> tuple[str, list[int]]:
    """校验发布者对所选范围是否有权限，返回 (scope, [ref_id,...])。"""
    scope = scope if scope in CONTENT_SCOPES else "public"
    if scope in ("group", "dataset"):
        ids = _norm_ids(scope_ref_ids)
        if not ids:
            raise ValueError("该可见范围需选择至少一个课题组/数据集")
        for rid in ids:
            ok = (is_group_member(db, rid, user) if scope == "group"
                  else is_dataset_member(db, rid, user))
            if not ok:
                raise ValueError("你不是所选课题组/数据集的成员，无法设为其可见范围")
        return scope, ids
    return scope, []


def set_scope(db: Session, content_type: str, content_id: int, scope: str,
              scope_ref_ids, user: User) -> None:
    """写入可见范围：public/self 存一行(ref=None)，group/dataset 每个 ref 存一行。"""
    scope, ids = validate_scope(db, scope, scope_ref_ids, user)
    db.query(ContentScope).filter_by(content_type=content_type,
                                     content_id=content_id).delete()
    if scope in ("group", "dataset"):
        for rid in ids:
            db.add(ContentScope(content_type=content_type, content_id=content_id,
                                scope=scope, scope_ref_id=rid))
    else:
        db.add(ContentScope(content_type=content_type, content_id=content_id, scope=scope))
    db.flush()


def get_scopes(db: Session, content_type: str, content_id: int) -> list[ContentScope]:
    return db.query(ContentScope).filter_by(content_type=content_type,
                                            content_id=content_id).all()


def scope_visible(db: Session, content_type: str, content_id: int,
                  owner_id: int, user: User) -> bool:
    """当前用户能否看到该内容。无记录时默认公开（兼容历史数据）。"""
    if owner_id == user.id or is_super_admin(user):
        return True
    rows = get_scopes(db, content_type, content_id)
    if not rows:
        return True
    scopes = {r.scope for r in rows}
    if "public" in scopes:
        return True
    if scopes == {"self"}:
        return False
    for r in rows:
        if r.scope == "group" and r.scope_ref_id and is_group_member(db, r.scope_ref_id, user):
            return True
        if r.scope == "dataset" and r.scope_ref_id and is_dataset_member(db, r.scope_ref_id, user):
            return True
    return False


def scope_summary(db: Session, content_type: str, content_id: int) -> dict:
    """给前端展示用：{scope, label, ref_ids}。"""
    rows = get_scopes(db, content_type, content_id)
    if not rows:
        return {"scope": "public", "label": "全平台公开", "ref_ids": []}
    scope = rows[0].scope
    ref_ids = [r.scope_ref_id for r in rows if r.scope_ref_id]
    base = scope_label(scope)
    if scope in ("group", "dataset") and len(ref_ids) > 1:
        base = f"{base}（{len(ref_ids)}个）"
    return {"scope": scope, "label": base, "ref_ids": ref_ids}


def scope_label(scope: str) -> str:
    return {"public": "全平台公开", "group": "课题组成员可见",
            "dataset": "数据集成员可见", "self": "仅自己可见"}.get(scope, scope)
