# VLM Prompt 模板与调参（按需加载）

**未来设计草案，未接入当前 CLI 或 Studio。** 仓库没有图像解析脚本，也没有完成本文所列模型/数据集试验；以下字段和参数均为待验证方案，不是实测记录。

## 版面解析 prompt（骨架）

```text
You are a document layout parser. For the given page image, return STRICT JSON:
{"page": <n>, "blocks": [{"bbox": [x0,y0,x1,y1], "type": "text|table|formula|figure",
  "order": <k>, "text": "...", "confidence": 0.0-1.0}]}
Rules:
- Reading order follows the visual flow, top-to-bottom then left-to-right for the doc language.
- A formula is any mathematical expression, inline or display; include surrounding delimiters in text.
- Tables must be one block; do NOT split a table across blocks.
- confidence is your own calibrated certainty; do not pad it.
```

## 重识别 prompt（doc-formula-verify RETRY 时）

```text
Transcribe ONLY the handwritten/printed formula inside this cropped image to LaTeX.
Return STRICT JSON {"latex": "...", "confidence": 0.0-1.0}. No commentary.
```

## 调参记录（TODO 目标环境回填）

- 温度 0；max_tokens 按页面积缩放
- 拟尝试原图 + 20% padding crop；比例及效果尚未验证
- TODO: PaddleOCR-VL 与 HunyuanOCR 在 OmniDocBench 子集上的实测选择
