# 图像公式重识别草案

状态：待接入。当前修复提供方处理公式文本；此页为后续图像输入保留接口方案。

## 候选请求

```text
Transcribe ONLY the handwritten/printed formula inside this cropped image to LaTeX.
Return STRICT JSON {"latex": "...", "confidence": 0.0-1.0}. No commentary.
```

拟使用原始 bbox 外扩20%的裁剪图，放大2倍。最多尝试两次；保留每次裁剪、转写和检查结果，未解决项交人工审阅。`confidence` 字段的定义及校准方法需要在接入时确定。

## 验证案例

- 手写分式：检查分数线是否被转写成减号。
- 上下标：检查分组花括号和索引是否保留。
- 矩阵：检查行分隔与列数，并将渲染结果与原图对照。

现有文本检查契约见 [SKILL.md](../SKILL.md) 和 [案例索引](../evals/evals.json)。
