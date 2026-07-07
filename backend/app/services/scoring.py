"""贡献度聚合（6.5）。基于 contribution_events。"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models.governance import ContributionEvent

BASE_SCORE = {
    "dataset_founder": 30, "code_add": 20, "post": 1,
    "skill_create": 15, "review_adopted": 3, "code_bug_accepted": 5,
}


def user_total(db: Session, user_id) -> float:
    rows = db.query(ContributionEvent).filter_by(user_id=user_id).all()
    return round(sum(r.weight or 1.0 for r in rows), 2)


def leaderboard(db: Session):
    q = (db.query(ContributionEvent.user_id, func.sum(ContributionEvent.weight))
           .group_by(ContributionEvent.user_id)
           .order_by(func.sum(ContributionEvent.weight).desc()))
    return [{"user_id": uid, "score": round(s or 0, 2)} for uid, s in q.all()]


def by_dataset(db: Session):
    q = (db.query(ContributionEvent.dataset_id, ContributionEvent.user_id,
                  func.sum(ContributionEvent.weight))
           .group_by(ContributionEvent.dataset_id, ContributionEvent.user_id))
    return [{"dataset_id": d, "user_id": u, "score": round(s or 0, 2)} for d, u, s in q.all()]
