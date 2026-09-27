#!/usr/bin/env python3
"""表格审计：行列数一致性与数值交叉验算（合计行/列）。纯标准库，无外部依赖。

stdin JSONL: 每行一条
  {"id": "t-003",
   "rows": [["项目","金额"],["A","1.5"],["B","2.5"],["合计","4"]],
   "expected": {"n_rows": 4, "n_cols": 2,
                "totals": {"col:1": 4.0, "row:3": 4.0}}}

输出: JSONL {"id","status":"OK|RETRY|NEEDS_HUMAN","reason","detail"}

reason 枚举（对应 SKILL.md 的处置路径）:
  - shape_mismatch → RETRY（重新提取该表区域）
  - sum_mismatch   → RETRY（重裁剪重识别，两次失败后上游转 NEEDS_HUMAN）
  - bad_number     → RETRY（单元格非数值，重识别该单元格）
数值比较用 Decimal 精确语义，容差 0（四舍五入差异走 NEEDS_HUMAN 由人工判）。

两条校验线：
  A. 表内自洽 —— 末行若为合计行（首格含 合计/总计/total），其各列数值必须等于数据行该列之和
  B. 与基准对照 —— expected.totals 提供时，同样与数据行之和比对
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation

_NUM_RE = re.compile(r"[+\-]?[0-9][0-9,，.（）()%]*")


def to_decimal(cell: str):
    """从单元格提取首个数值；无数值返回 None。"""
    if cell is None:
        return None
    m = _NUM_RE.search(str(cell).replace(" ", ""))
    if not m:
        return None
    s = m.group(0).replace(",", "").replace("，", "")
    s = s.replace("（", "-").replace("(", "-").replace("）", "").replace(")", "")
    s = s.rstrip("%")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def audit(rec: dict):
    rows = rec.get("rows") or []
    expected = rec.get("expected") or {}

    # 1) 行列数
    if "n_rows" in expected and len(rows) != expected["n_rows"]:
        return "RETRY", "shape_mismatch", f"rows: got {len(rows)}, expect {expected['n_rows']}"
    if "n_cols" in expected and rows and any(len(r) != expected["n_cols"] for r in rows):
        bad = [i for i, r in enumerate(rows) if len(r) != expected["n_cols"]]
        return "RETRY", "shape_mismatch", f"col count mismatch at rows {bad}"

    # 2) 表内自洽：识别合计行（A 线）
    total_labels = ("合计", "总计", "total")
    has_total_row = bool(rows) and any(k in str(rows[-1][0]).strip().lower() for k in total_labels)
    data_rows = rows[1:-1] if (has_total_row and len(rows) > 2) else rows[1:]

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
            got = sum(vals) if vals else None
            want = to_decimal(rows[-1][j]) if j < len(rows[-1]) else None
            if got is None or want is None:
                return "RETRY", "bad_number", f"total row col {j}: {rows[-1][j]!r}"
            if got != want:
                return "RETRY", "sum_mismatch", (
                    f"total row vs data rows, col {j}: row says {want}, data sums to {got}"
                )

    # 3) 与基准对照（B 线）
    totals = expected.get("totals") or {}
    for key, want in totals.items():
        try:
            idx = int(key.split(":", 1)[1])
        except (ValueError, IndexError):
            return "NEEDS_HUMAN", "bad_expectation", f"unparseable totals key: {key}"

        if key.startswith("col:"):
            if idx >= (len(rows[0]) if rows else 0):
                return "NEEDS_HUMAN", "bad_expectation", f"col index {idx} out of range"
            vals = []
            for r in data_rows:
                d = to_decimal(r[idx]) if idx < len(r) else None
                if d is None:
                    return "RETRY", "bad_number", f"non-numeric cell in col {idx}: {r[idx]!r}"
                vals.append(d)
            got = sum(vals) if vals else None
        elif key.startswith("row:"):
            if idx >= len(rows):
                return "NEEDS_HUMAN", "bad_expectation", f"row index {idx} out of range"
            vals = []
            for c in rows[idx][1:]:
                d = to_decimal(c)
                if d is None:
                    return "RETRY", "bad_number", f"non-numeric cell in row {idx}: {c!r}"
                vals.append(d)
            got = sum(vals) if vals else None
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
            continue
        status, reason, detail = audit(rec)
        print(json.dumps({"id": rec.get("id"), "status": status, "reason": reason, "detail": detail}))
        if status == "NEEDS_HUMAN":
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
