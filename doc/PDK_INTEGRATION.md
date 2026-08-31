# PDK 授权接入说明

智播豆启动登录现已接入 `src/pdk/pdk_client.py`，不再使用本地 `admin` 假登录或本地卡密文件模拟激活。

## 运行环境

项目虚拟环境安装：

```powershell
E:\zhibodou-ai\zhibodou\.venv\Scripts\python.exe -m pip install -r E:\zhibodou-ai\zhibodou\requirements.txt
```

## 配置

连接信息通过环境变量提供。与 `pdk_client.py::_demo` 一致，开发环境默认使用 `http://127.0.0.1:8080` 和 `appId=2`。默认只发现并显示服务端返回的 `bizCode`，不在客户端额外限制业务编码。

```powershell
$env:PDK_BASE_URL = "https://你的授权服务地址"
$env:PDK_APP_ID = "2"
# 可选：只有需要把安装包固定到某一业务时才设置
$env:PDK_BIZ_CODE = "ZHIBO_AI"
$env:PDK_REQUIRE_HTTPS = "true"
$env:PDK_VERIFY_TLS = "true"
$env:PDK_PUBLIC_KEY_PIN = "服务端公钥指纹"

# 可选：只用于预填登录窗口，不写入源码或普通日志
$env:PDK_PHONE = "手机号"
$env:PDK_PASSWORD = "密码"
$env:PDK_CARD_KEY = "新设备激活卡密"
```

生产环境必须使用 HTTPS、启用 TLS 校验并配置 `PDK_PUBLIC_KEY_PIN`。不要把真实密码、卡密或 Token 提交到 Git。

## 登录流程

普通登录：

```text
fetch_public_config
  → business_info
  → login(password)
  → verify_session
  → profile
  → device_license_current（仅 DEVICE_LICENSE）
  → 进入主界面
```

新设备在服务端返回 `40380` 时，客户端会自动切换到“激活”页，使用手机号、密码和卡密重新调用 `login(password, card_key)`。

点击退出登录或关闭主窗口时会调用服务端 `logout()`；即使网络注销失败，本地 Token 和 HTTP Session 也会被强制清理。

## 安全边界

- 会话当前只保存在内存，不会把 Token 明文写入 `src/data`。
- 主界面只显示脱敏手机号、业务、状态、到期时间和剩余次数。
- `pdk_client.py` 的 HTTP 诊断记录会对密码、卡密、Token、手机号和设备 ID 脱敏。
- 没有有效 PDK 会话时，总电源不会开启。
