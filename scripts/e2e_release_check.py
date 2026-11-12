"""E2E 发行驱动：预检、场景执行、证据写盘。

仅用于可信本机环境：真实 LaTeX 编译、真实 Ollama 模型、真实 Studio 后端。
运行入口见 docs/superpowers/plans/2026-11-12-e2e-release.md。
"""
import json
import shutil
import urllib.request
from pathlib import Path

REQUIRED_MODELS = ("openbmb/minicpm-v4.7", "minicpm-ocr")
DEFAULT_MODELS_BASE = "http://127.0.0.1:11434/v1"


class PreflightError(RuntimeError):
    """预检失败：环境或模型不满足真实 E2E 运行条件，消息含修复提示。"""


def probe_python(python_path=Path(".venv/bin/python")):
    """真实运行需要仓库 .venv（macOS ARM 开发环境）。"""
    if not Path(python_path).exists():
        raise PreflightError(f"缺少虚拟环境 {python_path}（先 python3 -m venv .venv 并安装依赖）")
    return str(python_path)


def probe_latex_tools(tools=("tectonic", "pdfinfo"), which=None):
    """编译与 PDF 检查工具必须在 PATH（brew poppler / install_local_tools.py）。"""
    which = which or shutil.which
    missing = [t for t in tools if which(t) is None]
    if missing:
        raise PreflightError(
            f"缺少 LaTeX 工具 {missing}（`brew install poppler` 或 `.venv/bin/python scripts/install_local_tools.py`）")
    return list(tools)


def probe_models(models_base, required=REQUIRED_MODELS, urlopen=None, timeout=2.0):
    """模型端点必须可达且含修复线与 OCR 线所需模型；失败必须响亮。"""
    urlopen = urlopen or urllib.request.urlopen
    url = models_base.rstrip("/") + "/models"
    try:
        with urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        ids = [m["id"] for m in payload["data"]]
    except Exception as exc:
        raise PreflightError(
            f"模型端点不可达或响应异常：{models_base}（{exc}；确认 Ollama 正在 11434 端口运行）") from exc
    for req in required:
        if not any(req in mid for mid in ids):
            raise PreflightError(f"模型 {req} 不在端点 {models_base}（现有：{ids}）")
    return ids


def preflight(skip_model=False, *, models_base=DEFAULT_MODELS_BASE,
              probe_python=probe_python, probe_latex_tools=probe_latex_tools,
              probe_models=probe_models):
    """真实 E2E 前置检查；skip_model 仅供日常开发，发布运行禁用。"""
    python = probe_python()
    latex_tools = probe_latex_tools()
    models = [] if skip_model else probe_models(models_base)
    return {"python": python, "latex_tools": list(latex_tools), "models": list(models)}


def write_evidence(results, out_dir):
    """落盘 e2e-results.json 与 SUMMARY.md；返回 (json_path, md_path)。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_passed = bool(results) and all(r.get("passed") for r in results)
    json_path = out_dir / "e2e-results.json"
    json_path.write_text(json.dumps({"results": results, "all_passed": all_passed},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E2E 发行验收结果", ""]
    for r in results:
        mark = "通过" if r.get("passed") else "未通过"
        lines.append(f"- {r.get('id')}: {mark}（{r.get('elapsed_seconds', 0):.1f}s）{r.get('detail', '')}")
    lines += ["", "总判定：" + ("全部通过" if all_passed else "未通过")]
    md_path = out_dir / "SUMMARY.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
