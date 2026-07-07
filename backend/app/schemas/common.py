from pydantic import BaseModel, ConfigDict, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def validate_http_url(v: str | None):
    if v in (None, ""):
        return v
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ValueError("URL 必须以 http:// 或 https:// 开头")
    return v
