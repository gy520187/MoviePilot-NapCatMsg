import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from app.sdk.plugin import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.network import RequestUtils


class NapCatMsg(_PluginBase):
    # 插件名称
    plugin_name = "QQ消息通知（NapCat）"
    # 插件描述
    plugin_desc = "通过NapCat（OneBot11）接口，向QQ好友或群聊发送MoviePilot消息通知。"
    # 插件图标
    plugin_icon = "https://avatars.githubusercontent.com/NapNeko?v=4"
    # 插件版本，需与 package.v3.json 中保持一致
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "monkeycode"
    # 作者主页
    author_url = ""
    # 插件配置项ID前缀
    plugin_config_prefix = "napcatmsg_"
    # 加载顺序
    plugin_order = 28
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _onlyonce = False
    _host = None
    _token = None
    _send_users = None
    _send_groups = None
    _at_all = False
    _msgtypes = []

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._host = config.get("host")
            self._token = config.get("token")
            self._send_users = config.get("send_users")
            self._send_groups = config.get("send_groups")
            self._at_all = config.get("at_all")
            self._msgtypes = config.get("msgtypes") or []

        if self._onlyonce:
            logger.info("立即测试一次QQ消息发送")
            self._onlyonce = False
            self.update_config({
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "host": self._host,
                "token": self._token,
                "send_users": self._send_users,
                "send_groups": self._send_groups,
                "at_all": self._at_all,
                "msgtypes": self._msgtypes,
            })
            self._send("QQ消息通知测试", "NapCat消息通知插件已启用，收到本条消息即代表MoviePilot与NapCat对接成功。")

    def get_state(self) -> bool:
        return self._enabled and bool(self._host) and (
            bool(self._parse_ids(self._send_users)) or bool(self._parse_ids(self._send_groups))
        )

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # 遍历 NotificationType 枚举，生成消息类型选项
        MsgTypeOptions = []
        for item in NotificationType:
            MsgTypeOptions.append({
                "title": item.value,
                "value": item.name
            })
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '测试插件（立即运行）',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'host',
                                            'label': 'NapCat服务地址',
                                            'placeholder': 'http://napcat:3000',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'token',
                                            'label': 'AccessToken（可选）',
                                            'placeholder': '与NapCat网络配置中的Token一致',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'send_users',
                                            'label': 'QQ号（私聊）',
                                            'placeholder': '接收通知的QQ号，多个用英文逗号分隔',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'send_groups',
                                            'label': '群号（群聊）',
                                            'placeholder': '接收通知的群号，多个用英文逗号分隔',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'at_all',
                                            'label': '群消息@全体成员',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'model': 'msgtypes',
                                            'label': '消息类型（留空为全部发送）',
                                            'items': MsgTypeOptions
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "host": "http://napcat:3000",
            "token": "",
            "send_users": "",
            "send_groups": "",
            "at_all": False,
            "msgtypes": [],
        }

    def get_page(self) -> Optional[List[dict]]:
        pass

    @staticmethod
    def _parse_ids(ids: Optional[str]) -> List[int]:
        """
        解析逗号分隔的QQ号、群号字符串为ID列表
        """
        if not ids:
            return []
        result = []
        for item in str(ids).replace("，", ",").split(","):
            item = item.strip()
            if item.isdigit():
                result.append(int(item))
        return result

    def _send(self, title: str, text: str, image: Optional[str] = None) -> Optional[Tuple[bool, str]]:
        """
        通过NapCat的OneBot11 HTTP接口发送QQ消息
        :param title: 标题
        :param text: 内容
        :param image: 图片URL（可选）
        """
        if not self._host:
            return False, "NapCat服务地址未配置"

        # 组装发送目标：私聊、群聊
        targets = []
        for user_id in self._parse_ids(self._send_users):
            targets.append(("send_private_msg", {"user_id": user_id}, f"私聊[{user_id}]"))
        for group_id in self._parse_ids(self._send_groups):
            targets.append(("send_group_msg", {"group_id": group_id}, f"群聊[{group_id}]"))
        if not targets:
            return False, "未配置接收消息的QQ号或群号"

        # 组装消息段：文本、可选@全体成员、可选图片
        content = f"{title}\n{text}" if text else title
        segments = []
        if self._at_all:
            segments.append({"type": "at", "data": {"qq": "all"}})
        segments.append({"type": "text", "data": {"text": content}})
        if image:
            segments.append({"type": "image", "data": {"url": image}})

        # OneBot11 HTTP鉴权：同时支持Bearer请求头和access_token参数
        headers = None
        if self._token:
            headers = {"Authorization": f"Bearer {self._token}"}

        success = True
        message = ""
        for action, extra, target_desc in targets:
            url = f"{self._host.rstrip('/')}/{action}"
            if self._token:
                url = f"{url}?{urlencode({'access_token': self._token})}"
            payload = {"message": segments, **extra}
            try:
                res = RequestUtils(
                    content_type="application/json", headers=headers
                ).post_res(url, json=payload, allow_redirects=False)
                if res and res.status_code == 200:
                    try:
                        res_json = res.json()
                    except Exception:
                        res_json = {}
                    # OneBot11响应码：0为成功，1为异步发送成功
                    if res_json.get("retcode") in (0, 1):
                        logger.info(f"NapCat消息发送成功：{target_desc}，内容：{title}")
                    else:
                        success = False
                        message = f"{target_desc} 发送失败，接口返回：{json.dumps(res_json, ensure_ascii=False)}"
                        logger.warning(f"NapCat消息发送失败，{message}")
                elif res is not None:
                    success = False
                    message = f"{target_desc} 发送失败，HTTP错误码：{res.status_code}，错误原因：{res.reason}"
                    logger.warning(f"NapCat消息发送失败，{message}")
                else:
                    success = False
                    message = f"{target_desc} 发送失败：未获取到返回信息，请检查NapCat服务地址 {self._host} 是否可达"
                    logger.warning(f"NapCat消息发送失败，{message}")
            except Exception as e:
                success = False
                message = f"{target_desc} 发送异常：{str(e)}"
                logger.error(f"NapCat消息发送异常：{str(e)}")
        return success, message

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        """
        监听消息通知事件，转发到NapCat
        """
        if not self.get_state():
            return

        if not event.event_data:
            return

        msg_body = event.event_data
        # 已指定发送渠道的消息不再重复发送
        channel = msg_body.get("channel")
        if channel:
            return
        # 类型
        msg_type: NotificationType = msg_body.get("type")
        # 标题
        title = msg_body.get("title")
        # 文本
        text = msg_body.get("text")
        # 图片
        image = msg_body.get("image")

        if not title and not text:
            logger.warning("标题和内容不能同时为空")
            return

        if (msg_type and self._msgtypes
                and msg_type.name not in self._msgtypes):
            logger.info(f"消息类型 {msg_type.value} 未开启消息发送")
            return

        return self._send(title, text, image)

    def stop_service(self):
        """
        退出插件
        """
        pass
