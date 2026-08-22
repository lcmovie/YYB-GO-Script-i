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
| 嘉立创签到 | `jlc.py` |
| 君品荟签到 | `jph.js` |
| 微信支付提现笔笔省 | `txbbs.py` |
| 习酒花园 | `xjhy.py` |
| 小米社区签到 | `miqd.py` |
| 中通快递 | `ztkd.py` |

使用前请先部署 YYB-Go-Enhanced，并按各脚本文件头部说明配置 `YYB_SERVER` 等环境变量。

## 独立脚本

目录：`idp-script/`

| 脚本 | 文件名 |
|---|---|
| 福利吧签到 | `fulibasign.js` |
| 联通 | `lt.py` |
| 网易云音乐签到脚本 | `netease_full.js` |
| 微软积分 | `Microsoft Rewards.js` |
| 无忧计划 | `wyjh.py` |
| 移动云盘 | `ydyp.py` |

各脚本所需环境变量、依赖和定时规则请查看对应文件头部说明。

## 注意事项

- 微信登录 code 通常只能使用一次，多个微信任务请错开运行时间。
- 外部接口可能随时调整，语法检查通过不代表业务接口永久可用，请以青龙实际运行日志为准。
- 本仓库脚本仅供学习和个人测试，请遵守相关服务条款及当地法律法规。
