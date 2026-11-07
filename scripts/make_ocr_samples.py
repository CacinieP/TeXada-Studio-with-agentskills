#!/usr/bin/env python3
"""Regenerate the committed OCR sample image from its readable source.

samples/ocr/source-inlines-01.tex --(tectonic)--> PDF --(pdftoppm, 150 dpi)--> PNG
产物 samples/ocr/inlines-01.png 已入库；本脚本保证任何人可复现同一来源的图片。
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "samples" / "ocr" / "source-inlines-01.tex"
TARGET = ROOT / "samples" / "ocr" / "inlines-01.png"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild samples/ocr/inlines-01.png from source.")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--tectonic", default="tectonic")
    parser.add_argument("--pdftoppm", default="pdftoppm")
    args = parser.parse_args()
    for tool in (args.tectonic, args.pdftoppm):
        if shutil.which(tool) is None:
            print(f"missing dependency: {tool}", file=sys.stderr)
            return 2
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        subprocess.run([args.tectonic, "-o", str(out), str(SOURCE)], check=True)
        stem = SOURCE.stem
        subprocess.run([args.pdftoppm, "-png", "-r", str(args.dpi), "-singlefile",
                        str(out / f"{stem}.pdf"), str(out / "page")], check=True)
        shutil.copyfile(out / "page.png", TARGET)
    print(f"written: {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
