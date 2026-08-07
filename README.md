# YB-GO-Script-i

首先感谢以下项目的作者：

- 感谢 [525815266/YYB-Go-Enhanced](https://github.com/525815266/YYB-Go-Enhanced) 作者提供应用宝协议服务增强版，以及微信账号管理和 `wx.login` code 获取能力。
- 感谢 [SuperNaiBA/YYB-GO-Script](https://github.com/SuperNaiBA/YYB-GO-Script) 作者提供 YYB Go 青龙适配脚本及仓库订阅范例。
- 感谢 [ZHwin/kuakuaql-docs](https://github.com/ZHwin/kuakuaql-docs) 及压缩包内各脚本原作者提供脚本资料；原作者信息尽量保留在各文件头部。

本项目是 **YYB-GO-Script 项目的脚本补充**，统一使用 `YYB_SERVER` 配置和 YYB-Go-Enhanced 的 `/wxapp/*` 接口，为青龙面板补充更多微信小程序脚本。

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
ql repo https://github.com/lcmovie/YB-GO-Script-i.git "" "" "main" ""
```

## 脚本

根目录脚本按类型分类如下：

| 分类 | 数量 | 脚本 |
| --- | ---: | --- |
| 核心脚本 | 1 | `WXZFTXBBS.py`（微信支付提现笔笔省） |
| Python 适配脚本 | 32 | `倍轻松.py`、`巅峰美缝师.py`、`东风日产.py`、`红人库.py`、`厚工坊.py`、`华润壹票达.py`、`嘉立创.py`、`快集合.py`、`老板服务微商城.py`、`绿蜜蜂.py`、`玛氏宠享会.py`、`毛铺草本荟.py`、`美的小天鹅.py`、`蒙娜丽莎.py`、`牛油谷.py`、`趣淘卡.py`、`雀巢健康.py`、`善羿科技.py`、`社服益寿活动.py`、`申工社.py`、`深圳体育湾春茧未来荟.py`、`汤星球.py`、`天机观.py`、`万家乐会员俱乐部.py`、`喂自由.py`、`习酒.py`、`小铛家.py`、`一汽丰田丰享汇.py`、`银鱼质享.py`、`悦喜荟.py`、`中通快递.py`、`iqoo社区.py` |
| JavaScript 适配脚本 | 23 | `爱玛会员俱乐部.js`、`白马智选.js`、`创维.js`、`广汽.js`、`海天美味馆.js`、`海信爱家.js`、`红色火箭.js`、`活力伊利.js`、`金典有机生活.js`、`君品荟签到.js`、`临水玉泉.js`、`霖久智服.js`、`绿树田园.js`、`每天有乐.js`、`美孚.js`、`拼多多果园.js`、`期云积签兑.js`、`全棉时代.js`、`拓路者签到.js`、`问问农.js`、`骁龙骁友会.js`、`伊家乐享会.js`、`stokke.js` |

以上共计 55 个 YYB-Go-Enhanced 适配脚本。

任务命令示例：

```bash
task lcmovie_YB-GO-Script-i/创维.js
task lcmovie_YB-GO-Script-i/东风日产.py
task lcmovie_YB-GO-Script-i/WXZFTXBBS.py
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

## 适配方式

- `getCode.py` 和 `getCode.js` 是统一兼容层。
- 兼容层从 `YYB_SERVER` 解析服务地址和账号 `ref`，并调用 `/wxapp/getCode`。
- 需要手机号授权或 `operateWxData` 的脚本会调用 YYB-Go-Enhanced 对应接口。
- 兼容层会为旧脚本生成仅包含账号 `ref` 的 `WX_ID` 进程变量；用户无需再配置 `WX_ID`、`WECHAT_SERVER` 或旧 `soy_*` 变量。
- 多账号可以位于同一 YYB-Go-Enhanced 服务，也可以分别指定不同地址。

## 筛选说明

本次导入严格排除了：

- 已经存在于 `SuperNaiBA/YYB-GO-Script` 的同项目脚本。
- 用户指定排除的 `所有女生会员服务中心.py`、`顺丰世界杯活动.py`。
- 被文档误归入小程序目录、实际属于公众号或网页的 `庙友之家.js`、`紫金.py`、`浙江福彩CODE.py`。
- 只支持抓取 Token、Cookie、手机号密码或 `3rdsession`，且源码没有提供 `wx.login code` 换业务凭据流程的 `开天工作室.js`、`美信优选.js`、`星韵优选.js`、`云朵充电.js`。为避免伪造接口，这些文件未发布。

## 注意事项

- 使用前请先在 YYB-Go-Enhanced 中完成微信账号授权，并确认账号状态正常。
- 微信登录 code 只能使用一次，多个任务请错开运行时间。
- 由于外部小程序接口可能调整，语法检查通过不代表目标服务永久可用；请以青龙实际日志为准。
- 本项目仅供学习与个人测试，请遵守相关服务条款及当地法律法规。
