package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo

/** 单步动作执行结果。atEnd 为协议保留字段(端侧不再产生，YAGNI)。 */
data class ExecResult(val ok: Boolean, val atEnd: Boolean = false)

/**
 * 真实动作执行器。framework 集成部分仅在真机联调验证；
 * 坐标几何委托给可单测的 GestureGeometry。
 *
 * 端侧为哑执行器，只做原子动作，归位判定在云端。
 */
class Executor(
    private val service: AccessibilityService,
    private val context: Context,
) {
    fun execute(op: String, params: Map<String, String>): ExecResult {
        return when (op) {
            "tap" -> ExecResult(ok = tap(params))
            "input" -> ExecResult(ok = input(params["text"].orEmpty()))
            "swipe" -> ExecResult(ok = swipe(params))
            "back" -> ExecResult(ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
            "home" -> ExecResult(ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME))
            "read_screen", "wait" -> ExecResult(true)
            else -> ExecResult(false)
        }
    }

    private fun findByText(text: String): AccessibilityNodeInfo? {
        if (text.isBlank()) return null
        val root = service.rootInActiveWindow ?: return null
        val matches = root.findAccessibilityNodeInfosByText(text)
        return matches.firstOrNull { it.isClickable } ?: matches.firstOrNull()
    }

    /**
     * tap 优先按云侧下发的 x/y 坐标点击(云侧已把选中节点解析为 bounds 中心，避免端侧全屏
     * 子串匹配误命中负一屏磁贴)；坐标缺失时回退 match_text 子串匹配。
     */
    private fun tap(params: Map<String, String>): Boolean {
        GestureGeometry.tapPointFromParams(params)?.let { (x, y) ->
            return dispatchTap(x, y)
        }
        return tapByText(params["match_text"].orEmpty())
    }

    private fun tapByText(matchText: String): Boolean {
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
}