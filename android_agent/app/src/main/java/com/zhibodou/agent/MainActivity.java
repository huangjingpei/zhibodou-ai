package com.zhibodou.agent;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * 极简状态看板与一键授权引导页
 */
public class MainActivity extends Activity {

    private TextView tvStatus;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(60, 80, 60, 80);

        TextView tvTitle = new TextView(this);
        tvTitle.setText("智播豆 Agent 2.0 (50KB 极速版)");
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
        if (DoubaoAccessibilityService.isServiceRunning()) {
            tvStatus.setText("✅ 状态：无障碍 Agent 运行中 (RPC 端口 18888 就绪)");
            tvStatus.setTextColor(0xFF008800);
        } else {
            tvStatus.setText("❌ 状态：无障碍服务未开启，请点击下方按钮开启授权");
            tvStatus.setTextColor(0xFFCC0000);
        }
    }
}
