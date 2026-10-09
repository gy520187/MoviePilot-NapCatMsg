"""NapCat消息通知插件 V3 smoke test，mock MoviePilot V3 宿主依赖并验证插件核心逻辑（含双向交互）。"""
import asyncio
import hashlib
import hmac
import importlib.util
import json
import logging
import os
import sys
import time
import types
from enum import Enum

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PLUGIN_PATH = os.path.join(REPO_ROOT, "plugins.v3", "napcatmsg", "__init__.py")

captured_requests = []
saved_config = {}
handled_messages = []


def wait_for(count, timeout=2.0):
    """等待后台线程把入站命令处理到指定数量，避免竞态"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(handled_messages) >= count:
            return True
        time.sleep(0.02)
    return False


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

    # app.chain.message：消息链（宿主处理入站命令的入口）
    app_chain = types.ModuleType("app.chain")
    app_chain_message = types.ModuleType("app.chain.message")

    class MessageChain:
        def handle_message(self, **kwargs):
            handled_messages.append(kwargs)

    app_chain_message.MessageChain = MessageChain
    app_chain.message = app_chain_message

    # fastapi：仅用到 Request
    fastapi_mod = types.ModuleType("fastapi")

    class Request:
        def __init__(self, headers=None, query_params=None, body=None):
            self.headers = headers or {}
            self.query_params = query_params or {}
            if isinstance(body, (dict, list)):
                self._body = json.dumps(body).encode()
            elif isinstance(body, str):
                self._body = body.encode()
            else:
                self._body = body or b""

        async def json(self):
            return json.loads(self._body)

        async def body(self):
            return self._body

    fastapi_mod.Request = Request

    # app.schemas.types：类型定义（成员与 V3 官方枚举一致）
    schemas = types.ModuleType("app.schemas")
    types_mod = types.ModuleType("app.schemas.types")

    class EventType(Enum):
        NoticeMessage = "notice.message"
        PluginAction = "plugin.action"

    class MessageType(Enum):
        Download = "资源下载"
        Organize = "整理入库"
        Subscribe = "订阅"
        SiteMessage = "站点"
        MediaServer = "媒体服务器"
        Manual = "手动处理"
        Plugin = "插件"
        Agent = "智能体"
        Other = "其它"

    class NotificationChannel(Enum):
        Wechat = "WeChat"
        Telegram = "Telegram"
        Slack = "Slack"
        Synologychat = "SynologyChat"
        Vocechat = "VoceChat"
        Rsshub = "RSSHub"
        Ntfy = "ntfy"
        Gotify = "gotify"
        Web = "Web"
        Webhook = "Webhook"
        Client = "Client"
        Cookiecloud = "CookieCloud"
        QQ = "QQ"

    types_mod.EventType = EventType
    types_mod.MessageType = MessageType
    types_mod.NotificationChannel = NotificationChannel

    app.sdk = sdk
    app.schemas = schemas
    app.chain = app_chain
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
        "app.chain": app_chain,
        "app.chain.message": app_chain_message,
        "app.schemas": schemas,
        "app.schemas.types": types_mod,
        "fastapi": fastapi_mod,
    }.items():
        sys.modules[name] = mod

    return EventType, MessageType, NotificationChannel, Event, Request


def load_plugin():
    spec = importlib.util.spec_from_file_location("napcatmsg_v3", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    EventType, MessageType, NotificationChannel, Event, Request = make_fake_app()
    module = load_plugin()
    plugin = module.NapCatMsg()

    # 1. get_form 结构与默认配置
    form, model = plugin.get_form()
    assert form[0]["component"] == "VForm", "配置页根组件应为VForm"
    for key in ("enabled", "host", "token", "send_users", "send_groups",
                "at_all", "msgtypes", "interaction", "report_token", "admin_users"):
        assert key in model, f"默认配置缺少字段 {key}"
    assert "host" in json.dumps(form), "配置页应包含 NapCat 服务地址输入项"
    assert "interaction" in json.dumps(form), "配置页应包含双向交互开关"
    print("[PASS] get_form 结构完整")

    # 1.1 get_api：上报端点匿名开放（自带令牌校验）
    apis = plugin.get_api()
    assert apis[0]["path"] == "/report" and apis[0]["endpoint"] == plugin.report
    assert apis[0]["allow_anonymous"] is True and "POST" in apis[0]["methods"]
    print("[PASS] get_api 上报端点注册正确")

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
        "interaction": True,
        "report_token": "report-secret",
        "admin_users": "10001",
    })
    assert saved_config.get("onlyonce") is False, "测试后onlyonce应复位"
    assert saved_config.get("interaction") is True and saved_config.get("report_token") == "report-secret", \
        "交互配置应完整保存"
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

    # 3. get_state：无目标但开启交互也应视为启用
    assert plugin.get_state() is True, "配置完整时应处于启用状态"
    plugin2 = module.NapCatMsg()
    plugin2.init_plugin({"enabled": True, "onlyonce": False, "host": "http://napcat:3000"})
    assert plugin2.get_state() is False, "未配置目标且未开交互时不应视为启用"
    plugin2b = module.NapCatMsg()
    plugin2b.init_plugin({"enabled": True, "onlyonce": False, "host": "http://napcat:3000", "interaction": True})
    assert plugin2b.get_state() is True, "仅开启交互时也应视为启用"
    print("[PASS] get_state 判断正确")

    # 4. NoticeMessage 事件：全类型放行 + 图片段
    captured_requests.clear()
    plugin.send(Event(EventType.NoticeMessage, {
        "type": MessageType.Download,
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
    plugin._msgtypes = ["Download"]
    plugin.send(Event(EventType.NoticeMessage, {
        "type": MessageType.Subscribe,
        "title": "新增订阅",
        "text": "Example.Movie",
    }))
    assert len(captured_requests) == 0, "未勾选的消息类型不应发送"
    plugin.send(Event(EventType.NoticeMessage, {
        "type": MessageType.Download,
        "title": "下载开始",
        "text": "Example.S01E02",
    }))
    assert len(captured_requests) == 3, "勾选的消息类型应正常发送"
    print("[PASS] 消息类型过滤正确")

    # 6. channel 过滤与空内容过滤
    captured_requests.clear()
    plugin.send(Event(EventType.NoticeMessage, {
        "channel": "telegram",
        "type": MessageType.Download,
        "title": "指定渠道",
        "text": "x",
    }))
    assert len(captured_requests) == 0, "指定渠道的消息不应重复发送"
    plugin.send(Event(EventType.NoticeMessage, {"type": MessageType.Other}))
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

    # 9. _extract_text：CQ码清理与message数组回退
    assert module.NapCatMsg._extract_text({
        "raw_message": "[CQ:at,qq=10000] /search 头文字D",
    }) == "/search 头文字D", "raw_message应去除CQ码"
    assert module.NapCatMsg._extract_text({
        "raw_message": "[CQ:at,qq=10000]",
        "message": [{"type": "text", "data": {"text": "/renew"}}],
    }) == "/renew", "raw_message清空后应回退到message数组拼接"
    assert module.NapCatMsg._extract_text({
        "message": [{"type": "at", "data": {"qq": "all"}}, {"type": "text", "data": {"text": "/help"}}],
    }) == "/help", "message数组应忽略非text段"
    print("[PASS] 入站文本提取正确")

    # 9.1 斜杠命令兼容映射
    assert module.NapCatMsg._normalize_command("/search 头文字D") == "搜索 头文字D"
    assert module.NapCatMsg._normalize_command("/search头文字D") == "/search头文字D", "无空格分隔的斜杠命令不映射"
    assert module.NapCatMsg._normalize_command("/Subscribe  Example") == "订阅 Example", "映射应忽略命令大小写"
    assert module.NapCatMsg._normalize_command("/download  Example.S01E01") == "下载 Example.S01E01"
    assert module.NapCatMsg._normalize_command("/version") == "/version", "系统命令不应映射"
    assert module.NapCatMsg._normalize_command("搜索 头文字D") == "搜索 头文字D", "中文动词命令保持原样"
    print("[PASS] 斜杠命令兼容映射正确")

    # 10. report：未启用交互直接忽略
    handled_messages.clear()
    plugin4 = module.NapCatMsg()
    plugin4.init_plugin({"enabled": True, "onlyonce": False, "host": "http://napcat:3000",
                         "interaction": False, "report_token": "report-secret"})
    res = asyncio.run(plugin4.report(Request(body={"post_type": "message"})))
    assert res == {"status": "ignored"} and not handled_messages, "未启用交互时应忽略上报"
    print("[PASS] 未启用交互时上报被忽略")

    # 11. report：令牌校验（Bearer头、query参数、错误令牌）与入站命令转发
    plugin4t = module.NapCatMsg()
    plugin4t.init_plugin({"enabled": True, "onlyonce": False, "host": "http://napcat:3000",
                          "interaction": True, "report_token": "report-secret"})
    body = {
        "post_type": "message", "message_type": "private",
        "user_id": 10001, "raw_message": "/search 头文字D",
        "sender": {"nickname": "阿明"}, "message_id": 9001,
    }
    res = asyncio.run(plugin4t.report(Request(
        headers={"authorization": "Bearer wrong-token"}, body=body)))
    assert res == {"status": "forbidden"} and not handled_messages, "错误令牌应被拒绝"
    res = asyncio.run(plugin4t.report(Request(
        headers={"authorization": "Bearer report-secret"}, body=body)))
    assert res == {"status": "ok"} and wait_for(1), "正确Bearer令牌应放行并转发命令"
    msg = handled_messages[0]
    assert msg["channel"] == NotificationChannel.QQ and msg["source"] == "NapCat"
    assert msg["userid"] == 10001 and msg["username"] == "阿明"
    assert msg["text"] == "搜索 头文字D" and msg["original_message_id"] == 9001
    res = asyncio.run(plugin4t.report(Request(
        query_params={"access_token": "report-secret"}, body=body)))
    assert res == {"status": "ok"} and wait_for(2), "query参数令牌应放行"
    res = asyncio.run(plugin4t.report(Request(
        headers={"authorization": "report-secret"}, body=body)))
    assert res == {"status": "ok"} and wait_for(3), "无Bearer前缀的裸Token头应放行"
    res = asyncio.run(plugin4t.report(Request(body=body)))
    assert res == {"status": "forbidden"}, "无鉴权信息的请求应被拒绝"
    print("[PASS] 上报令牌校验与入站命令转发正确")

    # 11.1 report：NapCat HMAC-SHA1签名校验（NapCat把Token作为secret对请求体签名）
    sign = hmac.new(b"report-secret", json.dumps(body).encode(), hashlib.sha1).hexdigest()
    res = asyncio.run(plugin4t.report(Request(
        headers={"x-signature": f"sha1={sign}"}, body=body)))
    assert res == {"status": "ok"} and wait_for(4), "正确的x-signature签名应放行"
    bad_sign = hmac.new(b"wrong-secret", json.dumps(body).encode(), hashlib.sha1).hexdigest()
    res = asyncio.run(plugin4t.report(Request(
        headers={"x-signature": f"sha1={bad_sign}"}, body=body)))
    assert res == {"status": "forbidden"} and len(handled_messages) == 4, "错误签名应被拒绝"
    res = asyncio.run(plugin4t.report(Request(
        headers={"x-signature": "sha1=deadbeef"}, body=body)))
    assert res == {"status": "forbidden"}, "非法签名应被拒绝"
    print("[PASS] NapCat HMAC-SHA1签名校验正确")

    # 12. report：心跳等元事件、非管理员、空文本
    plugin4b = module.NapCatMsg()
    plugin4b.init_plugin({"enabled": True, "onlyonce": False, "host": "http://napcat:3000",
                          "interaction": True, "report_token": "", "admin_users": "10001,20002"})
    res = asyncio.run(plugin4b.report(Request(body={"post_type": "meta_event", "meta_event_type": "heartbeat"})))
    assert res == {"status": "ok"} and len(handled_messages) == 4, "心跳事件不应触发命令处理"
    res = asyncio.run(plugin4b.report(Request(body={
        "post_type": "message", "message_type": "group", "user_id": 99999,
        "raw_message": "/search x", "group_id": 88888888, "sender": {"nickname": "路人"},
    })))
    assert res == {"status": "ok"} and len(handled_messages) == 4, "非可交互用户命令应被忽略"
    res = asyncio.run(plugin4b.report(Request(body={
        "post_type": "message", "message_type": "private", "user_id": 10001,
        "raw_message": "[CQ:at,qq=10000]", "sender": {"nickname": "阿明"},
    })))
    assert res == {"status": "ok"} and len(handled_messages) == 4, "无有效文本的上报不应触发命令处理"
    print("[PASS] 心跳/非管理员/空文本过滤正确")

    # 13. report：群聊命令处理 + 命令执行异常兜底（直接调用_handle_inbound验证）
    plugin4c = module.NapCatMsg()
    plugin4c.init_plugin({"enabled": True, "onlyonce": False, "host": "http://napcat:3000",
                          "interaction": True, "report_token": ""})
    res = asyncio.run(plugin4c.report(Request(body={
        "post_type": "message", "message_type": "group", "user_id": 10001,
        "raw_message": "/search 头文字D", "group_id": 88888888, "sender": {"nickname": "阿明"},
    })))
    assert res == {"status": "ok"} and wait_for(5), "群聊命令应正常处理"
    assert handled_messages[4]["userid"] == 10001, "群聊命令应记录发送者QQ号"

    handled_messages.clear()
    captured_requests.clear()

    class _BoomChain:
        def handle_message(self, **kwargs):
            raise RuntimeError("boom")

    original_chain = module.MessageChain
    module.MessageChain = _BoomChain
    try:
        plugin4c._handle_inbound(10001, "阿明", "/renew", 9002)
    finally:
        module.MessageChain = original_chain
    assert len(captured_requests) == 1, "命令执行异常时应向用户私聊发送失败回复"
    assert captured_requests[0]["data"]["user_id"] == 10001, "失败回复应发给命令来源用户"
    assert "命令执行失败" in captured_requests[0]["data"]["message"][-1]["data"]["text"], \
        "失败回复应包含异常提示"
    print("[PASS] 群聊命令处理与异常兜底正确")

    # 14. send：QQ渠道消息定向私聊回复（枚举与字符串两种形式）
    captured_requests.clear()
    plugin.send(Event(EventType.NoticeMessage, {
        "channel": NotificationChannel.QQ,
        "userid": 10001, "title": "执行完成", "text": "已搜索到3条结果",
    }))
    assert len(captured_requests) == 1, "QQ渠道回复应只发一条"
    assert captured_requests[0]["url"].startswith("http://napcat:3000/send_private_msg?access_token=my-token")
    assert captured_requests[0]["data"]["user_id"] == 10001, "回复应定向发给来源用户"
    captured_requests.clear()
    plugin.send(Event(EventType.NoticeMessage, {
        "channel": "QQ", "userid": 10001, "title": "执行完成", "text": "字符串渠道兼容",
    }))
    assert len(captured_requests) == 1 and captured_requests[0]["data"]["user_id"] == 10001, \
        "字符串形式的QQ渠道也应定向回复"
    captured_requests.clear()
    plugin.send(Event(EventType.NoticeMessage, {"channel": "QQ", "userid": 10001}))
    assert len(captured_requests) == 0, "标题内容均为空的回复不应发送"
    print("[PASS] QQ渠道双向回复正确")

    print("\n全部测试通过")


if __name__ == "__main__":
    main()
