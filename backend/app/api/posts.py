from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user, is_super_admin
from ..core.audit import record_contribution
from ..models.user import User
from ..models.group import GroupMember
from ..models.community import (Post, PostTag, PostReaction, PostComment, PostAdminFlag,
                                PostAttachment, PostFollow, PostCommentReaction,
                                Project, ProjectTag)
from ..schemas.models import PostIn, CommentIn, ProjectIn

router = APIRouter(tags=["community"])

# 讨论类型：key -> 中文名
POST_TYPES = {
    "question": "研究问题", "data": "数据问题", "method": "方法讨论",
    "collab": "合作招募", "discussion": "自由讨论",
}


def _bj(dt):
    if not dt:
        return None
    from datetime import timedelta
    return (dt + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")


def _comment_count(db: Session, pid: int) -> int:
    """帖子评论数：一级评论 + 回复总数（删除的评论已物理删除，不计入）。"""
    return db.query(PostComment).filter_by(post_id=pid).count()


def _hot_score(likes: int, comments: int, commenters: int, created_at) -> float:
    """热度 = 点赞 + 3×评论 + 2×独立参与人数，再乘时间衰减（半衰期约3天）。"""
    import math
    from datetime import datetime
    base = likes + 3 * comments + 2 * commenters
    age_h = 0.0
    if created_at:
        age_h = max(0.0, (datetime.utcnow() - created_at).total_seconds() / 3600.0)
    decay = math.pow(0.5, age_h / 72.0)   # 72h 半衰期
    return base * decay


def _post_visible(db, p, user, my_groups) -> bool:
    from ..core.scopes import scope_visible, get_scopes
    sc = get_scopes(db, "post", p.id)
    if sc:
        return scope_visible(db, "post", p.id, p.author_id, user)
    if p.visibility == "private" and p.author_id != user.id and not is_super_admin(user):
        return False
    if p.visibility == "group" and p.group_id not in my_groups \
            and p.author_id != user.id and not is_super_admin(user):
        return False
    return True


def _serialize_post(db, p, user, *, detail=False, likes=None, comments=None,
                    commenters=None):
    from ..core.scopes import scope_summary
    from ..models.dataset import Dataset
    from ..models.group import ResearchGroup
    _sum = scope_summary(db, "post", p.id)
    ds_slug = ds_name = None
    if p.dataset_id:
        dsx = db.get(Dataset, p.dataset_id)
        if dsx:
            ds_slug = dsx.slug; ds_name = dsx.name_zh
    grp_slug = grp_name = None
    if p.group_id:
        g = db.get(ResearchGroup, p.group_id)
        if g:
            grp_slug = g.slug; grp_name = g.name_zh
    tags = [t.tag for t in db.query(PostTag).filter_by(post_id=p.id).all()]
    if likes is None:
        likes = db.query(PostReaction).filter_by(post_id=p.id, type="like").count()
    if comments is None:
        comments = _comment_count(db, p.id)
    liked = db.query(PostReaction).filter_by(
        post_id=p.id, user_id=user.id, type="like").first() is not None
    followed = db.query(PostFollow).filter_by(
        post_id=p.id, user_id=user.id).first() is not None
    author = db.get(User, p.author_id)
    body = p.content_zh or ""
    summary = body if (detail or len(body) <= 140) else body[:140] + "…"
    return {
        "id": p.id, "author_id": p.author_id,
        "author_name": author.display_name if author else "",
        "author_avatar": author.avatar if author else None,
        "title": p.title, "post_type": p.post_type or "discussion",
        "post_type_label": POST_TYPES.get(p.post_type or "discussion", "讨论"),
        "status": p.status or "open",
        "content_zh": summary, "full_content": body if detail else None,
        "truncated": (not detail) and len(body) > 140,
        "visibility": p.visibility,
        "dataset_id": p.dataset_id, "dataset_slug": ds_slug, "dataset_name": ds_name,
        "group_id": p.group_id, "group_slug": grp_slug, "group_name": grp_name,
        "cover_icon": p.cover_icon,
        "scope": _sum["scope"], "scope_label": _sum["label"],
        "tags": tags, "likes": likes, "liked": liked,
        "comment_count": comments, "followed": followed,
        "created_at": _bj(p.created_at),
        "can_edit": p.author_id == user.id,
        "can_delete": p.author_id == user.id or is_super_admin(user),
    }


@router.get("/posts")
def feed(dataset_id: int | None = None, group_id: int | None = None,
         author_id: int | None = None, post_type: str | None = None,
         status: str | None = None, scope: str | None = None,
         mine: str | None = None,
         sort: str = "new", range: str = "all", limit: int = 100,
         db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """统一帖子流。研究广场/数据集讨论区/课题组/个人主页共享同一份数据，
    只是默认筛选不同。支持按 组/集/类型/状态/作者 筛选，按 new|hot 排序。
    mine=authored|liked|followed|commented：按「我参与」的方式筛选。"""
    from datetime import datetime, timedelta
    my_groups = {m.group_id for m in db.query(GroupMember)
                 .filter_by(user_id=user.id, status="active").all()}
    q = db.query(Post)
    if dataset_id:
        q = q.filter_by(dataset_id=dataset_id)
    if group_id:
        q = q.filter_by(group_id=group_id)
    if author_id:
        q = q.filter_by(author_id=author_id)
    if post_type:
        q = q.filter_by(post_type=post_type)
    if status:
        q = q.filter_by(status=status)
    if mine == "authored":
        q = q.filter(Post.author_id == user.id)
    elif mine == "liked":
        ids = [r.post_id for r in db.query(PostReaction.post_id).filter_by(
            user_id=user.id, type="like").all()]
        q = q.filter(Post.id.in_(ids or [-1]))
    elif mine == "followed":
        ids = [r.post_id for r in db.query(PostFollow.post_id).filter_by(
            user_id=user.id).all()]
        q = q.filter(Post.id.in_(ids or [-1]))
    elif mine == "commented":
        ids = [r.post_id for r in db.query(PostComment.post_id).filter_by(
            user_id=user.id).distinct().all()]
        q = q.filter(Post.id.in_(ids or [-1]))
    since = None
    if range == "24h":
        since = datetime.utcnow() - timedelta(hours=24)
    elif range == "7d":
        since = datetime.utcnow() - timedelta(days=7)
    rows = q.order_by(Post.id.desc()).limit(600).all()
    out = []
    for p in rows:
        if since and p.created_at and p.created_at < since:
            continue
        if not _post_visible(db, p, user, my_groups):
            continue
        likes = db.query(PostReaction).filter_by(post_id=p.id, type="like").count()
        comments = _comment_count(db, p.id)
        commenters = db.query(PostComment.user_id).filter_by(
            post_id=p.id).distinct().count()
        item = _serialize_post(db, p, user, likes=likes, comments=comments)
        if scope and item["scope"] != scope:
            continue
        item["_hot"] = _hot_score(likes, comments, commenters, p.created_at)
        out.append(item)
    if sort == "hot":
        out.sort(key=lambda x: x["_hot"], reverse=True)
    else:
        out.sort(key=lambda x: x["id"], reverse=True)
    out = out[:min(limit, 300)]
    for it in out:
        it.pop("_hot", None)
    return out


@router.get("/posts/hot")
def hot_posts(range: str = "7d", limit: int = 10, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """研究热榜：综合点赞/评论/参与人数 + 时间衰减，返回精简条目。"""
    items = feed(sort="hot", range=range, limit=limit, db=db, user=user)
    return [{"id": i["id"], "title": i["title"] or (i["content_zh"] or "")[:40],
             "author_name": i["author_name"], "likes": i["likes"],
             "comment_count": i["comment_count"], "post_type_label": i["post_type_label"]}
            for i in items]


@router.post("/posts")
def create_post(body: PostIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    from ..core.scopes import set_scope
    if not (body.content_zh or "").strip() and not (body.title or "").strip():
        raise HTTPException(400, "标题或正文至少填一项")
    legacy = {"public": "platform", "self": "private"}.get(body.scope, "group")
    p = Post(author_id=user.id, content_zh=body.content_zh, content_en=body.content_en,
             title=(body.title or None), post_type=body.post_type or "discussion",
             status=body.status or "open",
             dataset_id=body.dataset_id, group_id=body.group_id,
             visibility=legacy, cover_icon=body.cover_icon)
    db.add(p); db.flush()
    refs = body.scope_ref_ids or ([body.scope_ref_id] if body.scope_ref_id else [])
    try:
        set_scope(db, "post", p.id, body.scope, refs, user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    for tg in body.tags:
        if (tg or "").strip():
            db.add(PostTag(post_id=p.id, tag=tg.strip()))
    record_contribution(db, user.id, "post", "post", p.id, body.dataset_id, weight=1)
    db.commit()
    return {"id": p.id}


@router.get("/posts/{pid}")
def get_post(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Post, pid)
    if not p:
        raise HTTPException(404, "帖子不存在")
    my_groups = {m.group_id for m in db.query(GroupMember)
                 .filter_by(user_id=user.id, status="active").all()}
    if not _post_visible(db, p, user, my_groups):
        raise HTTPException(403, "无权查看该讨论")
    item = _serialize_post(db, p, user, detail=True)
    item["attachments"] = [
        {"id": a.id, "file_name": a.file_name, "size": a.size,
         "url": f"/api/posts/{pid}/attachments/{a.id}/download"}
        for a in db.query(PostAttachment).filter_by(post_id=pid).all()]
    return item


@router.patch("/posts/{pid}")
def edit_post(pid: int, body: PostIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    from ..core.scopes import set_scope
    p = db.get(Post, pid)
    if not p:
        raise HTTPException(404, "帖子不存在")
    if p.author_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "只能编辑本人帖子")
    p.content_zh = body.content_zh
    if body.title is not None:
        p.title = body.title or None
    if body.post_type:
        p.post_type = body.post_type
    if body.status:
        p.status = body.status
    # 更新标签
    db.query(PostTag).filter_by(post_id=pid).delete()
    for tg in body.tags:
        if (tg or "").strip():
            db.add(PostTag(post_id=pid, tag=tg.strip()))
    # 更新可见范围
    refs = body.scope_ref_ids or ([body.scope_ref_id] if body.scope_ref_id else [])
    try:
        set_scope(db, "post", pid, body.scope, refs, user)
        p.visibility = {"public": "platform", "self": "private"}.get(body.scope, "group")
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"ok": True}


@router.delete("/posts/{pid}")
def del_post(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Post, pid)
    if not p:
        raise HTTPException(404, "帖子不存在")
    if p.author_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "无权删除")
    # 连带清理评论/评论点赞/点赞/标签/附件/关注（附件文件也删）
    cids = [c.id for c in db.query(PostComment.id).filter_by(post_id=pid).all()]
    if cids:
        db.query(PostCommentReaction).filter(
            PostCommentReaction.comment_id.in_(cids)).delete(synchronize_session=False)
    db.query(PostComment).filter_by(post_id=pid).delete()
    db.query(PostReaction).filter_by(post_id=pid).delete()
    db.query(PostTag).filter_by(post_id=pid).delete()
    db.query(PostFollow).filter_by(post_id=pid).delete()
    for a in db.query(PostAttachment).filter_by(post_id=pid).all():
        from ..core.storage import storage
        try: storage.delete(a.file_path)
        except Exception: pass
        db.delete(a)
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


@router.post("/posts/{pid}/follow")
def follow_post(pid: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    p = db.get(Post, pid)
    if not p:
        raise HTTPException(404, "帖子不存在")
    ex = db.query(PostFollow).filter_by(post_id=pid, user_id=user.id).first()
    if ex:
        db.delete(ex); db.commit(); return {"followed": False}
    db.add(PostFollow(post_id=pid, user_id=user.id)); db.commit()
    return {"followed": True}


@router.get("/posts/{pid}/comments")
def get_comments(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cs = db.query(PostComment).filter_by(post_id=pid).order_by(PostComment.id).all()
    p = db.get(Post, pid)

    def mk(c):
        u = db.get(User, c.user_id)
        likes = db.query(PostCommentReaction).filter_by(
            comment_id=c.id, type="like").count()
        liked = db.query(PostCommentReaction).filter_by(
            comment_id=c.id, user_id=user.id, type="like").first() is not None
        return {"id": c.id, "user_id": c.user_id,
                "user_name": u.display_name if u else f"用户#{c.user_id}",
                "content": c.content, "parent_id": c.parent_id,
                "created_at": _bj(c.created_at),
                "likes": likes, "liked": liked,
                "is_mine": c.user_id == user.id,
                "can_delete": c.user_id == user.id
                or (p and p.author_id == user.id) or is_super_admin(user)}

    tops = [c for c in cs if not c.parent_id]
    replies = [c for c in cs if c.parent_id]
    # 「在每个用户的视角，他的评论排在最上方」：一级评论把当前用户的置顶，其余按时间
    tops.sort(key=lambda c: (0 if c.user_id == user.id else 1, c.id))
    # 一级评论在前、回复在后（前端按 parent_id 分组，各自保持此顺序）
    return [mk(c) for c in tops] + [mk(c) for c in replies]


@router.post("/comments/{cid}/react")
def react_comment(cid: int, type: str = "like", db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """给帖子评论点赞（所有入口共用同一份评论数据）。"""
    c = db.get(PostComment, cid)
    if not c:
        raise HTTPException(404, "评论不存在")
    ex = db.query(PostCommentReaction).filter_by(
        comment_id=cid, user_id=user.id, type=type).first()
    if ex:
        db.delete(ex); db.commit(); return {"toggled": "off"}
    db.add(PostCommentReaction(comment_id=cid, user_id=user.id, type=type))
    db.commit()
    return {"toggled": "on"}


@router.post("/posts/{pid}/comments")
def add_comment(pid: int, body: CommentIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    # 支持「评论的评论」：body.parent_id 指向同帖的某条评论
    parent_id = getattr(body, "parent_id", None)
    if parent_id:
        parent = db.get(PostComment, parent_id)
        if not parent or parent.post_id != pid:
            raise HTTPException(400, "父评论不存在")
    if not (body.content or "").strip():
        raise HTTPException(400, "评论内容不能为空")
    c = PostComment(post_id=pid, user_id=user.id, content=body.content.strip(),
                    parent_id=parent_id)
    db.add(c); db.commit()
    return {"id": c.id}


@router.delete("/comments/{cid}")
def del_comment(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(PostComment, cid)
    if not c:
        raise HTTPException(404, "评论不存在")
    p = db.get(Post, c.post_id)
    if c.user_id != user.id and (not p or p.author_id != user.id) and not is_super_admin(user):
        raise HTTPException(403, "无权删除")
    # 删除一条评论时，其下的回复一并删除；连带清理评论点赞
    reply_ids = [r.id for r in db.query(PostComment.id).filter_by(parent_id=cid).all()]
    all_ids = reply_ids + [cid]
    db.query(PostCommentReaction).filter(
        PostCommentReaction.comment_id.in_(all_ids)).delete(synchronize_session=False)
    db.query(PostComment).filter_by(parent_id=cid).delete()
    db.delete(c); db.commit()
    return {"ok": True}


@router.get("/posts/{pid}/attachments/{aid}/download")
def download_post_attachment(pid: int, aid: int, db: Session = Depends(get_db),
                             user: User = Depends(get_current_user)):
    from ..core.storage import storage
    my_groups = {m.group_id for m in db.query(GroupMember)
                 .filter_by(user_id=user.id, status="active").all()}
    p = db.get(Post, pid)
    if not p or not _post_visible(db, p, user, my_groups):
        raise HTTPException(403, "无权下载")
    a = db.get(PostAttachment, aid)
    if not a or a.post_id != pid:
        raise HTTPException(404, "附件不存在")
    return StreamingResponse(storage.open(a.file_path),
                             media_type=a.mime or "application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{a.file_name}"'})


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
from ..models.extras import ProjectMeta
from fastapi import Form


@router.get("/projects")
def list_projects(author_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    from ..core.scopes import scope_visible, scope_summary
    q = db.query(Project)
    if author_id:
        q = q.filter_by(author_id=author_id)
    rows = q.order_by(Project.id.desc()).all()
    out = []
    for p in rows:
        # 可见范围过滤（本人/管理员始终可见）
        if not scope_visible(db, "project", p.id, p.author_id, user):
            continue
        m = db.get(ProjectMeta, p.id)
        _sum = scope_summary(db, "project", p.id)
        out.append({"id": p.id, "title": p.title, "status": p.status,
                    "author_id": p.author_id, "open_for_discussion": p.open_for_discussion,
                    "body_zh": p.body_zh, "pinned": bool(m and m.pinned),
                    "has_image": bool(m and m.image_path),
                    "scope": _sum["scope"], "scope_label": _sum["label"],
                    "image_url": f"/api/projects/{p.id}/image" if (m and m.image_path) else None})
    # 置顶优先，其余按新→旧
    out.sort(key=lambda x: (not x["pinned"], -x["id"]))
    return out


@router.post("/projects")
def create_project(title: str = Form(...), body_zh: str = Form(...),
                   pinned: bool = Form(False), status: str | None = Form(None),
                   scope: str = Form("public"), scope_ref_ids: str = Form(""),
                   image: UploadFile = File(...), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """创建在做项目：标题、图片、文字均必填（图片作为封面）。可选择是否置顶与可见范围（多选）。"""
    from ..services.uploads import save_upload, IMG_EXT
    from ..core.scopes import set_scope
    if not (title or "").strip() or not (body_zh or "").strip():
        raise HTTPException(400, "标题与文字均必填")
    meta = save_upload(image, f"project/cover", whitelist=IMG_EXT)
    p = Project(author_id=user.id, title=title.strip(), body_zh=body_zh.strip(),
                status=status or "进行中", open_for_discussion=True, visibility="platform")
    db.add(p); db.flush()
    db.add(ProjectMeta(project_id=p.id, pinned=bool(pinned), image_path=meta["file_path"],
                       image_name=meta["file_name"], image_mime=meta["mime"]))
    try:
        set_scope(db, "project", p.id, scope, scope_ref_ids, user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"id": p.id}


@router.post("/projects/{pid}/pin")
def toggle_pin(pid: int, pinned: bool = True, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """对已发布项目设置/取消置顶（仅作者本人）。"""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    if p.author_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "仅作者可置顶")
    m = db.get(ProjectMeta, pid)
    if not m:
        m = ProjectMeta(project_id=pid); db.add(m)
    m.pinned = bool(pinned)
    db.commit()
    return {"ok": True, "pinned": m.pinned}


@router.get("/projects/{pid}/image")
def project_image(pid: int, db: Session = Depends(get_db)):
    from ..core.storage import storage
    m = db.get(ProjectMeta, pid)
    if not m or not m.image_path:
        raise HTTPException(404, "无封面图")
    return StreamingResponse(storage.open(m.image_path),
                             media_type=m.image_mime or "image/*")


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
    from ..models.community import ProjectComment, ProjectAttachment, ProjectTag
    from ..models.extras import ProjectMeta, ContentScope
    from ..core.storage import storage
    # 连带清理所有引用 projects.id 的子表，否则 Postgres 外键会阻断删除（删除失败）
    db.query(ProjectComment).filter_by(project_id=pid).delete()
    db.query(ProjectTag).filter_by(project_id=pid).delete()
    for a in db.query(ProjectAttachment).filter_by(project_id=pid).all():
        try: storage.delete(a.file_path)
        except Exception: pass
        db.delete(a)
    m = db.get(ProjectMeta, pid)
    if m:
        if m.image_path:
            try: storage.delete(m.image_path)
            except Exception: pass
        db.delete(m)
    db.query(ContentScope).filter_by(content_type="project", content_id=pid).delete()
    db.delete(p); db.commit()
    return {"ok": True}


@router.get("/projects/{pid}")
def get_project(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """项目详情（含正文、封面、可编辑/可评论标记）。"""
    from ..core.scopes import scope_visible, scope_summary
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    if not scope_visible(db, "project", p.id, p.author_id, user):
        raise HTTPException(403, "无权查看该项目")
    m = db.get(ProjectMeta, pid)
    au = db.get(User, p.author_id)
    _sum = scope_summary(db, "project", p.id)
    return {"id": p.id, "title": p.title, "body_zh": p.body_zh, "status": p.status,
            "author_id": p.author_id, "author_name": au.display_name if au else "",
            "open_for_discussion": p.open_for_discussion,
            "pinned": bool(m and m.pinned),
            "can_edit": p.author_id == user.id,
            "can_manage": p.author_id == user.id or is_super_admin(user),
            "scope": _sum["scope"], "scope_label": _sum["label"],
            "image_url": f"/api/projects/{p.id}/image" if (m and m.image_path) else None}


# -------- 项目评论 --------
def _proj_bj(dt):
    if not dt:
        return None
    from datetime import timedelta
    return (dt + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")


@router.get("/projects/{pid}/comments")
def list_project_comments(pid: int, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    from ..core.scopes import scope_visible
    from ..models.community import ProjectComment
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    if not scope_visible(db, "project", p.id, p.author_id, user):
        raise HTTPException(403, "无权查看")
    rows = (db.query(ProjectComment).filter_by(project_id=pid)
            .order_by(ProjectComment.id.asc()).all())
    out = []
    for c in rows:
        u = db.get(User, c.user_id)
        out.append({"id": c.id, "user_id": c.user_id,
                    "user_name": u.display_name if u else f"用户#{c.user_id}",
                    "content": c.content, "parent_id": c.parent_id,
                    "created_at": _proj_bj(c.created_at),
                    "can_delete": c.user_id == user.id or p.author_id == user.id
                    or is_super_admin(user)})
    return out


@router.post("/projects/{pid}/comments")
def add_project_comment(pid: int, body: CommentIn, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    from ..core.scopes import scope_visible
    from ..models.community import ProjectComment
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "项目不存在")
    if not p.open_for_discussion and p.author_id != user.id:
        raise HTTPException(403, "该项目未开放讨论")
    if not scope_visible(db, "project", p.id, p.author_id, user):
        raise HTTPException(403, "无权评论")
    if not (body.content or "").strip():
        raise HTTPException(400, "评论内容不能为空")
    c = ProjectComment(project_id=pid, user_id=user.id,
                       content=body.content.strip(), parent_id=body.parent_id)
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id}


@router.delete("/projects/{pid}/comments/{cid}")
def del_project_comment(pid: int, cid: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    from ..models.community import ProjectComment
    p = db.get(Project, pid)
    c = db.get(ProjectComment, cid)
    if not c or c.project_id != pid:
        raise HTTPException(404, "评论不存在")
    if c.user_id != user.id and (not p or p.author_id != user.id) and not is_super_admin(user):
        raise HTTPException(403, "无权删除")
    db.delete(c); db.commit()
    return {"ok": True}


# ================= 帖子附件上传 =================
from fastapi import UploadFile, File  # noqa: E402


@router.post("/posts/{pid}/attachments")
def upload_post_attachment(pid: int, file: UploadFile = File(...),
                           db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    from ..models.community import PostAttachment
    from ..services.uploads import save_upload
    p = db.get(Post, pid)
    if not p:
        raise HTTPException(404, "帖子不存在")
    if p.author_id != user.id and not is_super_admin(user):
        raise HTTPException(403, "只能给本人帖子加附件")
    meta = save_upload(file, f"post/{pid}")
    a = PostAttachment(post_id=pid, **meta)
    db.add(a); db.commit(); db.refresh(a)
    return {"id": a.id, "file_name": a.file_name}
