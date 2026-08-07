# YB-GO-Script-i

首先感谢以下两个项目的作者：

- 感谢 [525815266/YYB-Go-Enhanced](https://github.com/525815266/YYB-Go-Enhanced) 作者提供应用宝协议服务增强版，以及微信账号管理和 `wx.login` code 获取能力。
- 感谢 [SuperNaiBA/YYB-GO-Script](https://github.com/SuperNaiBA/YYB-GO-Script) 作者提供 YYB Go 青龙适配脚本及仓库订阅范例。

本项目是 **YYB-GO-Script 项目的脚本补充**，沿用其 `YYB_SERVER` 配置与青龙订阅方式，为 YYB-Go-Enhanced 补充更多可直接在青龙面板运行的脚本。

当前包含：

| 脚本 | 功能 |
| --- | --- |
| `WXZFTXBBS.py` | 微信支付提现笔笔省：登录、领取可用优惠券、查询提现免费券余额 |

## 环境变量

在青龙面板添加环境变量 `YYB_SERVER`，格式为 `YYB-Go-Enhanced地址@账号ref`。多账号每行一个：

```text
172.17.0.4:8000@1
172.17.0.4:8000@2
```

`ref` 可以填写 YYB-Go-Enhanced 中的账号 ID 或 OpenID。地址可以省略 `http://`；青龙与 YYB-Go-Enhanced 使用 Docker 部署时，应填写青龙容器能够访问的 IP 或主机名。

可选变量：

| 变量名 | 说明 |
| --- | --- |
| `LY_NOTIFY` | 设置为非空值时，任务结束后调用青龙 `notify.py` 推送日志 |
| `PROXY_API_URL` | 代理 API，返回 `IP:端口`；默认不使用 |

## 青龙订阅

在青龙面板“订阅管理”中添加：

```bash
ql repo https://github.com/lcmovie/YB-GO-Script-i.git "" "" "main" ""
```

也可以在青龙终端执行同一条命令。订阅完成后，脚本目录通常为 `lcmovie_YB-GO-Script-i`。

## 青龙任务

```bash
task lcmovie_YB-GO-Script-i/WXZFTXBBS.py
```

建议定时：

```cron
10 11,12 * * *
```

如果青龙没有安装 `requests`，请在“依赖管理 → Python3”中添加：

```text
requests
```

## 工作方式

脚本会读取 `YYB_SERVER` 的每个账号，通过 YYB-Go-Enhanced 的 `/wxapp/getCode` 接口取得目标小程序的 `wx.login` code，再登录笔笔省。登录 Token 会缓存在脚本目录的 `wxzftxbbs_account_info.json`，失效后自动重新取码登录。

## 注意事项

- 请先在 YYB-Go-Enhanced 中完成微信账号授权，并确认账号状态正常。
- 微信登录 code 只能使用一次，多个脚本任务请错开执行时间。
- 本项目仅供学习与个人测试，请遵守相关服务条款及当地法律法规。
