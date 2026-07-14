"""版本级「对照表(取值字典)」文件 + codebook/对照表 轻量勘误。

两张都是新表，靠 create_all 自动建，无需迁移旧表。

- VersionAuxFile：某版本除 data/codebook 之外的附加可下载文件。
  当前 kind 只用 "mapping"（对照表/取值字典：数字编码 ↔ 中文/文字 的映射，
  如城市列表、职位列表）。留 kind 字段方便以后扩别的类型。
- FileCorrection：对 codebook 或对照表的勘误报错。逻辑刻意做简单——
  不记录历史版本迭代，直接发给数据集管理员看，管理员确认采纳或驳回
  （与原始数据勘误一样的采纳/驳回动作）。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime
from ..core.db import Base


AUX_KINDS = ["mapping"]                 # 对照表/取值字典
CORRECTION_TARGETS = ["codebook", "mapping"]
FILE_CORRECTION_STATUS = ["pending", "accepted", "rejected"]


class VersionAuxFile(Base):
    """版本的附加下载文件（对照表/取值字典）。与 codebook 并列，跟着版本走。"""
    __tablename__ = "version_aux_files"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("data_versions.id"))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    kind = Column(String(20), default="mapping")   # AUX_KINDS
    filename = Column(String(200))
    file_path = Column(String(300))                # 存储 key（下载用）
    note_zh = Column(String(300))                  # 简短说明，如「城市编码对照」
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class FileCorrection(Base):
    """codebook / 对照表 的勘误报错。简单流转：提交 → 管理员采纳/驳回。"""
    __tablename__ = "file_corrections"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    version_id = Column(Integer, ForeignKey("data_versions.id"))  # 可空：针对某版本文件
    target = Column(String(20))                    # CORRECTION_TARGETS
    content = Column(Text)                          # 勘误内容/说明
    reporter_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(20), default="pending") # FILE_CORRECTION_STATUS
    decided_by = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
