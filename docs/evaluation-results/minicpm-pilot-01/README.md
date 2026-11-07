# MiniCPM 模型路由试点（issue #23 证据）

回答两个问题：MiniCPM 系列能否通过现有 Skill 加载协议进入修复链路；OCR 专用模型在本机端点是否可用。运行日期 2026-11-08，macOS ARM64，Ollama 本机端点 `127.0.0.1:11434`，提供方为 `OllamaProvider`（OpenAI 兼容 `/v1/chat/completions`，temperature=0、seed=0、严格 JSON 候选协议）。

## 运行一：MiniCPM5-1B @ 预算300（旧行为）

`texada-minicpm5-1b:baseline`（MiniCPM5-1B，Q4_K_M，688MB）。两组模型请求均为 `empty_response`：模型是 thinking 型，推理内容进入 `reasoning` 字段，300 token 预算全部耗尽（`completion_tokens=300`、`finish_reason=length`），正式答案未能进入 `content`。[证据](repair-1b-budget-300/results.jsonl)

## 运行二：MiniCPM5-1B @ 预算2048（适配验证）

同一模型、同一 seed。`empty_response` 消除，协议层开始看见真实候选问题：without_skill 组返回 `{"latex": "a\pm b"}`（JSON 字符串内反斜杠未转义 → `bad_candidate_json`）；with_skill 组混入多余字段（→ `bad_candidate_type`）。结论：预算是必要适配；1B 的候选质量不足（对 `a_` 的候选均非有效修复）。[证据](repair-1b-budget-2048/results.jsonl)

## 运行三：MiniCPM5-2B @ 预算8192（上限试点）

`hf.co/openbmb/MiniCPM5-2B-GGUF:Q4_K_M`（1.6GB）。试点协议下两次请求的思考过程均未在 8192 token 内收敛（`completion_tokens=8192` 耗尽仍无 `content`）；另一次对 `a_` 的直接请求在预算 8192 下收敛（849 token），候选为 `a _`，同样不是有效修复。结论：MiniCPM5 文本系作为修复引擎不稳定（思考不收敛 + 候选质量弱），不推荐作为默认修复模型。[证据](repair-2b-budget-8192/results.jsonl)

## OCR 探活：minicpm-ocr（vision）

`minicpm-ocr:latest`（MiniCPM-OCR-1.0，752M Q8_0，capabilities 含 vision）。原生 `/api/chat` 带 `images` 字段调用成功、正常停止。对三张占位合成图如实报告无文字（`"There is no text in this image."` 等）——占位图本无文字，说明模型未幻觉输出。图片输入链路（roadmap P2 / issue #24）需要含真实文字的原创合成样例。[证据](ocr-vision-probe.json)

## 结论与决策

1. **路由就绪**：`REPAIR_MODEL` / `OCR_MODEL` 环境变量进入 Studio 与部署文档；未设置时回退 `VLM_MODEL`（qwen3.8），已部署环境无感升级。
2. **默认修复模型不切换**：证据门控结论——MiniCPM5-1B/2B 候选质量与思考稳定性均不足以替代当前回退模型。后续修复质量对照候选 `minicpm-v4.7`（22GB VLM），属于 issue #24/#25 之后的扩展实验。
3. **token 预算适配**：默认 `max_tokens` 从 300 提升到 8192，允许 thinking 模型正常完成；非 thinking 模型早在 `finish_reason=stop` 停止，不受影响。参数写入 provider 指纹，续跑会重新检查。
4. **OCR 方向可行**：专用 OCR 模型在本机端点稳定可用，M2 以真实合成文字图接入正式提取链路。

## 复现（需要本机 Ollama 与已拉取的模型标签）

```bash\nPYTHONPATH=harness python scripts/evaluate_skills.py run \\\n  --cases samples/research/smoke_cases.json --outdir state/minicpm-rerun-1b \\\n  --mode model --base http://127.0.0.1:11434 \\\n  --model texada-minicpm5-1b:baseline --max-tokens 8192\n```

各试点目录含 manifest（配置、指纹、来源）、report（分组计数）与 results.jsonl（逐组检查、每次尝试、被拒原因）。人工语义复核按 `blind-review.csv` 流程另行进行，本记录不填写。
