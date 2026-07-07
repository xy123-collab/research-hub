from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean
from ..core.db import Base


class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(200)); overleaf_url = Column(String(300))


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)


class WorkspaceUpdate(Base):
    __tablename__ = "workspace_updates"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    body = Column(Text)


class WorkspaceTodo(Base):
    __tablename__ = "workspace_todos"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    text = Column(Text); done = Column(Boolean, default=False)
    assignee_id = Column(Integer, ForeignKey("users.id"))


class WorkspaceNote(Base):
    __tablename__ = "workspace_notes"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    body = Column(Text)


class WorkspaceFile(Base):
    __tablename__ = "workspace_files"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"))
    file_path = Column(String(300)); file_name = Column(String(200))
    mime = Column(String(120)); size = Column(Integer)
