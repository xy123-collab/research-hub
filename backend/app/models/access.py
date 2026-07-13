"""权限规则落地新增表（均为新表，靠 create_all 自动建，无需迁移旧表）。

对应《科研数据协作平台权限规则》：
- DatasetGrant   六节「单独授权」，带到期规则（永久/指定日期/指定版本/指定项目）
- DatasetSettings 七节「下载权限类型」与十节「数据集关闭」等数据集级开关
- DownloadRequest 七节「下载申请」：研究用途/版本/预计时间/是否共享/是否同意公约
- VersionCandidate 九节「上传候选文件」：获授权成员可上传候选，管理员发布
- CodebookDraft   六节「编辑 codebook 草稿」
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime
from ..core.db import Base


# 可单独授予的权限码（六节）——前后端共用白名单
GRANTABLE_PERMS = [
    "download.current",     # 下载当前完整正式版本
    "download.masked",      # 下载脱敏数据
    "version.history.view", # 查看历史版本
    "download.history",     # 下载历史版本
    "analysis.online",      # 在线分析功能
    "upload.candidate",     # 上传版本候选文件
    "codebook.draft",       # 编辑 codebook 草稿
    "code.maintain",        # 上传和维护处理代码
]

PERM_LABELS_ZH = {
    "download.current": "下载当前完整正式版本",
    "download.masked": "下载脱敏数据",
    "version.history.view": "查看历史版本",
    "download.history": "下载历史版本",
    "analysis.online": "在线分析功能",
    "upload.candidate": "上传版本候选文件",
    "codebook.draft": "编辑 codebook 草稿",
    "code.maintain": "上传和维护处理代码",
}

# 数据集下载策略（七节 2）
DOWNLOAD_POLICIES = ["public", "member", "approval", "masked_only", "forbidden"]


class DatasetGrant(Base):
    """数据集管理员对成员的单独授权（到期自动失效）。"""
    __tablename__ = "dataset_grants"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    perm = Column(String(40))                 # GRANTABLE_PERMS 之一
    scope_type = Column(String(20), default="permanent")  # permanent|until_date|version|project
    valid_to = Column(DateTime)               # until_date 用
    scope_version = Column(String(40))        # version 用：仅对指定版本有效
    project_note = Column(String(200))        # project 用：仅用于指定研究项目
    granted_by = Column(Integer, ForeignKey("users.id"))
    granted_at = Column(DateTime, default=datetime.utcnow)
    revoked = Column(Boolean, default=False)

    def is_active(self, now: datetime | None = None) -> bool:
        if self.revoked:
            return False
        now = now or datetime.utcnow()
        if self.scope_type == "until_date" and self.valid_to and now > self.valid_to:
            return False
        return True


class DatasetSettings(Base):
    """数据集级开关：下载策略、历史版本可见性、是否关闭。每数据集一行（懒创建）。"""
    __tablename__ = "dataset_settings"
    dataset_id = Column(Integer, ForeignKey("datasets.id"), primary_key=True)
    download_policy = Column(String(20), default="member")   # DOWNLOAD_POLICIES
    history_visible = Column(Boolean, default=True)          # 成员默认可见历史版本信息
    history_downloadable = Column(Boolean, default=False)    # 成员默认可下载历史版本
    analysis_open = Column(Boolean, default=False)           # 在线分析是否对全体成员开放
    is_closed = Column(Boolean, default=False)               # 关闭：不再接受申请/勘误/发版
    codebook_public = Column(Boolean, default=True)          # 公开 codebook 是否非成员可见
    dashboard_public = Column(Boolean, default=True)         # 公开看板是否非成员可见


class DownloadRequest(Base):
    """下载申请（审批后下载）。七节 3。"""
    __tablename__ = "download_requests"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    purpose = Column(Text)                 # 研究用途
    scope_version = Column(String(40))     # 申请的数据版本
    planned_until = Column(String(40))     # 预计使用时间
    share_with_others = Column(Boolean, default=False)  # 是否与他人共享
    agree_charter = Column(Boolean, default=False)      # 是否同意数据使用公约
    status = Column(String(20), default="pending")      # pending|approved|rejected|revoked
    decided_by = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime)
    valid_to = Column(DateTime)            # 管理员批准时可设有效期
    created_at = Column(DateTime, default=datetime.utcnow)


class VersionCandidate(Base):
    """版本候选文件：获 upload.candidate 授权成员上传，管理员据此发布正式版。九节 1。"""
    __tablename__ = "version_candidates"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    file_path = Column(String(300)); file_name = Column(String(200))
    note = Column(Text)
    status = Column(String(20), default="pending")   # pending|published|discarded
    created_at = Column(DateTime, default=datetime.utcnow)


class CodebookDraft(Base):
    """codebook 草稿：获 codebook.draft 授权成员/管理员可编辑，发版时正式化。"""
    __tablename__ = "codebook_drafts"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    body_zh = Column(Text); body_en = Column(Text)
    updated_by = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime, default=datetime.utcnow)
