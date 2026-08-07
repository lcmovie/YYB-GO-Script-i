#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
------------------------------------------
@Author: sm
@Date: 2026.07.24
@Description: 善羿科技/YSKJ 微信小程序每日签到（微信协议版，适配青龙）

cron: 12 7,13,20 * * *

变量名：WX_ID
变量值：微信账号（openid/wxid），多账号支持换行、& 分隔，必须配置

------------------------------------------

变量：
  WX_ID         微信账号（openid/wxid），多账号支持换行、& 分隔，必须配置
  WX_APP_ID     小程序 AppID（可选，默认 wxc59eee06736849e8）
  WECHAT_SERVER 牛子协议服务地址（可选）
  YYB_SERVER    应用宝服务地址（可选）

WX_ID 格式：
  wxid#备注  多个换行

说明：
  经本目录 getCode.py 统一接口（牛子/应用宝双协议）使用 WX_ID 自动获取
  wx.login code，无需手动抓包；登录 token 按 wxid 持久化到 .shanm_token.json，
  失效自动重新登录。
------------------------------------------
"""

import json
import hashlib
import os
import random
import sys
import time
import uuid
from typing import Any, Dict, List, Tuple

try:
    import requests
except ImportError:
    print("缺少 requests 依赖，请在青龙容器中执行: pip3 install requests")
    sys.exit(1)

try:
    from getCode import get_single_code
except ImportError:
    get_single_code = None


BASE_URL = "https://net.todaypayforyou.fun/YSKJ/api"
REFERER = "https://servicewechat.com/wxc59eee06736849e8/4/page-frame.html"
WX_APP_ID = os.getenv("WX_APP_ID", "wxc59eee06736849e8").strip()

UA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".shanm_ua.json")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".shanm_token.json")
DEVICE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".shanm_device.json")

ANDROID_VERSIONS = ["13", "14", "15"]
PHONE_MODELS = ["M2012K11AC", "M2101K9C", "V2183A", "PGT-AN00", "SM-G9860", "M2012K10C"]
BUILD_IDS = ["AQ3A.250226.002", "SP1A.210812.016", "UP1A.231005.007", "TP1A.220624.014"]
CHROME_VERSIONS = ["146.0.7680.178"]
XWEB_VERSIONS = ["1460243"]
MMWEBSDK_VERSIONS = ["20260502"]
MMWEBID_VERSIONS = ["3433"]
MICROMSG_VERSIONS = ["8.0.72.3100(0x28004853)"]


def generate_ua() -> str:
    """生成与抓包中一致格式的安卓微信小程序 WebView UA。"""
    return (
        "Mozilla/5.0 (Linux; Android %s; %s Build/%s; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
        "Chrome/%s Mobile Safari/537.36 "
        "XWEB/%s MMWEBSDK/%s MMWEBID/%s "
        "MicroMessenger/%s WeChat/arm64 Weixin NetType/WIFI "
        "Language/zh_CN ABI/arm64 MiniProgramEnv/android"
        % (
            random.choice(ANDROID_VERSIONS),
            random.choice(PHONE_MODELS),
            random.choice(BUILD_IDS),
            random.choice(CHROME_VERSIONS),
            random.choice(XWEB_VERSIONS),
            random.choice(MMWEBSDK_VERSIONS),
            random.choice(MMWEBID_VERSIONS),
            random.choice(MICROMSG_VERSIONS),
        )
    )


def account_ua(account_key: str) -> str:
    """按账号读取或创建固定 UA，文件损坏时自动重建。"""
    try:
        with open(UA_FILE, "r", encoding="utf-8") as handle:
            values = json.load(handle)
        if isinstance(values, dict) and values.get(account_key):
            return str(values[account_key])
    except (OSError, ValueError, TypeError):
        values = {}

    if not isinstance(values, dict):
        values = {}
    values[account_key] = generate_ua()
    try:
        with open(UA_FILE, "w", encoding="utf-8") as handle:
            json.dump(values, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        print("UA 持久化失败，将继续使用本次生成值: %s" % exc)
    return values[account_key]


def notify(title: str, content: str) -> None:
    """兼容青龙 notify.py；没有通知模块时只输出日志。"""
    try:
        from notify import send  # type: ignore
        send(title, content)
    except Exception as exc:
        print("通知发送失败: %s" % exc)


def split_accounts(value: str) -> List[str]:
    return [item.strip() for item in value.replace("&", "\n").replace("|", "\n").splitlines() if item.strip()]


def parse_wx_accounts(raw: str) -> List[Tuple[str, str]]:
    """解析 WX_ID：支持 wxid#备注，多账号换行/&/| 分隔。"""
    out: List[Tuple[str, str]] = []
    for item in split_accounts(raw):
        if "#" in item:
            wxid, remark = item.split("#", 1)
            out.append((wxid.strip(), remark.strip()))
        else:
            out.append((item.strip(), item.strip()))
    return out


def _load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _save_json(path: str, data: Dict[str, Any]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        print("JSON 持久化失败: %s" % exc)


def load_token(wxid: str) -> str:
    return str(_load_json(TOKEN_FILE).get(wxid) or "")


def save_token(wxid: str, token: str) -> None:
    cache = _load_json(TOKEN_FILE)
    cache[wxid] = token
    _save_json(TOKEN_FILE, cache)


def get_device_id(wxid: str) -> str:
    """按微信账号生成并持久化一个稳定的 device_id（格式对齐抓包）。"""
    cache = _load_json(DEVICE_FILE)
    if wxid in cache:
        return str(cache[wxid])
    device_id = "dev_%d_%s" % (int(time.time() * 1000), uuid.uuid4().hex[:9])
    cache[wxid] = device_id
    _save_json(DEVICE_FILE, cache)
    return device_id


def safe_json(response: requests.Response) -> Dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        raise RuntimeError("HTTP %s，响应不是 JSON: %s" % (response.status_code, response.text[:200]))
    if not isinstance(value, dict):
        raise RuntimeError("接口返回格式异常: %s" % type(value).__name__)
    return value


class ShanmApi:
    def __init__(self, token: str = "", account_key: str = "") -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": account_ua(account_key),
            "Referer": REFERER,
            "Content-Type": "application/json",
            "Charset": "utf-8",
            "Accept": "application/json",
        })
        self.token = token.strip()
        if self.token:
            self.session.headers["X-Token"] = self.token

    def request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        response = self.session.request(
            method, BASE_URL + path, timeout=(10, 20), **kwargs
        )
        if response.status_code in (401, 403):
            raise RuntimeError("鉴权失败，Token 可能已过期或已失效 (HTTP %s)" % response.status_code)
        response.raise_for_status()
        body = safe_json(response)
        if body.get("code") not in (None, 200):
            raise RuntimeError("接口失败: %s" % body.get("msg", body))
        return body

    def login(self, wx_code: str, device_id: str, invite_code: str = "") -> str:
        body = self.request("POST", "/user/login_wx", json={
            "code": wx_code,
            "device_id": device_id,
            "invite_code": invite_code,
            "nickname": "",
            "avatar": "",
        })
        token = str((body.get("data") or {}).get("token") or "")
        if not token:
            raise RuntimeError("登录响应中没有 token")
        self.token = token
        self.session.headers["X-Token"] = token
        return token

    def profile(self) -> Dict[str, Any]:
        return self.request("GET", "/user/profile").get("data") or {}

    def sign_status(self) -> Dict[str, Any]:
        return self.request("GET", "/sign/status").get("data") or {}

    def checkin(self) -> Dict[str, Any]:
        return self.request("POST", "/sign/checkin", json={}).get("data") or {}


def do_login(wxid: str, account_key: str) -> str:
    """通过微信协议(getCode)获取 code 并完成登录，返回 token。"""
    if get_single_code is None:
        raise RuntimeError("未找到 getCode.py，请将其放在同一目录后再运行")
    device_id = get_device_id(wxid)
    invite_code = os.getenv("SHANM_INVITE_CODE", "29EA21E9").strip()
    try:
        code = get_single_code(WX_APP_ID, wxid)
    except Exception as exc:
        raise RuntimeError("通过微信协议获取 code 失败: %s" % exc)
    if not code:
        raise RuntimeError("通过微信协议获取 code 失败（返回为空）")
    api = ShanmApi("", account_key)
    token = api.login(code, device_id, invite_code)
    if not token:
        raise RuntimeError("登录失败，未返回 token")
    return token


def run_account(index: int, wxid: str, remark: str) -> str:
    account_key = "wxid-" + hashlib.sha256(wxid.encode("utf-8")).hexdigest()

    token = load_token(wxid)
    api = ShanmApi(token, account_key)
    if not api.token:
        token = do_login(wxid, account_key)
        save_token(wxid, token)
        api = ShanmApi(token, account_key)

    try:
        profile = api.profile()
    except RuntimeError as exc:
        if "鉴权失败" in str(exc):
            token = do_login(wxid, account_key)
            save_token(wxid, token)
            api = ShanmApi(token, account_key)
            profile = api.profile()
        else:
            raise

    name = str(profile.get("nickname") or remark or "账号%d" % index)
    status = api.sign_status()
    if not status.get("can_checkin"):
        current = status.get("current_session") or "当前时段"
        return "%s：无需签到（%s 已签到或不在签到时段）" % (name, current)

    result = api.checkin()
    session = result.get("session", "未知时段")
    points = result.get("points_earned", "?")
    balance = result.get("points_balance", "?")
    return "%s：签到成功，时段=%s，获得积分=%s，积分余额=%s" % (
        name, session, points, balance
    )


def main() -> None:
    accounts = parse_wx_accounts(os.getenv("WX_ID", ""))
    if not accounts:
        raise RuntimeError("请配置青龙环境变量 WX_ID（微信协议版，格式 wxid#备注，多账号换行/&/| 分隔）")

    results: List[str] = []
    for index, (wxid, remark) in enumerate(accounts, 1):
        try:
            results.append(run_account(index, wxid, remark))
        except Exception as exc:
            results.append("账号%d(%s)：失败，%s" % (index, remark, exc))

    message = "\n".join(results)
    print(message)
    notify("善M签到", message)
    if any("失败" in item for item in results):
        sys.exit(1)


if __name__ == "__main__":
    main()


