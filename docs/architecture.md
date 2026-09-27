# 架构与内存预算

## 总体架构（可直接画成评审图）

```text
用户入口（CLI：python -m docforensics run ./samples/）
        │
Agent Harness（规划循环、三态协议、state.jsonl 断点续跑）
        │
Skills 层
 ├─ doc-layout-parse  → 结构树 JSON（带 bbox、node.type、confidence）
 ├─ doc-table-audit   → 表格节点三态判定（scripts 交叉验算）
 ├─ doc-formula-verify→ 公式节点三态判定（SymPy + VLM 重识别）
 └─ doc-report        → 报告 + diff + 证据链
        │
工具层：本地文件 / OpenCV（重裁剪）/ SymPy（CPU）
        │
模型层：LiteLLM 网关
 ├─ vLLM：30B MoE（NVFP4）—— 质检仲裁（常驻）
 ├─ vLLM：8B VLM —— 版面解析与重识别（常驻）
 ├─ embedding 0.6B + reranker 0.6B（常驻）
 └─ llama-swap：按需装卸，重负载串行排队
        │
DGX Spark · 128GB 统一内存 · 常驻总量 < 60GB 安全线
```

## 内存预算表

| 组件 | 精度 | 常驻占用 | 说明 |
| --- | --- | --- | --- |
| 8B VLM（解析/重识别） | FP8 | ~10 GB | PaddleOCR-VL / HunyuanOCR 级 |
| 30B MoE（质检仲裁） | NVFP4 | ~17–20 GB | Step 系 MoE，仲裁与重生成 |
| embedding + reranker | 原生 | ~2–3 GB | 0.6B × 2 |
| KV cache 余量 | — | ~15 GB | 并发批处理预留 |
| 系统 + Agent harness | — | ~8 GB | DGX OS + Python 栈 |
| **合计** | | **< 60 GB** | 128GB 内留 2× 余量 |

关键论证：**解析模型与仲裁模型同时常驻、互为校验**（并行仲裁），24GB 消费级显卡无法同时容纳二者；
这是「为什么需要这台机器」的一句话答案。decode 单流速度不作为叙事点，用并发吞吐与仲裁质量说话。

## 断点续跑协议（state.jsonl）

每行一条决策事件：

```json
{"ts": "...", "doc": "samples/exam-01", "node_id": "f-014", "skill": "doc-formula-verify",
 "action": "RETRY", "attempt": 2, "reason": "sympy parse error: unexpected token", "evidence": "state/crops/f-014-a2.png"}
```

- 启动时读入已有事件，跳过已完成节点（幂等）
- `NEEDS_HUMAN` 不阻塞流水线，仅进报告
- 中断恢复演示 = 杀进程 → 重跑 → 从断点继续（demo 脚本第 5 段）

## 安全边界（对应官方 Scanned 检查）

- Skill 不发起网络请求；模型推理仅指向 127.0.0.1 网关
- 无硬编码路径、无密钥；文件读写限定工作目录
- 声明的工具边界与实际行为一致（不越权执行 shell）
