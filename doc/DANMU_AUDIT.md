# 弹幕采集代码审查与客户端集成说明

审查日期：2026-08-25

审查范围：`src/danma/` 各平台采集与协议解析、原 `src/danma/server.py` HTTP 服务、`src/screen/danmu.py` 客户端弹幕模块、直播启停生命周期、配置与依赖。

## 结论

新增采集代码能够通过 Playwright 监听网页的 HTTP/WebSocket 数据，并把各平台消息统一为 `ChatMessage`、`GiftMessage`、`LikeMessage`、`RoomMessage` 等结构，但原始代码不能直接作为当前客户端模块使用：它是独立脚本，依赖固定工作目录，通过本机 HTTP POST 推送，无法停止，且当前客户端仍在等待另一套 WebSocket 服务。

现已改为以下进程内链路：

`Playwright 网页监听 → 平台协议解析 → message_callback → 有界 Queue → Tk 主线程每 100ms 批量更新 UI/状态`

不再启动 Flask，不再请求 `127.0.0.1:7979`，也不再连接旧的 `ws://127.0.0.1:8899`。

## 已发现并修复的问题

1. **采集器与客户端没有入口连接**：`src/danma/main.py` 只能独立运行，客户端导入的 `screen.danmu` 是另一套 WebSocket 客户端，而且没有真正启动。
2. **不必要的 HTTP 中转**：每批数据创建新线程，再 POST 到 Flask；HTTP 服务只打印消息，没有把它交给 GUI。高峰期会产生大量短线程、连接和序列化开销。
3. **无法正常停止**：`browser_close()` 是空函数，主循环为永久循环；停止直播和关闭客户端后浏览器仍可能存活。
4. **集成后配置路径错误**：使用 `sys.argv[0]` 推导 `setting.ini`，从 `src/main.py` 启动时会寻找不存在的 `src/setting/setting.ini`。
5. **Tk 线程安全问题**：浏览器事件发生在后台线程，不能直接更新 Tk 控件。现改为队列隔离，由 Tk 主线程消费。
6. **队列与 UI 内存无上限**：高弹幕量或 UI 消费变慢时可能无限占用内存。现使用 2000 条有界队列，并把 UI 历史限制为最近 1000 行。
7. **TikTok WebSocket 重复注册**：同一个 `framereceived` 回调会绑定两次，造成弹幕重复。
8. **淘宝响应重复解析**：相同 URL 条件执行两次，造成重复弹幕和重复人数更新。
9. **Nimo 批量消息重复推送**：循环消息列表时每次都推送完整列表，N 条消息会产生 N 份重复结果。
10. **Bilibili 弹幕类型错误**：`DANMU_MSG` 被转换为 `MemberMessage`，正文虽然解析出来却被丢弃。现改为 `ChatMessage`。
11. **PDD 运行时参数错误**：一次 `CreatSocialMessage()` 缺少 `head_image`，命中该事件就会抛 `TypeError`。
12. **异常退出不重连**：原浏览器循环一旦抛错就永久退出。客户端桥接层现加入 2～30 秒指数退避重连。
13. **依赖声明过旧/过重**：Playwright 固定在约 1.29，且加入未使用的 Google Cloud、Requests、ConfigObj。现改为 `playwright>=1.49,<2`、`protobuf>=4.25,<8`、`brotli>=1.1`。
14. **自动发现 Chrome 不稳定**：旧代码读取不到 Chrome 版本、又没装 pywin32 时会把已安装的 Chrome 判成不存在。现支持配置路径、PATH、用户/系统注册表和常见安装目录。
15. **自定义 Chrome executable 风险**：自动发现的 Chrome 现优先使用 Playwright 官方支持的 `channel="chrome"`；只有用户明确填写路径时才使用 `executable_path`。

## 客户端生命周期

- 点击“正式开播”：启动弹幕采集线程；弹幕失败只记录错误，不阻断 VAD/话术直播。
- 点击“停止直播”：发送停止信号，由 Playwright 所属线程关闭 Context/Chrome。
- 关闭总电源或关闭客户端：同样停止采集器。
- 消息结果直接更新 `core.state` 的 `online_num`、`like_cnt`、`gift_cnt`、`comment_cnt`、`last_danmu_text` 和 GUI。

## Headless 调研结论

可以不显示浏览器窗口。Playwright 的 `headless=True` 会在后台运行浏览器，HTTP 响应和 WebSocket 帧监听仍然可用；持久化 Context 也支持 `user_data_dir`，可以保存 Cookie 和 localStorage。

本机已用已安装的 Google Chrome 执行两层 headless 冒烟测试：原生 Playwright 后台成功打开页面并读取标题 `headless-ok`；项目的 `DanmuBrowserCollector` 也成功创建持久化 Context、发出“采集页面已启动”消息、响应停止信号并在 15 秒保护时间内退出线程。这证明当前电脑和 Chrome 版本支持无窗口采集及正常释放。

但“无窗口”不等于“不运行浏览器进程”。仍然会存在 Chrome/Chromium 后台进程，并消耗内存和网络。对于抖音公开直播间通常可以直接 headless；视频号、淘宝、小红书、PDD 等创作者后台通常需要登录，建议第一次设置 `danmu_headless=false` 完成扫码登录，退出后再改回 `true`，复用同一个用户数据目录。

平台可能检测自动化或在 headless 下改变播放/鉴权逻辑，所以不能保证所有平台永久有效。采集器当前增加了自动播放参数、抖音“继续播放”处理和自动重连，但平台协议或页面变化后仍需更新解析器。

官方依据：

- Playwright Python 默认支持 headless，设置 `headless=False` 才显示窗口：<https://playwright.dev/python/docs/library>
- Persistent Context 会在 `user_data_dir` 保存 Cookie/localStorage，且同一目录不能同时启动多个实例：<https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context>
- 官方建议优先使用 Playwright 浏览器或 branded browser channel，并提示任意 `executable_path` 不保证兼容：<https://playwright.dev/python/docs/api/class-browsertype>
- 登录态文件包含可冒用账号的敏感信息，不应提交代码库：<https://playwright.dev/python/docs/auth>

## 配置

配置已合并到客户端 `settings/config.py`：

```json
{
  "danmu_enabled": true,
  "danmu_platform": "douyin",
  "danmu_url": "",
  "danmu_headless": true,
  "danmu_user_data_dir": "",
  "danmu_chrome_path": ""
}
```

`danmu_url` 留空时按 `danmu_platform` 从 `danmu_urls` 选择默认地址。`danmu_user_data_dir` 留空时使用 `%LOCALAPPDATA%/Zhibodou/DanmuBrowserProfile`。

## 仍需实际直播验证的风险

1. 各平台使用非公开、经常变化的网页协议和 Protobuf 字段，单元测试只能验证客户端桥接，不能代替真实直播间验收。
2. 平台登录过期、验证码、风控或扫码确认必须人工处理；headless 无法完成首次扫码。
3. 页面成功打开但没有产生目标 WebSocket/HTTP 请求时，目前只能从“长时间无弹幕”侧判断，尚无各平台统一的“已进入直播间并订阅成功”确认协议。
4. 现有解析器对缺失 JSON/Protobuf 字段普遍使用直接索引，平台字段变化时单条消息可能解析失败；后续应按实际使用平台逐个增加样本回放测试。
5. 平台条款可能限制自动化访问和数据采集，部署前应确认账号权限、平台规则及合规要求。
