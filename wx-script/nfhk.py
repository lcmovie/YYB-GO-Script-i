#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name: 南方航空
# cron: 6 8 * * *
"""
name: 南方航空签到
cron: 6 8 * * *

中国南方航空（明珠会员）微信小程序「天天签到」每日签到 + 连续签到奖励（抽奖机会 / 里程），
基于 YYB-Go-Enhanced 自动取码登录，全程无需抓包。

青龙环境变量：
  YYB_SERVER           必填，YYB-Go-Enhanced地址@微信账号标识，多账号每行一条
                       例：yyb-go:8000@1
  YYB_API_KEY          可选，也可填写 YYB_PROTOCOL_TOKEN，值为 YYB 服务端协议令牌
  NFHK_DRY_RUN         可选，=1 只查询不签到（建议首次这样试）
  NFHK_ENABLE_SIGN     可选，默认 1；=0 只查询不签到
  NFHK_ENABLE_AWARD    可选，默认 1；=0 关闭「自动领取待领奖品」
  NFHK_ENABLE_LOTTERY  可选，默认 1；=0 关闭抽奖机会的探测与提示
  NFHK_ENABLE_RELOGIN  可选，默认 1；=0 关闭 S00011（登录信息失效）自动重新取码登录
  NFHK_LOGIN_RETRY     可选，登录重试次数，默认 3（code 一次性，失败会换新 code 重试）
  NFHK_REQUEST_TIMEOUT 可选，单次请求超时秒数，默认 30
  NFHK_RANDOM_HEADERS  可选，默认 1；=0 关闭随机 User-Agent
  NFHK_DEBUG           可选，=1 打印请求/响应明细，便于排查接口变动

依赖：requests（仓库 requirements.txt 已声明）
通知：优先使用青龙内置 notify.py；未配置时回落到 PushPlus / Server酱 / 企业微信 / Bark。
      通知里固定输出每个账号的「初始里程 → 最终里程」，便于对账。通知失败不影响签到结果。
功能：活动/日历/奖励阶梯读取 -> 每日签到 -> 自动领取待领奖品（含「抽奖机会」并解析抽奖入口）
      -> 复查里程与金币 -> 汇总通知。多账号串行，非明珠会员归入「跳过」不计失败。

────────────────────────────────────────────────────────────────────────────
登录链路（全部由小程序包 + 签到 H5 静态分析复现，无任何抓包）
────────────────────────────────────────────────────────────────────────────
小程序 AppID  wx729238547ac7a14c      接口域  https://wxapi.csair.com
签到业务在 H5：https://wxapi.csair.com/h5/sign/#/signTools （react SPA，
小程序「我 → 签到」用 web-view 打开它，登录态通过 URL 的 token 参数传入）

  1. YYB   POST /wxapp/getCode                        -> wx.login code + 微信 openid
  2. 南航  POST /mini/api/login/login                 -> sessionId / unionId / openId
           ?appid=wx729238547ac7a14c&wxchannel=wxopen&envVersion=release
           请求头 sessionId="" / channel=ecsair / activityChannel=1 / unnecessaryParam=""
           body   {"code": <code>}
  3. 南航  POST /mini/api/login/isLogin               -> 明珠会员信息（含 token、usefulMileage 里程）
           请求头 sessionId=<上一步 sessionId>
           body   {"ssoKey": <unionId>, "clientType": "PC"}
  4. 拿到的 member.token 就是签到 H5 的登录态：H5 把它写成 Cookie
           TOKEN=<token> 与 cs1246643sso=<token>（两个都必须带，缺一个会报 S0001 登录凭证为空）

────────────────────────────────────────────────────────────────────────────
签到 H5 接口（域 https://wxapi.csair.com，统一 query: type=APPTYPE&chanel=ss&lang=zh）
────────────────────────────────────────────────────────────────────────────
  POST /marketing-tools/activity/load            {activityType:"sign", channel:"mini"} 活动配置
        -> data.activityDtoList[].signActivity：activityName「天天签到」、
           rewardType=serialSign、signTimeRange=08:00:00-23:59:59、
           pinpointAwardConfig = 精准里程奖励日（指定日期签到额外给里程）
  GET  /marketing-tools/sign/getSignCalendarNew  ?startQueryDate=YYYYMM01&endQueryDate=YYYYMM末
        -> data.dateList 该月已签日期（只返回所查月份）、awardDisplay = 连签奖励阶梯
           阶梯元素：{dateOfAward, rewardType:"serialSign", prizeType:
                     "lotteryAward"（抽奖机会）|"mileageAward"（直接给里程）,
                     num, isGain}
  GET  /marketing-tools/sign/getSignProgress     已废弃，signSerial 恒为 null
  GET  /marketing-tools/sign/getUserAwardContent 奖励条件进度（如「抽奖机会（连签3天）」）
  GET  /marketing-tools/sign/getSignUserCoinBalance / POST .../getSignGoldCountNum {pageNo:1} 金币
        -> 上述账号金币体系未开通，balance 恒为 "--"，实际积分就是里程
  POST /marketing-tools/award/awardList          {activityType:"sign", awardStatus, pageNum}
        awardStatus ∈ {all, waitReceive, received, expired}
        （H5 按钮态另有 benefitWaitReceive / lotteryWaitReceive「待参与」，列表用 waitReceive 即可）
  POST /marketing-tools/award/getAward           {activityType:"sign", signUserRewardId} 领奖
  POST /marketing-tools/activity/join            {activityType:"sign", channel:"mini"} 执行签到
        respCode=0000 且 data.code ∈ {00A1 本次有奖, 00A2 成功, 00A0/00A3 本档无额外奖励}
        respCode ∈ {S2001 今日已签, 0130/0131/0140/0141/0150/0151} 为提示类，H5 也只弹文案
        respCode=S0003 需实名认证（2026-10 起，账号资质问题，不算脚本失败）
        respCode=S00011 登录信息失效 -> 按前端逻辑重新取码登录后重试（NFHK_ENABLE_RELOGIN）

────────────────────────────────────────────────────────────────────────────
关于「连续签到抽奖」（如实说明能力边界）
────────────────────────────────────────────────────────────────────────────
  活动「天天签到」是 serialSign（连续/累计签到）玩法，连签到达指定天数后由服务端
  在 awardList 里下发一条待领奖品：
      {"awardType":"lotteryAward", "awardName":"抽奖机会", "signDay":"3",
       "awardDesc":"{...lotteryUrl...}", "awardId":..., "activityId":..., "id":...}

  抽奖链路（H5 home chunk 的 signAwardJump / received 复现）：
    1. POST award/getAward {signUserRewardId: id}
       成功条件：respCode=0000 且 data.code=0000
    2. 若奖品是抽奖机会，H5 会拼出跳转地址并交给小程序打开：
         url = <lotteryUrl> &signInGiftId=<awardId>
                            &signInActivityId=<activityId> &rewardId=<id>
       lotteryUrl 有两个来源（两处代码各用一个）：奖品对象顶层的 `lotteryUrl`，
       或 `JSON.parse(awardDesc).lotteryUrl`；跳转字段另有 microJumpPage/microJumpLink。
       最终动作是 window.wx.miniProgram.navigateTo({url})，即**小程序内的一个页面**，
       转盘本身在那个页面里（通常还要看激励视频才给转）。

  因此本脚本对抽奖的能力边界是：**自动把「抽奖机会」领到手，并把抽奖入口原样打印出来**
  （通知里也会带），点一下即可参与。转盘本身在微信内的页面里、且带激励视频门槛，
  无法在青龙里代跑；脚本不会伪造任何抽奖结果。
  连签第 3 天（本活动 2026-09-23）首次拿到抽奖机会时，日志里会出现完整入口地址。

────────────────────────────────────────────────────────────────────────────
实测记录（2026-09-21，青龙容器 ql2）
────────────────────────────────────────────────────────────────────────────
  · 5 个账号：1/3/5 是明珠会员且签到成功，2/4 未注册 → 跳过（不算失败）
  · 定时任务 id=1127（task nfhk.py，6 8 * * *），走任务通道跑通，PushPlus 通知送达
  · 注意：面板用 command-run 手工跑不会加载任务环境变量，需要在命令里显式带上
  · 2026-10 起：面板任务改为仓库订阅模式（id=1128，task lcmovie_YYB-GO-Script-i_main/
    wx-script/nfhk.py），日志目录 wx-script_nfhk/

────────────────────────────────────────────────────────────────────────────
活动规则（2026-09 期，已与官方规则弹窗逐条核对）
────────────────────────────────────────────────────────────────────────────
  官方弹窗原文：「9月签到新玩法上线！每日 8:00—23:59:59 签到。
    9.1 签到可获得 2 里程；9.15 签到可获得 8 里程；9.28 签到可获得 88 里程；
    连续签到 3 天，可获得抽奖机会，有机会获得 6000 里程、666 里程、66 里程、
    5天+30%里程奖励券、2 里程。」

  与接口数据的对应关系（全部由 activity/load 下发，脚本不硬编码任何一条）：
    · 签到时段 8:00–23:59:59  -> signActivity.signTimeRange = "08:00:00-23:59:59"
    · 9.1/9.15/9.28 里程      -> signActivity.pinpointAwardConfig
                                 （3 条 mileageAward，分别为 2 / 8 / 88）
    · 连签 3 天得抽奖机会      -> getSignCalendarNew.awardDisplay 里
                                 dateOfAward=2026-09-23, prizeType=lotteryAward
                                 （同月还有 09-26 / 09-29 两个抽奖档、09-28 里程档）
  ⚠️ 弹窗里那份**奖池清单（6000/666/66 里程、5天+30%里程券、2 里程）接口并不下发**
     （activity/load 的 popContent / tagConfig / shareRewardConfig 全为 null，
      H5 全部 15 个 js chunk 里也搜不到这些数字，属运营侧图文）。
     所以脚本只认服务端返回的奖品，绝不猜测或写死奖池 —— 中奖结果以服务端为准。

────────────────────────────────────────────────────────────────────────────
2026-10 跨月复测（10-02，小程序 469→470、H5 chunk 已更新后实测）
────────────────────────────────────────────────────────────────────────────
  结论：**接口、签名参数、抽奖拼法全部不变，活动 id 每月滚动（300 → 308）由脚本动态选取**，
  无破坏性变更；10 月精准里程日（10-01 +8 / 10-15 +5 / 10-28 +28）与连签阶梯
  （下一档 10-03 抽奖机会）均正常下发。跨月连签合并实测正常（账号显示「本月 2 天 连续 8/12 天」）。

  新发现的两个点（已处理）：
  1. respCode=S00011「获取用户登录信息失败」：member token 偶发被服务端吊销
     （H5 的处理是 `"S00011"===respCode && this.getLogin()` 整页重登）。
     脚本对策：h5 链路收到 S00011 时自动重新取码登录一次并重试当前请求（NFHK_ENABLE_RELOGIN）。
  2. respCode=S0003「领取奖品需要先完成实名认证哦~」：10 月活动对**领奖**加了实名门槛
     （H5 同步新增实名认证弹窗与 aid/uid 校验）。这是账号资质问题，脚本无法代做，
     归类为「需实名认证」提示（不算脚本失败），到 南方航空App/小程序 完成实名后奖品可正常领取。

作者：lcmovie https://github.com/lcmovie
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    print("❌ 缺少依赖：pip install requests")
    sys.exit(1)

APP_NAME = "南方航空签到"
HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
APP_NO = "wx729238547ac7a14c"            # 南方航空小程序 AppID
MP_VERSION = "20260910"                  # 小程序版本号（用于 Referer）
API_BASE = "https://wxapi.csair.com"     # 小程序与签到 H5 共用同一个域
WX_CHANNEL = "wxopen"                    # 小程序 channel
ENV_VERSION = "release"
CLIENT_TYPE = "PC"                       # 仅作为 isLogin 的 clientType 字段

# 小程序统一请求头（来自 utils/ApiReq.js 的 O() 函数）
MP_HEADERS = {
    "sessionId": "",
    "channel": "ecsair",
    "activityChannel": "1",
    "unnecessaryParam": "",
}
# 登录 URL 上固定的 query（来自 utils/ApiReq.js 的 h() + config/interface.js）
MP_QUERY = {"appid": APP_NO, "wxchannel": WX_CHANNEL, "envVersion": ENV_VERSION}
# 签到 H5 统一 query（来自 H5 static/js 的 axios 封装）
H5_QUERY = {"type": "APPTYPE", "chanel": "ss", "lang": "zh"}

ACTIVITY_TYPE = "sign"
ACTIVITY_CHANNEL = "mini"                # 小程序侧渠道，活动/签到都传 mini

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) XWEB/8555",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Mobile/15E148 MicroMessenger/8.0.49(0x1800312b) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat XWEB/8555",
]

# 签到成功的结果码（activity/join -> data.code，取自 H5 home chunk 的判断分支）
SIGN_CODE_MAP = {
    "00A1": "签到成功（本次获得奖励）",
    "00A2": "签到成功",
    "00A0": "签到成功（本档无额外奖励）",
    "00A3": "签到成功（本档无额外奖励）",
}
# H5 视为「正常提示」而非报错的 respCode（signButton 的 r 映射表）
SIGN_SOFT_CODES = {"S2001", "0130", "0131", "0140", "0141", "0150", "0151"}
# H5/服务端返回 S00011 = 登录信息失效，H5 的处理是整页重新登录（this.getLogin()）
RELOGIN_CODE = "S00011"
# 领奖/签到返回 S0003 = 需实名认证（2026-10-02 实测），账号资质问题，不算脚本失败
REALNAME_CODES = {"S0003"}


class SkipAccount(Exception):
    """账号本身不具备参与条件（非会员 / 未绑定），归入「跳过」而非失败。"""


class ApiError(Exception):
    """接口返回了非预期结果。"""


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def env_flag(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name, "") or "").strip() or default)
    except Exception:
        return default


DRY_RUN = env_flag("NFHK_DRY_RUN", "0")
ENABLE_SIGN = env_flag("NFHK_ENABLE_SIGN", "1")
ENABLE_AWARD = env_flag("NFHK_ENABLE_AWARD", "1")
ENABLE_LOTTERY = env_flag("NFHK_ENABLE_LOTTERY", "1")
ENABLE_RELOGIN = env_flag("NFHK_ENABLE_RELOGIN", "1")
LOGIN_RETRY = max(1, env_int("NFHK_LOGIN_RETRY", 3))
TIMEOUT = env_int("NFHK_REQUEST_TIMEOUT", 30)
RANDOM_HEADERS = env_flag("NFHK_RANDOM_HEADERS", "1")
DEBUG = env_flag("NFHK_DEBUG", "0")

_CURRENT_UA = random.choice(UAS)


def log(*args: Any) -> None:
    print(*args, flush=True)


def dbg(*args: Any) -> None:
    if DEBUG:
        print("[DEBUG]", *args, flush=True)


def clean(value: Any, limit: int = 160) -> str:
    """清洗服务端返回的文本字段（去引号/空白/零宽字符），并截断。"""
    if value is None:
        return ""
    text = str(value)
    text = text.strip("\"' \t\r\n\u200b\u200c\u200d\ufeff")
    return text[:limit]


def preview(obj: Any, limit: int = 300) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)[:limit]
    except Exception:
        return str(obj)[:limit]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def month_start_end(offset: int = 0) -> Tuple[str, str]:
    """offset=0 本月，-1 上月。返回 (YYYYMM01, YYYYMM末)。"""
    today = datetime.now()
    first = today.replace(day=1)
    if offset:
        first = (first - timedelta(days=1)).replace(day=1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return first.strftime("%Y%m%d"), last.strftime("%Y%m%d")


def headers_json() -> Dict[str, str]:
    ua = random.choice(UAS) if RANDOM_HEADERS else _CURRENT_UA
    return {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json",
    }


def parse_ref_list(raw: str) -> List[Tuple[str, str]]:
    """解析 YYB_SERVER：每行 `地址@账号ID`。"""
    out: List[Tuple[str, str]] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "@" not in line:
            out.append((line, "1"))
            continue
        host, _, ref = line.rpartition("@")
        host = host.strip()
        if not host.startswith("http"):
            host = "http://" + host
        out.append((host, ref.strip() or "1"))
    return out


def parse_query(url: str) -> Dict[str, str]:
    """从 URL（含 hash 里的 query）提取全部参数。"""
    from urllib.parse import parse_qsl, urlparse

    res: Dict[str, str] = {}
    try:
        for chunk in (url, urlparse(url).fragment):
            _, _, q = chunk.partition("?")
            if q:
                for k, v in parse_qsl(q, keep_blank_values=True):
                    res[k] = v
    except Exception:
        pass
    return res


def serial_days(date_list: List[str]) -> int:
    """已签日期列表 -> 以「今天」结尾的连续签到天数。"""
    days = set()
    for item in date_list or []:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", clean(item))
        if m:
            days.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if not days:
        return 0
    cursor = datetime.now().date()
    if cursor not in {datetime(*d).date() for d in days}:
        return 0
    count = 0
    while cursor in {datetime(*d).date() for d in days}:
        count += 1
        cursor -= timedelta(days=1)
    return count


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class Client:
    """对 wxapi.csair.com 的薄封装：小程序链路 + 签到 H5 链路。"""

    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(headers_json())
        self.member: Dict[str, Any] = {}
        self.union_id = ""
        self.session_id = ""
        self.open_id = ""
        self.host = ""          # YYB 地址（relogin 用）
        self.ref = ""           # YYB 账号标识（relogin 用）

    # ---------------- 小程序链路 ---------------- #
    def mp_post(self, path: str, body: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
        headers = dict(MP_HEADERS)
        headers["sessionId"] = session_id if session_id is not None else self.session_id
        headers["User-Agent"] = random.choice(UAS) if RANDOM_HEADERS else _CURRENT_UA
        url = API_BASE + path
        r = self.s.post(url, params=MP_QUERY, headers=headers, json=body, timeout=TIMEOUT)
        dbg("POST", url, "->", r.status_code, preview(r.text, 400))
        if r.status_code != 200:
            raise ApiError(f"HTTP {r.status_code} @ {path}")
        try:
            return r.json()
        except Exception:
            raise ApiError(f"非 JSON 响应 @ {path}: {clean(r.text)}")

    def mp_get(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        headers = dict(MP_HEADERS)
        headers["User-Agent"] = random.choice(UAS) if RANDOM_HEADERS else _CURRENT_UA
        query = dict(MP_QUERY)
        query.update(params)
        r = self.s.get(API_BASE + path, params=query, headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            raise ApiError(f"HTTP {r.status_code} @ {path}")
        return r.json()

    # ---------------- 签到 H5 链路 ---------------- #
    def relogin(self) -> None:
        """S00011（登录信息失效）时按 H5 前端逻辑重新取码登录，原地更新会话。

        H5 源码：`"S00011"===t.respCode && this.getLogin()` —— 即整页重走登录链路。
        2026-10-02 实测：member token 偶发被服务端吊销，重新取码登录即可恢复。
        """
        if not self.host or not self.ref:
            raise ApiError(f"{RELOGIN_CODE} 需要重登，但 Client 未记录 YYB host/ref")
        code, openid = yyb_get_code(self.host, self.ref)
        self.open_id = openid
        data = self.mp_post("/mini/api/login/login", {"code": code})
        self.session_id = clean(data.get("sessionId"))
        self.union_id = clean(data.get("unionId"))
        if not self.session_id or not self.union_id:
            raise ApiError(f"重登 login/login 未返回 sessionId/unionId: {preview(data)}")
        member = self.mp_post("/mini/api/login/isLogin",
                              {"ssoKey": self.union_id, "clientType": CLIENT_TYPE})
        self.member = member or {}
        if not clean(self.member.get("token")):
            raise ApiError("重登后仍未取到会员 token（会员资格可能已变化）")
        log("   🔁 已重新取码登录，会话已恢复")

    def _h5_headers(self) -> Dict[str, str]:
        token = clean(self.member.get("token"))
        headers = headers_json()
        headers["Referer"] = API_BASE + "/h5/sign/"
        # ⚠️ 两个 Cookie 必须同时带：只带 TOKEN 时重接口（awardList / getSignProgress 等）
        #    会返回 respCode=S0001「登录凭证为空」。2026-09-21 实测。
        headers["Cookie"] = f"TOKEN={token}; cs1246643sso={token}"
        return headers

    def h5(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
           params: Optional[Dict[str, Any]] = None,
           _relogin_done: bool = False) -> Dict[str, Any]:
        query = dict(H5_QUERY)
        if params:
            for k, v in params.items():
                if v is not None:
                    query[k] = v
        url = API_BASE + path
        kwargs: Dict[str, Any] = {"params": query, "headers": self._h5_headers(), "timeout": TIMEOUT}
        if method.upper() == "POST":
            kwargs["json"] = body if body is not None else {}
        r = self.s.request(method.upper(), url, **kwargs)
        dbg(method.upper(), url, "->", r.status_code, preview(r.text, 400))
        if r.status_code == 405:
            raise ApiError(f"HTTP 405，请求方法不对 @ {path}")
        if r.status_code not in (200, 400):
            raise ApiError(f"HTTP {r.status_code} @ {path}")
        try:
            data = r.json()
        except Exception:
            raise ApiError(f"非 JSON 响应 @ {path}: {clean(r.text)}")
        # S00011 = 登录信息失效：与 H5 一致，重新取码登录后重试一次（防循环）
        if (ENABLE_RELOGIN and not _relogin_done
                and clean(data.get("respCode")).upper() == RELOGIN_CODE):
            log(f"   🔁 {path} 返回 {RELOGIN_CODE}（登录信息失效），自动重新登录后重试")
            self.relogin()
            return self.h5(method, path, body, params, _relogin_done=True)
        return data


def yyb_get_code(host: str, ref: str) -> Tuple[str, str]:
    """YYB 取 wx.login code → (code, openid)。"""
    url = host.rstrip("/") + "/wxapp/getCode"
    headers = {"User-Agent": _CURRENT_UA, "Content-Type": "application/json"}
    api_key = os.getenv("YYB_API_KEY", "").strip() or os.getenv("YYB_PROTOCOL_TOKEN", "").strip()
    if api_key:
        headers["Authorization"] = api_key if api_key.startswith("Bearer ") else "Bearer " + api_key
    r = requests.post(url, json={"app_id": APP_NO, "ref": str(ref)}, headers=headers, timeout=TIMEOUT)
    dbg("YYB getCode", r.status_code, preview(r.text, 300))
    if r.status_code != 200:
        raise ApiError(f"YYB 取码失败 HTTP {r.status_code}: {clean(r.text)}")
    data = r.json()
    if data.get("code") not in (0, "0", None) and not (data.get("data") or {}).get("result"):
        raise ApiError(f"YYB 取码失败: {clean(r.text)}")
    payload = data.get("data") or {}
    code = clean((payload.get("result") or {}).get("code"))
    if not code:
        raise ApiError(f"YYB 未返回 code: {clean(r.text)}")
    return code, clean(payload.get("openid"))


def login_once(host: str, ref: str) -> Client:
    """完整登录：YYB 取码 → /mini/api/login/login → /mini/api/login/isLogin。"""
    client = Client()
    client.host, client.ref = host, ref          # 记录来源，S00011 重登时要用
    code, openid = yyb_get_code(host, ref)
    client.open_id = openid
    dbg("code =", code[:24], "...")

    data = client.mp_post("/mini/api/login/login", {"code": code})
    client.session_id = clean(data.get("sessionId"))
    client.union_id = clean(data.get("unionId"))
    if not client.session_id or not client.union_id:
        raise ApiError(f"login/login 未返回 sessionId/unionId: {preview(data)}")

    member = client.mp_post("/mini/api/login/isLogin",
                            {"ssoKey": client.union_id, "clientType": CLIENT_TYPE})
    client.member = member or {}
    return client


def login(host: str, ref: str) -> Client:
    last: Optional[Exception] = None
    for attempt in range(1, LOGIN_RETRY + 1):
        try:
            client = login_once(host, ref)
            if not clean(client.member.get("token")):
                raise SkipAccount("非明珠会员（未注册/未绑定），无签到资格")
            mtype = clean(client.member.get("type"))
            if mtype == "default":
                raise SkipAccount("非明珠会员（type=default），无签到资格")
            return client
        except SkipAccount:
            raise
        except Exception as exc:
            last = exc
            log(f"   ⚠️ 第 {attempt}/{LOGIN_RETRY} 次登录失败：{clean(exc, 200)}")
            if attempt < LOGIN_RETRY:
                time.sleep(1.5 * attempt)
    raise ApiError(f"登录失败：{clean(last, 200)}")


# --------------------------------------------------------------------------- #
# 业务
# --------------------------------------------------------------------------- #
def fetch_member_brief(client: Client) -> Dict[str, Any]:
    """重新查一次会员信息（签到后里程会变，用它拿最新值）。"""
    try:
        member = client.mp_post("/mini/api/login/isLogin",
                                {"ssoKey": client.union_id, "clientType": CLIENT_TYPE})
        if clean(member.get("token")):
            client.member = member
    except Exception as exc:
        dbg("刷新会员信息失败", clean(exc))
    m = client.member or {}
    return {
        "name": clean(m.get("cnFullName")) or clean(m.get("enFullName")) or "明珠会员",
        "card": clean(m.get("cardNo-sensitive")),
        "mileage": to_float(m.get("usefulMileage")),
        "ffpTier": m.get("ffpTier"),
        "tier": clean(m.get("loaltyName")),
        "loginType": clean(m.get("loginType")),
        "identify": clean((m.get("euserInfoDto") or {}).get("identifyStatus")),
    }


def to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_activity(client: Client) -> Dict[str, Any]:
    data = client.h5("POST", "/marketing-tools/activity/load",
                     {"activityType": ACTIVITY_TYPE, "channel": ACTIVITY_CHANNEL})
    if data.get("respCode") != "0000":
        raise ApiError(f"activity/load 失败：{clean(data.get('respMsg'))}")
    payload = data.get("data") or {}
    chosen: Dict[str, Any] = {}
    for item in payload.get("activityDtoList") or []:
        sa = item.get("signActivity") or {}
        if clean(sa.get("activityType")) == ACTIVITY_TYPE and clean(sa.get("status")) == "enable":
            chosen = sa
            break
    if not chosen:
        for item in payload.get("activityDtoList") or []:
            sa = item.get("signActivity") or {}
            if sa:
                chosen = sa
                break
    pinpoint: List[Dict[str, Any]] = []
    raw_pin = chosen.get("pinpointAwardConfig")
    if raw_pin:
        try:
            pinpoint = json.loads(raw_pin) if isinstance(raw_pin, str) else (raw_pin or [])
        except Exception:
            pinpoint = []
    return {
        "activity": chosen,
        "style": payload.get("style") or {},
        "title": clean(chosen.get("activityName")) or clean(payload.get("signActivityTitle")) or "天天签到",
        "pageTitle": clean(payload.get("signActivityTitle")),
        "pinpoint": pinpoint if isinstance(pinpoint, list) else [],
    }


def fetch_calendar(client: Client, include_prev_month: bool = True) -> Dict[str, Any]:
    """签到日历 + 奖励阶梯。

    连续签到天数必须能跨月计算：本月已签日期只能看到本月，所以默认再取一次上月
    的 dateList 一起做并集（2026-09-21 实测：getSignCalendarNew 的 dateList
    就是「该月已签日期」列表，传哪个月就只返回哪个月）。
    """
    start, end = month_start_end(0)
    data = client.h5("GET", "/marketing-tools/sign/getSignCalendarNew",
                     params={"startQueryDate": start, "endQueryDate": end})
    if data.get("respCode") != "0000":
        raise ApiError(f"getSignCalendarNew 失败：{clean(data.get('respMsg'))}")
    d = data.get("data") or {}
    signed = [clean(x) for x in (d.get("dateList") or [])]
    serial = list(signed)

    if include_prev_month:
        try:
            p_start, p_end = month_start_end(-1)
            prev = client.h5("GET", "/marketing-tools/sign/getSignCalendarNew",
                             params={"startQueryDate": p_start, "endQueryDate": p_end})
            if clean(prev.get("respCode")) == "0000":
                serial += [clean(x) for x in ((prev.get("data") or {}).get("dateList") or [])]
        except Exception as exc:
            dbg("上月日历读取失败（不影响本月签到）", clean(exc))

    ladder: List[Dict[str, Any]] = []
    raw = d.get("awardDisplay")
    if raw:
        try:
            ladder = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            ladder = []
    return {
        "signedDays": sorted(set(signed)),      # 仅本月，用于展示「本月已签 N 天」
        "serialDates": sorted(set(serial)),     # 含上月，用于算连续天数
        "repairDays": [clean(x) for x in (d.get("repairSignDateList") or [])],
        "ladder": ladder,
        "serialStart": d.get("lastSerialStartDate"),
        "progressMsg": clean(d.get("signProgressMsg")),
        "remindSwitch": d.get("signRemindSwitch"),
    }


def fetch_progress(client: Client) -> Dict[str, Any]:
    try:
        data = client.h5("GET", "/marketing-tools/sign/getSignProgress")
        return data.get("data") or {}
    except Exception as exc:
        dbg("getSignProgress 失败", clean(exc))
        return {}


def fetch_award_content(client: Client) -> List[Dict[str, Any]]:
    try:
        data = client.h5("GET", "/marketing-tools/sign/getUserAwardContent")
        if data.get("respCode") == "0000" and isinstance(data.get("data"), list):
            return data["data"]
    except Exception as exc:
        dbg("getUserAwardContent 失败", clean(exc))
    return []


def fetch_gold(client: Client) -> str:
    """金币余额（部分账号为 --）。"""
    try:
        data = client.h5("POST", "/marketing-tools/sign/getSignGoldCountNum", {"pageNo": 1})
        if data.get("respCode") == "0000":
            bal = clean((data.get("data") or {}).get("balance"))
            if bal and bal != "--":
                return bal
    except Exception as exc:
        dbg("getSignGoldCountNum 失败", clean(exc))
    try:
        data = client.h5("GET", "/marketing-tools/sign/getSignUserCoinBalance")
        bal = clean(data.get("data"))
        if data.get("respCode") == "0000" and bal and bal != "--":
            return bal
    except Exception as exc:
        dbg("getSignUserCoinBalance 失败", clean(exc))
    return "--"


def fetch_awards(client: Client, status: str = "all") -> List[Dict[str, Any]]:
    try:
        data = client.h5("POST", "/marketing-tools/award/awardList",
                         {"activityType": ACTIVITY_TYPE, "awardStatus": status, "pageNum": 1})
        if data.get("respCode") == "0000":
            return (data.get("data") or {}).get("list") or []
        raise ApiError(f"awardList 失败：{clean(data.get('respMsg'))}")
    except ApiError:
        raise
    except Exception as exc:
        dbg("awardList 异常", clean(exc))
        return []


def do_sign(client: Client) -> Dict[str, Any]:
    """执行签到。返回 {status, message, code, data}。"""
    data = client.h5("POST", "/marketing-tools/activity/join",
                     {"activityType": ACTIVITY_TYPE, "channel": ACTIVITY_CHANNEL})
    resp_code = clean(data.get("respCode")).upper()
    if resp_code == "0000":
        inner = data.get("data") or {}
        code = clean(inner.get("code")).upper()
        label = SIGN_CODE_MAP.get(code) or clean(inner.get("result")) or "签到成功"
        if code:
            label += f"（code={code}）"
        return {"status": "ok", "code": code, "message": label, "data": inner}
    if resp_code in SIGN_SOFT_CODES:
        # S2001 今日已签；0130/0140/0141/0150/0151 为时段/重复类提示，H5 也只弹文案
        return {"status": "already", "code": resp_code,
                "message": clean(data.get("respMsg")) or f"未执行签到（respCode={resp_code}）",
                "data": data.get("data")}
    if resp_code in REALNAME_CODES:
        # S0003 需实名认证（2026-10 起）：账号资质问题，不算脚本失败
        return {"status": "need_verify", "code": resp_code,
                "message": (f"需实名认证：{clean(data.get('respMsg')) or '请先完成实名认证'}"
                            "（到「南方航空App/小程序-我的」完成实名后再试）"),
                "data": data.get("data")}
    return {"status": "fail", "code": resp_code,
            "message": f"{clean(data.get('respMsg')) or '签到失败'}（respCode={resp_code}）",
            "data": data.get("data")}


def claim_awards(client: Client) -> List[Dict[str, Any]]:
    """自动领取待领奖品；抽奖类奖品会解析出 lotteryUrl。"""
    results: List[Dict[str, Any]] = []
    if not ENABLE_AWARD:
        return results
    try:
        pending = fetch_awards(client, "waitReceive")
    except Exception as exc:
        return [{"ok": False, "message": f"奖品列表获取失败：{clean(exc)}"}]

    for award in pending:
        rid = award.get("id")
        if rid in (None, ""):
            continue
        name = clean(award.get("awardName")) or clean(award.get("awardType")) or "奖品"
        item: Dict[str, Any] = {"ok": False, "name": name, "lotteryUrl": ""}
        try:
            data = client.h5("POST", "/marketing-tools/award/getAward",
                             {"activityType": ACTIVITY_TYPE, "signUserRewardId": rid})
        except Exception as exc:
            item["message"] = f"{name} 领取异常：{clean(exc)}"
            results.append(item)
            continue

        # H5 的成功判定是 respCode=0000 且 data.code=0000（signAwardJump）
        inner = data.get("data") or {}
        inner_code = clean(inner.get("code")).upper()
        top_code = clean(data.get("respCode")).upper()
        if top_code in REALNAME_CODES:
            # S0003 需实名认证（2026-10 起）：无法代做，明确提示归为「待实名」
            item["need_verify"] = True
            item["message"] = (f"{name} 需实名认证：{clean(data.get('respMsg')) or '请先完成实名认证'}"
                               "（到「南方航空App/小程序-我的」完成实名后可正常领取）")
            results.append(item)
            continue
        if top_code != "0000" or inner_code not in ("", "0000"):
            item["message"] = (f"{name} 领取失败：{clean(data.get('respMsg')) or '未知原因'}"
                               f"（respCode={top_code}"
                               f"{'/code=' + inner_code if inner_code else ''}）")
            results.append(item)
            continue

        result = inner.get("result") or {}
        if not isinstance(result, dict):
            item["message"] = f"{name}：{clean(result) or '领取成功'}"
            item["ok"] = True
            results.append(item)
            continue

        item["lotteryId"] = result.get("lotteryId") or award.get("lotteryId")
        url, note = build_lottery_url(award)
        is_lottery = clean(award.get("awardType")) == "lotteryAward" or bool(result.get("needJump"))
        if is_lottery:
            item["ok"] = True
            item["lotteryUrl"] = url
            if url:
                item["message"] = f"{name}：抽奖机会已领取，抽奖入口已解析"
                log(f"   🎰 {note}")
                probe_lottery(url)
            else:
                item["message"] = f"{name}：抽奖机会已领取（服务端未下发抽奖入口，需在 App/小程序内手动打开）"
        else:
            item["ok"] = True
            item["message"] = f"{name}：{clean(result.get('result')) or '领取成功'}"
        results.append(item)
    return results


def build_lottery_url(award: Dict[str, Any]) -> Tuple[str, str]:
    """还原 H5 的抽奖入口地址。

    优先级与 H5 源码一致：
      1. 奖品对象顶层的 lotteryUrl（signAwardJump 用的就是它）
      2. awardDesc(JSON 字符串) 里的 lotteryUrl（received / getAwardListCallBack 用）
      3. 小程序内跳转字段 microJumpLink（goAwardSuccessAdJump 用）
    返回 (url, 说明文本)。
    """
    desc: Dict[str, Any] = {}
    raw = award.get("awardDesc")
    if raw:
        try:
            desc = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            desc = {}

    base = clean(award.get("lotteryUrl"), 800) or clean(desc.get("lotteryUrl"), 800)
    if base:
        sep = "&" if "?" in base else "?"
        url = (f"{base}{sep}signInGiftId={award.get('awardId')}"
               f"&signInActivityId={award.get('activityId')}&rewardId={award.get('id')}")
        return url, f"抽奖链接：{url}"

    micro = clean(award.get("microJumpLink"), 800)
    if micro:
        page = clean(award.get("microJumpPage"))
        return micro, f"抽奖入口（跳转方式 {page or 'micro'}）：{micro}"

    return "", "未在奖品下发字段里找到 lotteryUrl / microJumpLink"


def probe_lottery(url: str) -> None:
    """只读探测抽奖链接：仅当它是可直接访问的 http(s) 地址时才 GET 一次。

    目的是把真实抽奖页面记进日志，便于后续扩展；不伪造任何抽奖结果。
    """
    if not ENABLE_LOTTERY:
        return
    if not re.match(r"^https?://", url):
        log("      ↑ 非 http 地址，需在微信内打开（小程序页面路径）")
        return
    try:
        r = requests.get(url, headers={"User-Agent": _CURRENT_UA}, timeout=TIMEOUT, allow_redirects=True)
        log(f"      ↑ 该地址可直接访问：HTTP {r.status_code}")
        title = re.search(r"<title>(.*?)</title>", r.text or "", re.S | re.I)
        if title:
            log(f"      ↑ 页面标题：{clean(title.group(1), 80)}")
        dbg("抽奖页 HTML 片段:", clean(r.text, 400))
    except Exception as exc:
        log(f"      ↑ 探测失败（不影响领奖）：{clean(exc, 160)}")


def next_ladder(ladder: List[Dict[str, Any]], today: str) -> Optional[Dict[str, Any]]:
    """奖励阶梯里下一个未领取、且日期 >= 今天的档位。"""
    for item in ladder or []:
        date = clean(item.get("dateOfAward"))
        if item.get("isGain"):
            continue
        if date and date >= today:
            return item
    return None


def ladder_text(item: Optional[Dict[str, Any]]) -> str:
    if not item:
        return ""
    date = clean(item.get("dateOfAward"))
    detail = item.get("signAwardDetailDto") or {}
    if clean(item.get("prizeType")) == "mileageAward":
        reward = f"{item.get('num')} 里程"
    else:
        reward = "抽奖机会"
    label = clean(detail.get("pinpointAwardDateText")) or clean(item.get("rewardType"))
    return f"{date}　{reward}（{label or '连续签到奖励'}）"


def pinpoint_text(items: List[Dict[str, Any]]) -> str:
    """精准里程奖励：activity.load 的 pinpointAwardConfig，指定日期签到额外得里程。"""
    parts = []
    for it in items or []:
        date = clean(it.get("awardDate"))
        if not date:
            continue
        if clean(it.get("awardType")) == "mileageAward":
            parts.append(f"{date[5:]} +{it.get('mileage')}里程")
        else:
            parts.append(f"{date[5:]} {clean(it.get('awardName'))}")
    return "、".join(parts)


def next_pinpoint(items: List[Dict[str, Any]], today: str) -> Optional[Dict[str, Any]]:
    """下一个 >= 今天的精准奖励日。"""
    for it in sorted(items or [], key=lambda x: clean(x.get("awardDate"))):
        date = clean(it.get("awardDate"))
        if date and date >= today:
            return it
    return None


def award_content_text(items: List[Dict[str, Any]]) -> str:
    parts = []
    for it in items or []:
        name = clean(it.get("awardName"))
        status = clean(it.get("awardStatus"))
        if not name:
            continue
        mark = {"notComplete": "未达成", "complete": "可领取", "received": "已领取"}.get(status, status)
        day = clean(it.get("signDay"))
        parts.append(f"{name}{'（连签' + day + '天）' if day else ''}：{mark}")
    return "、".join(parts[:4])


def in_sign_window(activity: Dict[str, Any]) -> Tuple[bool, str]:
    """签到时段校验，如 08:00:00-23:59:59。"""
    rng = clean(activity.get("signTimeRange"))
    if not rng or "-" not in rng:
        return True, ""
    try:
        start_s, _, end_s = rng.partition("-")
        fmt = "%H:%M:%S"
        start = datetime.strptime(start_s.strip()[:8], fmt).time()
        end = datetime.strptime(end_s.strip()[:8], fmt).time()
    except Exception:
        return True, ""
    now = datetime.now().time()
    if start <= end:
        ok = start <= now <= end
    else:
        ok = now >= start or now <= end
    return ok, f"签到时段 {rng}"


# --------------------------------------------------------------------------- #
# 单账号流程
# --------------------------------------------------------------------------- #
def run_account(host: str, ref: str, label: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"label": label, "ref": ref}
    log(f"\n{'=' * 62}\n账号 {label}\n{'=' * 62}")
    try:
        client = login(host, ref)
    except SkipAccount as exc:
        log(f"   ⏭️ 跳过：{exc}")
        result.update(skipped=True, sign=f"跳过：{exc}")
        return result
    except Exception as exc:
        log(f"   ❌ 登录失败：{clean(exc, 220)}")
        result.update(error=f"登录失败：{clean(exc, 220)}")
        return result

    brief = fetch_member_brief(client)
    before_mileage = brief["mileage"]
    result["user"] = f"{brief['name']}　{brief['card']}".strip()
    log(f"   👤 {brief['name']}　{brief['card']}　里程 {before_mileage}")

    try:
        info = fetch_activity(client)
    except Exception as exc:
        log(f"   ❌ 活动信息获取失败：{clean(exc, 200)}")
        result.update(error=f"活动信息获取失败：{clean(exc, 200)}")
        return result

    activity = info["activity"]
    pinpoint = info.get("pinpoint") or []
    log(f"   📌 活动：{info['title']}（id={clean(activity.get('activityId'))}）")

    gold_before = fetch_gold(client)
    try:
        cal_before = fetch_calendar(client)
    except Exception as exc:
        dbg("日历读取失败", clean(exc))
        cal_before = {"signedDays": [], "ladder": [], "repairDays": []}
    awards_before = []
    try:
        awards_before = fetch_awards(client, "waitReceive")
    except Exception as exc:
        dbg("奖品读取失败", clean(exc))

    result["gold_before"] = gold_before
    result["mileage_before"] = before_mileage
    result["signed_before"] = len(cal_before.get("signedDays") or [])
    result["pending_before"] = len(awards_before)

    today = today_str()
    signed_today = today in (cal_before.get("signedDays") or [])
    log(f"   📅 本月已签 {result['signed_before']} 天"
        f"{'（今天已签）' if signed_today else ''}　连续 {serial_days(cal_before.get('serialDates') or [])} 天")
    if pinpoint:
        log(f"   🎁 精准里程奖励日：{pinpoint_text(pinpoint)}")

    # ---------------- 签到 ---------------- #
    sign_info: Dict[str, Any]
    if DRY_RUN:
        sign_info = {"status": "dry", "message": "干跑模式，未执行签到"}
    elif not ENABLE_SIGN:
        sign_info = {"status": "off", "message": "已关闭签到（NFHK_ENABLE_SIGN=0）"}
    elif signed_today:
        sign_info = {"status": "already", "message": "今天已经签到"}
    else:
        ok, note = in_sign_window(activity)
        if not ok:
            sign_info = {"status": "outwindow", "message": f"当前不在{note}"}
        else:
            try:
                sign_info = do_sign(client)
            except Exception as exc:
                sign_info = {"status": "fail", "message": f"签到异常：{clean(exc, 200)}"}
    result["sign"] = sign_info["message"]
    result["sign_status"] = sign_info["status"]
    log(f"   ✍️ 签到：{sign_info['message']}")

    # ---------------- 自动领奖 ---------------- #
    claimed = claim_awards(client)
    result["claimed"] = claimed
    for item in claimed:
        log(f"   🎁 {'✅' if item.get('ok') else '⚠️'} {item.get('message')}")

    # ---------------- 复查 ---------------- #
    brief_after = fetch_member_brief(client)
    after_mileage = brief_after["mileage"]
    gold_after = fetch_gold(client)
    try:
        cal_after = fetch_calendar(client)
    except Exception as exc:
        dbg("日历复查失败", clean(exc))
        cal_after = cal_before
    award_content = fetch_award_content(client)
    try:
        awards_after = fetch_awards(client, "waitReceive")
    except Exception:
        awards_after = []

    result["mileage_after"] = after_mileage
    result["gold_after"] = gold_after
    result["signed_after"] = len(cal_after.get("signedDays") or [])
    result["serial_days"] = serial_days(cal_after.get("serialDates") or [])
    result["pinpoint"] = pinpoint
    result["pinpoint_next"] = next_pinpoint(pinpoint, today)
    result["progress"] = fetch_progress(client)
    result["ladder_next"] = next_ladder(cal_after.get("ladder") or [], today)
    result["award_content"] = award_content
    result["pending_after"] = len(awards_after)

    delta = None
    if before_mileage is not None and after_mileage is not None:
        delta = round(after_mileage - before_mileage, 2)
    result["mileage_delta"] = delta
    log(f"   💎 里程：{before_mileage} → {after_mileage}"
        f"{f'（本日 {delta:+}）' if delta is not None else ''}　金币：{gold_before} → {gold_after}")
    if result["ladder_next"]:
        log(f"   🎯 下一档：{ladder_text(result['ladder_next'])}")
    if award_content:
        log(f"   🎟️ 奖励条件：{award_content_text(award_content)}")

    result["success"] = sign_info["status"] not in ("fail",)
    if sign_info["status"] == "fail":
        result["error"] = sign_info["message"]
    return result


# --------------------------------------------------------------------------- #
# 通知
# --------------------------------------------------------------------------- #
def load_notify():
    candidates = [
        Path(HERE) / "notify.py",
        Path("/ql/data/scripts/notify.py"),
        Path("/ql/scripts/notify.py"),
        Path("/ql/data/notify.py"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("nfhk_qinglong_notify", path)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(module)
            for name in ("send", "sendNotify"):
                func = getattr(module, name, None)
                if callable(func):
                    return func
        except Exception as exc:
            print(f"⚠️ [通知] 加载 {path} 失败：{clean(exc, 120)}")
    return None


# 青龙 notify.py 认得的推送变量（常见子集）。面板只认这些名字，
# 少写一个下划线（如 PLUSPLUS_TOKEN）notify.py 就会打印「无推送渠道」。
QL_PUSH_ENVS = (
    "BARK_PUSH", "DD_BOT_TOKEN", "FSKEY", "GOBOT_URL", "IGOT_PUSH_KEY", "PUSH_KEY",
    "DEER_KEY", "CHAT_URL", "PUSH_PLUS_TOKEN", "WE_PLUS_BOT_TOKEN", "QMSG_KEY",
    "QYWX_KEY", "QYWX_AM", "TG_BOT_TOKEN", "SMTP_SERVER", "PUSHME_KEY",
    "WEBHOOK_URL", "NTFY_TOPIC", "WXPUSHER_APP_TOKEN", "OPENILINK_APP_TOKEN",
)


def send_notify(title: str, content: str) -> None:
    panel_channel = next((k for k in QL_PUSH_ENVS if (os.getenv(k) or "").strip()), "")
    sender = load_notify()
    if sender is not None:
        if panel_channel:
            try:
                sender(title, content)
                log(f"✅ [通知] 已通过青龙通知模块发送（通道 {panel_channel}）")
                return
            except Exception as exc:
                log(f"⚠️ [通知] 青龙通知发送失败（不影响结果）：{clean(exc, 120)}")
        else:
            log("ℹ️ [通知] 青龙面板未配置推送变量，notify.py 只会打印「无推送渠道」，改用脚本自带通道")
    else:
        log("⚠️ [通知] 未找到青龙 notify.py，使用脚本自带通道")

    sent = False
    plusplus = (os.getenv("PUSH_PLUS_TOKEN", "") or os.getenv("PLUSPLUS_TOKEN", "") or "").strip()
    if plusplus:
        try:
            r = requests.post("https://www.pushplus.plus/send",
                              json={"token": plusplus, "title": title, "content": content,
                                    "template": "txt"}, timeout=20)
            ok = r.status_code == 200 and (r.json().get("code") == 200)
            sent = sent or ok
            log(f"{'✅' if ok else '❌'} [通知] PushPlus 发送{'成功' if ok else '失败：' + clean(r.text, 120)}")
        except Exception as exc:
            log(f"❌ [通知] PushPlus 发送失败：{clean(exc, 120)}")
    server_push = (os.getenv("PUSH_KEY", "") or os.getenv("SERVERPUSHKEY", "") or "").strip()
    if server_push and not sent:
        try:
            requests.post(f"https://sctapi.ftqq.com/{server_push}.send",
                          data={"title": title, "desp": content}, timeout=15)
            sent = True
            log("✅ [通知] Server 酱发送成功")
        except Exception as exc:
            log(f"❌ [通知] Server 酱发送失败：{clean(exc, 120)}")
    qywx = (os.getenv("QYWX_KEY", "") or os.getenv("QYWX_TOKEN", "") or "").strip()
    if qywx and not sent:
        try:
            requests.post(f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={qywx}",
                          json={"msgtype": "text",
                                "text": {"content": f"{title}\n\n{content}"}}, timeout=15)
            sent = True
            log("✅ [通知] 企业微信机器人发送成功")
        except Exception as exc:
            log(f"❌ [通知] 企业微信机器人发送失败：{clean(exc, 120)}")
    bark = (os.getenv("BARK_PUSH", "") or "").strip()
    if bark and not sent:
        try:
            requests.post(bark.rstrip("/"), json={"title": title, "body": content}, timeout=15)
            sent = True
            log("✅ [通知] Bark 发送成功")
        except Exception as exc:
            log(f"❌ [通知] Bark 发送失败：{clean(exc, 120)}")
    if not sent:
        log("ℹ️ [通知] 未配置任何可用推送通道，结果仅输出到日志")


def fmt_mileage(item: Dict[str, Any]) -> str:
    before, after = item.get("mileage_before"), item.get("mileage_after")
    if before is None and after is None:
        return "-"
    if before is None:
        return f"{after}"
    if after is None:
        return f"{before}"
    delta = item.get("mileage_delta")
    if delta is None:
        delta = after - before
    head = f"{_num(before)} → {_num(after)}"
    if delta:
        head += f"（本日 {'+' if delta > 0 else ''}{_num(delta)}）"
    else:
        head += "（本日 +0）"
    return head


def _num(value: Any) -> str:
    """里程是浮点，整数就不显示小数。"""
    try:
        f = float(value)
        return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def icon_for(item: Dict[str, Any]) -> str:
    if item.get("skipped"):
        return "⏭️"
    if item.get("error"):
        return "❌"
    status = item.get("sign_status")
    if status in ("ok", "already"):
        return "✅"
    if status in ("dry", "off"):
        return "🧪"
    return "⚠️"


def build_report(results: List[Dict[str, Any]]) -> str:
    lines = [f"✈️ {APP_NAME}｜{now_text()}", ""]
    for item in results:
        lines.append(f"{icon_for(item)} {item['label']}　{item.get('user') or ''}")
        if item.get("skipped"):
            lines.append(f"    ⏭️ {item.get('sign')}")
            lines.append("")
            continue
        if item.get("error") and not item.get("sign"):
            lines.append(f"    ❌ {item['error']}")
            lines.append("")
            continue
        lines.append(f"    ✍️ 签到：{item.get('sign')}")
        lines.append(f"    💎 里程（积分）：{fmt_mileage(item)}")
        gold_b, gold_a = item.get("gold_before"), item.get("gold_after")
        if gold_b not in (None, "--") or gold_a not in (None, "--"):
            lines.append(f"    🪙 金币：{gold_b} → {gold_a}")
        lines.append(f"    📅 本月已签 {item.get('signed_after')} 天"
                     f"　连续 {item.get('serial_days')} 天")
        if item.get("ladder_next"):
            lines.append(f"    🎯 下一档：{ladder_text(item['ladder_next'])}")
        nxt = item.get("pinpoint_next")
        if nxt:
            lines.append(f"    🎁 最近的精准里程日：{clean(nxt.get('awardDate'))[5:]} 签到"
                         f" +{nxt.get('mileage')} 里程")
        if item.get("award_content"):
            lines.append(f"    🎟️ 奖励条件：{award_content_text(item['award_content'])}")
        for claimed in item.get("claimed") or []:
            lines.append(f"    {'🎁' if claimed.get('ok') else '⚠️'} {claimed.get('message')}")
            if claimed.get("lotteryUrl"):
                lines.append(f"        🎰 抽奖链接：{claimed['lotteryUrl']}")
        if item.get("error") and item.get("sign"):
            lines.append(f"    ❌ {item['error']}")
        lines.append("")

    ok = sum(1 for i in results if i.get("success") and not i.get("skipped"))
    skipped = sum(1 for i in results if i.get("skipped"))
    failed = len(results) - ok - skipped
    tail = f"🏁 汇总：{ok} 成功"
    if skipped:
        tail += f" / {skipped} 非会员已跳过"
    tail += f" / {failed} 失败（共 {len(results)} 个账号）"
    lines.append(tail)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def main() -> int:
    log(f"===== {APP_NAME}｜{now_text()} =====")
    if DRY_RUN:
        log("🧪 干跑模式（NFHK_DRY_RUN=1），只查询不签到")

    raw = (os.getenv("YYB_SERVER", "") or "").strip()
    if not raw:
        log("❌ 未配置环境变量 YYB_SERVER（格式：yyb-go:8000@1，多账号每行一条）")
        return 1
    accounts = parse_ref_list(raw)
    if not accounts:
        log("❌ YYB_SERVER 解析后没有可用账号")
        return 1
    log(f"共 {len(accounts)} 个账号")

    results: List[Dict[str, Any]] = []
    for idx, (host, ref) in enumerate(accounts, 1):
        try:
            results.append(run_account(host, ref, f"[{idx}] {ref}"))
        except Exception as exc:                      # 兜底，单账号异常不影响其它账号
            log(f"   ❌ 账号 {ref} 异常：{clean(exc, 220)}")
            results.append({"label": f"[{idx}] {ref}", "error": f"异常：{clean(exc, 220)}"})

    report = build_report(results)
    log("\n" + "=" * 62)
    log(report)
    log("=" * 62)

    try:
        send_notify(APP_NAME, report)
    except Exception as exc:
        log(f"⚠️ 通知发送异常（不影响结果）：{clean(exc, 160)}")

    failed = [r for r in results if not r.get("skipped") and not r.get("success")]
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⏹️ 已手动中断")
        sys.exit(130)
