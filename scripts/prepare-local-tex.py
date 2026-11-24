#!/usr/bin/env python3
"""Explicit first-use TeX resource preparation; normal Studio previews stay offline."""
import argparse
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

SAMPLE = r"""\documentclass[UTF8,fontset=fandol]{ctexart}
\usepackage{amsmath,amssymb,amsthm,graphicx,booktabs}
\usepackage[margin=2.5cm]{geometry}
\newtheorem{theorem}{定理}
\begin{document}
\title{TeXada Studio 本地文档}\author{本地工作区}\date{\today}\maketitle
\tableofcontents
\section{Local document 中文标题}
\subsection{Text styles 中文小节}
\textbf{Bold} \textit{Italic} \texttt{Code}.
\begin{theorem}[示例定理]
本地文档排版测试。\[x^2+1\]
\end{theorem}
\begin{proof}
展开即可。
\end{proof}
\begin{enumerate}
  \item 填空：\underline{\hspace{2cm}}。
\end{enumerate}
\[\int_0^1 x^2\,dx=\frac{1}{3},\qquad
  \sum_{n=1}^{N} n=\frac{N(N+1)}{2},\qquad \sqrt{a^2+b^2}\]
\[
x_i=\frac{\det(A_i)}{\det(A)},\qquad
\|f\|_{L^p}=\left(\int_E |f|^p\,dx\right)^{1/p}
\]
\[
\begin{vmatrix}2x&1&-1\\-x&x&x\\1&2&x\end{vmatrix}
\qquad
\delta_{ij}=\begin{cases}1,&i=j\\0,&i\ne j\end{cases}
\]
\begin{tabular}{lr}\toprule Item & Value \\\midrule A & 2 \\\bottomrule\end{tabular}
\newpage
Second page: $\frac{1}{2}$.
Inline nested math: $\left(\frac{x^2-1}{x-1}\right)$.
In display, text, script, and scriptscript styles:
\[
  \displaystyle \frac{x^2}{y} \quad
  \textstyle \frac{x^2}{y} \quad
  \scriptstyle \frac{x^2}{y} \quad
  \scriptscriptstyle \frac{x^2}{y}.
\]
\end{document}
"""

LATIN_11PT_SAMPLE = r"""\documentclass[11pt]{article}
\usepackage{amsmath,amssymb,amsthm,graphicx,booktabs}
\usepackage[margin=2.2cm]{geometry}
\newtheorem{theorem}{Theorem}
\title{English Article Cache Check}
\author{TeXada Studio}
\date{\today}
\begin{document}
\maketitle
\begin{abstract}
Offline cache verification for 11pt article, amsthm, geometry, and math styles.
\end{abstract}
\section{Main Result}
\begin{theorem}
For all real numbers $a$ and $b$,
\begin{equation}
  (a+b)^2 = a^2 + 2ab + b^2
\end{equation}
\end{theorem}
\begin{proof}
Expand the left-hand side and collect terms.
\end{proof}
\end{document}
"""

LATIN_12PT_SAMPLE = r"""\documentclass[12pt]{article}
\usepackage{amsmath,amssymb}
\begin{document}
Twelve-point article cache verification: $E = mc^2$.
\end{document}
"""

BEAMER_SAMPLE = r"""\documentclass[UTF8,fontset=fandol]{ctexbeamer}
\usepackage{amsmath,amssymb}
\title{报告标题}
\author{报告人}
\date{\today}
\begin{document}
\begin{frame}
  \titlepage
\end{frame}
\begin{frame}{目录}
  \tableofcontents
\end{frame}
\section{背景}
\begin{frame}{核心公式}
  \begin{itemize}
    \item 要点一
  \end{itemize}
  \begin{equation}
    E = mc^2
  \end{equation}
\end{frame}
\end{document}
"""


def build_specimens():
    latin10 = SAMPLE.replace(r"\documentclass[UTF8,fontset=fandol]{ctexart}", r"\documentclass{article}")
    for chinese in sorted((
        "本地文档", "本地工作区", "中文标题", "中文小节", "本地文档排版测试。",
        "定理", "示例定理", "展开即可。", "填空：", "。",
    ), key=len, reverse=True):
        latin10 = latin10.replace(chinese, "Local text")
    return (
        ("chinese", SAMPLE),
        ("latin10", latin10),
        ("latin11", LATIN_11PT_SAMPLE),
        ("latin12", LATIN_12PT_SAMPLE),
        ("beamer", BEAMER_SAMPLE),
    )


def main():
    parser = argparse.ArgumentParser(description="检查或准备本机 TeX 缓存。默认完全离线。")
    parser.add_argument("--download-resources", action="store_true", help="显式允许 Tectonic 下载本例所需 TeX 资源")
    args = parser.parse_args()
    compiler = os.path.expanduser(os.environ.get("TECTONIC", "tectonic"))
    if not shutil.which(compiler):
        print("请先安装 Tectonic。")
        return 2
    with tempfile.TemporaryDirectory(prefix="texada-tex-check-") as folder:
        directory = Path(folder)
        for name, content in build_specimens():
            source = directory / (name + ".tex")
            source.write_text(content, encoding="utf-8")
            command = [compiler, "--untrusted", "-o", folder]
            if not args.download_resources:
                command.append("--only-cached")
            command.append(str(source))
            try:
                result = subprocess.run(command, cwd=directory, timeout=900 if args.download_resources else 120,
                                        capture_output=True, text=True, encoding="utf-8", errors="replace")
            except (OSError, subprocess.TimeoutExpired):
                print("TeX 资源检查未完成；请检查编译器与网络后重试。")
                return 2
            log = (result.stdout or "") + (result.stderr or "")
            if result.returncode or "Missing character:" in log or not source.with_suffix(".pdf").is_file():
                print(log[-5000:])
                print("本机 TeX 资源尚未齐备。可显式运行 --download-resources 准备，之后重新离线检查。")
                return 1
    print("本机中文、公式、表格、内置模板与多页 PDF 资源已就绪。日常预览无需联网。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
