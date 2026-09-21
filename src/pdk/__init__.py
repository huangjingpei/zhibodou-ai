# PDK 子系统包：auth_service / pdk_client / credential_store。
# 显式提供 __init__.py 使其成为常规包，避免 PyInstaller 静态分析
# 收不到命名空间包子模块（同 live_plate 缺 __init__ 的教训）。
