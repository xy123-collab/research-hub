"""本轮新增功能单测：名称去重(#1) / 对照表+文件勘误(#2) / 变量自动抽取(#3) / 沙箱真实变量(#4)。"""
import io
import pandas as pd


def _dta_bytes(df):
    buf = io.BytesIO(); df.to_stata(buf, write_index=False, version=118); buf.seek(0)
    return buf


def _publish_raw(client, headers, slug="cod", version_id="vf-raw", df=None):
    if df is None:
        df = pd.DataFrame({"officerID": ["O1", "O2"], "gender": [1, 2], "begin_yr": [2001, 2005]})
    files = {"data_file": (f"{version_id}.dta", _dta_bytes(df), "application/octet-stream")}
    return client.post(f"/api/datasets/{slug}/versions",
                       data={"version_id": version_id, "data_kind": "raw"},
                       files=files, headers=headers)


# ---------------- #1 名称去重 ----------------
def test_duplicate_group_name_blocked(client, founder):
    # 已存在「NSD 发展政经课题组」，再建同名（含大小写/空格差异）应被拦截
    r = client.post("/api/groups", json={"slug": "dup-grp-1",
                    "name_zh": "  NSD 发展政经课题组 ", "desc_zh": "x"}, headers=founder)
    assert r.status_code == 400 and "已存在" in r.json()["detail"]


def test_duplicate_dataset_name_blocked(client, founder):
    r = client.post("/api/datasets", json={"slug": "dup-ds-1",
                    "name_zh": "COD 地方官员数据库", "desc_zh": "x",
                    "founder_contact": "a@b.c"}, headers=founder)
    assert r.status_code == 400 and "已存在" in r.json()["detail"]


def test_unique_new_names_ok(client, founder):
    r = client.post("/api/datasets", json={"slug": "uniq-ds-xyz",
                    "name_zh": "全新独一无二数据集名", "desc_zh": "x",
                    "founder_contact": "a@b.c"}, headers=founder)
    assert r.status_code == 200


# ---------------- #3 变量自动抽取 ----------------
def test_variables_auto_extracted_on_publish(client, founder):
    df = pd.DataFrame({"uid": ["A", "B"], "newvar_x": [1, 2], "newvar_y": [3.0, 4.0]})
    r = _publish_raw(client, founder, version_id="vextract-1", df=df)
    assert r.status_code == 200
    synced = r.json().get("variables_synced")
    assert synced and "newvar_x" in [] or synced["total"] >= 3
    # data-config 变量清单应含新列
    cfg = client.get("/api/datasets/cod/data-config", headers=founder).json()
    names = {v["var_name"] for v in cfg["variables"]}
    assert {"uid", "newvar_x", "newvar_y"} <= names


def test_manual_refresh_variables(client, founder):
    _publish_raw(client, founder, version_id="vrefresh-1",
                 df=pd.DataFrame({"rid": ["A"], "colz": [9]}))
    r = client.post("/api/datasets/cod/variables/refresh", headers=founder)
    assert r.status_code == 200 and r.json()["ok"] is True


# ---------------- #4 沙箱真实变量 / context ----------------
def test_analysis_context_reports_real_variables(client, founder):
    _publish_raw(client, founder, version_id="vctx-1",
                 df=pd.DataFrame({"officerID": ["O1"], "salary": [100]}))
    r = client.get("/api/datasets/cod/analysis/context", headers=founder)
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is True
    assert "salary" in {v["var_name"] for v in body["variables"]}


# ---------------- #2 对照表 + 文件勘误 ----------------
def test_mapping_upload_and_download(client, founder):
    files = {
        "data_file": ("vmap.dta", _dta_bytes(pd.DataFrame({"id": [1], "v": [2]})), "application/octet-stream"),
        "mapping_file": ("city.csv", io.BytesIO("code,name\n110000,北京市\n".encode("utf-8")), "text/csv"),
    }
    r = client.post("/api/datasets/cod/versions",
                    data={"version_id": "vmap-1", "data_kind": "raw", "mapping_note": "城市编码对照"},
                    files=files, headers=founder)
    assert r.status_code == 200
    vid = r.json()["id"]
    vers = client.get("/api/datasets/cod/versions", headers=founder).json()
    row = next(v for v in vers if v["id"] == vid)
    assert row["mappings"] and row["mappings"][0]["kind"] == "mapping"
    dl = client.get(f"/api/datasets/cod/versions/{vid}/download?file=mapping", headers=founder)
    assert dl.status_code == 200 and "北京市" in dl.content.decode("utf-8")


def test_file_correction_flow(client, founder, member):
    # 成员提交 codebook 勘误 → 管理员采纳
    r = client.post("/api/datasets/cod/file-corrections",
                    data={"target": "codebook", "content": "第3页 gender 说明写反了"},
                    headers=member)
    assert r.status_code == 200
    fid = r.json()["id"]
    # 管理员能看到 pending
    lst = client.get("/api/datasets/cod/file-corrections", headers=founder).json()
    assert lst["is_admin"] is True
    assert any(i["id"] == fid and i["status"] == "pending" for i in lst["items"])
    # 采纳
    d = client.post(f"/api/datasets/cod/file-corrections/{fid}/decide",
                    params={"approve": True}, headers=founder)
    assert d.status_code == 200 and d.json()["status"] == "accepted"


def test_file_correction_invalid_target(client, member):
    r = client.post("/api/datasets/cod/file-corrections",
                    data={"target": "bogus", "content": "x"}, headers=member)
    assert r.status_code == 400


# ---------------- 文献同集查重（标题+作者+年份+刊物 四项全一致才算重复）----------------
def test_founder_shows_current_lead_email_and_follows_transfer(client, founder):
    """数据集「负责人及邮箱」= 当前总管理员及其注册邮箱；转让后自动更换。"""
    from app.core.db import SessionLocal
    from app.models.user import User
    from app.models.dataset import Dataset, DatasetMember
    from datetime import datetime
    # 建集（lixiaoyu 为总管理员），给两位用户设注册邮箱，并把 chenmo 加为成员
    r = client.post("/api/datasets", json={"slug": "lead-email-ds",
                    "name_zh": "负责人邮箱测试集", "desc_zh": "x"}, headers=founder)
    assert r.status_code == 200
    db = SessionLocal()
    lx = db.query(User).filter_by(username="lixiaoyu").first()
    cm = db.query(User).filter_by(username="chenmo").first()
    lx.email = "lixiaoyu@reg.com"; cm.email = "chenmo@reg.com"
    d = db.query(Dataset).filter_by(slug="lead-email-ds").first()
    db.add(DatasetMember(dataset_id=d.id, user_id=cm.id, ds_role="member",
                         joined_at=datetime.utcnow(), approved_by=lx.id))
    db.commit(); cm_id = cm.id; db.close()
    # 负责人 = 当前总管理员 lixiaoyu，邮箱 = 其注册邮箱
    det = client.get("/api/datasets/lead-email-ds", headers=founder).json()
    assert det["founder"]["name"] == "李小雨" and det["founder"]["contact"] == "lixiaoyu@reg.com"
    # 转让总管理员给 chenmo → 负责人及邮箱自动跟着变
    t = client.post(f"/api/datasets/lead-email-ds/transfer-lead/{cm_id}", headers=founder)
    assert t.status_code == 200
    det2 = client.get("/api/datasets/lead-email-ds", headers=founder).json()
    assert det2["founder"]["id"] == cm_id and det2["founder"]["contact"] == "chenmo@reg.com"


def test_literature_duplicate_only_when_all_four_match(client, founder):
    ref = {"title": "Officials and Growth ZZ", "authors": "张三", "year": 2020, "venue": "经济研究"}
    r1 = client.post("/api/datasets/cod/literature/refs", json={**ref, "confirm_real": True}, headers=founder)
    assert r1.json().get("ok") is True
    # 四项全一致（大小写/空格不敏感）→ 判重
    r2 = client.post("/api/datasets/cod/literature/refs",
                     json={**ref, "title": "  officials and growth zz ", "confirm_real": True}, headers=founder)
    assert r2.json().get("duplicate") is True
    # 仅标题相同、作者不同 → 不算重复，允许上传
    r3 = client.post("/api/datasets/cod/literature/refs",
                     json={**ref, "authors": "李四", "confirm_real": True}, headers=founder)
    assert r3.json().get("ok") is True
