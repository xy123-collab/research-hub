from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.permissions import get_current_user
from ..models.user import User
from ..models.workspace import (Workspace, WorkspaceMember, WorkspaceUpdate,
                                WorkspaceTodo, WorkspaceNote, WorkspaceFile)
from ..schemas.models import WorkspaceIn, WsUpdateIn, WsTodoIn, WsTodoPatch, WsNoteIn

router = APIRouter(tags=["workspaces"])


def _can_access(db, ws_id, user) -> bool:
    ws = db.get(Workspace, ws_id)
    if not ws:
        return False
    if ws.owner_id == user.id:
        return True
    return db.query(WorkspaceMember).filter_by(
        workspace_id=ws_id, user_id=user.id).first() is not None


def _guard(db, ws_id, user):
    if not _can_access(db, ws_id, user):
        raise HTTPException(403, "仅工作台成员可访问")


@router.get("/workspaces")
def my_workspaces(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owned = db.query(Workspace).filter_by(owner_id=user.id).all()
    member_ids = {m.workspace_id for m in db.query(WorkspaceMember)
                  .filter_by(user_id=user.id).all()}
    others = db.query(Workspace).filter(Workspace.id.in_(member_ids)).all() if member_ids else []
    seen = set()
    out = []
    for w in owned + others:
        if w.id in seen:
            continue
        seen.add(w.id)
        out.append({"id": w.id, "title": w.title, "overleaf_url": w.overleaf_url,
                    "is_owner": w.owner_id == user.id})
    return out


@router.post("/workspaces")
def create_ws(body: WorkspaceIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    w = Workspace(owner_id=user.id, title=body.title, overleaf_url=body.overleaf_url)
    db.add(w); db.flush()
    db.add(WorkspaceMember(workspace_id=w.id, user_id=user.id))
    for uid in body.member_ids:
        if uid != user.id:
            db.add(WorkspaceMember(workspace_id=w.id, user_id=uid))
    db.commit()
    return {"id": w.id}


@router.get("/workspaces/{wid}")
def get_ws(wid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    w = db.get(Workspace, wid)
    ups = db.query(WorkspaceUpdate).filter_by(workspace_id=wid).order_by(
        WorkspaceUpdate.id.desc()).all()
    todos = db.query(WorkspaceTodo).filter_by(workspace_id=wid).all()
    notes = db.query(WorkspaceNote).filter_by(workspace_id=wid).all()
    files = db.query(WorkspaceFile).filter_by(workspace_id=wid).all()
    members = db.query(WorkspaceMember).filter_by(workspace_id=wid).all()
    return {"id": w.id, "title": w.title, "overleaf_url": w.overleaf_url,
            "is_owner": w.owner_id == user.id,
            "members": [m.user_id for m in members],
            "updates": [{"id": u.id, "author_id": u.author_id, "body": u.body} for u in ups],
            "todos": [{"id": t.id, "text": t.text, "done": t.done,
                       "assignee_id": t.assignee_id} for t in todos],
            "notes": [{"id": n.id, "author_id": n.author_id, "body": n.body} for n in notes],
            "files": [{"id": f.id, "file_name": f.file_name} for f in files]}


@router.patch("/workspaces/{wid}")
def edit_ws(wid: int, body: WorkspaceIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    w = db.get(Workspace, wid)
    if not w or w.owner_id != user.id:
        raise HTTPException(403, "仅创建者可改")
    w.title = body.title; w.overleaf_url = body.overleaf_url
    # 更新成员
    db.query(WorkspaceMember).filter_by(workspace_id=wid).delete()
    db.add(WorkspaceMember(workspace_id=wid, user_id=user.id))
    for uid in body.member_ids:
        if uid != user.id:
            db.add(WorkspaceMember(workspace_id=wid, user_id=uid))
    db.commit()
    return {"ok": True}


@router.delete("/workspaces/{wid}")
def del_ws(wid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    w = db.get(Workspace, wid)
    if not w or w.owner_id != user.id:
        raise HTTPException(403, "仅创建者可删")
    db.query(WorkspaceMember).filter_by(workspace_id=wid).delete()
    db.delete(w); db.commit()
    return {"ok": True}


# ---- updates ----
@router.post("/workspaces/{wid}/updates")
def add_update(wid: int, body: WsUpdateIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    u = WorkspaceUpdate(workspace_id=wid, author_id=user.id, body=body.body)
    db.add(u); db.commit()
    return {"id": u.id}


@router.patch("/workspaces/{wid}/updates/{uid}")
def edit_update(wid: int, uid: int, body: WsUpdateIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    u = db.get(WorkspaceUpdate, uid)
    if not u:
        raise HTTPException(404, "不存在")
    u.body = body.body; db.commit()
    return {"ok": True}


@router.delete("/workspaces/{wid}/updates/{uid}")
def del_update(wid: int, uid: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    u = db.get(WorkspaceUpdate, uid)
    if u:
        db.delete(u); db.commit()
    return {"ok": True}


# ---- todos ----
@router.post("/workspaces/{wid}/todos")
def add_todo(wid: int, body: WsTodoIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    t = WorkspaceTodo(workspace_id=wid, text=body.text, assignee_id=body.assignee_id)
    db.add(t); db.commit()
    return {"id": t.id}


@router.patch("/workspaces/{wid}/todos/{tid}")
def patch_todo(wid: int, tid: int, body: WsTodoPatch, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    t = db.get(WorkspaceTodo, tid)
    if not t:
        raise HTTPException(404, "不存在")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(t, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/workspaces/{wid}/todos/{tid}")
def del_todo(wid: int, tid: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    t = db.get(WorkspaceTodo, tid)
    if t:
        db.delete(t); db.commit()
    return {"ok": True}


# ---- notes ----
@router.post("/workspaces/{wid}/notes")
def add_note(wid: int, body: WsNoteIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    n = WorkspaceNote(workspace_id=wid, author_id=user.id, body=body.body)
    db.add(n); db.commit()
    return {"id": n.id}


@router.delete("/workspaces/{wid}/notes/{nid}")
def del_note(wid: int, nid: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    n = db.get(WorkspaceNote, nid)
    if n:
        db.delete(n); db.commit()
    return {"ok": True}


# ================= 工作台文件上传/下载 =================
from fastapi import UploadFile, File  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402


@router.post("/workspaces/{wid}/files")
def upload_ws_file(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    from ..services.uploads import save_upload
    _guard(db, wid, user)
    meta = save_upload(file, f"workspace/{wid}")
    f = WorkspaceFile(workspace_id=wid, **meta)
    db.add(f); db.commit(); db.refresh(f)
    return {"id": f.id, "file_name": f.file_name}


@router.get("/workspaces/{wid}/files/{fid}/download")
def download_ws_file(wid: int, fid: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    from ..core.storage import storage
    _guard(db, wid, user)
    f = db.get(WorkspaceFile, fid)
    if not f or f.workspace_id != wid:
        raise HTTPException(404, "文件不存在")
    return StreamingResponse(storage.open(f.file_path), media_type=f.mime or "application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{f.file_name}"'})


@router.delete("/workspaces/{wid}/files/{fid}")
def del_ws_file(wid: int, fid: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _guard(db, wid, user)
    f = db.get(WorkspaceFile, fid)
    if f:
        from ..core.storage import storage
        try: storage.delete(f.file_path)
        except Exception: pass
        db.delete(f); db.commit()
    return {"ok": True}
