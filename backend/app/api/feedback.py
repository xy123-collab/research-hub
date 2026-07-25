from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.audit import write_audit
from ..core.db import get_db
from ..core.permissions import get_current_user, require_super_admin
from ..models.governance import FeedbackTicket
from ..models.user import User

router = APIRouter(tags=["feedback"])


class TicketIn(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=5, max_length=5000)
    expected_result: str | None = Field(default=None, max_length=2000)
    page_url: str | None = Field(default=None, max_length=800)
    object_type: str | None = Field(default=None, max_length=30)
    object_id: str | None = Field(default=None, max_length=100)
    impact: str = Field(default="suggestion", max_length=30)
    contact_email: str | None = Field(default=None, max_length=200)


class TicketUpdate(BaseModel):
    status: str
    admin_reply: str | None = Field(default=None, max_length=5000)


def _ticket_dict(db: Session, row: FeedbackTicket):
    submitter = db.get(User, row.submitted_by)
    handler = db.get(User, row.handled_by) if row.handled_by else None
    return {
        "id": row.id, "category": row.category, "title": row.title,
        "description": row.description, "expected_result": row.expected_result,
        "page_url": row.page_url, "object_type": row.object_type, "object_id": row.object_id,
        "impact": row.impact, "contact_email": row.contact_email, "status": row.status,
        "admin_reply": row.admin_reply,
        "submitter": {"id": submitter.id, "name": submitter.display_name} if submitter else None,
        "handler": {"id": handler.id, "name": handler.display_name} if handler else None,
        "created_at": str(row.created_at), "updated_at": str(row.updated_at),
    }


@router.post("/feedback")
def create_ticket(body: TicketIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    row = FeedbackTicket(submitted_by=user.id, contact_email=body.contact_email or user.email,
                         **body.model_dump(exclude={"contact_email"}))
    db.add(row)
    db.flush()
    write_audit(db, user.id, "feedback.submit", "feedback_ticket", row.id,
                {"category": body.category, "impact": body.impact})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "created_at": str(row.created_at)}


@router.get("/feedback/mine")
def my_tickets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(FeedbackTicket).filter_by(submitted_by=user.id)
            .order_by(FeedbackTicket.id.desc()).all())
    return [_ticket_dict(db, row) for row in rows]


@router.get("/admin/feedback")
def admin_tickets(status: str | None = None, db: Session = Depends(get_db),
                  user: User = Depends(require_super_admin)):
    q = db.query(FeedbackTicket)
    if status:
        q = q.filter(FeedbackTicket.status == status)
    return [_ticket_dict(db, row) for row in q.order_by(FeedbackTicket.id.desc()).limit(200).all()]


@router.patch("/admin/feedback/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_super_admin)):
    allowed = {"pending", "processing", "waiting_user", "resolved", "closed", "rejected"}
    if body.status not in allowed:
        raise HTTPException(400, "不支持的工单状态")
    row = db.get(FeedbackTicket, ticket_id)
    if not row:
        raise HTTPException(404, "工单不存在")
    row.status = body.status
    row.admin_reply = body.admin_reply
    row.handled_by = user.id
    row.handled_at = datetime.utcnow()
    write_audit(db, user.id, "feedback.update", "feedback_ticket", row.id,
                {"status": body.status})
    db.commit()
    return {"ok": True}
