# 智播豆项目核心技术扫描与 Vue 3 迁移可行性评估

> 扫描日期：2026-08-31  
> 项目目录：`E:\zhibodou-ai\zhibodou`  
> 结论类型：静态代码、配置、测试、打包目录及 Android Agent 扫描。VAD、CABLE、scrcpy、不同 Android 版本和各平台弹幕协议仍需要真机回归验证。

## 1. 最终结论

**可以使用 Vue 3 重做界面，而且值得做。** 当前 Tkinter 界面已经出现布局、样式、状态展示和业务耦合方面的瓶颈，Vue 3 + TypeScript 对登录页、配置页、实时日志、弹幕列表、VAD 音量仪表、运行状态、错误提示等界面能力没有障碍。

但必须区分两个概念：

1. **用 Vue 3 重做 UI：可行，风险可控，推荐。**
2. **把整个 Python 项目一次性全部改写成 JavaScript：风险很高，不推荐。**

Vue 只是渲染界面，不能单独替代桌面程序的音频采集、Windows CoreAudio、Win32 窗口嵌入、ADB/scrcpy 进程管理。Electron、Tauri 或 pywebview 之类的桌面容器才负责连接 Vue 和这些系统能力。

推荐目标是：

**Vue 3 + TypeScript 界面，Electron 主进程，保留 Python 核心 sidecar，Android Agent 继续使用 Java/Kotlin。**

这样可以先获得现代 UI，又不会破坏已经反复调试过的 VAD、CABLE、ADB 和 scrcpy 链路。后续只有经过回放测试的模块才逐个迁到 TypeScript。

综合评分：

| 方案 | 可行性 | 风险 | 建议 |
|---|---:|---:|---|
| Vue 3 只替换 Tkinter，Python 保留核心逻辑 | 9/10 | 中低 | **推荐** |
| Vue 3 + Electron + Python sidecar | 9/10 | 中 | **首选架构** |
| Vue 3 + Tauri + Python sidecar | 8/10 | 中高 | 团队具备 Rust 能力时可选 |
| Vue 3 + pywebview + Python | 7/10 | 中 | 最少改动的过渡方案 |
| 一次性将 Python、Windows 原生和协议解析全部改成 JS | 4/10 | 很高 | 不建议 |

## 2. 扫描范围与项目画像

本次扫描覆盖：

- `src/main.py` 启动、登录和生命周期；
- `src/gui` Tkinter 登录与主界面；
- `src/audio` VAD、PyAudio 和 TTS；
- `src/screen` scrcpy、Win32 嵌入、CABLE 音频链路、弹幕 UI、抓屏；
- `src/device` ADB、解锁、输入框定位和 Android Agent RPC；
- `src/broadcast` 开关机、话术循环和 VAD 放行逻辑；
- `src/danma` Playwright 弹幕采集与各平台私有协议解析；
- `android_agent` Android 无障碍服务；
- `tests`、`requirements.txt`、文档、打包产物及工具目录。

排除虚拟环境、编译缓存和大体积第三方二进制后，业务代码主体约为：

- Python 文件：69 个；
- Android Java 文件：2 个；
- Python 代码：约 7,100 行；
- 最大业务文件：`src/gui/login.py` 627 行、`src/audio/vad.py` 558 行、`src/danma/main.py` 382 行、`src/gui/ui.py` 380 行。

项目本质不是普通桌面 CRUD，而是一套由多个实时链路组成的 Windows/Android 自动化系统：

```text
用户配置与控制
      ↓
话术调度状态机 ──→ ADB/Android Agent ──→ 豆包输入与发送
      ↑                                      ↓
VAD 结束判定 ← CABLE Output ← CABLE Input ← scrcpy 手机音频

直播平台页面 ──→ Playwright 网络拦截 ──→ 私有协议解析 ──→ 弹幕/UI/统计
```

## 3. 核心技术点与迁移难度

### 3.1 VAD 与 Windows 音频采集——最高业务风险

当前核心在 `src/audio/vad.py`：

- 通过 PyAudio/PortAudio 枚举输入设备；
- 优先识别 Windows WASAPI 和指定的 `CABLE Output`；
- 按 PCM RMS 计算 dB；
- 启动前校准底噪并生成开口、结束阈值；
- 对音量采用“上次值 5/8、当前值 3/8”平滑；
- 使用 `WAITING → SPEAKING → ENDED` 三状态判断；
- 只有连续静音达到确认时长才允许切换下一条话术；
- 通过 generation/cancel 防止旧线程错误回调。

难点不在算法能否用 JS 编写，RMS、滤波和状态机都能用 TypeScript 实现；难点在于：

- 浏览器/WebView 的 Web Audio API 不等于 WASAPI/PortAudio，无法保证稳定地按 Windows 设备名获得 CABLE 数字回环；
- Electron 若直接采集任意系统设备，通常仍要依赖原生 Node 模块，带来 ABI、签名和打包风险；
- 不同声卡驱动、采样率、独占模式、设备重连都需要现场兼容；
- VAD 错一次就会直接造成话术重叠或直播停滞，容错要求高于普通音量显示。

**迁移建议：第一阶段完整保留 Python VAD。** Python 通过 IPC 发送 `rawDb`、`smoothedDb`、阈值、状态和故障码，Vue 只负责高频绘制音量条。这样能修复 Tkinter 音量显示体验，同时不改动判定链路。

### 3.2 scrcpy、手机音频与 CABLE 链路——系统集成高风险

当前链路是：

```text
Android 11+ 手机音频
  → scrcpy 音频转发
  → CABLE Input（Windows 播放端）
  → CABLE Output（Windows 录音端）
  → PyAudio/VAD
```

`src/screen/scrcpy_embed.py` 同时负责：

- 检测 Android API 版本；
- 拼装并尝试 scrcpy 启动参数；
- 指定 SDL 音频输出设备；
- 检查 VAD 输入和 scrcpy 输出是否形成虚拟声卡闭环；
- 启动、停止和重试外部进程；
- 查找 scrcpy 的 Windows 原生窗口并嵌入界面。

其中“启动 scrcpy”对 Node/Rust 都很简单，真正困难的是“把 scrcpy HWND 精确嵌入某个 Vue DOM 区域”。DOM 元素不是独立 HWND，无法直接作为 Win32 `SetParent` 的父句柄。

可选策略：

1. **第一版推荐：scrcpy 使用独立无边框窗口，由 Electron 跟随主窗口位置和尺寸。** 稳定性最高，视觉上可做成接近内嵌。
2. 使用 Electron 原生扩展/FFI 调用 `SetParent`。技术上可做，但 DPI、焦点、缩放、窗口销毁和安全软件兼容风险高。
3. 使用 Tauri/Rust 的 Win32 API 做嵌入。原生代码边界更清楚，但仍需解决 WebView 窗口层级与 DOM 区域坐标映射。
4. 长期重写为读取 scrcpy 视频流并在 `<video>`/Canvas 中渲染。体验最好，但工作量最大，也会触碰解码和低延迟链路。

Android API 29 本身不支持 scrcpy 的设备音频转发，这不是 Vue、Python或 UI 框架能够修复的限制。若仍要求全数字 CABLE 链路，必须使用 Android 11+；Android 10 只能另选实体采音或外部硬件方案。

### 3.3 Win32 原生窗口嵌入——高风险

`src/screen/win_embed.py` 直接使用 `ctypes.windll.user32`：

- 查找原生窗口句柄；
- 调用 `SetParent`；
- 修改 `GWL_STYLE`；
- 调用 `MoveWindow` 锁定尺寸。

这部分不能运行在 Vue 浏览器沙箱中。Electron 官方可以取得 BrowserWindow 的 Windows `HWND`，但把第三方窗口嵌到 WebView 内部仍需原生桥接；Tauri 则需要 Rust/Win32 插件。

因此，“投屏必须原生嵌入”是开始整体迁移前必须完成的技术验证项，不能等 UI 全部写完才验证。

### 3.4 Windows 默认音频设备切换——高风险且当前未接线

`src/screen/audio_route.py` 使用 `comtypes` 和 Windows CoreAudio COM，并直接调用未公开的 `IPolicyConfig` vtable 槽位切换默认播放设备。这类代码：

- 强依赖 Windows；
- 对系统版本、接口布局和权限敏感；
- 迁到纯前端 JavaScript 不现实；
- 迁到 Electron 需要原生扩展，迁到 Tauri 更适合用 Rust `windows` crate 重写。

扫描没有发现此模块被当前主流程调用，`requirements.txt` 也未声明 `comtypes`。它现在更像“写好但未接入”的能力，不能假设发布版会自动切换 CABLE。

**建议先明确产品是否需要自动切换系统默认设备。** 如果 scrcpy 已能按设备名定向输出，就尽量不要改变整台电脑的默认音频设备；这可以显著降低风险。

### 3.5 ADB 与 Android Agent——中等风险，可跨语言

当前发送链路不再依赖固定坐标，主要由 `src/device/input_text.py` 和 Android Agent 完成：

- ADB 端口转发到手机 `12051`；
- Android 无障碍服务查找豆包输入框；
- 设置文本并按控件语义点击发送；
- Agent 不可用时，通过 `uiautomator dump` 定位输入框/发送按钮并使用剪贴板降级。

ADB 子进程管理、XML 解析、HTTP 请求在 Node.js/Rust 中都能实现，JS 没有能力问题。但 Android 无障碍服务必须继续保留为 Android 原生应用，Vue 无法取代。

需要改进的协议问题：

- `accessibility_client.py` 与新 Agent 返回值曾存在 `success`/`code` 不一致，当前主链路已兼容，但旧客户端仍可能误判；
- `ui_locator.py`、`accessibility_client.py`、`input_text.py` 存在能力重叠，应收敛成一个设备服务；
- Agent 的轻量 HTTP 服务缺少认证和严格的来源限制；
- 长提示词不宜继续塞入 GET 查询参数，建议改成 POST JSON，并规定 UTF-8、最大长度、请求 ID 和幂等语义；
- 多设备时所有 ADB、forward、scrcpy 命令必须统一携带同一个 serial，避免发到错误手机。

### 3.6 弹幕采集与私有协议解析——中高风险，但很适合迁到 TS

`src/danma/main.py` 使用 Playwright 启动持久化浏览器、监听响应/WebSocket，并路由到多个平台解析器。目前包含抖音、TikTok、快手、Bilibili、拼多多、Nimo、Facebook、视频号、小红书、淘宝等适配代码。

这部分迁到 TypeScript 的技术可行性很高，因为 Playwright 原生支持 Node.js/TypeScript，protobuf、Brotli、WebSocket 和 JSON 也都有成熟生态。真正风险来自平台协议，而不是语言：

- 私有接口、签名、protobuf 字段和压缩方式可能随平台升级改变；
- headless 模式更容易触发登录、风控、验证码和反自动化差异；
- 持久化用户目录中包含 Cookie/登录态，必须隔离并保护；
- 当前解析器混合生成代码、第三方 Tars 代码和手写逻辑，缺少统一事件模型；
- 没有保存足够的原始帧样本，改写后难以确认兼容性。

推荐先定义统一事件：

```ts
type DanmuEvent =
  | { type: 'comment'; platform: string; user: string; content: string; ts: number }
  | { type: 'gift'; platform: string; user: string; gift: string; count: number; ts: number }
  | { type: 'like'; platform: string; count: number; ts: number }
  | { type: 'online'; platform: string; count: number; ts: number }
  | { type: 'status'; platform: string; state: string; detail?: string };
```

然后为每个平台保存脱敏后的响应/二进制帧，建立回放测试，再逐个平台迁移。未通过回放测试的平台继续运行 Python 解析器。

headless 可以保留为 UI 开关，但不能承诺所有平台都永远无需显示浏览器。建议产品状态明确区分“无头运行”“需要扫码/验证”“已登录运行”“风控阻断”。

### 3.7 话术调度与 VAD 放行——高业务风险

`src/broadcast/live.py` 负责：

- 根据在线人数选择区间话术；
- 给豆包追加主播角色限定提示词；
- 发送前准备音频设备并校准；
- 发送后等待 VAD 真正进入说话并确认连续静音；
- 只有 `VAD_ENDED` 才切到下一条；
- 暂停、停止和异常时中止当前循环。

这段逻辑代码不算长，但它是整个产品的业务中枢。迁移时不要把它散落到 Vue 组件、按钮回调和多个 watcher 中。应抽象成后端有限状态机，例如：

```text
IDLE → PREPARING_AUDIO → SENDING → WAITING_SPEECH
     → SPEAKING → CONFIRMING_SILENCE → READY_NEXT
     ↘ PAUSED / ERROR / STOPPED
```

Vue 只能发命令和显示状态，不能成为真相来源。关闭窗口、页面刷新或组件重建都不能让后台误切下一句。

### 3.8 Tkinter UI 与线程模型——迁移收益最高

当前 `src/gui/ui.py`、`src/gui/login.py` 使用模块级控件变量，大量业务模块直接 import `gui.ui` 后更新控件。后台线程通过 `root.after` 回到 UI 线程。

这造成：

- UI、配置、设备、直播状态互相引用；
- 单元测试需要模拟 Tk 控件；
- 状态变化没有统一事件定义；
- 某个线程异常时 UI 可能保持旧状态；
- 自定义 Canvas 登录页代码量大，但现代交互仍难实现；
- VAD 音量条、虚拟列表、过滤搜索、通知中心、响应式布局等实现成本高。

Vue 3 对这些问题非常适合。建议使用：

- Vue 3 Composition API；
- TypeScript；
- Pinia 管理“后端状态快照”，但后端仍为权威状态；
- Vite；
- 虚拟列表显示高频弹幕和日志；
- Canvas/SVG 显示 VAD 原始值、平滑值、开口阈值和结束阈值；
- 统一 toast、错误码和可复制诊断信息。

### 3.9 打包、发布和升级——高工程风险

现在项目同时包含 Python、Playwright 浏览器、scrcpy/adb、APK、配置、证书/授权数据和 Windows 音频依赖。换成 Vue 后不是简单生成几个静态文件，还必须设计：

- Electron/Tauri 主程序；
- Python sidecar 或独立核心服务；
- scrcpy/adb 二进制及依赖 DLL；
- Android Agent APK；
- Playwright 浏览器及平台登录目录；
- CABLE 驱动检测，但不能未经用户允许自动安装/切换；
- 代码签名、自动升级、杀毒软件误报和日志目录；
- 崩溃后回收 scrcpy、adb forward、Playwright 和 Python 子进程。

Electron 包更大，但 Node、Playwright 和进程管理对现有团队更直接。Tauri 壳更小，但本项目并不会因为用了 Tauri 就消除 Python、scrcpy 和 Playwright 体积，而且 Win32/音频能力会引入 Rust 开发成本。

## 4. 扫描发现的现存问题

下面的问题不应原样迁移到新 UI。

### P0：迁移前必须处理

1. **全局状态会吞掉字段错误**  
   `src/core/state.py::__getattr__` 对任何不存在字段都返回 `False`。拼写错误、漏初始化和跨模块状态不一致不会报错，只会变成错误分支。应删除这一兜底，改成显式 dataclass/枚举和线程安全状态服务。

2. **TTS 音频模式状态已经失联**  
   `src/broadcast/live.py` 使用模块局部 `inner_audio_mode`，`src/audio/tts.py` 却读取不存在的 `state.inner_audio_mode`。因为上一条兜底，它不会报错且始终得到 `False`。这说明吞异常/吞字段确实已经掩盖真实缺陷。

3. **认证当前等于未启用**  
   `check_machine_auth()` 恒返回 `True`，`auth_passed` 默认也是 `True`；默认管理员密码硬编码，密码用无盐 MD5。正式发布前必须重新设计，不能只是把登录页迁到 Vue。

4. **异常大量静默丢失**  
   `src` 下约有 131 个异常捕获块，其中约 88 个属于静默 `pass` 模式。音频、设备、UI 回调或平台解析失败时，很可能只表现为“没声音、没弹幕、按钮没反应”。应建立结构化日志和错误码。

5. **直播状态分散且不是线程安全状态机**  
   多个布尔量和线程句柄散布在 `core.state`、`broadcast.live`、VAD 实例和 UI 控件中。快速开始/停止/重启时存在旧线程覆盖新状态的风险。VAD 已局部使用 generation，但整个应用尚未统一。

### P1：高优先级改进

1. **配置层直接读取 Tk 控件**  
   `src/settings/config.py` 导入 tkinter，并在保存时直接读取控件，导致配置无法脱离旧 UI 测试和复用。应先改为纯数据 DTO + 校验函数。

2. **弹幕层直接写 Tk 控件**  
   `src/screen/danmu.py` 同时负责采集线程、队列、统计和 UI 更新。应拆为 collector、normalizer、event bus、UI consumer。

3. **音频路由模块未接入且依赖未声明**  
   `src/screen/audio_route.py` 没有主流程调用，`requirements.txt` 也没有 `comtypes`。需决定删除、接线或改为明确的可选能力。

4. **抓屏功能没有保存或分析图像**  
   `src/screen/capture.py` 每秒调用 `pyautogui.screenshot()`，随即丢弃结果，只记录“抓取完成”。这会持续消耗 CPU/内存带宽但没有业务产出。并且代码使用 `tk.messagebox` 却没有显式导入 `tkinter.messagebox`，存在运行时失败风险。

5. **设备发送存在重复实现**  
   `accessibility_client.py`、`ui_locator.py`、`input_text.py` 与历史 ADB 降级路径部分重叠，返回协议也不完全一致。应收敛成一个 `DeviceService`。

6. **Android Agent RPC 安全与健壮性不足**  
   自建 ServerSocket、简单 HTTP 行解析、固定端口、无认证。即使主要通过 ADB forward 使用，也应限制监听地址、加入会话 token、完整读取请求体并使用 POST JSON。

7. **文档与真实实现存在偏差**  
   部分文档仍描述旧 ADBKeyboard/旧发送路径，README 仍接近模板。迁移前需要以代码和协议测试为准，而不是照旧文档重写。

8. **生成代码、历史备份与运行数据混在源码树**  
   旧备份、构建产物、发布 APK、浏览器 profile、license 数据会影响打包、泄漏登录态或让开发者误改错误文件。应明确 source/build/runtime-data 边界并补齐 `.gitignore`。

### P2：持续工程化

- 为 VAD 增加录音样本回放测试，覆盖豆包短停顿、长停顿、弱音、音乐、断流和设备重连；
- 为每个平台弹幕保存脱敏协议样本并做解析回归；
- 为直播状态机做确定性单元测试；
- 增加 lint、类型检查、格式化、依赖锁文件和 CI；
- 日志增加 session ID、device serial、平台、状态迁移、原始/平滑 dB、阈值和错误栈；
- 密钥、授权文件、Cookie/profile 和用户配置移出源码目录；
- 统一所有子进程的启动、健康检查、超时、停止和孤儿进程回收。

## 5. 推荐架构

```text
┌────────────────────────────────────────────┐
│ Vue 3 + TypeScript Renderer                │
│ 登录 / 配置 / VAD仪表 / 弹幕 / 日志 / 状态 │
└───────────────────┬────────────────────────┘
                    │ 安全、类型化 IPC
┌───────────────────▼────────────────────────┐
│ Electron Main（推荐）                      │
│ 窗口 / 托盘 / 权限 / 更新 / 子进程生命周期  │
│ Renderer 只通过 preload 暴露的白名单 API    │
└─────────────┬─────────────────┬────────────┘
              │ JSON-RPC/stdio  │ Node Worker
┌─────────────▼────────────┐  ┌─▼──────────────────┐
│ Python Core Sidecar      │  │ TS Danmu Collector │
│ VAD / PyAudio / CABLE    │  │ Playwright / Parser│
│ 直播状态机 / ADB / scrcpy│  │ 可按平台渐进迁移    │
└──────────┬───────────────┘  └────────────────────┘
           │ ADB forward / subprocess
┌──────────▼─────────────────────────────────┐
│ Android Agent                              │
│ AccessibilityService / 豆包输入与语义点击  │
└────────────────────────────────────────────┘
```

关键约束：

- Vue Renderer 不直接调用 Node、PowerShell、ADB 或文件系统；
- Electron 保持 `contextIsolation` 和 sandbox，通过 preload 暴露最小白名单；
- Python 后端是直播、VAD、设备状态的唯一权威来源；
- IPC 消息带 `requestId`、`sessionId`、版本、时间戳和明确错误码；
- VAD 电平事件可以 20–30 Hz 推送，普通日志和统计应节流/批量发送；
- 进程退出顺序由 Electron 主进程统一托管；
- 调试模式与正式模式的 profile、日志和密钥目录完全分开。

## 6. Electron、Tauri、pywebview 如何选择

| 项目维度 | Electron | Tauri 2 | pywebview |
|---|---|---|---|
| Vue 3 支持 | 很成熟 | 很成熟 | 可加载构建产物 |
| 与 Node/Playwright 协作 | 最自然 | 需 Node sidecar 或保留 Python | 继续用 Python Playwright |
| Python sidecar | `child_process` 管理 | 官方支持 external binary sidecar | Python 本身就是宿主 |
| Win32/音频原生能力 | 原生扩展/FFI | Rust 插件最正规 | 可直接复用 Python ctypes/comtypes |
| scrcpy 真内嵌 | 仍需原生桥接 | 仍需 Rust/Win32 验证 | 可继续用 HWND，但 DOM 区域映射仍麻烦 |
| 安装包/内存 | 最大 | 壳较小 | 通常较小 |
| 当前团队迁移成本 | 最低 | 较高 | 最低，但长期架构一般 |
| 推荐定位 | **正式迁移首选** | 有 Rust 能力且重视体积时 | 快速过渡/验证 UI |

选择 Electron 的主要理由不是它“什么都能用 JS 做”，而是它能用成熟 IPC 和进程模型把 Vue、Node 弹幕模块与 Python sidecar 组织起来，团队不需要同时承担完整 Rust 重写。

如果产品硬性要求“scrcpy 必须像现在一样真正嵌入主窗口”，应并行做一个 Electron 与一个 Tauri 小型验证，验证完成后再最终定壳。除此以外，Electron 是当前更稳妥的默认选择。

## 7. 推荐迁移顺序

### 阶段 0：先固化行为，不改 UI

- 定义直播、VAD、设备、弹幕统一事件和错误码；
- 给当前 VAD 保存典型音频并建立回放测试；
- 给各弹幕平台保存脱敏帧并建立 parser 测试；
- 删除 `state.__getattr__` 式吞错，收敛状态机；
- 配置层与 Tk 控件解耦；
- 收敛 ADB/Agent 发送服务。

**完成标准：** 同一批样本每次得到相同 VAD 和解析结果，快速启停不会出现旧线程回写。

### 阶段 1：完成最小技术验证

只做一页 Vue 原型，验证六件事：

1. Electron 启动/停止 Python sidecar；
2. Vue 20–30 Hz 显示 VAD 原始值、平滑值和阈值；
3. Python 状态机完成一轮真实豆包发送与 VAD 放行；
4. Electron 启动 scrcpy，并采用独立跟随窗口；
5. CABLE Input/Output 在打包版中仍可稳定使用；
6. Playwright headless 与登录态在开发版和安装版中均可工作。

**这是迁移的真正 Go/No-Go 门槛。**

### 阶段 2：Vue 替换全部 Tkinter 页面

- 登录/授权；
- 产品和话术配置；
- 设备、scrcpy、音频路由状态；
- VAD 仪表；
- 弹幕、实时人数、礼物、点赞；
- 直播控制和诊断日志。

此阶段不改 VAD 算法、不改 Agent、不重写平台协议，只替换表现层和 IPC。

### 阶段 3：按收益迁移弹幕到 TypeScript

- 先迁 JSON/普通 WebSocket 平台；
- 再迁 protobuf/Brotli；
- 最后迁 Tars、签名复杂或风控严重的平台；
- 每迁一个平台都必须跑历史帧回放和真实直播间验证；
- Python 和 TS 解析器可在一段时间内双跑对比输出。

### 阶段 4：可选的原生能力重写

只有在 Python sidecar 已成为明确维护负担时，再考虑：

- 用 Rust/Windows API 替代 CoreAudio 和 HWND 操作；
- 用 Rust/PortAudio 替代 Python VAD 采集；
- 直接消费 scrcpy 视频流；
- 将 ADB 服务迁到 Node/Rust。

这些不是使用 Vue 3 的前置条件。

## 8. 不建议的做法

- 不要边写 Vue 页面边把 VAD 算法改成 Web Audio；
- 不要让 Vue 组件自己维护“是否正在直播/能否切下一句”的最终状态；
- 不要使用固定延时替代 VAD；
- 不要为了“纯 JS”而立即替换已验证的 PyAudio/CABLE 链路；
- 不要把 scrcpy 内嵌当成普通 DOM 功能；
- 不要一次迁移所有弹幕解析器而没有协议样本回放；
- 不要在 Electron Renderer 中开启完整 Node 权限；
- 不要继续把 Cookie、profile、授权文件和构建产物混在源码目录；
- 不要在 Android 10 上承诺 scrcpy 数字音频转发。

## 9. 最终建议

项目使用 Vue 3 不会因为 JavaScript 能力不足而失败。最可能导致失败的是“一次性全量重写”和“低估 Windows 原生集成”。

推荐决策是：

1. 正式确定 **Vue 3 + TypeScript + Electron + Python sidecar + Android Agent**；
2. 第一版 scrcpy 使用受主窗口管理的独立无边框窗口；
3. VAD、CABLE、话术状态机和 Agent 先保持现状并通过类型化 IPC 暴露；
4. 弹幕采集按平台逐步迁到 TypeScript；
5. 完成最小技术验证后再投入完整 UI，而不是先重画全部页面；
6. 迁移前先修复本报告 P0 问题，否则新界面会继续掩盖旧故障。

采用这条路线，现代 UI 和现有核心能力可以同时保住，不需要在“Tkinter 界面弱”和“全部重写风险大”之间二选一。

## 10. 官方能力参考

- Electron `BrowserWindow.getNativeWindowHandle()` 可取得 Windows HWND，但官方 API 并不直接提供把外部 HWND 嵌入某个 DOM 节点的能力：<https://www.electronjs.org/docs/latest/api/browser-window#wingetnativewindowhandle>
- Electron `utilityProcess` 提供独立 Node 子进程和消息端口；启动 Python 可使用 Node `child_process`：<https://www.electronjs.org/docs/latest/api/utility-process>
- Electron Renderer 默认沙箱及 `nodeIntegration` 安全边界：<https://www.electronjs.org/docs/latest/tutorial/sandbox>
- Tauri 2 官方支持将 Python/PyInstaller 程序作为 external binary sidecar 打包：<https://v2.tauri.app/develop/sidecar/>
- Playwright 官方支持 JavaScript/TypeScript、Python、Java 和 .NET，Node/TS 迁移不存在框架能力障碍：<https://playwright.dev/docs/languages>

