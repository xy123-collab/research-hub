"""新增：文件上传 + 核心闭环（发版把已采纳勘误标 fixed）+ 元信息编辑。"""
import io


def _hdr(client, u, p):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username':u,'password':p}).json()['access_token']}"}


def test_bug_evidence_attachment_upload_download(client):
    founder = _hdr(client, "lixiaoyu", "pass123")
    member = _hdr(client, "chenmo", "pass123")
    bid = client.post("/api/datasets/cod/bugs",
                      json={"officer_id": "O9", "description_zh": "带证据的勘误"},
                      headers=member).json()["id"]
    files = {"file": ("evidence.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    r = client.post(f"/api/bugs/{bid}/attachments", files=files, headers=member)
    assert r.status_code == 200
    aid = r.json()["id"]
    lst = client.get(f"/api/bugs/{bid}/attachments", headers=member).json()
    assert len(lst) == 1 and lst[0]["file_name"] == "evidence.pdf"
    dl = client.get(f"/api/bug-attachments/{aid}/download", headers=member)
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 fake"


def test_bad_file_type_rejected(client):
    member = _hdr(client, "chenmo", "pass123")
    bid = client.post("/api/datasets/cod/bugs", json={"description_zh": "x"}, headers=member).json()["id"]
    files = {"file": ("hack.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    r = client.post(f"/api/bugs/{bid}/attachments", files=files, headers=member)
    assert r.status_code == 400


def test_full_core_loop_download_bug_review_finalize_publish_fixed(client):
    founder = _hdr(client, "lixiaoyu", "pass123")
    member = _hdr(client, "chenmo", "pass123")
    # 提交 bug（附证据）
    bid = client.post("/api/datasets/cod/bugs",
                      json={"officer_id": "O1", "current_value": "1999",
                            "suggested_value": "1998", "description_zh": "年份笔误"},
                      headers=member).json()["id"]
    # 评审 + 终审采纳
    client.post(f"/api/bugs/{bid}/reviews", json={"acceptability_score": 8}, headers=founder)
    client.post(f"/api/bugs/{bid}/finalize",
                json={"adopt_level": "full", "final_score": 9}, headers=founder)
    assert client.get(f"/api/bugs/{bid}", headers=member).json()["status"] == "accepted"
    # 发布新版本并把该 bug 标 fixed
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame({"officerID": ["O1"], "year": [1998]}).to_stata(
        buf, write_index=False, version=118)
    buf.seek(0)
    files = {"data_file": ("cod.dta", buf, "application/octet-stream")}
    r = client.post("/api/datasets/cod/versions",
                    data={"version_id": "v1.2.0", "fixed_bug_ids": str(bid),
                          "changelog_zh": "修复年份笔误"},
                    files=files, headers=founder)
    assert r.status_code == 200 and bid in r.json()["fixed_bugs"]
    detail = client.get(f"/api/bugs/{bid}", headers=member).json()
    assert detail["status"] == "fixed" and detail["fixed_in_version"] == "v1.2.0"
    # 旧版本仍保留（列表里 v1.0.0 还在）
    vlist = [v["version_id"] for v in client.get("/api/datasets/cod/versions", headers=member).json()]
    assert "v1.0.0" in vlist and "v1.2.0" in vlist


def test_dataset_meta_edit_and_member_remove(client):
    founder = _hdr(client, "lixiaoyu", "pass123")
    assert client.patch("/api/datasets/cod", json={"desc_zh": "更新后的简介"},
                        headers=founder).status_code == 200
    assert client.get("/api/datasets/cod", headers=founder).json()["desc_zh"] == "更新后的简介"


def test_code_file_upload(client):
    founder = _hdr(client, "lixiaoyu", "pass123")
    files = {"file": ("merge.do", io.BytesIO(b"use x, clear\nmerge 1:1 id using y"), "text/plain")}
    r = client.post("/api/datasets/cod/code/upload",
                    data={"title_zh": "合并脚本", "lang": "Stata"},
                    files=files, headers=founder)
    assert r.status_code == 200
    cid = r.json()["id"]
    assert "merge 1:1" in client.get(f"/api/code/{cid}", headers=founder).json()["source_code"]
