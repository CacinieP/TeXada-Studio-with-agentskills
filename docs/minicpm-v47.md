# MiniCPM-V 4.7：Studio 单模型适配

真实协议、合成候选与编译边界见[本次验收](minicpm-v47-evidence.md)。

TeXada Studio 与 [TeXada Math Agent](https://github.com/CacinieP/TeXada-the-Math-Agent) 共用 MiniCPM-V-4.7-1B，分别承担文档编辑和数学表达工作流。Studio 的模型只提议公式语法修复；Python 保留确定性校验、至多两次尝试、审阅差异和人工确认。表格合计仍由本地精确计算处理。

## 启动

先创建项目虚拟环境并安装依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r webui/requirements.txt
```

通过当前进程环境设置 `DEMO_TOKEN` 和 `VLM_API_KEY`，然后启动：

```sh
export TEXADA_STUDIO_PYTHON="$PWD/.venv/bin/python"
./scripts/run-minicpm-v47-studio.sh
```

启动器固定 `VLM_MODEL=MiniCPM-V-4.7-1B`，默认端点为 `https://api.modelbest.cn/v1`。`VLM_API_KEY` 优先；未设置时读取 `TEXADA_OPENAI_API_KEY`，便于和 Math Agent 共用进程环境。服务端发送 Bearer 鉴权；密钥不进入提示词、配置指纹、修复日志或浏览器响应。不要把密钥放到 URL、命令参数或仓库文件中。

`.env.example` 中的密钥与端点都是注释占位。复制并加载它只设置非敏感默认值，不会清空已经导出的 `DEMO_TOKEN`、`VLM_API_KEY` 或覆盖专用启动器的默认端点。密钥通过进程环境提供，启动器本身不读取 `.env` 文件。

直接启动 WebUI、调用 provider 或使用 CLI 时，模型默认值也统一为 `MiniCPM-V-4.7-1B`，端点仍默认本机 loopback。ModelBest 端点由专用启动器选择。设置 `VLM_BASE_URL` 与 `VLM_MODEL`（CLI 使用 `--vlm` 与 `--vlm-model`）可显式选择其他 OpenAI 兼容端点和模型；主机地址和以 `/v1` 结尾的 API 根地址均可使用。

## 模型契约与验证边界

- 每次 MiniCPM-V 4.7 修复请求按[官方协议](https://github.com/OpenBMB/MiniCPM-V/blob/main/docs/api.md)发送 `chat_template_kwargs: {"enable_thinking": false}`，不解析推理正文。
- 候选必须是严格 JSON，且只能包含一个非空单行字符串字段 `latex`；重复字段、Markdown、额外字段、空结果、截断结果与拒绝响应均不会成为编辑。解码后的候选禁止 C0 控制字符和 DEL，避免 JSON 的 `\f` 等转义变成控制字符后被公式检查器误判。
- MiniCPM 使用真实的 `user` / `assistant` 示例消息对，演示合法 JSON 分式、TeX 大括号的位置和双反斜杠转义；最后一条 `user` 消息才是当前公式。加载的 Skill 与模型参数在 on/off 对照中保持原有约束。无效响应仍直接拒绝，不自动补反斜杠或改写响应内容。
- `SKILL_MODE=on/off` 只改变系统指令是否加载本地 Skill，端点、模型、校验器和尝试上限保持一致。
- 语法检查通过表示解析完成；不证明数学语义一致，仍需人工确认。
- 当前 Studio 路径发送公式文本，不发送图片。这是文本修复适配，不是图像 OCR 验收。

## 本地量化部署

模型权重：[openbmb/MiniCPM-V-4.7-1B](https://huggingface.co/openbmb/MiniCPM-V-4.7-1B)；[GGUF 权重](https://huggingface.co/openbmb/MiniCPM-V-4.7-1B-gguf)。如果本机服务提供与上方兼容的 `/v1/chat/completions`，将 `VLM_BASE_URL` 指向它即可沿用同一链路。Q4 的运行、图片投影器和精度需要单独验收；本次 API 适配不等于 Q4 已运行。

## 无网络回归

```sh
.venv/bin/python -m pip install -r webui/requirements-test.txt
.venv/bin/python -m unittest discover -s harness/tests -p 'test_*.py'
.venv/bin/python -m unittest discover -s webui -p 'test_*.py'
```

HTTP 契约测试检查 `/v1` 不重复、鉴权仅存在于请求头、MiniCPM 关闭思考、密钥不进入日志和指纹，以及旧 Ollama 入口的兼容性。真实 API、实际编辑/编译和本地量化验收须分别记录。
