from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, is_super_admin
from ..core.audit import record_contribution
from ..models.user import User
from ..models.group import GroupMember
from ..models.community import (Post, PostTag, PostReaction, PostComment, PostAdminFlag,
                                Project, ProjectTag)
from ..schemas.models import PostIn, CommentIn, ProjectIn

router = APIRouter(tags=["community"])


@router.get("/posts")
def feed(dataset_id: int | None = None, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)):
    my_groups = {m.group_id for m in db.query(GroupMember)
                 .filter_by(user_id=user.id, status="active").all()}
    q = db.query(Post)
    if dataset_id:
        q = q.filter_by(dataset_id=dataset_id)
    out = []
    for p in q.order_by(Post.id.desc()).limit(200).all():
        # 可见性三级
        if p.visibility == "private" and p.author_id != user.id and not is_super_admin(user):
            continue
        if p.visibility == "group" and p.group_id not in my_groups \
                and p.author_id != user.id and not is_super_admin(user):
            continue
        tags = [t.tag for t in db.query(PostTag).filter_by(post_id=p.id).all()]
        likes = db.query(PostReaction).filter_by(post_id=p.id, type="like").count()
        author = db.get(User, p.author_id)
        out.append({"id": p.id, "author_id": p.author_id,
                    "author_name": author.display_name if author else "",
                    "content_zh": p.content_zh, "visibility": p.visibility,
                    "dataset_id": p.dataset_id, "cover_icon": p.cover_icon,
                    "tags": tags, "likes": likes})
    return out


@router.post("/posts")
def create_post(body: PostIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    p = Post(author_id=user.id, content_zh=body.content_zh, content_en=body.content_en,
             dataset_id=body.dataset_id, group_id=body.group_id,
             visibility=body.visibility, cover_icon=body.cover_icon)
    db.add(p); db.flush()
    for t in body.tags:
        db.add(PostTag(post_id=p.id, tag=t))
    record_contribution(db, user.id, "post", "post", p.id, body.dataset_id, weight=1)
    db.commit()
    return {"id": p.id}


@router.patch("/posts/{pid}")
def edit_post(pid: int, body: PostIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    p = db.get(Post, pid)
    if not p:
        raise HTTPException(404, "帖子不存在")
    if p.author_id != user.id:
        raise HTTPException(403, "只能编辑本人帖子")
    p.content_zh = body.content_zh; p.visibility = body.visibility
    db.commit()
    return {"ok": True}


@router.delete("/posts/{pid}")
def del_post(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Post, pid)
    if not p:
        raise HTTPException(404, "帖子不存在")
    if p.author_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "无权删除")
    db.delete(p); db.commit()
    return {"ok": True}


@router.post("/posts/{pid}/react")
def react(pid: int, type: str = "like", db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    ex = db.query(PostReaction).filter_by(post_id=pid, user_id=user.id, type=type).first()
    if ex:
        db.delete(ex); db.commit(); return {"toggled": "off"}
    db.add(PostReaction(post_id=pid, user_id=user.id, type=type)); db.commit()
    return {"toggled": "on"}


@router.get("/posts/{pid}/comments")
def get_comments(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cs = db.query(PostComment).filter_by(post_id=pid).order_by(PostComment.id).all()
    return [{"id": c.id, "user_id": c.user_id, "content": c.content} for c in cs]


@router.post("/posts/{pid}/comments")
def add_comment(pid: int, body: CommentIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    c = PostComment(post_id=pid, user_id=user.id, content=body.content)
    db.add(c); db.commit()
    return {"id": c.id}


@router.delete("/comments/{cid}")
def del_comment(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(PostComment, cid)
    if not c:
        raise HTTPException(404, "评论不存在")
    if c.user_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "无权删除")
    db.delete(c); db.commit()
    return {"ok": True}


@router.post("/posts/{pid}/flag")
def flag_post(pid: int, recommended: bool = True, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    if not is_super_admin(user):
        raise HTTPException(403, "需管理员")
    f = db.query(PostAdminFlag).filter_by(post_id=pid).first()
    if not f:
        f = PostAdminFlag(post_id=pid, is_recommended=recommended); db.add(f)
    else:
        f.is_recommended = recommended
    db.commit()
    return {"ok": True}


# -------- projects --------
@router.get("/projects")
def list_projects(author_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    q = db.query(Project)
    if author_id:
        q = q.filter_by(author_id=author_id)
    return [{"id": p.id, "title": p.title, "status": p.status, "author_id": p.author_id,
             "open_for_discussion": p.open_for_discussion, "body_zh": p.body_zh}
            for p in q.order_by(Project.id.desc()).all()]


@router.post("/projects")
def create_project(body: ProjectIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    p = Project(author_id=user.id, **body.model_dump())
    db.add(p); db.commit()
    return {"id": p.id}


@router.patch("/projects/{pid}")
def edit_project(pid: int, body: ProjectIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    p = db.get(Project, pid)
    if not p or p.author_id != user.id:
        raise HTTPException(403, "无权编辑")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/projects/{pid}")
def del_project(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Project, pid)
    if not p or (p.author_id != user.id and not is_super_admin(user)):
        raise HTTPException(403, "无权删除")
    db.delete(p); db.commit()
    return {"ok": True}
