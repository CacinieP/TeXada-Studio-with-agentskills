#!/usr/bin/env python3
"""MinerU 全文.md → 可编译 .tex（抽取指定页码段）。

用法: gmd2tex.py 全文.md 0101 0120 out.tex "GTM249 · Classical Fourier Analysis"
- 标题映射: #/##/### → section/subsection/subsubsection
- $$ 块 → equation*；行内 $...$ 保留（MinerU 空格风格 LaTeX 可直接编译）
- 图片引用行、HTML 残留剔除
"""
import re
import sys

src, p1, p2, out, title = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
text = open(src).read()

# 抽页码段（MinerU 分隔注释: <!-- 原 PDF 第 X-Y 页 -->）
marker = re.compile(r"<!--\s*原 PDF 第 (\d+)-(\d+) 页\s*-->")
blocks = [(int(m.group(1)), text[m.end():text.find("<!--", m.end()) if text.find("<!--", m.end()) != -1 else len(text)])
          for m in marker.finditer(text)]
body = "\n\n".join(b for a, b in blocks if a >= int(p1) and a <= int(p2))
if not body.strip():
    body = text  # 找不到标记就用全文

# 行内公式规范化：$ x $ → $x$（保留内容原样，去掉 MinerU 注入的多余空格无必要，LaTeX 可编译）
body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)          # 图片引用
body = re.sub(r"<[^>]+>", "", body)                        # HTML 残留
body = re.sub(r"^#{1} (.+)$", r"\\section{\1}", body, flags=re.M)
body = re.sub(r"^## (.+)$", r"\\subsection{\1}", body, flags=re.M)
body = re.sub(r"^### (.+)$", r"\\subsubsection{\1}", body, flags=re.M)
body = re.sub(r"^\d+\. (.+)$", r"\\item \1", body, flags=re.M)
# 连续 \item 包 enumerate
body = re.sub(r"(?:\\item .+\n)+", lambda m: "\\begin{enumerate}\n" + m.group(0) + "\\end{enumerate}\n", body)
# $$ 块 → equation*
body = re.sub(r"\$\$\n(.*?)\n\$\$", lambda m: "\\[\n" + m.group(1) + "\n\\]", body, flags=re.S)

tex = f"""% TeXada-WebUI 样本 · 由 MinerU 解析转换（{title}）
% 源页: {p1}-{p2} · 转换: scripts/gmd2tex.py
\\documentclass[11pt]{{article}}
\\usepackage{{amsmath,amssymb,amsthm}}
\\usepackage[margin=2.2cm]{{geometry}}
\\usepackage{{xeCJK}}
\\setCJKmainfont{{Noto Sans CJK SC}}
\\allowdisplaybreaks
\\begin{{document}}
\\begin{{center}}{{\\Large \\textbf{{{title}}}}}\\\\[2pt]
{{\\small 源页 {p1}--{p2} · MinerU 解析 → TeXada-WebUI}}
\\end{{center}}

{body}
\\end{{document}}
"""
open(out, "w").write(tex)
print(f"{out}: {len(tex)} chars")
