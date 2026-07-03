// android/app/src/main/java/com/example/phoneagent/accessibility/Perception.kt
package com.example.phoneagent.accessibility

data class FlatNode(
    val id: String,
    val text: String? = null,
    val visible: Boolean = true,
    val clickable: Boolean = false,
    val editable: Boolean = false,
)

object PerceptionFilter {
    fun filter(nodes: List<FlatNode>): List<FlatNode> {
        return nodes.filter { n ->
            n.visible && (n.clickable || !n.text.isNullOrBlank())
        }
    }
}