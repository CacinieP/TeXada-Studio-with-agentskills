# 节点部署手册（demo-node 实测）

> 目标硬件：DGX Spark（GB10 · 128GB 统一内存 · 驱动 580.173.02 / CUDA 13.0 · Ubuntu 24.04 ARM64）
> 原则：全部用户级安装，不动系统配置（赛事红线），模型层只绑 127.0.0.1。

## 1. 代码上机

```bash
rsync -az --exclude .git --exclude .venv --exclude state --exclude dist \
  ./ spark:~/doc-forensics/          # ssh config 别名 spark（-p <SSH_PORT>）
```

## 2. 依赖与端到端自检（无需 GPU，5 分钟）

```bash
ssh spark
python3 -m venv ~/.venvs/docf
~/.venvs/docf/bin/pip install -r ~/doc-forensics/harness/requirements.txt
cd ~/doc-forensics && rm -rf state/node1
PYTHONPATH=harness ~/.venvs/docf/bin/python -m docforensics run samples \
  --state state/node1 --fixture-repairs samples/fixture_repairs.json
```

预期：`exam-01 OK=3 / paper-01 OK=2 NEEDS_HUMAN=1 / report-01 OK=2`（fixture 提供方，
报告如实标注）。依赖版本注意：**sympy 的 LaTeX 解析器只兼容 antlr4-python3-runtime 4.11**。

## 3. 模型层（Ollama 用户级）

宿主机无 nvcc、不便装 vLLM 时，Ollama 用户级部署即可满足 P0。

**模型选型（2026-09-28 实测定稿）**：

| 角色 | 模型 | 说明 |
| --- | --- | --- |
| 解析 + 重识别 + 仲裁（单模型） | `qwen3.8:27b-q4_K_M`（~16GB） | **Qwen3.8 原生多模态**（官方模型卡：Native support for image and video），一个模型覆盖三个角色，常驻内存减半 |
| 兼容回退 | `qwen2.5vl:7b`（~6GB） | 管线验证用；真实回路已验证（修复 + 幻觉拦截均工作） |
| P1 升级 | `qwen3.8:27b-nvfp4` | 原生 NVFP4；**Ollama 无法加载（需 MLX 运行时）**，走 vLLM/NGC 容器路线 |
| ~~Step 集成~~ | `stepfun-ai/Step-3.7-Flash` | **单机不可行（已否决）**：BF16 403GB、NVFP4 129GB、FP8 213GB，均超出节点 121GB 可用内存；无 GGUF。除非组委会提供双机互联或 Step 云端 API，否则不投入 |

```bash
mkdir -p ~/bin ~/lib
curl -fL -C - https://gh-proxy.com/https://github.com/ollama/ollama/releases/download/v0.34.4/ollama-linux-arm64.tar.zst -o /tmp/ollama.tar.zst
tar --zstd -xf /tmp/ollama.tar.zst -C ~/lib          # 得到 ~/lib/bin/ollama
tmux new-session -d -s ollama "$HOME/lib/bin/ollama serve"   # 127.0.0.1:11434
~/lib/bin/ollama pull qwen3.8:27b-q4_K_M              # 27B 原生 VL + 仲裁
~/lib/bin/ollama pull qwen2.5vl:7b                    # 可选：回退验证模型
```

> GitHub 直连在节点出口不可用（连接被重置），实测走 gh-proxy.com 镜像 10+ MB/s；
> 模型权重从 registry.ollama.ai 直连 11-12 MB/s。大文件一律节点内直下，禁止 scp 上传（赛事守则）。
> 注意：sympy 只兼容 antlr4-python3-runtime 4.11；节点系统 python 为 PEP 668 管理，pip 一律走 venv。

### Step-3.7-Flash 权重下载（ModelScope，节点内直下）

```bash
~/.venvs/docf/bin/pip install modelscope
tmux new-session -d -s step '~/.venvs/docf/bin/modelscope download \
  --model stepfun-ai/Step-3.7-Flash --local_dir ~/models/step3.7-flash'
```

## 4. 真实修复回路（已验证）

```bash
cd ~/doc-forensics && rm -rf state/node2
PYTHONPATH=harness ~/.venvs/docf/bin/python -m docforensics run samples \
  --state state/node2 --vlm http://127.0.0.1:11434 --vlm-model <模型tag>
```

qwen2.5vl:7b 实测（2026-09-28）：f-101 定界符补全 ✓、f-003 花括号修复 ✓、
**f-002 VLM 幻觉（瞎编下标 `a_\text{system}`）被 SymPy 仲裁拒绝转人工 ✓** ——
「解析与仲裁互为校验」的评审叙事已有实机证据。报告 provider 标注 `local-vlm`；
此模式结果才可进 BENCHMARK.md。表格 VLM 重提取为 P1（当前表格修复走 NEEDS_HUMAN）。

## 5. P1/P2 升级路径

- vLLM + NVFP4：NGC 容器（nvcr.io 可达），ARGB64 + CUDA 13 镜像，吞吐优于 Ollama
- Step 系 MoE 仲裁模型（赛方合作模型）按官方渠道替换 `--vlm-model`
- 内存预算见 docs/architecture.md（常驻 < 60GB 安全线）
