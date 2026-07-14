"""名称去重规则（#1）——集中在一处，前后端一致。

规则总览（哪些"名称"提交前必须自动检索、不允许重复；哪些可以重复）：

  必须唯一（创建/重命名时拦截，大小写与首尾空格不敏感）：
    - 账号用户名 username         —— 登录标识，全局唯一
    - 注册邮箱 email             —— 找回密码等靠它，全局唯一
    - 数据集机器名 slug          —— URL 标识，全局唯一
    - 数据集名称 name_zh         —— 全局唯一（避免检索/引用歧义）
    - 课题组机器名 slug          —— URL 标识，全局唯一
    - 课题组名称 name_zh         —— 全局唯一
    - 同一数据集内版本号 version_id
    - 同一数据集内变量名 var_name（由 .dta 抽取，天然唯一）

  允许重复（不拦截）：
    - 用户显示名 display_name    —— 同名同姓正常，用户名/ID 才是唯一键
    - 文献显示名 / 标题 title    —— 不同数据集常引同一篇，允许重复
    - 帖子标题、评论、工作台条目、公约、changelog 等自由文本
    - 处理代码 / skill 的标题     —— 版本化资源，靠 ID 区分，允许重名

比较口径：`normalize_name` 去首尾空格、把连续空白压成一个、casefold 小写化。
存储仍保留用户原样输入，只在"判重"时归一化。
"""


def normalize_name(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(str(s).split()).casefold()


def ensure_unique(db, model, field: str, value: str, label: str,
                  exclude_id=None, extra_filter: dict | None = None):
    """判重：库里已存在同名（归一化后相等）则抛 400。

    - model/field：要判重的表与列（如 Dataset, "name_zh"）。
    - label：报错里显示的中文名（如 "数据集名称"）。
    - exclude_id：重命名时排除自己（按主键 id）。
    - extra_filter：附加过滤（如软删除 is_deleted=False，或限定 dataset_id）。
    """
    from fastapi import HTTPException
    norm = normalize_name(value)
    if not norm:
        raise HTTPException(400, f"{label}不能为空")
    q = db.query(model)
    if extra_filter:
        q = q.filter_by(**extra_filter)
    for row in q.all():
        if exclude_id is not None and getattr(row, "id", None) == exclude_id:
            continue
        if normalize_name(getattr(row, field, None)) == norm:
            raise HTTPException(400, f"{label}「{value}」已存在，请换一个（名称不可重复）")
