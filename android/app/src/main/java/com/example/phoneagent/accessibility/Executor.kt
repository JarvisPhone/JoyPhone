package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo

/**
 * 真实动作执行器。framework 集成部分仅在真机联调验证；
 * 坐标几何委托给可单测的 GestureGeometry。
 */
class Executor(
    private val service: AccessibilityService,
    private val context: Context,
) {
    fun execute(op: String, params: Map<String, String>): Boolean {
        return when (op) {
            "tap" -> tap(params["match_text"].orEmpty())
            "input" -> input(params["text"].orEmpty())
            "swipe" -> swipe(params)
            "back" -> service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
            "home" -> service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
            "open_app" -> openApp(params["pkg"].orEmpty())
            "read_screen", "wait" -> true
            else -> false
        }
    }

    private fun findByText(text: String): AccessibilityNodeInfo? {
        if (text.isBlank()) return null
        val root = service.rootInActiveWindow ?: return null
        val matches = root.findAccessibilityNodeInfosByText(text)
        return matches.firstOrNull { it.isClickable } ?: matches.firstOrNull()
    }

    private fun tap(matchText: String): Boolean {
        val node = findByText(matchText) ?: return false
        val rect = android.graphics.Rect()
        node.getBoundsInScreen(rect)
        val (cx, cy) = GestureGeometry.centerOf(listOf(rect.left, rect.top, rect.right, rect.bottom))
        return dispatchTap(cx, cy)
    }

    private fun input(text: String): Boolean {
        val root = service.rootInActiveWindow ?: return false
        val editable = findEditable(root) ?: return false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return editable.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findEditable(child)
            if (found != null) return found
        }
        return null
    }

    private fun swipe(params: Map<String, String>): Boolean {
        val metrics = context.resources.displayMetrics
        val s = GestureGeometry.fromParams(params)
            ?: GestureGeometry.defaultSwipeUp(metrics.widthPixels, metrics.heightPixels)
        val path = Path().apply {
            moveTo(s.startX, s.startY)
            lineTo(s.endX, s.endY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 300))
            .build()
        return service.dispatchGesture(gesture, null, null)
    }

    private fun dispatchTap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
            .build()
        return service.dispatchGesture(gesture, null, null)
    }

    private fun openApp(pkg: String): Boolean {
        if (pkg.isBlank()) return false
        val intent = context.packageManager.getLaunchIntentForPackage(pkg) ?: return false
        intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return true
    }
}