import hashlib
import hmac
import json
import re
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi import Request

from app.chain.message import MessageChain
from app.sdk.plugin import _PluginBase
from app.schemas.types import EventType, MessageType, NotificationChannel
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.network import RequestUtils


class NapCatMsg(_PluginBase):
    # 插件名称
    plugin_name = "QQ消息通知（NapCat）"
    # 插件描述
    plugin_desc = "通过NapCat（OneBot11）接口与QQ双向交互：向好友或群聊发送通知，并接收QQ消息作为远程命令控制MoviePilot。"
    # 插件图标
    plugin_icon = "https://avatars.githubusercontent.com/NapNeko?v=4"
    # 插件版本，需与 package.v3.json 中保持一致
    plugin_version = "1.1.4"
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
    _interaction = False
    _report_token = None
    _admin_users = None

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
            self._interaction = config.get("interaction")
            self._report_token = config.get("report_token")
            self._admin_users = config.get("admin_users")

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
                "interaction": self._interaction,
                "report_token": self._report_token,
                "admin_users": self._admin_users,
            })
            self._send("QQ消息通知测试", "NapCat消息通知插件已启用，收到本条消息即代表MoviePilot与NapCat对接成功。")

    def get_state(self) -> bool:
        return bool(self._enabled and self._host and (
            self._parse_ids(self._send_users)
            or self._parse_ids(self._send_groups)
            or self._interaction
        ))

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册NapCat OneBot11 HTTP上报接收端点，外部回调接口使用独立令牌校验
        """
        return [
            {
                "path": "/report",
                "endpoint": self.report,
                "methods": ["POST"],
                "auth": "apikey",
                "allow_anonymous": True,
                "summary": "NapCat消息上报",
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # 遍历 MessageType 枚举，生成消息类型选项
        MsgTypeOptions = []
        for item in MessageType:
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
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'interaction',
                                            'label': '启用双向交互（接收QQ消息执行远程命令）',
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
                                            'model': 'report_token',
                                            'label': '上报令牌（可选）',
                                            'placeholder': '与NapCat HTTP上报配置中的Token一致',
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
                                            'model': 'admin_users',
                                            'label': '可交互QQ号（留空允许全部）',
                                            'placeholder': '允许发送命令的QQ号，多个用英文逗号分隔',
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
            "interaction": False,
            "report_token": "",
            "admin_users": "",
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

    # OneBot11 CQ码（如@通知）正则，用于提取纯文本命令
    _CQ_CODE_RE = re.compile(r"\[CQ:[^\]]+\]")

    @staticmethod
    def _extract_text(body: dict) -> Optional[str]:
        """
        从OneBot11消息事件中提取文本内容
        """
        raw = body.get("raw_message")
        if isinstance(raw, str) and raw.strip():
            # 去除@通知等CQ码，仅保留有效文本
            text = NapCatMsg._CQ_CODE_RE.sub("", raw).strip()
            if text:
                return text
        # 回退：拼接message数组中的文本段
        segments = body.get("message")
        parts = []
        if isinstance(segments, list):
            for seg in segments:
                if isinstance(seg, dict) and seg.get("type") == "text":
                    text = seg.get("data", {}).get("text")
                    if text:
                        parts.append(str(text))
        if parts:
            return "".join(parts).strip()
        return None

    def _verify_report_token(self, request: Request, body_bytes: bytes = b"") -> bool:
        """
        校验NapCat上报请求的令牌；未配置上报令牌时放行
        支持三种形式：HMAC-SHA1签名（NapCat HTTP上报实际行为）、
        Authorization请求头（Bearer前缀或裸Token）、URL的token/access_token参数
        """
        expected = (self._report_token or "").strip()
        if not expected:
            return True
        # OneBot11标准HMAC-SHA1签名：NapCat把上报Token作为secret对请求体签名，
        # 放在x-signature头（sha1=前缀），与go-cqhttp的secret行为一致
        sign_header = (request.headers.get("x-signature") or "").strip()
        if sign_header.lower().startswith("sha1=") and body_bytes:
            sign_hex = sign_header[5:].strip().lower()
            expected_sign = hmac.new(
                expected.encode("utf-8"), body_bytes, hashlib.sha1).hexdigest()
            if sign_hex and hmac.compare_digest(sign_hex, expected_sign):
                return True
        # 兼容其他协议端：Authorization: Bearer <token>
        auth_header = request.headers.get("authorization") or ""
        if auth_header.startswith("Bearer ") and hmac.compare_digest(
                auth_header[7:].strip(), expected):
            return True
        # 兼容无Bearer前缀的裸Token请求头（部分协议端实现）
        if auth_header and " " not in auth_header.strip() and hmac.compare_digest(
                auth_header.strip(), expected):
            return True
        # 兼容URL携带token / access_token参数
        for key in ("token", "access_token"):
            value = request.query_params.get(key)
            if value and hmac.compare_digest(value, expected):
                return True
        return False

    def _describe_request_auth(self, request: Request) -> str:
        """
        描述上报请求携带的鉴权形式（不输出令牌值），用于鉴权失败排障
        """
        sign_header = (request.headers.get("x-signature") or "").strip()
        if sign_header:
            return "x-signature签名头"
        auth_header = (request.headers.get("authorization") or "").strip()
        if auth_header.startswith("Bearer "):
            return "Authorization: Bearer头"
        if auth_header:
            return "裸Authorization头"
        for key in ("token", "access_token"):
            if request.query_params.get(key):
                return f"URL参数{key}"
        return "无鉴权信息"

    def _is_admin_user(self, user_id: Any) -> bool:
        """
        判断QQ用户是否允许执行交互命令
        """
        admins = self._parse_ids(self._admin_users)
        if not admins:
            return True
        try:
            return int(user_id) in admins
        except (TypeError, ValueError):
            return False

    async def report(self, request: Request) -> Dict[str, Any]:
        """
        接收NapCat OneBot11 HTTP上报消息，转发给MoviePilot消息链处理
        """
        if not self.get_state() or not self._interaction:
            return {"status": "ignored"}
        try:
            body_bytes = await request.body()
        except Exception:
            body_bytes = b""
        if not self._verify_report_token(request, body_bytes):
            logger.warning(
                f"NapCat消息上报鉴权失败：请求携带{self._describe_request_auth(request)}，"
                "请确认NapCat「HTTP上报」配置中的Token与插件「上报令牌」完全一致，或将NapCat侧Token留空并在插件侧也清空上报令牌")
            return {"status": "forbidden"}
        try:
            body = json.loads(body_bytes) if body_bytes else None
        except Exception:
            return {"status": "bad_request"}
        if not isinstance(body, dict) or body.get("post_type") != "message":
            # 心跳、元事件等直接忽略
            return {"status": "ok"}

        message_type = body.get("message_type")
        user_id = body.get("user_id")
        text = self._extract_text(body)
        if not user_id or not text:
            return {"status": "ok"}
        if not self._is_admin_user(user_id):
            logger.info(f"QQ用户 {user_id} 不在可交互名单中，已忽略命令：{text[:20]}")
            return {"status": "ok"}

        sender = (body.get("sender") or {}).get("nickname") or str(user_id)
        # 群聊消息在文本前附加群标识，便于日志追踪；回复仍走私聊
        if message_type == "group":
            group_id = body.get("group_id")
            logger.info(f"收到QQ群[{group_id}]用户[{user_id}]命令：{text[:50]}")
        else:
            logger.info(f"收到QQ私聊用户[{user_id}]命令：{text[:50]}")

        # 插件仅负责消息转发，命令的识别与执行由MoviePilot消息链完成
        thread = threading.Thread(
            target=self._handle_inbound,
            args=(user_id, sender, text, body.get("message_id")),
            daemon=True,
        )
        thread.start()
        return {"status": "ok"}

    def _handle_inbound(self, userid: Any, username: str, text: str, message_id: Any = None):
        """
        后台调用MoviePilot消息链处理入站命令
        """
        try:
            MessageChain().handle_message(
                channel=NotificationChannel.QQ,
                source="NapCat",
                userid=userid,
                username=username,
                text=text,
                original_message_id=message_id,
            )
        except Exception as e:
            logger.error(f"处理QQ消息命令异常：{str(e)}")
            self._send_reply("命令执行失败", f"处理命令时出现异常：{str(e)[:200]}", userid)

    def _build_targets(self) -> List[Tuple[str, Dict[str, Any], str]]:
        """
        根据配置组装广播发送目标：私聊、群聊
        """
        targets = []
        for user_id in self._parse_ids(self._send_users):
            targets.append(("send_private_msg", {"user_id": user_id}, f"私聊[{user_id}]"))
        for group_id in self._parse_ids(self._send_groups):
            targets.append(("send_group_msg", {"group_id": group_id}, f"群聊[{group_id}]"))
        return targets

    def _send(self, title: str, text: str, image: Optional[str] = None) -> Optional[Tuple[bool, str]]:
        """
        通过NapCat的OneBot11 HTTP接口向配置的所有目标发送广播消息
        :param title: 标题
        :param text: 内容
        :param image: 图片URL（可选）
        """
        if not self._host:
            return False, "NapCat服务地址未配置"
        targets = self._build_targets()
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
        return self._post_onebot(targets, segments, title)

    def _send_reply(self, title: str, text: str, userid: Any, image: Optional[str] = None) -> Optional[Tuple[bool, str]]:
        """
        向单个QQ用户私聊发送交互回复
        :param title: 标题
        :param text: 内容
        :param userid: 回复目标QQ号
        :param image: 图片URL（可选）
        """
        if not self._host:
            return False, "NapCat服务地址未配置"
        try:
            target_user = int(userid)
        except (TypeError, ValueError):
            logger.warning(f"交互回复用户ID无效：{userid}")
            return False, "无效用户ID"
        content = f"{title}\n{text}" if text else title
        segments = [{"type": "text", "data": {"text": content}}]
        if image:
            segments.append({"type": "image", "data": {"url": image}})
        return self._post_onebot(
            [("send_private_msg", {"user_id": target_user}, f"私聊[{target_user}]")],
            segments, title)

    def _post_onebot(self, targets: List[Tuple[str, Dict[str, Any], str]],
                     segments: List[dict], title: str) -> Tuple[bool, str]:
        """
        调用NapCat OneBot11 HTTP接口向指定目标发送消息
        """
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
        # 类型
        msg_type: MessageType = msg_body.get("type")
        # 标题
        title = msg_body.get("title")
        # 文本
        text = msg_body.get("text")
        # 图片
        image = msg_body.get("image")
        # 渠道：兼容枚举成员与字符串两种事件数据形式
        channel = msg_body.get("channel")
        channel_value = getattr(channel, "value", channel)

        if channel_value == NotificationChannel.QQ.value:
            # MoviePilot双向交互回复：定向发回来源用户
            userid = msg_body.get("userid")
            if not userid or (not title and not text):
                return
            return self._send_reply(title, text, userid, image)

        if channel_value:
            # 其他渠道的消息不处理
            return

        # 已指定发送渠道的消息不再重复发送
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
