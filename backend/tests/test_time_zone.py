from datetime import datetime, timezone

from app.core.time import china_iso


def test_naive_utc_is_serialized_as_china_time_with_offset():
    assert china_iso(datetime(2026, 7, 26, 1, 25, 31)) == "2026-07-26T09:25+08:00"


def test_aware_utc_is_serialized_as_china_time_with_offset():
    value = datetime(2026, 7, 26, 16, 30, tzinfo=timezone.utc)
    assert china_iso(value) == "2026-07-27T00:30+08:00"


def test_download_history_uses_china_time_for_member_and_admin_views(client, founder):
    from app.core.db import SessionLocal
    from app.models.dataset import Dataset
    from app.models.notify import DownloadHistory
    from app.models.user import User

    db = SessionLocal()
    user = db.query(User).filter_by(username="lixiaoyu").first()
    dataset = db.query(Dataset).filter_by(slug="cod").first()
    row = DownloadHistory(
        user_id=user.id, dataset_id=dataset.id, source="dataset_version",
        file_name="tz-check.dta", location_label="版本库",
        downloaded_at=datetime(2026, 7, 26, 16, 30),
    )
    db.add(row); db.commit(); row_id = row.id; db.close()
    try:
        mine = client.get("/api/me/downloads", headers=founder).json()["items"]
        mine_row = next(x for x in mine if x["id"] == row_id)
        assert mine_row["downloaded_at"] == "2026-07-27T00:30+08:00"

        console = client.get("/api/admin/datasets/cod/console", headers=founder).json()
        admin_row = next(x for x in console["download_history"] if x["id"] == row_id)
        assert admin_row["downloaded_at"] == "2026-07-27T00:30+08:00"
    finally:
        db = SessionLocal()
        db.query(DownloadHistory).filter_by(id=row_id).delete()
        db.commit(); db.close()
