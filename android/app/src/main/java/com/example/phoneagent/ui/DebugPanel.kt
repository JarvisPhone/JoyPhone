package com.example.phoneagent.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val UpColor = Color(0xFF2563EB)
private val DownColor = Color(0xFF16A34A)
private val InfoColor = Color(0xFF6B7280)
private val OkColor = Color(0xFF22C55E)
private val ErrorColor = Color(0xFFEF4444)

@Composable
fun DebugPanel(
    debug: DebugInfo,
    onHide: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var actionsExpanded by remember { mutableStateOf(true) }
    var eventsExpanded by remember { mutableStateOf(true) }
    var traceExpanded by remember { mutableStateOf(true) }

    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "调试信息",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                )
                TextButton(onClick = onHide) {
                    Text("收起")
                }
            }

            MetaInfoSection(debug)

            HorizontalDivider()

            CollapsibleSection(
                title = "最近动作",
                count = debug.recentActions.size,
                expanded = actionsExpanded,
                onToggle = { actionsExpanded = !actionsExpanded },
            ) {
                if (debug.recentActions.isEmpty()) {
                    Text("（暂无）", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    debug.recentActions.takeLast(10).reversed().forEach { a ->
                        ActionLogItem(a.op, a.ok, a.detail)
                    }
                }
            }

            CollapsibleSection(
                title = "WS 事件",
                count = debug.wsEvents.size,
                expanded = eventsExpanded,
                onToggle = { eventsExpanded = !eventsExpanded },
            ) {
                if (debug.wsEvents.isEmpty()) {
                    Text("（暂无）", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    debug.wsEvents.takeLast(10).reversed().forEach { e ->
                        WsEventItem(e.event, e.detail, e.ts)
                    }
                }
            }

            CollapsibleSection(
                title = "实时事件流",
                count = debug.traceEvents.size,
                expanded = traceExpanded,
                onToggle = { traceExpanded = !traceExpanded },
            ) {
                if (debug.traceEvents.isEmpty()) {
                    Text("（暂无）", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    debug.traceEvents.takeLast(30).reversed().forEach { ev ->
                        TraceEventItem(ev)
                    }
                }
            }
        }
    }
}

@Composable
private fun MetaInfoSection(debug: DebugInfo) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        MetaRow("WS_URL", debug.wsUrl)
        MetaRow("deviceId", debug.deviceId)
        MetaRow("重连次数", debug.reconnectAttempts.toString())
    }
}

@Composable
private fun MetaRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(text = "$label:", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, modifier = Modifier.weight(0.3f))
        Text(text = value, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(0.7f))
    }
}

@Composable
private fun CollapsibleSection(title: String, count: Int, expanded: Boolean, onToggle: () -> Unit, content: @Composable () -> Unit) {
    Column {
        Row(modifier = Modifier.fillMaxWidth().clickable { onToggle() }.padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(text = title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Medium)
                Badge(count = count)
            }
            Icon(imageVector = if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore, contentDescription = null, modifier = Modifier.size(20.dp))
        }
        AnimatedVisibility(visible = expanded, enter = expandVertically(), exit = shrinkVertically()) {
            Column(modifier = Modifier.padding(start = 8.dp, top = 4.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                content()
            }
        }
    }
}

@Composable
private fun Badge(count: Int) {
    Box(modifier = Modifier.clip(RoundedCornerShape(10.dp)).background(MaterialTheme.colorScheme.surfaceVariant).padding(horizontal = 8.dp, vertical = 2.dp)) {
        Text(text = count.toString(), style = MaterialTheme.typography.labelSmall, fontSize = 10.sp)
    }
}

@Composable
private fun ActionLogItem(op: String, ok: Boolean, detail: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(modifier = Modifier.size(8.dp).clip(RoundedCornerShape(4.dp)).background(if (ok) OkColor else ErrorColor))
        Text(text = op, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, modifier = Modifier.weight(0.3f))
        Text(text = if (ok) "✓" else "✗", style = MaterialTheme.typography.bodySmall, color = if (ok) OkColor else ErrorColor, modifier = Modifier.weight(0.1f))
        Text(text = detail, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(0.6f))
    }
}

@Composable
private fun WsEventItem(event: String, detail: String, ts: Long) {
    val time = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault()).format(Date(ts))
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(text = time, style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(0.35f))
        Text(text = event, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, modifier = Modifier.weight(0.25f))
        Text(text = detail, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(0.4f), maxLines = 1)
    }
}

@Composable
private fun TraceEventItem(ev: TraceEvent) {
    val time = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault()).format(Date(ev.ts))
    val (arrow, arrowColor) = when (ev.direction) {
        TraceDirection.UP -> "↑" to UpColor
        TraceDirection.DOWN -> "↓" to DownColor
        TraceDirection.INFO -> "·" to InfoColor
    }
    val kindColor = when (ev.direction) {
        TraceDirection.UP -> UpColor
        TraceDirection.DOWN -> DownColor
        TraceDirection.INFO -> InfoColor
    }
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(text = time, style = MaterialTheme.typography.labelSmall, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(0.35f))
        Text(text = arrow, style = MaterialTheme.typography.bodyMedium, color = arrowColor, fontWeight = FontWeight.Bold, modifier = Modifier.weight(0.08f))
        Text(text = ev.kind, style = MaterialTheme.typography.bodySmall, color = kindColor, fontWeight = FontWeight.Medium, modifier = Modifier.weight(0.25f))
        Text(text = ev.summary, style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(0.32f), maxLines = 1)
    }
}
