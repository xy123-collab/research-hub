"""只读分析沙箱：AI/手写分析代码在此执行——只读加载数据、禁网络、禁写回原表。
这是"看板 AI/手写分析不改原始值"的技术保证（见 5.7 / 十三章）。
一期为进程内受限执行示意；生产建议放独立容器 + seccomp + 只读挂载。"""
import multiprocessing as mp


_FORBIDDEN = ["open(", "to_csv", "to_stata", "to_pickle", "write", "os.", "sys.",
              "subprocess", "socket", "requests", "urllib", "shutil", "remove",
              "__import__", "eval(", "exec("]


class SandboxViolation(Exception):
    pass


def static_guard(code: str):
    lowered = code
    for f in _FORBIDDEN:
        if f in lowered:
            raise SandboxViolation(f"禁止的操作: {f}（沙箱只读，禁写回/禁网络）")


def _worker(code, df_records, q):
    try:
        import pandas as pd
        df = pd.DataFrame(df_records)  # 只读副本
        safe_builtins = {"len": len, "range": range, "min": min, "max": max,
                         "sum": sum, "round": round, "sorted": sorted, "abs": abs}
        env = {"__builtins__": safe_builtins, "df": df, "pd": pd, "result": None}
        exec(code, env)  # noqa: S102 — 已静态过滤 + 独立进程 + 无写权限
        res = env.get("result")
        if hasattr(res, "to_dict"):
            res = res.to_dict()
        q.put({"ok": True, "result": res})
    except Exception as e:
        q.put({"ok": False, "error": str(e)})


def run_readonly(code: str, df_records: list[dict], timeout: int = 10) -> dict:
    """在独立进程运行分析代码，超时保护。df_records 为只读聚合样本，不含敏感原始行。"""
    static_guard(code)
    q = mp.Queue()
    p = mp.Process(target=_worker, args=(code, df_records, q))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        return {"ok": False, "error": "执行超时"}
    return q.get() if not q.empty() else {"ok": False, "error": "无返回"}
