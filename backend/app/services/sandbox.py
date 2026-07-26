"""只读分析沙箱：AI/手写分析代码在此执行——只读加载数据、禁网络、禁写回原表。
这是"看板 AI/手写分析不改原始值"的技术保证（见 5.7 / 十三章）。

—— 2026-07 整改（迁移清单 A4）——
原实现有两个致命问题：
1. 用 `multiprocessing.Process` fork 子进程，子进程**继承父进程的环境变量**。
   而 `/proc/self/environ` 是普通文件，`pd.read_csv('/proc/self/environ')` 就能读到
   JWT_SECRET（拿到即可伪造总管理员令牌）、DATABASE_URL、AI_API_KEY、存储密钥。
2. 静态检查是字符串黑名单，`read_csv` 不在名单里；就算加进去，
   `getattr(pd, 'read_'+'csv')` 也能绕过。黑名单不能作为安全边界。

现在改成两层：
- 【语法层】AST 白名单式检查：禁 import、禁一切双下划线属性/名字、
  禁 getattr/eval/exec/open/compile 等反射与 IO 入口、禁 pandas 的 read_*/to_*。
  基于语法树判断，拼字符串绕不过去（拼出来的名字没法在 AST 上变成属性访问）。
- 【进程层】用 `subprocess` 重新 execve 一个干净解释器：
  env 白名单（只留 PATH/LANG 等无害项，**不含任何密钥**）→ `/proc/self/environ`
  里已经没有秘密可读；再叠 RLIMIT_FSIZE=0（完全无法写文件）、
  RLIMIT_AS（内存上限）、RLIMIT_CPU（CPU 上限）、工作目录切到空临时目录。

真正的最终形态仍是"独立容器 + --network none --read-only"（迁到阿里云后做），
但上面两层已经把"读走全部生产密钥"和"写服务器文件"这两条路堵死。
应急时把环境变量 ENABLE_ONLINE_ANALYSIS 设为 false，可一键关闭在线分析。
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile

from ..core.config import settings

# 反射 / IO / 进程相关的入口，一律不许出现在分析代码里
_FORBIDDEN_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "input", "breakpoint",
    "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir",
    "memoryview", "exit", "quit", "help", "super", "object", "type",
}
# 禁止的属性名：pandas 的读写 IO + 常见落盘/网络方法
_FORBIDDEN_ATTR_RE = re.compile(
    r"^(read_\w+|to_(csv|stata|pickle|excel|parquet|json|sql|hdf|feather|clipboard|latex|xml|orc)"
    r"|write\w*|system|popen|remove|unlink|rename|mkdir|rmdir|chdir|environ|getenv)$")
# 结果对象允许的转换方法（to_dict 白名单，避免被上面的 to_* 规则误伤）
_ALLOWED_ATTRS = {"to_dict", "to_list", "to_numpy", "to_frame", "to_string", "to_period",
                  "to_datetime", "to_timedelta", "to_records"}


class SandboxViolation(Exception):
    pass


def strip_code_fences(code: str) -> str:
    """AI 常把代码包在 ```python ... ``` 里，直接 exec 会报 invalid syntax。
    这里剥掉 markdown 围栏与语言标注，保留纯代码。"""
    if not code:
        return ""
    s = code.strip()
    if "```" in s:
        m = re.search(r"```(?:[a-zA-Z0-9_+-]*)?\s*\n?(.*?)```", s, re.S)
        if m:
            s = m.group(1)
        else:
            s = s.replace("```", "")
    return s.strip()


def static_guard(code: str):
    """AST 级检查。任何一条不合规直接拒绝执行，并给出人话原因。"""
    try:
        tree = ast.parse(code or "")
    except SyntaxError as e:
        raise SandboxViolation(f"代码语法错误：第 {e.lineno} 行 {e.msg}")

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


# 在子进程里跑的引导脚本：读 stdin 的 JSON（代码 + 数据），把结果写回 stdout。
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
    exec(payload["code"], env)   # noqa: S102 — AST 已过滤 + 独立干净进程 + 无写权限

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
except Exception as e:
    out = {"ok": False, "error": str(e)}
sys.stdout.write("\x1e" + json.dumps(out, ensure_ascii=False, default=str))
'''


def _clean_env(workdir: str) -> dict:
    """给子进程的环境变量白名单：只留跑 Python 必需的，绝不带任何密钥。

    这是修 `pd.read_csv('/proc/self/environ')` 的关键——子进程是重新 execve 的，
    `/proc/self/environ` 里就只有下面这几项。
    """
    keep = {}
    for k in ("PATH", "LANG", "LC_ALL", "TZ", "SSL_CERT_FILE"):
        if os.environ.get(k):
            keep[k] = os.environ[k]
    keep.update({"HOME": workdir, "TMPDIR": workdir, "PYTHONHASHSEED": "0",
                 "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg",
                 "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
    # 显式把父进程的 import 搜索路径传下去：环境是从零构建的，
    # 不这么做子进程可能找不到 pandas / dateutil（本地开发常把包装在 user site 里）。
    keep["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    return keep


def _limits(timeout: int):
    """子进程资源上限（POSIX）。RLIMIT_FSIZE=0 = 一个字节都写不出去。

    注意不要在这里调 os.setsid()：subprocess 的 start_new_session 已经做过，
    再调一次会 EPERM 把子进程直接搞挂。
    """
    try:
        import resource
    except ImportError:      # Windows 开发机：降级为不设限，靠 AST 检查 + 超时兜底
        return None

    def _apply():
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))                 # 禁止写文件
        resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 2))   # CPU 秒
        if sys.platform.startswith("linux"):
            # 只在 Linux 限地址空间：macOS 上设 RLIMIT_AS 会让 numpy/pandas 起不来
            try:
                resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
            except (ValueError, OSError):
                pass
    return _apply


def run_readonly(code: str, df_records: list[dict], timeout: int = 10) -> dict:
    """在**干净的独立进程**里运行分析代码，超时保护。df_records 可为真实数据行或聚合样本。"""
    if not settings.ENABLE_ONLINE_ANALYSIS:
        return {"ok": False, "error": "在线分析已由平台管理员暂时关闭，请稍后再试"}
    code = strip_code_fences(code)
    static_guard(code)
    if not code.strip():
        return {"ok": False, "error": "代码为空"}

    payload = json.dumps({"code": code, "rows": df_records}, ensure_ascii=False, default=str)
    with tempfile.TemporaryDirectory(prefix="rh-sandbox-") as workdir:
        try:
            proc = subprocess.run(
                # 关键在 env：这是一次全新的 execve，子进程的 /proc/self/environ
                # 里只有 _clean_env 给的那几项，没有 JWT_SECRET / DATABASE_URL / AI_API_KEY
                [sys.executable, "-c", _RUNNER],
                input=payload, capture_output=True, text=True, timeout=timeout,
                cwd=workdir, env=_clean_env(workdir), preexec_fn=_limits(timeout),
                start_new_session=True)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"执行超时（{timeout} 秒）——数据量或计算过大，请缩小范围"}
        except Exception as e:
            return {"ok": False, "error": f"沙箱启动失败：{e}"}

    # 用 \x1e 作分隔符，把用户代码里的 print 输出与结果 JSON 分开
    out = proc.stdout or ""
    if "\x1e" not in out:
        err = (proc.stderr or "").strip().splitlines()
        detail = err[-1] if err else "无返回"
        if "MemoryError" in (proc.stderr or "") or proc.returncode in (-9, 137):
            detail = "超出内存/资源上限，请缩小数据范围"
        return {"ok": False, "error": detail}
    stdout_text, _, result_text = out.rpartition("\x1e")
    try:
        res = json.loads(result_text)
    except json.JSONDecodeError:
        return {"ok": False, "error": "沙箱返回结果解析失败"}
    if stdout_text.strip():
        res["stdout"] = stdout_text.strip()[:4000]
    return res
