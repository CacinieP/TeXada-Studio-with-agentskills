# OCR 候选链路首跑（issue #24 第一段）

验证分而治之边界下的第一段：`samples/ocr/inlines-01.png`（原创合成真实文字图，
由 [source-inlines-01.tex](../../../samples/ocr/source-inlines-01.tex) 经
Tectonic + pdftoppm 150dpi 生成，`scripts/make_ocr_samples.py` 可复现）→
`skills/doc-ocr-extract/scripts/ocr_extract.py` → 本机 `minicpm-ocr:latest`。

## 运行

- 日期 2026-11-08；macOS ARM64；Ollama `http://127.0.0.1:11434`
- 结果 [inlines-01-run.json](inlines-01-run.json)：`status=OK`，6 行候选，
  `eval_count=175`，退出码 0；同图两次同级运行曾得到 7 行候选
  （端点对相同请求非确定性，行边界并入段落），该波动按边界如实记录而非取最优值
- 命令：`python3 skills/doc-ocr-extract/scripts/ocr_extract.py samples/ocr/inlines-01.png`

## 候选质量观察（人工对照源文件）

正确恢复：标题行；`$E = \frac{1}{2}mv^2$`、`$a^2-b^2=(a-b)(a+b)$`、
`\int_{0}^{1} x^2 \, dx = \frac{1}{3}`、`$a_{n+1} = q a_n$` 等行内公式的可解析 LaTeX；
表格行 `Item Value / Alpha 45 / Beta 60 / Sum 105` 与数字事实一致。

需人工处理的候选缺陷（按 SKILL 契约不静默入文）：

1. 多个源段落被并成一行候选（行边界不忠实于源版面）；
2. 源中的 `\ge` 被候选写成 `\geq`（语义等价但文本不同，直接采纳会改变源文）；
3. 公式内空格风格与源不完全一致（`E = \frac...` 带 UTF-8 空格）。

以上缺陷正是「候选 → 人工审阅 → 采纳」必须存在的原因；脚本不修改候选、不写任何状态。

## 边界

- 本次运行只证明链路与候选质量样例，不证明 OCR 对任意版面/字体的正确率；
- 样例图为原创合成材料（AGPL-3.0-only），不含第三方内容；
- 与占位 crop（无文字）的早期探测不同，本图为真实文字渲染，作为正式链路的第一张证据图；
- **传输统一记录（issue #30）**：同一张样例图经 OpenAI 兼容 `/v1/chat/completions`
  传输再次运行成功（[inlines-01-run-openai.json](inlines-01-run-openai.json)，6 行、
  `completion_tokens=174`，URL、请求体与响应形状见 `tests/test_ocr_extract.py`）；
  Ollama 原生 `/api/chat` 保留为 `--transport ollama` 回退（6 行、`eval_count=175`）。
  两种传输候选契约一致，默认 openai 与修复线共用同一协议面；
- 后续（#24 后续段）：候选行转 layout.json 节点、Studio 图片上传与采纳 UI、多图批处理与低置信转人工清单。
