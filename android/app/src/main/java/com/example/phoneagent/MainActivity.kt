package com.example.phoneagent

import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.phoneagent.accessibility.PhoneAgentService

class MainActivity : AppCompatActivity() {

    private lateinit var tip: TextView
    private lateinit var btn: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
        }

        tip = TextView(this)
        btn = Button(this).apply {
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        }

        root.addView(tip)
        root.addView(btn)
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    private fun refreshStatus() {
        val componentFlat = ComponentName(this, PhoneAgentService::class.java).flattenToString()
        val setting = Settings.Secure.getString(
            contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        )
        val enabled = AccessibilityStatus.isEnabled(setting, componentFlat)

        if (enabled) {
            tip.text = "JoyPhone Agent\n\n无障碍服务已开启，可开始真机联调。"
            btn.text = "查看无障碍设置"
        } else {
            tip.text = "JoyPhone Agent\n\n请先开启无障碍服务后再进行真机联调。"
            btn.text = "打开无障碍设置"
        }
    }
}