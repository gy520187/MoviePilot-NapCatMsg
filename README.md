# MoviePilot 对接 NapCat QQ 消息通知

本仓库提供 MoviePilot 与 NapCatQQ 对接的完整方案，同时适配 V3 与 V2：

- `plugins.v3/napcatmsg/`：V3 插件「QQ消息通知（NapCat）」（基于 `app.sdk` 稳定接口，MoviePilot v3.1.0 验证目标）
- `package.v3.json`：V3 插件市场索引，V3 宿主可直接把本仓库添加为插件市场
- `plugins.v2/napcatmsg/`：V2 插件（旧版本 MoviePilot 宿主使用）
- `package.v2.json`：V2 插件市场索引
- `docker-compose.yml` + `.env.example`：MoviePilot V3 + NapCat 一键部署编排

插件通过 NapCat 的 OneBot 11 HTTP 接口，把 MoviePilot 的通知转发到 QQ 好友私聊或群聊，支持消息类型过滤、@全体成员与图片消息。

消息链路：

```
MoviePilot（通知事件）
    -> NapCatMsg插件（OneBot 11 HTTP API：send_private_msg / send_group_msg）
    -> NapCat（QQ协议端）
    -> QQ好友 / QQ群
```

## 快速开始（Docker Compose 全新部署）

### 1. 准备配置

```bash
cp .env.example .env
```

编辑 `.env`，至少修改 `NAPCAT_TOKEN` 为随机字符串（两侧鉴权使用），并按需修改 `MOVIEPILOT_API_TOKEN`、`NAPCAT_ACCOUNT`（机器人 QQ 号）。

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

1. 查看启动日志获取 WebUI 登录 Token：`docker logs napcat`，日志中会输出 `WebUI Token: xxxx`
2. 浏览器打开 `http://<服务器IP>:6099/webui`，输入 Token 登录
3. 在 QQ 登录页使用手机 QQ 扫码登录（建议使用小号）
4. 登录态已持久化到 `./napcat/qq`，重启容器无需重新扫码

### 4. NapCat 配置 OneBot HTTP 服务器

在 NapCat WebUI 中：`网络配置` -> `新建` -> `HTTP服务器`：

- 启用：勾选
- Host：`0.0.0.0`
- Port：`3000`
- Token：与 `.env` 中 `NAPCAT_TOKEN` 一致（未设置 token 则两侧都留空）

保存后，NapCat 侧配置完成。容器间通过 compose 内部网络互访，`http://napcat:3000` 即 NapCat 的 OneBot HTTP 接口。

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
4. 打开「测试插件（立即运行）」开关保存，配置的 QQ 和群应立即收到测试消息

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

## 常见问题

**发送失败，HTTP 401/403**：两侧 Token 不一致。检查 NapCat HTTP 服务器配置中的 Token 与插件 AccessToken 是否完全相同。

**未获取到返回信息**：MoviePilot 无法访问 NapCat 服务地址。同 compose 网络内用 `http://napcat:3000`；NapCat 独立部署时填其宿主机 IP，并确认端口已放行。

**接口返回 failed**：机器人 QQ 与目标 QQ 非好友时私聊会被 QQ 风控拦截；群聊需机器人在群内。先用 NapCat WebUI 的日志确认请求是否到达。

**消息重复发送**：插件与内置渠道并存属正常现象，可分别在插件「消息类型」中勾选实现分工。

**QQ 掉线频繁**：建议使用活跃度较高的小号，长期使用请开启设备锁，并保持登录态目录 `./napcat/qq` 持久化。

**安全提示**：6099（WebUI）与 OneBot 端口请勿直接暴露公网；Token 建议设置为 16 位以上随机字符串。

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
