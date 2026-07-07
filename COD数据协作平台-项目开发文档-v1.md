# 组内科研数据协作平台 · 项目开发文档（产品设计 + 技术实现）

> 版本：v5.0（在 v4 多课题组平台基础上增补：数据核验专栏与自动化实现、版本号与下载分级、项目工作台、Skill 共享、个人简历、总管理员隐私边界、平台品牌页脚）｜日期：2026-07｜状态：待确认后交接执行

> **v5 相对 v4 的增补（最近一轮反馈）**：
> - 公约改为**进入对应课题组/数据集页面时**弹出确认（非登录/首页）。
> - 版本**下载分级**：成员下当前版、管理员下全部历史；补**版本号规则表**。
> - 每个数据集加"**代码规则 + AI 数据核验**"专栏；写清**核验底层实现**——检测全自动、AI 只发现与起草、**绝不静默改原始数据**、采纳走评分制勘误管线、人工只剩"发版时一次批量确认"。
> - 处理代码"**一键生成数据处理说明**"（写作规范草稿）。
> - 个人主页"在做的项目"加**私密项目工作台**（进展/讨论/待办/Overleaf 跳转，可见成员自选）。
> - 新增"**科研 Skill 共享**"栏目（与数据集同构：发起/权限/协作优化/GitHub 链接；计入贡献）。
> - 个人主页可进入并编辑**个人简历**（模板/空白 + 基础排版）。
> - **总管理员改为平台维护者**：隐私隔离，不看课题组/数据内部内容与贡献，不单方面删数据（软删除+留痕）。
> - 首页/注册页加**平台名 + slogan + 北大国发院智慧科研团队**页脚。
> 定位：整合《痛点分析 v0.2》《COD 核心需求说明 v1.0》《研究平台建设方案 v3》，并按用户反馈把平台升级为**面向多个课题组的开放科研数据共享平台**。平台名"**科研数据共享平台 / Research Hub**"；"**NSD 发展政经课题组**"是平台上的首个课题组，COD 是其首个数据集，核心识别变量 `officerID`、`termID`。

> **v4 相对 v3 的重大变化（本轮反馈落地）**：
> 1. **多课题组平台**：课题组（research group）成为顶层实体，平台可容纳多个课题组。新用户注册后是"空白视角"——只有栏目，可在研究广场/我的主页维护（对全平台可见）；可**创建课题组**或**申请加入课题组**（课题组管理员同意）。一个人可加入多个课题组，并选择是否在主页显示某课题组标签。
> 2. **三级权限 + 角色在创建时产生、可交接**：**总管理员（全站，可多个）→ 课题组管理员 → 数据集管理员/发起人**。**身份不在登录时选择**——登录即"你本人"，持有哪些角色由"创建课题组/数据集"时产生，且可交接赋予。
> 3. **发帖可见性三级**：全平台可见 / 本课题组可见 / 仅自己。
> 4. **公约（charter）**：每个课题组、每个数据集都有公约显示栏；新注册/新打开自动弹出公约提示需确认；对应级别管理员可编辑（如"禁止外传数据""学术讨论禁止截图公开发表"）。
> 5. **数据集非成员权限**：未申请加入某数据集处理的用户，可看 codebook、用数据看板，但**不能下载原始数据**。
> 6. **数据发起人信息**：每个数据集顶部显示发起人 ID（自动 link 到其平台主页）+ 联系方式（发起人必填）。
> 7. **评分制审核**：原始数据勘误与处理代码勘误均可由**成员参与评审 + AI 自动评审**，各打 0–10 可采纳度分；**管理员终审**决定是否采纳、采纳程度并给最终分；贡献度按终审分加权。
> 8. **贡献展示**：我的主页蓝色 banner 只显示"贡献度"；"我的贡献"页展开明细（发起人分、勘误分按终审加权、审核被采纳分、代码发起/勘误/被采纳分等）。管理后台的全员贡献分**全员总贡献度**与**分数据集贡献度**两块；课题组管理后台内容只在管理后台出现（不在首页/广场/主页下方）。
> 9. **发起入口**：首页可创建/加入课题组；课题组页可"发起新数据集"。

> **v3 相对 v2 的新增（本轮反馈落地）**：
> 1. **数据集社区化**：每个数据集详情增加"近期刊物""近期研究想法（本数据集）""文献思维导图 + 重点文献清单"；发帖加数据集标签即进入对应数据集的近期想法。
> 2. **分级权限**：区分**总管理员（全站，可多个）**与**数据集发起人（单数据集内最大权限）**；发起人可给成员授权（最高可至与自己一致）；加入某数据集处理需发起人/总管理员**审批**，审批记录（谁、何时同意）在数据集内展示；首页数据集卡片显示**成员数**。
> 3. **数据看板增强**：支持**手写代码 / AI 自动生成分析代码**做描述性分析，**只读、绝不修改原始值**。
> 4. **个人主页增强**：新增"**在做的项目 · 欢迎讨论**"，可含图/附件/标签，像帖子一样发出并单独列在项目区。
> 5. **自动化与部署策略**（新增第十三章）：哪些功能可自动化、付费 API vs 本地模型的取舍、数据安全边界、校内本地部署技术方案。

---

## 〇、本次重构要点（相对 v1）

用户明确了更大的目标：**不只做一个数据库的协作平台，而是做组内共享科研平台**。核心仍是数据协作，但外延扩展为：

1. **多数据集**：平台承载多个共享数据库（COD、地级市财政、政商网络、文本语料…），首页是**数据集入口墙**，不是单一 COD 首页。
2. **不只数据，还有社区**：像小红书一样的**个人主页** + **发帖交流学术想法**（"研究广场"），首页同时是**近期发帖入口**。
3. **单数据集的勘误分两类**：(a) **原始数据错误核对**；(b) **数据处理代码勘误**——后者需要一个**公共处理代码展示页面**。
4. **单数据集的数据看板**：提供更详细的入口，可做**描述性分析**，且**可自定义选择描述维度**。
5. **管理端可见全员贡献**：管理后台新增**全员贡献总览**（排行 + 明细），作为署名/推荐信/名额分配依据。

以下章节已按此重构。

---

## 一、产品愿景与设计原则

### 1.1 一句话价值
把课题组分散的、私有黑箱的、被反复重建的多份自建数据，变成一批**可审计、可溯源、有质量保证、贡献可归属可兑换**的共享研究资产；并在其上长出一个低成本的**学术交流社区**，让"谁在围绕这些数据想什么"被沉淀下来。

### 1.2 三个产品面（决定信息架构）
- **数据面（核心）**：多数据集的版本、下载、勘误、代码、看板。
- **社区面**：研究广场（发帖/想法流）+ 小红书式个人主页。
- **治理面**：权限与审计、全员贡献总览、质量巡检。

### 1.3 分层协作模型（设计基石）

| 层 | 内容 | 协作形态 | 平台目标 |
|---|---|---|---|
| 基础设施层 | 多份核心数据、清洗/链接流程、方法与代码 | 尽量网状、开放共享 | 把固定成本从"每人付 N 遍"摊薄成"全组付一遍" |
| 产出层 | 论文、想法、发帖、署名 | 个体化，灵活组队 | 保护"可归属到个人的独立贡献" |

两层由**贡献归属与兑换**连接。

### 1.4 设计原则（选型与取舍准绳）
- **分层原则**：基础设施层最大共享，产出层保护个体。
- **正确性是承重的**：版本不可覆盖、更正必留痕、任意时点可复现。
- **代码即数据资产**：处理/清洗代码与原始数据同等重要，需公开、可复用、可勘误、可归属。
- **激励多通道、即时+延迟结合**：平台职责是提供"让稀缺资源按真实公共投入公平分配"的清晰记录（全员贡献总览就是这份记录的出口）。
- **协作要便宜且被奖励，而非强制**；**社区降低求助社交成本**。
- **抗人员流动 + 防数据流失**；**PI 做兜底而非中继**。

### 1.5 与飞书/Notion 的根本区别
科研没有"公司发放回报"的机制——回报是署名、致谢、推荐信、名额，平台必须自己记录、导师必须亲自认可。因此不可缺的是"贡献记录 → 多通道兑现"这条链，以及数据可信化，而非更花哨的聊天/看板。

---

## 二、模块地图（M1–M11，多数据集视角）

| 模块 | 名称 | 层 | 本次重构后的落点 |
|---|---|---|---|
| M1 | 数据质量巡检 | 基础设施 | 每个数据集独立规则；管理端手动/定时跑 |
| M2 | 数据溯源与更正 | 基础设施 | **原始数据勘误**轨道 + 版本时点可复现 |
| M3 | 关联数据统一管理 | 基础设施 | **升为一等公民：多数据集注册 + 首页入口墙**；跨集联查留二期 |
| M4 | 方法与代码库 | 基础设施 | **升级为公共处理代码库 + 代码勘误轨道**（本次重点） |
| M5 | 项目与研究进展 | 协作与知识 | **研究广场发帖 + 小红书式个人主页**（本次重点） |
| M6 | 发现与匹配 | 协作与知识 | AI 推送连接线索（远期），社区是其载体 |
| M7 | 数据处理的学术化导出 | 协作与知识 | 溯源+贡献 → 论文数据附录（远期） |
| **M8** | **贡献与激励系统** ★ | 激励与治理 | 贡献事件覆盖数据勘误/代码勘误/发帖/上传；**管理端全员贡献总览**（本次重点） |
| M9 | 个人即时收益工具 | 激励与治理 | 数据看板、"该 ID 是否已验证"等 |
| M10 | 数据资产安全与成员流转 | 激励与治理 | 成员状态 + 导出审计 |
| M11 | 权限与审计 | 激励与治理 | 从第一天在线；三级权限 + 总管理员隐私边界 |
| M12 | 数据核验专栏 | 基础设施 | 规则 + AI 检测→只发现/起草，采纳走评分管线，不静默改数据 |
| M13 | 科研 Skill 共享 | 协作与知识 | 与数据集同构：发起/权限/协作优化/GitHub；计入贡献 |

---

## 三、信息架构（重构后）

```
注册/登录（登录即"你本人"，不选身份；公约弹窗需确认）
└─ 首页 Home
   ├─ 我的课题组（我加入/创建的 group 卡片，显示成员数/数据集数/我的角色） + [＋创建课题组]
   ├─ 发现课题组（其他 group，可申请加入 → 课题组管理员审批）
   └─ 研究广场·近期（全平台可见的发帖流）
   │
   ├─▶ 课题组详情 Group（点某课题组进入）
   │   ├─ 公约栏（可查看全文；课题组管理员可编辑）
   │   ├─ 数据集网格（本组的多个数据集卡片） + [＋发起新数据集]
   │   ├─ 课题组成员（+ 申请加入审批由课题组管理员处理）
   │   └─ 本组近期研究想法
   │
   ├─▶ 数据集详情 Dataset（点某数据集进入）
   │   ├─ 顶部：数据发起人 ID(link 到主页) + 联系方式(必填) · 数据集公约栏
   │   ├─ 非成员：可看 codebook / 数据看板，不能下载原始数据（[申请加入处理]）
   │   ├─ 概览：当前版本/下载(成员才可下载) · 成员+加入审批记录 · 近期刊物 · 近期研究想法(本数据集)
   │   ├─ 数据看板：① 样本描述性统计(勾选多个变量→N/均值/标准差/分位) ② 自定义维度分布图 ③ 手写/AI 描述分析(只读沙箱,不改原始值)
   │   ├─ 文献地图：研究话题思维导图 + 重点文献清单（AI 自动总结研究用途/话题；成员可上传修改，编辑与完整显示需权限）
   │   ├─ 版本库：历史版本、changelog、不可覆盖、（发起人/数据集管理员）发布新版本
   │   ├─ 原始数据勘误：提交 → 成员评审+AI评审(各0–10分) → 管理员终审(采纳程度+最终分)（M2）
   │   ├─ 处理代码库：公共代码展示 + 代码预览 + 代码勘误队列(同评分制审核)（M4）
   │   └─ 数据集后台（仅数据集管理员）：加入审批 / 成员授权 / 勘误终审 / 本数据集贡献度 / 公约编辑
   │
   ├─▶ 研究广场 Feed：发帖、想法流、点赞/评论/收藏/标签/关联数据集；**可见性三级(全平台/本课题组/仅自己)**（带数据集标签→进入该数据集近期想法）
   ├─▶ 我的主页 Profile（小红书式）：banner 只显示"贡献度" + 我的课题组(可勾选显示/隐藏) + [在做的项目·欢迎讨论 | 我的发帖 | 我的贡献(明细) | 我维护/发起的数据·代码]
   └─▶ 管理后台 Admin（**内容只在此出现**，按持有角色展示）：
        · 总管理员：全部课题组 / 总管理员管理(可多个·可交接) / 全站审计日志
        · 课题组管理员：加入课题组审批 / 公约编辑 / 全员总贡献度 + 分数据集贡献度
        · 数据集管理员：入口指向各数据集的"数据集后台"页签
```

顶部导航：**首页 · 研究广场 · 我的主页 · 管理后台(admin)**；右上角语言切换与用户。

---

## 四、分阶段路线图

> 排序：价值 + 不可替代性优先。本次用户决策：一期做广、覆盖 M1–M11 大部分底座，社区与多数据集框架一期就要立起来；重逻辑（激励兑换、看板实时计算引擎、跨集联查、AI）留二期/远期。

### 一期 · 基础框架（约 1–2 个月）— 本文档重点
**做实的核心闭环 + 多数据集/社区框架 + 权限审计底座：**
- 登录/注册 + 全程审计日志（M11）；**三级 RBAC**（站点 super_admin / 课题组 group_admin / 数据集 founder-maintainer-member），角色创建时产生、可交接
- **多课题组**：`research_groups` 顶层表 + 首页"我的/发现课题组" + 创建/加入审批 + 课题组详情
- **多数据集**：`datasets`（归属课题组）+ 课题组内数据集网格 + 发起新数据集(founder_contact 必填) + 数据集详情框架
- **公约**：课题组/数据集公约 + 进入弹窗确认(`charter_acks`) + 对应级管理员编辑
- **发帖可见性三级**（全平台/本组/私密）；数据集**非成员**可看 codebook+看板、不能下载
- 每个数据集：版本库（`.dta`/codebook、不可覆盖、changelog）、下载日志、概览
- **两类勘误轨道 + 评分制审核**：原始数据勘误（M2）+ 处理代码库与代码勘误（M4）；均支持成员评分(0–10) + AI 评分 → 数据集管理员终审(采纳程度+最终分)，贡献按终审分加权
- **研究广场**发帖 + 想法流（点赞/评论/收藏/标签/关联数据集）+ **可见性三级(全平台/本组/私密)**（M5）
- **小红书式个人主页**：banner 只显示贡献度 + 我的课题组(可显隐) + 在做的项目/我的发帖/我的贡献明细/我维护发起的数据代码（M5）
- **数据集社区化**：近期刊物（人工 + 可选 Crossref 自动）、近期研究想法（发帖标签路由）、文献思维导图 + 重点文献清单（一期人工录入 + 预留 AI 总结）；数据集顶部发起人 ID(link) + 联系方式(必填)
- **三级权限 + 公约 + 加入审批**（本轮重点）：总管理员/课题组管理员/数据集发起人，角色创建时产生可交接；课题组与数据集公约 + 进入弹窗确认；加入课题组/数据集审批与记录展示；首页课题组成员数
- **数据看板**（M9）：① 样本描述性统计(勾选多变量→N/均值/标准差/分位) ② 自定义维度分布 ③ AI/手写描述分析(只读沙箱，不改原始值，一期先接一个 AI provider 做代码生成)
- **贡献展示**（M8）：全员总贡献度 + 分数据集贡献度（仅在管理后台），个人贡献明细；兑换逻辑留二期
- **数据质量巡检自动化**（M1）：一期即上定时自动巡检（1–2 条规则，见第十三章），不只手动
- 变量下拉（每数据集一套）；双语（zh/en）

**一期只建表/最小入口的钩子**：M8 积分与访问分级兑换、M3 跨集联查、M9 一键合并导出、M10 外部协作者降权、M6/M7、文献 AI 总结的完整生产化。

### 二期 · 服务与激励（约 3–6 个月）
- **数据看板完整自定义引擎**：任意变量 × 任意维度的实时描述性分析（分布、交叉表、分位数、时间趋势），后端计算 + 缓存 + 导出 CSV/PNG
- **AI 功能生产化**（经 AI 网关，元数据-only + 只读沙箱，见第十三章）：看板 AI 描述分析、文献研究用途/话题 AI 总结、发现匹配(M6 起步)
- R/Python 数据 API；跨数据集联合查询与导出（M3）
- **M8 完整体**：贡献度接多通道回报（访问分级、互惠积分、队列优先级、数据红利、CRediT 署名导出、给 PI 的决策支持），门槛先软后硬
- M1 定时自动巡检 + 错误队列；Datasette/Metabase 接入
- 代码库接 Gitea；更细粒度（数据集级/贡献分级）权限

### 远期 · 精细化与全生态（6 个月后）
- M6 AI 发现与匹配（在研究广场/勘误上主动推送连接线索）
- M7 数据处理的学术化导出（溯源+贡献 → 论文数据附录，CRediT）
- M10 完整资产安全与成员流转
- Overleaf 集成 / 校内自建实例；全自动化本地生态

---

## 五、数据库 Schema（一期，多数据集）

> SQLite 起步，PostgreSQL 兼容；均含 `created_at/updated_at`；`*_zh/*_en` 为双语字段。**核心变化：`datasets` 成为一等表，版本/勘误/变量/代码等均按 `dataset_id` 归属。**

### 5.0 课题组（顶层实体，本轮新增）
```sql
research_groups(
  id PK, slug UNIQUE, name_zh, name_en, icon, desc_zh, desc_en,
  discoverable BOOL,          -- 课题组管理员可关闭：关闭后不在"发现课题组"列出
  created_by FK→users, created_at
)
group_members(
  group_id FK, user_id FK,
  group_role,                 -- 'group_admin'|'member'（group_admin 可多个，可交接）
  show_on_profile BOOL,       -- 用户选择是否在主页显示该组标签
  status, joined_at, approved_by FK→users,
  PK(group_id,user_id)
)
group_join_requests( id PK, group_id FK, user_id FK, message, status, decided_by FK, decided_at, created_at )
-- 公约（课题组级 + 数据集级共用一张表，scope 区分）
charters(
  id PK, scope,               -- 'group'|'dataset'
  ref_id,                     -- group_id 或 dataset_id
  body_zh, body_en, version, updated_by FK, updated_at
)
charter_acks( id PK, user_id FK, charter_id FK, charter_version, acked_at )   -- 记录谁已同意哪版公约
```

### 5.1 数据集与用户权限（M3 + M11 底座）
```sql
datasets(
  id PK, group_id FK→research_groups,   -- 数据集归属某课题组（本轮新增）
  slug UNIQUE, name_zh, name_en, icon,
  desc_zh, desc_en, join_key,
  founder_id FK→users,                  -- 数据发起人（顶部展示，link 到其主页）
  founder_contact,                       -- 发起人联系方式（必填，NOT NULL）
  current_version_id FK,
  is_public BOOL, created_at
)
users(
  id PK, username UNIQUE, email, password_hash, display_name, avatar,
  bio_zh, bio_en,                        -- 小红书式个人主页
  role_id FK→roles, preferred_language,  -- 'zh'|'en'
  status,                                -- 'active'|'external'|'left'（M10 底座）
  created_at, updated_at
)
roles( id PK, code UNIQUE, name_zh, name_en )            -- 站点级：super_admin / member（super_admin 可多个）
permissions( id PK, code UNIQUE, desc_zh, desc_en )      -- bug.review / version.publish / code.review ...
role_permissions( role_id FK, permission_id FK )
audit_log( id PK, user_id FK, action, object_type, object_id, detail_json, ip, created_at )

-- 数据集级分级权限（本轮新增，见第六章权限模型）
dataset_members(
  dataset_id FK, user_id FK,
  ds_role,                               -- 'founder'|'maintainer'|'member'（数据集内角色）
  granted_perms_json,                    -- 该成员在此数据集被授予的权限码集合；founder 可授到与自己一致
  joined_at, approved_by FK→users,       -- 谁批准（审批记录来源）
  PK(dataset_id,user_id)
)
join_requests(
  id PK, dataset_id FK, user_id FK, message,
  status,                                -- 'pending'|'approved'|'rejected'
  decided_by FK→users, decided_at, created_at   -- 审批人+时间→数据集内"加入审批记录"
)
```
> **权限层次**：站点级 `super_admin`（全站最大权限，可多个，通常导师+核心维护者）；数据集级 `founder`（该数据集内最大权限，等价于站点超管但作用域限于本数据集）→ `maintainer` → `member`（按 `granted_perms_json` 分级）。判断顺序：super_admin 全通过 → 否则查 `dataset_members` 的 ds_role/granted_perms。

### 5.2 版本与下载（每数据集独立，M2）
```sql
data_versions(
  id PK, dataset_id FK, version_id,      -- (dataset_id, version_id) 唯一，如 'v1.3.0'
  based_on_version, release_date,
  data_file_path,                        -- 独立文件，不可覆盖
  codebook_file_path,
  changelog_zh, changelog_en, created_by FK,
  is_current BOOL, valid_from, valid_to  -- 时点可复现（M2）
)
download_logs( id PK, user_id FK, dataset_id FK, version_id FK, file_type, file_name, downloaded_at, user_ip )
```
**下载权限分级（本轮明确）**：
- 数据集**成员**：可下载**当前推荐版本**（`is_current`）的数据与 codebook。
- 数据集**管理员/发起人（及组内被授权的维护者）**：可下载**全部历史版本**。
- **非成员**：仅可下载/查看 codebook，不能下载任何原始数据（见 6.1）。

**版本号规则（底层约定）**：
| 版本类型 | 触发条件 | 版本号示例 |
|---|---|---|
| 常规小修 | 集中修复若干已采纳 bug | `v1.0.1`, `v1.0.2` |
| 紧急修复 | 严重错误影响核心变量或大范围样本 | `v1.0.1-hotfix` |
| 中等更新 | 新增变量、补充样本、更新 codebook | `v1.1.0` |
| 重大更新 | 数据结构重构、变量体系变化 | `v2.0.0` |

发版逻辑遵循语义化版本：`major.minor.patch`（+ 可选 `-hotfix`）。任何版本均不可覆盖旧文件；发版时关联本次修复的 accepted 勘误并自动标 `fixed`。

### 5.3 变量与原始数据勘误（M2）
```sql
variables( id PK, dataset_id FK, var_name, group_code, label_zh, label_en )   -- 每数据集一套
bugs(                                     -- 原始数据勘误
  id PK, dataset_id FK, reporter_id FK, related_version_id FK,
  officer_id, term_id, variable_id FK,
  current_value, suggested_value, bug_type,
  description_zh, description_en, evidence,
  status,                                 -- pending|accepted|rejected|fixed
  fixed_in_version_id FK, reviewed_by FK, reviewed_at,
  created_at, updated_at
)
bug_attachments( id PK, bug_id FK, file_path, file_name, mime, size, uploaded_by, uploaded_at )
```
**评分制审核（原始数据勘误 + 代码勘误共用，本轮新增）**：
```sql
correction_reviews(                       -- 成员评审 + AI 自动评审
  id PK, target_type,                     -- 'bug' | 'code_bug'
  target_id,
  reviewer_type,                          -- 'member' | 'ai'
  reviewer_id FK→users NULL,              -- ai 评审为空
  acceptability_score,                    -- 0–10 可采纳度
  comment, created_at
)
correction_finals(                        -- 管理员终审（唯一）
  id PK, target_type, target_id,
  decided_by FK→users,                    -- 数据集管理员/发起人
  adopt_level,                            -- 'full'全部采纳|'partial'部分采纳|'reject'不采纳
  final_score,                            -- 0–10，贡献度按此加权
  comment, decided_at
)
```
> 审核流程：任意成员可对一条勘误打 0–10 可采纳度分（`correction_reviews`, member）；系统触发 AI 自动评审也落一条（reviewer_type=ai）；数据集管理员看到成员分 + AI 分后**终审**（`correction_finals`），决定采纳程度与最终分。**贡献度按 `final_score` 加权**计入报告人（见 6.5）。

### 5.4 公共处理代码库 + 代码勘误（M4，本次重点）
```sql
code_scripts(                             -- 公共处理/清洗代码，公开展示
  id PK, dataset_id FK, filename, lang,   -- 'Stata'|'Python'|'R'
  title_zh, title_en, desc_zh, desc_en,
  source_code TEXT,                       -- 一期直接存文本用于展示；二期可接 Gitea
  author_id FK, reuse_count, created_at, updated_at
)
code_bugs(                                -- 数据处理代码勘误
  id PK, script_id FK, reporter_id FK,
  line_ref,                               -- 定位到行/片段，如 'L8'
  description_zh, description_en, suggested_patch,
  status,                                 -- pending|accepted|rejected|fixed
  fixed_in_version_id FK, reviewed_by FK, reviewed_at, created_at
)
```

### 5.5 研究广场与个人主页（M5，社区）
```sql
posts(                                    -- 研究广场发帖 / 想法（原 research_ideas 升级）
  id PK, author_id FK, dataset_id FK NULL,-- 可关联某数据集(带标签→进该数据集近期想法)
  group_id FK NULL,                       -- visibility=group 时指哪个课题组
  content_zh, content_en, cover_icon,
  visibility,                             -- 'platform'(全平台) | 'group'(本课题组) | 'private'(仅自己)
  created_at, updated_at
)
post_attachments( id PK, post_id FK, file_path, file_name, mime, size )
post_variables( post_id FK, variable_id FK )        -- 关联变量
post_tags( id PK, post_id FK, tag )
post_reactions( id PK, post_id FK, user_id FK, type )   -- like/favorite
post_comments( id PK, post_id FK, user_id FK, content, created_at )
post_admin_flags( post_id FK, is_recommended BOOL )
```

### 5.6 贡献台账与质量巡检（M8 + M1 底座）
```sql
contribution_events(                      -- 一切公共投入统一落账
  id PK, user_id FK, dataset_id FK NULL,
  event_type,   -- 'bug_accepted'|'code_bug_accepted'|'data_upload'|'code_add'|'post'|'correction'
  ref_type, ref_id, weight, created_at    -- weight 预留，一期可 =1
)
-- 管理端全员贡献总览 = 对 contribution_events 的聚合视图（按 user 汇总 + 排行）
quality_rules( id PK, dataset_id FK, code, name_zh, name_en, expr_or_desc, enabled BOOL )
quality_runs( id PK, rule_id FK, version_id FK, run_by FK, status, n_failed, detail_json, created_at )
-- 数据核验专栏（本轮新增）：AI/规则识别出的疑似问题
verify_flags(
  id PK, dataset_id FK, version_id FK,
  source,           -- 'rule'（确定性规则）| 'ai'（概率性）
  officer_id, term_id, variable_name,
  issue_desc, confidence,   -- rule 为 1.0；ai 为 0–1
  status,           -- 'open'|'confirmed'|'dismissed'|'drafted'（已生成勘误草稿）| 'fixed'
  drafted_bug_id FK→bugs NULL,   -- 一键生成的勘误草稿
  created_at
)
```

### 5.6.1 数据 / 代码核验的底层实现（本轮重点澄清：尽量不人工，且绝不静默改原始数据）
每个数据集有一个"**代码规则 + AI 数据核验**"专栏，检测**自动化**，但修复**永远走版本化勘误管线**，不静默改原始值（否则破坏 M2 溯源）。分两条通道：

- **① 确定性规则通道（rule）**：定时自动跑 `quality_rules`（ID 唯一性、`begin_yr≤end_yr`、复合键冲突、`region_code` 对照码表、分布突变…）。失败项写 `verify_flags(source='rule')`。对于**规则明确、修复唯一**的项，系统可**自动生成候选修正**并进入"待发布候选"，由数据集管理员在发版时**一键批量确认**（一次点击、全程留痕、可回滚）——这一步是唯一保留的人工，且是批量的、极轻量的，不是逐条手改。
- **② AI 概率通道（ai）**：AI 扫描疑似问题（如疑似编码错配、异常值、未标准化取值），写 `verify_flags(source='ai', confidence)`，**标为"疑似"，绝不自动改数据**。成员在使用中发现问题、或看到 AI 提示后**去核查确认**，一键把某个 flag **生成勘误草稿**（`bugs` 记录，预填 officerID/变量/当前值/建议值/证据来源=AI+规则），进入 6.3 的**评分制审核**（成员评分 + AI 评分 → 管理员终审）。被采纳者按终审分**计入贡献度**——这正是"看见 AI 提示 → 去检查 → 贡献勘误 → 得分"的闭环。

一句话：**检测全自动，采纳走管线，人工只剩"管理员发版时的一次批量确认"**；AI 只负责"发现与起草"，不负责"改数据"。**代码核验**同理：规则/AI 可标记脚本可疑逻辑（如 `tenure<=0` 误删跨年记录），生成**代码勘误草稿**进入同一评分制审核，不自动改代码。

### 5.7 数据看板 + AI/代码描述分析（M9）
一期预设看板从**派生汇总表**出图，不直接读 `.dta`：发布版本时后台脚本预生成 `dataset_summaries(dataset_id, version_id, var_name, group_key, bucket, value)` 长表，前端按 `(var, group)` 查询出条形图。二期升级为对全量数据的实时任意维度计算引擎。

**手写/AI 描述分析（只读，不改原始值）**：
```sql
analysis_snippets(
  id PK, dataset_id FK, user_id FK,
  prompt,                    -- 用户的自然语言分析需求（可空，手写模式）
  code, lang,                -- 生成/手写的分析代码（pandas/Stata/R）
  ai_generated BOOL, result_json, chart_path,
  created_at
)
```
执行安全约束（强制）：分析代码在**只读沙箱**中运行——数据以只读方式加载（`load_readonly(dataset, version)`），沙箱**无写权限/无网络**，禁止任何写回原表的操作；AI 只接收变量名/codebook/需求（**不接收原始敏感数据行**），生成代码后本地执行，结果可回传 AI 做自然语言解读时只传**聚合、非可识别**的汇总。详见第十三章。

### 5.8 文献地图 · 刊物 · 项目（社区扩展表）
```sql
-- 文献思维导图（研究话题）+ 重点文献
lit_topics( id PK, dataset_id FK, parent_id NULL, title_zh, title_en, ai_generated BOOL, updated_by FK, updated_at )
lit_refs( id PK, dataset_id FK, title, authors, venue, year, url, note_zh, note_en, added_by FK )
-- 数据集研究用途/话题的 AI 总结（可被成员编辑覆盖；编辑与完整显示需权限）
dataset_summary_ai( dataset_id FK PK, purpose_zh, purpose_en, topics_json, ai_model, edited_by FK, updated_at )

-- 近期刊物（可 Crossref/Scholar 自动追踪 + 人工补录）
publications( id PK, dataset_id FK NULL, title, venue, year, url, used_version, source, created_at )

-- 在做的项目（帖子的一种子类型；同时进入研究广场与个人主页项目区）
projects(
  id PK, author_id FK, dataset_id FK NULL,
  title, body_zh, body_en, cover_icon, status,   -- '进行中'|'找数据中'|'初步结果'...
  open_for_discussion BOOL, visibility, created_at, updated_at
)
project_attachments( id PK, project_id FK, file_path, file_name, mime, size )
project_tags( id PK, project_id FK, tag )
```
> 说明：`posts` 与 `projects` 共享附件/标签/评论的交互形态；`projects` 额外有 `status` 与"欢迎讨论"标记，并单独列在个人主页"在做的项目"。研究广场发帖带 `dataset_id`（数据集标签）时，即在该数据集"近期研究想法"中出现。

### 5.9 项目工作台（私密协作，本轮新增）
个人主页"在做的项目"分两层：**公开展示**（上面的 `projects`，用于交流/招募）+ **项目工作台**（仅选定协作者可见，用于共同推进）。
```sql
workspaces(
  id PK, owner_id FK, title, overleaf_url,   -- 可放 Overleaf 链接，点击跳转
  created_at, updated_at
)
workspace_members( workspace_id FK, user_id FK, PK )     -- 可见成员由创建者选定
workspace_updates( id PK, workspace_id FK, author_id FK, body, created_at )   -- 进展记录
workspace_todos( id PK, workspace_id FK, text, done BOOL, assignee_id FK NULL )  -- 待办
workspace_notes( id PK, workspace_id FK, author_id FK, body, created_at )     -- 讨论/结果存档
workspace_files( id PK, workspace_id FK, file_path, file_name, mime, size )
```
用途：共同做项目的人互相看进度、存讨论与结果、维护待办、外接 Overleaf 跳转；可见范围由创建者选定成员。

### 5.10 处理代码 → 数据处理说明（写作规范，M4→M7）
`code_scripts` 每条支持"一键生成数据处理说明"：AI 依据脚本逻辑（读入、构造、筛选、变量定义）生成符合论文"数据来源与处理/数据附录"写法的草稿（可复制到 Overleaf 或导出）。这是 M7 学术化导出在代码维度的即时出口。
```sql
code_writeups( id PK, script_id FK, body_zh, body_en, ai_model, generated_by FK, created_at )
```

### 5.11 科研 Skill 共享（本轮新增，与数据集同构）
科研技能包（清洗流程、计量方法、AI 提示词、复现脚手架…），**功能/权限与数据集一致**：可发起、有发起人与成员授权、可协作勘误优化、可推荐并链接 GitHub。**创建与优化计入贡献度**（`contribution_events` 增 `skill_create`/`skill_improve`）。
```sql
skills(
  id PK, group_id FK NULL,        -- 可属某课题组，或平台级
  name_zh, name_en, icon, desc_zh, desc_en,
  founder_id FK→users, github_url, is_public BOOL, created_at
)
skill_members( skill_id FK, user_id FK, ds_role, granted_perms_json, PK )   -- 同数据集的成员/授权模型
skill_versions( id PK, skill_id FK, version_id, notes, created_by, created_at )
skill_bugs( ... )               -- 结构同 code_bugs，走评分制审核
github_skill_recos( id PK, group_id FK NULL, name, note, github_url, added_by )  -- GitHub 推荐 skill（点击跳转）
```

### 5.12 个人简历（本轮新增）
我的主页可进入**个人简历**，本人可编辑；提供**模板**或**空白创建**，支持基础排版（大标题 / 小标题 / 正文 / 分点）。
```sql
resumes( id PK, user_id FK UNIQUE, from_template BOOL, updated_at )
resume_blocks( id PK, resume_id FK, seq, type, text_zh, text_en )   -- type: 'h'|'h2'|'p'|'li'
```

---

## 六、权限模型与关键流程

### 6.1 三级角色模型（本轮重构，权限码驱动）

身份**不在登录时选择**——登录即"你本人"。角色在**创建时产生**并**可交接**：创建课题组 → 成为该组 `group_admin`；发起数据集 → 成为该数据集 `founder`。角色可转让给他人（交接）。

**① 站点级（全站作用域）**
| 角色 | 权限 |
|---|---|
| **super_admin 总管理员 / 平台维护者**（可多个、可交接，通常平台运维 + 导师） | **平台运维层面**：账号生命周期（启用/停用/重置密码）、课题组登记的**元信息**审批（新建/停用）、平台配置与 AI 网关、存储/备份、滥用与申诉处理、**动作元数据级审计**。 |
| member 普通成员（含新注册的空白账户） | `post.create`(全平台/组内/私密)、`group.create`(创建课题组)、`group.join_request`、`profile.edit`，未加入任何组也能在研究广场/我的主页维护（对全平台可见） |

> **总管理员的隐私边界（本轮明确，重要）**：总管理员是**平台维护者**，不是内容超级用户。为避免隐私泄露，**总管理员默认不能查看任何课题组/数据集的内部内容、原始数据、成员贡献明细或研究想法**（只见名称/负责人/成员数等元信息）；审计日志对其只暴露**动作元数据**（谁在何时做了什么类型的操作），不暴露内容与被改的具体值。总管理员**不能单方面删除用户数据**——删除须由数据/内容所有者发起，或经明示的申诉/合规流程，且一律为**可审计的软删除**（保留可恢复窗口 + 全程留痕）。需要跨隐私边界的操作（如合规调查）应走"双人授权 + 留痕"的例外流程，而非日常权限。全员贡献总览等含成员数据的视图归**课题组管理员**（组内作用域），不归总管理员。

**② 课题组级（作用域限单个课题组，存 `group_members.group_role`）**
| 角色 | 权限 |
|---|---|
| **group_admin 课题组管理员**（可多个、可交接） | 审批加入本课题组的申请、管理本组成员、编辑**课题组公约**、在本组下管理数据集、查看本组全员总贡献度与分数据集贡献度 |
| member 课题组成员 | 浏览本组数据集与想法、在本组发帖、申请加入本组某数据集处理 |

**③ 数据集级（作用域限单个数据集，存 `dataset_members.ds_role` + `granted_perms_json`）**
| 角色 | 权限 |
|---|---|
| **founder 发起人 / 数据集管理员**（可交接） | 该数据集内最大权限：发版、勘误**终审**、管理成员与授权、编辑数据集公约与文献地图、审批加入本数据集处理的申请。可**给成员授权，最高可授到与自己一致** |
| maintainer 维护者 | 勘误写入、跑质量巡检、维护代码库（按授予的权限码） |
| member 数据集成员 | 按 `granted_perms_json` 分级：默认可下载数据、提交/评审勘误；更高权限由发起人授予 |

**数据集非成员的访问（本轮明确）**：任何登录用户即使**未加入某数据集处理**，也可**查看 codebook + 使用数据看板（含样本描述统计/分布/只读 AI 分析）**；但**不能下载原始数据**，也不能提交勘误写入。要下载/参与处理须"申请加入处理"经发起人/管理员审批。

**课题组的可发现性与非成员视图（本轮新增）**：`research_groups.discoverable` 由课题组管理员开关——关闭后该组不在"发现课题组"列出（他人看不到）。即使可发现，**非成员访问某课题组只显示公开信息：简介、成员人数、被作者设为"全平台可见"的研究想法**；**不显示成员名单明细**，数据集与组内可见内容需加入后可见。

**判断顺序**：`super_admin` 全通过 → 否则依次查该用户在**当前课题组** `group_members` 与**当前数据集** `dataset_members` 的角色/授权。业务代码只判断权限码；加角色/授权/交接 = 改数据行，不改代码。

### 6.2 加入数据集的审批流（本轮新增）
1. 成员在数据集详情点"申请加入处理" → 写 `join_requests(status=pending)`。
2. 该数据集 **founder 或任一 super_admin** 审批 → approved/rejected，记 `decided_by` + `decided_at`。
3. 通过后写 `dataset_members`（默认 ds_role=member + 基础授权，`approved_by` 记审批人）。
4. 数据集详情"**加入审批记录**"区展示：谁、何时加入、经谁同意（如"陈默 · 2026-05-10 加入 · 经 李小雨(发起人)同意"）。
5. 首页数据集卡片显示**成员数**。所有审批动作落 `audit_log`。

### 6.3 关键流程
- **原始数据勘误（评分制审核）**：成员提交 → 任意成员可**评审打 0–10 分** + **AI 自动评审打分** → 数据集管理员看到成员分/AI 分后**终审**（采纳程度 full/partial/reject + 最终分 0–10）→ 采纳则发版时修复、标 fixed + `fixed_in_version_id` → 通知 → 报告人贡献按**终审分加权**落账；参与评审且被采纳者也得分。
- **代码勘误**：成员在代码库定位某脚本某行提交 → 成员+AI 评分 → 数据集管理员终审 → 采纳随版本/代码更新修复 → 按终审分加权落账。
- **加入审批**：加入**课题组**由课题组管理员/超管审批；加入**数据集处理**由数据集发起人/管理员/超管审批；审批记录（谁、何时、经谁同意）在对应实体展示。
- **版本发布**：数据集 founder 或 super_admin；不可覆盖旧文件；版本号规范（`v1.0.1` 常规 /`-hotfix` 紧急 /`v1.1.0` 中等 /`v2.0.0` 重大）。
- **发帖可见性**：默认 group，可 private；带数据集标签→进入该数据集近期想法；super_admin/founder 可删重复、管标签、标"推荐讨论"，一期不默认允许改他人帖。
- **全员贡献总览**：super_admin 可见每个成员的数据勘误/代码勘误/数据上传/发帖计数与贡献度排行，可导出，作为署名/推荐信/名额依据。

### 6.4 附件限制
单附件 ≤ 50MB；数据文件仅 `.dta`，codebook PDF/DOCX；bug/帖子附件同 v1 白名单。

### 6.5 贡献度计分模型（本轮明确）
贡献度 = 各来源分项之和，勘误类按**管理员终审分**加权：

| 分项 | 计分方式 |
|---|---|
| 数据集发起人 | 固定基础分（如 +30） |
| 数据处理代码发起人 | 固定基础分（如 +20） |
| 原始数据勘误分 | Σ 每条被采纳勘误的 `final_score`（0–10 加权） |
| 原始数据勘误审核被采纳 | 参与评审且方向与终审一致时得分（每次 +k） |
| 数据处理代码勘误分 | Σ 被采纳代码勘误的 `final_score` |
| 数据处理代码被采纳 | 每次 +k |
| Skill 发起 / 优化被采纳 | 发起固定基础分；优化按被采纳加权（同勘误） |
| 数据核验（AI/规则提示后经核查提交并被采纳的勘误） | 计入上面"勘误分"，按终审分加权 |

展示：**我的主页 banner 只显示总"贡献度"**；"我的贡献"页展开上表明细。管理后台分**全员总贡献度**与**分数据集贡献度**两张表（对贡献事件按 user、按 (user,dataset) 聚合）。

### 6.6 公约（charter）与确认
- 每个**课题组**、每个**数据集**各有一份公约（`charters`，按 scope 区分），有显示栏与"查看全文"。
- **弹出时机（本轮明确）**：公约**不在登录/首页弹出**，而是在用户**首次进入对应课题组页面 / 数据集页面**时弹出（或该实体公约更新版本后首次进入时）。用户勾选同意后写 `charter_acks`（含版本），方可继续浏览该实体内容。已确认过的同版本公约不再重复弹。
- 编辑权限：课题组公约→课题组管理员；数据集公约→数据集发起人/管理员。典型条款如"禁止外传数据""学术讨论禁止截图公开发表""引用须致谢维护者"。

---

## 七、API 设计（一期，REST 摘要）

```
# 认证与用户
POST /api/auth/login | /api/auth/refresh
GET  /api/me                             -> 用户 + 权限码
GET  /api/users/{id}                      -> 个人主页(简介/统计/发帖/贡献/维护清单)
PATCH/api/me (language, bio, avatar)

# 课题组
GET  /api/groups                          -> 我的课题组 + 发现课题组
POST /api/groups                          -> 创建课题组(创建者成为 group_admin)
GET  /api/groups/{slug}                   -> 课题组详情(公约/数据集/成员/想法)
POST /api/groups/{slug}/join-requests ; POST /api/group-join/{id}/decide [group_admin/super]
POST /api/groups/{slug}/datasets          [group_admin/member] 发起新数据集(founder_contact 必填)

# 公约
GET  /api/charters?scope=&ref=            -> 取某组/数据集公约
POST /api/charters/{id}/ack               -> 用户确认同意(记版本)
PUT  /api/charters/{id}                    [对应级管理员] 编辑

# 数据集
GET  /api/datasets                        -> 首页入口墙(含成员数)
GET  /api/datasets/{slug}                 -> 详情(概览/当前版本/统计/成员/审批记录/近期刊物/近期想法)
GET  /api/datasets/{slug}/versions ; POST /api/datasets/{slug}/versions [founder/admin]
GET  /api/datasets/{slug}/versions/{v}/download?file=data|codebook  -> data 需数据集成员权限；codebook 任意登录用户可下
GET  /api/datasets/{slug}/variables ; GET /api/datasets/{slug}/codebook  -> 非成员亦可

# 数据集成员与加入审批
GET  /api/datasets/{slug}/members                     -> 成员列表 + 审批记录
POST /api/datasets/{slug}/join-requests               -> 申请加入
POST /api/join-requests/{id}/decide                   [founder/super_admin] approve|reject
POST /api/datasets/{slug}/members/{uid}/grant         [founder] 授权(≤ 自己权限)

# 数据看板 + AI/代码描述分析（只读）
GET  /api/datasets/{slug}/dashboard?var=&group=&metric=   -> 预设看板分布
POST /api/datasets/{slug}/analysis/generate              -> 传 prompt+schema，返回 AI 生成代码(不传原始数据)
POST /api/datasets/{slug}/analysis/run                   -> 只读沙箱执行手写/AI代码，返回聚合结果/图

# 文献地图 + 刊物
GET  /api/datasets/{slug}/literature                     -> 思维导图话题 + 重点文献
POST /api/datasets/{slug}/literature/ai-summarize        [perm] AI 总结研究用途/话题
POST /api/datasets/{slug}/literature (topics/refs)       [perm] 上传/修改
GET  /api/datasets/{slug}/publications                   -> 近期刊物(自动追踪+人工补录)

# 原始数据勘误（评分制审核）
GET/POST /api/datasets/{slug}/bugs ; PATCH /api/bugs/{id}
POST /api/bugs/{id}/reviews               -> 成员评审打分(0–10)
POST /api/bugs/{id}/ai-review             -> 触发 AI 自动评审打分
POST /api/bugs/{id}/finalize              [数据集管理员] 终审:采纳程度+最终分

# 处理代码库 + 代码勘误
GET  /api/datasets/{slug}/code ; GET /api/code/{id}
GET/POST /api/code/{id}/bugs
POST /api/codebugs/{id}/reviews | /ai-review | /finalize   -- 同评分制审核

# 研究广场 / 帖子 / 项目
GET/POST /api/posts ; PATCH /api/posts/{id}         -- 带 dataset_id → 进该数据集近期想法
POST /api/posts/{id}/react | /comments | /flag[admin]
GET/POST /api/projects ; PATCH /api/projects/{id}   -- 在做的项目(欢迎讨论)，同时进广场与个人主页
GET  /api/users/{id}/projects

# 治理
GET  /api/me/contributions                -> 个人贡献明细(发起/勘误分/审核被采纳/代码...)
GET  /api/admin/contributions?scope=total|by_dataset   [group_admin/super] 全员总贡献度 / 分数据集贡献度
GET  /api/admin/group-join-requests       [group_admin/super] 加入课题组申请
GET  /api/admin/super-admins ; POST ...   [super_admin] 管理/交接总管理员
GET  /api/admin/groups                     [super_admin] 全部课题组
GET  /api/admin/audit-log ; POST /api/quality/run [super/group/founder 按域]
```

---

## 八、视觉规范（学术科研共享平台：简约 · 高级 · 专业）

Design tokens（前端 CSS 变量，静态原型已落地）：
- **配色**：墨色文字 `#1a1a1a`；暖白背景 `#faf9f6`；卡片白 `#fff`；细线 `#e6e3dc`；**单一学术强调色深靛蓝 `#2d4a7c`**（备选深勃艮第红）；状态色克制（绿/琥珀/灰红/蓝）。个人主页 banner 用强调色渐变，克制使用。
- **字体**：正文无衬线（Inter/思源黑体）；标题与数据大数用衬线（Source Serif/思源宋体）；`officerID`/版本号/变量名/代码用等宽。
- **排版**：大量留白、三线表、小型全大写标签、卡片悬浮微动效；数据集卡片、帖子卡片（小红书式网格）保持一致的克制质感；代码用深色 `pre` 展示。
- **社区不花哨**：研究广场与个人主页借用小红书的"低门槛发帖 + 卡片流"交互，但视觉保持学术冷静感，不做重色彩/重表情。
- 全部可见文本走 i18n，中英即时切换。

---

### 8.3 交互规范（可点击 / 详情 / 增删改，本轮明确）
- **处处可 link 到主页**：任何显示用户的地方（研究想法作者、评论者、成员列表、贡献排行、发起人 ID、勘误提交/评审人）都可点击进入该用户主页。
- **内容可点开详情**：研究想法、发帖、在做的项目、刊物、重点文献、代码脚本、贡献明细行、数据集/课题组卡片都应能点开查看更完整内容（详情页/弹窗）。
- **贡献可溯源**：我的贡献每一条可点开并**跳转到来源**（对应数据集 / 勘误 / 代码 / 评审记录）。
- **发起人可增删改自己的内容**：本人对自己的发帖、在做的项目、勘误(未审核前)、评论有编辑/删除；数据集/代码发起人对相应对象有管理权。
- **创建入口齐全**：创建课题组(首页)、发起数据集(课题组页)、发帖(广场)、发起项目(主页)、**提交新代码/新功能脚本(处理代码库)**、提交勘误、添加重点文献、发布版本、编辑公约、授权成员。
- **"我维护/发起的数据·代码"可 link** 到对应数据集页与代码页。

### 8.4 平台品牌与页脚（本轮新增）
首页与注册/登录页底部有统一页脚：**平台名（暂定"科研数据共享平台 · Research Hub"）+ slogan（暂定"让每一份自建数据都可信、可复用、可归属"）+ "北京大学国家发展研究院 · 智慧科研团队" + 版权年**。配色沿用学术强调色，克制、居中、细分隔线，与整体简约高级风一致。平台名/slogan 为占位，可由团队最终确定。

## 九、部署方案（两阶段：腾讯云先行 → 北大校内迁移）

> 落地路线：**第一步部署到腾讯云**（快速上线、团队试用、内测），**第二步迁移到北大校内服务器**（承载真实敏感数据）。应用从一开始就按"可迁移"设计，两阶段用同一套代码，只换配置与数据存储位置。

### 9.1 第一阶段 · 腾讯云（首发）
| 用途 | 腾讯云选型（二选一按预算） | 说明 |
|---|---|---|
| 计算 | **轻量应用服务器 Lighthouse**（2C4G 起，省心）或 **CVM 云服务器**（2C4G/4C8G，Ubuntu 22.04） | 跑 FastAPI(Gunicorn+Uvicorn worker) + 前端静态资源 |
| 数据库 | **TencentDB for PostgreSQL**（托管，自动备份/高可用）；预算紧可先在同机自装 PostgreSQL 15 | 与本地 SQLite 同一 SQLAlchemy 代码，仅换 `DATABASE_URL` |
| 文件对象存储 | **腾讯云 COS**（数据版本 `.dta`/codebook、附件、简历图等），用 SDK 上传下载 + 私有读、签名 URL | `storage` 接口抽象：本地目录 / COS 两实现可切换 |
| 反代与 HTTPS | Nginx + **腾讯云 SSL 证书**（免费 DV）或直接域名接 CLB | 前端走 HTTPS，API 同域 `/api` |
| 域名 | 腾讯云 DNS 解析（如需公网访问需 ICP 备案，预留 2–3 周） | 内测可先用 IP + 自签或临时域名 |
| 备份 | TencentDB 自动备份 + COS 版本控制/跨地域复制；应用侧每日 `pg_dump` 存 COS | |
| 日志/监控 | 云监控 + 应用结构化日志（写文件 + 可接 CLS 日志服务） | |

**部署形态**：推荐 **Docker Compose**（`web`=FastAPI、`nginx`、可选 `db`）。一条 `docker compose up -d` 起服务；升级即换镜像。CI 可用 GitHub Actions/腾讯云 CODING 构建镜像推到 **TCR 容器镜像服务**。

### 9.2 关键：敏感数据在两阶段的处理（务必遵守）
官员数据敏感。**第一阶段在腾讯云上不要放真实敏感原始数据**：
- 腾讯云阶段用于**功能试用与内测**，数据集只放**合成/脱敏样例**（保留结构与变量，不含真实敏感取值）；或团队评估后仅放**非敏感数据集**。
- 平台从设计上支持"**数据留在私有环境**"：真实敏感 `.dta` 待**第二阶段迁到北大校内**再导入；届时 COS 换成校内对象存储/本地目录，DB 换成校内 PostgreSQL。
- 无论哪个阶段：最小授权、下载分级（6.1）、导出全程 `audit_log` 留痕、AI 网关"元数据出站校验"（第十三章）一律生效。
- 若团队接受在腾讯云放某些真实数据，须先做**合规评估 + 数据使用协议 + 传输/静态加密（COS SSE、DB 加密、全站 HTTPS）**，并把敏感数据集标记 `is_sensitive` 以强约束下载与外发。

### 9.3 第二阶段 · 北大校内服务器（承载真实敏感数据）
- 校内 Linux VM（Ubuntu 22.04，参考 4C/16G/1T，可按数据规模申请）；仅校园网段开放、不暴露公网、校外经北大 VPN。
- **迁移动作**：换 `DATABASE_URL` 到校内 PostgreSQL；`storage` 从 COS 切到本地/校内对象存储；`pg_dump`/`pg_restore` 迁移库；文件搬迁；DNS/反代改校内。**代码不变**。
- 备份至另一校内节点/北大网盘；数据不出校园网。

### 9.4 可迁移性设计要求（一期就要落实）
- 所有环境相关项走**环境变量/配置**：`DATABASE_URL`、`STORAGE_BACKEND(local|cos)`、`COS_*`、`AI_GATEWAY_URL`、`JWT_SECRET`、`ALLOWED_ORIGINS`。
- `storage` 与 `ai_client` 都是**接口 + 多实现**，切换=改配置。
- DB 只用 PostgreSQL 兼容语法（本地开发可 SQLite，生产两阶段都 PostgreSQL），迁移经 Alembic。
- 不写死任何云厂商 SDK 到业务逻辑，仅在 `storage` 实现层引用 COS SDK。

---

## 十、技术栈与工程结构

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11 + FastAPI + Uvicorn + SQLAlchemy 2 + Alembic + Pydantic v2 |
| 鉴权 | JWT(access+refresh) + argon2 密码哈希；权限码守卫 |
| 数据库 | 本地开发 SQLite；**生产两阶段均 PostgreSQL 15**（腾讯云 TencentDB → 校内 PG），`DATABASE_URL` 切换 |
| 前端 | **Vue 3 + Vite + TS + vue-router + pinia + vue-i18n + Tailwind**（执行者更熟 React 可整体替换为 React+Vite，架构等价） |
| 图表 | 看板用轻量图表（如 ECharts / Chart.js）；一期原型用纯 CSS 条形示意 |
| 文件 | `storage` 接口 + 双实现：本地目录（校内）/ 腾讯云 COS（云上），`STORAGE_BACKEND` 切换 |
| AI | `ai_client` 接口 + 出站脱敏网关；provider 走配置（付费 API / 校内自托管） |
| 打包部署 | **Docker + docker-compose**（web/nginx[/db]）；镜像可推 TCR；CI 用 GitHub Actions/CODING |

```
/backend   app/(main.py, models/, schemas/, api/, core/(auth,perm,audit,storage,ai), services/) + alembic/ + seed.py + tests/
/frontend  src/(router, stores, i18n, views/{Home,Group,Dataset,Feed,Skills,Profile,Admin}, components/)
/deploy    docker-compose.yml  Dockerfile  nginx.conf  .env.example
/data      versions/  uploads/  (本地开发；生产用 COS/校内存储)
/docs      本文档
```
必备配置项（`.env`）：`DATABASE_URL`、`STORAGE_BACKEND`(local|cos)、`COS_BUCKET/COS_REGION/COS_SECRET_ID/COS_SECRET_KEY`、`AI_GATEWAY_URL`、`AI_PROVIDER`、`JWT_SECRET`、`JWT_ACCESS_TTL/REFRESH_TTL`、`ALLOWED_ORIGINS`、`MAX_UPLOAD_MB=50`。

---

## 十一、交接执行清单（下一线程直接照做）

> 落地顺序：先 M0–M6 搭骨架跑通第十五章验收清单，再把原型里所有 `alert('原型：...')` 占位替换为真实接口（见第十四章 CRUD 清单）。首发部署到腾讯云。

**M0 脚手架 + 部署骨架**：前后端分离 monorepo；后端 FastAPI+SQLAlchemy+Alembic+JWT；前端 Vite+Vue3+TS+Tailwind+i18n，落地第八章 tokens；同时写好 `/deploy`（Dockerfile + docker-compose + nginx + `.env.example`），`storage`/`ai_client` 双实现接口。**尽早在腾讯云拉起最小可运行版**（Lighthouse/CVM + PostgreSQL + COS + HTTPS），后续持续部署。

**M1 数据模型与底座**：按第五章建全部表（含 `research_groups`/`group_members`/`charters`/`datasets`/`correction_reviews`/`correction_finals` 等）+ 初始迁移；seed 预置总管理员、NSD 课题组 + 2–3 数据集(含发起人+联系方式)、公约、权限码、变量/版本/代码/帖子/贡献。实现审计中间件与 `record_contribution()`。

**M1.5 三级权限 + 公约确认**：站点 super_admin(可多个,可交接) / 课题组 group_admin / 数据集 founder-maintainer-member(+granted_perms)；角色创建时产生、可交接；权限判断按"super_admin→课题组→数据集"顺序。公约进入弹窗 + `charter_acks`。**数据集非成员**：codebook+看板放行、下载/写入拦截。

**M2 多课题组 + 数据集 + 双勘误评分审核**：首页我的/发现课题组 + 创建/加入审批；课题组详情(公约/数据集网格/发起新数据集/成员/想法)；数据集详情 Tab(概览/看板/文献/版本/原始勘误/代码库/数据集后台)；勘误走**成员评分+AI评分→管理员终审最终分**，贡献按终审分加权。

**M2.5 数据核验专栏**：规则自动跑写 `verify_flags`；AI 扫描写疑似 flag；"一键生成勘误草稿"→预填 `bugs` 进评分制审核；**不静默改原始数据**（单测）。

**M3 社区 + 项目工作台 + Skill + 简历**：研究广场发帖(可见性三级+标签路由)+评论/点赞/收藏完整 CRUD；个人主页(banner 只贡献度 + 课题组显隐)；**公开项目 + 项目工作台完整 CRUD**（进展/待办/讨论/文件/Overleaf 链接录入与跳转，见 14.2）；**Skill 共享**(发起/权限/协作/GitHub 链接/计分)；**个人简历**(模板/空白 + 块级增删改排序)；处理代码"一键生成数据处理说明"。

**M4 看板 + AI/代码分析**：① 样本描述统计(勾选多变量) ② 自定义维度分布 ③ AI/手写描述分析(AI 网关生成代码 + **只读沙箱**执行,禁写回/禁网络)。文献地图 + 重点文献(人工+AI 总结)；刊物(人工+可选 Crossref)。

**M5 自动化**：定时质量巡检(APScheduler)；刊物追踪(可选)。搭 `ai_client` 网关 + 出站脱敏校验（第十三章）。

**M6 治理与自检**：三级管理后台(超管:课题组/总管理员交接/全站日志；课题组管理员:加入审批/公约/全员总贡献度+分数据集贡献度；数据集管理员:数据集后台)；单测覆盖三级权限、版本不可覆盖、沙箱只读、非成员下载拦截、公约门禁；假数据走通全流程；README(含 AI 网关配置与校内 GPU 可选路线)。

---

## 十二、留待团队决定的开放问题
1. 激励"软/硬"程度（建议二期从软起）。
2. 访问分级门槛：贡献到什么程度解锁什么；原始 vs 衍生数据是否区别对待。
3. 署名/稀缺资源折算规则、裁定人。
4. 数据看板：一期"预设+有限自定义"是否够用，还是二期尽快上实时引擎。
5. 敏感数据流失防线（最小授权边界、导出审计粒度、使用协议）。
6. 前端框架最终确认：Vue（默认）or React；强调色深靛蓝 or 勃艮第红。
7. **AI 方案选型**（见第十三章）：付费 API（Claude，元数据不出敏感数据）先行，还是一期就在校内 GPU 自建开源模型？看板 AI 分析、文献总结分别用哪档。
8. **腾讯云阶段的数据边界**：仅放合成/脱敏数据，还是允许部分非敏感真实数据？敏感数据一律等第二阶段迁北大？（建议：云上只放合成/脱敏，真实敏感数据待校内。）
9. **贡献度各分项的具体权重数值**：发起人基础分、每类勘误的加权系数、审核被采纳的 +k、Skill 分等，需团队定标（第 6.5 节给了结构，数值待定）。
10. **平台名与 slogan 最终确定**（第 8.4 节为占位）。

---

## 十三、自动化与 AI 集成 · 部署策略

> 回应"哪些功能可自动化、如何接入自动化、付费 API vs 本地、经济性与数据安全、本地部署技术方案"。核心判断：**先做不需要 AI 的确定性自动化（几乎零成本、零风险），AI 功能用"元数据出、原始数据不出"的网关先接付费前沿模型，把 provider 藏在一个可切换的抽象后，将来按需换成校内 GPU 自托管。**

### 13.1 哪些功能可自动化（按"是否需要 AI / 成本 / 价值"分档）

**A. 无需 AI 的确定性自动化——优先做，成本≈0，价值高**
- **数据质量巡检（M1）**：定时跑规则（ID 唯一性、`begin_yr≤end_yr`、复合键冲突、字段分布突变），失败进错误队列并通知。用 APScheduler/cron，纯规则，确定可靠。→ **一期就上。**
- **近期刊物追踪**：按数据集关键词/引用定期查 **Crossref API（免费）**，自动补 `publications`。
- **活动摘要/通知**：定时汇总近期勘误、发版、热帖，发平台内消息/邮件。
- **下载与审计统计**：定时聚合成报表。

**B. 需要 LLM、但只吃"元数据/公开文本"——安全，付费 API 性价比最高**
- **看板 AI 描述分析（本轮点 3）**：LLM 只接收**变量名 + codebook + 自然语言需求**，生成 pandas/Stata 代码；**代码在校内只读沙箱执行**，原始敏感数据**不出服务器**。（要 AI 解读结果时，只回传聚合、非可识别的汇总。）
- **文献研究用途/话题总结 + 思维导图（本轮点 5）**：对公开论文与数据集描述做总结，无敏感数据。低频、突发。
- **代码勘误/研究想法的辅助**：预筛 bug、建议 patch、给发帖打标签。

**C. 需要 LLM + 检索/向量——中期**
- **发现与匹配（M6）**：谁清过某变量、谁在做相近题目。用**本地嵌入模型**（CPU 即可，便宜）算相似度 + 少量 LLM 生成线索。
- **数据处理的学术化导出（M7）**：溯源+贡献→论文数据附录。突发、付费 API 即可。

### 13.2 付费 API vs 本地模型：成本、效果、安全的权衡

- **成本不是主要矛盾**：课题组的 AI 用量是突发的（每天几十~几百次），前沿付费 API（如 Claude）月成本大概率在几十到一两百元量级——相对经费可忽略。**真正的约束是数据安全**：官员数据敏感，原则上不出校园网、不发商业 API。
- **关键设计：把"敏感原始数据"与"元数据/文本"分开**。绝大多数 AI 任务（代码生成、文献总结、匹配）只需要元数据/公开文本，**天然可以安全地用付费 API**；唯一会碰到原始数据的是"对数据算描述统计"，而这一步的正确做法是**LLM 只写代码、代码在本地跑**，数据仍不出服务器。→ 因此**付费 API 能覆盖绝大部分 AI 需求且不触碰敏感数据**。
- **何时必须本地模型**：若团队/合规要求"连元数据都不得出校园网"，则需自托管开源模型。这要**GPU**——当前规划的 4 核/16G CPU 服务器跑不动好模型。
- **建议（性价比 + 安全的折中）**：
  1. 一期：只做 A 类确定性自动化 + 搭好 **AI 网关抽象层**（一个 `ai_client` 接口 + 出站**脱敏/白名单校验**，硬性拦截任何原始数据行进入 payload）。
  2. 二期：AI 功能（看板分析、文献总结）先接**付费前沿 API（元数据-only）**，效果最好、上线最快、成本可忽略。
  3. 若安全策略收紧：把网关指向**校内 GPU 上自托管的开源模型**（如 Qwen2.5-32B/72B 量化版，用 vLLM/Ollama 暴露 OpenAI 兼容接口），业务代码零改动。

### 13.3 本地/校内部署的技术实现

- **Web 应用 + 数据库**：部署在 v3 备忘录规划的**校内 Linux VM（Ubuntu 22.04，4C/16G/1T）**，仅校园网段开放、不暴露公网、校外经北大 VPN。FastAPI(+Uvicorn/Gunicorn) + 前端静态资源 + SQLite→PostgreSQL，Nginx 反代，systemd 守护，每日备份至另一校内节点/北大网盘。
- **只读分析沙箱**：在同一台机或旁挂容器里跑，**只读挂载**数据版本目录，**禁网络、禁写回**，超时与资源限额（跑用户/AI 生成的分析代码）。这是"看板 AI/手写分析不改原始值"的技术保证。
- **AI 服务的位置**：
  - **付费 API 路线**：Web 应用经 AI 网关出站到商业 API；网关强制"仅元数据/聚合"策略，原始数据永不出服务器。无需 GPU。
  - **自托管路线**：向**学校高性能计算中心 / 国发院 IT 申请一台 GPU 节点**（1×24–48GB 显存可跑量化 32B；70B 需更大或多卡），与 Web 服务器同处校园网内网互通；用 vLLM/Ollama/TGI 起一个内网 `http://ai-node:8000/v1` 的 OpenAI 兼容端点，AI 网关指过去即可。**不建议把 GPU 推理和 Web/DB 挤在同一台 4C/16G 机器上**。
- **provider 可切换**：所有 AI 调用只经过 `ai_client`（配置项决定指向付费 API 或内网自托管端点），从而"先付费、后自托管"的迁移只是改配置。

### 13.4 一句话建议
确定性自动化（质量巡检、刊物追踪、摘要）**一期直接上**，几乎零成本零风险；AI 功能**二期接付费前沿 API（元数据-only + 只读沙箱）**，效果最好且不碰敏感数据；把 provider 藏在网关后，为将来校内 GPU 自托管留好一键切换。这样既不"一味贵"，也守住数据安全。

---

## 十四、功能完整性与 CRUD 清单（落地必做，勿只做"能看"的壳）

> **重要**：随附的 HTML 原型是**视觉与流程演示**，其中大量按钮是占位（`alert('原型：...')`），如"新建工作台""更新进展""添加待办""上传 Overleaf/GitHub 链接"等**都还没有真实实现**。落地时必须把每个实体做成完整 CRUD + 权限校验 + 校验/错误处理 + 审计。下表逐一列出（★=原型里目前是空按钮/占位，落地必须补实）。

### 14.1 CRUD 与交互总表

| 实体 | 增 Create | 查 Read | 改 Update | 删 Delete | 关键交互（★=原型占位待实现） |
|---|---|---|---|---|---|
| 课题组 group | ★创建(成为 group_admin) | 列表/详情 | ★改简介/图标/discoverable | 停用(软删) | ★申请加入→审批；成员显隐 |
| 数据集 dataset | ★发起(填 founder_contact 必填校验) | 详情/Tab | ★改元信息 | 停用(软删) | ★申请加入处理→审批；下载分级 |
| 数据版本 version | ★发布(上传 .dta/codebook，不可覆盖) | 版本库 | 仅元数据(changelog) | 不可删(仅下架) | 关联修复 bug；下载(成员当前/管理员全部) |
| 变量 variable | ★录入/导入 codebook | 下拉/列表 | ★改标签 | 停用 | — |
| 原始勘误 bug | 提交(附件) | 列表/详情 | 本人未审核前可改 | 本人未审核前可删 | ★成员评分/AI评分/★管理员终审 |
| 代码脚本 code | ★提交新代码(★原型有按钮，需接后端) | 库/预览 | 作者/管理员改 | 作者/管理员删 | ★一键生成数据处理说明 |
| 代码勘误 code_bug | 提交 | 队列 | 本人未审核前 | 本人未审核前 | 评分制审核(同上) |
| 核验 flag→草稿 | ★由规则/AI 生成 flag；★一键生成勘误草稿 | 核验专栏 | 确认/忽略 | — | ★"去核查"跳转记录；采纳计分 |
| 研究想法/发帖 post | 发布(可见性三级+数据集标签) | 广场/详情 | ★本人编辑 | ★本人删除 | 点赞/收藏/★评论增改删 |
| 公开项目 project | 发布 | 详情 | ★本人编辑 | ★本人删除 | 评论、招募 |
| 项目工作台 workspace | ★新建(选可见成员) | 仅协作者可见 | ★改标题/成员/Overleaf 链接 | ★删除 | 见 14.2 |
| ★工作台进展 update | ★新增进展 | 列表 | ★编辑 | ★删除 | — |
| ★工作台待办 todo | ★新增待办 | 列表 | ★编辑文本/★勾选完成/指派 | ★删除 | — |
| ★工作台讨论 note | ★新增讨论 | 列表 | ★编辑 | ★删除 | @成员 |
| ★工作台文件 | ★上传结果文件 | 列表 | — | ★删除 | — |
| Overleaf/GitHub 链接 | ★录入 URL(带 http/格式校验) | 点击跳转 | ★修改 URL | ★清除 | 打开新窗口 |
| Skill | ★发起(同数据集) | 库/详情 | ★改/协作优化 | 停用 | GitHub 链接录入；★申请加入；计分 |
| GitHub 推荐 skill | ★添加(URL 校验) | 列表 | ★改 | ★删 | 跳转 |
| 个人简历 resume | ★模板/空白创建 | 查看 | ★块级编辑(标题/小标题/正文/分点，增删改、排序) | ★删块 | 导出(可选) |
| 公约 charter | 随实体创建 | 显示栏/全文 | ★对应级管理员编辑(生成新版本→成员重新确认) | — | 进入弹窗确认(`charter_acks`) |
| 成员授权 grant | ★发起人授权(≤自己) | 成员表 | ★改授权 | ★撤销 | — |
| 加入审批 | 申请 | 待审队列 | approve/reject(记审批人+时间) | — | 课题组/数据集两类 |
| 文献/思维导图 lit | ★添加文献/★AI 生成/编辑话题 | 文献地图 | ★编辑 | ★删 | 权限门控完整显示 |
| 总管理员 | ★新增/交接 | 列表 | 交接 | 移除 | 账号启停/重置密码(不删数据) |

### 14.2 项目工作台的完整交互（回应反馈里的具体缺口）
- **新建工作台**：弹表单 → 标题、选择可见成员（成员选择器）、可选 Overleaf URL → `POST /api/workspaces`。
- **进展记录**：列表 + "＋更新进展"（新增）+ 每条可编辑/删除（本人或协作者按权限）→ `POST/PATCH/DELETE /api/workspaces/{id}/updates`。
- **待办**：新增、勾选完成(toggle done)、编辑文本、指派成员、删除 → `.../todos`。
- **讨论记录**：新增、编辑、删除、@成员 → `.../notes`。
- **结果文件**：上传/删除（走 storage，≤50MB 白名单）→ `.../files`。
- **Overleaf 链接**：输入框录入并校验 `https://www.overleaf.com/...`，保存后按钮可点击跳转；可修改/清除。
- 权限：仅 `workspace_members` 可读写；owner 可增删成员与删工作台。

### 14.3 需补齐的 API（对应 14.1，摘要）
```
# 工作台
GET/POST /api/workspaces ; GET/PATCH/DELETE /api/workspaces/{id}
POST/PATCH/DELETE /api/workspaces/{id}/updates|todos|notes|files
POST/DELETE /api/workspaces/{id}/members
# Skill
GET/POST /api/skills ; GET/PATCH/DELETE /api/skills/{id}
POST /api/skills/{id}/join-requests ; POST /api/skills/{id}/versions
GET/POST/PATCH/DELETE /api/github-skill-recos
# 简历
GET /api/users/{id}/resume ; PUT /api/me/resume ; POST/PATCH/DELETE /api/me/resume/blocks
# 公约 / 核验 / 代码说明
PUT /api/charters/{id}（生成新版本）
POST /api/datasets/{slug}/verify/run ; POST /api/verify-flags/{id}/draft-bug ; POST /api/verify-flags/{id}/dismiss
POST /api/code/{id}/writeup（AI 生成数据处理说明）
# 帖子/项目/评论 完整 CRUD
PATCH/DELETE /api/posts/{id} ; POST/PATCH/DELETE /api/posts/{id}/comments
GET/POST/PATCH/DELETE /api/projects[/id]
```
所有写接口：JWT + 权限码校验、Pydantic 入参校验、URL/文件类型校验、写 `audit_log`、返回结构化错误。

---

## 十五、验收标准与交接就绪度

### 15.1 一期完成定义（DoD，逐条可勾验收）
- [ ] 注册/登录/JWT；三级权限按"超管→课题组→数据集"判定；总管理员隐私边界（看不到内容/贡献、不能删数据）经测试。
- [ ] 课题组：创建/发现/申请加入/审批/成员显隐/discoverable 开关；非成员只见公开信息。
- [ ] 数据集：发起(联系方式必填)/版本发布(不可覆盖)/下载分级(成员当前·管理员全部)/codebook 非成员可看。
- [ ] 双勘误评分制审核全链路：提交→成员评分+AI评分→管理员终审(采纳程度+最终分)→发版修复→贡献按终审分加权入账。
- [ ] 数据核验专栏：规则自动跑 + AI 标记疑似 + 一键生成勘误草稿；**不静默改原始数据**（单测覆盖）。
- [ ] 看板：样本描述统计(多变量) + 自定义维度分布 + AI/手写只读沙箱(禁写回/禁网络，单测覆盖)。
- [ ] 社区：发帖(可见性三级+标签路由)/评论/点赞/收藏；公开项目 + **项目工作台完整 CRUD**(进展/待办/讨论/文件/Overleaf)。
- [ ] Skill 共享(发起/权限/协作/GitHub 链接/计分)；个人简历(模板/空白/块级编辑)。
- [ ] 公约：进入课题组/数据集时弹出确认 + 版本化 + 管理员可编辑。
- [ ] 全站/组内/数据集三层管理后台各就位；全员总贡献度 + 分数据集贡献度(归课题组管理员)。
- [ ] 双语 zh/en 全量；i18n 无漏词。
- [ ] 部署：Docker Compose 起腾讯云；COS 存文件；PostgreSQL；HTTPS；每日备份；`.env.example` 齐全。
- [ ] 测试：权限矩阵、版本不可覆盖、下载分级、沙箱只读、核验不改数据、公约门禁的单测/集成测试通过；关键流程 e2e 走通。
- [ ] 敏感数据合规：腾讯云阶段仅合成/脱敏数据；导出留痕；AI 网关脱敏校验开启。

### 15.2 就绪度自评（诚实说明）
本文档已覆盖**产品设计 + 数据模型(schema) + 三级权限 + API 面 + 部署(腾讯云→北大) + 完整 CRUD 清单 + 验收标准**，可作为**开发交接蓝图**直接开工。仍需下一线程在实现中补足的：具体字段级校验规则、分页/排序/搜索细节、错误码规范、前端组件级交互稿(可照原型)、贡献度各分项的**具体权重数值**(需团队定)、以及第十二章"留待团队决定"的策略项。建议：**先按第十一章 M0–M6 搭骨架并跑通验收清单，把原型中所有 `alert('原型：...')` 占位替换为真实接口调用**。

---

> 一句话总结：平台是一个**多课题组的开放科研数据共享空间**——把各组自建数据变成可信、可复用、贡献可归属的共享资产（数据面），在其上长出跨组的低成本学术交流社区（社区面），用三级权限、公约、评分制审核与清晰的贡献记录把公共投入公平兑现（治理面）。一期先把**多课题组框架 + 三级权限与公约 + 加入审批 + 双勘误评分审核 + 数据集社区化(刊物/想法/文献) + 看板(样本统计/分布/AI只读分析) + 贡献明细与总览 + 确定性自动化**的底座和核心闭环立起来。
