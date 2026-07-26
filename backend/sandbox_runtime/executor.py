"""沙箱容器内部的受限 Python 执行器。

AST 过滤是纵深防御，不是安全边界。真正的边界由 Docker Compose 提供：
独立镜像、无网络、只读根文件系统、无业务环境变量、资源上限，以及执行用户降权。
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile


class SandboxViolation(Exception):
    pass


_FORBIDDEN_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
    "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir",
    "memoryview", "exit", "quit", "help", "super", "object", "type",
}
_FORBIDDEN_ATTR_RE = re.compile(
    r"^(read_\w+|to_(csv|stata|pickle|excel|parquet|json|sql|hdf|feather|clipboard|latex|xml|orc)"
    r"|write\w*|system|popen|remove|unlink|rename|mkdir|rmdir|chdir|environ|getenv)$")
_ALLOWED_ATTRS = {
    "to_dict", "to_list", "to_numpy", "to_frame", "to_string", "to_period",
    "to_datetime", "to_timedelta", "to_records",
}


def strip_code_fences(code: str) -> str:
    if not code:
        return ""
    value = code.strip()
    if "```" in value:
        match = re.search(r"```(?:[a-zA-Z0-9_+-]*)?\s*\n?(.*?)```", value, re.S)
        value = match.group(1) if match else value.replace("```", "")
    return value.strip()


def static_guard(code: str) -> None:
    try:
        tree = ast.parse(code or "")
    except SyntaxError as exc:
        raise SandboxViolation(f"代码语法错误：第 {exc.lineno} 行 {exc.msg}") from exc

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxViolation(
                "沙箱内禁止 import：可直接使用已注入的 df（数据）、pd（pandas）、columns")
        if isinstance(node, ast.Attribute):
            name = node.attr
            if name.startswith("_"):
                raise SandboxViolation(f"禁止访问内部属性 {name}（沙箱只读，禁反射）")
            if name not in _ALLOWED_ATTRS and _FORBIDDEN_ATTR_RE.match(name):
                raise SandboxViolation(
                    f"禁止的操作 .{name}()（沙箱只读：不能读写文件、不能访问系统环境）")
        if isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise SandboxViolation(f"禁止使用内部名字 {node.id}")
            if node.id in _FORBIDDEN_NAMES:
                raise SandboxViolation(
                    f"禁止的操作 {node.id}（沙箱只读，禁反射/文件/进程）")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise SandboxViolation("禁止 global / nonlocal")


_RUNNER = r'''
import json, sys
payload = json.load(sys.stdin)
try:
    import pandas as pd
    df = pd.DataFrame(payload["rows"])
    safe_builtins = {"len": len, "range": range, "min": min, "max": max,
                     "sum": sum, "round": round, "sorted": sorted, "abs": abs,
                     "list": list, "dict": dict, "set": set, "str": str,
                     "int": int, "float": float, "bool": bool, "enumerate": enumerate,
                     "zip": zip, "tuple": tuple, "print": print}
    env = {"__builtins__": safe_builtins, "df": df, "pd": pd,
           "columns": list(df.columns), "result": None}
    exec(payload["code"], env)

    def jsonable(res):
        try:
            import numpy as np
            if isinstance(res, np.generic):
                return res.item()
            if isinstance(res, np.ndarray):
                return [jsonable(x) for x in res.tolist()]
        except Exception:
            pass
        if hasattr(res, "to_dict"):
            try:
                return res.to_dict()
            except Exception:
                return str(res)
        if isinstance(res, (list, tuple)):
            return [jsonable(x) for x in res]
        if isinstance(res, dict):
            return {str(k): jsonable(v) for k, v in res.items()}
        if isinstance(res, (str, int, float, bool)) or res is None:
            return res
        return str(res)

    out = {"ok": True, "result": jsonable(env.get("result"))}
except Exception as exc:
    out = {"ok": False, "error": str(exc)}
sys.stdout.write("\x1e" + json.dumps(out, ensure_ascii=False, default=str))
'''


def clean_env(workdir: str) -> dict[str, str]:
    """从零构造环境；绝不继承 Web 的 JWT/DB/AI/COS 配置。"""
    env = {}
    for key in ("PATH", "LANG", "LC_ALL", "TZ"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    env.update({
        "HOME": workdir,
        "TMPDIR": workdir,
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLBACKEND": "Agg",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
    })
    # 只传 sandbox 镜像自身的 Python 搜索路径，不从 Web 请求中接收任何路径。
    env["PYTHONPATH"] = os.pathsep.join(path for path in sys.path if path)
    return env


def _preexec(timeout: int, drop_uid: int | None, drop_gid: int | None):
    try:
        import resource
    except ImportError:
        resource = None

    def apply() -> None:
        if resource is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 2))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
            except (ValueError, OSError):
                pass
            if sys.platform.startswith("linux"):
                try:
                    memory = 640 * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
                except (ValueError, OSError):
                    pass
        if drop_uid is not None:
            if os.geteuid() != 0:
                raise PermissionError("沙箱 worker 必须以 root 启动后再将任务降权")
            os.setgroups([])
            if drop_gid is not None:
                os.setgid(drop_gid)
            os.setuid(drop_uid)

    return apply


def execute_payload(code: str, rows: list[dict], timeout: int = 10,
                    *, drop_uid: int | None = None,
                    drop_gid: int | None = None) -> dict:
    """仅供独立 sandbox worker 调用；Web 进程不得直接调用。"""
    code = strip_code_fences(code)
    static_guard(code)
    if not code:
        return {"ok": False, "error": "代码为空"}

    payload = json.dumps({"code": code, "rows": rows}, ensure_ascii=False, default=str)
    with tempfile.TemporaryDirectory(prefix="rh-sandbox-task-") as workdir:
        if drop_uid is not None and os.geteuid() == 0:
            os.chown(workdir, drop_uid, drop_gid if drop_gid is not None else drop_uid)
        try:
            process = subprocess.run(
                [sys.executable, "-c", _RUNNER],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env=clean_env(workdir),
                preexec_fn=_preexec(timeout, drop_uid, drop_gid),
                start_new_session=True,
            )
        except subprocess.TimeoutExpired:
            # subprocess.run 会 kill 并 wait 当前进程；AST 同时禁止 import/进程入口，
            # 容器 pids_limit 仍负责兜住未来可能出现的绕过。
            return {"ok": False, "error": f"执行超时（{timeout} 秒）——请缩小数据或计算范围"}
        except Exception as exc:
            return {"ok": False, "error": f"沙箱任务启动失败：{exc}"}

    output = process.stdout or ""
    if "\x1e" not in output:
        errors = (process.stderr or "").strip().splitlines()
        detail = errors[-1] if errors else "无返回"
        if "MemoryError" in (process.stderr or "") or process.returncode in (-9, 137):
            detail = "超出内存/资源上限，请缩小数据范围"
        return {"ok": False, "error": detail}
    printed, _, result_text = output.rpartition("\x1e")
    try:
        result = json.loads(result_text)
    except json.JSONDecodeError:
        return {"ok": False, "error": "沙箱返回结果解析失败"}
    if printed.strip():
        result["stdout"] = printed.strip()[:4000]
    return result
