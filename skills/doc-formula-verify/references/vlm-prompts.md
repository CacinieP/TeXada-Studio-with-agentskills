# 公式重识别 Prompt（RETRY 路径）

## 高分辨率重识别

```text
Transcribe ONLY the handwritten/printed formula inside this cropped image to LaTeX.
Return STRICT JSON {"latex": "...", "confidence": 0.0-1.0}. No commentary.
```

- 输入：原始 bbox 外扩 20% 的 crop，放大 2× 重采样
- attempt=2 仍失败 → `NEEDS_HUMAN`，报告中给出两张 crop 与两次 SymPy 报错原文

## 已知坑（TeXWizard/CROHME 经验）

- 手写分式横线易被识别为 `-`：SymPy 报错模式 `unexpected token` → 优先怀疑结构而非符号
- 上下标粘连：重识别时在 prompt 中强调 explicit braces
- 打印体矩阵：`matrix` 环境漏 `\\` 时 parse 失败但视觉正确，复验需渲染比对（P2）
