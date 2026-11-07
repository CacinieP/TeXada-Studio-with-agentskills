# MiniCPM-V 4.7 pilot: model identity correction

Recorded 2026-11-08 (Asia/Shanghai). This directory preserves the completed
original pilot; the manifest and result records have not been rewritten.

## Model identity

The Cline session's final successful `ollama show minicpm-v4.7:latest` returned
`qwen35moe`, **34.7B**, `Q4_K_M`, and a 552.99M CLIP projector. Its local filename
was `MiniCPM-V-4_7-35B-A3B-Q4_K_M.gguf` (21,166,255,008 bytes), accompanied by
`mmproj-model-f16.gguf` (1,119,575,840 bytes). These are observations from that
session, not a new API measurement. The unqualified tag is not a 1B checkpoint.

Official sources distinguish both variants:
- [1B model](https://huggingface.co/openbmb/MiniCPM-V-4.7-1B)
- [35B-A3B GGUF](https://huggingface.co/openbmb/MiniCPM-V-4.7-35B-A3B-gguf)

A local MiniCPM5-1B text model is a separate model, not MiniCPM-V-4.7-1B.
Do not substitute one for the other when reporting results.

## Completed results and limits

S02 (`a_+b`) made one repair request per model arm. Both returned `timeout`
after about 120 seconds; neither produced a candidate or token usage. S01/S03
were initially parseable controls and made no model requests. Thus this pilot
has two actual model calls, not six successful model evaluations, and provides
no repair-quality or semantic-accuracy measurement for either variant.

The previous claim that a Mac cannot host this model, or requires CUDA, is
withdrawn. This host reports an Apple GPU with Metal support; absence of a
discrete GPU does not imply CPU-only execution. Actual Ollama GPU offload,
model-load latency, concurrency and request queueing were not captured at the
time of the pilot. These timeouts do not establish their cause or rule out
local Apple GPU inference.

This continuation could not query localhost Ollama: the execution sandbox
returned `operation not permitted`. No 1B download or new inference is claimed.
Keep the repair default unchanged until a correctly identified checkpoint has
fresh candidate and checker evidence. Rerun with explicit variant-qualified
names and capture model metadata, model digest and backend/offload alongside
the existing prompt/configuration fingerprints.
