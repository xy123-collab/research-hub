from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime, JSON
from ..core.db import Base


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("research_groups.id"))
    slug = Column(String(80), unique=True, nullable=False)
    name_zh = Column(String(160)); name_en = Column(String(160))
    icon = Column(String(80))
    desc_zh = Column(Text); desc_en = Column(Text)
    join_key = Column(String(80))
    founder_id = Column(Integer, ForeignKey("users.id"))
    founder_contact = Column(String(200), nullable=False)   # 必填
    current_version_id = Column(Integer)
    is_public = Column(Boolean, default=True)
    is_sensitive = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)


class DatasetMember(Base):
    __tablename__ = "dataset_members"
    dataset_id = Column(Integer, ForeignKey("datasets.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    ds_role = Column(String(20), default="member")   # founder|maintainer|member
    granted_perms_json = Column(JSON, default=list)
    joined_at = Column(DateTime)
    approved_by = Column(Integer, ForeignKey("users.id"))


class JoinRequest(Base):
    __tablename__ = "join_requests"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    status = Column(String(20), default="pending")
    decided_by = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime)


class Variable(Base):
    __tablename__ = "variables"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    var_name = Column(String(80))
    group_code = Column(String(80))
    label_zh = Column(String(200)); label_en = Column(String(200))
    enabled = Column(Boolean, default=True)
