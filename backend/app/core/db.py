from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, DeclarativeBase
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """所有表共用 created_at / updated_at。"""
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
