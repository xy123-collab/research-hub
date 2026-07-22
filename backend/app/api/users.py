from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from ..core.db import get_db
from ..core.permissions import get_current_user
from ..models.user import User
from ..models.resume import Resume, ResumeBlock
from ..models.community import Post, Project
from ..models.extras import UserProfile
from ..schemas.models import ResumeBlockIn
from ..services.scoring import user_total

router = APIRouter(tags=["users"])


class ProfilePatch(BaseModel):
    display_name: str | None = None
    bio_zh: str | None = None
    bio_en: str | None = None
    avatar: str | None = None
    preferred_language: str | None = None
    contact: str | None = None
    research_direction: str | None = None   # 研究方向（存 UserProfile）
    keywords: str | None = None             # 关键词（存 UserProfile）
    email: str | None = None                # 公开联系邮箱（存 UserProfile，选填）


def _profile_extra(db: Session, uid: int) -> UserProfile:
    p = db.get(UserProfile, uid)
    if not p:
        p = UserProfile(user_id=uid); db.add(p); db.flush()
    return p


@router.get("/users/search")
def search_users(q: str = "", limit: int = 20, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """按姓名 / 用户名 / ID 检索平台全体成员（用于邀请/授权）。"""
    q = (q or "").strip()
    query = db.query(User).filter(User.status != "left")
    if q:
        conds = [User.display_name.ilike(f"%{q}%"), User.username.ilike(f"%{q}%")]
        if q.isdigit():
            conds.append(User.id == int(q))
        query = query.filter(or_(*conds))
    rows = query.order_by(User.id).limit(min(limit, 50)).all()
    return [{"id": u.id, "display_name": u.display_name, "username": u.username,
             "avatar": u.avatar} for u in rows]


@router.get("/me/collab-scopes")
def my_collab_scopes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """我所在的课题组与数据集，供发布内容时的「可见范围」下拉选择。"""
    from ..models.group import ResearchGroup, GroupMember
    from ..models.dataset import Dataset, DatasetMember
    gids = [m.group_id for m in db.query(GroupMember).filter_by(
        user_id=user.id, status="active").all()]
    dids = [m.dataset_id for m in db.query(DatasetMember).filter_by(user_id=user.id).all()]
    groups = db.query(ResearchGroup).filter(ResearchGroup.id.in_(gids or [-1])).all()
    datasets = db.query(Dataset).filter(Dataset.id.in_(dids or [-1])).all()
    return {"groups": [{"id": g.id, "name": g.name_zh, "slug": g.slug} for g in groups],
            "datasets": [{"id": d.id, "name": d.name_zh, "slug": d.slug,
                          "group_id": d.group_id} for d in datasets]}


@router.get("/users/{uid}")
def get_user(uid: int, db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "用户不存在")
    posts = db.query(Post).filter_by(author_id=uid, visibility="platform").count()
    projects = db.query(Project).filter_by(author_id=uid).count()
    ex = db.get(UserProfile, uid)
    summary = _contrib_summary(db, uid)
    return {"id": u.id, "username": u.username, "display_name": u.display_name,
            "bio_zh": u.bio_zh, "bio_en": u.bio_en, "avatar": u.avatar,
            "contact": u.contact, "contribution": summary["total"],
            "contribution_breakdown": summary["breakdown"],
            "research_direction": ex.research_direction if ex else None,
            "keywords": ex.keywords if ex else None,
            "email": ex.email if ex else None,
            "post_count": posts, "project_count": projects}


@router.patch("/me")
def patch_me(body: ProfilePatch, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    extra_keys = {"research_direction", "keywords", "email"}
    if data.keys() & extra_keys:
        p = _profile_extra(db, user.id)
        for k in list(extra_keys):
            if k in data:
                setattr(p, k, data.pop(k))
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    return {"ok": True}


# -------- 注册邮箱（账号邮箱）：本人查看 / 修改 / 发测试信 --------
import re as _re

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountEmailIn(BaseModel):
    email: str


@router.get("/me/account-email")
def get_account_email(user: User = Depends(get_current_user)):
    """返回本人注册邮箱（账号邮箱），仅本人可见。"""
    return {"email": user.email or ""}


@router.put("/me/account-email")
def set_account_email(body: AccountEmailIn, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """修改本人注册邮箱：校验格式 + 全局唯一（找回密码等靠它）。"""
    from ..core.naming import ensure_unique
    email = (body.email or "").strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "邮箱格式不正确")
    ensure_unique(db, User, "email", email, "注册邮箱", exclude_id=user.id)
    user.email = email
    db.commit()
    return {"ok": True, "email": email}


@router.post("/me/test-email")
def send_test_email(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """给本人注册邮箱发一封测试邮件，用于验证邮件（SMTP）配置是否生效。
    返回投递状态，前端可据此提示成功/失败原因。"""
    from ..core.email_service import send_email
    from ..core.config import settings
    if not (user.email or "").strip():
        raise HTTPException(400, "你还没有设置注册邮箱，请先填写并保存")
    ev = send_email(
        db, user_id=user.id, to_email=user.email,
        subject="【科研数据共享平台】测试邮件",
        body=(f"{user.display_name or user.username} 你好：\n\n"
              "这是一封来自科研数据共享平台的测试邮件。\n"
              "如果你收到了它，说明平台的邮件发送配置已经生效，"
              "密码找回、每日消息摘要等邮件功能都可以正常使用。\n\n"
              "——科研数据共享平台"),
        kind="system", meta={"kind": "test"})
    return {"status": ev.status, "error": ev.error, "to": user.email,
            "backend": settings.EMAIL_BACKEND}


# -------- 邮件提醒开关（注册后默认开启；开/关都发一封确认信）--------
class EmailPrefIn(BaseModel):
    opt_in: bool


def _email_opt_in(db: Session, uid: int) -> bool:
    p = db.get(UserProfile, uid)
    # 未设置（None）视为开启，符合"注册后默认开启"
    return True if (not p or p.email_opt_in is None) else bool(p.email_opt_in)


@router.get("/me/email-pref")
def get_email_pref(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"opt_in": _email_opt_in(db, user.id), "email": user.email or ""}


@router.put("/me/email-pref")
def set_email_pref(body: EmailPrefIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """开启/关闭邮件提醒。两个方向都发一封确认邮件（关闭时这封是最后一封）。"""
    from ..core.email_service import send_email
    from ..core.config import settings
    p = _profile_extra(db, user.id)
    p.email_opt_in = bool(body.opt_in)
    db.commit()
    # 发确认信（无邮箱或投递失败都不阻断开关本身）
    email_status = "skipped"; email_error = None
    if (user.email or "").strip():
        if body.opt_in:
            subject = "【科研数据共享平台】邮件提醒已开启"
            text = ("你已开启邮件提醒。此后密码找回、每日消息摘要等邮件会正常发送到此邮箱。\n"
                    "如需关闭，可在个人主页「编辑资料」里再次切换。")
        else:
            subject = "【科研数据共享平台】邮件提醒已关闭"
            text = ("你已关闭邮件提醒，这是最后一封提醒邮件。此后平台不再向此邮箱发送每日摘要等提醒。\n"
                    "（出于账号安全，密码找回等必要邮件仍会发送。）\n"
                    "如需重新开启，可在个人主页「编辑资料」里再次切换。")
        ev = send_email(db, user_id=user.id, to_email=user.email, subject=subject,
                        body=f"{user.display_name or user.username} 你好：\n\n{text}\n\n——科研数据共享平台",
                        kind="system", meta={"kind": "email_pref", "opt_in": body.opt_in})
        email_status = ev.status; email_error = ev.error
    return {"ok": True, "opt_in": body.opt_in,
            "email_status": email_status, "email_error": email_error,
            "backend": settings.EMAIL_BACKEND}


@router.post("/me/avatar")
def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """上传头像图片，返回可访问 URL 并写入 user.avatar。"""
    from ..services.uploads import save_upload, IMG_EXT
    meta = save_upload(file, f"avatar/{user.id}", whitelist=IMG_EXT)
    user.avatar = f"/api/me/avatar/file?k={meta['file_path']}"
    db.commit()
    return {"avatar": user.avatar}


@router.get("/me/avatar/file")
def get_avatar_file(k: str, db: Session = Depends(get_db)):
    from ..core.storage import storage
    if not k.startswith("avatar/"):
        raise HTTPException(400, "非法路径")
    try:
        from ..services.uploads import open_stored_file
        return StreamingResponse(open_stored_file(k), media_type="image/*")
    except Exception:
        raise HTTPException(404, "头像不存在")


# -------- resume --------
@router.get("/users/{uid}/resume")
def get_resume(uid: int, db: Session = Depends(get_db)):
    r = db.query(Resume).filter_by(user_id=uid).first()
    if not r:
        return {"resume": None, "blocks": []}
    blocks = (db.query(ResumeBlock).filter_by(resume_id=r.id)
              .order_by(ResumeBlock.seq).all())
    return {"resume": {"id": r.id, "from_template": r.from_template},
            "blocks": [{"id": b.id, "seq": b.seq, "type": b.type,
                        "text_zh": b.text_zh, "text_en": b.text_en} for b in blocks]}


@router.put("/me/resume")
def upsert_resume(from_template: bool = False, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    r = db.query(Resume).filter_by(user_id=user.id).first()
    if not r:
        r = Resume(user_id=user.id, from_template=from_template)
        db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id}


class ResumeBulkIn(BaseModel):
    blocks: list[ResumeBlockIn]


@router.put("/me/resume/blocks")
def replace_blocks(body: ResumeBulkIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """整块替换本人简历：一次保存所有块（支持排序/增删/编辑）。

    前端把整份简历当一个文本/表单编辑，保存时一次提交，避免一行一行操作。
    """
    r = db.query(Resume).filter_by(user_id=user.id).first()
    if not r:
        r = Resume(user_id=user.id); db.add(r); db.commit(); db.refresh(r)
    db.query(ResumeBlock).filter_by(resume_id=r.id).delete()
    for i, b in enumerate(body.blocks):
        db.add(ResumeBlock(resume_id=r.id, type=b.type, text_zh=b.text_zh,
                           text_en=b.text_en, seq=i))
    db.commit()
    return {"ok": True, "count": len(body.blocks)}


@router.post("/me/resume/blocks")
def add_block(body: ResumeBlockIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    r = db.query(Resume).filter_by(user_id=user.id).first()
    if not r:
        r = Resume(user_id=user.id); db.add(r); db.commit(); db.refresh(r)
    b = ResumeBlock(resume_id=r.id, type=body.type, text_zh=body.text_zh,
                    text_en=body.text_en, seq=body.seq)
    db.add(b); db.commit(); db.refresh(b)
    return {"id": b.id}


@router.patch("/me/resume/blocks/{bid}")
def edit_block(bid: int, body: ResumeBlockIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    b = db.get(ResumeBlock, bid)
    if not b:
        raise HTTPException(404, "块不存在")
    r = db.get(Resume, b.resume_id)
    if r.user_id != user.id:
        raise HTTPException(403, "只能编辑本人简历")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(b, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/me/resume/blocks/{bid}")
def del_block(bid: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    b = db.get(ResumeBlock, bid)
    if not b:
        raise HTTPException(404, "块不存在")
    r = db.get(Resume, b.resume_id)
    if r.user_id != user.id:
        raise HTTPException(403, "只能编辑本人简历")
    db.delete(b); db.commit()
    return {"ok": True}


# ---- 贡献度：公开汇总 + 按权限过滤的明细 ----
CONTRIB_CATEGORIES = {
    "bug_accepted": "数据勘误", "correction": "数据勘误",
    "review_adopted": "核验", "verify": "核验",
    "code_bug_accepted": "代码勘误", "code_add": "代码贡献",
    "data_upload": "数据发布", "dataset_founder": "数据发布",
    "post": "讨论发帖", "skill_create": "Skill 贡献", "skill_improve": "Skill 贡献",
    "lit_upload": "文献上传",
}


def _contrib_summary(db: Session, uid: int) -> dict:
    """公开的贡献汇总：总分 + 按类别的次数。仅聚合数字，不含具体内容，任何人可见。"""
    from ..models.governance import ContributionEvent
    rows = db.query(ContributionEvent).filter_by(user_id=uid).all()
    breakdown: dict[str, int] = {}
    for e in rows:
        label = CONTRIB_CATEGORIES.get(e.event_type, "其他")
        breakdown[label] = breakdown.get(label, 0) + 1
    return {"total": user_total(db, uid),
            "breakdown": [{"label": k, "count": v} for k, v in breakdown.items()]}


def _contrib_event_visible(db: Session, ev, viewer: User) -> bool:
    """明细是否对访问者可见：本人/管理员全可见；无数据集(帖子/skill)公开；
    公开数据集或访问者为其成员可见；否则计入「非公开」。"""
    from ..models.dataset import Dataset, DatasetMember
    if viewer and (ev.user_id == viewer.id):
        return True
    if not ev.dataset_id:
        return True
    d = db.get(Dataset, ev.dataset_id)
    if d and d.is_public:
        return True
    if viewer and db.query(DatasetMember).filter_by(
            dataset_id=ev.dataset_id, user_id=viewer.id).first():
        return True
    return False


@router.get("/users/{uid}/contributions")
def user_contributions(uid: int, viewer: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """他人可查看的贡献明细：只返回访问者有权看到的记录；
    不可公开的记录不逐条展示，但用「另有 N 项非公开贡献」告知，汇总分不消失。"""
    from ..models.governance import ContributionEvent
    from ..models.dataset import Dataset
    rows = db.query(ContributionEvent).filter_by(user_id=uid).all()
    ds_ids = {e.dataset_id for e in rows if e.dataset_id}
    ds_map = {d.id: d for d in db.query(Dataset).filter(
        Dataset.id.in_(ds_ids or [-1])).all()}
    events = []; hidden = 0
    for e in rows:
        if not _contrib_event_visible(db, e, viewer):
            hidden += 1
            continue
        d = ds_map.get(e.dataset_id)
        events.append({"type": e.event_type,
                       "category": CONTRIB_CATEGORIES.get(e.event_type, "其他"),
                       "ref_type": e.ref_type, "ref_id": e.ref_id,
                       "dataset_id": e.dataset_id,
                       "dataset_slug": d.slug if d else None,
                       "dataset_name": d.name_zh if d else None,
                       "weight": e.weight})
    summary = _contrib_summary(db, uid)
    return {"total": summary["total"], "breakdown": summary["breakdown"],
            "events": events, "hidden_count": hidden,
            "is_me": viewer and viewer.id == uid}


@router.get("/me/contributions")
def my_contributions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models.governance import ContributionEvent
    from ..models.dataset import Dataset
    rows = db.query(ContributionEvent).filter_by(user_id=user.id).all()
    # 预取涉及的数据集，供前端一键跳转
    ds_ids = {e.dataset_id for e in rows if e.dataset_id}
    ds_map = {d.id: d for d in db.query(Dataset).filter(
        Dataset.id.in_(ds_ids or [-1])).all()}
    events = []
    for e in rows:
        d = ds_map.get(e.dataset_id)
        events.append({"type": e.event_type, "ref_type": e.ref_type,
                       "ref_id": e.ref_id, "dataset_id": e.dataset_id,
                       "dataset_slug": d.slug if d else None,
                       "dataset_name": d.name_zh if d else None,
                       "weight": e.weight})
    return {"total": user_total(db, user.id), "events": events}


# -------- 简历 AI 一键排版 --------
class ResumeAIFormatIn(BaseModel):
    text: str


@router.post("/me/resume/ai-format")
def ai_format_resume(body: ResumeAIFormatIn, user: User = Depends(get_current_user)):
    """把用户散乱的简历文字整理成本平台的简历结构标记，仅返回文本供用户预览确认。

    结构约定与手动编辑一致：# 大标题 / ## 小标题 / - 分点 / 其余为正文。
    只做排版整理，不虚构内容。"""
    from ..core.ai_client import ai_client, OutboundGuardError
    raw = (body.text or "").strip()
    if not raw:
        raise HTTPException(400, "请先填写简历内容")
    if not ai_client.enabled():
        raise HTTPException(400, "AI 未启用：请在环境变量配置 AI_PROVIDER 与 AI_API_KEY")
    system = (
        "你是中文学术个人简历排版助手。把用户给的简历原文整理成规范的结构化纯文本，"
        "严格使用以下标记，每行一条：\n"
        "# 表示大标题（如：教育经历、工作经历、研究成果、获奖）\n"
        "## 表示小标题（如：某学校·某学位、某职位）\n"
        "- 表示分点（时间、职责、成果等）\n"
        "其余普通文字作为正文段落。\n"
        "要求：只做归类与排版，不要虚构或添加原文没有的信息；不要输出解释、不要用代码围栏、"
        "不要用 Markdown 加粗；直接输出整理后的文本。")
    try:
        out = ai_client.complete(raw, system=system)
    except OutboundGuardError as e:
        raise HTTPException(400, str(e))
    # 去掉可能的 ``` 围栏
    out = out.strip()
    if out.startswith("```"):
        out = "\n".join(l for l in out.splitlines() if not l.strip().startswith("```"))
    return {"text": out.strip()}
