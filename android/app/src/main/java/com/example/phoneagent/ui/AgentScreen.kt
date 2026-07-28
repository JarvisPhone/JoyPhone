package com.example.phoneagent.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.ui.theme.JoyPhoneTheme
import com.example.phoneagent.ui.theme.StatusColors

private val DoneGreen = Color(0xFF16A34A)
private val FailedRed = Color(0xFFDC2626)
private val SendBlue = Color(0xFF2563EB)

private const val DEFAULT_GOAL = "打开飞书，给群「Android AI 开发组」发一条消息"

@Composable
fun AgentScreen(
    uiState: AgentUiState,
    onTitleTap: () -> Unit,
    onOpenAccessibility: () -> Unit,
    onSendGoal: (String) -> Unit,
    onCaptureSample: () -> Unit,
    onHideDebug: () -> Unit,
    onCancelTask: () -> Unit = {},
) {
    val connected = uiState.status.connection == ConnectionState.CONNECTED

    Scaffold { inner ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(inner)
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(top = 20.dp, bottom = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            HeaderTitle(
                onTap = onTitleTap,
                taskState = uiState.status.task,
            )

            AccessibilityCard(
                granted = uiState.status.accessibilityGranted,
                onOpen = onOpenAccessibility,
            )

            ConnectionCard(state = uiState.status.connection)

            TaskStatusCard(
                task = uiState.status.task,
                onCancel = onCancelTask,
            )

            // 发送任务卡:放在场景采样之前,便于连续测试。
            // enabled 只按 connected 判,任务执行中也允许覆盖式发送(便于回归复测)。
            InputCard(
                enabled = connected,
                defaultText = DEFAULT_GOAL,
                onSend = onSendGoal,
            )

            SampleCard(
                enabled = connected,
                countdown = uiState.sampleCountdown,
                hint = uiState.sampleHint,
                onCapture = onCaptureSample,
            )

            if (uiState.debugUnlocked) {
                DebugPanel(debug = uiState.debug, onHide = onHideDebug)
            }
        }
    }
}

@Composable
private fun HeaderTitle(
    onTap: () -> Unit,
    taskState: TaskState,
) {
    val isRunning = taskState is TaskState.Running
    val pulseColor = if (isRunning) StatusColors.Pending else MaterialTheme.colorScheme.primary

    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            text = "JoyPhone",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(top = 2.dp),
        )
        if (isRunning) {
            Icon(
                imageVector = Icons.Default.Sync,
                contentDescription = null,
                modifier = Modifier
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(DoneGreen)
                    .padding(2.dp),
                tint = Color.White,
            )
        }
    }
}

@Composable
private fun AccessibilityCard(granted: Boolean, onOpen: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(
                    Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(if (granted) DoneGreen else FailedRed),
                )
                Text("无障碍服务", style = MaterialTheme.typography.titleMedium)
            }
            Text(
                if (granted) "已授权，可开始联调"
                   else "未授权，请先开启无障碍服务",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
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
        ConnectionState.CONNECTED    -> DoneGreen to "已连接"
        ConnectionState.CONNECTING    -> StatusColors.Pending to "连接中…"
        ConnectionState.RECONNECTING  -> StatusColors.Pending to "重连中…"
        ConnectionState.DISCONNECTED  -> FailedRed to "已断开"
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(Modifier.size(10.dp).clip(CircleShape).background(color))
            Column {
                Text("云端连接", style = MaterialTheme.typography.titleMedium)
                Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun TaskStatusCard(task: TaskState, onCancel: () -> Unit) {
    when (task) {
        is TaskState.Idle -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f)),
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("任务状态", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "空闲中 — 在下方输入你想完成的任务",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        is TaskState.Running -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFEFF6FF)),
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(
                            imageVector = Icons.Default.Sync,
                            contentDescription = null,
                            tint = SendBlue,
                            modifier = Modifier.size(18.dp),
                        )
                        Text("执行中", style = MaterialTheme.typography.titleMedium, color = SendBlue)
                    }
                    Text(
                        task.description,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                    // 中止按钮(2026-07-26 加):走协议 task.cancel → _terminate,
                    // 与发送框独立——发送框在任务执行中也可点(覆盖式发送),
                    // 中止按钮走 cancel 协议明确终止当前任务。
                    TextButton(
                        onClick = onCancel,
                        colors = ButtonDefaults.textButtonColors(contentColor = FailedRed),
                    ) {
                        Text("中止任务")
                    }
                }
            }
        }
        is TaskState.Done -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFF0FDF4)),
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(
                            imageVector = Icons.Default.CheckCircle,
                            contentDescription = null,
                            tint = DoneGreen,
                            modifier = Modifier.size(18.dp),
                        )
                        Text("已完成", style = MaterialTheme.typography.titleMedium, color = DoneGreen)
                    }
                    Text(task.summary, style = MaterialTheme.typography.bodyMedium, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    TextButton(onClick = onCancel) { Text("重新输入") }
                }
            }
        }
        is TaskState.Failed -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFEF2F2)),
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(
                            imageVector = Icons.Default.Error,
                            contentDescription = null,
                            tint = FailedRed,
                            modifier = Modifier.size(18.dp),
                        )
                        Text("执行失败", style = MaterialTheme.typography.titleMedium, color = FailedRed)
                    }
                    Text(task.reason, style = MaterialTheme.typography.bodyMedium, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    TextButton(onClick = onCancel) { Text("重新输入") }
                }
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
            Button(onClick = onCapture, enabled = enabled && !counting) {
                Text(if (counting) "倒计时 $countdown s…" else "开始采样(10s 后抓帧)")
            }
            if (hint.isNotBlank()) {
                Text(hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun InputCard(
    enabled: Boolean,
    defaultText: String,
    onSend: (String) -> Unit,
) {
    // remember 只在首次生效,后续文本由用户输入维持在 state,连续测试时不会被覆盖。
    var text by remember { mutableStateOf(defaultText) }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("发送任务", style = MaterialTheme.typography.titleMedium)

            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("你想让我做什么？") },
                enabled = enabled,
                minLines = 2,
                maxLines = 4,
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = SendBlue,
                    unfocusedBorderColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.6f),
                ),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(
                    onDone = {
                        val trimmed = text.trim()
                        if (trimmed.isNotEmpty() && enabled) {
                            onSend(trimmed)
                        }
                    },
                ),
            )

            Button(
                onClick = {
                    val trimmed = text.trim()
                    if (trimmed.isNotEmpty()) {
                        onSend(trimmed)
                    }
                },
                enabled = enabled && text.trim().isNotEmpty(),
                modifier = Modifier.align(Alignment.End),
                colors = ButtonDefaults.buttonColors(containerColor = SendBlue),
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.Send,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp),
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text("发送")
            }
        }
    }
}
