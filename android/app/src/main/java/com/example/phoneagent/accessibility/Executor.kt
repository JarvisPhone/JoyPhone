package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo

/** 单步动作执行结果。atEnd 仅在桌面翻页(next_page)到底时为 true。 */
data class ExecResult(val ok: Boolean, val atEnd: Boolean = false)

/**
 * 真实动作执行器。framework 集成部分仅在真机联调验证；
 * 坐标几何委托给可单测的 GestureGeometry。
 *
 * 桌面翻屏算子(home_first_page / next_page)只提供「归位/翻页」纯线性能力，不懂业务：
 * LLM 用它们像真人一样翻桌面找应用图标，翻到底(atEnd)仍没找到则由云端决定 abort。
 *
 * swipe 方向语义：
 * - 手指往右滑(toRight=true) = 看左边的屏(往回/归位到最左第一屏)
 * - 手指往左滑(toRight=false) = 看右边的屏(往前翻下一屏)
 */
class Executor(
    private val service: AccessibilityService,
    private val context: Context,
) {
    fun execute(op: String, params: Map<String, String>): ExecResult {
        return when (op) {
            "tap" -> ExecResult(ok = tap(params["match_text"].orEmpty()))
            "input" -> ExecResult(ok = input(params["text"].orEmpty()))
            "swipe" -> ExecResult(ok = swipe(params))
            "back" -> ExecResult(ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
            "home" -> ExecResult(ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME))
            "home_first_page" -> homeFirstPage()
            "next_page" -> nextPage()
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

    /** 当前屏幕指纹快照，用于翻页前后同屏判定。 */
    private fun snapshotFingerprint(): String =
        ScreenFingerprint.of(NodeFlattener.flatten(service.rootInActiveWindow))

    /**
     * 水平滑动手势。
     * toRight=true：startX=0.2w→endX=0.8w(手指往右滑=看左屏/归位)；
     * toRight=false：startX=0.8w→endX=0.2w(手指往左滑=看右屏/前翻)。
     * 滑动后 sleep SETTLE_MS 等界面稳定。
     */
    private fun swipeHorizontal(toRight: Boolean): Boolean {
        val metrics = context.resources.displayMetrics
        val w = metrics.widthPixels
        val h = metrics.heightPixels
        val startX = if (toRight) w * 0.2f else w * 0.8f
        val endX = if (toRight) w * 0.8f else w * 0.2f
        val y = h / 2f
        val path = Path().apply {
            moveTo(startX, y)
            lineTo(endX, y)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 300))
            .build()
        val ok = service.dispatchGesture(gesture, null, null)
        Thread.sleep(SETTLE_MS)
        return ok
    }

    /**
     * 回到桌面并归位到最左第一屏。先 HOME，再反复往回滑(看左屏)，
     * 直到翻页前后同屏(已到最左)或达到 MAX_PAGES 上限。
     */
    private fun homeFirstPage(): ExecResult {
        service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
        Thread.sleep(SETTLE_MS)
        repeat(MAX_PAGES) {
            val before = snapshotFingerprint()
            swipeHorizontal(toRight = true)
            val after = snapshotFingerprint()
            if (after == before) return ExecResult(ok = true)
        }
        return ExecResult(ok = true)
    }

    /** 桌面向后翻一屏(看右屏)。翻页前后同屏说明已到最后一屏 -> atEnd=true。 */
    private fun nextPage(): ExecResult {
        val before = snapshotFingerprint()
        swipeHorizontal(toRight = false)
        val after = snapshotFingerprint()
        return ExecResult(ok = true, atEnd = (after == before))
    }

    companion object {
        const val SETTLE_MS = 500L
        const val MAX_PAGES = 12
    }
}