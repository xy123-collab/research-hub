import io
import json


def _make_stata(records) -> bytes:
    import pandas as pd
    buf = io.BytesIO()
    pd.DataFrame(records).to_stata(buf, write_index=False, version=118)
    return buf.getvalue()


def _new_dataset(client, founder, slug: str, records: list[dict]):
    made = client.post("/api/datasets", json={
        "slug": slug, "name_zh": f"透明勘误测试-{slug}",
        "desc_zh": "用于勘误透明化验收",
    }, headers=founder)
    assert made.status_code == 200, made.text
    raw = _make_stata(records)
    published = client.post(
        f"/api/datasets/{slug}/versions",
        data={"version_id": "v1", "data_kind": "raw"},
        files={"data_file": ("base.dta", io.BytesIO(raw), "application/octet-stream")},
        headers=founder,
    )
    assert published.status_code == 200, published.text
    client.put(f"/api/datasets/{slug}/data-config",
               json={"unique_id_var": "officerID"}, headers=founder)
    variables = client.get(f"/api/datasets/{slug}/variables", headers=founder).json()
    return published.json()["id"], {
        item["var_name"]: item["id"] for item in variables
    }


def _submit(client, founder, slug, var_id, uid, old, new, confirm=False):
    return client.post(f"/api/datasets/{slug}/bugs", json={
        "officer_id": uid, "variable_id": var_id,
        "current_value": str(old), "suggested_value": str(new),
        "description_zh": "履历年份需要校正",
        "evidence": "组织部门公开履历，2026-07-20 核对",
        "confirm_new_officer": confirm,
    }, headers=founder)


def test_uid_confirmation_review_reason_and_list_metadata(client, founder):
    slug = "ds-correction-meta"
    _, variables = _new_dataset(
        client, founder, slug, [{"officerID": "A1", "year": 2001}])

    exists = client.get(f"/api/datasets/{slug}/bugs/id-check",
                        params={"value": " A1 "}, headers=founder)
    assert exists.status_code == 200 and exists.json()["exists"] is True
    missing = client.get(f"/api/datasets/{slug}/bugs/id-check",
                         params={"value": "NEW1"}, headers=founder)
    assert missing.status_code == 200 and missing.json()["exists"] is False

    blocked = _submit(client, founder, slug, variables["year"], "NEW1", "", 1990)
    assert blocked.status_code == 409
    added = _submit(
        client, founder, slug, variables["year"], "NEW1", "", 1990, confirm=True)
    assert added.status_code == 200
    detail = client.get(f"/api/bugs/{added.json()['id']}", headers=founder).json()
    assert detail["items"][0]["is_new_officer"] is True
    assert detail["items"][0]["evidence"].startswith("组织部门")

    regular = _submit(client, founder, slug, variables["year"], "A1", 2001, 2000)
    bid = regular.json()["id"]
    no_reason = client.post(f"/api/bugs/{bid}/reviews",
                            json={"acceptability_score": 7}, headers=founder)
    assert no_reason.status_code == 422
    for score in (7, 8):
        rated = client.post(f"/api/bugs/{bid}/reviews",
                            json={"acceptability_score": score,
                                  "comment": "证据与建议值一致"}, headers=founder)
        assert rated.status_code == 200
    row = next(item for item in client.get(
        f"/api/datasets/{slug}/bugs", headers=founder).json() if item["id"] == bid)
    assert row["reviewer_count"] == 1
    assert row["created_at"].endswith("+08:00")


def test_batch_validation_separates_evidence_and_marks_new_officer(client, founder):
    slug = "ds-correction-batch"
    _new_dataset(client, founder, slug, [{"officerID": "B1", "year": 2001}])
    csv = (
        "唯一ID值,变量名,当前值,建议值,说明,证据\n"
        "B1,year,2001,2000,年份有误,任免公告\n"
        "B2,year,,1998,新增官员任职年,官方简历\n"
    ).encode("utf-8")
    checked = client.post(
        f"/api/datasets/{slug}/bugs/batch/validate",
        files={"file": ("batch.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert checked.status_code == 200
    assert checked.json()["missing_uid_values"] == ["B2"]
    assert checked.json()["valid_rows"] == 2
    assert checked.json()["invalid_rows"] == 0
    assert checked.json()["problem_rows"] == 1

    blocked = client.post(
        f"/api/datasets/{slug}/bugs/batch",
        files={"file": ("batch.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert blocked.status_code == 409
    committed = client.post(
        f"/api/datasets/{slug}/bugs/batch",
        data={"confirmed_new_officer_ids": json.dumps(["B2"])},
        files={"file": ("batch.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert committed.status_code == 200
    assert len(committed.json()["ids"]) == 2
    details = [
        client.get(f"/api/bugs/{bid}", headers=founder).json()
        for bid in committed.json()["ids"]
    ]
    assert all(len(detail["items"]) == 1 for detail in details)
    assert [detail["items"][0]["is_new_officer"] for detail in details] == [False, True]

    old = "唯一ID值,变量名,当前值,建议值,说明与证据\nB1,year,2001,2000,旧模板\n"
    legacy = client.post(
        f"/api/datasets/{slug}/bugs/batch/validate",
        files={"file": ("old.csv", io.BytesIO(old.encode()), "text/csv")},
        headers=founder,
    )
    assert legacy.status_code == 400 and "旧版" in legacy.json()["detail"]


def test_alternative_id_requires_confirmation_and_supports_safe_apply(client, founder):
    slug = "ds-correction-alternative-id"
    base_id, variables = _new_dataset(client, founder, slug, [
        {"rowID": "R1", "officerID": "O1", "year": 2001},
        {"rowID": "R2", "officerID": "O2", "year": 2002},
        {"rowID": "R3", "officerID": "O3", "year": 2003},
    ])
    client.put(
        f"/api/datasets/{slug}/data-config",
        json={"unique_id_var": "rowID"}, headers=founder,
    )
    checked = client.get(
        f"/api/datasets/{slug}/bugs/id-check",
        params={"id_var": "officerID", "value": "O1"}, headers=founder,
    )
    assert checked.status_code == 200
    assert checked.json()["uses_alternative_id"] is True

    body = {
        "uid_var": "officerID", "officer_id": "O1",
        "variable_id": variables["year"], "current_value": "2001",
        "suggested_value": "2000", "description_zh": "年份有误",
        "evidence": "公开履历",
    }
    blocked = client.post(
        f"/api/datasets/{slug}/bugs", json=body, headers=founder)
    assert blocked.status_code == 409 and "不是管理员推荐" in blocked.json()["detail"]
    submitted = client.post(
        f"/api/datasets/{slug}/bugs",
        json={**body, "confirm_alternative_id": True}, headers=founder,
    )
    assert submitted.status_code == 200
    detail = client.get(
        f"/api/bugs/{submitted.json()['id']}", headers=founder).json()
    assert detail["items"][0]["uid_var"] == "officerID"
    assert detail["items"][0]["uses_alternative_id"] is True
    item_id = detail["items"][0]["id"]
    assert client.post(
        f"/api/bug-items/{item_id}/finalize",
        json={"adopt_level": "full", "final_score": 9}, headers=founder,
    ).status_code == 200
    recommended = client.post(
        f"/api/datasets/{slug}/bugs",
        json={
            "uid_var": "rowID", "officer_id": "R3",
            "variable_id": variables["year"], "current_value": "2003",
            "suggested_value": "2004", "description_zh": "另一行年份有误",
            "evidence": "公开履历",
        },
        headers=founder,
    )
    assert recommended.status_code == 200
    recommended_item = client.get(
        f"/api/bugs/{recommended.json()['id']}", headers=founder
    ).json()["items"][0]["id"]
    assert client.post(
        f"/api/bug-items/{recommended_item}/finalize",
        json={"adopt_level": "full", "final_score": 9}, headers=founder,
    ).status_code == 200
    preview = client.get(
        f"/api/datasets/{slug}/corrections-release-preview",
        params={"base_version_id": base_id}, headers=founder,
    )
    assert preview.status_code == 200
    assert preview.json()["auto_count"] == 2
    assert preview.json()["manual_count"] == 0
    assert "定位：officerID=O1" in preview.json()["script"]
    assert "定位：rowID=R3" in preview.json()["script"]
    applied = client.post(
        f"/api/datasets/{slug}/apply-corrections",
        data={
            "base_version_id": base_id,
            "new_version_id": "v2-alternative-id",
            "preview_hash": preview.json()["preview_hash"],
        },
        headers=founder,
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] == 2
    assert client.get(
        f"/api/bugs/{submitted.json()['id']}", headers=founder
    ).json()["status"] == "fixed"

    csv = (
        "定位唯一id,定位id的值,变量名,当前值,建议值,说明,证据\n"
        "officerID,O2,year,2002,2003,批量年份校正,公开履历\n"
    ).encode("utf-8")
    batch_checked = client.post(
        f"/api/datasets/{slug}/bugs/batch/validate",
        files={"file": ("alternative.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert batch_checked.status_code == 200
    assert batch_checked.json()["alternative_id_rows"] == [2]
    batch_blocked = client.post(
        f"/api/datasets/{slug}/bugs/batch",
        files={"file": ("alternative.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert batch_blocked.status_code == 409
    batch_submitted = client.post(
        f"/api/datasets/{slug}/bugs/batch",
        data={"confirmed_alternative_id_rows": json.dumps([2])},
        files={"file": ("alternative.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert batch_submitted.status_code == 200
    batch_detail = client.get(
        f"/api/bugs/{batch_submitted.json()['id']}", headers=founder).json()
    assert batch_detail["items"][0]["uid_var"] == "officerID"
    assert batch_detail["items"][0]["manual_only"] is False


def test_unstructured_correction_is_required_and_never_auto_applied(client, founder):
    slug = "ds-correction-unstructured"
    _new_dataset(
        client, founder, slug, [{"officerID": "U1", "year": 2001}])
    invalid = client.post(
        f"/api/datasets/{slug}/bugs/unstructured",
        json={"issue": "1. 两个 ID 应合并", "suggestion": "", "evidence": "公开简历"},
        headers=founder,
    )
    assert invalid.status_code == 422
    submitted = client.post(
        f"/api/datasets/{slug}/bugs/unstructured",
        json={
            "issue": "1. U1 与 U2 为同一官员\n2. 缺少一段任职经历",
            "suggestion": "1. 合并为 U1\n2. 补录完整任职经历",
            "evidence": "1. 官方简历链接\n2. 任免公告链接",
        },
        headers=founder,
    )
    assert submitted.status_code == 200
    bid = submitted.json()["id"]
    detail = client.get(f"/api/bugs/{bid}", headers=founder).json()
    assert detail["correction_type"] == "unstructured"
    assert detail["manual_only"] is True
    assert detail["items"] == []
    assert "合并为 U1" in detail["suggested_value"]
    assert client.post(
        f"/api/bugs/{bid}/finalize",
        json={"adopt_level": "full", "final_score": 9}, headers=founder,
    ).status_code == 200
    preview = client.get(
        f"/api/datasets/{slug}/corrections-release-preview", headers=founder)
    assert preview.status_code == 400
    assert "没有待应用" in preview.json()["detail"]


def test_duplicate_detection_batch_row_removal_and_pending_delete(client, founder):
    slug = "ds-correction-deduplicate"
    _, variables = _new_dataset(client, founder, slug, [
        {"officerID": "E1", "year": 2001},
        {"officerID": "E2", "year": 2002},
    ])
    first = _submit(
        client, founder, slug, variables["year"], "E1", 2001, 2000)
    assert first.status_code == 200
    duplicate = _submit(
        client, founder, slug, variables["year"], "E1", 2001, 2000)
    assert duplicate.status_code == 409 and "重复勘误" in duplicate.json()["detail"]

    csv = (
        "唯一ID值,变量名,当前值,建议值,说明,证据\n"
        "E1,year,2001,2000,历史重复,同一份公告\n"
        "E2,not_a_variable,2002,2003,变量错误,测试\n"
        "E2,year,2002,2003,有效修改,新公告\n"
    ).encode("utf-8")
    checked = client.post(
        f"/api/datasets/{slug}/bugs/batch/validate",
        files={"file": ("batch.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert checked.status_code == 200
    payload = checked.json()
    assert payload["invalid_rows"] == 2 and payload["valid_rows"] == 1
    assert "重复勘误" in payload["items"][0]["problems"][0]
    assert "不在当前变量清单" in payload["items"][1]["problems"][0]

    committed = client.post(
        f"/api/datasets/{slug}/bugs/batch",
        data={"included_row_numbers": json.dumps([4])},
        files={"file": ("batch.csv", io.BytesIO(csv), "text/csv")},
        headers=founder,
    )
    assert committed.status_code == 200 and committed.json()["items"] == 1
    saved = client.get(
        f"/api/bugs/{committed.json()['id']}", headers=founder).json()
    assert saved["items"][0]["uid_value"] == "E2"
    assert saved["can_delete"] is True
    deleted = client.delete(
        f"/api/bugs/{committed.json()['id']}", headers=founder)
    assert deleted.status_code == 200
    assert client.get(
        f"/api/bugs/{committed.json()['id']}", headers=founder).status_code == 404

    rejected_id = _submit(
        client, founder, slug, variables["year"], "E1", 2001, 1999).json()["id"]
    rejected_item = client.get(
        f"/api/bugs/{rejected_id}", headers=founder).json()["items"][0]["id"]
    assert client.post(
        f"/api/bug-items/{rejected_item}/finalize",
        json={"adopt_level": "reject", "final_score": 0}, headers=founder,
    ).status_code == 200
    rejected_duplicate = _submit(
        client, founder, slug, variables["year"], "E1", 2001, 1999)
    assert rejected_duplicate.status_code == 409


def test_partial_adoption_requires_real_edit_and_keeps_original(client, founder):
    slug = "ds-correction-partial-edit"
    _, variables = _new_dataset(
        client, founder, slug, [{"officerID": "P1", "year": 2001}])
    bid = _submit(
        client, founder, slug, variables["year"], "P1", 2001, 2000).json()["id"]
    detail = client.get(f"/api/bugs/{bid}", headers=founder).json()
    item = detail["items"][0]

    direct = client.post(
        f"/api/bug-items/{item['id']}/finalize",
        json={"adopt_level": "partial", "final_score": 6}, headers=founder)
    assert direct.status_code == 409
    unchanged = client.post(
        f"/api/bug-items/{item['id']}/finalize-partial",
        json={
            "uid_value": "P1", "var_name": "year",
            "current_value": "2001", "suggested_value": "2000",
            "reason": "履历年份需要校正", "final_score": 6,
        }, headers=founder)
    assert unchanged.status_code == 400 and "实际修改" in unchanged.json()["detail"]

    changed = client.post(
        f"/api/bug-items/{item['id']}/finalize-partial",
        json={
            "uid_value": "P1", "var_name": "year",
            "current_value": "2001", "suggested_value": "1999",
            "reason": "管理员依据正式任免公告修正建议值", "final_score": 6,
        }, headers=founder)
    assert changed.status_code == 200
    reviewed = client.get(f"/api/bugs/{bid}", headers=founder).json()
    assert reviewed["status"] == "accepted"
    modified = reviewed["items"][0]
    assert modified["admin_modified"] is True
    assert modified["original"]["suggested_value"] == "2000"
    assert modified["suggested_value"] == "1999"
    assert modified["original"]["reason"] == "履历年份需要校正"
    assert modified["reason"].startswith("管理员依据")
    assert _submit(
        client, founder, slug, variables["year"], "P1", 2001, 2000
    ).status_code == 409
    assert _submit(
        client, founder, slug, variables["year"], "P1", 2001, 1999
    ).status_code == 409
    assert client.delete(f"/api/bugs/{bid}", headers=founder).status_code == 403


def test_preview_hash_safe_apply_and_manual_new_officer_remains(client, founder):
    slug = "ds-correction-apply"
    base_id, variables = _new_dataset(
        client, founder, slug, [{"officerID": "C1", "year": 2001}])
    safe = _submit(client, founder, slug, variables["year"], "C1", 2001, 2000).json()["id"]
    manual = _submit(
        client, founder, slug, variables["year"], "C2", "", 1998, confirm=True).json()["id"]
    for bid in (safe, manual):
        item_id = client.get(f"/api/bugs/{bid}", headers=founder).json()["items"][0]["id"]
        finalized = client.post(
            f"/api/bug-items/{item_id}/finalize",
            json={"adopt_level": "full", "final_score": 9}, headers=founder)
        assert finalized.status_code == 200

    preview = client.get(
        f"/api/datasets/{slug}/corrections-release-preview",
        params={"base_version_id": base_id}, headers=founder).json()
    assert preview["auto_count"] == 1 and preview["manual_count"] == 1
    assert "assert r(N) == 1" in preview["script"]
    assert "人工处理：新增官员" in preview["script"]

    drift = client.post(f"/api/datasets/{slug}/apply-corrections", data={
        "base_version_id": base_id, "new_version_id": "v2-bad",
        "preview_hash": "not-the-reviewed-hash",
    }, headers=founder)
    assert drift.status_code == 409
    applied = client.post(f"/api/datasets/{slug}/apply-corrections", data={
        "base_version_id": base_id, "new_version_id": "v2",
        "changelog_zh": "透明应用勘误",
        "preview_hash": preview["preview_hash"],
    }, headers=founder)
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] == 1 and applied.json()["manual_remaining"] == 1
    assert client.get(f"/api/bugs/{safe}", headers=founder).json()["status"] == "fixed"
    assert client.get(f"/api/bugs/{manual}", headers=founder).json()["status"] == "accepted"
    assert _submit(
        client, founder, slug, variables["year"], "C1", 2001, 2000
    ).status_code == 409


def test_ai_review_requires_four_inputs_and_saves_reason(client, founder, monkeypatch):
    slug = "ds-correction-ai"
    _, variables = _new_dataset(
        client, founder, slug, [{"officerID": "D1", "year": 2001}])
    bid = _submit(client, founder, slug, variables["year"], "D1", 2001, 2000).json()["id"]
    from app.core.ai_client import ai_client
    captured = {}
    monkeypatch.setattr(ai_client, "enabled", lambda: True)

    def fake_complete(prompt, system="", strong=False):
        captured["prompt"] = prompt
        return '{"score":8.5,"reason":"证据来源明确，当前值与建议值可核对"}'

    monkeypatch.setattr(ai_client, "complete", fake_complete)
    result = client.post(f"/api/bugs/{bid}/ai-review", headers=founder)
    assert result.status_code == 200
    assert result.json()["ai_score"] == 8.5 and "证据来源" in result.json()["reason"]
    assert all(label in captured["prompt"] for label in ("当前值", "建议值", "修改说明", "证据"))


def test_discussion_search_users_posts_and_public_datasets(client, founder):
    client.patch("/api/me", json={
        "research_direction": "透明检索政治经济学",
        "keywords": "稀有检索词",
    }, headers=founder)
    users = client.get("/api/users/search", params={"q": "稀有检索词"}, headers=founder).json()
    assert any(user["username"] == "lixiaoyu" for user in users)

    public = client.post("/api/datasets", json={
        "slug": "ds-public-search", "name_zh": "公开检索数据集",
        "desc_zh": "包含独特公开数据关键词",
    }, headers=founder)
    assert public.status_code == 200
    datasets = client.get("/api/datasets/search", params={
        "q": "独特公开数据关键词", "public_only": True,
    }, headers=founder).json()
    assert [item["slug"] for item in datasets] == ["ds-public-search"]
    assert client.get("/api/datasets/search", params={
        "q": "COD", "public_only": True,
    }, headers=founder).json() == []

    visible = client.post("/api/posts", json={
        "title": "透明检索公开帖子", "content_zh": "包含稀有帖子关键词",
        "tags": ["检索验收"], "scope": "public",
    }, headers=founder).json()["id"]
    client.post("/api/posts", json={
        "title": "内部帖子", "content_zh": "同样包含稀有帖子关键词",
        "dataset_id": 1, "tags": ["检索验收"], "scope": "dataset",
        "scope_ref_ids": [1],
    }, headers=founder)
    posts = client.get("/api/posts/search", params={
        "q": "稀有帖子关键词",
    }, headers=founder).json()
    assert [post["id"] for post in posts] == [visible]
