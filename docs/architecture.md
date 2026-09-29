# 架构与数据流

TeXada 有两个入口：Studio 处理单个 `.tex`，CLI 读取已有 `layout.json`。两者共用公式检查脚本和文本模型提供方，表格解析与结果交付各自实现。

```text
Studio：Monaco → FastAPI → 行内公式 / 简单 tabular 检查
                        → 公式模型候选或表格规则重算 → 回判
                        → Tectonic 前后编译 → diff → 人工采用 → 导出

CLI：layout.json → 按节点类型检查 → 最多两次候选尝试
                 → state.jsonl → 本轮 report.md
                 → 按输入与执行上下文复用结果
```

## Skill 指令怎样进入请求

[`skills_runtime.py`](../harness/docforensics/skills_runtime.py)只加载白名单内的 `doc-formula-verify/SKILL.md`，校验名称、路径及符号链接边界。[`OllamaProvider`](../harness/docforensics/vlm.py)将完整文件内容加入 system 消息，把待修公式放进独立的 user JSON，并记录 Skill、提示和工具哈希。

CLI 默认 `--skill-mode on`，Studio 默认 `SKILL_MODE=on`。`off` 省去 Skill 内容，保留基础提示、模型参数和检查流程；fixture 从文件读取预设候选，模型请求数为0。Python 负责固定编排、工具调用和重试预算，模型返回候选文本。其余 Skill 的脚本或操作约定见[入口映射](skills-technical-report.md#skill-与代码的对应关系)。服务间使用普通 HTTP，无 MCP 依赖。

## 检查与候选

公式先检查定界符，再由 SymPy 严格解析。只有可重试的语法失败进入模型流程，候选使用同一检查器回判；检查器故障会停止模型尝试。

Studio 对简单表格使用 Decimal 重算；CLI 检查布局树中的网格和显式合计约束。两者按输入位数设置求和精度，但数字与表格格式的支持范围不同。CLI 的真实模型提供方暂未实现表格修复。

Studio 的公式提取限于同一行的 `$...$`，尚未识别注释、verbatim 或多行数学环境。界面问题数应结合抽取范围阅读；数学等式的真值由人工核对。详细输入契约见[技术报告](skills-technical-report.md)。

## 状态存储与审阅

CLI 的终态由文档、节点 ID、输入哈希和执行上下文哈希共同标识。输入包含节点内容与已有 crop 字节；上下文包含程序、检查器、依赖、提供方、模型参数及 Skill。变化后重新检查，暂时故障在恢复后重试。日志逐条追加并落盘，报告只统计当前 `run_id`。同一状态目录只允许一个写入进程。[续跑协议](../harness/README.md)

Studio 在 `state/studio/jobs/<job_id>/` 保存 `job.json` 和 `events.jsonl`；编译产物位于 `state/studio/<文档名>/before-<job_id>/` 与 `after-<job_id>/`。完成结果可在重启后按 ID 读取；中断任务显示已有事件并要求新建。页面暂未提供任务历史列表。

候选通过检查后进入 diff，点击采用才更新浏览器编辑器，导出用于保存修改。报告包含前后文本、内容哈希、编译状态、剩余问题与请求记录。检查器接受和使用者采用是两个独立动作，当前事件日志记录前者。

## 部署组成

FastAPI 与任务调度使用单个 Uvicorn worker，面向持有共享令牌的可信用户。多用户隔离、可靠队列和整项目上传尚待实现。实机环境为 ARM64 Spark / NVIDIA GB10，Ollama 查询到的模型标签为 `qwen3.8:27b-q4_K_M`，实际请求仅含文本；环境与单次运行记录见[验证页](validation.md)。

Monaco 0.52.2 资源随仓库分发并保留 MIT 许可。Tectonic 负责 TeX 编译，Poppler 生成第一页预览；初次 TeX 包、依赖和模型下载可能访问网络。旧仪表盘另有 KaTeX CDN 依赖。安装与配置见 [README](../README.md)。
