package com.example.phoneagent.accessibility

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import com.example.phoneagent.protocol.NodeDto

/** 节点扁平化：递归 AccessibilityNodeInfo → List<NodeDto>。纯辅助方法可单测。 */
object NodeFlattener {

    fun makeId(indexPath: List<Int>): String = indexPath.joinToString("-")

    fun rectToBounds(l: Int, t: Int, r: Int, b: Int): List<Int> = listOf(l, t, r, b)

    fun rectToBounds(rect: Rect): List<Int> = rectToBounds(rect.left, rect.top, rect.right, rect.bottom)

    const val MAX_TEXT_LEN = 20

    /** text 截断：超过 MAX_TEXT_LEN 加省略号。null 原样返回。纯逻辑，可单测。 */
    fun truncate(s: String?): String? {
        if (s == null) return null
        return if (s.length > MAX_TEXT_LEN) s.substring(0, MAX_TEXT_LEN) + "…" else s
    }

    /** 是否保留该节点：可交互或携带可定位语义(desc)。纯逻辑，可单测。 */
    fun shouldKeep(
        clickable: Boolean,
        editable: Boolean,
        scrollable: Boolean,
        checkable: Boolean,
        hasDesc: Boolean,
    ): Boolean = clickable || editable || scrollable || checkable || hasDesc

    /** 递归收集节点（framework 集成，真机验证）。 */
    fun flatten(root: AccessibilityNodeInfo?): List<NodeDto> {
        val out = mutableListOf<NodeDto>()
        if (root != null) walk(root, listOf(0), out)
        return out
    }

    private fun walk(node: AccessibilityNodeInfo, path: List<Int>, out: MutableList<NodeDto>) {
        val rect = Rect().also { node.getBoundsInScreen(it) }
        val visible = rect.width() > 0 && rect.height() > 0
        val text = node.text?.toString()
        // 与云端 PerceptionFilter 对齐：可见且(可点击或有文本)才上报
        if (visible && (node.isClickable || !text.isNullOrBlank())) {
            out.add(
                NodeDto(
                    id = makeId(path),
                    text = text,
                    desc = node.contentDescription?.toString(),
                    className = node.className?.toString(),
                    bounds = rectToBounds(rect),
                    clickable = node.isClickable,
                    editable = node.isEditable,
                )
            )
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            walk(child, path + i, out)
        }
    }
}