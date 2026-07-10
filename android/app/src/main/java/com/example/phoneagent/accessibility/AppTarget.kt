package com.example.phoneagent.accessibility

/**
 * open_app 目标解析（纯逻辑，可单测）。
 * 云端契约：params 允许 {"package":"包名"}/{"pkg":"包名"}（直接是包名）
 * 或 {"app":"应用名"}（需 PackageManager 反查包名）。
 * 包名优先于应用名。framework 反查在 Executor 完成。
 */
sealed interface AppTarget {
    data class ByPackage(val pkg: String) : AppTarget
    data class ByLabel(val label: String) : AppTarget
    data object None : AppTarget

    companion object {
        fun fromParams(params: Map<String, String>): AppTarget {
            val pkg = params["package"]?.takeIf { it.isNotBlank() }
                ?: params["pkg"]?.takeIf { it.isNotBlank() }
            if (pkg != null) return ByPackage(pkg)

            val label = params["app"]?.takeIf { it.isNotBlank() }
            if (label != null) return ByLabel(label)

            return None
        }
    }
}