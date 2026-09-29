# 图像版面解析草案

状态：待接入。当前 CLI 从已有 `layout.json` 开始；以下是图像解析阶段的接口提案。

## 输出结构

```text
You are a document layout parser. For the given page image, return STRICT JSON:
{"page": <n>, "blocks": [{"bbox": [x0,y0,x1,y1], "type": "text|table|formula|figure",
  "order": <k>, "text": "...", "confidence": 0.0-1.0}]}
Rules:
- Reading order follows the visual flow for the document language.
- Preserve formula delimiters in the transcription.
- Keep each table in one block.
```

接入时确定坐标系、阅读顺序和 `confidence` 的校准方法，并保存原图与块位置的对应关系。公式重识别使用[专用请求](../../doc-formula-verify/references/vlm-prompts.md)。

## 待验证设置

- 比较整页解析与外扩20%的局部裁剪。
- 对照固定样本，记录阅读顺序、公式转写和表格结构错误。
- 在目标设备上评估候选解析模型，再固定版本、参数及样本清单。
