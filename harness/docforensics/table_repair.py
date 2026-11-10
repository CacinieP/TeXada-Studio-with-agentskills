"""Source-scope guard for table grid candidates (issue #25).

A table candidate may pass ``audit_table.py`` while silently rewriting a data
cell so that a wrong total "matches". The checker cannot see that, so the host
compares the candidate with the original grid and authorizes only three edits:

- ``recompute_total_row``: change numeric cells of an existing final total row;
- ``complete_total_row``: fill missing cells of a short existing total row;
- ``append_total_row``: append one total row when no total row exists and
  ``expected.n_rows`` explicitly declares exactly one more row.

The header, every data row and the total label are authoritative source data.
The guard never authorizes an edit the checker rejects; both must pass.
"""

import importlib.util
import os

_AUDIT = os.path.join(os.path.dirname(__file__), "..", "..", "skills", "doc-table-audit", "scripts", "audit_table.py")
_spec = importlib.util.spec_from_file_location("_texada_table_audit", os.path.abspath(_AUDIT))
_audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_audit)

TOTAL_LABELS = ("合计", "总计", "total")


def is_total_row(row):
    return (isinstance(row, list) and bool(row)
            and any(label in str(row[0]).strip().lower() for label in TOTAL_LABELS))


def _valid_grid(rows):
    return (isinstance(rows, list) and bool(rows)
            and all(isinstance(row, list) for row in rows)
            and all(isinstance(cell, (str, int, float)) and not isinstance(cell, bool)
                    for row in rows for cell in row))


def _reject(reason, **location):
    return {"allowed": False, "reason": reason, "method": None, **location}


def _first_difference(original_row, candidate_row):
    for index in range(max(len(original_row), len(candidate_row))):
        left = original_row[index] if index < len(original_row) else None
        right = candidate_row[index] if index < len(candidate_row) else None
        if left != right:
            return index
    return None


def _check_total_cells(candidate_row, width, row_index):
    if len(candidate_row) != width:
        return _reject("table_scope_violation", row_index=row_index)
    for col, cell in enumerate(candidate_row[1:], start=1):
        if _audit.to_decimal(cell) is None:
            return _reject("table_total_non_numeric", row_index=row_index, col_index=col)
    return None


def assess_table_candidate(original, candidate, expected=None):
    """Return an auditable verdict; ``allowed`` is True only for the scoped edits."""
    if not _valid_grid(original) or not original[0]:
        return _reject("bad_original")
    if not _valid_grid(candidate):
        return _reject("bad_candidate_type")
    if candidate == original:
        return _reject("unchanged_candidate")
    if candidate[0] != original[0]:
        return _reject("table_header_modified", row_index=0, col_index=_first_difference(original[0], candidate[0]))
    width = len(original[0])
    expected = expected if isinstance(expected, dict) else {}

    if is_total_row(original[-1]) and len(original) > 1:
        total = len(original) - 1
        if len(candidate) != len(original):
            return _reject("table_scope_violation", row_index=min(len(original), len(candidate)))
        for row in range(1, total):
            col = _first_difference(original[row], candidate[row])
            if col is not None:
                return _reject("table_data_modified", row_index=row, col_index=col)
        if not candidate[total] or candidate[total][0] != original[total][0]:
            return _reject("table_total_label_modified", row_index=total, col_index=0)
        problem = _check_total_cells(candidate[total], width, total)
        if problem:
            return problem
        method = "complete_total_row" if len(original[total]) < width else "recompute_total_row"
        return {"allowed": True, "reason": "authorized_table_scope", "method": method, "row_index": total}

    # No total row: every original row is data and must be copied exactly.
    for row in range(1, min(len(original), len(candidate))):
        col = _first_difference(original[row], candidate[row])
        if col is not None:
            return _reject("table_data_modified", row_index=row, col_index=col)
    declared = expected.get("n_rows")
    if (len(candidate) == len(original) + 1 and type(declared) is int and declared == len(candidate)
            and is_total_row(candidate[-1])):
        problem = _check_total_cells(candidate[-1], width, len(original))
        if problem:
            return problem
        return {"allowed": True, "reason": "authorized_table_scope", "method": "append_total_row",
                "row_index": len(original)}
    return _reject("table_scope_violation", row_index=min(len(original), len(candidate)))
