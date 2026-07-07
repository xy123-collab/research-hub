from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, JSON
from ..core.db import Base


class LitTopic(Base):
    __tablename__ = "lit_topics"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    parent_id = Column(Integer, ForeignKey("lit_topics.id"))
    title_zh = Column(String(200)); title_en = Column(String(200))
    ai_generated = Column(Boolean, default=False)
    updated_by = Column(Integer, ForeignKey("users.id"))


class LitRef(Base):
    __tablename__ = "lit_refs"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    title = Column(String(300)); authors = Column(String(300))
    venue = Column(String(200)); year = Column(Integer); url = Column(String(300))
    note_zh = Column(Text); note_en = Column(Text)
    added_by = Column(Integer, ForeignKey("users.id"))


class DatasetSummaryAI(Base):
    __tablename__ = "dataset_summary_ai"
    dataset_id = Column(Integer, ForeignKey("datasets.id"), primary_key=True)
    purpose_zh = Column(Text); purpose_en = Column(Text)
    topics_json = Column(JSON); ai_model = Column(String(80))
    edited_by = Column(Integer, ForeignKey("users.id"))


class Publication(Base):
    __tablename__ = "publications"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    title = Column(String(300)); venue = Column(String(200)); year = Column(Integer)
    url = Column(String(300)); used_version = Column(String(40))
    source = Column(String(40))   # manual | crossref


class DatasetSummary(Base):
    """派生汇总长表，看板从此出图，不直读 .dta。"""
    __tablename__ = "dataset_summaries"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    version_id = Column(Integer, ForeignKey("data_versions.id"))
    var_name = Column(String(80)); group_key = Column(String(80))
    bucket = Column(String(120)); value = Column(String(120))


class AnalysisSnippet(Base):
    __tablename__ = "analysis_snippets"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    prompt = Column(Text); code = Column(Text); lang = Column(String(20))
    ai_generated = Column(Boolean, default=False)
    result_json = Column(JSON); chart_path = Column(String(300))
