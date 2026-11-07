# 本地 API 与版本绑定

仅在需要自动化现有 Studio、浏览器工具不足或验证接口时读取本页。路由以
[`webui/app.py`](../../../webui/app.py) 为准，模型、OCR 限制以
[`webui/local_runtime.py`](../../../webui/local_runtime.py) 为准。

## 连接与凭据

从**本次选定工作区**的 `session.json` 在进程内读取 `base_url`、`url`、`running`；
启动器默认使用系统用户数据目录，也允许 `--state-dir`。不要扫描其他工作区寻找凭据。
核对 HTTP 回环地址、存活服务及会话后，从私密入口查询参数取得 token，在内存中构造请求。
Studio API 使用 `token` 查询参数；不要把真实 token 或私密入口写进 shell 参数、日志、示例或共享文件。
本机请求绕过代理，禁止把凭据跟随重定向发送到其他地址。401 时恢复正确会话，不关闭鉴权。

编辑器资源有单独的受限 cookie；持有资源 cookie 不代表 API 已鉴权。浏览器中的未保存缓冲区
只能从编辑器取得，不能用 `/file` 的磁盘内容代替。

## 常用路由

下表中的路径统一以 `/api/studio` 开头。JSON 请求设置 `Content-Type: application/json`。

| 方法、路由 | 输入或返回要点 |
| --- | --- |
| `GET /config` | 工具、配置与限制；默认不探测模型 |
| `POST /probe` | `{base_url, model}` 检查草稿连接，不保存；也可不带 body 检查已保存配置 |
| `POST /settings` | 精确字段 `{base_url, model}`；仅本机回环 HTTP，影响此 Studio 的连接设置 |
| `GET /files` | 文档列表与本地/示例来源 |
| `GET /file?name=…` | `{name, content, sha256, origin, ...}`；`sha256` 是已保存版本 |
| `POST /create` | `{name, content}`；重名返回 409 |
| `POST /save` | `{name, content, expected_sha256}`；现有文档须提供读取版本的 SHA256 |
| `POST /analyze` | `{name, content}`；仅检查，不返回模型修复候选 |
| `POST /fix` | `{name, content, planner_mode:false, skill_selection:false}`；立即返回 `{job}` |
| `GET /fixstatus?id=…` | `done`、`error`、`result`、日志和审阅状态；`done` 不等于成功 |
| `GET /jobs` | 最近任务；完成但来源不匹配的历史候选不可采用 |
| `POST /jobs/{id}/cancel` | 请求停止；等待状态，不假定正在运行的 HTTP 推理已被即时终止 |
| `POST /jobs/{id}/decision` | `{name, content, candidate_sha256, decision}`；`content` 是原文，决定为 `accept` 或 `reject` |
| `POST /preview` | `{name, content}`；返回 `compile_ok`、`preview_ok`、`page_count`、页面 URL 与 PDF URL |
| `POST /import` | `{name, mime_type, data_base64, page_start, max_pages}`；只产生需审阅的转写候选 |

单个 `.tex` 上限 2 MiB。导入上限 12 MiB；支持 PNG/JPEG/WebP/PDF，每次最多 5 页，
PDF 起始页从 1 计数。以 `/config` 的实际限制与接口校验为准。导入不会创建或覆盖文档；
审阅后使用 `/create` 写入候选。

检查的 `content` 应明确绑定实际目标。当前 UI 的 `currentContent()` 在普通视图读取主编辑器，
在候选 diff 视图读取右栏候选；“检查”、预览编译和源码导出使用该内容。
纯 API 路线也应明确取得目标缓冲区，不要用磁盘原文的检查结果代替未保存内容或候选的检查结果。

## 将已审阅内容交给 CLI

图片/PDF 转写不会自动形成节点树。先对照原件将目标公式或表格整理成独立 `layout.json`，
使用唯一文档/节点 ID，保留实际来源页码；表格使用明确的 `rows` 与可信的 `expected`，
不编造参考合计或裁剪文件。仅检查时，从仓库根目录运行：

```bash
PYTHONPATH=harness .venv/bin/python -m docforensics run /path/to/layout-directory \
  --state state/review-check-01
```

将示例输入目录换成用户本次的目录，状态目录换成尚未使用的本轮目录。
省略 `--vlm` 和 `--fixture-repairs` 时没有候选提供方；查看报告中的实际节点状态，
不要只根据进程退出码声称表格全部通过。完整输入契约见 [Harness 手册](../../../harness/README.md)。

## 一次候选审阅与保存

1. 记录当前编辑器文件名、内容、文件切换标记和编辑器版本；取得对应原文 SHA256。
2. 发起 `/fix` 后轮询该任务。只有 `done=true`、无错误且结果完整时处理候选。
3. `result.original_sha256` 须匹配来源内容，`result.candidate_sha256` 须匹配 `fixed_content`；
   审阅前还要核对编辑器版本与文件标记未变化。内容相同但经过编辑撤销的旧候选也不能直接复用。
4. 按已有授权审阅差异并发送显式决定。`/decision` **只记录决定，不写编辑器或文档文件**。
   UI 路线由浏览器处理采用；纯 API 路线确需写文件时，以此前读取的 `expected_sha256` 单独 `/save`。
   不混用两条路线去覆盖浏览器中的未保存编辑。
5. 409 表示版本、绑定或决定冲突。保留内容，重新读取并比较或另存；不要改哈希来让旧候选通过校验。

`compile_ok=true` 与 `preview_ok=true` 分别表示 PDF 已生成和页面可渲染；两者均不证明数学正确。
使用该次 `/preview` 返回的不可变 URL 下载对应页面及 PDF，保留鉴权；不要猜测“最新 PDF”路径。
当前缓冲区变化后重新编译。交付中文页面前做视觉核对，避免把缺字的图片当作预览成功。

## 来源与报告

`imports/{id}/candidate.json` 保存 OCR 来源哈希、页码、模型和候选；`source.*` 保存原资料。
`jobs/{id}/job.json` 与 `events.jsonl` 保存修复与审阅历史。它们属于选定用户数据目录，
不应直接修改或整体公开。界面 `.audit.md` 不能自动替代这些所有记录，按
[doc-report](../../doc-report/SKILL.md) 核对实际导出范围。
