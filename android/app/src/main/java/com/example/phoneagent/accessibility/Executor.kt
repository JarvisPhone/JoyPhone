package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import android.util.Log
import com.example.phoneagent.protocol.NodeDto

/** 单步动作执行结果。error 为机器可读错误码(anchor_not_found 等),随 action.result 回传云端。 */
data class ExecResult(val ok: Boolean, val error: String? = null)

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
            "tap" -> tap(params)
            "tap_at" -> tapAt(params)
            "input" -> input(params)
            "swipe" -> ExecResult(ok = swipe(params))
            "back" -> ExecResult(ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
            "home" -> ExecResult(ok = service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME))
            "read_screen", "wait" -> ExecResult(true)
            else -> ExecResult(false, "unknown_op")
        }
    }

    /** 实时树快照:flatten 内部回收子节点,root 由本方法回收。 */
    private fun liveNodes(): List<NodeDto>? {
        val root = service.rootInActiveWindow ?: return null
        return try {
            NodeFlattener.flatten(root)
        } finally {
            root.recycle()
        }
    }

    /**
     * tap 只接受语义锚点:执行瞬间在实时树上重新定位,用「当下的」bounds 点击。
     * 不使用云端坐标(帧过期即点歪);匹配不到/有歧义 fail-closed 报错。
     */
    private fun tap(params: Map<String, String>): ExecResult {
        val anchor = AnchorResolver.fromParams(params)
            ?: return ExecResult(false, "anchor_missing")
        val nodes = liveNodes() ?: return ExecResult(false, "no_window")
        return when (val r = AnchorResolver.resolve(nodes, anchor)) {
            is ResolveResult.Found -> {
                val bounds = r.node.bounds
                    ?: return ExecResult(false, "anchor_no_bounds")
                val (cx, cy) = GestureGeometry.centerOf(bounds)
                ExecResult(dispatchTap(cx, cy))
            }
            ResolveResult.NotFound -> ExecResult(false, "anchor_not_found")
            is ResolveResult.Ambiguous -> ExecResult(false, "anchor_ambiguous")
        }
    }

    /** tap_at:原始坐标点击,逃生舱(画布/地图等无语义节点场景),正常任务不生成。 */
    private fun tapAt(params: Map<String, String>): ExecResult {
        val point = GestureGeometry.tapPointFromParams(params)
            ?: return ExecResult(false, "bad_coords")
        return ExecResult(dispatchTap(point.first, point.second))
    }

    /**
     * input 只接受语义锚点:在实时树上解析出目标 editable 的 NodeDto(含 id 路径),
     * 再按 id 路径在活树上找到对应 AccessibilityNodeInfo 执行 SET_TEXT。
     * 无锚点/未命中 fail-closed,绝不写进错误的输入框。
     */
    private fun input(params: Map<String, String>): ExecResult {
        val text = params["text"].orEmpty()
        val anchor = AnchorResolver.fromParams(params)
            ?: return ExecResult(false, "anchor_missing")
        val root = service.rootInActiveWindow ?: return ExecResult(false, "no_window")
        try {
            val targetId = when (val r = AnchorResolver.resolve(NodeFlattener.flatten(root), anchor, editableOnly = true)) {
                is ResolveResult.Found -> r.node.id
                ResolveResult.NotFound -> return ExecResult(false, "anchor_not_found")
                is ResolveResult.Ambiguous -> return ExecResult(false, "anchor_ambiguous")
            }
            val editable = findNodeByPath(root, targetId)
                ?: return ExecResult(false, "anchor_stale")
            try {
                val args = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
                }
                return ExecResult(editable.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args), null)
            } finally {
                // editable 可能就是 root 本身(id="0"),外层 finally 会回收 root,避免 double-recycle
                if (editable !== root) editable.recycle()
            }
        } finally {
            root.recycle()
        }
    }

    /**
     * 按 NodeFlattener 的 id(DFS 下标路径,如 "0-1-2")在活树上定位节点。
     * 命中节点所有权转移给调用方(用完 recycle);路径失效(树已变化)返回 null。
     */
    private fun findNodeByPath(root: AccessibilityNodeInfo, id: String): AccessibilityNodeInfo? {
        val segments = id.split("-").mapNotNull { it.toIntOrNull() }
        if (segments.isEmpty()) return null
        val chain = mutableListOf<AccessibilityNodeInfo>()
        var current: AccessibilityNodeInfo = root
        for (seg in segments.drop(1)) {
            val child = current.getChild(seg) ?: break
            chain.add(child)
            current = child
        }
        if (chain.size != segments.size - 1) {
            chain.forEach { it.recycle() }
            return null
        }
        val target = chain.lastOrNull() ?: return root
        chain.dropLast(1).forEach { it.recycle() }
        return target
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
        return dispatchGestureFireAndForget(gesture, "swipe")
    }

    private fun dispatchTap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
            .build()
        return dispatchGestureFireAndForget(gesture, "tap")
    }

    /**
     * 非阻塞派发手势:返回值仅代表「框架已受理」,不代表手势已执行完成。
     * 不在 WS reader 线程上等待 GestureResultCallback——实测部分 ROM 上回调
     * 延迟 1.7~6s,等待会把后续动作全部堵在队列里(2026-07-21 back 延迟 6s
     * 导致误判 abort 事故的根因)。动作的真实结果由云端通过后续 perception
     * 帧判定(归位判定在云端),onCancelled 仅记日志。
     */
    private fun dispatchGestureFireAndForget(gesture: GestureDescription, tag: String): Boolean {
        return service.dispatchGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
                override fun onCancelled(gestureDescription: GestureDescription?) {
                    Log.w("PhoneAgent", "gesture cancelled: $tag")
                }
            },
            null,
        )
    }
}
