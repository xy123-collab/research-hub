from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime
from ..core.db import Base


class DataVersion(Base):
    __tablename__ = "data_versions"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    version_id = Column(String(40))   # (dataset_id, version_id) 唯一; e.g. v1.3.0
    based_on_version = Column(String(40))
    release_date = Column(DateTime)
    data_file_path = Column(String(300))      # 独立文件，不可覆盖
    codebook_file_path = Column(String(300))
    changelog_zh = Column(Text); changelog_en = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    is_current = Column(Boolean, default=False)
    valid_from = Column(DateTime); valid_to = Column(DateTime)


class DownloadLog(Base):
    __tablename__ = "download_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    version_id = Column(Integer, ForeignKey("data_versions.id"))
    file_type = Column(String(20))   # data | codebook
    file_name = Column(String(200))
    downloaded_at = Column(DateTime)
    user_ip = Column(String(60))
