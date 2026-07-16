"""@提及：候选范围计算、写入校验、被@消息聚合。

允许范围（按需求）：可@自己所在的全部数据集/课题组（整组）、以及这些数据集/课题组
成员范围内的单个成员。被@的人进入「新消息提示」范围（interact 类）。
"""
from __future__ import annotations
from sqlalchemy.orm import Session
from ..models.user import User
from ..models.group import ResearchGroup, GroupMember
from ..models.dataset import Dataset, DatasetMember
from ..models.notify import Mention


def my_scopes(db: Session, user: User) -> tuple[list[Dataset], list[ResearchGroup]]:
    dids = [m.dataset_id for m in db.query(DatasetMember).filter_by(user_id=user.id).all()]
    gids = [m.group_id for m in db.query(GroupMember).filter_by(
        user_id=user.id, status="active").all()]
    datasets = db.query(Dataset).filter(Dataset.id.in_(dids or [-1])).all()
    groups = db.query(ResearchGroup).filter(ResearchGroup.id.in_(gids or [-1])).all()
    return datasets, groups


def _members_of(db: Session, datasets, groups) -> dict[int, dict]:
    """返回 {user_id: {user, scopes:[(type,id,name)]}}，跨数据集/课题组去重。"""
    acc: dict[int, dict] = {}

    def add(uid, stype, sid, sname):
        e = acc.setdefault(uid, {"scopes": []})
        e["scopes"].append({"type": stype, "id": sid, "name": sname})

    for d in datasets:
        for m in db.query(DatasetMember).filter_by(dataset_id=d.id).all():
            add(m.user_id, "dataset", d.id, d.name_zh)
    for g in groups:
        for m in db.query(GroupMember).filter_by(group_id=g.id, status="active").all():
            add(m.user_id, "group", g.id, g.name_zh)
    return acc


def candidates(db: Session, user: User, q: str = "",
               scope_type: str = "", scope_id: int | None = None) -> dict:
    """检索可@对象：整组/整集 + 范围内单个成员。q 匹配名称/用户名/ID。"""
    datasets, groups = my_scopes(db, user)
    q = (q or "").strip().lower()

    # 限定某个具体数据集/课题组
    if scope_type == "dataset" and scope_id:
        datasets = [d for d in datasets if d.id == scope_id]; groups = []
    elif scope_type == "group" and scope_id:
        groups = [g for g in groups if g.id == scope_id]; datasets = []

    scope_entries = []
    for d in datasets:
        scope_entries.append({"target_type": "dataset", "target_id": d.id,
                              "name": d.name_zh, "kind": "dataset"})
    for g in groups:
        scope_entries.append({"target_type": "group", "target_id": g.id,
                              "name": g.name_zh, "kind": "group"})

    mem = _members_of(db, datasets, groups)
    members = []
    for uid, info in mem.items():
        if uid == user.id:
            continue
        u = db.get(User, uid)
        if not u or u.status == "left":
            continue
        members.append({"target_type": "user", "target_id": uid,
                        "display_name": u.display_name, "username": u.username,
                        "scopes": info["scopes"]})

    if q:
        def sm(s):  # 整组/整集按名称过滤
            return q in (s["name"] or "").lower()
        scope_entries = [s for s in scope_entries if sm(s)]
        def mm(m):
            return (q in (m["display_name"] or "").lower()
                    or q in (m["username"] or "").lower()
                    or (q.isdigit() and int(q) == m["target_id"]))
        members = [m for m in members if mm(m)]

    members.sort(key=lambda m: (m["display_name"] or m["username"] or ""))
    return {"scopes": scope_entries, "members": members[:50]}


def allowed_targets(db: Session, user: User) -> tuple[set[int], set[int], set[int]]:
    """返回 (allowed_user_ids, allowed_dataset_ids, allowed_group_ids)。"""
    datasets, groups = my_scopes(db, user)
    d_ids = {d.id for d in datasets}
    g_ids = {g.id for g in groups}
    mem = _members_of(db, datasets, groups)
    return set(mem.keys()), d_ids, g_ids


def record_mentions(db: Session, *, source_type: str, source_id: int, post_ref: str,
                    snippet: str, by_user: User, raw_mentions: list[dict]) -> int:
    """把评论里的 @对象落 Mention（仅保留在允许范围内的目标）。返回写入条数。"""
    if not raw_mentions:
        return 0
    u_ok, d_ok, g_ok = allowed_targets(db, by_user)
    n = 0
    seen = set()
    for m in raw_mentions:
        t = (m or {}).get("target_type"); tid = (m or {}).get("target_id")
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            continue
        if (t, tid) in seen:
            continue
        ok = ((t == "user" and tid in u_ok and tid != by_user.id)
              or (t == "dataset" and tid in d_ok)
              or (t == "group" and tid in g_ok))
        if not ok:
            continue
        seen.add((t, tid))
        db.add(Mention(source_type=source_type, source_id=source_id, post_ref=post_ref,
                       target_type=t, target_id=tid, mentioned_by=by_user.id,
                       snippet=(snippet or "")[:300]))
        n += 1
    return n


def mentions_for_user(db: Session, user: User, limit: int = 20) -> list[Mention]:
    """我被@的消息：直接@我 + @了我所在数据集/课题组（整组）。"""
    _, d_ids, g_ids = allowed_targets(db, user)
    # 我作为成员的数据集/课题组（整组@会通知到我）
    my_d = {m.dataset_id for m in db.query(DatasetMember).filter_by(user_id=user.id).all()}
    my_g = {m.group_id for m in db.query(GroupMember).filter_by(
        user_id=user.id, status="active").all()}
    rows = db.query(Mention).filter(Mention.mentioned_by != user.id).order_by(
        Mention.id.desc()).limit(400).all()
    out = []
    for m in rows:
        hit = ((m.target_type == "user" and m.target_id == user.id)
               or (m.target_type == "dataset" and m.target_id in my_d)
               or (m.target_type == "group" and m.target_id in my_g))
        if hit:
            out.append(m)
        if len(out) >= limit:
            break
    return out
