# TeXada Studio 桌面窗口(macOS,可选)

在独立窗口(WKWebView)中打开本地 Studio,提供 Dock 图标与正常的开关机语义;
复用当前仓库检出的 `.venv` 与启动器,不打包 Python、模型或 TeX 资源。

## 生成与使用

```bash
.venv/bin/pip install -r desktop/requirements.txt   # 仅需一次;pywebview
.venv/bin/python desktop/build_app.py               # 生成 dist/TeXada Studio.app
open "dist/TeXada Studio.app"                       # 或在访达中双击
```

把 `TeXada Studio.app` 拖入 `~/Applications` 即可脱离 dist 目录使用。

## 行为

- **复用优先**:工作区已有存活的 Studio 会话(终端或先前窗口启动的)时,新窗口直接连它,不另起服务、退出也不影响它。
- **自持模式**:没有可用会话时,窗口进程拉起 `scripts/run-local-studio.py`(模型、端口与数据目录参数照常透传),关闭窗口即回收**自己启动**的后端。
- **强杀安全**:窗口进程意外终止(SIGKILL 等)时,它启动的后端会在数秒内检测到孤儿状态并优雅退出,不留残留端口或会话记录。
- 凭据仍存于用户数据目录的 `session.json`;窗口只加载回环私密入口,不引入新的网络路径。

## 已知限制

- 应用包是**本地生成的薄壳**:可执行文件内嵌生成时的仓库绝对路径。移动仓库或重建 `.venv` 后,重新运行 `desktop/build_app.py`。
- 运行期间 Dock/菜单栏进程名显示为 "Python"(Homebrew Python 的 GUI 载入机制所致);窗口标题与功能不受影响。若需要完整应用身份,可后续引入 py2app 打包,本目录刻意不引入该构建链。
- 仅支持 macOS;Windows/Linux 请继续使用浏览器入口(`scripts/start-local-studio.command` 或 `run-local-studio.py`)。

## 测试

```bash
.venv/bin/python -m unittest discover -s desktop -p 'test_*.py'
```

覆盖会话读取(回环/凭据校验)、存活判定、启动器命令行与环境组装、应用包结构生成;不启动 GUI、不联网。
