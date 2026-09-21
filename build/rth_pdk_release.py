# -*- coding: utf-8 -*-
"""交付版（release）运行时钩子：默认指向生产 PDK 后端。

由 build_onefile_release.py 通过 --runtime-hook 挂载，在任何业务代码之前执行。
用 setdefault：环境变量 PDK_BASE_URL 优先级更高，本机联调 / 临时切测试服
无需重新打包，直接设变量即可。
debug / 测试构建（build_onefile.py、build_console_debug.py）不挂本钩子，
默认仍为 http://127.0.0.1:8080（见 src/pdk/auth_service.py::PdkSettings.from_env）。
"""
import os

# 交付版（release）强制指向生产 PDK 后端。
# 用直接赋值（而非 setdefault）：即使打包/运行环境里残留
# PDK_BASE_URL=http://127.0.0.1:8080（本地联调遗留），也不会被带进交付包，
# 避免交付版误连本地。本机联调请改用 debug 构建（不挂本钩子，默认 127.0.0.1，
# 可用 PDK_BASE_URL 环境变量切测试服）。
os.environ["PDK_BASE_URL"] = "https://pdk.graddu.com"
