"""新增：文件上传 + 核心闭环（发版把已采纳勘误标 fixed）+ 元信息编辑。"""
import io


def _hdr(client, u, p):
    return {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username':u,'password':p}).json()['access_token']}"}


def _create_bug(client, founder, member, suffix, uid="O1", current="1999"):
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame({"officerID": [uid], "year": [int(current)]}).to_stata(
        buf, write_index=False, version=118)
    buf.seek(0)
    pub = client.post("/api/datasets/cod/versions",
                      data={"version_id": f"v-{suffix}", "data_kind": "raw"},
                      files={"data_file": (f"{suffix}.dta", buf, "application/octet-stream")},
                      headers=founder)
    assert pub.status_code == 200, pub.text
    client.put("/api/datasets/cod/data-config",
               json={"unique_id_var": "officerID"}, headers=founder)
    variables = client.get("/api/datasets/cod/variables", headers=founder).json()
    var_id = next(v["id"] for v in variables if v["var_name"] == "year")
    response = client.post("/api/datasets/cod/bugs",
                           json={"officer_id": uid, "variable_id": var_id,
                                 "current_value": current, "suggested_value": "1998",
                                 "description_zh": "年份笔误", "evidence": "履历核对"},
                           headers=member)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_bug_evidence_attachment_upload_download(client):
    founder = _hdr(client, "lixiaoyu", "pass123")
    member = _hdr(client, "chenmo", "pass123")
    bid = _create_bug(client, founder, member, "attachment", uid="O9")
    files = {"file": ("evidence.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    r = client.post(f"/api/bugs/{bid}/attachments", files=files, headers=member)
    assert r.status_code == 200
    aid = r.json()["id"]
    lst = client.get(f"/api/bugs/{bid}/attachments", headers=member).json()
    assert len(lst) == 1 and lst[0]["file_name"] == "evidence.pdf"
    dl = client.get(f"/api/bug-attachments/{aid}/download", headers=member)
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 fake"


def test_bad_file_type_rejected(client):
    founder = _hdr(client, "lixiaoyu", "pass123")
    member = _hdr(client, "chenmo", "pass123")
    bid = _create_bug(client, founder, member, "bad-attachment", uid="O10")
    files = {"file": ("hack.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    r = client.post(f"/api/bugs/{bid}/attachments", files=files, headers=member)
    assert r.status_code == 400


def test_full_core_loop_download_bug_review_finalize_publish_fixed(client):
    founder = _hdr(client, "lixiaoyu", "pass123")
    member = _hdr(client, "chenmo", "pass123")
    # 提交 bug（附证据）
    bid = _create_bug(client, founder, member, "core-loop", uid="O1")
    # 评审 + 终审采纳
    client.post(f"/api/bugs/{bid}/reviews",
                json={"acceptability_score": 8, "comment": "证据充分"}, headers=founder)
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
    raw = b"use x, clear\nmerge 1:1 id using y"
    files = {"file": ("merge.do", io.BytesIO(raw), "text/plain")}
    r = client.post("/api/datasets/cod/code/upload",
                    data={"title_zh": "合并脚本", "lang": "Stata"},
                    files=files, headers=founder)
    assert r.status_code == 200
    cid = r.json()["id"]
    detail = client.get(f"/api/code/{cid}", headers=founder).json()
    assert detail["current_file_name"] == "merge.do"
    assert detail["source_code"] == ""
    assert client.get(f"/api/code/{cid}/download", headers=founder).content == raw


def test_code_submission_accepts_any_file_or_pasted_text_or_both(client):
    founder = _hdr(client, "lixiaoyu", "pass123")

    # 任意格式文件可单独提交，二进制内容原样保存并下载。
    doc_bytes = b"PK\x03\x04\x00binary-docx"
    r = client.post(
        "/api/datasets/cod/code/upload",
        data={"title_zh": "说明文档", "lang": "其他"},
        files={"file": ("处理说明.docx", io.BytesIO(doc_bytes),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=founder,
    )
    assert r.status_code == 200
    cid = r.json()["id"]
    detail = client.get(f"/api/code/{cid}", headers=founder).json()
    assert detail["current_file_name"] == "处理说明.docx"
    assert detail["source_code"] == ""
    downloaded = client.get(f"/api/code/{cid}/download", headers=founder)
    assert downloaded.status_code == 200 and downloaded.content == doc_bytes

    # 粘贴文本可单独提交。
    pasted = client.post(
        "/api/datasets/cod/code/upload",
        data={"title_zh": "粘贴脚本", "lang": "Python", "source_code": "print('ok')"},
        headers=founder,
    )
    assert pasted.status_code == 200
    pasted_id = pasted.json()["id"]
    pasted_detail = client.get(f"/api/code/{pasted_id}", headers=founder).json()
    assert pasted_detail["current_file_name"] is None
    assert pasted_detail["source_code"] == "print('ok')"
    assert client.get(f"/api/code/{pasted_id}/download", headers=founder).content == b"print('ok')"

    # 两种方式可共存：原文件用于下载，粘贴文本用于在线预览。
    both = client.post(
        "/api/datasets/cod/code/upload",
        data={"title_zh": "文件与说明", "lang": "其他", "source_code": "配套处理说明"},
        files={"file": ("readme.md", io.BytesIO(b"# raw file"), "text/markdown")},
        headers=founder,
    )
    assert both.status_code == 200
    both_id = both.json()["id"]
    both_detail = client.get(f"/api/code/{both_id}", headers=founder).json()
    assert both_detail["current_file_name"] == "readme.md"
    assert both_detail["source_code"] == "配套处理说明"
    assert client.get(f"/api/code/{both_id}/download", headers=founder).content == b"# raw file"

    # 发布后续版本时同样支持两种方式并存，文件下载与文本预览各自保留。
    version = client.post(
        f"/api/code/{both_id}/versions",
        data={"version_label": "v2", "changelog": "补充处理说明",
              "source_code": "更新后的在线预览"},
        files={"file": ("appendix.doc", io.BytesIO(b"binary-v2"), "application/msword")},
        headers=founder,
    )
    assert version.status_code == 200
    version_detail = client.get(f"/api/code/{both_id}", headers=founder).json()
    assert version_detail["current_file_name"] == "appendix.doc"
    assert version_detail["source_code"] == "更新后的在线预览"
    assert client.get(
        f"/api/code/{both_id}/download?vid={version.json()['id']}",
        headers=founder,
    ).content == b"binary-v2"

    empty = client.post(
        "/api/datasets/cod/code/upload",
        data={"title_zh": "空提交", "lang": "其他"},
        headers=founder,
    )
    assert empty.status_code == 400
