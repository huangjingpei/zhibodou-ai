# 智播豆无障碍 Agent 商用级优化方案

本方案旨在将现有的实验性无障碍服务提升为工业级可靠的后台常驻 Agent，重点解决稳定性、资源管理和长效运行问题。

## 用户审核要求
- **前台通知**：为了保证服务常驻，应用将显示一个持续的通知。这是 Android 系统对长效后台服务的强制要求。
- **资源占用**：优化后依然保持极低内存占用（< 10MB），但由于引入了线程池，并发处理能力将大幅提升。

## 拟议更改

### 1. 核心无障碍服务 [DoubaoAccessibilityService.java](file:///E:/zhibodou-ai/zhibodou/android_agent/app/src/main/java/com/zhibodou/agent/DoubaoAccessibilityService.java)

#### [MODIFY] 内存与线程管理
- **线程池化**：引入 `Executors.newFixedThreadPool(4)` 管理 RPC 客户端连接，避免线程爆炸。
- **节点回收**：在所有递归遍历函数中添加 `recycle()` 调用，消除潜在的内存泄漏和系统卡顿。
- **Socket 安全**：在 `try-with-resources` 中正确关闭 Socket 资源。

#### [NEW] 前台常驻机制
- **Notification Channel**：在 `onServiceConnected` 中创建通知渠道。
- **startForeground**：启动服务时立即显示通知，提升系统保活等级。

#### [MODIFY] 语义搜索增强
- **健壮性优化**：增加对节点有效性的多重校验。

---

### 2. 项目配置与资源

#### [MODIFY] [AndroidManifest.xml](file:///E:/zhibodou-ai/zhibodou/android_agent/app/src/main/AndroidManifest.xml)
- 添加 `FOREGROUND_SERVICE_TYPE_SPECIAL_USE` (适配 Android 14+) 或基础前台服务权限。

#### [MODIFY] [strings.xml](file:///E:/zhibodou-ai/zhibodou/android_agent/app/src/main/res/values/strings.xml)
- 添加通知相关的文本描述。

## 验证计划

### 自动化测试
- 模拟高频 RPC 请求（ping/get_ui_state），检查线程池负载。
- 使用内存分析工具（Memory Profiler）观察 `AccessibilityNodeInfo` 对象计数，确保无泄漏。

### 手动验证
- **保活测试**：将 App 切入后台并清理任务管理器，确认无障碍服务图标在状态栏依然存在。
- **功能测试**：在豆包（com.larus.nova）界面触发指令，验证输入与发送逻辑是否依然准确。
