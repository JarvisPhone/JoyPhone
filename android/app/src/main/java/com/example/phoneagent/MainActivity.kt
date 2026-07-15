package com.example.phoneagent

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.phoneagent.ui.AgentScreen
import com.example.phoneagent.ui.MainViewModel
import com.example.phoneagent.ui.theme.JoyPhoneTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            JoyPhoneTheme {
                val uiState by viewModel.uiState.collectAsStateWithLifecycle()
                AgentScreen(
                    uiState = uiState,
                    onTitleTap = viewModel::onTitleTap,
                    onOpenAccessibility = { openAccessibilitySettings() },
                    onRunTestTask = viewModel::onRunTestTask,
                    onHideDebug = viewModel::onHideDebug,
                )
            }
        }
    }

    private fun openAccessibilitySettings() {
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }
}