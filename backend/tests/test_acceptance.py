"""验收单测（对应文档 15.1 / README 验收清单）。"""


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_three_level_permission_non_member_cannot_submit_bug(client, outsider):
    # 非成员不能提交勘误（数据集级权限拦截）
    r = client.post("/api/datasets/cod/bugs", json={"description_zh": "x"}, headers=outsider)
    assert r.status_code == 403


def test_non_member_download_blocked_but_codebook_ok(client, outsider):
    # 非成员可看变量/codebook，但不能下载原始数据
    assert client.get("/api/datasets/cod/variables", headers=outsider).status_code == 200
    vid = client.get("/api/datasets/cod/versions", headers=outsider).json()[0]["id"]
    r = client.get(f"/api/datasets/cod/versions/{vid}/download?file=data", headers=outsider)
    assert r.status_code == 403


def test_version_not_overwritable(client, founder):
    # 版本不可覆盖：重复 version_id 报错
    import io, pandas as pd
    def valid_dta():
        buf = io.BytesIO()
        pd.DataFrame({"id": [1]}).to_stata(buf, write_index=False, version=118)
        buf.seek(0)
        return buf
    files = {"data_file": ("x.dta", valid_dta(), "application/octet-stream")}
    r1 = client.post("/api/datasets/cod/versions",
                     data={"version_id": "v1.1.0"}, files=files, headers=founder)
    assert r1.status_code == 200
    files2 = {"data_file": ("x.dta", valid_dta(), "application/octet-stream")}
    r2 = client.post("/api/datasets/cod/versions",
                     data={"version_id": "v1.1.0"}, files=files2, headers=founder)
    assert r2.status_code == 400 and "不可覆盖" in r2.json()["detail"]


def _publish_raw_dta(client, headers, slug="cod", version_id="vtest-raw"):
    """发布一版带真实 .dta 的原始数据（供沙箱加载真实变量）。"""
    import io, pandas as pd
    df = pd.DataFrame({"officerID": ["O1", "O2", "O3"], "gender": [1, 2, 1],
                       "begin_yr": [2001, 2005, 2010]})
    buf = io.BytesIO(); df.to_stata(buf, write_index=False, version=118); buf.seek(0)
    files = {"data_file": (f"{version_id}.dta", buf, "application/octet-stream")}
    return client.post(f"/api/datasets/{slug}/versions",
                       data={"version_id": version_id, "data_kind": "raw"},
                       files=files, headers=headers)


def test_sandbox_readonly_blocks_write(client, founder):
    # 只读沙箱：禁写回/禁网络（需先连上真实数据，才轮到静态过滤拦截）
    _publish_raw_dta(client, founder, version_id="vwrite-guard")
    bad = "import os\nresult = os.system('echo hi')"
    r = client.post("/api/datasets/cod/analysis/run", params={"code": bad}, headers=founder)
    assert r.status_code == 400


def test_sandbox_readonly_allows_aggregation(client, founder):
    # 现在沙箱 df 就是真实原始数据：len(df)=真实行数，真实变量名可直接用
    _publish_raw_dta(client, founder, version_id="vagg-raw")
    r = client.post("/api/datasets/cod/analysis/run",
                    params={"code": "result = len(df)"}, headers=founder)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["result"] == 3
    # 真实变量：markdown 围栏也应被剥离，返回真实列
    r2 = client.post("/api/datasets/cod/analysis/run",
                     params={"code": "```python\nresult = df['gender'].tolist()\n```"},
                     headers=founder)
    assert r2.status_code == 200 and r2.json()["ok"] is True
    assert r2.json()["result"] == [1, 2, 1]


def test_verify_flag_draft_does_not_modify_data(client, founder, member):
    # 核验：一键生成勘误草稿走评分制审核，绝不静默改原始数据
    from app.core.db import SessionLocal
    from app.models.dataset import Dataset
    from app.models.governance import VerifyFlag
    db = SessionLocal()
    d = db.query(Dataset).filter_by(slug="cod").first()
    f = VerifyFlag(dataset_id=d.id, source="ai", officer_id="O123",
                   variable_name="begin_yr", issue_desc="疑似异常", confidence=0.7, status="open")
    db.add(f); db.commit(); fid = f.id; db.close()

    r = client.post(f"/api/verify-flags/{fid}/draft-bug", headers=member)
    assert r.status_code == 200
    body = r.json()
    assert body["flag_status"] == "drafted" and body["bug_id"]
    # 生成的是 pending 勘误（草稿），数据未被改
    bugs = client.get("/api/datasets/cod/bugs", headers=member).json()
    drafted = [b for b in bugs if b["id"] == body["bug_id"]][0]
    assert drafted["status"] == "pending"


def test_scoring_review_full_chain_and_contribution(client, founder, member):
    # 评分制审核全链路：提交→成员评分+AI评分→管理员终审→贡献按终审分加权
    r = client.post("/api/datasets/cod/bugs",
                    json={"officer_id": "O1", "current_value": "1999",
                          "suggested_value": "1998", "description_zh": "年份笔误"},
                    headers=member)
    bid = r.json()["id"]
    assert client.post(f"/api/bugs/{bid}/reviews",
                       json={"acceptability_score": 8}, headers=founder).status_code == 200
    client.post(f"/api/bugs/{bid}/ai-review", headers=founder)
    before = client.get("/api/me/contributions", headers=member).json()["total"]
    fin = client.post(f"/api/bugs/{bid}/finalize",
                      json={"adopt_level": "full", "final_score": 9}, headers=founder)
    assert fin.status_code == 200 and fin.json()["status"] == "accepted"
    after = client.get("/api/me/contributions", headers=member).json()["total"]
    assert after == before + 9   # 报告人按终审分加权 +9


def test_charter_gate(client, outsider):
    # 公约：进入数据集时可取公约且记录是否已确认
    d = client.get("/api/datasets/cod", headers=outsider).json()
    c = client.get("/api/charters", params={"scope": "dataset", "ref": d["id"]}, headers=outsider).json()
    assert c["charter"] is not None and c["acked"] is False
    cid = c["charter"]["id"]
    assert client.post(f"/api/charters/{cid}/ack", headers=outsider).status_code == 200
    c2 = client.get("/api/charters", params={"scope": "dataset", "ref": d["id"]}, headers=outsider).json()
    assert c2["acked"] is True


def test_super_admin_privacy_boundary(client):
    # 总管理员隐私边界：只见元信息，不见贡献明细路由归课题组管理员；审计只暴露动作元数据
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    groups = client.get("/api/admin/groups", headers=H)
    assert groups.status_code == 200
    # 审计日志字段仅动作元数据（无 detail 内容值）
    log = client.get("/api/admin/audit-log", headers=H).json()
    if log:
        assert set(log[0].keys()) <= {"id", "user_id", "action", "object_type", "object_id", "created_at"}
