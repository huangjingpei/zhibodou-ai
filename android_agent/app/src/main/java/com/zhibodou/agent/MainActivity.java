package com.zhibodou.agent;

import android.app.Activity;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.List;

/**
 * 极简状态看板与一键授权引导页
 */
public class MainActivity extends Activity {

    private TextView tvStatus;
    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private final Runnable mRefreshTask = new Runnable() {
        @Override
        public void run() {
            refreshStatus();
            mHandler.postDelayed(this, 1000); // 每秒自动刷新一次，增强感知
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(60, 80, 60, 80);

        TextView tvTitle = new TextView(this);
        tvTitle.setText("智播豆 Agent 2.0 (商用强化版)");
        tvTitle.setTextSize(22);
        tvTitle.setPadding(0, 0, 0, 40);
        layout.addView(tvTitle);

        tvStatus = new TextView(this);
        tvStatus.setTextSize(16);
        tvStatus.setPadding(0, 0, 0, 40);
        layout.addView(tvStatus);

        Button btnOpenSetting = new Button(this);
        btnOpenSetting.setText("👉 点击开启无障碍服务 (Accessibility)");
        btnOpenSetting.setOnClickListener(v -> {
            Intent intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            startActivity(intent);
        });
        layout.addView(btnOpenSetting);

        setContentView(layout);
    }

    @Override
    protected void onResume() {
        super.onResume();
        mHandler.post(mRefreshTask);
    }

    @Override
    protected void onPause() {
        super.onPause();
        mHandler.removeCallbacks(mRefreshTask);
    }

    private void refreshStatus() {
        if (isAccessibilityServiceEnabled()) {
            tvStatus.setText("✅ 状态：无障碍服务已激活 (后台常驻监听中)");
            tvStatus.setTextColor(0xFF008800);
        } else {
            tvStatus.setText("❌ 状态：无障碍服务未开启，请点击下方按钮开启授权");
            tvStatus.setTextColor(0xFFCC0000);
        }
    }

    /**
     * 工业级可靠检测逻辑
     */
    private boolean isAccessibilityServiceEnabled() {
        // 1. 内存实例检查 (最快)
        if (DoubaoAccessibilityService.isAlive()) return true;

        // 2. 数据库匹配检查 (绕过系统缓存)
        String service = getPackageName() + "/" + DoubaoAccessibilityService.class.getName();
        try {
            String setting = Settings.Secure.getString(getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (!TextUtils.isEmpty(setting)) {
                TextUtils.SimpleStringSplitter colonSplitter = new TextUtils.SimpleStringSplitter(':');
                colonSplitter.setString(setting);
                while (colonSplitter.hasNext()) {
                    String componentName = colonSplitter.next();
                    if (componentName.equalsIgnoreCase(service)) {
                        return true;
                    }
                }
            }
        } catch (Exception ignored) {}

        // 3. Manager 检查 (最后保底)
        AccessibilityManager am = (AccessibilityManager) getSystemService(Context.ACCESSIBILITY_SERVICE);
        if (am != null) {
            List<AccessibilityServiceInfo> enabledServices = am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
            if (enabledServices != null) {
                for (AccessibilityServiceInfo info : enabledServices) {
                    if (info.getId().contains(getPackageName())) return true;
                }
            }
        }

        return false;
    }
}
