"""独立沙箱容器 worker：通过共享任务卷与 Web 交换一次性 JSON 任务。

任务载荷不会通过网络传输。worker 在执行用户代码前删除输入文件，并把子进程降为
nobody；任务卷目录保持 root:root 0700，因此用户代码无法读取任务卷中的其他内容。
"""
import argparse
import json
import os
import time
from pathlib import Path
from threading import Event

from .executor import SandboxViolation, execute_payload


def ensure_layout(job_dir: str) -> dict[str, Path]:
    base = Path(job_dir)
    paths = {
        "base": base,
        "in": base / "in",
        "processing": base / "processing",
        "out": base / "out",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except PermissionError:
            pass
    return paths


def _atomic_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    temp.chmod(0o600)
    os.replace(temp, path)


def process_once(job_dir: str, *, drop_uid: int | None = 65534,
                 drop_gid: int | None = 65534) -> bool:
    paths = ensure_layout(job_dir)
    jobs = sorted(paths["in"].glob("*.json"))
    if not jobs:
        return False

    incoming = jobs[0]
    processing = paths["processing"] / incoming.name
    try:
        os.replace(incoming, processing)
    except FileNotFoundError:
        return False

    job_id = processing.stem
    try:
        with processing.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        result = {"ok": False, "error": f"任务载荷无效：{exc}"}
    else:
        # 先删载荷再启动降权子进程，杜绝用户代码读取本次数据 JSON。
        processing.unlink(missing_ok=True)
        try:
            result = execute_payload(
                payload.get("code", ""),
                payload.get("rows", []),
                timeout=max(1, min(int(payload.get("timeout", 10)), 30)),
                drop_uid=drop_uid,
                drop_gid=drop_gid,
            )
        except SandboxViolation as exc:
            result = {"ok": False, "error": str(exc)}
        except Exception as exc:
            result = {"ok": False, "error": f"沙箱 worker 失败：{exc}"}
    processing.unlink(missing_ok=True)
    _atomic_json(paths["out"] / f"{job_id}.json", result)
    return True


def run_worker(job_dir: str, *, stop_event: Event | None = None,
               poll_interval: float = 0.05, drop_identity: bool = True) -> None:
    stop_event = stop_event or Event()
    uid = 65534 if drop_identity else None
    gid = 65534 if drop_identity else None
    while not stop_event.is_set():
        if not process_once(job_dir, drop_uid=uid, drop_gid=gid):
            stop_event.wait(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", default="/sandbox-jobs")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("sandbox worker 必须以 root 启动，以便任务子进程降权为 nobody")
    run_worker(args.job_dir)


if __name__ == "__main__":
    main()
