#!/usr/bin/env python3
"""doc-ocr-extract: image → raw text candidate lines via a local vision model.

分而治之（ADR-017 对齐）：本脚本只把图片转成候选文本行，不判定数学语义、
不做修复、不写任何状态。候选必须经人工审阅后才可能进入文档。

输入（二选一）:
  - 命令行参数: ocr_extract.py image.png
  - stdin JSONL: {"id": "img-01", "image": "<base64 PNG>"}  每行一条
输出: JSONL  {"id", "status", "lines" 或诊断 "candidate_lines", "review_items",
             "raw_response", "response_truncated", "output_complete", "finish_reason",
             "model", "eval_count", "elapsed_seconds", "reason"}

约定（与 doc-formula-verify/scripts/verify.py 一致）:
  - OK           模型返回了可审阅的非空文本行（候选质量由人工判断）
  - NEEDS_HUMAN  空/非文本、截断/结束状态未知、拒绝或客观异常字符等需人工处理
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
MAX_LINES = 4096
MAX_LINE_CHARS = 32768
DEFAULT_BASE = os.environ.get("OCR_BASE", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OCR_MODEL", "minicpm-ocr:latest")
# 统一协议面：默认走 OpenAI 兼容 /v1/chat/completions（与修复线一致），
# Ollama 原生 /api/chat 保留为显式回退。
DEFAULT_TRANSPORT = os.environ.get("OCR_TRANSPORT", "openai")
DEFAULT_PROMPT = ("Extract the text lines (including formulas as plain text) "
                  "from this image. Return only the extracted text, one line "
                  "per source line. Do not translate, repair or comment.")


def _excerpt(text: str):
    """Return a bounded excerpt and truncation flag; never invent content."""
    return text[:RESPONSE_EXCERPT_LIMIT], len(text) > RESPONSE_EXCERPT_LIMIT


def extract(image_bytes: bytes, *, model: str, base: str, prompt: str,
            transport: str = DEFAULT_TRANSPORT, timeout: int = 180):
    """请求一次 vision 模型。返回 (status, reason, payload)。

    transport="openai" 走 /v1/chat/completions + image_url(data URL)，
    transport="ollama" 走原生 /api/chat + images。两者候选契约一致，
    默认 openai 与修复线统一在同一协议面上。
    """
    try:
        encoded = base64.b64encode(image_bytes).decode("ascii")
    except (TypeError, ValueError):
        return "NEEDS_ENV", "bad_image", {}
    if transport == "openai":
        payload = {"model": model, "stream": False, "max_tokens": 2048,
                   "messages": [{"role": "user", "content": [
                       {"type": "text", "text": prompt},
                       {"type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + encoded}}]}]}
        path = "/v1/chat/completions"
    elif transport == "ollama":
        payload = {"model": model, "stream": False,
                   "messages": [{"role": "user", "content": prompt, "images": [encoded]}]}
        path = "/api/chat"
    else:
        return "NEEDS_ENV", "bad_transport", {}
    request = urllib.request.Request(base + path,
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

    if not isinstance(body, dict):
        return "NEEDS_ENV", "bad_response_shape", {}
    refusal = False
    if transport == "openai":
        try:
            choice = body["choices"][0]
            message = choice["message"]
            content = message.get("content")
            finish = choice.get("finish_reason")
            refusal = bool(message.get("refusal")) or finish == "content_filter"
        except (KeyError, IndexError, TypeError, AttributeError):
            return "NEEDS_ENV", "bad_response_shape", {}
        usage = body.get("usage")
        counter = usage.get("completion_tokens") if isinstance(usage, dict) else None
        complete = True if finish == "stop" else False if finish == "length" else None
    else:
        message = body.get("message")
        if not isinstance(message, dict):
            return "NEEDS_ENV", "bad_response_shape", {}
        content = message.get("content")
        counter = body.get("eval_count")
        finish = body.get("done_reason")
        complete = (False if finish == "length" or body.get("done") is False else
                    True if body.get("done") is True and finish in (None, "stop") else None)
    if finish is not None and not isinstance(finish, str):
        return "NEEDS_ENV", "bad_response_shape", {}
    if not isinstance(content, str):
        if refusal and content is None:
            content = ""
        else:
            return "NEEDS_ENV", "bad_response_shape", {}
    if type(counter) is not int or counter < 0:
        counter = None
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    items = []
    if refusal:
        items.append({"reason": "refused_output", "scope": "record"})
    elif complete is False:
        items.append({"reason": "incomplete_output", "scope": "record"})
    elif complete is None:
        items.append({"reason": "completion_unconfirmed", "scope": "record"})
    if not lines:
        items.append({"reason": "no_text", "scope": "record"})
    over_limit = len(lines) > MAX_LINES or any(len(line) > MAX_LINE_CHARS for line in lines)
    if over_limit:
        items.append({"reason": "text_limits_exceeded", "scope": "record"})
    if any(ord(char) < 32 and char not in "\t\r\n" or ord(char) == 127 for char in content):
        items.append({"reason": "control_character", "scope": "record"})
    for number, line in enumerate(lines[:MAX_LINES], 1):
        reasons = []
        if line.casefold() in {"[non-text]", "[no text]"}:
            reasons.append("non_text_marker")
        if "\ufffd" in line:
            reasons.append("replacement_character")
        for reason in reasons:
            items.append({"reason": reason, "scope": "line", "line": number,
                          "text": line[:RESPONSE_EXCERPT_LIMIT]})
    excerpt, truncated = _excerpt(content)
    payload = {"raw_response": excerpt, "response_truncated": truncated,
               "model": model, "eval_count": counter, "output_complete": complete,
               "finish_reason": finish, "review_items": items,
               "elapsed_seconds": round(time.monotonic() - started, 6)}
    if items:
        # Partial/suspect text is diagnostic material, never success-path lines.
        payload["candidate_lines"] = [line[:MAX_LINE_CHARS] for line in lines[:MAX_LINES]]
        payload["candidate_lines_truncated"] = over_limit
        return "NEEDS_HUMAN", items[0]["reason"], payload
    payload["lines"] = lines
    return "OK", "", payload


def run_record(record, *, model: str, base: str, prompt: str,
               transport: str = DEFAULT_TRANSPORT) -> int:
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
    status, reason, payload = extract(image_bytes, model=model, base=base, prompt=prompt,
                                      transport=transport)
    sys.stdout.write(json.dumps({"id": record_id, "status": status, "reason": reason, **payload},
                                ensure_ascii=False) + "\n")
    return {"OK": 0}.get(status, {"NEEDS_HUMAN": 1}.get(status, 2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Image → text candidate lines (local OCR model).")
    parser.add_argument("image", nargs="?", help="input image path (omit to read JSONL on stdin)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--transport", choices=["openai", "ollama"], default=DEFAULT_TRANSPORT,
                        help="openai: /v1/chat/completions (default, unified with the repair "
                             "line); ollama: native /api/chat fallback")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--id", default="argv")
    args = parser.parse_args()
    code = EXIT_OK
    if args.image:
        code = run_record({"id": args.id, "image_path": args.image},
                          model=args.model, base=args.base, prompt=args.prompt,
                          transport=args.transport)
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
            code = max(code, run_record(record, model=args.model, base=args.base,
                                        prompt=args.prompt, transport=args.transport))
    return code


if __name__ == "__main__":
    sys.exit(main())

