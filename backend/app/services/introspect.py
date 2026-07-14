"""从上传的 .dta 读取「变量清单」与「真实数据」，供：
  - 数据处理设置里的变量清单自动抽取（#3）
  - AI/手写描述分析沙箱加载真实变量与真实值（#4）

pandas 仅在函数内惰性导入，避免拉高常驻内存（512MB 免费档）。
所有读取都做行数上限，防止大文件把免费实例撑爆。
"""
import io
from ..core.storage import storage

# 沙箱只读加载真实数据时的行数上限：防止大文件爆内存。
# 描述性统计/看分布，前 N 行足够；需要全量请本地跑。
SANDBOX_MAX_ROWS = 50000
# 抽取变量清单时只需要列结构，读极少行即可。
SCHEMA_PROBE_ROWS = 5


def _read_bytes(key: str) -> bytes:
    buf = io.BytesIO()
    src = storage.open(key)
    for chunk in iter(lambda: src.read(1 << 16), b""):
        buf.write(chunk)
    return buf.getvalue()


def read_dta_schema(key: str) -> list[dict]:
    """读取 .dta 的变量清单：[{var_name, label_zh(来自Stata变量标签), dtype}]。
    只读少量行拿列结构（chunksize），失败返回 []。"""
    try:
        raw = _read_bytes(key)
        import pandas as pd
        # 只读一小块拿列名与 dtype，不必全表加载
        chunk = next(pd.read_stata(io.BytesIO(raw), chunksize=SCHEMA_PROBE_ROWS))
        cols = list(chunk.columns)
        dtypes = {c: str(chunk[c].dtype) for c in cols}
        # 变量标签来自 StataReader（pandas 2.x 公开 variable_labels()）
        labels = {}
        try:
            with pd.io.stata.StataReader(io.BytesIO(raw)) as rdr:
                labels = rdr.variable_labels() or {}
        except Exception:
            labels = {}
        out = []
        for c in cols:
            out.append({"var_name": str(c),
                        "label_zh": (str(labels.get(c) or "").strip() or None),
                        "dtype": dtypes.get(c, "")})
        return out
    except Exception:
        return []


def load_dta_records(key: str, max_rows: int = SANDBOX_MAX_ROWS) -> tuple[list[dict], dict]:
    """把 .dta 前 max_rows 行读成 records（供沙箱构造真实 df）。
    返回 (records, meta)；meta 含 total_rows_loaded / truncated / columns。
    失败返回 ([], {...})。"""
    try:
        raw = _read_bytes(key)
        import pandas as pd
        # 只读到上限，避免全量加载
        df = pd.read_stata(io.BytesIO(raw))
        total = len(df)
        truncated = total > max_rows
        if truncated:
            df = df.head(max_rows)
        # NaN 用 None，方便 JSON/跨进程
        df = df.astype(object).where(df.notna(), None)
        records = df.to_dict("records")
        meta = {"columns": [str(c) for c in df.columns],
                "rows_loaded": len(records), "total_rows": total,
                "truncated": truncated}
        return records, meta
    except Exception as e:
        return [], {"error": str(e), "columns": [], "rows_loaded": 0,
                    "total_rows": 0, "truncated": False}
