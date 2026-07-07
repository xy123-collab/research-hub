from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime
from ..core.db import Base


class ResearchGroup(Base):
    __tablename__ = "research_groups"
    id = Column(Integer, primary_key=True)
    slug = Column(String(80), unique=True, nullable=False)
    name_zh = Column(String(160)); name_en = Column(String(160))
    icon = Column(String(80))
    desc_zh = Column(Text); desc_en = Column(Text)
    discoverable = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)   # 软删除
    created_by = Column(Integer, ForeignKey("users.id"))


class GroupMember(Base):
    __tablename__ = "group_members"
    group_id = Column(Integer, ForeignKey("research_groups.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    group_role = Column(String(20), default="member")   # group_admin | member
    show_on_profile = Column(Boolean, default=True)
    status = Column(String(20), default="active")
    joined_at = Column(DateTime)
    approved_by = Column(Integer, ForeignKey("users.id"))


class GroupJoinRequest(Base):
    __tablename__ = "group_join_requests"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("research_groups.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    status = Column(String(20), default="pending")   # pending|approved|rejected
    decided_by = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime)


class Charter(Base):
    __tablename__ = "charters"
    id = Column(Integer, primary_key=True)
    scope = Column(String(20))          # group | dataset
    ref_id = Column(Integer)            # group_id 或 dataset_id
    body_zh = Column(Text); body_en = Column(Text)
    version = Column(Integer, default=1)
    updated_by = Column(Integer, ForeignKey("users.id"))


class CharterAck(Base):
    __tablename__ = "charter_acks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    charter_id = Column(Integer, ForeignKey("charters.id"))
    charter_version = Column(Integer)
    acked_at = Column(DateTime)
