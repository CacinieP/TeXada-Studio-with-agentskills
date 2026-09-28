"""修复提供方：fixture（离线测试替身）与 Ollama/OpenAI 兼容文本端点。

- CLI 真实模式在显式指定 --vlm 时启用，地址由操作者提供，并未强制回环地址。
- 当前仅传文本，没有图像输入；模型与依赖预备好后才能讨论断网运行。
- fixture 模式是开发/演示用的测试替身，报告中必须如实标注 provider。
"""

import json
import re
import urllib.request


class FixtureProvider:
    name = "fixture (offline test double)"

    def __init__(self, repairs_file=None):
        if repairs_file:
            with open(repairs_file) as f:
                self.repairs = json.load(f)
        else:
            self.repairs = {}

    def repair_formula(self, node):
        r = self.repairs.get(node["id"], {})
        return r.get("latex")

    def repair_table(self, node):
        r = self.repairs.get(node["id"], {})
        return r.get("rows")


class OllamaProvider:
    """OpenAI 兼容 /v1/chat/completions（Ollama serve 或 vLLM 均可）。"""

    name = "local-vlm"

    def __init__(self, base="http://127.0.0.1:11434", model="qwen2.5vl:7b"):
        self.base = base.rstrip("/")
        self.model = model

    def _chat(self, prompt, max_tokens=300):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            self.base + "/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())

    def repair_formula(self, node):
        latex = (node.get("data") or {}).get("latex", "")
        prompt = (
            "The following LaTeX was OCR-extracted and failed a symbolic syntax check.\n"
            'Return STRICT JSON {"latex": "..."} with the corrected LaTeX only. No commentary.\n'
            f"broken latex: {latex}"
        )
        try:
            resp = self._chat(prompt)
            text = resp["choices"][0]["message"]["content"].strip()
            m = re.search(r"\{.*\}", text, re.S)
            if not m:
                return None
            return json.loads(m.group(0)).get("latex")
        except Exception:
            return None

    def repair_table(self, node):
        # TODO(P1): VLM 表格重提取；当前表格修复失败走 NEEDS_HUMAN
        return None
