"""本轮细节修改回归：多数据格式、中文名称、任意格式辅助文件、勘误发版预填和具体存储错误。"""
import io
import numpy as np
import pandas as pd
from scipy.io import savemat

from app.services.introspect import read_table_df


def _csv_bytes():
    return "编号,姓名,指标\n甲,张三,1\n乙,李四,2\n".encode("utf-8-sig")


def test_dashboard_reader_supports_csv_xlsx_parquet_mat_and_chinese_columns():
    csv_df = read_table_df(_csv_bytes(), "csv")
    assert list(csv_df.columns) == ["编号", "姓名", "指标"]

    source = pd.DataFrame({"中文变量": [1, 2], "value": [3.0, 4.0]})
    xlsx = io.BytesIO(); source.to_excel(xlsx, index=False); xlsx.seek(0)
    assert "中文变量" in read_table_df(xlsx.getvalue(), "xlsx").columns

    parquet = io.BytesIO(); source.to_parquet(parquet, index=False); parquet.seek(0)
    assert "中文变量" in read_table_df(parquet.getvalue(), "parquet").columns

    mat = io.BytesIO(); savemat(mat, {"matrix": np.array([[1, 2], [3, 4]])})
    assert list(read_table_df(mat.getvalue(), "mat").columns) == ["matrix_1", "matrix_2"]


def test_publish_csv_with_chinese_filename_and_variables_then_download(client, founder):
    files = {"data_file": ("官员数据_中文文件名.csv", io.BytesIO(_csv_bytes()), "text/csv")}
    r = client.post("/api/datasets/cod/versions",
                    data={"version_id": "v-unicode-csv", "data_kind": "raw"},
                    files=files, headers=founder)
    assert r.status_code == 200, r.text
    assert r.json()["variables_synced"]["total"] == 3
    cfg = client.get("/api/datasets/cod/data-config", headers=founder).json()
    assert {"编号", "姓名", "指标"} <= {x["var_name"] for x in cfg["variables"]}
    analysis = client.post("/api/datasets/cod/analysis/run",
                           params={"code": "result = df['指标'].sum()"}, headers=founder)
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["ok"] is True and analysis.json()["result"] == 3

    vid = r.json()["id"]
    dl = client.get(f"/api/datasets/cod/versions/{vid}/download?file=data", headers=founder)
    assert dl.status_code == 200 and "张三" in dl.content.decode("utf-8-sig")
    cd = dl.headers["content-disposition"]
    assert "filename*=UTF-8''" in cd and "%E5%AE%98%E5%91%98" in cd


def test_invalid_supported_data_file_is_rejected_before_publish(client, founder):
    r = client.post("/api/datasets/cod/versions",
                    data={"version_id": "v-broken-data", "data_kind": "raw"},
                    files={"data_file": ("损坏数据.xlsx", io.BytesIO(b"not-an-excel"),
                                         "application/octet-stream")},
                    headers=founder)
    assert r.status_code == 400
    assert "无法解析数据文件" in r.json()["detail"]
    versions = client.get("/api/datasets/cod/versions", headers=founder).json()
    assert "v-broken-data" not in {v["version_id"] for v in versions}


def test_codebook_and_mapping_accept_arbitrary_formats_and_keep_extensions(client, founder):
    files = {
        "codebook_file": ("说明文档.pages", io.BytesIO(b"pages-content"),
                          "application/octet-stream"),
        "mapping_file": ("取值字典.dta", io.BytesIO(b"stored-only-dta"),
                         "application/octet-stream"),
    }
    r = client.post("/api/datasets/cod/versions",
                    data={"version_id": "v-any-aux", "data_kind": "sample"},
                    files=files, headers=founder)
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    cb = client.get(f"/api/datasets/cod/versions/{vid}/download?file=codebook", headers=founder)
    mp = client.get(f"/api/datasets/cod/versions/{vid}/download?file=mapping", headers=founder)
    assert cb.status_code == 200 and cb.content == b"pages-content"
    assert mp.status_code == 200 and mp.content == b"stored-only-dta"
    assert ".pages" in cb.headers["content-disposition"]
    assert ".dta" in mp.headers["content-disposition"]


def test_correction_release_preview_contains_text_and_change_code(client, founder, member):
    data = {"data_file": ("勘误测试.csv", io.BytesIO(_csv_bytes()), "text/csv")}
    pub = client.post("/api/datasets/cod/versions",
                      data={"version_id": "v-correction-preview", "data_kind": "raw"},
                      files=data, headers=founder)
    assert pub.status_code == 200, pub.text
    client.put("/api/datasets/cod/data-config",
               json={"unique_id_var": "编号", "rules": []}, headers=founder)
    variables = client.get("/api/datasets/cod/variables", headers=founder).json()
    var_id = next(v["id"] for v in variables if v["var_name"] == "指标")
    bug = client.post("/api/datasets/cod/bugs",
                      json={"officer_id": "甲", "variable_id": var_id,
                            "current_value": "1", "suggested_value": "10",
                            "description_zh": "指标校正"}, headers=member)
    assert bug.status_code == 200
    detail = client.get(f"/api/bugs/{bug.json()['id']}", headers=founder).json()
    fin = client.post(f"/api/bug-items/{detail['items'][0]['id']}/finalize",
                      json={"adopt_level": "full", "final_score": 9}, headers=founder)
    assert fin.status_code == 200

    preview = client.get("/api/datasets/cod/corrections-release-preview", headers=founder)
    assert preview.status_code == 200, preview.text
    text = preview.json()["changelog_zh"]
    assert "指标校正" in text and "修改代码" in text
    assert "replace 指标" in text and "if 编号" in text


def test_missing_download_file_returns_actionable_error(client, founder, monkeypatch):
    files = {"data_file": ("missing-check.csv", io.BytesIO(b"id,value\n1,2\n"), "text/csv")}
    pub = client.post("/api/datasets/cod/versions",
                      data={"version_id": "v-missing-file", "data_kind": "raw"},
                      files=files, headers=founder)
    assert pub.status_code == 200
    from app.core.storage import storage
    monkeypatch.setattr(storage, "open", lambda key: (_ for _ in ()).throw(FileNotFoundError(key)))
    dl = client.get(f"/api/datasets/cod/versions/{pub.json()['id']}/download?file=data",
                    headers=founder)
    assert dl.status_code == 404
    assert "重新上传" in dl.json()["detail"] and "COS" in dl.json()["detail"]
