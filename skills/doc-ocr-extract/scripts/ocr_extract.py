#!/usr/bin/env python3
"""doc-ocr-extract: image → raw text candidate lines via a local vision model.

分而治之（ADR-017 对齐）：本脚本只把图片转成候选文本行，不判定数学语义、
不做修复、不写任何状态。候选必须经人工审阅后才可能进入文档。

输入（二选一）:
  - 命令行参数: ocr_extract.py image.png
  - stdin JSONL: {"id": "img-01", "image": "<base64 PNG>"}  每行一条
输出: JSONL  {"id", "status", "lines", "raw_response", "response_truncated",
             "model", "eval_count", "elapsed_seconds", "reason"}

约定（与 doc-formula-verify/scripts/verify.py 一致）:
  - OK           模型返回了可审阅的非空文本行（候选质量由人工判断）
  - NEEDS_HUMAN  模型没有给出可用的文本内容（空响应、无文本图）
  - NEEDS_ENV    端点、网络、依赖或图片读取失败（环境问题，不视为候选）

预处理: 原始字节直传（raw 保色）。二值化/放大在消融中有已知信息损失，
如需对照由调用方显式预处理后再传入。
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

EXIT_OK = 0
RESPONSE_EXCERPT_LIMIT = 1024
DEFAULT_BASE = os.environ.get("OCR_BASE", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OCR_MODEL", "minicpm-ocr:latest")
DEFAULT_PROMPT = ("Extract the text lines (including formulas as plain text) "
                  "from this image. Return only the extracted text, one line "
                  "per source line. Do not translate, repair or comment.")


def _excerpt(text: str):
    """Return a bounded excerpt and truncation flag; never invent content."""
    return text[:RESPONSE_EXCERPT_LIMIT], len(text) > RESPONSE_EXCERPT_LIMIT


def extract(image_bytes: bytes, *, model: str, base: str, prompt: str, timeout: int = 180):
    """请求一次 vision 模型。返回 (status, reason, payload)。"""
    try:
        encoded = base64.b64encode(image_bytes).decode("ascii")
    except (TypeError, ValueError):
        return "NEEDS_ENV", "bad_image", {}
    payload = {"model": model, "stream": False,
               "messages": [{"role": "user", "content": prompt, "images": [encoded]}]}
    request = urllib.request.Request(base + "/api/chat",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            return "NEEDS_ENV", "response_too_large", {}
        body = json.loads(raw)
    except json.JSONDecodeError:
        return "NEEDS_ENV", "bad_response_json", {}
    except urllib.error.HTTPError:
        return "NEEDS_ENV", "http_error", {}
    except (TimeoutError, urllib.error.URLError):
        return "NEEDS_ENV", "timeout_or_network", {}
    except Exception:
        return "NEEDS_ENV", "provider_error", {}

    content = (body.get("message") or {}).get("content")
    if not isinstance(content, str):
        return "NEEDS_ENV", "bad_response_shape", {}
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return "NEEDS_HUMAN", "no_text", {"raw_response": "", "response_truncated": False,
                                          "model": model,
                                          "eval_count": body.get("eval_count"),
                                          "elapsed_seconds": round(time.monotonic() - started, 6)}
    excerpt, truncated = _excerpt(content)
    return "OK", "", {"lines": lines, "raw_response": excerpt, "response_truncated": truncated,
                      "model": model, "eval_count": body.get("eval_count"),
                      "elapsed_seconds": round(time.monotonic() - started, 6)}


def run_record(record, *, model: str, base: str, prompt: str) -> int:
    """处理一条 {id, image|image_path} 记录，返回该条的退出码贡献。"""
    record_id = record.get("id") if isinstance(record.get("id"), str) else None
    image, path = record.get("image"), record.get("image_path")
    if isinstance(image, str) and image.strip():
        try:
            image_bytes = base64.b64decode(image, validate=True)
        except (ValueError, TypeError):
            sys.stdout.write(json.dumps({"id": record_id, "status": "NEEDS_ENV",
                                        "reason": "bad_image_b64"}, ensure_ascii=False) + "\n")
            return 2
    elif isinstance(path, str) and path.strip():
        try:
            with open(path, "rb") as handle:
                image_bytes = handle.read(24 * 1024 * 1024 + 1)
            if len(image_bytes) > 24 * 1024 * 1024:
                raise ValueError("image_too_large")
        except (OSError, ValueError):
            sys.stdout.write(json.dumps({"id": record_id, "status": "NEEDS_ENV",
                                        "reason": "image_unreadable"}, ensure_ascii=False) + "\n")
            return 2
    else:
        sys.stdout.write(json.dumps({"id": record_id, "status": "NEEDS_HUMAN",
                                    "reason": "bad_input"}, ensure_ascii=False) + "\n")
        return 1
    status, reason, payload = extract(image_bytes, model=model, base=base, prompt=prompt)
    sys.stdout.write(json.dumps({"id": record_id, "status": status, "reason": reason, **payload},
                                ensure_ascii=False) + "\n")
    return {"OK": 0}.get(status, {"NEEDS_HUMAN": 1}.get(status, 2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Image → text candidate lines (local OCR model).")
    parser.add_argument("image", nargs="?", help="input image path (omit to read JSONL on stdin)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--id", default="argv")
    args = parser.parse_args()
    code = EXIT_OK
    if args.image:
        code = run_record({"id": args.id, "image_path": args.image},
                          model=args.model, base=args.base, prompt=args.prompt)
    else:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                sys.stdout.write(json.dumps({"id": None, "status": "NEEDS_HUMAN",
                                            "reason": "bad_input", "detail": str(exc)}) + "\n")
                code = max(code, 1)
                continue
            if not isinstance(record, dict):
                sys.stdout.write(json.dumps({"id": None, "status": "NEEDS_HUMAN",
                                            "reason": "bad_input"}) + "\n")
                code = max(code, 1)
                continue
            code = max(code, run_record(record, model=args.model, base=args.base, prompt=args.prompt))
    return code


if __name__ == "__main__":
    sys.exit(main())

