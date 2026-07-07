from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean
from ..core.db import Base


class Resume(Base):
    __tablename__ = "resumes"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    from_template = Column(Boolean, default=False)


class ResumeBlock(Base):
    __tablename__ = "resume_blocks"
    id = Column(Integer, primary_key=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"))
    seq = Column(Integer, default=0)
    type = Column(String(8))   # h | h2 | p | li
    text_zh = Column(Text); text_en = Column(Text)
