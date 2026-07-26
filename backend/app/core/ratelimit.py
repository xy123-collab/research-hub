"""登录 / 注册 / 找回密码的频率限制（对应整改清单 A6 里的 B1 项）。

实现刻意做得很轻：进程内滑动窗口计数，不引入 Redis。
- 线上 WEB_CONCURRENCY=1（免费档硬约束），单进程计数即全局计数；
- 将来多 worker 时它退化成"每 worker 各限一份"，仍能挡住脚本化暴力破解，
  真正的全局限流交给迁移后 Nginx 的 limit_req（见迁移清单 5.6）。

用法：
    rate_limit("login", request, limit=10, window=300)          # 按 IP
    rate_limit("login:" + username, request, limit=5, window=900, by_ip=False)
超限抛 429，前端 api/index.ts 已有 429 的中文提示。
"""
from __future__ import annotations

import threading
import time

from fastapi import HTTPException, Request

from .config import settings

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}
_last_gc = 0.0


def client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    # 线上在 Render / Nginx 反代后面，真实 IP 在 X-Forwarded-For 第一段
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _gc(now: float) -> None:
    global _last_gc
    if now - _last_gc < 300:
        return
    _last_gc = now
    for k in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
        _hits.pop(k, None)


def rate_limit(bucket: str, request: Request | None = None, *,
               limit: int = 10, window: int = 300, by_ip: bool = True,
               message: str = "操作过于频繁，请稍后再试") -> None:
    """滑动窗口限流：window 秒内最多 limit 次，超限抛 429。"""
    if not settings.RATE_LIMIT_ENABLED:
        return
    key = f"{bucket}|{client_ip(request)}" if by_ip else bucket
    now = time.time()
    with _lock:
        _gc(now)
        hits = [t for t in _hits.get(key, []) if now - t < window]
        if len(hits) >= limit:
            wait = int(window - (now - hits[0])) + 1
            _hits[key] = hits
            raise HTTPException(429, f"{message}（请等待约 {max(wait, 1)} 秒）")
        hits.append(now)
        _hits[key] = hits


def reset(bucket_prefix: str = "") -> None:
    """清空计数。测试用；也可在管理端解锁某个账号。"""
    with _lock:
        for k in [k for k in _hits if k.startswith(bucket_prefix)]:
            _hits.pop(k, None)
