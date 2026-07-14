"""本轮精修新增表（均为新表，靠 create_all 自动建，无需迁移旧表）。

覆盖：个人主页扩展(研究方向/关键词)、项目置顶与封面、工作台时间轴条目、
其他协作分区、Skill 扩展(可见范围/文件/文本)、Skill 评论、
邮件事件记录、找回密码令牌。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime, JSON
from ..core.db import Base


# ---------- 个人主页扩展 ----------
class UserProfile(Base):
    """用户主页附加信息：研究方向、关键词。每用户一行（懒创建）。"""
    __tablename__ = "user_profiles"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    research_direction = Column(Text)   # 研究方向
    keywords = Column(Text)             # 关键词，逗号分隔


# ---------- 在做项目：置顶 + 封面图 ----------
class ProjectMeta(Base):
    """项目扩展：置顶、封面图。每项目一行。"""
    __tablename__ = "project_meta"
    project_id = Column(Integer, ForeignKey("projects.id"), primary_key=True)
    pinned = Column(Boolean, default=False)
    image_path = Column(String(300))
    image_name = Column(String(200))
    image_mime = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 工作台时间轴条目（相册式 + 分类）----------
WORKSPACE_CATEGORIES = ["progress", "data", "figure", "literature", "result", "discussion", "other"]


class WorkspaceEntry(Base):
    """工作台时间轴条目：分类 + 文字 + 可选文件（图片相册式展示）。"""
    __tablename__ = "workspace_entries"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    category = Column(String(20), default="progress")   # WORKSPACE_CATEGORIES
    title = Column(String(200))
    body = Column(Text)
    file_path = Column(String(300))
    file_name = Column(String(200))
    mime = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 其他协作：分区 ----------
class CollabSection(Base):
    """协作分区：内置 skill 分区 + 用户自建其他类型协作分区。"""
    __tablename__ = "collab_sections"
    id = Column(Integer, primary_key=True)
    key = Column(String(60), unique=True)   # skill / 自定义唯一键
    name_zh = Column(String(160)); name_en = Column(String(160))
    desc_zh = Column(Text)
    kind = Column(String(20), default="generic")   # skill | generic
    created_by = Column(Integer, ForeignKey("users.id"))
    seq = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- Skill 扩展：可见范围 / 文件 / 文本 ----------
SKILL_SCOPES = ["public", "group", "dataset", "self"]   # 公开/课题组成员/数据集成员/仅自己


class SkillMeta(Base):
    """Skill 附加信息：所属分区、可见范围、正文文本、附件文件。"""
    __tablename__ = "skill_meta"
    skill_id = Column(Integer, ForeignKey("skills.id"), primary_key=True)
    section_id = Column(Integer, ForeignKey("collab_sections.id"))
    scope = Column(String(20), default="public")        # SKILL_SCOPES
    scope_ref_id = Column(Integer)                       # group_id 或 dataset_id
    body_text = Column(Text)
    file_path = Column(String(300))
    file_name = Column(String(200))
    mime = Column(String(120))
    created_at = Column(DateTime, default=datetime.utcnow)


class SkillComment(Base):
    """Skill 评论（支持对评论回复：parent_id）。"""
    __tablename__ = "skill_comments"
    id = Column(Integer, primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    parent_id = Column(Integer, ForeignKey("skill_comments.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 邮件事件（抽象层记录；未来接 SMTP/API）----------
class EmailEvent(Base):
    """邮件事件记录：无论 mock 还是真实发送都落一条，便于审计与去重。"""
    __tablename__ = "email_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    to_email = Column(String(200))
    subject = Column(String(300))
    body = Column(Text)
    kind = Column(String(40))       # digest | password_reset | invite | system
    status = Column(String(20), default="mock")   # mock | sent | failed | skipped
    error = Column(Text)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------- 找回密码令牌 ----------
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String(80), unique=True)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
