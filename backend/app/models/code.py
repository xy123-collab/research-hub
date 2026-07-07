from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from ..core.db import Base


class CodeScript(Base):
    __tablename__ = "code_scripts"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    filename = Column(String(200)); lang = Column(String(20))   # Stata|Python|R
    title_zh = Column(String(200)); title_en = Column(String(200))
    desc_zh = Column(Text); desc_en = Column(Text)
    source_code = Column(Text)
    author_id = Column(Integer, ForeignKey("users.id"))
    reuse_count = Column(Integer, default=0)


class CodeBug(Base):
    __tablename__ = "code_bugs"
    id = Column(Integer, primary_key=True)
    script_id = Column(Integer, ForeignKey("code_scripts.id"))
    reporter_id = Column(Integer, ForeignKey("users.id"))
    line_ref = Column(String(40))
    description_zh = Column(Text); description_en = Column(Text)
    suggested_patch = Column(Text)
    status = Column(String(20), default="pending")
    fixed_in_version_id = Column(Integer)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)


class CodeWriteup(Base):
    __tablename__ = "code_writeups"
    id = Column(Integer, primary_key=True)
    script_id = Column(Integer, ForeignKey("code_scripts.id"))
    body_zh = Column(Text); body_en = Column(Text)
    ai_model = Column(String(80))
    generated_by = Column(Integer, ForeignKey("users.id"))
