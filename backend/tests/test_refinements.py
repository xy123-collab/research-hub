"""本轮精修新功能的回归测试：
个人主页(编辑资料/简历批量/项目图片必填/置顶)、工作台时间轴、
其他协作(分区/skill 范围/评论/下载)、评论的评论、找回密码、消息分类、邮件 mock。
"""
import io


def _auth(client, u, p):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': u, 'password': p}).json()['access_token']}"}


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def test_register_requires_email(client):
    r = client.post("/api/auth/register", json={"username": "noemail", "password": "pass123"})
    assert r.status_code == 422
    r2 = client.post("/api/auth/register", json={"username": "hasemail", "password": "pass123",
                                                 "email": "he@x.com"})
    assert r2.status_code == 200


def test_forgot_and_reset_password(client):
    client.post("/api/auth/register", json={"username": "reset1", "password": "pass123",
                                            "email": "reset1@x.com"})
    assert client.post("/api/auth/forgot-password", json={"email": "reset1@x.com"}).status_code == 200
    # 取出 mock 邮件里的 token
    from app.core.db import SessionLocal
    from app.models.extras import PasswordResetToken
    db = SessionLocal()
    tk = db.query(PasswordResetToken).order_by(PasswordResetToken.id.desc()).first().token
    db.close()
    r = client.post("/api/auth/reset-password", json={"token": tk, "new_password": "newpass1"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"username": "reset1", "password": "newpass1"}).status_code == 200


def test_profile_extra_and_resume_bulk(client, founder):
    assert client.patch("/api/me", json={"research_direction": "IO", "keywords": "反垄断,平台"},
                        headers=founder).status_code == 200
    me = client.get("/api/me", headers=founder).json()
    got = client.get(f"/api/users/{me['id']}", headers=founder).json()
    assert got["research_direction"] == "IO" and "平台" in got["keywords"]
    assert client.put("/api/me/resume/blocks",
                      json={"blocks": [{"type": "h", "text_zh": "教育"},
                                       {"type": "p", "text_zh": "北大"}]},
                      headers=founder).status_code == 200
    assert len(client.get(f"/api/users/{me['id']}/resume", headers=founder).json()["blocks"]) == 2


def test_project_image_required_and_pin(client, founder):
    r = client.post("/api/projects", data={"title": "P", "body_zh": "x"}, headers=founder)
    assert r.status_code == 422   # 缺图片
    r2 = client.post("/api/projects", data={"title": "P", "body_zh": "内容", "pinned": "true"},
                     files={"image": ("c.png", PNG, "image/png")}, headers=founder)
    assert r2.status_code == 200
    pid = r2.json()["id"]
    lst = client.get("/api/projects", params={"author_id": client.get('/api/me', headers=founder).json()['id']}, headers=founder).json()
    assert any(p["id"] == pid and p["pinned"] and p["image_url"] for p in lst)
    assert client.post(f"/api/projects/{pid}/pin", params={"pinned": False}, headers=founder).status_code == 200


def test_workspace_timeline_entries(client, founder):
    wid = client.post("/api/workspaces", json={"title": "WS", "member_ids": []}, headers=founder).json()["id"]
    e = client.post(f"/api/workspaces/{wid}/entries",
                    data={"category": "figure", "title": "图", "body": "说明"},
                    files={"file": ("f.png", PNG, "image/png")}, headers=founder)
    assert e.status_code == 200
    ws = client.get(f"/api/workspaces/{wid}", headers=founder).json()
    assert len(ws["entries"]) == 1 and ws["entries"][0]["is_image"]
    eid = ws["entries"][0]["id"]
    assert client.delete(f"/api/workspaces/{wid}/entries/{eid}", headers=founder).status_code == 200


def test_user_search(client, founder):
    r = client.get("/api/users/search", params={"q": "李"}, headers=founder)
    assert r.status_code == 200


def test_collab_sections_and_skill_flow(client, founder, member):
    secs = client.get("/api/collab/sections", headers=founder).json()
    assert any(s["key"] == "skill" for s in secs)
    assert client.post("/api/collab/sections", json={"name_zh": "数据清洗协作"}, headers=founder).status_code == 200
    # 发起 public skill 带文件
    rs = client.post("/api/skills",
                     data={"name_zh": "清洗脚本", "desc_zh": "d", "scope": "public", "body_text": "正文"},
                     files={"file": ("s.txt", b"code", "text/plain")}, headers=founder)
    assert rs.status_code == 200
    sid = rs.json()["id"]
    assert client.get(f"/api/skills/{sid}/download", headers=member).status_code == 200
    assert client.post(f"/api/skills/{sid}/comments", json={"content": "赞"}, headers=member).status_code == 200
    cid = client.get(f"/api/skills/{sid}/comments", headers=member).json()[0]["id"]
    assert client.post(f"/api/skills/{sid}/comments", json={"content": "回复", "parent_id": cid}, headers=founder).status_code == 200


def test_skill_scope_self_hidden(client, founder, member):
    rs = client.post("/api/skills", data={"name_zh": "私密", "scope": "self", "body_text": "x"}, headers=founder)
    sid = rs.json()["id"]
    ids = [s["id"] for s in client.get("/api/skills", headers=member).json()]
    assert sid not in ids   # 仅自己可见
    assert sid in [s["id"] for s in client.get("/api/skills", headers=founder).json()]


def test_post_comment_reply(client, founder):
    pid = client.post("/api/posts", json={"content_zh": "hi", "visibility": "platform", "tags": []}, headers=founder).json()["id"]
    c1 = client.post(f"/api/posts/{pid}/comments", json={"content": "一级"}, headers=founder).json()["id"]
    assert client.post(f"/api/posts/{pid}/comments", json={"content": "二级", "parent_id": c1}, headers=founder).status_code == 200
    cs = client.get(f"/api/posts/{pid}/comments", headers=founder).json()
    assert any(c["parent_id"] == c1 for c in cs)


def test_notifications_categorized(client, founder):
    r = client.get("/api/notifications", headers=founder)
    assert r.status_code == 200
    body = r.json()
    assert "groups" in body and "category_meta" in body


def test_digest_mock_run(client):
    from app.services.digest import run_digest_once
    out = run_digest_once()
    assert set(out.keys()) == {"scanned", "sent", "skipped"}
