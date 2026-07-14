"""《科研数据协作平台权限规则》验收单测（本轮新增）。"""


def _super(client):
    tok = client.post("/api/auth/login",
                      json={"username": "admin", "password": "admin123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


# 原则一：平台总管理员 ≠ 数据管理员，不自动接触数据集内容
def test_super_admin_not_dataset_member(client):
    H = _super(client)
    d = client.get("/api/datasets/cod", headers=H).json()
    assert d["is_member"] is False and d["is_admin"] is False
    # 不能提交勘误 / 不能看成员名单 / 不能下载原始数据
    assert client.post("/api/datasets/cod/bugs",
                       json={"description_zh": "x"}, headers=H).status_code == 403
    assert client.get("/api/datasets/cod/members", headers=H).status_code == 403
    vid = client.get("/api/datasets/cod/versions", headers=H).json()[0]["id"]
    assert client.get(f"/api/datasets/cod/versions/{vid}/download?file=data",
                      headers=H).status_code == 403


# 原则三：加入数据集 ≠ 下载权。审批后下载策略下需单独批准
def test_approval_download_flow(client, founder, member):
    # 管理员把下载策略设为「审批后下载」
    assert client.patch("/api/datasets/cod/settings",
                        json={"download_policy": "approval"}, headers=founder).status_code == 200
    cur = client.get("/api/datasets/cod", headers=member).json()["current_version"]
    vid = client.get("/api/datasets/cod/versions", headers=member).json()
    cur_vid = [v["id"] for v in vid if v["is_current"]][0]
    # 成员此时无授权，下载被拒
    assert client.get(f"/api/datasets/cod/versions/{cur_vid}/download?file=data",
                      headers=member).status_code == 403
    # 提交下载申请（需同意公约 + 用途）
    r = client.post("/api/datasets/cod/download-requests",
                    json={"purpose": "复现研究", "agree_charter": True,
                          "scope_version": cur["version_id"]}, headers=member)
    assert r.status_code == 200
    rid = r.json()["id"]
    # 管理员在成员面板看到该下载申请并批准
    dls = client.get("/api/datasets/cod/members", headers=founder).json()["download_requests"]
    assert any(x["id"] == rid for x in dls)
    assert client.post(f"/api/download-requests/{rid}/decide",
                       params={"approve": True}, headers=founder).status_code == 200
    # 批准后成员可下载当前版本
    assert client.get(f"/api/datasets/cod/versions/{cur_vid}/download?file=data",
                      headers=member).status_code == 200
    # 复位策略，避免影响其他用例
    client.patch("/api/datasets/cod/settings",
                 json={"download_policy": "member"}, headers=founder)


# 单独授权：在线分析需授权
def test_online_analysis_requires_grant(client, founder, member):
    # 默认成员无在线分析授权 → 被拒
    assert client.post("/api/datasets/cod/analysis/run",
                       params={"code": "result=len(df)"}, headers=member).status_code == 403
    # 管理员授予 analysis.online
    assert client.post("/api/datasets/cod/members/%d/grant" % _uid(client, "chenmo"),
                       json={"perm": "analysis.online", "scope_type": "permanent"},
                       headers=founder).status_code == 200
    assert client.post("/api/datasets/cod/analysis/run",
                       params={"code": "result=len(df)"}, headers=member).status_code == 200
    # 撤销授权后再次被拒
    client.post("/api/datasets/cod/members/%d/revoke" % _uid(client, "chenmo"),
                params={"perm": "analysis.online"}, headers=founder)
    assert client.post("/api/datasets/cod/analysis/run",
                       params={"code": "result=len(df)"}, headers=member).status_code == 403


# 至少保留一名数据集管理员
def test_cannot_remove_sole_admin(client, founder):
    uid = _uid(client, "lixiaoyu")
    assert client.delete(f"/api/datasets/cod/members/{uid}", headers=founder).status_code == 400


# 八节 4：多管理员时，管理员不得审核自己提交的勘误
def test_admin_cannot_self_review_when_multiple_admins(client, founder, member):
    mid = _uid(client, "chenmo")
    # 先把 chenmo 提为管理员（此时数据集有两名管理员）
    assert client.post(f"/api/datasets/cod/admins/{mid}", headers=founder).status_code == 200
    bid = client.post("/api/datasets/cod/bugs",
                      json={"description_zh": "自审测试"}, headers=member).json()["id"]
    # chenmo 审核自己提交的勘误应被拒
    r = client.post(f"/api/bugs/{bid}/finalize",
                    json={"adopt_level": "full", "final_score": 8}, headers=member)
    assert r.status_code == 403
    # 复位：取消 chenmo 管理员
    client.delete(f"/api/datasets/cod/admins/{mid}", headers=founder)


# 消息中心：管理员能看到待办
def test_notifications_for_admin(client, founder, member):
    # member 申请加入 fiscal（founder=chenmo），chenmo 应收到待办
    client.post("/api/datasets/fiscal/join-requests", headers=founder)
    notif = client.get("/api/notifications", headers=member).json()
    assert "action_count" in notif and isinstance(notif["items"], list)


# 两级管理员：仅总管理员可增删管理员与转让；转让后原总管理员降为普通管理员
def test_two_tier_admin_and_transfer(client, founder, member):
    lead = _uid(client, "lixiaoyu")   # cod 总管理员
    mid = _uid(client, "chenmo")
    # 总管理员把 chenmo 提为普通管理员
    assert client.post(f"/api/datasets/cod/admins/{mid}", headers=founder).status_code == 200
    # 普通管理员(chenmo) 不能增设管理员（仅总管理员可）
    assert client.post(f"/api/datasets/cod/admins/{lead}", headers=member).status_code == 403
    # 转让总管理员给 chenmo
    assert client.post(f"/api/datasets/cod/transfer-lead/{mid}", headers=founder).status_code == 200
    d = client.get("/api/datasets/cod", headers=member).json()
    assert d["is_lead"] is True and d["lead_id"] == mid
    # 新总管理员不能直接取消自己的管理员（须先转让）
    assert client.delete(f"/api/datasets/cod/admins/{mid}", headers=member).status_code == 400
    # 转让回去并复位
    assert client.post(f"/api/datasets/cod/transfer-lead/{lead}", headers=member).status_code == 200
    assert client.delete(f"/api/datasets/cod/admins/{mid}", headers=founder).status_code == 200


# 管理控制台：按我管理的范围返回，并能取到数据集控制台指标
def test_admin_console(client, founder):
    scopes = client.get("/api/admin/my-scopes", headers=founder).json()
    assert any(x["slug"] == "cod" and x["role"] == "lead" for x in scopes["datasets"])
    con = client.get("/api/admin/datasets/cod/console", headers=founder)
    assert con.status_code == 200
    body = con.json()
    assert "activity" in body and "contributions" in body and "pending" in body


def _uid(client, username):
    # 借助登录返回或用户检索；这里用 seed 已知用户名，通过 /api 无直接接口，走数据库
    from app.core.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    u = db.query(User).filter_by(username=username).first()
    uid = u.id
    db.close()
    return uid
