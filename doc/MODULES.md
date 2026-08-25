# 智播豆 · 模块设计文档

> 本文档说明 `src/` 下按「单一职责 + 功能分组」拆分后的包结构、依赖关系与运行方式。
> 原单体文件 `zhibodou_full.py`（1100 行）已重构为多个小模块，并归并到 7 个功能包中，入口为 `main.py`。
> 旧文件保留为 `zhibodou_full.py.bak` 仅供对比，不再参与运行。

---

## 1. 设计目标

- **单一职责**：每个文件只做一件事（路径 / 状态 / 配置 / 授权 / ADB / 控件定位 / 文本输入 / 投屏嵌入 / 弹幕 / 抓屏 / 直播 / 电源 / 弹窗 / UI / 入口）。
- **功能分组**：相关模块再归并到目录包（core / settings / device / screen / broadcast / audio / gui），项目骨架更清晰。
- **可维护**：改 UI 不动逻辑，改发送逻辑不动 UI；升级某个能力只动对应包里的文件。
- **无循环依赖**：所有跨包引用自上而下，依赖图是 DAG（见 §3）。包内 import 统一用**绝对导入**（`from gui.ui import set_status`），`src/` 为导入根。
- **入口统一**：`python main.py`（或双击 `一键启动.bat`）启动。

---

## 2. 目录结构与模块清单

```
src/
├── main.py                  # 程序入口：构建 UI、接线按钮、初始化、主循环
├── core/                    # 基础设施（零内部依赖）
│   ├── paths.py             # 基于 __file__ 推导所有资源/运行时路径
│   ├── state.py             # 全局运行时状态（替代散落的 global）
│   └── doubao.py            # 豆包 APP 控件锚点常量
├── settings/                # 配置与授权
│   ├── config.py            # pyautogui 初始化、WS 地址、默认话术、配置读写
│   └── auth.py              # 机器码绑定、授权校验、管理员密码
├── device/                  # 设备通信（只碰手机）
│   ├── adb_utils.py         # ADB 底层命令封装
│   ├── ui_locator.py        # uiautomator 控件树解析 + 动态坐标定位
│   ├── input_text.py        # 文本输入：ADBKeyboard 直输 + 剪贴板降级 + 统一发送入口
│   ├── doubao_check.py      # 豆包就绪体检：灭屏/锁屏→自动唤醒拉起 + 运行/前台/对话界面/无遮挡/可发送
│   └── wake_unlock.py       # 灭屏/锁屏检测 + 亮屏唤醒 + 自动拉起豆包到对话页
├── screen/                  # 投屏与画面
│   ├── win_embed.py         # Windows 原生 API：嵌入 scrcpy 窗口并锁死样式
│   ├── scrcpy_embed.py      # scrcpy 子进程启停、窗口嵌入（视频低码率/低帧率 + 音频低延迟 PCM；分级回退防单参数不兼容）
│   ├── capture.py           # 定时截图抓屏 + 日志刷新
│   └── danmu.py             # 弹幕/礼物/点赞解析 + WebSocket 接收循环
├── broadcast/               # 直播业务
│   ├── live.py              # 开播预演、区间话术循环、音频模式、启停
│   └── power.py             # 总电源开关 + 开机自检
├── audio/                   # 语音
│   ├── tts.py               # TTS 语音播报（外音模式）
│   └── vad.py               # VAD 本地语音活动检测（只读旁听，驱动下一轮话术）
└── gui/                     # 界面
    ├── ui.py                # 构建全部 Tk 界面、暴露控件引用、set_status()
    └── dialogs.py           # 密码修改 / 授权管理弹窗
```

| 模块 | 所在包 | 职责 | 关键导出 |
|---|---|---|---|
| `core/paths.py` | core | 推导所有资源/运行时文件路径 | `SCRCPY_EXE` `ADB_EXE` `ADBKEYBOARD_APK` `CONFIG_JSON` `PWD_FILE` |
| `core/state.py` | core | 全局运行时状态 | `system_power` `live_running` `scrcpy_hwnd` `msg_queue` `locker` |
| `core/doubao.py` | core | 豆包控件锚点常量 | `DOUBAO_INPUT_ID` `DOUBAO_SEND_ID` `DOUBAO_PKG` |
| `settings/config.py` | settings | 配置读写、默认话术、WS 地址 | `load_config()` `save_config()` `DEFAULT_CFG` `WS_SERVER_URL` |
| `settings/auth.py` | settings | 机器码绑定、授权、管理员密码 | `verify_admin_pwd()` `change_admin_password()` `init_admin_password()` |
| `device/adb_utils.py` | device | ADB 底层命令封装 | `adb_shell()` `adb_tap()` `adb_set_phone_clipboard()` `adb_devices_online()` `doubao_in_foreground()` |
| `screen/win_embed.py` | screen | Windows 原生 API 嵌入窗口 | `real_embed_window()` `find_scrcpy_main_hwnd()` `get_tk_widget_hwnd()` |
| `device/ui_locator.py` | device | 控件树解析 + 动态坐标定位 | `get_input_center()` `tap_send_button()` `tap_input_box()` `_dump_ui_xml()` |
| `device/input_text.py` | device | 文本输入与统一发送入口 | `send_text_to_doubao()` `check_adbkeyboard_installed()` `get_adbkeyboard_ime_id()` |
| `device/doubao_check.py` | device | **豆包就绪体检（发送前置检测）** | `check_doubao_ready()` `doubao_installed()` `doubao_running()` `in_conversation_screen()` `is_occluded()` `can_send()` |
| `device/wake_unlock.py` | device | 灭屏/锁屏检测 + 亮屏拉起豆包 | `is_screen_off()` `is_keyguard_locked()` `wake_screen()` `launch_doubao()` `enter_first_conversation()` `ensure_doubao_awake_and_foreground()` |
| `screen/scrcpy_embed.py` | screen | scrcpy 启停与嵌入 | `start_scrcpy_embed()` `lock_scrcpy_loop()` `stop_scrcpy_embed()` |
| `screen/danmu.py` | screen | 弹幕解析 + WS 接收 | `parse_danmu()` `ws_danmu_loop()` |
| `screen/capture.py` | screen | 定时截图抓屏 | `screen_capture_loop()` `start_capture()` `stop_capture()` |
| `audio/tts.py` | audio | TTS 播报 | `speak_text()` |
| `audio/vad.py` | audio | VAD 监听豆包语流，驱动下一轮 | `AudioPlaybackMonitor` `list_audio_input_devices()` `quick_probe()` |
| `broadcast/live.py` | broadcast | 直播控制 | `run_pre_meet()` `start_live()` `stop_live()` `send_script_content()` |
| `broadcast/power.py` | broadcast | 总电源 + 自检 | `toggle_power()` `power_on_self_check()` |
| `gui/dialogs.py` | gui | 密码/授权弹窗 | `dialog_modify_pwd()` `dialog_auth_mgr()` |
| `gui/ui.py` | gui | 构建 Tk 界面、set_status、音量指示条 | `build_ui()` `set_status()` `set_volume_meter()` `reset_volume_meter()` `ui.root` `ui.btn_power` ... |
| `main.py` | （入口） | 构建 UI、接线回调、初始化、主循环 | `main()` |

> `gui.ui` 里的控件（`ui.btn_power`、`ui.lab_sys_status`、`ui.embed_container`）以**模块级变量**形式暴露，其他模块通过 `from gui import ui` 读写，避免在逻辑模块里散落 `global`。

---

## 3. 依赖关系（无环）

```
main.py
  ├─ gui.ui        ── settings.config ── core.paths
  ├─ core.state
  ├─ settings.auth ── core.paths
  ├─ broadcast.power  ── device.adb_utils, device.input_text, device.doubao_check,
  │                      device.wake_unlock, screen.scrcpy_embed,
  │                      screen.capture, settings.auth, core.doubao, core.paths
  ├─ broadcast.live   ── device.input_text, screen.danmu, screen.capture,
  │                      settings.config, core.state
  ├─ screen.capture   ── core.state, gui.ui
  ├─ screen.scrcpy_embed ── screen.win_embed, gui.ui, core.state, core.paths
  ├─ screen.danmu     ── settings.config, core.state, gui.ui
  └─ gui.dialogs      ── settings.auth

device.input_text   ── device.ui_locator, device.adb_utils, device.wake_unlock, core.doubao, gui.ui
device.doubao_check ── device.adb_utils, device.ui_locator, device.wake_unlock, core.doubao
device.wake_unlock   ── device.adb_utils, device.ui_locator, core.doubao
device.ui_locator   ── device.adb_utils, core.doubao, gui.ui
device.adb_utils    ── core.paths, gui.ui(仅函数内懒加载 set_status)
screen.win_embed    ── (ctypes / pygetwindow)
```

要点：
- 叶子包模块（`core.paths` `core.state` `core.doubao`）零内部依赖。
- `gui.ui` 不反向依赖任何业务逻辑模块（按钮回调由 `main.py` 统一接线），因此不存在循环。
- `device.adb_utils` 仅**在函数内** `from gui.ui import set_status`，不会在导入期触发 UI 模块副作用。
- 包内/跨包 import 一律用绝对导入（以 `src/` 为根），例如 `from gui.ui import set_status`、`from settings.config import load_config`、`from device.adb_utils import adb_shell`。

---

## 4. 关键流程

### 4.1 启动
`main.py: main()` → `ui.build_ui()`（建界面+回填配置）→ 接线按钮 → `auth.init_admin_password()` → **后台线程 `power.startup_readiness_check()`**（对豆包做一次只读体检，结果写屏幕日志 + 刷新状态栏）→ `root.mainloop()`。这样一开程序就能直接看到「豆包是否就绪」。

### 4.2 开机（总电源）
`broadcast.power.toggle_power()` → `power_on_self_check()`：
- **`device.doubao_check.check_doubao_ready()`**：查 ⓪豆包**是否已安装**（`pm list packages` 精确匹配，未装直接报 ❌）①adb 设备在线 → **灭屏/锁屏优先分支**：若 `wake_unlock.is_screen_off()`/`is_keyguard_locked()` 为真，先 `ensure_doubao_awake_and_foreground()` 自动亮屏+拉起豆包到对话页（无锁屏全自动；PIN/密码/图案锁屏停在解锁界面并提示手动解锁，本次自检标为未就绪）；②豆包已运行且在**前台**(resumed activity) ③处于**对话界面**(控件树有输入框) ④界面**无遮挡**(焦点窗口/覆盖层不是豆包) ⑤**可发送**(输入框存在且可编辑)。
- **离线降级（无 adb 设备）**：`check_doubao_ready()` 返回 `mode='offline'`，不阻塞程序，给出「手动模式」指引——用户用肉眼确认豆包状态并手动操作；重连 adb 后程序自动恢复在线体检。
- ADBKeyboard 是否安装 / 是否为当前输入法（仅在线模式检查）。
通过后点亮按钮 → `screen.scrcpy_embed.start_scrcpy_embed()`（拉起 scrcpy 子进程并嵌入窗口）→ 后台 `lock_scrcpy_loop()` 锁死窗口。

### 4.3 发送话术（开播预演 / 直播）
`broadcast.live.run_pre_meet()` 或 `broadcast.live.send_script_content()` → `device.input_text.send_text_to_doubao()`：
0. **发送前置灭屏恢复**：若 `wake_unlock.is_screen_off()/is_keyguard_locked()` 为真，先 `ensure_doubao_awake_and_foreground()` 自动亮屏拉起豆包；锁屏则报错提示手动解锁（调用方重试）。避免「黑屏假阴性」误报。
1. `_clear_input_box()` 清空旧草稿；
2. ADBKeyboard 已装 → `ime enable` + `ime set` + 重新聚焦 → `adb_input_text_via_ime()`（base64 广播直输）；
3. 未装 → 降级 clipper 剪贴板（仅老系统可用）；
4. `device.ui_locator.tap_send_button()` 控件定位点击发送，并做「发送后验证 + 自动重试」。

### 4.4 自动直播循环
`broadcast.live.start_live()` → 起 `ws_danmu_loop()`（弹幕）+ `auto_live_loop()`（按区间 1→2→3 循环调 `send_script_content`）+ `screen.capture.start_capture()`；每次发送后 `count_down_work()` 倒计时，结束才解除 `can_next_speak` 节流锁。

### 4.5 VAD 音频源选择与 OBS 路由
VAD（`audio/vad.py`）只读旁听电脑本地音频【输入】设备，判断豆包是否在说话，**不改原始音频数据**。
scrcpy 与 VAD 是两个独立进程，靠 Windows 音频回环设备桥接。**声音链路**：
`手机发声 → ADB → scrcpy(经 SDL2) → 【CABLE Input 虚拟线】→ CABLE Output 镜像 → ①VAD 旁听 ②OBS 捕获 ③(开侦听)扬声器`。
其中 **scrcpy 往哪送** 由 `settings/config.py` 的 `scrcpy_audio_output_device` 控制（启动 scrcpy 时注入 `SDL_AUDIO_DEVICE_NAME`，只定向 scrcpy 的音频、不影响系统其他声音）；**VAD 从哪收** 由 `vad_input_device` 控制。两者必须成对（均为 Virtual Cable / 均为 Voicemeeter）。

| 场景 | scrcpy_audio_output_device（送） | vad_input_device（收） | OBS 侧处理 |
|---|---|---|---|
| **OBS 用户首选** | 留空（用系统默认播放设备） | 留空（启用 Windows「立体声混音」后自动命中） | OBS「桌面音频」自动包含豆包、你也能正常听，零改动 |
| 用 VB-Audio Virtual Cable | `"CABLE Input (VB-Audio Virtual Cable)"` | `"CABLE Output"` | OBS 加「CABLE Output 音频输入捕获」；需给 CABLE Output 开「侦听」才能用耳朵听 |
| 用 Voicemeeter | `"VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)"` | `"VoiceMeeter Output"` | 1 源→多消费者正解：扇出到扬声器 + 虚拟输出，OBS 与 VAD 各读一份 |

- 多个程序可同时读同一输入设备（Windows 共享模式），VAD 与 OBS **不冲突**。
- `SDL_AUDIO_DEVICE_NAME` 对设备名大小写/空格敏感，填错会静默回退到默认设备；接不上就跑 `python -m src.audio.vad` 核对设备全名，或把 `CABLE Input` 直接设成 Windows 默认播放设备作为兜底。
- 不确定设备名？运行 `python -m src.audio.vad`（或看开机自检日志）会列出所有输入设备与索引，带「回环/混音」标记的就是该填的；也可直接填索引数字（如 `"3"`）。
- 没装 pyaudio / 没有任何输入设备时，VAD 自动旁路为「固定等待」并在日志明确告警，不会假生效。

---

## 5. 运行方式

```bash
cd E:\zhibodou-ai\zhibodou
pip install -r requirements.txt      # 安装依赖（pyautogui/pyttsx3/websocket-client/pyperclip/pygetwindow）
双击 src\一键启动.bat                  # 或直接：python src/main.py
```

前置条件：USB 连手机并授权调试；手机安装并启用 ADBKeyboard；豆包停留在前台对话页。

---

## 6. 重构说明与注意点

- **状态集中**：原 `global system_power / live_running / scrcpy_hwnd ...` 全部迁入 `core/state.py`，模块用 `state.xxx` 读写。
- **按钮接线在 `main.py`**：`gui.ui.build_ui()` 不绑定业务回调（避免 `gui.ui` 反向依赖业务逻辑），由入口统一 `config`/`power`/`live` 等接线。
- **包化导入**：所有跨模块引用改为以 `src/` 为根的绝对导入（如 `from gui.ui import set_status`）。`main.py` 开头会把自身所在目录插入 `sys.path`，因此双击 `.bat`（cwd=src）或从项目根 `python src/main.py` 均可正确解析包。
- **`adb devices` 必须用 `run_adb(['devices'])`**：曾误写成 `adb_shell('devices')`（会变成 `adb shell devices`，无效），已在 `device/adb_utils.py` 修正。
- **向后兼容**：旧单体 `zhibodou_full.py.bak` 仅留作对照；`ut/` 下两个测试已改为直接 `import` 新包模块（`from device.input_text import ...` / `from device.ui_locator import ...` / `from device.adb_utils import ...` / `from core.doubao import ...`）。
- **`.bat` 编码**：`一键启动.bat` 须为 **GBK + CRLF**（见项目记忆）；已改为启动 `main.py`。
