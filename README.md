# 科研数据共享平台 · Research Hub

面向多个课题组的开放科研数据共享平台：把各组自建数据变成**可信、可溯源、有版本、贡献可归属**的共享资产，并配学术交流社区。首个课题组 = NSD 发展政经课题组，首个数据集 = COD 地方官员数据库。

> 按《README-交接摘要.md》《COD数据协作平台-项目开发文档-v1.md》实现。一期落地腾讯云（TencentDB + COS），仅放合成/脱敏数据内测；二期迁北大校内换配置即可。

## 技术栈
- 后端 FastAPI + SQLAlchemy2 + Alembic + Pydantic v2 + JWT(argon2)
- 前端 Vue3 + Vite + TS + vue-router + pinia + vue-i18n + Tailwind
- 数据库 本地 SQLite / 生产 PostgreSQL15（`DATABASE_URL` 切换）
- 存储 `storage` 接口双实现：本地目录 / 腾讯云 COS（`STORAGE_BACKEND` 切换）
- AI `ai_client` 接口 + 出站脱敏网关（provider 可换）
- 部署 Docker Compose（web / nginx[/db]）

## 目录结构
```
backend/   FastAPI 应用（app/core, app/models[56表], app/schemas, app/api[13路由], app/services, alembic, tests, seed.py）
frontend/  Vue3 应用（src/views[8页], components, stores, i18n, api, router）
deploy/    docker-compose.yml, deploy.sh(一键), .env.example, nginx-ssl.conf.example
data/      本地开发文件目录（生产用 COS/校内存储）
```

## 本地开发
```bash
# 后端
cd backend
pip install -r requirements.txt
export DATABASE_URL="sqlite:////tmp/dev.db"
python -m app.seed                 # 灌入假数据
uvicorn app.main:app --reload      # http://localhost:8000/docs

# 前端
cd frontend
npm install
npm run dev                        # http://localhost:5173 （已配 /api 代理到 8000）
```
默认账号：`admin/admin123`、`lixiaoyu/pass123`（NSD 组管理员 + COD 发起人）、`chenmo/pass123`（成员）。

## 一键部署到腾讯云
见 **《腾讯云部署指南.md》**。核心：填好 `.env` → `bash deploy/deploy.sh`。

## 测试（验收单测）
```bash
cd backend && python -m pytest tests/ -q
```
覆盖：三级权限、非成员下载拦截、版本不可覆盖、只读沙箱禁写、核验不改数据、评分制审核全链路+贡献加权、公约门禁、总管理员隐私边界。

## 已实现（对应文档模块）
三级权限(super/group/dataset)与判定顺序、课题组创建/发现/加入审批、数据集发起(联系方式必填)/版本发布(不可覆盖)/下载分级、双勘误评分制审核(成员+AI 评分→管理员终审→贡献按终审分加权)、数据核验专栏(flag→勘误草稿不改数据)、看板(派生汇总出图+只读沙箱)、研究广场发帖(可见性三级)+评论/点赞、公开项目 + 项目工作台完整CRUD(进展/待办/讨论/Overleaf)、Skill 共享、个人简历块级编辑、文献/刊物、公约版本化+进入门禁、三级管理后台+全员贡献总览、审计中间件、双语 zh/en、storage/ai_client 双实现、Docker 一键部署。

## 待团队定 / 二期
贡献度各分项权重数值（现用文档建议值：发起+30/代码+20/评审+3/勘误按终审分）、AI provider 生产化、看板实时计算引擎、跨集联查、平台名与 slogan 最终确定。
