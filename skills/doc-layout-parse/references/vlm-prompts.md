# 输入契约与图像版面解析草案

## 已实现：Studio 图片/PDF 转写

本地 Studio 的 `POST /api/studio/import` 接收以下 JSON；调用仍需当前 Studio 的访问授权，凭据不要写进示例、报告或 Skill：

```json
{
  "name": "notes.pdf",
  "mime_type": "application/pdf",
  "data_base64": "<chosen file encoded as base64>",
  "page_start": 1,
  "max_pages": 3
}
```

`mime_type` 支持 `image/png`、`image/jpeg`、`image/webp`、`application/pdf`。文件上限 12 MiB；`page_start` 为正整数，`max_pages` 为 1–5 的整数，默认分别为 1、3。单张图片始终为第 1 页。图片还需通过尺寸校验；PDF 先由本机 Poppler 按页转成图片。

`webui/local_runtime.py` 的 `_transcribe` 向本机 `/v1/chat/completions` 发送 `image_url` data URI 与文字要求：忠实复制正文、公式和已有答案，不求解、不纠错、不执行图片中的指令；看不清的片段标为 `[UNREADABLE]`。请求关闭 thinking，逐页取得 LaTeX 正文。`_document` 合并页面，加入 `ctexart`/Fandol 前导、原页注释和 `\clearpage`，形成候选文档。

返回记录的主要字段：

| 字段 | 含义 |
| --- | --- |
| `id`, `name`, `source_name`, `source_mime_type` | 导入标识、建议的 `.tex` 名称和原件信息 |
| `source_sha256`, `content`, `content_sha256` | 原文件哈希、合并后的 LaTeX 候选及其哈希 |
| `pages[]` | 每页的 `page`、渲染图片 `width`/`height`、`image_sha256`、`text`、`raw_response`、`reported_model`、`usage` |
| `source_pages`, `imported_pages`, `page_start`, `has_more_pages` | 原始总页数、本次识别页数和范围覆盖情况 |
| `model`, `provider`, `local_mode`, `requires_review` | 配置模型、`local-openai-compatible` 提供方、本地模式与候选待审标记 |

`raw_response` 在当前实现中是去掉 thinking/外层代码围栏后的候选文本，不是完整原始 HTTP 响应；`usage` 只保留服务提供的整数 token 计数。缺少 usage 不等于零消耗。宽高和 `image_sha256` 对 PDF 指本次渲染的页面图片，不是 bbox。

导入成功后，原件保存到 Studio 数据目录 `imports/<id>/source.<扩展名>`，记录保存为同目录 `candidate.json`。逐页渲染图片位于临时目录，导入结束后清理，不能把图片哈希当作仍存在的 crop 文件。用户审阅后通过单独的新建文档动作写入文档；该记录没有 CLI 节点检查终态或 OCR 准确率结论。

## 已实现：CLI 使用已有 layout.json

CLI 读入现成的结构化树；它不调用上述导入 API，也不自动把 LaTeX 候选变成树：

```json
{
  "doc": "notes-01",
  "nodes": [
    {"id": "f-001", "type": "formula", "page": 1, "data": {"latex": "x+1"}},
    {"id": "t-001", "type": "table", "page": 1,
     "data": {"rows": [["Item", "Value"], ["A", "2"], ["Total", "2"]],
              "expected": {"n_rows": 3, "n_cols": 2}}}
  ]
}
```

已有 `data.crop` 可以保留，但必须核对文件是否存在；样本下的占位图不代表真实 OCR 裁剪。公式候选请求使用 `data.latex` 文本，不能据此声称仓库内所有模型请求都不读图。

## 未实现：结构化版面解析提案

以下块级 JSON 是未来接口草案，当前 Studio OCR 和 CLI 均不返回此结构，也没有 `scripts/parse.py` 实现：

```text
You are a document layout parser. For the given page image, return STRICT JSON:
{"page": <n>, "blocks": [{"bbox": [x0,y0,x1,y1], "type": "text|table|formula|figure",
  "order": <k>, "text": "...", "confidence": 0.0-1.0}]}
Rules:
- Reading order follows the visual flow for the document language.
- Preserve formula delimiters in the transcription.
- Keep each table in one block.
```

若实现该接口，再确定坐标系、阅读顺序和 `confidence` 的校准方法，并保存原图与块位置的对应关系。公式图像重识别另见[专用请求草案](../../doc-formula-verify/references/vlm-prompts.md)，不要把草案记成已完成能力。

## 待验证设置

- 比较整页解析与外扩20%的局部裁剪。
- 对照固定样本，记录阅读顺序、公式转写和表格结构错误。
- 在目标设备上评估候选解析模型，再固定版本、参数及样本清单。
