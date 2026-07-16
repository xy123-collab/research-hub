"""邮件通知 / @提及 / 历史下载 相关新表。

全部为新表（靠 create_all 启动自动补建，无需迁移旧表）。对应：
- 《邮件通知与每周周报功能需求文档》：notification_preferences / notification_events /
  email_deliveries / dataset_follows。
- @提及：mentions（被@的人进入新消息提示范围）。
- 历史下载：download_history（跨数据集与其它位置的统一下载留痕）。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime, JSON
from ..core.db import Base


# ========== 通知偏好（每用户一行，懒创建；缺省即默认值）==========
# 频率：immediate 立即 / daily 每日8:00汇总 / weekly 每周一8:00汇总 / off 关闭
NOTIFY_FREQUENCIES = ["immediate", "daily", "weekly"]
# 周报范围：public 全平台公开 / groups 我的课题组 / datasets 我加入的数据集
DIGEST_SCOPES = ["public", "groups", "datasets"]


class NotificationPreference(Base):
    """用户邮件订阅细分设置。email_enabled 为总开关（与找回密码隔离）。"""
    __tablename__ = "notification_preferences"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    email_enabled = Column(Boolean, default=True)          # 总开关（找回密码不受其约束）
    # 数据版本更新
    version_email_enabled = Column(Boolean, default=True)
    version_email_frequency = Column(String(20), default="immediate")
    # 处理代码更新
    code_email_enabled = Column(Boolean, default=True)
    code_email_frequency = Column(String(20), default="immediate")
    # 消息通知（被回复/被@/权限申请/自己权限通过等；每日8:00与18:00巡检）
    message_email_enabled = Column(Boolean, default=True)
    # 每周帖子周报
    weekly_digest_enabled = Column(Boolean, default=True)
    weekly_digest_scope = Column(JSON, default=lambda: ["public", "groups", "datasets"])
    # 通用
    email_language = Column(String(10), default="zh-CN")   # zh-CN | en
    timezone = Column(String(40), default="Asia/Shanghai")
    updated_at = Column(DateTime, default=datetime.utcnow)


# ========== 通知事件（一次“发生的事”，由它派生若干投递记录）==========
class NotificationEvent(Base):
    __tablename__ = "notification_events"
    id = Column(Integer, primary_key=True)
    # dataset_version_published | dataset_code_published | weekly_digest | message_digest
    event_type = Column(String(40))
    object_type = Column(String(40))     # dataset_version | code_version | digest_period
    object_id = Column(String(60))       # 关联版本/周期标识
    created_by = Column(Integer, ForeignKey("users.id"))   # 定时任务可空
    payload = Column(JSON, default=dict)                    # 渲染邮件所需结构化数据
    created_at = Column(DateTime, default=datetime.utcnow)


# ========== 邮件投递记录（去重 + 可重试 + 留痕）==========
class EmailDelivery(Base):
    __tablename__ = "email_deliveries"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("notification_events.id"))
    recipient_user_id = Column(Integer, ForeignKey("users.id"))
    recipient_email = Column(String(200))       # 发送时邮箱快照
    template_key = Column(String(60))
    status = Column(String(20), default="pending")   # pending|sending|sent|failed|skipped
    scheduled_at = Column(DateTime)             # 计划发送（daily/weekly 汇总用）
    sent_at = Column(DateTime)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    dedupe_key = Column(String(200), unique=True)    # 同用户+同对象+同类型 唯一
    subject = Column(String(300))
    body = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# ========== 数据集关注（可单独控制是否接收版本通知）==========
class DatasetFollow(Base):
    __tablename__ = "dataset_follows"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    version_notification_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ========== @提及 ==========
# source：评论所在位置；target：被@的对象（单人/整个数据集/整个课题组）
MENTION_SOURCES = ["post_comment", "project_comment", "code_comment", "skill_comment"]
MENTION_TARGETS = ["user", "dataset", "group"]


class Mention(Base):
    __tablename__ = "mentions"
    id = Column(Integer, primary_key=True)
    source_type = Column(String(30))      # MENTION_SOURCES
    source_id = Column(Integer)           # 评论 id
    post_ref = Column(String(120))        # 前端跳转用的定位串（如 post=123 / dataset slug）
    target_type = Column(String(20))      # user | dataset | group
    target_id = Column(Integer)           # 被@的用户/数据集/课题组 id
    mentioned_by = Column(Integer, ForeignKey("users.id"))
    snippet = Column(String(300))         # 评论摘要，用于通知展示
    created_at = Column(DateTime, default=datetime.utcnow)


# ========== 历史下载（跨数据集 + 其它位置统一留痕）==========
# source：dataset_version | code | bug_attachment | skill | post_attachment
class DownloadHistory(Base):
    __tablename__ = "download_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    source = Column(String(30))
    dataset_id = Column(Integer, ForeignKey("datasets.id"))   # 可空（非数据集来源）
    location_label = Column(String(200))     # 展示：数据集名/“处理代码”/“Skill”等
    detail = Column(String(200))             # 版本号/文件类型等补充
    file_name = Column(String(200))
    link = Column(String(200))               # 前端可跳转的定位
    downloaded_at = Column(DateTime, default=datetime.utcnow)
