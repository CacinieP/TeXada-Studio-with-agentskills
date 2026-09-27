---
name: spark-ops
description: Plan memory budgets and manage model services for DGX Spark local inference — resident-model sizing, vLLM launch parameters, OOM diagnosis and graceful degradation. Use when preparing the model layer for a pipeline that keeps several models resident on a 128GB unified-memory device, or when a run fails with out-of-memory errors during document processing.
---

# Spark Ops（内部依赖 · 不单独参赛）

> 本 Skill 是 doc-forensics 的运维底座，为评审回答「为什么需要这台机器」提供数据支撑。

## Workflow

1. On pipeline start, run `scripts/budget_check.py` (TODO P1) against the declared resident set
   (vlm-8b / 30b-moe / embed / rerank) and the device memory ceiling; refuse to start if projected > 60GB.
2. Expose `nvidia-smi`/`tegrastats` snapshots into the demo overlay so residency claims are visible on screen.
3. On OOM: log the failing allocation, unload the lowest-priority model via llama-swap, retry once, then degrade
   (serialize the two vision-heavy stages) and record the degradation in state.jsonl.

## Guardrails

- Monitoring commands are read-only; never kill user processes.
- Degradation must be reversible and reported — silent performance loss is a failure mode, not a workaround.
