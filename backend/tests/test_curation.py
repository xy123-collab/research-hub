"""本轮：数据分类/脱敏、批量勘误+逐条终审+应用到数据、代码版本 验收单测。"""
import io


def _uid(username):
    from app.core.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    u = db.query(User).filter_by(username=username).first()
    uid = u.id; db.close()
    return uid


def _make_stata(records) -> bytes:
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame(records).to_stata(buf, write_index=False, version=118)
    return buf.getvalue()


def test_data_config_and_unique_id(client, founder):
    # 设置唯一ID变量
    r = client.put("/api/datasets/cod/data-config",
                   json={"unique_id_var": "officerID"}, headers=founder)
    assert r.status_code == 200
    d = client.get("/api/datasets/cod", headers=founder).json()
    assert d["unique_id_var"] == "officerID"


def test_bug_template_downloads_xlsx(client, member):
    r = client.get("/api/datasets/cod/bug-template", headers=member)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"   # xlsx=zip


def test_batch_correction_integrates_items_and_per_item_finalize(client, founder, member):
    # 批量提交 CSV → 集成为一条含多子项的勘误
    csv = ("唯一ID值,变量名,当前值,建议值,说明与证据\n"
           "O1,begin_yr,1999,1998,年份笔误\n"
           "O2,gender,1,0,性别录错\n").encode("utf-8")
    files = {"file": ("batch.csv", io.BytesIO(csv), "text/csv")}
    r = client.post("/api/datasets/cod/bugs/batch", data={"title": "批量A"},
                    files=files, headers=member)
    assert r.status_code == 200 and r.json()["items"] == 2
    bid = r.json()["id"]
    detail = client.get(f"/api/bugs/{bid}", headers=member).json()
    assert len(detail["items"]) == 2
    it0 = detail["items"][0]["id"]
    # 逐条终审（管理员）
    fin = client.post(f"/api/bug-items/{it0}/finalize",
                      json={"adopt_level": "full", "final_score": 8}, headers=founder)
    assert fin.status_code == 200 and fin.json()["status"] == "accepted"


def test_apply_corrections_writes_new_version(client, founder, member):
    # 造一个带 officerID 的原始版本
    data = _make_stata([{"officerID": "A1", "begin_yr": 1999},
                        {"officerID": "A2", "begin_yr": 2000}])
    files = {"data_file": ("v.dta", io.BytesIO(data), "application/octet-stream")}
    pub = client.post("/api/datasets/cod/versions",
                      data={"version_id": "vA.1", "data_kind": "raw"},
                      files=files, headers=founder)
    assert pub.status_code == 200
    base_id = pub.json()["id"]
    # 设唯一ID
    client.put("/api/datasets/cod/data-config", json={"unique_id_var": "officerID"}, headers=founder)
    # 批量勘误一条并终审采纳
    csv = "唯一ID值,变量名,当前值,建议值,说明与证据\nA1,begin_yr,1999,1998,改年份\n".encode("utf-8")
    files = {"file": ("b.csv", io.BytesIO(csv), "text/csv")}
    bid = client.post("/api/datasets/cod/bugs/batch", files=files, headers=member).json()["id"]
    it = client.get(f"/api/bugs/{bid}", headers=member).json()["items"][0]["id"]
    client.post(f"/api/bug-items/{it}/finalize",
                json={"adopt_level": "full", "final_score": 9}, headers=founder)
    # 一键应用到数据 → 生成新版本
    r = client.post("/api/datasets/cod/apply-corrections",
                    data={"base_version_id": base_id, "new_version_id": "vA.2",
                          "changelog_zh": "应用勘误"}, headers=founder)
    assert r.status_code == 200 and r.json()["generated"] == "server"
    assert r.json()["applied"] == 1


def test_sample_version_public_download(client, founder, outsider):
    # 发布样例版本（公开可下）
    data = _make_stata([{"officerID": "S1", "x": 1}])
    files = {"data_file": ("s.dta", io.BytesIO(data), "application/octet-stream")}
    pub = client.post("/api/datasets/cod/versions",
                      data={"version_id": "sample.1", "data_kind": "sample"},
                      files=files, headers=founder)
    assert pub.status_code == 200
    vid = pub.json()["id"]
    # 非成员也能下样例数据
    r = client.get(f"/api/datasets/cod/versions/{vid}/download?file=data", headers=outsider)
    assert r.status_code == 200


def test_desensitize_generates_masked_version(client, founder):
    data = _make_stata([{"officerID": "D1", "salary": 100, "name": "张三"},
                        {"officerID": "D2", "salary": 200, "name": "李四"}])
    files = {"data_file": ("r.dta", io.BytesIO(data), "application/octet-stream")}
    base = client.post("/api/datasets/cod/versions",
                       data={"version_id": "raw.9", "data_kind": "raw"},
                       files=files, headers=founder).json()["id"]
    # 规则：name 删除、salary 分桶
    client.put("/api/datasets/cod/data-config", json={"unique_id_var": "officerID",
        "rules": [{"var_name": "name", "mask_action": "drop"},
                  {"var_name": "salary", "mask_action": "bucket", "bucket_size": 100}]},
        headers=founder)
    r = client.post(f"/api/datasets/cod/versions/{base}/desensitize",
                    data={"new_version_id": "masked.9"}, headers=founder)
    assert r.status_code == 200 and r.json()["generated"] == "server"


def test_code_version_permission_and_comment(client, founder, member):
    # 成员建代码 → 作者发新版本 → 评论
    cid = client.post("/api/datasets/cod/code",
                      json={"filename": "clean.py", "lang": "Python", "title_zh": "清洗",
                            "source_code": "print(1)"}, headers=member).json()["id"]
    # 作者(member)发布新版本，需写 changelog
    r = client.post(f"/api/code/{cid}/versions",
                    data={"version_label": "v2", "changelog": "修复缺失值处理",
                          "source_code": "print(2)"}, headers=member)
    assert r.status_code == 200
    # 非作者非管理员无重发权限
    info = client.get(f"/api/code/{cid}", headers=founder).json()
    assert info["can_publish"] is True   # founder 是数据集管理员
    # 评论（勘误类）
    cm = client.post(f"/api/code/{cid}/comments",
                     data={"content": "第3行有bug", "is_correction": True}, headers=founder)
    assert cm.status_code == 200
    comments = client.get(f"/api/code/{cid}/comments", headers=member).json()
    assert any(c["is_correction"] for c in comments)
