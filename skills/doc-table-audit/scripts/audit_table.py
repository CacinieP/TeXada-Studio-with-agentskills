#!/usr/bin/env python3
"""表格审计：行列数一致性与数值交叉验算（合计行/列）。纯标准库，无外部依赖。

stdin JSONL: 每行一条
  {"id": "t-003",
   "rows": [["项目","金额"],["A","1.5"],["B","2.5"],["合计","4"]],
   "expected": {"n_rows": 4, "n_cols": 2,
                "totals": {"col:1": 4.0, "row:3": 4.0}}}

输出: JSONL {"id","status":"OK|RETRY|NEEDS_HUMAN","reason","detail"}

reason 枚举（对应 SKILL.md 的处置路径）:
  - shape_mismatch / sum_mismatch / bad_number → RETRY（上游可尝试提供候选）
  - bad_input / bad_expectation → NEEDS_HUMAN（输入契约错误，不应请求模型）
数值比较用 Decimal，容差 0；数值差异返回 RETRY，未解决时由上游转人工。
当前无图像重提取，只接受完整的十进制数字单元格；单位、百分比与会计括号需人工处理。

两条校验线：
  A. 表内自洽 —— 末行若为合计行（首格含 合计/总计/total），其各列数值必须等于数据行该列之和
  B. 与基准对照 —— expected.totals 提供时，同样与数据行之和比对
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, localcontext

_NUM_RE = re.compile(r"[+\-]?(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]*)?|\.[0-9]+)")


def to_decimal(cell: str):
    """只接受整个单元格为有限十进制数，不从单位或表达式中猜取数字。"""
    if isinstance(cell, bool) or not isinstance(cell, (str, int, float, Decimal)):
        return None
    text = str(cell).strip().replace("，", ",")
    if not _NUM_RE.fullmatch(text):
        return None
    try:
        value = Decimal(text.replace(",", ""))
        return value if value.is_finite() else None
    except InvalidOperation:
        return None


def exact_sum(values):
    """Set enough precision for the supplied finite decimal strings, including carries."""
    if not values:
        return None
    with localcontext() as context:
        context.prec = max(28, sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent)
                                   for v in values) + 2)
        return sum(values, Decimal(0))


def audit(rec: dict):
    if not isinstance(rec, dict):
        return "NEEDS_HUMAN", "bad_input", "record must be an object"
    rows = rec.get("rows")
    expected = rec.get("expected", {})
    if not isinstance(rows, list) or not rows or any(not isinstance(row, list) for row in rows):
        return "NEEDS_HUMAN", "bad_input", "rows must be a nonempty list of row lists"
    if not rows[0] or not isinstance(expected, dict):
        return "NEEDS_HUMAN", "bad_input", "header must be nonempty and expected must be an object"
    if any(isinstance(cell, (list, dict, bool)) for row in rows for cell in row):
        return "NEEDS_HUMAN", "bad_input", "cells must be scalar text or numbers"
    for name in ("n_rows", "n_cols"):
        if name in expected and (type(expected[name]) is not int or expected[name] <= 0):
            return "NEEDS_HUMAN", "bad_expectation", f"{name} must be a positive integer"
    totals = expected.get("totals", {})
    if not isinstance(totals, dict):
        return "NEEDS_HUMAN", "bad_expectation", "totals must be an object"

    # 1) 行列数
    if "n_rows" in expected and len(rows) != expected["n_rows"]:
        return "RETRY", "shape_mismatch", f"rows: got {len(rows)}, expect {expected['n_rows']}"
    if "n_cols" in expected and rows and any(len(r) != expected["n_cols"] for r in rows):
        bad = [i for i, r in enumerate(rows) if len(r) != expected["n_cols"]]
        return "RETRY", "shape_mismatch", f"col count mismatch at rows {bad}"
    if any(len(row) != len(rows[0]) for row in rows):
        return "RETRY", "shape_mismatch", "rows must have a consistent column count"

    # 2) 表内自洽：识别合计行（A 线）
    total_labels = ("合计", "总计", "total")
    has_total_row = bool(rows) and any(k in str(rows[-1][0]).strip().lower() for k in total_labels)
    data_rows = rows[1:-1] if has_total_row else rows[1:]
    if has_total_row and not data_rows:
        return "NEEDS_HUMAN", "bad_input", "a total row requires at least one data row after the header"

    if has_total_row:
        n_cols = len(rows[0])
        for j in range(1, n_cols):
            vals = []
            for r in data_rows:
                if j >= len(r):
                    return "RETRY", "shape_mismatch", f"col {j} missing in data row"
                d = to_decimal(r[j])
                if d is None:
                    return "RETRY", "bad_number", f"non-numeric cell in col {j}: {r[j]!r}"
                vals.append(d)
            got = exact_sum(vals)
            want = to_decimal(rows[-1][j]) if j < len(rows[-1]) else None
            if got is None or want is None:
                return "RETRY", "bad_number", f"total row col {j}: {rows[-1][j]!r}"
            if got != want:
                return "RETRY", "sum_mismatch", (
                    f"total row vs data rows, col {j}: row says {want}, data sums to {got}"
                )

    # 3) 与基准对照（B 线）
    for key, want in totals.items():
        if not isinstance(key, str):
            return "NEEDS_HUMAN", "bad_expectation", "totals keys must be strings"
        try:
            idx = int(key.split(":", 1)[1])
        except (ValueError, IndexError):
            return "NEEDS_HUMAN", "bad_expectation", f"unparseable totals key: {key}"

        if key.startswith("col:"):
            if idx < 0 or idx >= len(rows[0]):
                return "NEEDS_HUMAN", "bad_expectation", f"col index {idx} out of range"
            vals = []
            for r in data_rows:
                d = to_decimal(r[idx]) if idx < len(r) else None
                if d is None:
                    return "RETRY", "bad_number", f"non-numeric cell in col {idx}: {r[idx]!r}"
                vals.append(d)
            got = exact_sum(vals)
        elif key.startswith("row:"):
            if idx < 0 or idx >= len(rows):
                return "NEEDS_HUMAN", "bad_expectation", f"row index {idx} out of range"
            vals = []
            for c in rows[idx][1:]:
                d = to_decimal(c)
                if d is None:
                    return "RETRY", "bad_number", f"non-numeric cell in row {idx}: {c!r}"
                vals.append(d)
            got = exact_sum(vals)
        else:
            return "NEEDS_HUMAN", "bad_expectation", f"unknown totals key: {key}"

        w = to_decimal(str(want))
        if w is None or got is None:
            return "RETRY", "bad_number", f"total {key}: expect={want!r} got_sum={got}"
        if got != w:
            return "RETRY", "sum_mismatch", f"total {key}: expect {w}, got {got}"

    return "OK", "", ""


def main() -> int:
    code = 0
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps({"id": None, "status": "NEEDS_HUMAN", "reason": "bad_input", "detail": str(e)}))
            code = 1
            continue
        status, reason, detail = audit(rec)
        print(json.dumps({"id": rec.get("id") if isinstance(rec, dict) else None, "status": status, "reason": reason, "detail": detail}))
        if status == "NEEDS_HUMAN":
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
