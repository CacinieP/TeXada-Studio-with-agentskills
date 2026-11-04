# py2app 捆绑入口:标记捆绑目录后以别名加载 desktop/app.py(避免占用 "app" 模块名,后端要 import webui/app.py)。
from __future__ import annotations

import importlib.util
import os
import sys

CONTENTS = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
RESOURCES = os.path.join(CONTENTS, "Resources")
os.environ.setdefault("TEXADA_BUNDLE_DIR", RESOURCES)

_desktop = os.path.join(RESOURCES, "desktop", "app.py")
_spec = importlib.util.spec_from_file_location("texada_desktop_app", _desktop)
_module = importlib.util.module_from_spec(_spec)
sys.modules["texada_desktop_app"] = _module
_spec.loader.exec_module(_module)

raise SystemExit(_module.main())
