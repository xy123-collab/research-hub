from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, JSON, DateTime
from ..core.db import Base


class Skill(Base):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("research_groups.id"))   # 可空=平台级
    name_zh = Column(String(160)); name_en = Column(String(160))
    icon = Column(String(80)); desc_zh = Column(Text); desc_en = Column(Text)
    founder_id = Column(Integer, ForeignKey("users.id"))
    github_url = Column(String(300)); is_public = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)


class SkillMember(Base):
    __tablename__ = "skill_members"
    skill_id = Column(Integer, ForeignKey("skills.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    ds_role = Column(String(20), default="member")
    granted_perms_json = Column(JSON, default=list)


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    id = Column(Integer, primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.id"))
    version_id = Column(String(40)); notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))


class SkillBug(Base):
    __tablename__ = "skill_bugs"
    id = Column(Integer, primary_key=True)
    skill_id = Column(Integer, ForeignKey("skills.id"))
    reporter_id = Column(Integer, ForeignKey("users.id"))
    description_zh = Column(Text); description_en = Column(Text)
    suggested_patch = Column(Text)
    status = Column(String(20), default="pending")
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)


class GithubSkillReco(Base):
    __tablename__ = "github_skill_recos"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("research_groups.id"))
    name = Column(String(160)); note = Column(Text); github_url = Column(String(300))
    added_by = Column(Integer, ForeignKey("users.id"))
