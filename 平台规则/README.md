# 平台底层规则文档

> 本目录每个文件描述**一项**平台底层规则，**严格按代码实际实现**书写（标注了对应的
> 后端文件/函数/枚举值），不是需求或预期。改代码后请同步更新对应文件。

| 文件 | 规则 | 核心代码 |
|---|---|---|
| `00-总览与分区关系.md` | 五大分区（数据集/课题组/研究讨论区/其他协作/管理后台）+ 个人主页/工作台如何组织与跳转 | `frontend/router`、`App.vue` |
| `01-权限规则.md` | 六类角色、两级管理员、四条原则、八项可授权限、授权/转让/增删管理员按钮位置与约束 | `core/permissions.py`、`models/access.py` |
| `02-数据集使用规则.md` | 数据集从创建到关闭的完整使用逻辑、九个页签、成员与加入审批 | `api/datasets.py` |
| `03-版本与数据分类规则.md` | 版本不可覆盖、原始/脱敏/样例三分类、当前版竞争、脱敏、应用勘误、变量自动抽取、codebook/对照表 | `api/datasets.py`、`services/data_ops.py`、`services/introspect.py` |
| `04-下载分级规则.md` | 五种下载策略、样例公开、历史版本、codebook/对照表、单独授权到期、下载申请审批、留痕、历史下载 | `api/datasets.py`(`check_download`)、`services/downloads.py` |
| `05-勘误规则.md` | 三类勘误（原始数据/文件codebook·对照表/处理代码）各自的流转与自审规则 | `api/bugs.py`、`api/datasets.py`、`api/code.py` |
| `06-可见范围规则.md` | 四类可见范围、多选、发帖/项目/skill 共用 | `core/scopes.py` |
| `07-消息中心与邮件提醒规则.md` | 消息分类与红点、轮询、通知偏好细分、版本/代码更新邮件、每周周报、去重/重试/退订、被@通知 | `api/notifications.py`、`api/notify_prefs.py`、`services/notify.py`、`services/weekly_digest.py`、`services/digest.py` |
| `08-账号与安全规则.md` | 注册/登录/令牌、找回密码、邮件后端、资料 | `api/auth.py`、`core/security.py`、`core/email_service.py` |
| `09-在线分析与沙箱规则.md` | 沙箱只读接真实数据、行数上限、禁写禁网、AI 仅送元数据 | `services/sandbox.py`、`api/datasets.py` |
| `10-名称与文献去重规则.md` | 哪些名称必须唯一、文献同集四项判重 | `core/naming.py`、`api/datasets.py` |
| `11-研究讨论区规则.md` | 统一帖子系统、可见范围、评论回复点赞、未读计数 | `api/posts.py`、`components/PostCard.vue` |
| `12-贡献度规则.md` | 各类行为计分、本人看明细他人看汇总 | `services/scoring.py`、`core/audit.py` |
| `13-@提及与历史下载规则.md` | 所有评论处@数据集/课题组及成员（关键词检索、按权限校验、被@进新消息）、跨位置历史下载统一留痕与双入口 | `services/mentions.py`、`services/downloads.py`、`components/MentionInput.vue` |
| `14-删除与账号注销规则.md` | 公共研究成果的删除边界、二次确认、管理责任交接、账号匿名化与可选删帖 | `api/users.py`、`services/content_deletion.py`、`api/groups.py`、`api/datasets.py`、`api/code.py`、`api/skills.py` |
