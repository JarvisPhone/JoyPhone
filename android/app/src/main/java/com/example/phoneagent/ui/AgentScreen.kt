package com.example.phoneagent.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.ui.theme.JoyPhoneTheme
import com.example.phoneagent.ui.theme.StatusColors

@Composable
fun AgentScreen(
    uiState: AgentUiState,
    onTitleTap: () -> Unit,
    onOpenAccessibility: () -> Unit,
    onRunTestTask: () -> Unit,
    onCaptureSample: () -> Unit,
    onHideDebug: () -> Unit,
) {
    Scaffold { inner ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(inner)
                .padding(20.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "JoyPhone Agent",
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.clickable { onTitleTap() },
            )

            AccessibilityCard(uiState.status.accessibilityGranted, onOpenAccessibility)
            ConnectionCard(uiState.status.connection)
            TestTaskCard(
                enabled = uiState.status.connection == ConnectionState.CONNECTED,
                onRunTestTask = onRunTestTask,
            )
            SampleCard(
                enabled = uiState.status.connection == ConnectionState.CONNECTED,
                countdown = uiState.sampleCountdown,
                hint = uiState.sampleHint,
                onCapture = onCaptureSample,
            )
            TaskCard(uiState.status.task)

            if (uiState.debugUnlocked) {
                DebugPanel(debug = uiState.debug, onHide = onHideDebug)
            }
        }
    }
}

@Composable
private fun AccessibilityCard(granted: Boolean, onOpen: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("无障碍服务", style = MaterialTheme.typography.titleMedium)
            Text(
                if (granted) "已授权，可开始联调" else "未授权，请先开启无障碍服务",
                style = MaterialTheme.typography.bodyMedium,
            )
            if (!granted) {
                Button(onClick = onOpen) { Text("去开启") }
            }
        }
    }
}

@Composable
private fun ConnectionCard(state: ConnectionState) {
    val (color, label) = when (state) {
        ConnectionState.CONNECTED -> StatusColors.Connected to "已连接"
        ConnectionState.CONNECTING -> StatusColors.Pending to "连接中…"
        ConnectionState.RECONNECTING -> StatusColors.Pending to "重连中…"
        ConnectionState.DISCONNECTED -> StatusColors.Disconnected to "已断开"
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(Modifier.size(14.dp).background(color, CircleShape))
            Column {
                Text("云端连接", style = MaterialTheme.typography.titleMedium)
                Text(label, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
private fun TestTaskCard(enabled: Boolean, onRunTestTask: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("测试任务", style = MaterialTheme.typography.titleMedium)
            Button(onClick = onRunTestTask, enabled = enabled) {
                Text("运行测试任务")
            }
        }
    }
}

@Composable
private fun SampleCard(
    enabled: Boolean,
    countdown: Int,
    hint: String,
    onCapture: () -> Unit,
) {
    val counting = countdown > 0
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("场景采样", style = MaterialTheme.typography.titleMedium)
            Button(
                onClick = onCapture,
                enabled = enabled && !counting,
            ) {
                Text(if (counting) "倒计时 $countdown s…" else "开始采样(10s 后抓帧)")
            }
            if (hint.isNotBlank()) {
                Text(hint, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun TaskCard(task: TaskState) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("当前任务", style = MaterialTheme.typography.titleMedium)
            when (task) {
                is TaskState.Idle -> Text("空闲中", style = MaterialTheme.typography.bodyMedium)
                is TaskState.Running -> Text("执行中：${task.description}", style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun PreviewConnected() {
    JoyPhoneTheme {
        AgentScreen(
            uiState = AgentUiState(
                status = AgentStatus(
                    accessibilityGranted = true,
                    connection = ConnectionState.CONNECTED,
                    task = TaskState.Running("打开飞书并回复消息"),
                ),
            ),
            onTitleTap = {}, onOpenAccessibility = {}, onRunTestTask = {}, onCaptureSample = {}, onHideDebug = {},
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun PreviewDisconnected() {
    JoyPhoneTheme {
        AgentScreen(
            uiState = AgentUiState(
                status = AgentStatus(
                    accessibilityGranted = false,
                    connection = ConnectionState.DISCONNECTED,
                    task = TaskState.Idle,
                ),
                debug = DebugInfo(wsUrl = "ws://10.0.2.2:8000", deviceId = "abc123", reconnectAttempts = 2),
                debugUnlocked = true,
            ),
            onTitleTap = {}, onOpenAccessibility = {}, onRunTestTask = {}, onCaptureSample = {}, onHideDebug = {},
        )
    }
}