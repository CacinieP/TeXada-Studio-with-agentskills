#!/usr/bin/env python3
"""Explicit first-use TeX resource preparation; normal Studio previews stay offline."""
import argparse
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

SAMPLE = r"""\documentclass[UTF8,fontset=fandol]{ctexart}
\usepackage{amsmath,amssymb,graphicx,booktabs}
\begin{document}
\title{TeXada Studio 本地文档}\author{本地工作区}\date{}\maketitle
\section{Local document 中文标题}
\subsection{Text styles 中文小节}
\textbf{Bold} \textit{Italic} \texttt{Code}.
本地文档排版测试。\[x^2+1\]
\[\int_0^1 x^2\,dx=\frac{1}{3},\qquad
  \sum_{n=1}^{N} n=\frac{N(N+1)}{2},\qquad \sqrt{a^2+b^2}\]
\begin{tabular}{lr}\toprule Item & Value \\\midrule A & 2 \\\bottomrule\end{tabular}
\newpage
Second page: $\frac{1}{2}$.
\end{document}
"""


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
        latin = SAMPLE.replace(r"\documentclass[UTF8,fontset=fandol]{ctexart}", r"\documentclass{article}")
        for chinese in sorted(("本地文档", "本地工作区", "中文标题", "中文小节", "本地文档排版测试。"), key=len, reverse=True):
            latin = latin.replace(chinese, "Local text")
        for name, content in (("chinese", SAMPLE), ("latin", latin)):
            source = directory / (name + ".tex")
            source.write_text(content, encoding="utf-8")
            command = [compiler, "--untrusted", "-o", folder]
            if not args.download_resources:
                command.append("--only-cached")
            command.append(str(source))
            try:
                result = subprocess.run(command, cwd=directory, timeout=900 if args.download_resources else 120,
                                        capture_output=True, text=True)
            except (OSError, subprocess.TimeoutExpired):
                print("TeX 资源检查未完成；请检查编译器与网络后重试。")
                return 2
            log = (result.stdout or "") + (result.stderr or "")
            if result.returncode or "Missing character:" in log or not source.with_suffix(".pdf").is_file():
                print(log[-5000:])
                print("本机 TeX 资源尚未齐备。可显式运行 --download-resources 准备，之后重新离线检查。")
                return 1
    print("本机中文、公式、表格与多页 PDF 资源已就绪。日常预览无需联网。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
