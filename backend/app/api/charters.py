from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, is_group_admin, is_dataset_admin
from ..models.user import User
from ..models.group import Charter, CharterAck
from ..schemas.models import CharterIn

router = APIRouter(tags=["charters"])


@router.get("/charters")
def get_charter(scope: str, ref: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    c = (db.query(Charter).filter_by(scope=scope, ref_id=ref)
         .order_by(Charter.version.desc()).first())
    if not c:
        return {"charter": None, "acked": True}
    acked = db.query(CharterAck).filter_by(
        user_id=user.id, charter_id=c.id, charter_version=c.version).first() is not None
    return {"charter": {"id": c.id, "scope": c.scope, "ref_id": c.ref_id,
                        "body_zh": c.body_zh, "body_en": c.body_en, "version": c.version},
            "acked": acked}


@router.post("/charters/{cid}/ack")
def ack_charter(cid: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    c = db.get(Charter, cid)
    if not c:
        raise HTTPException(404, "公约不存在")
    exists = db.query(CharterAck).filter_by(
        user_id=user.id, charter_id=c.id, charter_version=c.version).first()
    if not exists:
        db.add(CharterAck(user_id=user.id, charter_id=c.id, charter_version=c.version,
                          acked_at=datetime.utcnow()))
        db.commit()
    return {"ok": True}


@router.put("/charters/{cid}")
def edit_charter(cid: int, body: CharterIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    c = db.get(Charter, cid)
    if not c:
        raise HTTPException(404, "公约不存在")
    ok = (is_group_admin(db, c.ref_id, user) if c.scope == "group"
          else is_dataset_admin(db, c.ref_id, user))
    if not ok:
        raise HTTPException(403, "无编辑权限")
    # 生成新版本 → 成员需重新确认
    new = Charter(scope=c.scope, ref_id=c.ref_id, body_zh=body.body_zh,
                  body_en=body.body_en, version=c.version + 1, updated_by=user.id)
    db.add(new); db.commit()
    return {"id": new.id, "version": new.version}
