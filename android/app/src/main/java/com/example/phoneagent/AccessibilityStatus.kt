package com.example.phoneagent

/** 无障碍启用状态判定：纯字符串匹配，可单测。 */
object AccessibilityStatus {

    /**
     * @param enabledSetting Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES 的值（冒号分隔的组件列表）
     * @param componentFlat  目标服务的 ComponentName.flattenToString()
     */
    fun isEnabled(enabledSetting: String?, componentFlat: String): Boolean {
        if (enabledSetting.isNullOrBlank()) return false
        return enabledSetting.split(':').any { it.equals(componentFlat, ignoreCase = true) }
    }
}