# User Instruction Memory

This file records user instructions, preferences, and teachings for reference in future interactions.

## Format

### User Instruction Entry
User instruction entries should follow this format:

[User Instruction Summary]
- Date: [YYYY-MM-DD]
- Context: [Mentioned scenario or time]
- Instructions:
  - [Content of user teaching or instruction, described line by line]

### Project Knowledge Entry
Entries discovered by the Agent during task execution should follow this format:

[Project Knowledge Summary]
- Date: [YYYY-MM-DD]
- Context: Discovered by Agent while performing [specific task description]
- Category: [Operations & Deployment|Build Methods|Testing Methods|Troubleshooting & Debugging|Workflow & Collaboration|Environment Configuration]
- Instructions:
  - [Specific knowledge points, described line by line]

## Deduplication Strategy
- Before adding a new entry, check for similar or identical instructions.
- If a duplicate is found, skip the new entry or merge it with the existing one.
- When merging, update the context or date information.
- This helps avoid redundant entries and keeps the memory file tidy.

## Entries

[Project Knowledge Summary]
- Date: 2026-10-10
- Context: Discovered by Agent while implementing napcat-full-takeover（分析 MoviePilot v3 分支源码）
- Category: Build Methods
- Instructions:
  - MoviePilot v3 每条通知有两条分发路径：先广播 EventType.NoticeMessage 事件（数据为 Message.model_dump 字典，含 targets），再经消息队列调用 run_module("post_message") 模块分发；post_medias_message/post_torrents_message 仅走模块分发
  - 模块分发会调用所有实现同名方法的模块（内置+插件 get_module()），各模块自行按渠道过滤；插件 get_module() 仅在 get_state() 为真时被聚合注册
  - 用户通知设置绑定渠道后，按用户路由的通知通过 Message.targets 字典传递目标（QQ 官方机器人键：qq_userid/qq_openid/qq_group_openid/qq_group），channel 保持为空；notification_route_scope 是私有属性，事件数据不含
  - 插件测试命令：python3 tests/v3/napcatmsg/test_plugin.py（自建 mock 宿主的 smoke test，直接运行即可）
  - 插件版本需同步保持 plugins.v3/napcatmsg/__init__.py 的 plugin_version 与 package.v3.json 的 version 一致
