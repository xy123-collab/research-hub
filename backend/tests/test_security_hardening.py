"""P0 安全整改（A1–A6）与注册准入（邀请码 + 邮箱验证）的回归测试。

对应《claude-阿里云迁移-可行性评估与实施清单》3.1 节 A1/A2/A3/A4/A5/A6 与 A8 验证门槛。
每个测试都写清"原来是什么问题"，将来有人改回去会立刻红。
"""
import pytest

from app.core.config import settings

PW = "Rhub-Test-2026"


def _h(client, u, p):
    r = client.post("/api/auth/login", json={"username": u, "password": p})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return _h(client, "admin", "admin123")


# ---------- A2：未鉴权的群发邮件接口 ----------
def test_a2_mass_mail_endpoints_require_super_admin(client, founder):
    """原来任何人无需登录就能 POST 触发全平台群发，可打爆企业邮日配额。"""
    for path in ("/api/admin/run-digest", "/api/admin/run-weekly-digest",
                 "/api/admin/flush-deliveries"):
        assert client.post(path).status_code == 401, path        # 匿名
        assert client.post(path, headers=founder).status_code == 403, path  # 登录但非总管理员


# ---------- A3：路径穿越 + 头像接口 ----------
def test_a3_avatar_path_traversal_rejected(client, founder):
    """`avatar/../versions/xxx.dta` 曾经能读到任意数据集的原始数据文件。"""
    assert client.get("/api/me/avatar/file", params={"k": "avatar/1/a.png"}).status_code == 401
    for k in ("avatar/../versions/x.dta", "avatar/../../../etc/passwd",
              "avatar/..%2f..%2fetc/passwd", "versions/x.dta", "avatar/1/../../etc/passwd"):
        r = client.get("/api/me/avatar/file", params={"k": k}, headers=founder)
        assert r.status_code in (400, 404), (k, r.status_code)


def test_a3_storage_layer_rejects_dotdot():
    from app.core.storage import StorageKeyError, safe_key
    for bad in ("avatar/../x", "../etc/passwd", "a/../../b", "", "/",
                "/versions/x.dta"):
        with pytest.raises(StorageKeyError):
            safe_key(bad)
    assert safe_key("versions/a.dta") == "versions/a.dta"


# ---------- A4：沙箱不再能读走生产密钥 ----------
def test_a4_sandbox_blocks_env_and_file_reads():
    from app.services.sandbox import SandboxViolation, static_guard
    payloads = [
        "result = pd.read_csv('/proc/self/environ')",     # 报告里实测可用的逃逸
        "result = pd.read_csv('/app/.env')",
        "import os",
        "result = open('/etc/passwd').read()",
        "result = getattr(pd, 'read_' + 'csv')('/etc/passwd')",   # 拼字符串绕黑名单
        "result = ().__class__.__mro__[-1].__subclasses__()",
        "df.to_csv('/tmp/x.csv')",
    ]
    for code in payloads:
        with pytest.raises(SandboxViolation):
            static_guard(code)


def test_a4_sandbox_child_process_has_no_secrets(monkeypatch):
    """子进程是重新 execve 的干净进程：环境里读不到 JWT_SECRET 等密钥。"""
    from app.services import sandbox
    monkeypatch.setenv("JWT_SECRET", "super-secret-value")
    env = sandbox._clean_env("/tmp")
    assert "JWT_SECRET" not in env and "DATABASE_URL" not in env
    assert "AI_API_KEY" not in env and "COS_SECRET_KEY" not in env
    # 正常统计仍然跑得通
    assert sandbox.run_readonly("result = len(df)", [{"a": 1}, {"a": 2}])["result"] == 2


# ---------- A5：匿名信息泄露 ----------
def test_a5_user_info_requires_login(client, founder):
    assert client.get("/api/users/2").status_code == 401
    assert client.get("/api/users/2/resume").status_code == 401
    assert client.get("/api/users/2", headers=founder).status_code == 200


def test_a5_project_image_requires_login_and_scope(client, founder, outsider):
    """原来按 pid 遍历即可拿到「仅自己可见」项目的封面图。"""
    import io
    r = client.post("/api/projects", data={"title": "私密项目", "body_zh": "x",
                                           "status": "doing", "scope": "self"},
                    files={"image": ("c.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 40),
                                     "image/png")}, headers=founder)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert client.get(f"/api/projects/{pid}/image").status_code == 401
    assert client.get(f"/api/projects/{pid}/image", headers=outsider).status_code == 403
    # 有权限的人从详情接口拿到的鉴权地址可以正常打开
    url = client.get(f"/api/projects/{pid}", headers=founder).json()["image_url"]
    assert url == f"/api/projects/{pid}/image"
    assert client.get(url, headers=founder).status_code == 200


# ---------- A6：密码强度 / 生产配置 ----------
@pytest.mark.parametrize("pw", ["short1!", "pass123", "abcdefghij", "1234567890"])
def test_a6_weak_password_rejected_on_register(client, pw):
    r = client.post("/api/auth/register", json={"username": f"weak{abs(hash(pw)) % 9999}",
                                                "password": pw, "email": f"w{abs(hash(pw))%9999}@x.com"})
    assert r.status_code == 422, r.text


def test_a6_production_guard_rejects_default_secret(monkeypatch):
    from app.core.config import Settings
    s = Settings(DATABASE_URL="postgresql://u:p@h:5432/db", JWT_SECRET="change-me-in-prod")
    assert s.is_production is True and s.docs_enabled is False
    with pytest.raises(RuntimeError):
        s.assert_production_ready()
    s2 = Settings(DATABASE_URL="postgresql://u:p@h:5432/db",
                  JWT_SECRET="a-real-strong-secret", ENABLE_ONLINE_ANALYSIS=False)
    s2.assert_production_ready()          # 不抛异常即通过
    s3 = Settings(DATABASE_URL="postgresql://u:p@h:5432/db",
                  JWT_SECRET="a-real-strong-secret", ENABLE_ONLINE_ANALYSIS=True)
    with pytest.raises(RuntimeError):
        s3.assert_production_ready()


def test_a6_rate_limit_blocks_burst(client, monkeypatch):
    """限流平时在测试里关着（整套测试同一个 IP），这里单独打开验证确实会 429。"""
    from app.core import ratelimit
    ratelimit.reset("")
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    codes = [client.post("/api/auth/login",
                         json={"username": "no_such_user", "password": "x"}).status_code
             for _ in range(25)]
    assert 429 in codes
    ratelimit.reset("")


# ---------- A1：会话与令牌撤销 ----------
def test_a1_refresh_rotates_and_old_token_dies(client):
    client.post("/api/auth/register", json={"username": "sess1", "password": PW,
                                            "email": "sess1@x.com"})
    tok = client.post("/api/auth/login", json={"username": "sess1", "password": PW}).json()
    r1 = client.post("/api/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r1.status_code == 200
    # 旧 refresh 已被轮换作废，不能再用第二次
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": tok["refresh_token"]}).status_code == 401
    # 新 refresh 正常可用
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": r1.json()["refresh_token"]}).status_code == 200


def test_a1_password_reset_revokes_old_access_token(client):
    from app.core.db import SessionLocal
    from app.models.extras import PasswordResetToken
    client.post("/api/auth/register", json={"username": "sess2", "password": PW,
                                            "email": "sess2@x.com"})
    tok = client.post("/api/auth/login", json={"username": "sess2", "password": PW}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.get("/api/me", headers=h).status_code == 200

    client.post("/api/auth/forgot-password", json={"email": "sess2@x.com"})
    db = SessionLocal()
    t = (db.query(PasswordResetToken).filter_by(used=False)
         .order_by(PasswordResetToken.id.desc()).first().token)
    db.close()
    assert client.post("/api/auth/reset-password",
                       json={"token": t, "new_password": "Rhub-Reset-2026"}).status_code == 200
    # 改密码后旧 access token 立刻失效（原来还能继续用满一小时）
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": tok["refresh_token"]}).status_code == 401
    # 重置后立即用新密码登录也应可用，不能被同一秒的撤销边界误伤。
    fresh = client.post("/api/auth/login",
                        json={"username": "sess2", "password": "Rhub-Reset-2026"}).json()
    assert client.get("/api/me", headers={
        "Authorization": f"Bearer {fresh['access_token']}"}).status_code == 200


def test_a1_logout_all_kills_current_session(client):
    client.post("/api/auth/register", json={"username": "sess3", "password": PW,
                                            "email": "sess3@x.com"})
    tok = client.post("/api/auth/login", json={"username": "sess3", "password": PW}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.post("/api/auth/logout-all", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401


def test_a1_logout_revokes_refresh_even_without_access(client):
    client.post("/api/auth/register", json={"username": "sess4", "password": PW,
                                            "email": "sess4@x.com"})
    tok = client.post("/api/auth/login", json={"username": "sess4", "password": PW}).json()
    assert client.post("/api/auth/logout",
                       json={"refresh_token": tok["refresh_token"]}).status_code == 200
    assert client.post("/api/auth/refresh",
                       json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_reset_token_not_stored_in_email_meta(client):
    """B6：重置令牌曾被明文写进 email_events.meta，有后台权限的人可接管任意账号。"""
    from app.core.db import SessionLocal
    from app.models.extras import EmailEvent
    client.post("/api/auth/forgot-password", json={"email": "sess3@x.com"})
    db = SessionLocal()
    ev = (db.query(EmailEvent).filter_by(kind="password_reset")
          .order_by(EmailEvent.id.desc()).first())
    db.close()
    assert ev and "token" not in (ev.meta or {})


# ---------- 新功能：邀请制注册 ----------
def _set_reg(client, admin, **kw):
    r = client.patch("/api/admin/registration", json=kw, headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def test_invite_only_registration_flow(client, admin, founder):
    # 平台策略是公开可读的（登录页要据此决定显不显示邀请码框）
    assert client.get("/api/auth/register-policy").json()["invite_required"] is False
    # 非总管理员碰不到邀请码后台
    assert client.get("/api/admin/invite-codes", headers=founder).status_code == 403

    made = client.post("/api/admin/invite-codes",
                       json={"count": 2, "valid_days": 30, "max_uses": 1, "note": "第一批"},
                       headers=admin)
    assert made.status_code == 200, made.text
    codes = made.json()["codes"]
    assert len(codes) == 2 and len(set(codes)) == 2

    _set_reg(client, admin, invite_only=True)
    assert client.get("/api/auth/register-policy").json()["invite_required"] is True

    # 不填邀请码 → 拒绝
    r = client.post("/api/auth/register", json={"username": "inv_no", "password": PW,
                                                "email": "inv_no@x.com"})
    assert r.status_code == 400 and "邀请码" in r.json()["detail"]
    # 乱填 → 拒绝
    r = client.post("/api/auth/register", json={"username": "inv_bad", "password": PW,
                                                "email": "inv_bad@x.com", "invite_code": "ZZZZZZZZZZ"})
    assert r.status_code == 400
    # 正确的码 → 通过
    r = client.post("/api/auth/register", json={"username": "inv_ok", "password": PW,
                                                "email": "inv_ok@x.com", "invite_code": codes[0]})
    assert r.status_code == 200, r.text
    # 同一个一次性码不能再用
    r = client.post("/api/auth/register", json={"username": "inv_ok2", "password": PW,
                                                "email": "inv_ok2@x.com", "invite_code": codes[0]})
    assert r.status_code == 400 and "次数" in r.json()["detail"]

    # 后台能看到核销记录，并能停用剩下那个码
    rows = client.get("/api/admin/invite-codes", headers=admin).json()
    used = [x for x in rows if x["code"] == codes[0]][0]
    assert used["state"] == "used_up" and used["used_by"][0]["username"] == "inv_ok"
    left = [x for x in rows if x["code"] == codes[1]][0]
    assert client.patch(f"/api/admin/invite-codes/{left['id']}", params={"active": False},
                        headers=admin).json()["state"] == "disabled"
    r = client.post("/api/auth/register", json={"username": "inv_off", "password": PW,
                                                "email": "inv_off@x.com", "invite_code": codes[1]})
    assert r.status_code == 400 and "停用" in r.json()["detail"]

    # 关掉邀请制后恢复自由注册
    _set_reg(client, admin, invite_only=False)
    assert client.post("/api/auth/register", json={"username": "free_ok", "password": PW,
                                                   "email": "free_ok@x.com"}).status_code == 200


def test_expired_invite_code_rejected(client, admin):
    from datetime import datetime, timedelta
    from app.core.db import SessionLocal
    from app.models.authx import InviteCode
    code = client.post("/api/admin/invite-codes", json={"count": 1, "valid_days": 1},
                       headers=admin).json()["codes"][0]
    db = SessionLocal()
    row = db.query(InviteCode).filter_by(code=code).first()
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit(); db.close()
    _set_reg(client, admin, invite_only=True)
    r = client.post("/api/auth/register", json={"username": "inv_exp", "password": PW,
                                                "email": "inv_exp@x.com", "invite_code": code})
    assert r.status_code == 400 and "过期" in r.json()["detail"]
    _set_reg(client, admin, invite_only=False)


# ---------- 新功能：注册邮箱验证 ----------
def test_email_verification_flow(client, admin, monkeypatch):
    from types import SimpleNamespace
    from app.services import registration as reg
    monkeypatch.setattr(reg, "email_backend_can_send", lambda: True)
    monkeypatch.setattr(reg, "send_email", lambda *a, **k: SimpleNamespace(status="sent"))
    _set_reg(client, admin, email_verify="on")
    assert client.get("/api/auth/register-policy").json()["email_verify_required"] is True

    # 没验证码 → 拒绝
    r = client.post("/api/auth/register", json={"username": "ev1", "password": PW,
                                                "email": "ev1@x.com"})
    assert r.status_code == 400 and "验证码" in r.json()["detail"]

    sent = client.post("/api/auth/send-email-code", json={"email": "ev1@x.com"})
    assert sent.status_code == 200
    assert "dev_code" not in sent.json()  # 验证码绝不能通过匿名 API 回传
    from app.core.db import SessionLocal
    from app.models.authx import EmailVerification
    db = SessionLocal()
    code = (db.query(EmailVerification).filter_by(email="ev1@x.com", used=False)
            .order_by(EmailVerification.id.desc()).first().code)
    db.close()

    # 错的验证码 → 拒绝
    r = client.post("/api/auth/register", json={"username": "ev1", "password": PW,
                                                "email": "ev1@x.com", "email_code": "000000"})
    assert r.status_code == 400
    # 对的验证码 → 通过
    r = client.post("/api/auth/register", json={"username": "ev1", "password": PW,
                                                "email": "ev1@x.com", "email_code": code})
    assert r.status_code == 200, r.text
    # 验证码一次性：同一个码不能再用
    r = client.post("/api/auth/register", json={"username": "ev2", "password": PW,
                                                "email": "ev1@x.com", "email_code": code})
    assert r.status_code == 400

    # 已注册的邮箱不向匿名调用者泄露存在性（返回与普通请求同样的 200）
    assert client.post("/api/auth/send-email-code",
                       json={"email": "ev1@x.com"}).status_code == 200
    _set_reg(client, admin, email_verify="off")
    assert client.get("/api/auth/register-policy").json()["email_verify_required"] is False


def test_email_verify_auto_mode_follows_email_backend(client, admin):
    """auto = 邮件后端真能发信才要求验证；Render 免费档发不出信，不该把人挡在门外。"""
    st = _set_reg(client, admin, email_verify="auto")
    assert st["email_verify"] == "auto"
    assert st["email_verify_effective"] is False        # 测试环境 EMAIL_BACKEND=mock


def test_email_verify_cannot_be_forced_before_mail_is_ready(client, admin):
    """邮件未接入时只预留代码、不要求验证，避免新用户被挡在注册页外。"""
    st = _set_reg(client, admin, email_verify="on")
    assert st["email_verify_effective"] is False
    assert client.get("/api/auth/register-policy").json()["email_verify_required"] is False
    r = client.post("/api/auth/register", json={"username": "mail_not_ready",
                                                "password": PW,
                                                "email": "mail_not_ready@x.com"})
    assert r.status_code == 200, r.text
    assert client.post("/api/auth/send-email-code",
                       json={"email": "new_mail@x.com"}).status_code == 400
    _set_reg(client, admin, email_verify="off")
