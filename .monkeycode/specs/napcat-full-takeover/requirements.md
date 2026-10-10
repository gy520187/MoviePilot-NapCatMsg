# Requirements Document - NapCat 完整接管 MoviePilot 消息

Feature Name: napcat-full-takeover
Updated: 2026-10-10
Status: CONFIRMED（用户已确认：模块化接管方案、支持用户级目标绑定、仅做 V3）

## Introduction

现有 NapCatMsg 插件（V3 v1.1.5）通过监听 `NoticeMessage` 事件实现单向通知广播，通过 `/report` 端点实现双向交互，并通过模块方法拦截 QQ 渠道的媒体/种子候选列表。

经源码分析（MoviePilot v3 分支 `app/chain/_messaging.py`），V3 宿主的通知分发存在两条并行路径：

1. **事件广播路径**：每条通知先广播 `EventType.NoticeMessage` 事件（插件当前仅使用此路径）
2. **模块分发路径**：随后经消息队列调用 `run_module("post_message", ...)`，所有实现了该方法的模块（内置 Telegram/微信/官方QQ机器人模块、插件模块方法）均会收到，由各模块自行按渠道过滤

当前插件缺失 `post_message` 模块方法，channel=QQ 的定向消息完全依赖事件广播路径。"完整接管"目标：让 NapCat 成为 MoviePilot V3 中 QQ 渠道的完整实现，覆盖所有出站消息路径，并消除双通道重复发送。

## Glossary

- **NapCat**：基于 NTQQ 的 OneBot 11 协议端，提供 HTTP API 收发 QQ 消息
- **NoticeMessage 事件**：宿主每条通知都会广播的事件，携带 type/title/text/image/channel/userid
- **模块分发**：宿主经消息队列调用各模块同名方法（post_message/post_medias_message/post_torrents_message）的机制
- **通知路由范围（route_scope）**：admin（管理员）/ user（绑定目标的用户）/ all（广播）
- **通知目标键**：用户通知设置中绑定渠道目标的字段名，官方 QQ 机器人模块使用 qq_userid/qq_openid/qq_group_openid/qq_group
- **msgtypes 过滤**：插件配置中的消息类型开关

## Requirements

### R1. QQ 渠道模块化接管（V3）

**User Story:** 作为 MoviePilot V3 用户，我希望插件声明 `post_message` 模块方法接管 QQ 渠道定向消息，使交互回复与按用户路由的通知经 NapCat 直达 QQ。

#### Acceptance Criteria

1. WHEN 宿主以模块分发方式投递 channel=QQ 的消息，插件 SHALL 通过 NapCat 将消息发送到消息指定的目标（message.userid，或用户绑定目标键中的 QQ 号/群号）
2. WHEN 模块分发的消息渠道为其他渠道，插件 SHALL 跳过处理
3. WHEN 模块分发的消息未指定渠道且 targets 不含 QQ 目标键，插件 SHALL 跳过处理（由事件广播路径负责，保持现有广播行为）
4. WHEN 消息带明确渠道标记（channel=QQ），NoticeMessage 事件处理 SHALL 忽略该消息（由模块分发路径负责，避免重复发送）
5. WHEN 消息未指定渠道但 targets 含 QQ 目标键（用户/管理员绑定通知），NoticeMessage 事件处理 SHALL 忽略该消息（由模块分发路径负责定向发送，避免向全部目标广播）

### R2. 用户通知目标绑定（V3）

**User Story:** 作为多用户 MoviePilot 的管理员，我希望用户在「通知设置」中绑定 QQ 目标后，按用户路由的通知定向送达该用户的 QQ。

#### Acceptance Criteria

1. WHEN 消息 targets 携带 qq_userid 或 qq_openid 目标键，插件 SHALL 通过 send_private_msg 定向发送
2. WHEN 消息 targets 携带 qq_group 或 qq_group_openid 目标键，插件 SHALL 通过 send_group_msg 定向发送
3. IF 消息同时含私聊与群聊目标键，插件 SHALL 向全部解析出的目标发送
4. IF targets 不含任何 QQ 目标键且消息未指定 userid，插件 SHALL 按事件广播路径的现有行为回落到插件配置的 QQ 号/群号

### R3. 广播通知（现有行为保持）

**User Story:** 作为单用户 MoviePilot 的管理员，我希望所有未指定渠道的通知按插件配置的 QQ 号/群号广播。

#### Acceptance Criteria

1. WHEN 未指定渠道的通知到达，插件 SHALL 按消息类型过滤后发送到配置的全部私聊与群聊目标
2. IF 消息类型未在 msgtypes 开关中启用，插件 SHALL 跳过该消息

### R4. 入站交互完整接管（现有能力巩固）

**User Story:** 作为 MoviePilot 用户，我希望在 QQ 中完成搜索、选择、下载等全部交互，所有回复经 NapCat 私聊返回。

#### Acceptance Criteria

1. WHEN QQ 用户发送文本命令，插件 SHALL 校验可交互名单后转交宿主消息链（现有行为）
2. WHEN 宿主向 QQ 渠道回复候选列表，插件 SHALL 文本化后私聊回复发起交互的用户（现有行为）
3. WHEN 上报令牌校验失败，插件 SHALL 拒绝请求并记录鉴权形式日志（现有行为）

## Confirmed Decisions

1. 采纳「模块化接管」方案：插件声明 `post_message` 模块方法处理 channel=QQ 定向消息；事件广播路径只处理无渠道消息；两条路径互补且不重复。
2. 支持用户级通知目标绑定：与官方 QQ 机器人模块的目标键对齐（qq_userid/qq_openid/qq_group_openid/qq_group），未绑定 QQ 目标时回落插件全局配置目标。
3. 仅增强 V3 插件；V2 插件保持现状（单向通知）。
