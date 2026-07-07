from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship
from ..core.db import Base


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)   # super_admin / member
    name_zh = Column(String(100)); name_en = Column(String(100))


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    code = Column(String(80), unique=True, nullable=False)
    desc_zh = Column(String(200)); desc_en = Column(String(200))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), primary_key=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(160))
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(120))
    avatar = Column(String(255))
    bio_zh = Column(Text); bio_en = Column(Text)
    role_id = Column(Integer, ForeignKey("roles.id"))
    preferred_language = Column(String(4), default="zh")   # zh | en
    status = Column(String(20), default="active")          # active | external | left
    contact = Column(String(200))
    role = relationship("Role", lazy="joined")
