from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Text, Boolean, DateTime
from ..core.db import Base


class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))   # 可空
    group_id = Column(Integer, ForeignKey("research_groups.id"))  # visibility=group 时
    title = Column(String(300))                            # 帖子标题（可选）
    post_type = Column(String(30), default="discussion")   # 讨论类型：question/data/method/collab/discussion
    content_zh = Column(Text); content_en = Column(Text)
    cover_icon = Column(String(80))
    visibility = Column(String(20), default="platform")   # platform|group|private
    status = Column(String(20), default="open")           # open|resolved|closed
    created_at = Column(DateTime, default=datetime.utcnow)


class PostFollow(Base):
    """关注帖子：有人关注我的帖子会产生通知；也用于「我关注的讨论」。"""
    __tablename__ = "post_follows"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class PostAttachment(Base):
    __tablename__ = "post_attachments"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    file_path = Column(String(300)); file_name = Column(String(200))
    mime = Column(String(120)); size = Column(Integer)


class PostVariable(Base):
    __tablename__ = "post_variables"
    post_id = Column(Integer, ForeignKey("posts.id"), primary_key=True)
    variable_id = Column(Integer, ForeignKey("variables.id"), primary_key=True)


class PostTag(Base):
    __tablename__ = "post_tags"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    tag = Column(String(80))


class PostReaction(Base):
    __tablename__ = "post_reactions"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String(20))   # like | favorite
    created_at = Column(DateTime, default=datetime.utcnow)


class PostComment(Base):
    __tablename__ = "post_comments"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    parent_id = Column(Integer, ForeignKey("post_comments.id"))   # 评论的评论
    created_at = Column(DateTime, default=datetime.utcnow)


class PostCommentReaction(Base):
    """评论点赞：所有入口的帖子评论共用（一份数据）。"""
    __tablename__ = "post_comment_reactions"
    id = Column(Integer, primary_key=True)
    comment_id = Column(Integer, ForeignKey("post_comments.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String(20), default="like")
    created_at = Column(DateTime, default=datetime.utcnow)


class PostAdminFlag(Base):
    __tablename__ = "post_admin_flags"
    post_id = Column(Integer, ForeignKey("posts.id"), primary_key=True)
    is_recommended = Column(Boolean, default=False)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    title = Column(String(200)); body_zh = Column(Text); body_en = Column(Text)
    cover_icon = Column(String(80)); status = Column(String(40))
    open_for_discussion = Column(Boolean, default=True)
    visibility = Column(String(20), default="platform")


class ProjectAttachment(Base):
    __tablename__ = "project_attachments"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    file_path = Column(String(300)); file_name = Column(String(200))
    mime = Column(String(120)); size = Column(Integer)


class ProjectTag(Base):
    __tablename__ = "project_tags"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    tag = Column(String(80))


class ProjectComment(Base):
    __tablename__ = "project_comments"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    parent_id = Column(Integer, ForeignKey("project_comments.id"))   # 评论的评论
    created_at = Column(DateTime, default=datetime.utcnow)
