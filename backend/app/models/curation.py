"""本轮新增表（均为新表，靠 create_all 自动建，无需迁移旧表）。

覆盖：版本数据分类(原始/脱敏/样例)、唯一ID与脱敏规则、勘误实际修改项、
处理代码版本/授权/评论。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, Float, DateTime
from ..core.db import Base


# ---------- 版本数据分类 ----------
DATA_KINDS = ["raw", "masked", "sample"]   # 原始 / 脱敏 / 样例
MASK_ACTIONS = ["keep", "drop", "hash", "bucket"]  # 保留/删除/哈希/分桶


class VersionExtra(Base):
    """DataVersion 的附加信息：数据分类等。每个版本一行（发版时创建）。"""
    __tablename__ = "version_extra"
    version_id = Column(Integer, ForeignKey("data_versions.id"), primary_key=True)
    data_kind = Column(String(10), default="raw")       # raw|masked|sample
    masked_source_version = Column(String(40))          # 脱敏版来自哪个原始版本号
    generated = Column(String(10))                      # 空 | server | script（脱敏/改数来源）


class DatasetDataConfig(Base):
    """数据集级数据处理配置：唯一ID变量、是否仅脚本模式。每数据集一行（懒创建）。"""
    __tablename__ = "dataset_data_config"
    dataset_id = Column(Integer, ForeignKey("datasets.id"), primary_key=True)
    unique_id_var = Column(String(80))     # 上传数据时强制选择的唯一标识变量，如 officerID
    script_only = Column(Boolean, default=False)   # 数据过大/管理员选择：只生成脚本不在服务器改


class VariableMaskRule(Base):
    """脱敏规则：某数据集某变量在生成脱敏版时的动作。"""
    __tablename__ = "variable_mask_rules"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    var_name = Column(String(80))
    mask_action = Column(String(10), default="keep")   # MASK_ACTIONS
    bucket_size = Column(Integer)   # bucket 时的分桶宽度（数值型）


# ---------- 批量勘误子项 ----------
class BugItem(Base):
    """一个实际修改项。新批量导入的每一行各自生成一条 Bug + 一个 BugItem；
    历史批量数据仍可能是一条 Bug 含多个子项。"""
    __tablename__ = "bug_items"
    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey("bugs.id"))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    seq = Column(Integer, default=1)
    uid_var = Column(String(80))       # 本条勘误实际使用的 ID 变量；空值兼容旧记录（取管理员推荐 ID）
    uid_value = Column(String(200))     # 唯一ID的取值，如 officerID=O123
    var_name = Column(String(80))       # 要改的变量
    current_value = Column(String(300))
    suggested_value = Column(String(300))
    reason = Column(Text)               # 修改说明
    evidence = Column(Text)             # 证据来源/链接/出处
    is_new_officer = Column(Boolean, default=False)  # 最新原始版中没有该唯一 ID
    status = Column(String(20), default="pending")   # pending|accepted|rejected|fixed
    ai_score = Column(Float)
    final_score = Column(Float)
    adopt_level = Column(String(20))    # full|partial|reject
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)
    applied_in_version = Column(Integer, ForeignKey("data_versions.id"))
    # 管理员选择“部分采纳”时先保留下列原始投稿，再把上方字段改成终审后的实际内容。
    original_uid_value = Column(String(200))
    original_var_name = Column(String(80))
    original_current_value = Column(String(300))
    original_suggested_value = Column(String(300))
    original_reason = Column(Text)
    admin_edited_by = Column(Integer, ForeignKey("users.id"))
    admin_edited_at = Column(DateTime)


# ---------- 处理代码：版本 / 授权 / 评论 ----------
class CodeVersion(Base):
    """处理代码的版本迭代。发布新版本需写清修改内容(changelog)。"""
    __tablename__ = "code_versions"
    id = Column(Integer, primary_key=True)
    script_id = Column(Integer, ForeignKey("code_scripts.id"))
    version_label = Column(String(40))
    filename = Column(String(200))
    file_path = Column(String(300))     # 存储 key（下载用）
    source_code = Column(Text)          # 文本副本（预览用）
    changelog = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_current = Column(Boolean, default=False)


class CodeGrant(Base):
    """代码作者授予其他成员的权限：修改 / 重新发布。"""
    __tablename__ = "code_grants"
    id = Column(Integer, primary_key=True)
    script_id = Column(Integer, ForeignKey("code_scripts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    can_edit = Column(Boolean, default=False)
    can_publish = Column(Boolean, default=False)
    granted_by = Column(Integer, ForeignKey("users.id"))


class CodeComment(Base):
    """代码评论；可标记为「勘误类评论」(指出代码问题)。"""
    __tablename__ = "code_comments"
    id = Column(Integer, primary_key=True)
    script_id = Column(Integer, ForeignKey("code_scripts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    is_correction = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
