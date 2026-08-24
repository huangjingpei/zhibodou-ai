package com.zhibodou.agent;

import android.accessibilityservice.AccessibilityService;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 【智播豆常驻无障碍 Agent 商用强化版】
 */
public class DoubaoAccessibilityService extends AccessibilityService {

    private static final String TAG = "ZhibodouAgent";
    private static final int RPC_PORT = 12051;
    private static final String CHANNEL_ID = "zhibodou_agent_channel";
    private static final int NOTIFICATION_ID = 1001;

    private static DoubaoAccessibilityService sInstance = null;
    private ServerSocket mServerSocket;
    private boolean mIsRunning = false;
    private int mScreenHeight = 2400;
    private int mScreenWidth = 1080;

    private final ExecutorService mThreadPool = Executors.newFixedThreadPool(4);

    public static boolean isAlive() {
        return sInstance != null;
    }

    @Override
    public void onServiceConnected() {
        super.onServiceConnected();
        sInstance = this;
        Log.i(TAG, "onServiceConnected: 服务已绑定并激活");

        DisplayMetrics dm = getResources().getDisplayMetrics();
        mScreenWidth = dm.widthPixels;
        mScreenHeight = dm.heightPixels;

        showForegroundNotification();
        startRpcServer();
    }

    private void showForegroundNotification() {
        NotificationManager notificationManager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.notification_channel_name),
                    NotificationManager.IMPORTANCE_LOW
            );
            notificationManager.createNotificationChannel(channel);
        }

        Notification.Builder builder = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) 
                ? new Notification.Builder(this, CHANNEL_ID) 
                : new Notification.Builder(this);
        
        Notification notification = builder
                .setContentTitle(getString(R.string.notification_title))
                .setContentText(getString(R.string.notification_content))
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setOngoing(true)
                .build();

        startForeground(NOTIFICATION_ID, notification);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {}

    @Override
    public void onInterrupt() {
        Log.w(TAG, "onInterrupt: 服务中断");
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        sInstance = null;
        mIsRunning = false;
        mThreadPool.shutdownNow();
        try {
            if (mServerSocket != null) mServerSocket.close();
        } catch (Exception ignored) {}
    }

    private void startRpcServer() {
        if (mIsRunning) return;
        mIsRunning = true;
        new Thread(() -> {
            try {
                mServerSocket = new ServerSocket(RPC_PORT);
                Log.i(TAG, "RPC Server 已在端口 " + RPC_PORT + " 就绪");
                while (mIsRunning) {
                    final Socket socket = mServerSocket.accept();
                    mThreadPool.execute(() -> handleClientSocket(socket));
                }
            } catch (Exception e) {
                if (mIsRunning) Log.e(TAG, "Server 异常: " + e.getMessage());
            }
        }).start();
    }

    private void handleClientSocket(Socket socket) {
        try (Socket s = socket;
             BufferedReader reader = new BufferedReader(new InputStreamReader(s.getInputStream(), StandardCharsets.UTF_8));
             OutputStream out = s.getOutputStream()) {

            String line = reader.readLine();
            if (line == null) return;

            Log.d(TAG, ">>> 收到原始数据: " + line);

            String action = "";
            String injectText = "";

            // 1. 自动兼容处理 HTTP 协议 (针对浏览器或 curl 测试)
            if (line.startsWith("GET ") || line.startsWith("POST ")) {
                if (line.contains("/ping")) {
                    action = "ping";
                } else if (line.contains("/inject_and_send") || line.contains("/set_text")) {
                    action = "inject_and_send";
                    // 尝试从 URL 提取 text 参数
                    if (line.contains("text=")) {
                        String part = line.substring(line.indexOf("text=") + 5);
                        injectText = part.split("[ &]")[0];
                        injectText = URLDecoder.decode(injectText, "UTF-8");
                    }
                } else if (line.contains("/clear")) {
                    action = "clear";
                }
                // 消耗掉剩下的 HTTP Header
                while (true) {
                    String h = reader.readLine();
                    if (h == null || h.isEmpty()) break;
                }
            } else {
                // 2. 原生 JSON 解析
                try {
                    JSONObject req = new JSONObject(line);
                    action = req.optString("action");
                    injectText = req.optString("text");
                } catch (Exception e) {
                    Log.e(TAG, "JSON 解析失败: " + e.getMessage());
                }
            }

            // 3. 执行指令
            JSONObject resp = new JSONObject();
            resp.put("code", 0);
            
            if ("ping".equals(action)) {
                resp.put("msg", "pong");
            } else if ("inject_and_send".equals(action)) {
                Log.i(TAG, "正在执行注入发送: " + injectText);
                boolean ok = performInjectAndSend(injectText);
                resp.put("code", ok ? 0 : -1);
                resp.put("msg", ok ? "success" : "failed (check if Doubao is in foreground)");
            } else if ("clear".equals(action)) {
                Log.i(TAG, "正在执行清空输入框");
                boolean ok = performClear();
                resp.put("code", ok ? 0 : -1);
                resp.put("msg", ok ? "success" : "failed");
            } else {
                Log.w(TAG, "未知 Action: " + action + " (原始行: " + line + ")");
                resp.put("code", 404);
                resp.put("msg", "unknown action: " + action);
            }

            // 4. 返回响应 (如果是 HTTP 则加上 Header)
            String body = resp.toString() + "\n";
            if (line.startsWith("GET") || line.startsWith("POST")) {
                String httpHeader = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n";
                out.write(httpHeader.getBytes(StandardCharsets.UTF_8));
            }
            out.write(body.getBytes(StandardCharsets.UTF_8));
            out.flush();
            Log.d(TAG, "<<< 响应已发送: " + body.trim());

        } catch (Exception e) {
            Log.e(TAG, "通信处理异常: " + e.getMessage());
        }
    }

    private synchronized boolean performInjectAndSend(String text) {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) {
            Log.e(TAG, "错误：无法获取活动窗口，请确保豆包 App 处于前台！");
            return false;
        }

        try {
            // 检测是否在豆包 App 中
            CharSequence pkg = root.getPackageName();
            Log.d(TAG, "当前前台包名: " + pkg);

            AccessibilityNodeInfo input = findInputNode(root);
            if (input == null) {
                Log.w(TAG, "未能在当前屏幕找到输入框 (EditText)");
                return false;
            }

            Bundle args = new Bundle();
            args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
            boolean setOk = input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
            Log.i(TAG, "文本注入状态: " + setOk);
            input.recycle();

            if (setOk) {
                try { Thread.sleep(300); } catch (Exception ignored) {} // 等待 UI 刷新
                AccessibilityNodeInfo newRoot = getRootInActiveWindow();
                if (newRoot != null) {
                    AccessibilityNodeInfo send = findSendButton(newRoot);
                    if (send != null) {
                        boolean clickOk = send.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                        Log.i(TAG, "发送按钮点击状态: " + clickOk);
                        send.recycle();
                        newRoot.recycle();
                        return clickOk;
                    }
                    newRoot.recycle();
                }
            }
            return setOk;
        } finally {
            root.recycle();
        }
    }

    private synchronized boolean performClear() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return false;
        try {
            AccessibilityNodeInfo input = findInputNode(root);
            if (input == null) return false;
            Bundle args = new Bundle();
            args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, "");
            boolean ok = input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
            input.recycle();
            return ok;
        } finally {
            root.recycle();
        }
    }

    private AccessibilityNodeInfo findInputNode(AccessibilityNodeInfo root) {
        List<AccessibilityNodeInfo> nodes = new ArrayList<>();
        collectNodesByClass(root, "android.widget.EditText", nodes);
        if (nodes.isEmpty()) return null;
        
        AccessibilityNodeInfo best = null;
        int maxY = -1;
        Rect rect = new Rect();
        for (AccessibilityNodeInfo n : nodes) {
            n.getBoundsInScreen(rect);
            if (rect.top > maxY) {
                if (best != null) best.recycle();
                maxY = rect.top;
                best = n;
            } else {
                n.recycle();
            }
        }
        return best;
    }

    private AccessibilityNodeInfo findSendButton(AccessibilityNodeInfo root) {
        List<AccessibilityNodeInfo> clickables = new ArrayList<>();
        collectClickableNodes(root, clickables);
        
        Rect rect = new Rect();
        AccessibilityNodeInfo fallback = null;
        int maxScore = -1;

        for (AccessibilityNodeInfo n : clickables) {
            String desc = String.valueOf(n.getContentDescription());
            String text = String.valueOf(n.getText());
            
            if (desc.contains("发送") || text.contains("发送")) {
                for (AccessibilityNodeInfo other : clickables) { if (other != n) other.recycle(); }
                return n;
            }
            
            n.getBoundsInScreen(rect);
            if (rect.left > mScreenWidth * 0.6 && rect.top > mScreenHeight * 0.6) {
                int score = rect.left + rect.top;
                if (score > maxScore) {
                    if (fallback != null) fallback.recycle();
                    maxScore = score;
                    fallback = n;
                    continue;
                }
            }
            n.recycle();
        }
        return fallback;
    }

    private void collectNodesByClass(AccessibilityNodeInfo node, String clazz, List<AccessibilityNodeInfo> out) {
        if (node == null) return;
        if (clazz.equals(node.getClassName())) out.add(AccessibilityNodeInfo.obtain(node));
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            collectNodesByClass(child, clazz, out);
            if (child != null) child.recycle();
        }
    }

    private void collectClickableNodes(AccessibilityNodeInfo node, List<AccessibilityNodeInfo> out) {
        if (node == null) return;
        if (node.isClickable()) out.add(AccessibilityNodeInfo.obtain(node));
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            collectClickableNodes(child, out);
            if (child != null) child.recycle();
        }
    }
}
