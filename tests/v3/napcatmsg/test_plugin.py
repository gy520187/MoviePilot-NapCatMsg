"""NapCat消息通知插件 V3 smoke test，mock MoviePilot V3 宿主依赖并验证插件核心逻辑。"""
import importlib.util
import json
import logging
import os
import sys
import types
from enum import Enum

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PLUGIN_PATH = os.path.join(REPO_ROOT, "plugins.v3", "napcatmsg", "__init__.py")

captured_requests = []
saved_config = {}


# ---------- 构造假 MoviePilot V3 宿主模块 ----------

def make_fake_app():
    app = types.ModuleType("app")
    sdk = types.ModuleType("app.sdk")

    # app.sdk.plugin：插件基类
    sdk_plugin = types.ModuleType("app.sdk.plugin")

    class _PluginBase:
        def update_config(self, config):
            saved_config.update(config)

        def get_config(self):
            return dict(saved_config)

    sdk_plugin._PluginBase = _PluginBase

    # app.sdk.events：事件定义与事件管理器
    sdk_events = types.ModuleType("app.sdk.events")

    class Event:
        def __init__(self, event_type=None, event_data=None):
            self.event_type = event_type
            self.event_data = event_data

    class EventManager:
        def register(self, event_type):
            def decorator(func):
                return func
            return decorator

    sdk_events.eventmanager = EventManager()
    sdk_events.Event = Event

    # app.sdk.logging：日志
    sdk_logging = types.ModuleType("app.sdk.logging")
    logging.basicConfig(level=logging.DEBUG)
    sdk_logging.logger = logging.getLogger("test")

    # app.sdk.network：同步HTTP工具
    sdk_network = types.ModuleType("app.sdk.network")

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self.reason = "OK"
            self._payload = payload if payload is not None else {"status": "ok", "retcode": 0}

        def json(self):
            return self._payload

    class RequestUtils:
        def __init__(self, headers=None, content_type=None, **kwargs):
            self.headers = headers or {}
            self.content_type = content_type

        def post_res(self, url, json=None, **kwargs):
            captured_requests.append({
                "url": url,
                "headers": {**self.headers, "Content-Type": self.content_type},
                "data": json,
            })
            return FakeResponse()

    sdk_network.RequestUtils = RequestUtils

    # app.schemas.types：类型定义
    schemas = types.ModuleType("app.schemas")
    types_mod = types.ModuleType("app.schemas.types")

    class EventType(Enum):
        NoticeMessage = "notice.message"
        PluginAction = "plugin.action"

    class NotificationType(Enum):
        UserMessage = "用户消息"
        SubscribeAdded = "新增订阅"
        DownloadAdded = "新增下载"
        OrganizeCompleted = "整理完成"

    types_mod.EventType = EventType
    types_mod.NotificationType = NotificationType

    app.sdk = sdk
    app.schemas = schemas
    sdk.plugin = sdk_plugin
    sdk.events = sdk_events
    sdk.logging = sdk_logging
    sdk.network = sdk_network
    schemas.types = types_mod

    for name, mod in {
        "app": app,
        "app.sdk": sdk,
        "app.sdk.plugin": sdk_plugin,
        "app.sdk.events": sdk_events,
        "app.sdk.logging": sdk_logging,
        "app.sdk.network": sdk_network,
        "app.schemas": schemas,
        "app.schemas.types": types_mod,
    }.items():
        sys.modules[name] = mod

    return EventType, NotificationType, Event


def load_plugin():
    spec = importlib.util.spec_from_file_location("napcatmsg_v3", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    EventType, NotificationType, Event = make_fake_app()
    module = load_plugin()
    plugin = module.NapCatMsg()

    # 1. get_form 结构与默认配置
    form, model = plugin.get_form()
    assert form[0]["component"] == "VForm", "配置页根组件应为VForm"
    for key in ("enabled", "host", "token", "send_users", "send_groups", "at_all", "msgtypes"):
        assert key in model, f"默认配置缺少字段 {key}"
    assert "host" in json.dumps(form), "配置页应包含 NapCat 服务地址输入项"
    print("[PASS] get_form 结构完整")

    # 2. init_plugin + onlyonce 立即测试：验证 URL、鉴权、payload
    captured_requests.clear()
    saved_config.clear()
    plugin.init_plugin({
        "enabled": True,
        "onlyonce": True,
        "host": "http://napcat:3000/",
        "token": "my-token",
        "send_users": "10001, 20002",
        "send_groups": "88888888",
        "at_all": True,
        "msgtypes": [],
    })
    assert saved_config.get("onlyonce") is False, "测试后onlyonce应复位"
    assert len(captured_requests) == 3, f"应发送3条消息（2私聊+1群聊），实际{len(captured_requests)}"

    req = captured_requests[0]
    assert req["url"].startswith("http://napcat:3000/send_private_msg?access_token=my-token"), \
        f"私聊URL拼接错误: {req['url']}"
    assert req["headers"].get("Authorization") == "Bearer my-token", "应携带Bearer鉴权头"
    assert req["headers"].get("Content-Type") == "application/json", "应为JSON请求"
    assert req["data"]["user_id"] == 10001, "第一个私聊目标应为10001"
    assert "QQ消息通知测试" in req["data"]["message"][-1]["data"]["text"], "消息正文应包含标题"

    group_req = captured_requests[2]
    assert group_req["url"].startswith("http://napcat:3000/send_group_msg?access_token=my-token"), \
        f"群聊URL拼接错误: {group_req['url']}"
    assert group_req["data"]["group_id"] == 88888888, "群聊目标应为88888888"
    assert group_req["data"]["message"][0]["type"] == "at", "at_all开启时群消息应携带@全体段"
    print("[PASS] init_plugin 立即测试：URL、鉴权、payload、@全体 正确")

    # 3. get_state
    assert plugin.get_state() is True, "配置完整时应处于启用状态"
    plugin2 = module.NapCatMsg()
    plugin2.init_plugin({"enabled": True, "onlyonce": False, "host": "http://napcat:3000"})
    assert plugin2.get_state() is False, "未配置目标时不应视为启用"
    print("[PASS] get_state 判断正确")

    # 4. NoticeMessage 事件：全类型放行 + 图片段
    captured_requests.clear()
    plugin.send(Event(EventType.NoticeMessage, {
        "type": NotificationType.DownloadAdded,
        "title": "下载开始",
        "text": "Example.S01E01",
        "image": "https://example.com/poster.jpg",
    }))
    assert len(captured_requests) == 3, "未过滤消息类型时应全量发送"
    assert captured_requests[0]["data"]["user_id"] == 10001
    last_segment = captured_requests[0]["data"]["message"][-1]
    assert last_segment["type"] == "image" and last_segment["data"]["url"] == "https://example.com/poster.jpg", \
        "事件携带图片时应附加图片消息段"
    print("[PASS] NoticeMessage 事件转发与图片消息段正确")

    # 5. 消息类型过滤：未勾选的类型不发
    captured_requests.clear()
    plugin._msgtypes = ["DownloadAdded"]
    plugin.send(Event(EventType.NoticeMessage, {
        "type": NotificationType.SubscribeAdded,
        "title": "新增订阅",
        "text": "Example.Movie",
    }))
    assert len(captured_requests) == 0, "未勾选的消息类型不应发送"
    plugin.send(Event(EventType.NoticeMessage, {
        "type": NotificationType.DownloadAdded,
        "title": "下载开始",
        "text": "Example.S01E02",
    }))
    assert len(captured_requests) == 3, "勾选的消息类型应正常发送"
    print("[PASS] 消息类型过滤正确")

    # 6. channel 过滤与空内容过滤
    captured_requests.clear()
    plugin.send(Event(EventType.NoticeMessage, {
        "channel": "telegram",
        "type": NotificationType.DownloadAdded,
        "title": "指定渠道",
        "text": "x",
    }))
    assert len(captured_requests) == 0, "指定渠道的消息不应重复发送"
    plugin.send(Event(EventType.NoticeMessage, {"type": NotificationType.UserMessage}))
    print("[PASS] channel 与空内容过滤正确")

    # 7. 中文/全角逗号解析与非法输入
    assert module.NapCatMsg._parse_ids(" 111,，222，abc,,333 ") == [111, 222, 333], "ID解析应兼容全角逗号并过滤非法值"
    print("[PASS] ID解析正确")

    # 8. 无token场景URL
    captured_requests.clear()
    saved_config.clear()
    plugin3 = module.NapCatMsg()
    plugin3.init_plugin({
        "enabled": True, "onlyonce": False, "host": "http://napcat:3000",
        "token": "", "send_users": "10001", "send_groups": "",
    })
    plugin3._send("标题", "内容")
    assert captured_requests[0]["url"] == "http://napcat:3000/send_private_msg", "无token时URL不应带access_token"
    assert "access_token" not in captured_requests[0]["url"]
    print("[PASS] 无token场景URL正确")

    print("\n全部测试通过")


if __name__ == "__main__":
    main()
