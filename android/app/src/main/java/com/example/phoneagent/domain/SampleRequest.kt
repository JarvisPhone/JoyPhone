package com.example.phoneagent.domain

/** UI 发给无障碍服务的采样请求信号:延时 delaySeconds 秒后抓当前帧,打上 label。 */
data class SampleRequest(
    val label: String,
    val delaySeconds: Int,
)