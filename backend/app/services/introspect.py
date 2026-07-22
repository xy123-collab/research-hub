"""从上传的数据文件读取「变量清单」与「真实数据」，供：
  - 数据处理设置里的变量清单自动抽取（#3）
  - AI/手写描述分析沙箱加载真实变量与真实值（#4）

支持格式：.dta（含 Stata 变量标签）/ .csv（自动识别 utf-8/gbk）/ .xlsx / .xls /
.parquet / .mat（v7.2 及以下，取首个二维数值矩阵）。
中文文件名、中文变量名均可正常读取（pandas 层面对 Unicode 透明）。

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


def _ext_of(key: str) -> str:
    return key.rsplit(".", 1)[-1].lower() if "." in (key or "") else ""


def read_table_df(raw: bytes, ext: str, nrows: int | None = None):
    """按格式把字节读成 DataFrame；nrows 用于只读前几行（探结构）。

    各格式读取失败都会抛异常，由调用方决定降级策略。"""
    import pandas as pd
    bio = io.BytesIO(raw)
    if ext == "dta":
        if nrows is None:
            return pd.read_stata(bio)
        return next(pd.read_stata(bio, chunksize=nrows))
    if ext == "csv":
        # 中文 Windows Excel 常存 GBK；utf-8 失败时回退 gb18030
        for enc in ("utf-8-sig", "gb18030"):
            try:
                bio.seek(0)
                return pd.read_csv(bio, encoding=enc, nrows=nrows)
            except (UnicodeDecodeError, UnicodeError):
                continue
        bio.seek(0)
        return pd.read_csv(bio, encoding="utf-8", encoding_errors="replace", nrows=nrows)
    if ext in ("xlsx", "xls"):
        return pd.read_excel(bio, nrows=nrows)
    if ext == "parquet":
        df = pd.read_parquet(bio)  # parquet 不支持 nrows，读后截断
        return df if nrows is None else df.head(nrows)
    if ext == "mat":
        # scipy.io.loadmat 支持 v7.2 及以下；v7.3(HDF5) 会抛 NotImplementedError
        from scipy.io import loadmat
        m = loadmat(io.BytesIO(raw))
        for k, v in m.items():
            if k.startswith("__"):
                continue
            if getattr(v, "ndim", 0) == 2 and getattr(v, "size", 0):
                if v.shape[1] == 1:
                    df = pd.DataFrame({k: v.ravel()})
                else:
                    df = pd.DataFrame(v, columns=[f"{k}_{i+1}" for i in range(v.shape[1])])
                return df if nrows is None else df.head(nrows)
        raise ValueError("MAT 文件中未找到二维数值矩阵变量（v7.3 HDF5 格式暂不支持，"
                         "请在 MATLAB 里 save(..., '-v7') 另存后再传）")
    raise ValueError(f"不支持的数据格式 .{ext}")


def read_table_schema(key: str) -> list[dict]:
    """读取数据文件的变量清单：[{var_name, label_zh(仅 .dta 有 Stata 标签), dtype}]。
    只读少量行拿列结构，失败返回 []。"""
    try:
        raw = _read_bytes(key)
        ext = _ext_of(key)
        chunk = read_table_df(raw, ext, nrows=SCHEMA_PROBE_ROWS)
        cols = [str(c) for c in chunk.columns]
        dtypes = {str(c): str(chunk[c].dtype) for c in chunk.columns}
        # 变量标签仅 Stata 格式带（pandas 2.x 公开 variable_labels()）
        labels = {}
        if ext == "dta":
            try:
                import pandas as pd
                with pd.io.stata.StataReader(io.BytesIO(raw)) as rdr:
                    labels = rdr.variable_labels() or {}
            except Exception:
                labels = {}
        return [{"var_name": c,
                 "label_zh": (str(labels.get(c) or "").strip() or None),
                 "dtype": dtypes.get(c, "")} for c in cols]
    except Exception:
        return []


def load_table_records(key: str, max_rows: int = SANDBOX_MAX_ROWS) -> tuple[list[dict], dict]:
    """把数据文件前 max_rows 行读成 records（供沙箱构造真实 df）。
    返回 (records, meta)；meta 含 total_rows_loaded / truncated / columns。
    失败返回 ([], {...})。"""
    try:
        raw = _read_bytes(key)
        df = read_table_df(raw, _ext_of(key))
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


# 兼容旧名（历史调用点），统一走多格式实现
def read_dta_schema(key: str) -> list[dict]:
    return read_table_schema(key)


def load_dta_records(key: str, max_rows: int = SANDBOX_MAX_ROWS) -> tuple[list[dict], dict]:
    return load_table_records(key, max_rows)
