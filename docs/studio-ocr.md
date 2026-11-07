# Studio image OCR

Open `/studio?token=...`, choose **图片 OCR**, and upload a PNG (maximum 8 MiB).
Candidates appear in the right panel and remain plain text. Edit and review the
lines, then use **审阅后插入光标处** in an open document. Insertion supports undo;
it does not save, compile, or run formula repair. Finish repair/diff mode before
adopting. Check TeX escaping and math delimiters yourself.

**导出待审 layout.json** exports text nodes with source SHA-256, model and pending
review status. It does not infer formula/table structure, bounding boxes,
confidence scores or semantic correctness. Uploading another image clears old
candidates, including on a failed request. Images and candidates are not written
by the server.

`POST /api/studio/ocr?token=...` accepts raw `image/png` bytes. It checks auth,
body size and the PNG signature before invoking the shared doc-ocr-extract
transport in a worker thread. This signature check is not full image decoding;
malformed PNG content can still be rejected by the model server. OCR_BASE,
OCR_MODEL and OCR_TRANSPORT are configured on the server; requests cannot
supply an endpoint or a local file path. Defaults remain local minicpm-ocr and
OpenAI-compatible transport, with explicit Ollama fallback. Statuses remain
OK (reviewable candidate), NEEDS_HUMAN (no text), NEEDS_ENV (provider failure).

Validation: offline API and page-handler regression tests cover auth, size,
format rejection, shared transport, failure states, explicit adoption, plain
text candidates and pending text-node export. Live model and browser rendering
were not validated in the restricted continuation environment.
