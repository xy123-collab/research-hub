"""Web → 独立沙箱容器的文件队列客户端。

Web 不再执行用户代码。它只把代码和数据写入共享任务卷；没有网络、没有业务密钥的
sandbox 容器读取任务，执行后写回结果。共享卷使用单任务锁，避免并行任务的数据互见。
"""
import json
import os
import time
import uuid
from pathlib import Path

from sandbox_runtime.executor import SandboxViolation, static_guard, strip_code_fences

from ..core.config import settings

__all__ = ["SandboxViolation", "static_guard", "strip_code_fences", "run_readonly"]


def _layout() -> tuple[Path, Path, Path]:
    base = Path(settings.SANDBOX_JOB_DIR)
    incoming = base / "in"
    outgoing = base / "out"
    for path in (base, incoming, outgoing):
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except PermissionError:
            pass
    return base, incoming, outgoing


def _acquire(lock_path: Path, job_id: str, timeout: int) -> bool:
    payload = json.dumps({"job_id": job_id, "created_at": time.time()}).encode()
    for attempt in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            # Web 异常退出后自动回收陈旧锁；正常任务最长 30 秒，60 秒留足余量。
            try:
                if time.time() - lock_path.stat().st_mtime > max(60, timeout * 3):
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            return False
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            return True
    return False


def _release(lock_path: Path, job_id: str) -> None:
    try:
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        if current.get("job_id") == job_id:
            lock_path.unlink(missing_ok=True)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass


def _atomic_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    temp.chmod(0o600)
    os.replace(temp, path)


def run_readonly(code: str, df_records: list[dict], timeout: int | None = None) -> dict:
    if not settings.ENABLE_ONLINE_ANALYSIS:
        return {"ok": False, "error": "在线分析已由平台管理员暂时关闭，请稍后再试"}
    if settings.SANDBOX_BACKEND != "isolated_queue":
        return {"ok": False, "error": "在线分析安全配置错误：未接入独立沙箱容器"}

    code = strip_code_fences(code)
    static_guard(code)
    if not code:
        return {"ok": False, "error": "代码为空"}

    timeout = max(1, min(int(timeout or settings.SANDBOX_TIMEOUT), 30))
    base, incoming, outgoing = _layout()
    job_id = uuid.uuid4().hex
    lock_path = base / ".busy"
    if not _acquire(lock_path, job_id, timeout):
        return {"ok": False, "error": "沙箱正在执行另一项分析，请稍后重试"}

    input_path = incoming / f"{job_id}.json"
    output_path = outgoing / f"{job_id}.json"
    try:
        _atomic_json(input_path, {"code": code, "rows": df_records, "timeout": timeout})
        deadline = time.monotonic() + timeout + 5
        while time.monotonic() < deadline:
            try:
                with output_path.open("r", encoding="utf-8") as handle:
                    result = json.load(handle)
                output_path.unlink(missing_ok=True)
                return result
            except FileNotFoundError:
                time.sleep(0.05)
            except json.JSONDecodeError:
                time.sleep(0.02)
        return {"ok": False, "error": "独立沙箱容器无响应，请管理员检查 sandbox 服务"}
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        _release(lock_path, job_id)
