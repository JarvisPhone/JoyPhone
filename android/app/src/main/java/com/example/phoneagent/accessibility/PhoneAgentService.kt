// android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt
package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

class PhoneAgentService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // MVP: 事件入口，后续接入节点树提取与上报
    }

    override fun onInterrupt() = Unit
}