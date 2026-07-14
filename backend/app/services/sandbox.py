"""只读分析沙箱：AI/手写分析代码在此执行——只读加载数据、禁网络、禁写回原表。
这是"看板 AI/手写分析不改原始值"的技术保证（见 5.7 / 十三章）。
一期为进程内受限执行示意；生产建议放独立容器 + seccomp + 只读挂载。"""
import re
import multiprocessing as mp


_FORBIDDEN = ["open(", "to_csv", "to_stata", "to_pickle", "write", "os.", "sys.",
              "subprocess", "socket", "requests", "urllib", "shutil", "remove",
              "__import__", "eval(", "exec("]


class SandboxViolation(Exception):
    pass


def strip_code_fences(code: str) -> str:
    """AI 常把代码包在 ```python ... ``` 里，直接 exec 会报 invalid syntax。
    这里剥掉 markdown 围栏与语言标注，保留纯代码。"""
    if not code:
        return ""
    s = code.strip()
    if "```" in s:
        # 抓第一段 ``` 代码块
        m = re.search(r"```(?:[a-zA-Z0-9_+-]*)?\s*\n?(.*?)```", s, re.S)
        if m:
            s = m.group(1)
        else:
            s = s.replace("```", "")
    return s.strip()


def static_guard(code: str):
    lowered = code
    for f in _FORBIDDEN:
        if f in lowered:
            raise SandboxViolation(f"禁止的操作: {f}（沙箱只读，禁写回/禁网络）")


def _jsonable(res):
    """把 numpy / pandas 结果转成能安全跨进程+JSON 的普通对象。"""
    try:
        import numpy as np
        if isinstance(res, np.generic):
            return res.item()
        if isinstance(res, np.ndarray):
            return [_jsonable(x) for x in res.tolist()]
    except Exception:
        pass
    if hasattr(res, "to_dict"):
        try:
            return res.to_dict()
        except Exception:
            return str(res)
    if isinstance(res, (list, tuple)):
        return [_jsonable(x) for x in res]
    if isinstance(res, dict):
        return {str(k): _jsonable(v) for k, v in res.items()}
    if isinstance(res, (str, int, float, bool)) or res is None:
        return res
    return str(res)


def _worker(code, df_records, q):
    try:
        import pandas as pd
        df = pd.DataFrame(df_records)  # 只读副本（真实数据 / 汇总，取决于调用方）
        safe_builtins = {"len": len, "range": range, "min": min, "max": max,
                         "sum": sum, "round": round, "sorted": sorted, "abs": abs,
                         "list": list, "dict": dict, "set": set, "str": str,
                         "int": int, "float": float, "bool": bool, "enumerate": enumerate,
                         "zip": zip, "tuple": tuple, "print": print}
        env = {"__builtins__": safe_builtins, "df": df, "pd": pd,
               "columns": list(df.columns), "result": None}
        exec(code, env)  # noqa: S102 — 已静态过滤 + 独立进程 + 无写权限
        q.put({"ok": True, "result": _jsonable(env.get("result"))})
    except Exception as e:
        q.put({"ok": False, "error": str(e)})


def run_readonly(code: str, df_records: list[dict], timeout: int = 10) -> dict:
    """在独立进程运行分析代码，超时保护。df_records 可为真实数据行或聚合样本。"""
    code = strip_code_fences(code)
    static_guard(code)
    if not code.strip():
        return {"ok": False, "error": "代码为空"}
    q = mp.Queue()
    p = mp.Process(target=_worker, args=(code, df_records, q))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "执行超时（10 秒）——数据量或计算过大，请缩小范围"}
    return q.get() if not q.empty() else {"ok": False, "error": "无返回"}
