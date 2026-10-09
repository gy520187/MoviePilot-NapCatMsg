# MoviePilot 对接 NapCat QQ 消息通知与远程命令

本仓库提供 MoviePilot 与 NapCatQQ 对接的完整方案，同时适配 V3 与 V2：

- `plugins.v3/napcatmsg/`：V3 插件「QQ消息通知（NapCat）」（基于 `app.sdk` 稳定接口，MoviePilot v3.1.0 验证目标）
- `package.v3.json`：V3 插件市场索引，V3 宿主可直接把本仓库添加为插件市场
- `plugins.v2/napcatmsg/`：V2 插件（旧版本 MoviePilot 宿主使用，仅单向通知）
- `package.v2.json`：V2 插件市场索引
- `docker-compose.yml` + `.env.example`：MoviePilot V3 + NapCat 一键部署编排

插件通过 NapCat 的 OneBot 11 HTTP 接口，把 MoviePilot 的通知转发到 QQ 好友私聊或群聊，支持消息类型过滤、@全体成员与图片消息；V3 插件还支持双向交互——在 QQ 里发送命令即可远程控制 MoviePilot（搜索、订阅、识别等，与内置微信/Telegram 机器人命令一致）。

消息链路：

```
通知下发：
MoviePilot（通知事件）
    -> NapCatMsg插件（OneBot 11 HTTP API：send_private_msg / send_group_msg）
    -> NapCat（QQ协议端）
    -> QQ好友 / QQ群

命令上报（仅V3双向交互）：
QQ好友 / QQ群
    -> NapCat（OneBot 11 HTTP上报）
    -> NapCatMsg插件（/report 接口）
    -> MoviePilot消息链（执行远程命令）
    -> 插件私聊回复执行结果
```

## 快速开始（Docker Compose 全新部署）

### 1. 准备配置

```bash
cp .env.example .env
```

编辑 `.env`，至少修改 `NAPCAT_WEBUI_TOKEN` 为随机字符串（NapCat WebUI 登录令牌，固定后重启不变），并按需修改 `MOVIEPILOT_API_TOKEN`、`NAPCAT_ACCOUNT`（机器人 QQ 号）。OneBot 鉴权令牌在后面 NapCat WebUI 的「网络配置」中设置。

### 2. 启动服务

```bash
docker compose up -d
```

compose 使用 V3 镜像 `jxxghp/moviepilot-v3:latest`。两个容器的角色：

| 服务 | 端口 | 用途 |
|------|------|------|
| moviepilot | 3000 | MoviePilot Web 界面 |
| napcat | 6099 | NapCat WebUI，用于 QQ 扫码登录和 OneBot 网络配置 |

### 3. NapCat 扫码登录 QQ

1. 查看启动日志获取 WebUI 登录 Token：`docker logs napcat`，日志中会输出 `WebUI Token: xxxx`（在 `.env` 中设置了 `NAPCAT_WEBUI_TOKEN` 时即为该值，重启固定）
2. 浏览器打开 `http://<服务器IP>:6099/webui`，输入 Token 登录
3. 在 QQ 登录页使用手机 QQ 扫码登录（建议使用小号）
4. 登录态已持久化到 `./napcat/qq`，重启容器无需重新扫码

### 4. NapCat 配置 OneBot HTTP 服务器（通知下发链路）

在 NapCat WebUI 中：`网络配置` -> `新建` -> `HTTP服务器`：

- 名称：如 `moviepilot`（随意）
- 启用：勾选
- Host：`0.0.0.0`
- 端口：`3000`
- 消息格式：`Array`
- 鉴权 Token：自定义一段随机字符串（此令牌与插件 AccessToken 一致，与 WebUI 登录令牌是两回事）

保存后，NapCat 侧配置完成。容器间通过 compose 内部网络互访，`http://napcat:3000` 即 NapCat 的 OneBot HTTP 接口（该端口仅容器网络内可达，未映射宿主机属预期）。

### 5. MoviePilot 安装并配置插件

1. 浏览器打开 `http://<服务器IP>:3000`，使用超级管理员登录
2. 进入 `插件` 市场，在自定义插件源中添加本仓库地址后刷新，找到「QQ消息通知（NapCat）」并安装
   - V3 宿主自动读取 `package.v3.json`，旧 V2 宿主读取 `package.v2.json`，同一仓库两个版本通吃
3. 打开插件配置：
   - 启用插件：开
   - NapCat服务地址：`http://napcat:3000`（与 napcat 容器同 compose 网络时直接用服务名）
   - AccessToken：与 NapCat HTTP 服务器配置的 Token 一致
   - QQ号（私聊）：接收通知的 QQ 号，多个用英文逗号分隔
   - 群号（群聊）：接收通知的群号，多个用英文逗号分隔
   - 群消息@全体成员：按需开启
   - 消息类型：留空发送全部类型，也可只勾选需要的类型
   - 启用双向交互：需要远程命令时开启（配置方法见下节）
4. 打开「测试插件（立即运行）」开关保存，配置的 QQ 和群应立即收到测试消息

### 6.（可选）开启双向交互：QQ 消息作为远程命令

1. 在插件配置中：
   - 启用双向交互：开
   - 上报令牌：设置一个随机字符串（推荐，与 NapCat HTTP 上报的 Token 一致）
   - 可交互QQ号：允许发送命令的 QQ 号（留空表示允许所有人，强烈建议配置）
2. 在 NapCat WebUI 中：`网络配置` -> `新建` -> `HTTP上报`：
   - 启用：勾选
   - URL：`http://moviepilot:3000/api/v1/plugin/NapCatMsg/report`（容器内服务名跨机部署时换成实际地址）
   - Token：与插件「上报令牌」一致
   - 上报类型：保持默认即可
3. 保存后用配置的 QQ 号私聊机器人发送 `搜索 头文字D`（或 `/search 头文字D`），机器人应私聊回复搜索候选列表

命令与 MoviePilot 内置 Telegram/微信机器人的命令语法一致（`/search`、`/subscribe`、`/rename` 等，可在 `设定` -> `服务` 中查看命令列表）。群聊中发送命令同样生效，回复会私聊发给发送者。

## 已有 MoviePilot 环境（只装插件）

无需 docker compose，两种方式任选：

方式一（推荐）：把本仓库 fork 或推送到自己的 GitHub 仓库，然后在 MoviePilot `设定` -> `系统` -> `插件市场` 中追加该仓库地址，刷新插件市场后安装。

方式二：手动复制插件目录并重启容器：
- V3 宿主：把 `plugins.v3/napcatmsg/` 复制到 `/config/plugins/` 下
- V2 宿主：把 `plugins.v2/napcatmsg/` 复制到 `/config/plugins/` 下

插件通过监听 MoviePilot 的消息通知事件工作，与 Telegram、微信等内置渠道互不冲突，可同时使用。

### V2 升级 V3 提示

按官方迁移指引：把 compose 中镜像改为 `jxxghp/moviepilot-v3:latest` 后拉取重建容器，配置目录映射保持不变，数据库可自动向前升级（升级前建议完整备份 `/config`）。

## 插件配置项

| 配置项 | 说明 |
|--------|------|
| NapCat服务地址 | NapCat OneBot HTTP 服务器地址，如 `http://napcat:3000`；跨机部署填实际 IP |
| AccessToken | OneBot 鉴权令牌，同时通过 `Authorization: Bearer` 头和 `access_token` 参数传递 |
| QQ号（私聊） | 调用 `send_private_msg` 的目标，多个用逗号分隔 |
| 群号（群聊） | 调用 `send_group_msg` 的目标，多个用逗号分隔 |
| 群消息@全体成员 | 开启后群聊消息追加 `@全体成员` 消息段 |
| 消息类型 | 按通知类型过滤，留空为全部发送 |
| 启用双向交互 | 开启后接收 QQ 消息作为远程命令（仅 V3 插件支持） |
| 上报令牌 | NapCat HTTP 上报的鉴权 Token，留空表示不校验（不建议） |
| 可交互QQ号 | 允许发送命令的 QQ 号，留空允许所有人（强烈建议配置） |

## 双向交互（V3 插件）

开启后，在 QQ 中给机器人发消息即可远程控制 MoviePilot：

- V3 使用中文动词交互（与微信等内置渠道一致）：`搜索 头文字D`、`下载 名称`、`订阅 标题 [TMDBID]`、`洗版 名称`，随后按提示回复数字选择结果
- 插件已做斜杠命令兼容：`/search 关键词`、`/subscribe 标题`、`/download 名称`、`/resubscribe 名称` 会自动映射为对应中文动词
- 系统类斜杠命令仍直接可用：`/version`、`/downloading`、`/subscribes`、`/sites`、`/restart`、`/clear_session` 等
- 私聊和群聊均可发送命令；执行结果会私聊回复给发送者
- 群聊中 @机器人 发送的命令会自动去除 @ 前缀
- 通过 NapCat 的「HTTP上报」功能把 QQ 消息推送到插件端点 `/api/v1/plugin/NapCatMsg/report`，插件校验上报令牌后转交 MoviePilot 消息链处理
- 收到的命令只在「可交互QQ号」名单内的用户生效，防止陌生人滥用
- 命令在后台线程执行，上报接口立即返回，不影响 NapCat 其他事件上报

安全建议：务必设置「上报令牌」并配置「可交互QQ号」。上报端点无需 MoviePilot 登录态（NapCat 无法提供），仅靠上报令牌校验，令牌泄露等于把 MoviePilot 命令权限开放给外部。

## 常见问题

**发送失败，HTTP 401/403**：两侧 Token 不一致。检查 NapCat HTTP 服务器配置中的 Token 与插件 AccessToken 是否完全相同。

**未获取到返回信息**：MoviePilot 无法访问 NapCat 服务地址。同 compose 网络内用 `http://napcat:3000`；NapCat 独立部署时填其宿主机 IP，并确认端口已放行。

**接口返回 failed**：机器人 QQ 与目标 QQ 非好友时私聊会被 QQ 风控拦截；群聊需机器人在群内。先用 NapCat WebUI 的日志确认请求是否到达。

**消息重复发送**：插件与内置渠道并存属正常现象，可分别在插件「消息类型」中勾选实现分工。

**QQ 掉线频繁**：建议使用活跃度较高的小号，长期使用请开启设备锁，并保持登录态目录 `./napcat/qq` 持久化。

**QQ 发命令无反应**：依次检查：1) NapCat WebUI「网络配置」中 HTTP上报 已启用且 URL 为 `http://<MoviePilot地址>:端口/api/v1/plugin/NapCatMsg/report`；2) 上报 Token 与插件「上报令牌」一致（插件日志会提示请求携带的鉴权形式，NapCat 侧 Token 留空时插件侧也需清空上报令牌）；3) 插件已开启「双向交互」且发送者 QQ 在「可交互QQ号」名单内；4) MoviePilot 日志中搜索「收到QQ」，确认消息是否到达插件。

**双向交互回复了「命令执行失败」**：查看 MoviePilot 运行日志定位异常堆栈；多数情况是 TMDB 网络问题或媒体库访问异常。

**安全提示**：6099（WebUI）与 OneBot 端口请勿直接暴露公网；Token 建议设置为 16 位以上随机字符串；开启双向交互后务必配置「上报令牌」与「可交互QQ号」。

## 目录结构

```
.
├── docker-compose.yml           # MoviePilot V3 + NapCat 一键部署
├── .env.example                 # 环境变量模板
├── package.v3.json              # V3 插件市场索引
├── plugins.v3/napcatmsg/        # V3 插件（app.sdk 接口）
├── package.v2.json              # V2 插件市场索引
├── plugins.v2/napcatmsg/        # V2 插件（旧宿主）
└── tests/
    ├── v2/napcatmsg/            # V2 插件 smoke test
    └── v3/napcatmsg/            # V3 插件 smoke test
```

## 本地验证插件

```bash
python3 tests/v2/napcatmsg/test_plugin.py
python3 tests/v3/napcatmsg/test_plugin.py
```
