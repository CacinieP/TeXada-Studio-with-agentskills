# OCR 真实文字样例

原创合成材料（AGPL-3.0-only），用于[图片 → 文本候选链路](../../skills/doc-ocr-extract/SKILL.md)的验证输入。

| 文件 | 说明 |
| --- | --- |
| [source-inlines-01.tex](source-inlines-01.tex) | 可读源：课程笔记风格短文 + 行内公式 + 简单表格 |
| [inlines-01.png](inlines-01.png) | 由源文件渲染的 150dpi 页面图（已入库，可复现） |

再生成图片（需要 `tectonic` 与 `pdftoppm`）：

```bash
python scripts/make_ocr_samples.py
```

[samples/exam-01 等 crops 目录](../exam-01/)的占位图不含文字，仅用于 CLI 流程冒烟；本目录图含真实渲染文字，是 OCR 候选质量证据的正式输入。首次运行记录见 [ocr-chain-01](../../docs/evaluation-results/ocr-chain-01/README.md)。
