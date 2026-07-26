"""时间边界：数据库继续存 naive UTC，API 展示值必须带明确时区。"""
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def as_utc(value: datetime) -> datetime:
    """历史库里的 naive datetime 按 UTC 解释；aware datetime 正常换算。"""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def china_iso(value: datetime | None, *, timespec: str = "minutes") -> str | None:
    """输出带 +08:00 的 ISO 时间，防止前端把北京时间误当 UTC 二次换算。"""
    if value is None:
        return None
    return as_utc(value).astimezone(CHINA_TZ).isoformat(timespec=timespec)
