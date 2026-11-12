# OCR 页面原图证据

PDF 导入会在临时目录生成页面图像。只保存源 PDF 和页面哈希时，临时目录清理后无法直接取回参与识别的图像。保存本次实际使用的页面字节，可以让后续候选核验和原图审阅使用同一份证据。

## 保存与读取

`LocalRuntime.import_document()`将源文件、候选 JSON 和参与识别的 PDF 页面 PNG 一起保存到导入目录。图片输入复用已保存的源文件，不重复复制。每页记录相对 `image_file`、`image_mime_type`、尺寸与 SHA256。

文件先写入权限受限的暂存目录，全部写完后在同一文件系统内重命名发布。保存失败时清理暂存目录，不留下半份导入记录。

`LocalRuntime.get_page_evidence(import_id, page)`只读取保存的图像字节，核对记录 ID、页码、预期路径、哈希和实际尺寸。它不重绘 PDF、不调用模型。证据缺失、变更和记录无效会返回明确错误。

历史导入若缺少页面证据字段，会返回错误，不隐式重跑 OCR。此内部方法尚未暴露为浏览器 API；后续接入应沿用已有鉴权边界。

候选仍标记 `requires_review=True`。保存证据不表示转写正确，也不会自动采用候选。

## 验证

- `python -m unittest -v test_local_runtime test_source_evidence`：运行时及页面证据测试，覆盖临时目录清理后的 PDF 页读取、图片复用、发布失败清理、内容变更、路径及符号链接限制。
- `python -m unittest -v test_local_product`：现有产品 HTTP 接口回归。

上述测试使用临时存储和模型替身，不启动推理服务。
