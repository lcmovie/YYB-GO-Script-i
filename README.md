# YYB-GO-Script-i

青龙脚本订阅仓库，脚本按运行方式分为两类：

- `wx-script/`：对接 [YYB-Go-Enhanced](https://github.com/525815266/YYB-Go-Enhanced) 的微信小程序脚本。
- `idp-script/`：独立脚本。

## 青龙拉库命令

### 1. 只拉取微信小程序脚本

```bash
ql repo "https://github.com/lcmovie/YYB-GO-Script-i.git" "^wx-script/.*\.(js|py)$" "" "" "main" "js py"
```

### 2. 只拉取独立脚本

```bash
ql repo "https://github.com/lcmovie/YYB-GO-Script-i.git" "^idp-script/.*\.(js|py)$" "" "" "main" "js py"
```

### 3. 拉取全部脚本

```bash
ql repo "https://github.com/lcmovie/YYB-GO-Script-i.git" "^(wx-script|idp-script)/.*\.(js|py)$" "" "" "main" "js py"
```

参数顺序：

```text
仓库地址 | 白名单 | 黑名单 | 依赖文件 | 分支 | 文件后缀
```

不同青龙版本的 `ql repo` 参数可能存在差异。如果命令行筛选无效，请在青龙面板的“订阅管理”中填写相同的仓库地址、分支和白名单。

## 微信小程序脚本

目录：`wx-script/`

| 脚本 | 文件名 |
|---|---|
| 飞猪签到 | `fzqd.py` |
| 红色火箭 | `hshj.js` |
| 哈啰出行签到 | `hl.py` |
| 华润通签到 | `hrt.py` |
| 嘉立创签到 | `jlc.py` |
| 君品荟签到 | `jph.js` |
| 微信支付提现笔笔省 | `txbbs.py` |
| 习酒花园 | `xjhy.py` |
| 小米社区签到 | `miqd.py` |
| 中通快递 | `ztkd.py` |
| 平安i动签到 | `paid.js` |
| 长虹智慧家 | `chzhjj.py` |
| 创维 | `cw.js` |
| QQ音乐签到 | `qqmusic.py` |
| 爱裹旧衣回收 | `agyh.js` |
| 白鲸鱼旧衣服回收 | `bjy.py` |
| 回收猿签到 | `hsy.py` |
| 漓泉啤酒生态营地 | `lqpj.py` |
| 拾绿旧衣回收 | `sljy.js` |
| 太平洋蓝医保 | `tpylyb.py` |
| 丸丫甄选 | `wyzx.js` |
| Zippo会员 | `zippo.js` |
| 迪卡侬 | `dkn.py` |
| 神州车友会签到 | `szcyh.py` |
| 中华保签到 | `zhb.py` |
| 中国移动10086+签到 | `yd10086.py` |
| 南方航空签到 | `nfhk.py` |
| 哈啰出行 | `hlcx.py` |
| WorkBuddy签到 | `WorkBuddy_yyb.py` |
| elm_Cookie同步 | `elm_cookie.py` |
| 勇闯天涯签到 | `ycty.py` |
| 众安健康签到 | `zajk.py` |
| JD Cookie同步 | `jd_cookie.py` |
| 移动云盘（code版） | `ydyp_code.py` |
| 顺丰速运自动任务 | `sfsy.py` |
| 影视飓风 | `YSJF.js` |
| 铛铛一下 | `DDYX.py` |


红色火箭（`wx-script/hshj.js`）保留签到、当日 ROE 口令兑换、积分及红包记录查询；现金红包需在小程序手动领取。青龙通知仅推送账号汇总，不包含详细执行日志；设置 `HSJJ_NOTIFY=0` 可关闭该脚本通知。

## 独立脚本

目录：`idp-script/`

| 脚本 | 文件名 |
|---|---|
| 福利吧签到 | `fulibasign.js` |
| 联通 | `lt.py` |
| 联通乘风破浪2026 | `lt_cmf2026.py` |
| 网易云音乐签到脚本 | `netease_full.js` |
| 微软积分 | `microsoft_rewards.js` |
| 雨云自动签到 | `Rainyun.py` |
| 电信光耀网龄 | `dxgy.py` |
| 电信好运连连转盘 | `dxhyll.py` |
| 电信AI奇遇 | `dxai.py` |

各脚本所需环境变量、依赖和定时规则请查看对应文件头部说明。

## 微软积分配置

在青龙中新增并启用一条环境变量 `MS_REWARDS_ACCOUNTS`，多账号每行一条：

```text
your_account@example.com#your_password
another_account@example.com#your_password#YOUR_TOTP_SECRET
```

未设置二次验证时省略第三项；第三项填写 TOTP 密钥，不是动态验证码。密码含 `#` 时写成 `\#`，反斜杠可写成 `\\`。地区固定为 `cn`、语言为 `en`、不使用代理。账号信息无需写入脚本，订阅更新不会覆盖环境变量。

仅检查配置、不登录和不执行积分任务：

```bash
task lcmovie_YYB-GO-Script-i_main/idp-script/microsoft_rewards.js -- --check-config
```

## 注意事项

- 微信登录 code 通常只能使用一次，多个微信任务请错开运行时间。
- 外部接口可能随时调整，语法检查通过不代表业务接口永久可用，请以青龙实际运行日志为准。
- 本仓库脚本仅供学习和个人测试，请遵守相关服务条款及当地法律法规。
