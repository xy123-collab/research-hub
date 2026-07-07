from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, JSON, Float
from ..core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(80))
    object_type = Column(String(60)); object_id = Column(String(60))
    detail_json = Column(JSON); ip = Column(String(60))


class ContributionEvent(Base):
    __tablename__ = "contribution_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    event_type = Column(String(40))   # bug_accepted|code_bug_accepted|data_upload|code_add|post|correction|skill_create|skill_improve
    ref_type = Column(String(40)); ref_id = Column(String(60))
    weight = Column(Float, default=1.0)


class QualityRule(Base):
    __tablename__ = "quality_rules"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    code = Column(String(80)); name_zh = Column(String(160)); name_en = Column(String(160))
    expr_or_desc = Column(Text); enabled = Column(Boolean, default=True)


class QualityRun(Base):
    __tablename__ = "quality_runs"
    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("quality_rules.id"))
    version_id = Column(Integer, ForeignKey("data_versions.id"))
    run_by = Column(Integer, ForeignKey("users.id"))
    status = Column(String(20)); n_failed = Column(Integer, default=0)
    detail_json = Column(JSON)


class VerifyFlag(Base):
    __tablename__ = "verify_flags"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    version_id = Column(Integer, ForeignKey("data_versions.id"))
    source = Column(String(10))   # rule | ai
    officer_id = Column(String(80)); term_id = Column(String(80))
    variable_name = Column(String(80))
    issue_desc = Column(Text); confidence = Column(Float)   # rule=1.0; ai 0-1
    status = Column(String(20), default="open")   # open|confirmed|dismissed|drafted|fixed
    drafted_bug_id = Column(Integer, ForeignKey("bugs.id"))
