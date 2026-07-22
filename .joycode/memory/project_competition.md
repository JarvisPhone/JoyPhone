---
name: JoyPhone 代码开发大赛答辩定位
description: 'JoyPhone 参加集团代码开发大赛的赛道/阶段/评审导向,以及答辩叙事的关键约束'
type: project
---

JoyPhone 报名"AI 产品孵化"赛道,当前处于**海选(初试)阶段**,答辩形式为 2 分钟讲解 + 3 分钟提问(严格控时,超时打断)。

**Why:** 只有通过海选才能继续参加后续代码开发大赛环节。

**How to apply:**
- 海选阶段评审**只看创意,不看代码实现**——答辩要讲"我们打算怎么做"的愿景蓝图,不要纠结当前 Demo 跑通了多少、SDK 是否已真正集成。用户明确指示:"不用说我们做了什么,而要说我们打算怎么做"。
- vivo 企业 SDK 在 Android 源码中**尚未真正集成**(仅 sdk/vivo_sdk.md 文档规划),但按赛题要求"用 SDK 做",答辩需按设计意图大胆讲 SDK 的合规护城河角色,无需澄清"还没集成"。
- 无障碍 vs SDK 分工定调:无障碍(AccessibilityService)= 通用"手和眼"(读屏+执行);vivo 企业 SDK = 企业级"底座/保镖"(强制开启无障碍且用户不可关闭 setAccessibilityServcie/setPermittedAccessibilityServices、设备管理器 setVivoAdmin 实现不可卸载/常驻保活/白名单联网)。
- 项目定位见 docs/competition/ 赛题原文:项目名"JoyPhone·AI工作手机",slogan"让AI像人一样用手机,用得越多,越懂业务",落地场景=客服通知/营销推广/逾期催收的合规批量触达。