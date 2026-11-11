#!/usr/bin/env python3
"""Offline, review-gated OCR lines -> harness layout.json; never runs a model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zlib

MAX_BYTES = 4 * 1024 * 1024
MAX_LINES = 4096
MAX_LINE_CHARS = 32768
DOC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def record_digest(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _formula(text):
    for left, right in (("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")):
        if text.startswith(left) and text.endswith(right) and len(text) > len(left) + len(right):
            inner = text[len(left):-len(right)].strip()
            if right in inner:
                raise ValueError("multiple_math_spans_require_review")
            return inner
    return text


def _table(lines, separator):
    if separator not in ("tab", "pipe"):
        raise ValueError("table_separator_required")
    rows = []
    for line in lines:
        if separator == "pipe":
            line = line.strip()
            if line.startswith("|"):
                line = line[1:]
            if line.endswith("|"):
                line = line[:-1]
        delimiter = "\t" if separator == "tab" else "|"
        # Escaped delimiters and Markdown separator rows need explicit human
        # normalization upstream; silently removing them would lose source data.
        if delimiter not in line or "\\" + delimiter in line:
            raise ValueError("ambiguous_table_delimiter")
        cells = [cell.strip() for cell in line.split(delimiter)]
        if any(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            raise ValueError("markdown_separator_requires_review")
        if any(len(cell) > 256 for cell in cells):
            raise ValueError("table_cell_too_large")
        rows.append(cells)
    if (not 2 <= len(rows) <= 64 or not 2 <= len(rows[0]) <= 32
            or any(len(row) != len(rows[0]) for row in rows) or not all(rows[0])):
        raise ValueError("table_must_be_rectangular_with_header")
    return rows


def read_source_image(path):
    """Bind bounded PNG bytes and IHDR dimensions, without decoding/cropping.

    IHDR validation is not a full image-integrity or pixel-content check.
    """
    with open(path, "rb") as stream:
        image = stream.read(24 * 1024 * 1024 + 1)
    if len(image) > 24 * 1024 * 1024:
        raise ValueError("source_image_too_large")
    if (len(image) < 33 or image[:8] != b"\x89PNG\r\n\x1a\n"
            or image[8:16] != b"\x00\x00\x00\x0dIHDR"
            or zlib.crc32(image[12:29]) != struct.unpack(">I", image[29:33])[0]):
        raise ValueError("source_image_requires_png_ihdr")
    width, height = struct.unpack(">II", image[16:24])
    metadata = {"sha256": hashlib.sha256(image).hexdigest(), "width": width,
                "height": height, "format": "png", "file": "source.png"}
    _validate_image(metadata)
    return image, metadata


def _validate_image(image):
    if (not isinstance(image, dict) or image.get("format") != "png"
            or image.get("file") != "source.png"
            or not isinstance(image.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", image["sha256"])
            or any(type(image.get(key)) is not int or not 1 <= image[key] <= 32768
                   for key in ("width", "height"))):
        raise ValueError("invalid_source_image_metadata")


def _validate_bbox(bbox, image):
    if (not isinstance(bbox, list) or len(bbox) != 4
            or any(type(value) is not int for value in bbox)):
        raise ValueError("bbox_requires_four_integer_pixels")
    x0, y0, x1, y1 = bbox
    if not (0 <= x0 < x1 <= image["width"] and 0 <= y0 < y1 <= image["height"]):
        raise ValueError("bbox_outside_source_image")


def _ocr_review_items(record):
    """Copy only bounded, objective OCR diagnostics; never import confidence."""
    items = record.get("review_items", [])
    if not isinstance(items, list) or len(items) > MAX_LINES + 8:
        raise ValueError("invalid_ocr_review_items")
    result = []
    for item in items:
        if (not isinstance(item, dict) or not isinstance(item.get("reason"), str)
                or not item["reason"].strip() or len(item["reason"]) > 200):
            raise ValueError("invalid_ocr_review_item")
        scope = item.get("scope", "line" if "line" in item else "record")
        if scope not in ("record", "line"):
            raise ValueError("invalid_ocr_review_scope")
        copied = {"reason": item["reason"], "scope": scope}
        if scope == "line":
            number = item.get("line")
            if type(number) is not int or not 1 <= number <= MAX_LINES:
                raise ValueError("invalid_ocr_review_line")
            copied["line"] = number
        if "text" in item:
            if not isinstance(item["text"], str) or len(item["text"]) > MAX_LINE_CHARS:
                raise ValueError("invalid_ocr_review_text")
            copied["text"] = item["text"]
        result.append(copied)
    return result


def convert(record, review=None, *, doc, page=1, source_image=None):
    """Return candidate layout only when every OCR line has a valid decision.

    Review is an operator attestation, not proof of a person's identity or of
    mathematical correctness. No confidence scores or image boxes are inferred.
    """
    if not isinstance(doc, str) or not DOC_ID.fullmatch(doc) or doc in (".", ".."):
        raise ValueError("invalid_document_id")
    if type(page) is not int or not 1 <= page <= 100000:
        raise ValueError("invalid_page")
    if not isinstance(record, dict):
        raise ValueError("ocr_record_must_be_object")
    digest = record_digest(record)
    result = {"schema_version": 1, "status": "NEEDS_HUMAN", "record_sha256": digest,
              "layout": None, "review_items": [], "rejected_lines": []}
    if source_image is not None:
        _validate_image(source_image)
        result["source_image"] = dict(source_image)
    if review is not None:
        if not isinstance(review, dict):
            raise ValueError("invalid_or_stale_review")
        decisions = review.get("decisions")
        has_regions = "source_image_sha256" in review or (isinstance(decisions, list) and any(
            isinstance(item, dict) and "bbox" in item for item in decisions))
        if source_image is None and has_regions:
            raise ValueError("source_image_required_for_regions")
        if source_image is not None and review.get("source_image_sha256") != source_image["sha256"]:
            raise ValueError("stale_source_image_review")
    signals = _ocr_review_items(record)
    if "output_complete" in record and record["output_complete"] is not None and type(record["output_complete"]) is not bool:
        raise ValueError("invalid_ocr_completion_metadata")
    if "candidate_lines_truncated" in record and type(record["candidate_lines_truncated"]) is not bool:
        raise ValueError("invalid_ocr_diagnostic_metadata")
    finish = record.get("finish_reason")
    if finish is not None and not isinstance(finish, str):
        raise ValueError("invalid_ocr_finish_reason")
    derived = []
    if "output_complete" in record and record["output_complete"] is not True:
        derived.append("incomplete_output" if record["output_complete"] is False else "completion_unconfirmed")
    if record.get("candidate_lines_truncated") is True:
        derived.append("text_limits_exceeded")
    if finish == "length":
        derived.append("incomplete_output")
    elif finish == "content_filter":
        derived.append("refused_output")
    elif finish not in (None, "stop"):
        derived.append("completion_unconfirmed")
    for cause in derived:
        if not any(item["reason"] == cause for item in signals):
            signals.append({"reason": cause, "scope": "record"})
    if record.get("status") != "OK" or signals:
        reason = record.get("reason")
        summary = {"reason": "ocr_not_ok" if record.get("status") != "OK" else "ocr_review_required",
                   "ocr_status": record.get("status")}
        if isinstance(reason, str) and reason:
            summary["ocr_reason"] = reason[:200]
        result["review_items"] = [summary, *signals]
        excerpt = record.get("raw_response")
        if isinstance(excerpt, str):
            result["diagnostic_excerpt"] = excerpt[:1024]
            result["diagnostic_excerpt_truncated"] = len(excerpt) > 1024 or record.get("response_truncated") is True
        return result
    lines = record.get("lines")
    if (not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES
            or any(not isinstance(line, str) or not line.strip() or len(line) > MAX_LINE_CHARS
                   or any(ord(char) < 32 and char != "\t" for char in line) or "\x7f" in line for line in lines)):
        raise ValueError("invalid_ocr_lines")
    if review is None:
        result["review_items"] = [{"line": i, "text": text, "reason": "unreviewed"}
                                  for i, text in enumerate(lines, 1)]
        return result
    if (not isinstance(review, dict) or review.get("record_sha256") != digest
            or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
            or len(review["reviewer"]) > 200 or not isinstance(review.get("decisions"), list)
            or len(review["decisions"]) > MAX_LINES):
        raise ValueError("invalid_or_stale_review")
    covered, nodes = set(), []
    for decision in review["decisions"]:
        if not isinstance(decision, dict):
            raise ValueError("invalid_review_decision")
        start, end, action = (decision.get(key) for key in ("start_line", "end_line", "action"))
        if (type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines)
                or action not in ("accept", "reject")):
            raise ValueError("invalid_review_range_or_action")
        indices = set(range(start, end + 1))
        if covered & indices:
            raise ValueError("overlapping_review_ranges")
        covered |= indices
        selected = lines[start - 1:end]
        if "bbox" in decision:
            _validate_bbox(decision["bbox"], source_image)
        if action == "reject":
            reason = decision.get("reason")
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
                raise ValueError("rejection_reason_required")
            result["rejected_lines"].append({"start_line": start, "end_line": end,
                                             "text": selected, "reason": reason})
            if "bbox" in decision:
                result["rejected_lines"][-1]["bbox"] = list(decision["bbox"])
            continue
        if source_image is not None and "bbox" not in decision:
            result["review_items"].append({"start_line": start, "end_line": end,
                                            "text": selected, "reason": "source_region_required"})
            continue
        kind = decision.get("type")
        if kind not in ("formula", "table", "text"):
            raise ValueError("explicit_node_type_required")
        try:
            if kind == "table":
                data = {"rows": _table(selected, decision.get("separator"))}
            else:
                if start != end:
                    raise ValueError("formula_and_text_require_single_line")
                data = {"latex": _formula(selected[0])} if kind == "formula" else {"text": selected[0]}
                if kind == "formula" and not data["latex"].strip():
                    raise ValueError("empty_formula")
        except ValueError as exc:
            result["review_items"].append({"start_line": start, "end_line": end,
                                            "text": selected, "reason": str(exc)})
            continue
        nodes.append({"id": f"ocr-{start:04d}-{end:04d}", "type": kind, "page": page, "data": data,
                      "ocr_source": {"record_sha256": digest, "start_line": start, "end_line": end,
                                     "text": selected, "reviewer": review["reviewer"]}})
        if source_image is not None:
            nodes[-1]["ocr_source"]["region"] = {
                "image_sha256": source_image["sha256"], "bbox": list(decision["bbox"]),
                "coordinate_system": "top_left_pixel_xyxy_half_open",
                "annotation_source": "operator_provided"}
    result["review_items"].extend({"line": i, "text": text, "reason": "unreviewed"}
                                  for i, text in enumerate(lines, 1) if i not in covered)
    if not nodes and not result["review_items"]:
        result["review_items"].append({"reason": "no_accepted_nodes"})
    if not result["review_items"]:
        result.update(status="OK", layout={"doc": doc, "source": "reviewed OCR text candidates",
                      "ocr_record_sha256": digest, "reviewer": review["reviewer"],
                      "nodes": sorted(nodes, key=lambda node: node["ocr_source"]["start_line"])})
        if source_image is not None:
            result["layout"]["source_image"] = dict(source_image)
    return result


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("input_too_large")
    # Reject duplicate keys and non-finite numbers rather than hashing an
    # ambiguous review document differently from the operator's JSON parser.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("non_finite_json_number")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", help="one OCR JSON record (a single JSONL record is also valid)")
    parser.add_argument("--review", help="hash-bound operator review JSON; omit to generate a review template")
    parser.add_argument("--source-image", type=Path, help="optional source PNG; enables hash-bound operator pixel regions")
    parser.add_argument("--doc", required=True, help="stable ASCII document id")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True, help="new sample directory; never overwritten")
    args = parser.parse_args(argv)
    try:
        record = _load(args.record)
        review = _load(args.review) if args.review else None
        image_bytes, image_metadata = read_source_image(args.source_image) if args.source_image else (None, None)
        result = convert(record, review, doc=args.doc, page=args.page, source_image=image_metadata)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        def save(name, value):
            (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        save("review.json", result)
        if image_bytes is not None:
            (args.output_dir / "source.png").write_bytes(image_bytes)
        if review is None:
            template = {"record_sha256": result["record_sha256"], "reviewer": "", "decisions": []}
            if image_metadata is not None:
                template["source_image_sha256"] = image_metadata["sha256"]
            save("review-template.json", template)
        if result["layout"] is not None:
            save("layout.json", result["layout"])
        print(json.dumps({"status": result["status"], "review_items": len(result["review_items"]),
                          "layout_created": result["layout"] is not None}))
        return 0 if result["status"] == "OK" else 1
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"conversion failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
