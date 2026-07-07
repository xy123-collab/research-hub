# Render 免费部署指南（一键 Blueprint）

用 Render 免费托管平台测试本平台。**免信用卡**，单服务形态（后端容器同时托管前端，前后端同源，无需 CORS/反代）。已为你准备好 `render.yaml`，连上 GitHub 一键起。

---

## 需要你提供
- 一个 **GitHub 账号**（把本项目推上去）。
- 一个 **Render 账号**（render.com，用 GitHub 登录即可，免信用卡）。
- 其它都不用 —— 数据库、JWT 密钥由 `render.yaml` 自动创建/生成。

---

## 步骤（约 5 分钟操作 + 几分钟构建）

### 1. 把项目推到 GitHub
在项目根目录（含 `backend/ frontend/ deploy/ render.yaml`）：
```bash
git init
git add .
git commit -m "research hub"
git branch -M main
git remote add origin https://github.com/<你的用户名>/research-hub.git
git push -u origin main
```

### 2. 在 Render 用 Blueprint 一键部署
1. 登录 render.com → 右上 **New +** → **Blueprint**。
2. 选择刚推上去的仓库 → Render 自动读取 `render.yaml`。
3. 点 **Apply**。它会自动创建：
   - 一个免费 **PostgreSQL** 数据库（`research-hub-db`）
   - 一个免费 **Web 服务**（`research-hub`，Docker 构建，后端 + 前端）
   - 自动注入 `DATABASE_URL`、自动生成 `JWT_SECRET`
4. 等构建完成（首次约 5–10 分钟，含前端构建 + 装依赖）。

### 3. 访问
- 打开 Render 给的地址：`https://research-hub-xxxx.onrender.com/`
- 首次启动会自动跑迁移 + 灌 seed 假数据。
- 登录：`admin/admin123`、`lixiaoyu/pass123`（NSD 组管理员 / COD 发起人）、`chenmo/pass123`。
- 健康检查：`https://research-hub-xxxx.onrender.com/api/health`

---

## 免费档要知道的三个限制（测试无妨）
1. **闲置休眠**：15 分钟没人访问后端会休眠，下次访问冷启动约 1 分钟（首屏会转一会）。
2. **免费 PostgreSQL 30 天到期**：到期前 Render 会提醒，可导出数据或升级。做演示够用；想长期免费可换 **Neon** 永久免费 PG（把 `render.yaml` 里 `databases` 段删掉，改用 Neon 的连接串填到 Web 服务的 `DATABASE_URL` 环境变量）。
3. **磁盘不持久**：免费档无持久盘，`STORAGE_BACKEND=local`，**上传的文件（数据版本 .dta/附件）在重启后会清空**；但账号、勘误、贡献等都在 PostgreSQL 里，会保留。纯功能演示不受影响。

---

## 上线后建议
- 改掉 seed 弱密码，或把 Web 服务环境变量 `SEED_ON_START` 设 `false` 后清库重灌真实账号。
- 演示给别人看时，先自己访问一下"唤醒"服务，避免对方等冷启动。

---

## 想换 Neon 永久免费数据库（可选）
1. neon.tech 注册（免费），建一个 Project，复制它的 **connection string**（`postgresql://...`）。
2. 在 `render.yaml` 删掉 `databases:` 整段；把 Web 服务的 `DATABASE_URL` 从 `fromDatabase` 改成 `sync: false`（部署后到 Render 面板手填 Neon 连接串）。
3. 我可以帮你改好 `render.yaml`，说一声即可。

> 备注：`render.yaml`、`deploy/Dockerfile.render` 已就绪；后端已支持"有前端产物就同源托管"，并自动兼容 Render 的 `postgres://` 连接串。
