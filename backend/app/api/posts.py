from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
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
    from ..core.scopes import scope_visible, get_scopes, scope_summary
    my_groups = {m.group_id for m in db.query(GroupMember)
                 .filter_by(user_id=user.id, status="active").all()}
    q = db.query(Post)
    if dataset_id:
        q = q.filter_by(dataset_id=dataset_id)
    out = []
    for p in q.order_by(Post.id.desc()).limit(200).all():
        # 优先用统一可见范围 ContentScope；无记录时回退旧 visibility 三级
        sc = get_scopes(db, "post", p.id)
        if sc:
            if not scope_visible(db, "post", p.id, p.author_id, user):
                continue
        else:
            if p.visibility == "private" and p.author_id != user.id and not is_super_admin(user):
                continue
            if p.visibility == "group" and p.group_id not in my_groups \
                    and p.author_id != user.id and not is_super_admin(user):
                continue
        _sum = scope_summary(db, "post", p.id)
        ds_slug = ds_name = None
        if p.dataset_id:
            from ..models.dataset import Dataset
            dsx = db.get(Dataset, p.dataset_id)
            if dsx:
                ds_slug = dsx.slug; ds_name = dsx.name_zh
        tags = [t.tag for t in db.query(PostTag).filter_by(post_id=p.id).all()]
        likes = db.query(PostReaction).filter_by(post_id=p.id, type="like").count()
        author = db.get(User, p.author_id)
        out.append({"id": p.id, "author_id": p.author_id,
                    "author_name": author.display_name if author else "",
                    "content_zh": p.content_zh, "visibility": p.visibility,
                    "dataset_id": p.dataset_id, "cover_icon": p.cover_icon,
                    "scope": _sum["scope"], "scope_label": _sum["label"],
                    "dataset_slug": ds_slug, "dataset_name": ds_name,
                    "tags": tags, "likes": likes})
    return out


@router.post("/posts")
def create_post(body: PostIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    from ..core.scopes import set_scope
    # 兼容旧字段：由统一 scope 推导 legacy visibility
    legacy = {"public": "platform", "self": "private"}.get(body.scope, "group")
    p = Post(author_id=user.id, content_zh=body.content_zh, content_en=body.content_en,
             dataset_id=body.dataset_id, group_id=body.group_id,
             visibility=legacy, cover_icon=body.cover_icon)
    db.add(p); db.flush()
    refs = body.scope_ref_ids or ([body.scope_ref_id] if body.scope_ref_id else [])
    try:
        set_scope(db, "post", p.id, body.scope, refs, user)
    except ValueError as e:
        raise HTTPException(400, str(e))
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
    out = []
    for c in cs:
        u = db.get(User, c.user_id)
        out.append({"id": c.id, "user_id": c.user_id,
                    "user_name": u.display_name if u else f"用户#{c.user_id}",
                    "content": c.content, "parent_id": c.parent_id,
                    "created_at": str(c.created_at) if c.created_at else None})
    return out


@router.post("/posts/{pid}/comments")
def add_comment(pid: int, body: CommentIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    # 支持「评论的评论」：body.parent_id 指向同帖的某条评论
    parent_id = getattr(body, "parent_id", None)
    if parent_id:
        parent = db.get(PostComment, parent_id)
        if not parent or parent.post_id != pid:
            raise HTTPException(400, "父评论不存在")
    c = PostComment(post_id=pid, user_id=user.id, content=body.content, parent_id=parent_id)
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
    from ..models.community import ProjectComment
    db.query(ProjectComment).filter_by(project_id=pid).delete()
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
