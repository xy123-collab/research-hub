"""首次部署时创建管理员账号（替代会灌弱口令的 seed）。

背景（整改清单 A6a）：`app/seed.py` 在库为空时会建 admin/admin123 和两个 pass123，
新库上线的瞬间就存在弱口令总管理员。生产因此改成 `SEED_ON_START=false`，
由本脚本从环境变量读取一个你自己指定的强口令来建首位总管理员。

用法（在部署环境变量里配好后重启一次即可，之后可以删掉这三个变量）：
    BOOTSTRAP_ADMIN_USERNAME=你的账号名
    BOOTSTRAP_ADMIN_PASSWORD=一个强密码（≥10 位、含两类字符）
    BOOTSTRAP_ADMIN_EMAIL=你的邮箱

行为：
- 三个变量任一为空 → 什么都不做（正常启动会走到这里，不能报错）。
- 该账号名已存在 → 只补齐总管理员角色，不改密码（防止环境变量泄露后被顶号）。
- 库里已经有总管理员且该账号名不存在 → 仍然创建，便于加第二位管理员。
运行：python -m app.bootstrap_admin
"""
import os
import sys

from .core.db import Base, SessionLocal, engine
from .core.security import hash_password, password_problem
from . import models  # noqa: F401 注册全部表
from .models.user import Role, User


def run() -> None:
    username = (os.getenv("BOOTSTRAP_ADMIN_USERNAME") or "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or ""
    email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or "").strip()
    if not (username and password and email):
        return

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        problem = password_problem(password)
        if problem:
            print(f"[bootstrap_admin] 未创建管理员：BOOTSTRAP_ADMIN_PASSWORD {problem}")
            return
        role = db.query(Role).filter_by(code="super_admin").first()
        if not role:
            role = Role(code="super_admin", name_zh="总管理员", name_en="Super Admin")
            db.add(role)
        if not db.query(Role).filter_by(code="member").first():
            db.add(Role(code="member", name_zh="普通成员", name_en="Member"))
        db.flush()

        u = db.query(User).filter_by(username=username).first()
        if u:
            if u.role_id != role.id:
                u.role_id = role.id
                db.commit()
                print(f"[bootstrap_admin] 已把已有账号 {username} 提升为总管理员。")
            else:
                print(f"[bootstrap_admin] 账号 {username} 已是总管理员，未做改动。")
            return
        db.add(User(username=username, password_hash=hash_password(password),
                    display_name=username, email=email, role_id=role.id, status="active"))
        db.commit()
        print(f"[bootstrap_admin] 已创建总管理员 {username}。"
              f"请立即在部署环境变量里删除 BOOTSTRAP_ADMIN_PASSWORD。")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        run()
    except Exception as e:      # 启动流程不能因为它失败而中断
        print(f"[bootstrap_admin] 跳过：{e}", file=sys.stderr)
