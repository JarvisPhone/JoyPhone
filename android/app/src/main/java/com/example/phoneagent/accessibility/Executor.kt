// android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt
package com.example.phoneagent.accessibility

class Executor {
    fun execute(op: String, params: Map<String, String>): Boolean {
        return when (op) {
            "tap", "input", "swipe", "back", "home", "wait", "open_app", "read_screen" -> true
            else -> false
        }
    }
}