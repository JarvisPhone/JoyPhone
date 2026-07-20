package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.graphics.Rect
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** 单步动作执行结果。 */
data class ExecResult(val ok: Boolean)

/**
 * 真实动作执行器。framework 集成部分仅在真机联调验证；
 * 坐标几何委托给可单测的 GestureGeometry。
 *
 * 端侧为哑执行器，只做原子动作，归位判定在云端。
 *
 * 节点回收约定:
 * - rootInActiveWindow 拿到的 root 由本类各方法在使用完毕后 recycle。
 * - findByText / findEditable / findEditableAt 返回的命中节点所有权转移给调用方,
 *   调用方用完必须 recycle;遍历中未命中的节点在函数内部即时 recycle。
 */
@Suppress("DEPRECATION") // recycle() 在 API 33+ 标记废弃,但 minSdk 以下仍需显式回收防泄漏
class Executor(
    private val service: AccessibilityService,
    private val context: Context,
) {
    fun execute(op: String, params: Map<String, String>): ExecResult {
        return when (op) {
            "tap" -> ExecResult(ok = tap(params))
            "input" -> ExecResult(ok = input(params))
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
        try {
            val matches = root.findAccessibilityNodeInfosByText(text)
            val picked = matches.firstOrNull { it.isClickable } ?: matches.firstOrNull()
            matches.forEach { if (it !== picked) it.recycle() }
            return picked
        } finally {
            root.recycle()
        }
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
        val rect = Rect()
        node.getBoundsInScreen(rect)
        node.recycle()
        val (cx, cy) = GestureGeometry.centerOf(listOf(rect.left, rect.top, rect.right, rect.bottom))
        return dispatchTap(cx, cy)
    }

    /**
     * input 优先按 params 的 x/y 坐标命中 editable(bounds 包含该点),与云端
     * _input_target_node 逻辑对称;坐标缺失时才回退首个 editable。
     * 坐标存在但无命中返回 false,让云侧感知失败重新决策,而不是写进错误的输入框。
     */
    private fun input(params: Map<String, String>): Boolean {
        val text = params["text"].orEmpty()
        val root = service.rootInActiveWindow ?: return false
        try {
            val point = GestureGeometry.tapPointFromParams(params)
            val editable = if (point != null) {
                findEditableAt(root, point.first, point.second)
            } else {
                findEditable(root)
            } ?: return false
            try {
                val args = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
                }
                return editable.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
            } finally {
                editable.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    /**
     * 找首个 editable。命中节点所有权转移给调用方(调用方用完 recycle);
     * 未命中的 child 在此回收。
     */
    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findEditable(child)
            if (found != null) {
                if (found !== child) child.recycle()
                return found
            }
            child.recycle()
        }
        return null
    }

    /**
     * 找 bounds 包含点 (x, y) 的 editable。命中节点所有权转移给调用方(调用方用完 recycle);
     * 未命中的 child 在此回收。
     */
    private fun findEditableAt(node: AccessibilityNodeInfo, x: Float, y: Float): AccessibilityNodeInfo? {
        if (node.isEditable) {
            val rect = Rect()
            node.getBoundsInScreen(rect)
            if (GestureGeometry.pointInBounds(listOf(rect.left, rect.top, rect.right, rect.bottom), x, y)) {
                return node
            }
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findEditableAt(child, x, y)
            if (found != null) {
                if (found !== child) child.recycle()
                return found
            }
            child.recycle()
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
        return dispatchGestureBlocking(gesture)
    }

    private fun dispatchTap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
            .build()
        return dispatchGestureBlocking(gesture)
    }

    /**
     * 派发手势并等待真实结果:onCompleted→true / onCancelled→false。
     * execute 为同步签名,这里用 CountDownLatch 阻塞等待,2s 超时兜底返回 false。
     * 注意:阻塞的是 WS listener 线程(OkHttp 回调线程,非主线程),不会卡 UI。
     */
    private fun dispatchGestureBlocking(gesture: GestureDescription): Boolean {
        val latch = CountDownLatch(1)
        val ok = AtomicBoolean(false)
        val accepted = service.dispatchGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) {
                    ok.set(true)
                    latch.countDown()
                }

                override fun onCancelled(gestureDescription: GestureDescription?) {
                    ok.set(false)
                    latch.countDown()
                }
            },
            null,
        )
        if (!accepted) return false
        return latch.await(2, TimeUnit.SECONDS) && ok.get()
    }
}
