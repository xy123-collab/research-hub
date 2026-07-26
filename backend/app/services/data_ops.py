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
             f"* 唯一ID变量：{unique_id_var}",
             "* 每项先检查唯一匹配和当前值；assert 失败时 Stata 会停止，避免静默误改。"]
    for it in items:
        uid = str(it["uid_value"]).replace('"', '""')
        v = str(it["var_name"]).strip()
        old = str(it.get("current_value") or "").replace('"', '""')
        val = str(it.get("suggested_value") or "").replace('"', '""')
        if it.get("is_new_officer"):
            lines.extend([
                "",
                f"* [人工处理：新增官员] {unique_id_var}={uid}",
                "* 当前原始数据中没有该 ID；系统不会自动追加字段不完整的空记录。",
                f"* 待人工补全官员记录后，将 {v} 设置为：{val}",
            ])
            continue
        lines.extend([
            "",
            f"* 勘误 #{it.get('bug_id', '')}·第 {it.get('item_seq', '')} 项",
            f'capture confirm numeric variable {unique_id_var}',
            "if !_rc {",
            f'    count if {unique_id_var} == real("{uid}")',
            "    assert r(N) == 1",
            f"    capture confirm numeric variable {v}",
            "    if !_rc {",
            f'        assert {v} == real("{old}") if {unique_id_var} == real("{uid}")',
            f'        replace {v} = real("{val}") if {unique_id_var} == real("{uid}")',
            "    }",
            "    else {",
            f'        assert strtrim({v}) == "{old}" if {unique_id_var} == real("{uid}")',
            f'        replace {v} = "{val}" if {unique_id_var} == real("{uid}")',
            "    }",
            "}",
            "else {",
            f'    count if strtrim({unique_id_var}) == "{uid}"',
            "    assert r(N) == 1",
            f"    capture confirm numeric variable {v}",
            "    if !_rc {",
            f'        assert {v} == real("{old}") if strtrim({unique_id_var}) == "{uid}"',
            f'        replace {v} = real("{val}") if strtrim({unique_id_var}) == "{uid}"',
            "    }",
            "    else {",
            f'        assert strtrim({v}) == "{old}" if strtrim({unique_id_var}) == "{uid}"',
            f'        replace {v} = "{val}" if strtrim({unique_id_var}) == "{uid}"',
            "    }",
            "}",
        ])
    return "\n".join(lines) + "\n"


class CorrectionPreconditionError(ValueError):
    """数据已变化或唯一 ID 不再唯一时中止整批自动应用。"""


def _canonical_scalar(value, numeric: bool) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if not numeric:
        return text
    try:
        from decimal import Decimal, InvalidOperation
        return format(Decimal(text).normalize(), "f")
    except (InvalidOperation, ValueError):
        return text


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
        uid_numeric = pd.api.types.is_numeric_dtype(df[unique_id_var])
        key_values = df[unique_id_var].map(lambda x: _canonical_scalar(x, uid_numeric))
        planned = []
        problems = []
        # 先验证整批，再做任何赋值，保证失败时不产生半成品。
        for it in items:
            v = it["var_name"]
            if v not in df.columns:
                problems.append(f"勘误#{it.get('bug_id')}：变量 {v} 不存在")
                continue
            uid = _canonical_scalar(it["uid_value"], uid_numeric)
            mask = key_values == uid
            matches = int(mask.sum())
            if matches != 1:
                problems.append(
                    f"勘误#{it.get('bug_id')}：{unique_id_var}={it['uid_value']} "
                    f"匹配到 {matches} 条，要求恰好 1 条")
                continue
            col = df[v]
            value_numeric = pd.api.types.is_numeric_dtype(col)
            actual = _canonical_scalar(col.loc[mask].iloc[0], value_numeric)
            expected = _canonical_scalar(it.get("current_value"), value_numeric)
            if actual != expected:
                problems.append(
                    f"勘误#{it.get('bug_id')}：{v} 当前值已变为「{actual}」，"
                    f"不再等于提交时的「{expected}」")
                continue
            newval = it["suggested_value"]
            if value_numeric:
                try:
                    newval = pd.to_numeric(newval)
                except Exception:
                    problems.append(
                        f"勘误#{it.get('bug_id')}：建议值「{newval}」不能写入数值变量 {v}")
                    continue
            planned.append((it, mask, v, newval))
        if problems:
            raise CorrectionPreconditionError("；".join(problems))
        applied = []
        for it, mask, v, newval in planned:
            df.loc[mask, v] = newval
            applied.append(it["seq"])
        out = io.BytesIO()
        df.to_stata(out, write_index=False, version=118)
        return out.getvalue(), "server", script, applied
    except CorrectionPreconditionError:
        raise
    except Exception:
        return None, "script", script, []
