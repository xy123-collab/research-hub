"""删除/注销规则回归：权限、二次确认、责任交接与公共记录保留。"""


def _register(client, username: str):
    password = "pass123"
    r = client.post("/api/auth/register", json={
        "username": username, "password": password,
        "email": f"{username}@example.com", "display_name": username,
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, password


def test_account_deactivation_keeps_comments_but_can_delete_own_posts(client, founder):
    headers, password = _register(client, "deactivate_rules_user")
    host = client.post("/api/posts", json={
        "content_zh": "他人的帖子", "post_type": "discussion", "scope": "public",
    }, headers=founder)
    assert host.status_code == 200, host.text
    host_id = host.json()["id"]
    comment = client.post(f"/api/posts/{host_id}/comments",
                          json={"content": "这条评论应保留"}, headers=headers)
    assert comment.status_code == 200, comment.text
    own = client.post("/api/posts", json={
        "content_zh": "我的帖子可选删除", "post_type": "discussion", "scope": "public",
    }, headers=headers)
    assert own.status_code == 200, own.text
    own_id = own.json()["id"]

    check = client.get("/api/me/deactivation-check", headers=headers)
    assert check.status_code == 200 and check.json()["eligible"] is True
    assert check.json()["own_posts"] == 1
    bad = client.post("/api/me/deactivate", json={
        "password": password, "confirmation": "确认", "delete_own_posts": True,
    }, headers=headers)
    assert bad.status_code == 400 and "注销账号" in bad.json()["detail"]

    done = client.post("/api/me/deactivate", json={
        "password": password, "confirmation": "注销账号", "delete_own_posts": True,
    }, headers=headers)
    assert done.status_code == 200, done.text
    assert client.post("/api/auth/login", json={
        "username": "deactivate_rules_user", "password": password,
    }).status_code == 401

    from app.core.db import SessionLocal
    from app.models.community import Post, PostComment
    from app.models.user import User
    db = SessionLocal()
    try:
        assert db.get(Post, own_id) is None
        kept = db.get(PostComment, comment.json()["id"])
        assert kept is not None and kept.content == "这条评论应保留"
        user = db.query(User).filter_by(id=kept.user_id).first()
        assert user.status == "left" and user.email is None
        assert user.display_name.startswith("已注销用户")
    finally:
        db.close()


def test_lead_must_transfer_before_deactivation_and_dataset_delete_needs_name(client):
    headers, password = _register(client, "dataset_delete_lead")
    created = client.post("/api/datasets", json={
        "name_zh": "待删除数据集", "desc_zh": "test",
    }, headers=headers)
    assert created.status_code == 200, created.text
    slug = created.json()["slug"]
    check = client.get("/api/me/deactivation-check", headers=headers).json()
    assert check["eligible"] is False
    assert any(b["type"] == "dataset" and b["slug"] == slug for b in check["blockers"])
    blocked = client.post("/api/me/deactivate", json={
        "password": password, "confirmation": "注销账号", "delete_own_posts": False,
    }, headers=headers)
    assert blocked.status_code == 409 and "未交接" in blocked.json()["detail"]["message"]

    assert client.patch(f"/api/datasets/{slug}", json={"is_public": False},
                        headers=headers).status_code == 200
    viewer, _ = _register(client, "private_dataset_viewer")
    hidden = client.get(f"/api/datasets/{slug}", headers=viewer)
    assert hidden.status_code == 403 and "仅已加入成员可见" in hidden.json()["detail"]
    assert slug not in {x["slug"] for x in client.get("/api/datasets", headers=viewer).json()}

    wrong = client.request("DELETE", f"/api/datasets/{slug}",
                           json={"confirmation": "错误名称"}, headers=headers)
    assert wrong.status_code == 400
    deleted = client.request("DELETE", f"/api/datasets/{slug}",
                             json={"confirmation": "待删除数据集"}, headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/api/datasets/{slug}", headers=headers).status_code == 404


def test_group_code_skill_and_section_controlled_deletion(client):
    headers, _ = _register(client, "controlled_delete_user")

    group = client.post("/api/groups", json={"name_zh": "可删空课题组"}, headers=headers)
    assert group.status_code == 200, group.text
    group_slug = group.json()["slug"]
    wrong_group = client.request("DELETE", f"/api/groups/{group_slug}",
                                 json={"confirmation": "x"}, headers=headers)
    assert wrong_group.status_code == 400
    assert client.request("DELETE", f"/api/groups/{group_slug}",
                          json={"confirmation": "可删空课题组"}, headers=headers).status_code == 200

    dataset = client.post("/api/datasets", json={"name_zh": "代码删除测试集"}, headers=headers)
    slug = dataset.json()["slug"]
    code = client.post(f"/api/datasets/{slug}/code", json={
        "filename": "clean.py", "lang": "Python", "title_zh": "数据清洗代码",
        "source_code": "print('ok')",
    }, headers=headers)
    assert code.status_code == 200, code.text
    cid = code.json()["id"]
    assert client.request("DELETE", f"/api/code/{cid}",
                          json={"confirmation": "数据清洗代码"}, headers=headers).status_code == 200
    assert client.get(f"/api/code/{cid}", headers=headers).status_code == 404

    section = client.post("/api/collab/sections", json={"name_zh": "空协作分区"}, headers=headers)
    assert section.status_code == 200, section.text
    sid = section.json()["id"]
    assert client.request("DELETE", f"/api/collab/sections/{sid}",
                          json={"confirmation": "空协作分区"}, headers=headers).status_code == 200

    skill = client.post("/api/skills", data={
        "name_zh": "可删 Skill", "body_text": "workflow", "scope": "public",
    }, headers=headers)
    assert skill.status_code == 200, skill.text
    skill_id = skill.json()["id"]
    vis = client.patch(f"/api/skills/{skill_id}/visibility",
                       json={"scope": "self", "scope_ref_ids": []}, headers=headers)
    assert vis.status_code == 200, vis.text
    assert client.get(f"/api/skills/{skill_id}", headers=headers).json()["scope"] == "self"
    assert client.request("DELETE", f"/api/skills/{skill_id}",
                          json={"confirmation": "可删 Skill"}, headers=headers).status_code == 200
    assert client.get(f"/api/skills/{skill_id}", headers=headers).status_code == 404
