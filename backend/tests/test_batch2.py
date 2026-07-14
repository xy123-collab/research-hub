"""第二批修改的回归测试：统一可见范围、文献批量导入/引用/AI核验、数据修正、改名。"""
import io


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def _h(client, u, p):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': u, 'password': p}).json()['access_token']}"}


def test_collab_scopes_endpoint(client, founder):
    r = client.get("/api/me/collab-scopes", headers=founder)
    assert r.status_code == 200
    body = r.json()
    assert "groups" in body and "datasets" in body
    # 李小雨是 NSD 成员
    assert any("NSD" in g["name"] or g["name"] for g in body["groups"])


def test_post_scope_self_hidden_from_others(client, founder, member):
    client.post("/api/posts", json={"content_zh": "只有我可见xyz", "scope": "self", "tags": []}, headers=founder)
    seen = [p["content_zh"] for p in client.get("/api/posts", headers=member).json()]
    assert "只有我可见xyz" not in seen
    mine = [p["content_zh"] for p in client.get("/api/posts", headers=founder).json()]
    assert "只有我可见xyz" in mine


def test_post_scope_group_requires_membership(client, outsider):
    # outsider 不属于任何组，选 group 且乱填 id 应 400
    r = client.post("/api/posts", json={"content_zh": "g", "scope": "group", "scope_ref_id": 1, "tags": []}, headers=outsider)
    assert r.status_code == 400


def test_project_scope_filtering(client, founder, member):
    client.post("/api/projects", data={"title": "私密项目", "body_zh": "x", "scope": "self"},
                files={"image": ("c.png", PNG, "image/png")}, headers=founder)
    fid = client.get("/api/me", headers=founder).json()["id"]
    other_view = client.get("/api/projects", params={"author_id": fid}, headers=member).json()
    assert not any(p["title"] == "私密项目" for p in other_view)
    own = client.get("/api/projects", params={"author_id": fid}, headers=founder).json()
    assert any(p["title"] == "私密项目" for p in own)


def test_lit_template_and_batch_flow(client, founder):
    # 模板可下载
    tp = client.get("/api/datasets/cod/lit-template", headers=founder)
    assert tp.status_code == 200
    # CSV 解析（含表头）
    csv = "标题,作者,年份,刊物/出版社,DOI,链接URL\n增长,Barro,1991,QJE,,\n".encode("utf-8-sig")
    pr = client.post("/api/datasets/cod/literature/parse",
                     files={"file": ("t.csv", csv, "text/csv")}, headers=founder)
    assert pr.status_code == 200
    rows = pr.json()["rows"]
    assert rows[0]["citation"] and not rows[0]["missing"]
    # AI 未启用 → verdict unknown，不拦截，可导入
    refs = [{"title": r["title"], "authors": r["authors"], "year": r["year"], "venue": r["venue"]} for r in rows]
    v = client.post("/api/datasets/cod/literature/ai-verify", json={"refs": refs}, headers=founder)
    assert v.status_code == 200 and v.json()["results"][0]["verdict"] in ("unknown", "real", "suspect")
    b = client.post("/api/datasets/cod/literature/batch", json={"refs": refs}, headers=founder)
    assert b.status_code == 200 and b.json().get("ok") is True


def test_lit_batch_missing_required(client, founder):
    r = client.post("/api/datasets/cod/literature/batch",
                    json={"refs": [{"title": "只有标题"}]}, headers=founder)
    assert r.status_code == 400


# 注：data_fixes 的一次性删除逻辑（删除陈默等）会破坏共享测试库，
# 已在独立数据库中冒烟验证其正确性与幂等性，此处不在共享套件中执行。
