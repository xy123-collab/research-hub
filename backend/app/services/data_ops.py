"""数据处理：一键脱敏、一键应用勘误到上一版数据。

策略（用户选「两者结合」）：小数据在服务器端真读写 .dta；文件过大或
管理员设为 script_only 或处理失败时，回退为「生成修改脚本」供本地运行。
pandas 仅在函数内惰性导入，避免拉高常驻内存。
"""
import io
import hashlib
from ..core.storage import storage

# 服务器端处理的体量上限（字节）。超过则回退脚本，保护 512MB 免费档。
SERVER_APPLY_MAX_BYTES = 40 * 1024 * 1024


def _read_bytes(key: str) -> bytes:
    buf = io.BytesIO()
    src = storage.open(key)
    for chunk in iter(lambda: src.read(1 << 16), b""):
        buf.write(chunk)
    return buf.getvalue()


def _too_big(raw: bytes) -> bool:
    return len(raw) > SERVER_APPLY_MAX_BYTES


# ---------------- 脱敏 ----------------
def desensitize_script(rules: list[dict], unique_id_var: str | None) -> str:
    """生成 Stata 脱敏 do 文件文本（本地运行）。"""
    lines = ["* 自动生成的脱敏脚本（在原始数据上运行后另存为脱敏版）",
             "* 规则：keep=保留 drop=删除 hash=哈希替换 bucket=数值分桶"]
    for r in rules:
        v, act = r["var_name"], r.get("mask_action", "keep")
        if act == "drop":
            lines.append(f"capture drop {v}")
        elif act == "hash":
            lines.append(f"* 对 {v} 做不可逆编码：")
            lines.append(f"egen _h_{v} = group({v})")
            lines.append(f"drop {v}")
            lines.append(f"rename _h_{v} {v}")
        elif act == "bucket":
            size = r.get("bucket_size") or 5
            lines.append(f"replace {v} = floor({v}/{size})*{size}")
    return "\n".join(lines) + "\n"


def desensitize(raw_key: str, rules: list[dict], unique_id_var: str | None,
                script_only: bool = False):
    """返回 (new_bytes|None, source, script)。
    source: 'server' 表示已在服务器生成脱敏数据；'script' 表示回退脚本。"""
    script = desensitize_script(rules, unique_id_var)
    if script_only:
        return None, "script", script
    try:
        raw = _read_bytes(raw_key)
        if _too_big(raw):
            return None, "script", script
        from .introspect import read_table_df, _ext_of
        import pandas as pd
        df = read_table_df(raw, _ext_of(raw_key))
        for r in rules:
            v, act = r["var_name"], r.get("mask_action", "keep")
            if v not in df.columns:
                continue
            if act == "drop":
                df = df.drop(columns=[v])
            elif act == "hash":
                df[v] = df[v].astype(str).map(
                    lambda x: hashlib.sha1(x.encode("utf-8")).hexdigest()[:12])
            elif act == "bucket":
                size = r.get("bucket_size") or 5
                try:
                    df[v] = (pd.to_numeric(df[v], errors="coerce") // size) * size
                except Exception:
                    pass
        out = io.BytesIO()
        df.to_stata(out, write_index=False, version=118)
        return out.getvalue(), "server", script
    except Exception:
        return None, "script", script


# ---------------- 应用勘误 ----------------
def apply_corrections_script(items: list[dict], unique_id_var: str) -> str:
    lines = ["* 自动生成的勘误应用脚本（在上一版数据上运行后作为新版发布）",
             f"* 唯一ID变量：{unique_id_var}"]
    for it in items:
        uid = str(it["uid_value"]).replace('"', '')
        v = it["var_name"]
        val = str(it["suggested_value"]).replace('"', '')
        # 数值/字符串两种写法都给出，数值优先
        lines.append(f'replace {v} = "{val}" if {unique_id_var} == "{uid}"'
                     f"   // 若为数值请去掉引号：replace {v} = {val} if {unique_id_var}==...")
    return "\n".join(lines) + "\n"


def apply_corrections(base_key: str, items: list[dict], unique_id_var: str,
                      script_only: bool = False):
    """把已采纳勘误子项应用到 base 版本数据。
    返回 (new_bytes|None, source, script, applied_seqs)。按唯一ID+变量名定位单元格。"""
    script = apply_corrections_script(items, unique_id_var)
    if script_only or not unique_id_var:
        return None, "script", script, []
    try:
        raw = _read_bytes(base_key)
        if _too_big(raw):
            return None, "script", script, []
        from .introspect import read_table_df, _ext_of
        import pandas as pd
        df = read_table_df(raw, _ext_of(base_key))
        if unique_id_var not in df.columns:
            return None, "script", script, []
        key_str = df[unique_id_var].astype(str)
        applied = []
        for it in items:
            v = it["var_name"]
            if v not in df.columns:
                continue
            mask = key_str == str(it["uid_value"])
            if not mask.any():
                continue
            # 按列 dtype 尽量转换建议值
            newval = it["suggested_value"]
            col = df[v]
            try:
                if pd.api.types.is_numeric_dtype(col):
                    newval = pd.to_numeric(newval)
            except Exception:
                pass
            df.loc[mask, v] = newval
            applied.append(it["seq"])
        out = io.BytesIO()
        df.to_stata(out, write_index=False, version=118)
        return out.getvalue(), "server", script, applied
    except Exception:
        return None, "script", script, []
