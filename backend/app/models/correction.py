from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Float
from ..core.db import Base


class Bug(Base):
    __tablename__ = "bugs"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    reporter_id = Column(Integer, ForeignKey("users.id"))
    related_version_id = Column(Integer, ForeignKey("data_versions.id"))
    officer_id = Column(String(80)); term_id = Column(String(80))
    variable_id = Column(Integer, ForeignKey("variables.id"))
    current_value = Column(String(300)); suggested_value = Column(String(300))
    bug_type = Column(String(60))
    description_zh = Column(Text); description_en = Column(Text)
    evidence = Column(Text)
    status = Column(String(20), default="pending")   # pending|accepted|rejected|fixed
    fixed_in_version_id = Column(Integer, ForeignKey("data_versions.id"))
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)


class BugAttachment(Base):
    __tablename__ = "bug_attachments"
    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey("bugs.id"))
    file_path = Column(String(300)); file_name = Column(String(200))
    mime = Column(String(120)); size = Column(Integer)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime)


class CorrectionReview(Base):
    """成员评审 + AI 自动评审（0-10 可采纳度）。bug + code_bug 共用。"""
    __tablename__ = "correction_reviews"
    id = Column(Integer, primary_key=True)
    target_type = Column(String(20))    # bug | code_bug
    target_id = Column(Integer)
    reviewer_type = Column(String(10))  # member | ai
    reviewer_id = Column(Integer, ForeignKey("users.id"))   # ai 为空
    acceptability_score = Column(Float)   # 0-10
    comment = Column(Text)


class CorrectionFinal(Base):
    """管理员终审（唯一）。贡献度按 final_score 加权。"""
    __tablename__ = "correction_finals"
    id = Column(Integer, primary_key=True)
    target_type = Column(String(20)); target_id = Column(Integer)
    decided_by = Column(Integer, ForeignKey("users.id"))
    adopt_level = Column(String(20))   # full | partial | reject
    final_score = Column(Float)        # 0-10
    comment = Column(Text)
    decided_at = Column(DateTime)
