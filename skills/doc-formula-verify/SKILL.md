---
name: doc-formula-verify
version: 1.0.0
description: Check LaTeX formula syntax with SymPy and review repair candidates from an explicitly configured text model. Use when a LaTeX formula fails to parse or OCR-derived formula text needs syntax checks. Parsing does not validate mathematical meaning.
---

# Formula Verification

## Workflow

1. Read formula text from a supplied layout tree or the user's LaTeX source. Preserve the original text and location.
2. Run `scripts/verify.py` with the formula as one command argument, or send JSONL records on stdin. Never build a shell command from document text.
3. `OK` means the parser accepted the expression; it is not a semantic proof. `RETRY` means parsing failed. `NEEDS_ENV` means dependencies or the checker need attention; do not call the model for an environment error. `NEEDS_HUMAN / bad_input` means malformed JSON or a missing/non-string `latex` field; correct the input contract without a model call.
4. For `RETRY`, the supplied harness can ask the explicitly configured OpenAI-compatible model endpoint for a text candidate and run the checker again. The operator selects a loopback endpoint or an authorized cloud endpoint; the MiniCPM profile selects the configured MiniCPM checkpoint. Limit this to two attempts. The current provider sends text only and does not inspect crops.
5. Preserve a diff and the source evidence. Ask the reviewer to verify meaning, especially when an index or symbol was missing. After unsuccessful attempts, keep the original and mark `NEEDS_HUMAN`.
6. The CLI records each repair attempt, provider outcome and candidate check in `state.jsonl`; Studio persists job events and presents a candidate for the user to adopt into the editor. Preserve rejected candidates and their reasons as evidence, not just the final candidate. Raw provider response excerpts are size-limited and carry an explicit truncation flag.
7. A model candidate must be a single-line formula without control characters, even when its JSON syntax is valid. JSON backslash escapes such as `\f` can decode to control characters instead of a TeX command; reject these candidates before running the formula checker. Never silently add escapes or alter a malformed model response.

## Boundaries

- Do not invent an original image, confidence score, or semantic validation result.
- Existing crop files can accompany CLI evidence; missing crops must be disclosed.
- Re-cropping and image-based repair are future integration work, not implemented by these scripts.
- Use only the endpoint explicitly selected by the operator. A cloud endpoint requires the user's authorization or explicit cloud profile selection; an existing explicit API authorization is sufficient. Keep credentials in the server process environment, outside prompts and document evidence.

## Executable contract

For one record, exit codes are `OK/RETRY: 0`, `NEEDS_HUMAN: 1`, `NEEDS_ENV: 2`; a JSONL stream returns the highest code encountered. The wrappers reject mismatched status/exit codes. See `evals/evals.json` for real F01–F10 case references, including syntactically valid `1+1=3` returning `OK`. This does not prove mathematical truth.

The bundled runtime uses fixed Python orchestration. In explicit `skill_mode=on`, its instruction host reads this allowlisted `SKILL.md`, validates the metadata and path, hashes its exact contents, and includes those contents in the model's system message. Formula text is supplied separately as untrusted user data. In `skill_mode=off`, the host omits the Skill text while preserving the base prompt, model and request parameters for a controlled comparison. This is instruction loading, not autonomous planning or arbitrary tool execution; the model does not decide which checker runs.

The provider records the loaded Skill hash, prompt hash, HTTP request count and a bounded response excerpt for each completed repair call. Request counts include failures such as timeouts and do not prove that inference completed. Checker acceptance is a syntax result, not user adoption or mathematical validation. CLI reuse additionally requires matching input and execution context; an interrupted call can retain a start event without a response.

Studio extracts dollar-delimited text with a per-line regex, not a complete TeX parser; comments and verbatim text may also be considered formula candidates. Formula repair is text-only, and semantic review remains mandatory.

Studio has an optional, default-off constrained planner and a separate, default-off Skill selection experiment. With selection enabled, the model sees capability metadata before any job-specific body loading; the host validates formula applicability and version before loading this body. Selection and loading have separate audit events. Python still owns revision validation, action masks, budgets, checker execution and candidate construction. The formula body can inform text repair, but does not grant code execution, OCR or semantic verification.
