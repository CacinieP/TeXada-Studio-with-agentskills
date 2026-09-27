# 批量 OCR 与文本差异交付

需要处理一套本地 OCR 并保留可复核例子时使用。完整副本与文本导出放在两个独立的新目录，
先固定输入哈希，再批量运行。已核实的校订可作为片段覆盖；它们必须在原始全文唯一出现且互不重叠。

```json
{
  "schema_version": 1,
  "books": [
    {
      "id": "book-001",
      "source": "original/book.md",
      "source_sha256": "填写实际的64位SHA256",
      "overlays": [
        {
          "id": "page-041",
          "before": "review/page-041.before.md",
          "before_sha256": "填写实际的64位SHA256",
          "after": "review/page-041.after.md",
          "after_sha256": "填写实际的64位SHA256"
        }
      ]
    }
  ]
}
```

路径相对于 manifest；无需校订时省略 `overlays`。ID 忽略大小写仍须唯一，避免不同系统覆盖文件。
片段覆盖的证据判断在此脚本之前完成；脚本仅检查文件版本、位置、范围和输出字节。

```sh
python3 scripts/run_ocr_corpus.py /local/manifest.json \
  --output-dir /local/new-cleaned-corpus \
  --export-dir /local/new-text-export
```

脚本对每本调用原有保守 formatter，并验证幂等；首尾复核输入哈希。输出的 `status` 描述
formatter 状态，`output_changed` 描述包含校订在内的实际结果，不能混为一谈。
拒绝、跳过或复核事项逐本保留；退出码 0 仅表示全体机械格式处理通过，1 表示批次完成但有
保留/待核状态，2 表示未能完成。任何退出码都不证明全文数学内容正确。

普通变更导出零上下文 `.diff`，用 `git apply --unidiff-zero` 重放。改变控制字符时导出
`latex-cleanup-byte-patch-v1` JSON：固定前后哈希、原始字节范围和转义后的 old/new；可用
`run_ocr_corpus.apply_text_patch` 重放。它与 `apply_verified_edits.py` 的计划格式不同，
也不绕过后者的 NUL 拒绝规则。完整副本与本地路径仅在私有输出目录。

## 全量公式诊断

```sh
node scripts/audit_math.cjs --manifest /local/manifest.json \
  --outdir /local/new-formula-audit --katex-module /local/node_modules/katex
node tests/test_audit_math.cjs
```

探针需要本机可用的 KaTeX。它只读输入，输出解析计数、失败位置与有限别名候选；不执行
任何候选替换。候选仍需检查宏定义、代码保护和当前渲染器语境。不能为了消除解析错误删掉
未知命令、公式项、上下标或图像。失败详情含原文与本地路径，文件名带 `.local.json`，
不要把整个探针输出目录直接加入 Git。

美元定界符提取不是完整 Markdown 解析；查看输出中的 `limitations`。原 PDF 页范围来自
分段标记，不能精确推断每条公式所在单页。缺少定界符、能解析但含错符号的公式以及图像
丢失都需要其他检查。实际完整例子见 [GTM 语料实例](../examples/gtm-corpus/README.md)。
