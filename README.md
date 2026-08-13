# YYB-GO-Script-i

首先感谢以下项目的作者：

- 感谢 [525815266/YYB-Go-Enhanced](https://github.com/525815266/YYB-Go-Enhanced) 作者提供应用宝协议服务增强版，以及微信账号管理和 `wx.login` code 获取能力。
- 感谢 [SuperNaiBA/YYB-GO-Script](https://github.com/SuperNaiBA/YYB-GO-Script) 作者提供 YYB Go 青龙适配脚本及仓库订阅范例。
- 感谢 [ZHwin/kuakuaql-docs](https://github.com/ZHwin/kuakuaql-docs) 及压缩包内各脚本原作者提供脚本资料；原作者信息尽量保留在各文件头部。

本项目是 **YYB-GO-Script 项目的脚本补充**，统一使用 `YYB_SERVER` 配置和 YYB-Go-Enhanced 的 `/wxapp/*` 接口，为青龙面板补充更多微信小程序脚本，后续我将陆续把调整好的脚本贡献到[SuperNaiBA/YYB-GO-Script](https://github.com/SuperNaiBA/YYB-GO-Script)中，建议优先使用该订阅。

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

仓库根目录现已恢复原有脚本，并保留新增的小米社区签到脚本。参照 kuakuaql-docs 的日常使用类目整理如下：

### 🍔 餐饮 / 食品 / 酒水

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | 临水玉泉 | `临水玉泉.js` | JS |
| 2 | 海天美味馆 | `海天美味馆.js` | JS |
| 3 | 每天有乐 | `每天有乐.js` | JS |
| 4 | 期云积签兑 | `期云积签兑.js` | JS |
| 5 | 天机观 | `天机观.py` | PY |
| 6 | 毛铺草本荟 | `毛铺草本荟.py` | PY |

### 👗 美妆 / 个护 / 母婴

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | stokke | `stokke.js` | JS |

### 🏠 家居 / 家电 / 建材

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | 全棉时代 | `全棉时代.js` | JS |
| 2 | 拓路者签到 | `拓路者签到.js` | JS |
| 3 | 巅峰美缝师 | `巅峰美缝师.py` | PY |
| 4 | 厚工坊 | `厚工坊.py` | PY |
| 5 | 蒙娜丽莎 | `蒙娜丽莎.py` | PY |

### 🚗 汽车 / 出行 / 能源

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | 广汽 | `广汽.js` | JS |
| 2 | 骁龙骁友会 | `骁龙骁友会.js` | JS |
| 3 | 美孚 | `美孚.js` | JS |
| 4 | 海信爱家 | `海信爱家.js` | JS |
| 5 | 东风日产 | `东风日产.py` | PY |
| 6 | 一汽丰田丰享汇 | `一汽丰田丰享汇.py` | PY |

### 💊 健康 / 医疗 / 医药

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | 金典有机生活 | `金典有机生活.js` | JS |
| 2 | 社服益寿活动 | `社服益寿活动.py` | PY |

### 🛒 商超 / 电商 / 零售

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | 拼多多果园 | `拼多多果园.js` | JS |
| 2 | 爱玛会员俱乐部 | `爱玛会员俱乐部.js` | JS |
| 3 | 白马智选 | `白马智选.js` | JS |
| 4 | 伊家乐享会 | `伊家乐享会.js` | JS |
| 5 | 活力伊利 | `活力伊利.js` | JS |
| 6 | 华润壹票达 | `华润壹票达.py` | PY |
| 7 | 万家乐会员俱乐部 | `万家乐会员俱乐部.py` | PY |
| 8 | 小铛家 | `小铛家.py` | PY |
| 9 | 喂自由 | `喂自由.py` | PY |

### 🏢 品牌 / 会员 / 其他

| 序号 | 脚本名称 | 文件名 | 语言 |
| ---: | --- | --- | --- |
| 1 | 红人库 | `红人库.py` | PY |
| 2 | 倍轻松 | `倍轻松.py` | PY |
| 3 | 玛氏宠享会 | `玛氏宠享会.py` | PY |
| 4 | 美的小天鹅 | `美的小天鹅.py` | PY |
| 5 | 牛油谷 | `牛油谷.py` | PY |
| 6 | 趣淘卡 | `趣淘卡.py` | PY |
| 7 | 善羿科技 | `善羿科技.py` | PY |
| 8 | 深圳体育湾春茧未来荟 | `深圳体育湾春茧未来荟.py` | PY |
| 9 | 悦喜荟 | `悦喜荟.py` | PY |
| 10 | 中通快递 | `中通快递.py` | PY |
| 11 | iqoo社区 | `iqoo社区.py` | PY |
| 12 | 绿蜜蜂 | `绿蜜蜂.py` | PY |
| 13 | 汤星球 | `汤星球.py` | PY |
| 14 | 快集合 | `快集合.py` | PY |
| 15 | 老板服务微商城 | `老板服务微商城.py` | PY |
| 16 | 小米社区签到 | `小米社区签到.py` | PY |

以上业务分类共收录 45 个脚本。

任务命令示例：

```bash
task lcmovie_YYB-GO-Script-i/全棉时代.js
task lcmovie_YYB-GO-Script-i/东风日产.py
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
