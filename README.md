# YYB-GO-Script-i

首先感谢以下项目的作者：

- 感谢 [525815266/YYB-Go-Enhanced](https://github.com/525815266/YYB-Go-Enhanced) 作者提供应用宝协议服务增强版API，本项目下所有脚本需配合该容器。
- 感谢 [SuperNaiBA/YYB-GO-Script](https://github.com/SuperNaiBA/YYB-GO-Script) 作者提供 YYB Go 青龙适配脚本及仓库订阅范例。

本项目是 **YYB-GO-Script 项目的脚本补充**，使用 `YYB_SERVER` 配置和 YYB-Go-Enhanced 的 `/wxapp/*` 接口，为青龙面板补充更多微信小程序脚本。

## 脚本需求
如有新脚本需求，可在lssues中提出，有能力下会做！

## 环境变量

变量名 | 格式 | 示例
--- | --- | ---
`YYB_SERVER` | `地址@账号ref`，多账号每行一个 | `172.17.0.4:8000@1`

示例：

```text
172.17.0.4:8000@1
172.17.0.4:8000@2
```

`ref` 可以使用 YYB-Go-Enhanced 中的账号 ID 或 OpenID。地址可以省略 `http://`。Docker 部署时，地址必须能从青龙容器访问。

## 青龙订阅

```bash
ql repo https://github.com/lcmovie/YYB-GO-Script-i.git "" "" "main" ""
```

## 脚本

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | 小米社区签到 | `小米社区签到.js` | py |

任务命令示例：

```bash
task lcmovie_YYB-GO-Script-i/小米社区签到.py
```

各脚本的 cron 建议和额外可选配置请查看对应文件头部。

## 依赖

青龙“依赖管理 → NodeJs”添加：

```text
axios
crypto-js
dayjs
got@11
request
tough-cookie
undici
```

青龙“依赖管理 → Python3”添加：

```text
requests
pycryptodome
gmssl
brotli
```

## 消息通知

仓库内置 `sendNotify.js` 和 `notify.py` 统一通知兼容层，支持 YYB-Go-Enhanced 账号任务注入的以下环境变量：

| 渠道 | 环境变量 |
| --- | --- |
| Server酱 | `PUSH_KEY` |
| PushPlus | `PUSH_PLUS_TOKEN`，可选群组 `PUSH_PLUS_USER` |
| 企业微信机器人 | `QYWX_KEY` |

未配置通知变量时，通知内容只输出到青龙任务日志，不影响脚本执行。

## 适配方式

- `getCode.py` 和 `getCode.js` 是统一兼容层。
- 兼容层从 `YYB_SERVER` 解析服务地址和账号 `ref`，并调用 `/wxapp/getCode`。
- 需要手机号授权或 `operateWxData` 的脚本会调用 YYB-Go-Enhanced 对应接口。
- 兼容层会为旧脚本生成仅包含账号 `ref` 的 `WX_ID` 进程变量；用户无需再配置 `WX_ID`、`WECHAT_SERVER` 或旧 `soy_*` 变量。
- 多账号可以位于同一 YYB-Go-Enhanced 服务，也可以分别指定不同地址。

## 注意事项

- 使用前请先在 YYB-Go-Enhanced 中完成微信账号授权，并确认账号状态正常。
- 微信登录 code 只能使用一次，多个任务请错开运行时间。
- 由于外部小程序接口可能调整，语法检查通过不代表目标服务永久可用；请以青龙实际日志为准。
- 本项目仅供学习与个人测试，请遵守相关服务条款及当地法律法规。
