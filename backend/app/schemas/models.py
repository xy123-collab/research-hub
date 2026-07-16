"""业务 I/O schema（精简，够用即可）。"""
from pydantic import BaseModel, field_validator
from .common import ORMModel, validate_http_url


# -------- group --------
class GroupIn(BaseModel):
    slug: str; name_zh: str; name_en: str | None = None
    desc_zh: str | None = None; desc_en: str | None = None
    icon: str | None = None; discoverable: bool = True


class GroupOut(ORMModel):
    id: int; slug: str; name_zh: str; name_en: str | None = None
    desc_zh: str | None = None; desc_en: str | None = None
    icon: str | None = None; discoverable: bool = True


# -------- dataset --------
class DatasetIn(BaseModel):
    slug: str; name_zh: str; name_en: str | None = None
    desc_zh: str | None = None; desc_en: str | None = None
    icon: str | None = None
    # 联系方式不再手填：数据集「负责人」及邮箱一律取当前总管理员的注册邮箱（自动、随转让更新）。
    # 字段保留为可选，兼容历史调用。
    founder_contact: str | None = None
    is_sensitive: bool = False


class DatasetOut(ORMModel):
    id: int; group_id: int; slug: str; name_zh: str; name_en: str | None = None
    desc_zh: str | None = None; icon: str | None = None
    founder_id: int | None = None; founder_contact: str | None = None
    current_version_id: int | None = None; is_sensitive: bool = False


# -------- version --------
class VersionIn(BaseModel):
    version_id: str; based_on_version: str | None = None
    changelog_zh: str | None = None; changelog_en: str | None = None


# -------- charter --------
class CharterIn(BaseModel):
    body_zh: str; body_en: str | None = None


# -------- bug --------
class BugIn(BaseModel):
    officer_id: str | None = None; term_id: str | None = None
    variable_id: int | None = None
    current_value: str | None = None; suggested_value: str | None = None
    bug_type: str | None = None
    description_zh: str; description_en: str | None = None; evidence: str | None = None


class ReviewIn(BaseModel):
    acceptability_score: float; comment: str | None = None

    @field_validator("acceptability_score")
    @classmethod
    def _r(cls, v):
        if not 0 <= v <= 10:
            raise ValueError("评分需在 0-10 之间")
        return v


class FinalizeIn(BaseModel):
    adopt_level: str  # full|partial|reject
    final_score: float; comment: str | None = None

    @field_validator("final_score")
    @classmethod
    def _f(cls, v):
        if not 0 <= v <= 10:
            raise ValueError("最终分需在 0-10 之间")
        return v


# -------- code --------
class CodeIn(BaseModel):
    filename: str; lang: str; title_zh: str; title_en: str | None = None
    desc_zh: str | None = None; source_code: str


class CodeBugIn(BaseModel):
    line_ref: str | None = None; description_zh: str
    description_en: str | None = None; suggested_patch: str | None = None


# -------- post / project --------
class PostIn(BaseModel):
    content_zh: str; content_en: str | None = None
    title: str | None = None
    post_type: str = "discussion"         # question|data|method|collab|discussion
    status: str | None = None             # open|resolved|closed
    dataset_id: int | None = None; group_id: int | None = None
    visibility: str = "platform"; cover_icon: str | None = None
    tags: list[str] = []
    scope: str = "public"                 # public|group|dataset|self
    scope_ref_id: int | None = None       # 兼容旧单选
    scope_ref_ids: list[int] = []         # 多选：选中的课题组/数据集 id 列表


class MentionIn(BaseModel):
    target_type: str               # user | dataset | group
    target_id: int


class CommentIn(BaseModel):
    content: str
    parent_id: int | None = None   # 评论的评论
    mentions: list[MentionIn] = []  # @提及（前端结构化传入，后端按范围校验）


class ProjectIn(BaseModel):
    title: str; body_zh: str | None = None; body_en: str | None = None
    dataset_id: int | None = None; status: str | None = None
    open_for_discussion: bool = True; visibility: str = "platform"
    labels: list[str] | None = None    # 项目标签（欢迎讨论/欢迎合作/…，可自定义）
    scope: str | None = None           # 可见范围：public|group|dataset|self
    scope_ref_ids: list[int] | None = None   # group/dataset 时选中的组/集 id


# -------- workspace --------
class WorkspaceIn(BaseModel):
    title: str; overleaf_url: str | None = None
    member_ids: list[int] = []

    @field_validator("overleaf_url")
    @classmethod
    def _u(cls, v):
        return validate_http_url(v)


class WsUpdateIn(BaseModel):
    body: str


class WsTodoIn(BaseModel):
    text: str; assignee_id: int | None = None


class WsTodoPatch(BaseModel):
    text: str | None = None; done: bool | None = None; assignee_id: int | None = None


class WsNoteIn(BaseModel):
    body: str


# -------- skill --------
class SkillIn(BaseModel):
    name_zh: str; name_en: str | None = None; desc_zh: str | None = None
    group_id: int | None = None; github_url: str | None = None

    @field_validator("github_url")
    @classmethod
    def _g(cls, v):
        return validate_http_url(v)


# -------- resume --------
class ResumeBlockIn(BaseModel):
    type: str; text_zh: str | None = None; text_en: str | None = None; seq: int = 0


# -------- literature --------
class LitRefIn(BaseModel):
    title: str; authors: str | None = None; venue: str | None = None
    year: int | None = None; url: str | None = None; doi: str | None = None
    note_zh: str | None = None
    confirm_real: bool = False   # 用户确认为真实文献（覆盖 AI 判定强制上传）


class CitationTextIn(BaseModel):
    text: str


class AiSummaryIn(BaseModel):
    prompt: str = ""     # 用户自定义提示词，基于现有文献标题做定制化综述


class AiHintIn(BaseModel):
    prompt: str = ""     # 人工追加的方向提示词
    mode: str = "check"  # check=提示可能有问题的方面 / patterns=从历史勘误总结规律


class LitRefRow(BaseModel):
    title: str | None = None; authors: str | None = None; venue: str | None = None
    year: int | None = None; doi: str | None = None; url: str | None = None
    confirm_real: bool = False   # 用户确认为真实文献（覆盖 AI 判定强制上传）


class LitBatchIn(BaseModel):
    refs: list[LitRefRow]
