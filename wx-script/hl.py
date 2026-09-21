#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name: 哈啰出行
# cron: 35 8 * * *
"""
name: 哈啰出行签到
cron: 35 8 * * *

哈啰出行微信小程序每日签到与奖励金查询，基于 YYB-Go-Enhanced 自动取码登录。

环境变量：
  YYB_SERVER     必填，格式：YYB-Go-Enhanced 地址@微信账号标识；多账号每行一条
  YYB_API_KEY    可选，YYB 协议令牌
  HL_DRY_RUN     可选，=1 时仅查询，不执行签到
  HL_ENABLE_SIGN 可选，默认 1；=0 时仅查询奖励金

功能仅包含：静默登录、每日签到、签到前后奖励金对比、钱包余额查询与通知。
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:
    print("❌ 缺少依赖：pip install requests")
    sys.exit(1)

APP_NAME = "哈啰出行签到"
HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
APP_NO = "wxb937e3d0b3ca117e"                 # 哈啰出行小程序 AppID
MP_VERSION = "358"                            # 小程序版本号（仅用于 Referer）
API_BASE = "https://api.hellobike.com/api"    # 小程序接口域
MKT_BASE = "https://marketingapi.hellobike.com/api"

ACT_LOGIN = "user.account.weixinEasyLogin"
ACT_SIGN = "common.welfare.signAndRecommend"
ACT_SIGN_INFO = "common.welfare.signInfo"
ACT_POINT = "user.taurus.pointInfo"
ACT_WALLET = "user.wallet.account"
ACT_USER = "user.account.getInfo"

SYS_CODE = 64                                 # 微信小程序渠道
H5_SYSTEM_CODE = 62                           # 奖励金/福利中心 H5 渠道
H5_VERSION = "6.46.0"                         # H5 版本号（服务端只做弱校验）
# --------------------------------------------------------------------------- #
# 开关
# --------------------------------------------------------------------------- #
DRY_RUN = os.getenv("HL_DRY_RUN", "").strip() == "1"
ENABLE_SIGN = os.getenv("HL_ENABLE_SIGN", "1").strip() != "0"
DEBUG = os.getenv("HL_DEBUG", "").strip() == "1"
RANDOM_HEADERS = os.getenv("HL_RANDOM_HEADERS", "1").strip() != "0"
UA_MODE = (os.getenv("HL_UA_MODE", "run").strip() or "run").lower()
LOGIN_RETRY = max(1, int(os.getenv("HL_LOGIN_RETRY", "3") or 3))
YYB_TIMEOUT = float(os.getenv("YYB_REQUEST_TIMEOUT", "40") or 40)
HTTP_TIMEOUT = float(os.getenv("HL_HTTP_TIMEOUT", "25") or 25)

# --------------------------------------------------------------------------- #
# 随机请求头
# --------------------------------------------------------------------------- #
UA_POOL = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.53(0x18003528) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.55(0x18003728) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (Linux; Android 14; V2309A Build/UP1A.231005.007; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/122.0.6261.120 Mobile Safari/537.36 XWEB/1220093 "
    "MMWEBSDK/20240301 MicroMessenger/8.0.50.2701(0x2800323D) WeChat/arm64 Weixin NetType/WIFI "
    "Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 13; PGT110 Build/TKQ1.220829.002; wv) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 XWEB/1160065 "
    "MMWEBSDK/20231202 MicroMessenger/8.0.49.2600(0x28003133) WeChat/arm64 Weixin NetType/WIFI "
    "Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) "
    "WindowsWechat(0x63090b19) XWEB/11581",
]
_RUN_UA = ""


def pick_user_agent() -> str:
    global _RUN_UA
    if UA_MODE == "request" or not _RUN_UA:
        _RUN_UA = random.choice(UA_POOL)
    return _RUN_UA


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def mask_phone(value: Any) -> str:
    text = str(value or "").strip()
    return f"{text[:3]}****{text[-4:]}" if len(text) == 11 else (text or "-")


def preview(data: Any, limit: int = 300) -> str:
    try:
        text = json.dumps(data, ensure_ascii=False)
    except Exception:
        text = str(data)
    return text[:limit]


def b32(value: Any) -> str:
    """清洗文本：去掉引号/换行等，避免日志与通知里出现脏名字。"""
    text = str(value or "").strip()
    text = text.strip("\"'` \t\r\n\u200b")
    return text


def day_index(bonus_list: Any) -> Optional[int]:
    """从 bonusList 里找出「今天」是第几天（hasDaySign=True 的那一格）。"""
    if not isinstance(bonus_list, list):
        return None
    for idx, item in enumerate(bonus_list):
        if isinstance(item, dict) and item.get("hasDaySign"):
            return idx + 1
    return None


def as_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def as_num(value: Any) -> Optional[float]:
    """宽容取数（接口里奖励金偶尔是 "20.0" 这种字符串）。"""
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def fmt_num(value: Any) -> str:
    """整数不带小数点，非整数保留原样。"""
    num = as_num(value)
    if num is None:
        return "-"
    return str(int(num)) if float(num).is_integer() else ("%g" % num)


def banner(lines: List[str]) -> None:
    print("=" * 78)
    for line in lines:
        print(line)
    print("=" * 78)


def deep_first(node: Any, key: str) -> Any:
    if isinstance(node, dict):
        if node.get(key) not in (None, ""):
            return node[key]
        for value in node.values():
            found = deep_first(value, key)
            if found not in (None, ""):
                return found
    elif isinstance(node, list):
        for item in node:
            found = deep_first(item, key)
            if found not in (None, ""):
                return found
    return None


# --------------------------------------------------------------------------- #
# 账号配置
# --------------------------------------------------------------------------- #
class AccountTarget:
    def __init__(self, endpoint: str = "", ref: str = "", index: int = 0):
        self.endpoint = normalize_endpoint(endpoint) if endpoint else ""
        self.ref = str(ref or "")
        self.index = index
        self.label_suffix = ""

    @property
    def yyb_base(self) -> str:
        return self.endpoint

    @property
    def label(self) -> str:
        number = self.ref if self.ref else str(self.index or "?")
        suffix = f"（{self.label_suffix}）" if self.label_suffix else ""
        return f"账号 {number}{suffix}"

    @property
    def server(self) -> str:
        return f"{self.endpoint}@{self.ref}" if self.endpoint and self.ref else "未配置 YYB_SERVER"


def normalize_endpoint(value: str) -> str:
    text = (value or "").strip().rstrip("/")
    if not text:
        return ""
    if not re.match(r"^https?://", text, re.I):
        text = "http://" + text
    return text


def load_accounts() -> List[AccountTarget]:
    raw = os.getenv("YYB_SERVER", "").strip()
    accounts: List[AccountTarget] = []
    if raw:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "@" not in line:
                print(f"⚠️ [配置] 忽略无账号标识的行：{line}")
                continue
            endpoint, ref = (part.strip() for part in line.rsplit("@", 1))
            if not endpoint or not ref:
                print(f"⚠️ [配置] 忽略不完整行：{line}")
                continue
            accounts.append(AccountTarget(endpoint=endpoint, ref=ref, index=len(accounts) + 1))
    if not accounts:
        raise RuntimeError(
            "未读取到有效账号。请配置环境变量 YYB_SERVER，每行一个账号，格式：\n"
            "  YYB地址@账号ID      例：yyb-go:8000@1\n"
            "  多账号就是多行（第 2 个账号写 @2，以此类推）"
        )
    return accounts


# --------------------------------------------------------------------------- #
# YYB 调用
# --------------------------------------------------------------------------- #
def yyb_post(account: AccountTarget, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = account.yyb_base + path
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "okhttp/3.12.13"}
    api_key = os.getenv("YYB_API_KEY", "").strip() or os.getenv("YYB_PROTOCOL_TOKEN", "").strip()
    if api_key:
        headers["Authorization"] = api_key if " " in api_key else "Bearer " + api_key
    resp = requests.post(url, json=payload, headers=headers, timeout=YYB_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    if DEBUG:
        print(f"    · [YYB] {path} → {preview(body, 400)}")
    if isinstance(body, dict) and body.get("code") not in (0, None):
        raise RuntimeError(f"YYB {path} 返回错误：{body.get('msg') or preview(body)}")
    return body


def yyb_get_wx_code(account: AccountTarget) -> Dict[str, str]:
    """取 wx.login code（一次性，拿到后需尽快使用）+ 微信 openid。"""
    body = yyb_post(account, "/wxapp/getCode", {"ref": account.ref, "app_id": APP_NO})
    data = body.get("data") or {}
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    code = ""
    for candidate in (result.get("code"), data.get("code"), deep_first(body, "code")):
        if isinstance(candidate, str) and len(candidate) >= 16:
            code = candidate
            break
    if not code:
        raise RuntimeError(f"YYB 未返回有效 code：{preview(body, 200)}")
    nickname = b32((data.get("account") or {}).get("nickname")) or b32(
        (data.get("account") or {}).get("alias"))
    return {"code": code, "openid": b32(data.get("openid")), "nickname": nickname}


# --------------------------------------------------------------------------- #
# 哈啰客户端
# --------------------------------------------------------------------------- #
class NotBoundError(RuntimeError):
    """微信账号尚未绑定哈啰账号 —— 重试无意义。"""


class HlClient:
    """哈啰接口客户端：静默登录 + 福利中心/奖励金业务请求。"""

    def __init__(self, account: AccountTarget):
        self.account = account
        self.session = requests.Session()
        self.token = ""
        self.user: Dict[str, Any] = {}
        self.openid = ""

    # ---------------- 底层请求 ----------------
    def headers(self) -> Dict[str, str]:
        head = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": pick_user_agent(),
            "Origin": "https://servicewechat.com",
            "Referer": f"https://servicewechat.com/{APP_NO}/{MP_VERSION}/page-frame.html",
        }
        if RANDOM_HEADERS:
            head["Accept-Language"] = random.choice(
                ["zh-CN,zh;q=0.9", "zh-CN,zh-Hans;q=0.9", "zh-Hans-CN;q=1, zh-Hans;q=0.9"])
        return head

    def post(self, action: str, payload: Optional[Dict[str, Any]] = None,
             host: str = API_BASE) -> Dict[str, Any]:
        body: Dict[str, Any] = {"action": action}
        if payload:
            body.update(payload)
        url = f"{host}?{action}"
        resp = self.session.post(url, data=json.dumps(body, ensure_ascii=False),
                                 headers=self.headers(), timeout=HTTP_TIMEOUT)
        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"{action} 返回非 JSON（HTTP {resp.status_code}）：{resp.text[:200]}")
        if DEBUG:
            print(f"    · [{action}] {preview(data, 500)}")
        return data

    # ---------------- 登录 ----------------
    def _silent_login_once(self) -> Dict[str, Any]:
        info = yyb_get_wx_code(self.account)
        self.openid = info["openid"]
        if info.get("nickname"):
            self.account.label_suffix = info["nickname"][:12]
        payload = {
            "iv": None,
            "encryptedData": None,
            "wechatLoginCode": info["code"],
            "pageName": "pages/index/index",
            "city": "",
            "adCode": "",
            "cityCode": "",
            "channel": 0,
            "flagType": "WECHAT_SEAMLESS",
            "systemCode": SYS_CODE,
            "extendValue": json.dumps({"openId": info["openid"]}, separators=(",", ":")),
            "ssid": "",
        }
        res = self.post(ACT_LOGIN, payload)
        code = res.get("code")
        if code == 0:
            data = res.get("data") or {}
            token = b32(data.get("token"))
            if not token:
                raise RuntimeError(f"登录成功但未返回 token：{preview(res, 200)}")
            self.token = token
            self.user = data
            return data
        if code == 71000:
            raise NotBoundError("该微信尚未注册/绑定哈啰账号（登录失败！）")
        raise RuntimeError(f"登录失败：{res.get('code')} {res.get('msg') or preview(res, 160)}")

    def login(self) -> Dict[str, Any]:
        last: Optional[Exception] = None
        for attempt in range(1, LOGIN_RETRY + 1):
            try:
                return self._silent_login_once()
            except NotBoundError:
                raise
            except Exception as exc:
                last = exc
                print(f"    ⚠️ 第 {attempt}/{LOGIN_RETRY} 次登录失败：{preview(exc, 160)}")
                if attempt < LOGIN_RETRY:
                    time.sleep(random.uniform(1.5, 3.0))
        raise last if last else RuntimeError("登录失败")

    # ---------------- 业务 ----------------
    def _h5_payload(self) -> Dict[str, Any]:
        return {"from": "h5", "platform": 4, "version": H5_VERSION, "token": self.token}

    def point_info(self) -> Dict[str, Any]:
        body = self._h5_payload()
        body.update({"action": ACT_POINT, "systemCode": 61, "pointType": 1})
        return self.post(ACT_POINT, body)

    def sign_info(self) -> Dict[str, Any]:
        body = self._h5_payload()
        body.update({"action": ACT_SIGN_INFO, "systemCode": H5_SYSTEM_CODE, "pointType": 1})
        return self.post(ACT_SIGN_INFO, body)

    def do_sign(self) -> Dict[str, Any]:
        body = self._h5_payload()
        body.update({"action": ACT_SIGN, "systemCode": H5_SYSTEM_CODE, "pointType": 1})
        return self.post(ACT_SIGN, body)

    def wallet(self) -> Dict[str, Any]:
        return self.post(ACT_WALLET, {"token": self.token})

    def user_info(self) -> Dict[str, Any]:
        return self.post(ACT_USER, {"token": self.token})



# --------------------------------------------------------------------------- #
# 单账号执行
# --------------------------------------------------------------------------- #
def points_of(node: Dict[str, Any]) -> Optional[int]:
    data = node.get("data") if isinstance(node, dict) else None
    if not isinstance(data, dict):
        return None
    if "points" in data:
        return as_int(data.get("points"))
    if "accountBalance" in data:
        return None
    return None


def amount_of(node: Dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node, dict) else None
    if not isinstance(data, dict):
        return ""
    if data.get("amount") not in (None, ""):
        return str(data.get("amount"))
    return ""


# 「看视频」类任务的市场计划 / 任务类型（都走微信激励视频，脚本无法代做）
VIDEO_MARKET_PLANS = {"incentive_video_scheme"}
VIDEO_TASK_TYPES = {"meal_subsidy", "sleeping_subsidy"}


def run_account(index: int, total: int, account: AccountTarget) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "label": account.label, "server": account.server, "success": False, "skipped": False,
        "user": "-", "sign": "-", "bonus": "-", "title": "", "extra": "",
        "points_before": None, "points_after": None, "points_delta": None,
        "amount_before": "", "amount_after": "", "wallet": "", "continuous": "-",
        "sign_source": "", "error": "",
    }
    print(f"\n{'─' * 78}")
    print(f"▶️ [{index}/{total}] {account.label}　←　{account.server}")

    client = HlClient(account)
    try:
        user = client.login()
        result["label"] = account.label
        mobile = b32(user.get("mobile"))
        result["user"] = f"{mask_phone(mobile)}"
        print(f"    ✅ 登录成功：{account.label}　手机号 {mask_phone(mobile)}　"
              f"userNewId={b32(user.get('userNewId'))}")
    except NotBoundError as exc:
        result["label"] = account.label
        result["skipped"] = True
        result["sign"] = f"该微信未绑定哈啰账号，已跳过（{exc}）"
        print(f"    ⏭️ {account.label}：{exc}")
        return result
    except Exception as exc:
        result["error"] = f"登录异常：{exc}"
        print(f"    ❌ {account.label} 登录异常：{exc}")
        return result

    # ---- 初始奖励金 ----
    try:
        before = client.point_info()
        result["points_before"] = points_of(before)
        result["amount_before"] = amount_of(before)
        print(f"    💰 签到前奖励金：{result['points_before']}　"
              f"≈{result['amount_before'] or '-'} 元")
    except Exception as exc:
        print(f"    ⚠️ 查询奖励金失败：{preview(exc, 160)}")

    # ---- 签到状态 ----
    sign_state: Dict[str, Any] = {}
    try:
        info = client.sign_info()
        sign_state = info.get("data") or {}
        result["title"] = b32(sign_state.get("title"))
        result["extra"] = b32(sign_state.get("extraRewardBtnText"))
        day = day_index(sign_state.get("bonusList"))
        result["continuous"] = f"第 {day}/7 天" if day else "-"
        print(f"    📋 签到状态：{'今日已签到' if sign_state.get('didSignToday') else '今日未签到'}"
              f"　今日奖励金 {sign_state.get('bountyCountToday') or '-'}"
              f"　{result['continuous']}　{result['title']}")
    except Exception as exc:
        print(f"    ⚠️ 查询签到状态失败：{preview(exc, 160)}")

    # ---- 签到 ----
    if DRY_RUN:
        result["sign"] = "DRY_RUN：未执行签到"
        result["success"] = True
    elif not ENABLE_SIGN:
        result["sign"] = "已关闭签到（HL_ENABLE_SIGN=0）"
        result["success"] = True
    else:
        try:
            res = client.do_sign()
            data = res.get("data") or {}
            if res.get("code") != 0:
                result["sign"] = f"签到接口返回异常：{res.get('code')} {res.get('msg') or ''}".strip()
                print(f"    ❌ {result['sign']}")
            else:
                did = bool(data.get("didSignToday"))
                this_time = bool(data.get("doSignThisTime"))
                today_bonus = b32(data.get("bountyCountToday"))
                result["title"] = b32(data.get("title")) or result["title"]
                result["extra"] = b32(data.get("extraRewardBtnText")) or result["extra"]
                bonus_list = data.get("bonusList") or []
                if isinstance(bonus_list, list) and bonus_list:
                    src = b32((bonus_list[0] or {}).get("signSource"))
                    result["sign_source"] = src
                    result["bonus"] = f"{today_bonus} 奖励金"
                day = day_index(bonus_list)
                result["continuous"] = f"第 {day}/7 天" if day else "-"
                if this_time:
                    result["sign"] = f"签到成功，+{today_bonus} 奖励金（{result['continuous']}）"
                    result["success"] = True
                elif did:
                    result["sign"] = (f"今日已签到（本次不重复发放，+0 奖励金，"
                                      f"{result['continuous']}）")
                    result["success"] = True
                else:
                    result["sign"] = "签到未生效，请检查账号状态"
                    print(f"    ⚠️ 上游返回：{preview(data, 400)}")
                print(f"    ✍️ {result['sign']}　{result['title']}")
        except Exception as exc:
            result["sign"] = f"签到异常：{exc}"
            print(f"    ❌ {result['sign']}")

    # ---- 最终奖励金 ----
    try:
        time.sleep(random.uniform(1.0, 2.0))
        after = client.point_info()
        result["points_after"] = points_of(after)
        result["amount_after"] = amount_of(after)
        if result["points_before"] is not None and result["points_after"] is not None:
            result["points_delta"] = result["points_after"] - result["points_before"]
        print(f"    💰 签到后奖励金：{result['points_after']}　"
              f"≈{result['amount_after'] or '-'} 元")
    except Exception as exc:
        print(f"    ⚠️ 查询最终奖励金失败：{preview(exc, 160)}")

    # ---- 钱包余额（附赠信息）----
    try:
        w = client.wallet()
        wd = w.get("data") or {}
        if wd.get("accountBalance") not in (None, ""):
            result["wallet"] = f"{wd.get('accountBalance')} 元"
    except Exception:
        pass

    if not result["success"] and not result["error"] and result["sign"] != "-":
        result["success"] = True if result["points_delta"] is not None else result["success"]
    return result


# --------------------------------------------------------------------------- #
# 汇总与通知
# --------------------------------------------------------------------------- #
def _icon(item: Dict[str, Any]) -> str:
    if item.get("skipped"):
        return "⏭️"
    return "✅" if item.get("success") else "❌"


def fmt_points(item: Dict[str, Any]) -> str:
    """奖励金「初始 → 最终（+变化）」文本。"""
    before = item.get("points_before")
    after = item.get("points_after")
    if before is None and after is None:
        return "-"
    if before is None or after is None:
        return f"{after if after is not None else before}"
    delta = item.get("points_delta")
    if delta is None:
        delta = after - before
    money_b = item.get("amount_before") or ""
    money_a = item.get("amount_after") or ""
    tail = f"　≈{money_b} → {money_a} 元" if (money_b or money_a) else ""
    return f"{before} → {after}（{'+' if delta >= 0 else ''}{delta}）{tail}"


def build_report(results: List[Dict[str, Any]]) -> str:
    lines = [f"🚲 {APP_NAME}｜{now_text()}", ""]
    for item in results:
        lines.append(f"{_icon(item)} {item['label']}　{item.get('user') or ''}")
        if item.get("skipped"):
            lines.append(f"    ⏭️ {item['sign']}")
            lines.append("")
            continue
        if item.get("error"):
            lines.append(f"    ❌ {item['error']}")
        lines.append(f"    ✍️ 签到：{item['sign']}")
        if item.get("title"):
            lines.append(f"    🎁 连签进度：{item['title']}")
        lines.append(f"    💰 奖励金：{fmt_points(item)}")
        if item.get("wallet"):
            lines.append(f"    👛 钱包余额：{item['wallet']}")
        lines.append("")
    ok = sum(1 for i in results if i.get("success") and not i.get("skipped"))
    skipped = sum(1 for i in results if i.get("skipped"))
    failed = len(results) - ok - skipped
    tail = f"🏁 汇总：{ok} 成功"
    if skipped:
        tail += f" / {skipped} 未绑定已跳过"
    tail += f" / {failed} 失败（共 {len(results)} 个账号）"
    lines.append(tail)
    return "\n".join(lines)


def load_notify():
    """兼容青龙各版本的 notify.py 位置（脚本目录 / 订阅目录 / 根目录）。"""
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
            spec = importlib.util.spec_from_file_location("hl_qinglong_notify", path)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(module)
            for name in ("send", "sendNotify"):
                func = getattr(module, name, None)
                if callable(func):
                    return func
        except Exception as exc:
            print(f"⚠️ [通知] 加载 {path} 失败：{preview(exc, 120)}")
    return None


def send_notify(title: str, content: str) -> None:
    sender = load_notify()
    if sender is not None:
        try:
            sender(title, content)
            print("✅ [通知] 已通过青龙通知模块发送")
            return
        except Exception as exc:
            print(f"⚠️ [通知] 青龙通知发送失败（不影响结果）：{preview(exc, 120)}")
    else:
        print("⚠️ [通知] 未找到青龙 notify.py，尝试兜底通道")

    sent = False
    plusplus = os.getenv("PLUSPLUS_TOKEN", "").strip()
    if plusplus:
        try:
            requests.post("https://www.pushplus.plus/send",
                          json={"token": plusplus, "title": title, "content": content,
                                "template": "txt"}, timeout=15)
            print("✅ [通知] PushPlus 发送成功")
            sent = True
        except Exception as exc:
            print(f"❌ [通知] PushPlus 发送失败：{exc}")

    server_push = os.getenv("PUSH_KEY", "").strip() or os.getenv("SERVERPUSHKEY", "").strip()
    if server_push and not sent:
        try:
            requests.post(f"https://sctapi.ftqq.com/{server_push}.send",
                          data={"title": title, "desp": content}, timeout=15)
            print("✅ [通知] Server 酱发送成功")
            sent = True
        except Exception as exc:
            print(f"❌ [通知] Server 酱发送失败：{exc}")

    qywx = os.getenv("QYWX_KEY", "").strip() or os.getenv("QYWX_TOKEN", "").strip()
    if qywx and not sent:
        try:
            requests.post(f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={qywx}",
                          json={"msgtype": "text", "text": {"content": f"{title}\n\n{content}"}},
                          timeout=15)
            print("✅ [通知] 企业微信机器人发送成功")
            sent = True
        except Exception as exc:
            print(f"❌ [通知] 企业微信机器人发送失败：{exc}")

    bark = os.getenv("BARK_PUSH", "").strip()
    if bark and not sent:
        try:
            requests.post(bark.rstrip("/"), json={"title": title, "body": content}, timeout=15)
            print("✅ [通知] Bark 发送成功")
            sent = True
        except Exception as exc:
            print(f"❌ [通知] Bark 发送失败：{exc}")

    if not sent:
        print("ℹ️ [通知] 未配置任何可用推送通道，结果仅输出到日志")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def main() -> int:
    banner([
        f"🚲 {APP_NAME}",
        f"🕒 启动时间: {now_text()}",
        f"🆔 小程序  : {APP_NO}",
        f"🧪 DRY_RUN : {'开启（只查询）' if DRY_RUN else '关闭'}",
        f"🔐 登录    : YYB 取码 → weixinEasyLogin 静默登录（无需抓包）",
        f"✍️ 签到    : " + ("开启" if ENABLE_SIGN else "关闭（HL_ENABLE_SIGN=0）"),
    ])

    try:
        accounts = load_accounts()
    except Exception as exc:
        print(f"❌ [配置] {exc}")
        send_notify(f"❌ {APP_NAME} 配置错误", str(exc))
        return 1

    print(f"✅ 共读取到 {len(accounts)} 个账号")
    for account in accounts:
        print(f"   · {account.label}　←　{account.server}")

    results: List[Dict[str, Any]] = []
    for index, account in enumerate(accounts, 1):
        try:
            results.append(run_account(index, len(accounts), account))
        except Exception as exc:
            print(f"❌ [主程序] {account.label} 执行异常：{exc}")
            results.append({
                "label": account.label, "server": account.server, "success": False,
                "skipped": False, "user": "-", "sign": "-", "bonus": "-", "title": "",
                "extra": "", "points_before": None, "points_after": None, "points_delta": None,
                "amount_before": "", "amount_after": "", "wallet": "", "continuous": "-",
                "sign_source": "", "error": str(exc), "tasks": None,
            })
        if index < len(accounts):
            time.sleep(random.uniform(3.0, 6.0))

    report = build_report(results)
    print()
    print(report)

    prefix = "🧪 " if DRY_RUN else ""
    send_notify(f"{prefix}{APP_NAME} {now_text()}", report)

    failed = sum(1 for item in results if not item["success"] and not item["skipped"])
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⏹️ 已手动中断")
        sys.exit(130)
