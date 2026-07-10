package com.example.phoneagent.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun DebugPanel(
    debug: DebugInfo,
    onHide: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .padding(16.dp)
             .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("调试信息", style = MaterialTheme.typography.titleMedium)
            Text("WS_URL: ${debug.wsUrl}", style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
            Text("deviceId: ${debug.deviceId}", style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
            Text("重连次数: ${debug.reconnectAttempts}", style = MaterialTheme.typography.bodySmall)

            Text("最近动作", style = MaterialTheme.typography.titleSmall)
            if (debug.recentActions.isEmpty()) {
                Text("（暂无）", style = MaterialTheme.typography.bodySmall)
            } else {
              debug.recentActions.takeLast(10).reversed().forEach { a ->
                    Text(
                        "${a.op} ${if (a.ok) "✓" else "✗"} ${a.detail}",
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                  )
                }
            }

            Text("WS 事件", style = MaterialTheme.typography.titleSmall)
            if (debug.wsEvents.isEmpty()) {
                Text("（暂无）", style = MaterialTheme.typography.bodySmall)
            } else {
                debug.wsEvents.takeLast(10).reversed().forEach { e ->
                    Text(
                        "${e.event}: ${e.detail}",
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }

            Text("实时事件流", style = MaterialTheme.typography.titleSmall)
            if (debug.traceEvents.isEmpty()) {
                Text("（暂无）", style = MaterialTheme.typography.bodySmall)
            } else {
                debug.traceEvents.takeLast(30).reversed().forEach { ev ->
                    Text(
                        formatLine(ev),
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }

            TextButton(onClick = onHide) { Text("收起调试视图") }
        }
    }
}

private fun formatLine(ev: TraceEvent): String {
    val time = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date(ev.ts))
    val arrow = when (ev.direction) {
        TraceDirection.UP -> "↑"
        TraceDirection.DOWN -> "↓"
        TraceDirection.INFO -> "·"
    }
    return "$time $arrow ${ev.kind} ${ev.summary}"
}