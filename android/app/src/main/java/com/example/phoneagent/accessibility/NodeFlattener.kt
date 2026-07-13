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

    /**
     * 递归收集节点：
     * - 可交互(clickable/editable/scrollable/checkable)或有 contentDescription 才收录。
     * - 子树向上合并：可交互节点自身 text 为空时，取子树中最近的非空 text/desc 补上。
     * - 合并后不再单独收录被吸收的纯文本叶子。
     * framework 集成，真机验证。
     */
    private fun walk(node: AccessibilityNodeInfo, path: List<Int>, out: MutableList<NodeDto>) {
        val rect = Rect().also { node.getBoundsInScreen(it) }
        val visible = rect.width() > 0 && rect.height() > 0
        val text = node.text?.toString()
        val desc = node.contentDescription?.toString()
        val interactive = node.isClickable || node.isEditable || node.isScrollable || node.isCheckable
        val keep = visible && shouldKeep(
            clickable = node.isClickable,
            editable = node.isEditable,
            scrollable = node.isScrollable,
            checkable = node.isCheckable,
            hasDesc = !desc.isNullOrBlank(),
        )

        if (keep) {
            // 可交互但自身无文本 -> 向下摘一个最近的非空 text/desc 补上
            val label = when {
                !text.isNullOrBlank() -> text
                !desc.isNullOrBlank() -> desc
                interactive -> firstDescendantLabel(node)
                else -> null
            }
            out.add(
                NodeDto(
                    id = makeId(path),
                    text = truncate(label),
                    desc = truncate(desc),
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

    /** 深度优先取子树中第一个非空 text/desc（供可交互父容器合并用）。 */
    private fun firstDescendantLabel(node: AccessibilityNodeInfo):String? {
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val t = child.text?.toString()
            if (!t.isNullOrBlank()) return t
            val d = child.contentDescription?.toString()
            if (!d.isNullOrBlank()) return d
            val deeper = firstDescendantLabel(child)
            if (deeper != null) return deeper
        }
        return null
    }
}