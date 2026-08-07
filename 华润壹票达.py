#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
壹票达小程序 - 青龙每日签到
cron: 18 9,17 * * *
# name: 华润壹票达
环境变量（
  WX_ID / ypd_wxid / YPD_WXID
      格式：wxid#备注，多账号换行或 @
      兼容：备注#wxid（备注不以 wxid_ 开头时）
  WECHAT_SERVER   牛子协议服务，默认 http://127.0.0.1:8011
                  （仅手机号加密包使用 /get/all/mobile；YYB 账号由 getCode 自动路由）
  YYB_SERVER      应用宝(YYB) 服务地址（getCode 读取，auto 模式自动路由）

"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import random
import re
import string
import sys
import time
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
import getCode


# =========================
# 可手动修改的固定配置
# =========================
DEFAULT_MERCHANT_ID = "6942616f50ef5900011a1d2e"
DEFAULT_APPID = "wx70c418a86bc52a9f"
DEFAULT_VER = "4.63.0"
DEFAULT_SRC = "weixin_mini"
DEFAULT_TERMINAL_SRC = "WEIXIN_MINI"
DEFAULT_UTC_OFFSET = "480"
DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"
API_HOST = "https://crld.caiyicloud.com"
NOTIFY_TITLE = "壹票达签到"

PATH_UNION_LOGIN = "/cyy_gatewayapi/mcommon/pub/v1/union_login"
PATH_UNION_AUTH = "/cyy_gatewayapi/mcommon/pub/v1/union_login/authorization"
PATH_CHECK_IN = "/cyy_gatewayapi/user/buyer/v1/check_in"
PATH_CHECK_IN_CALENDAR = "/cyy_gatewayapi/user/buyer/v1/check_in_calendar"
PATH_POINT_TASK = "/cyy_gatewayapi/user/buyer/v3/current_user_point_task"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF "
    "WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254151e) XWEB/17127"
)

TZ_CN = timezone(timedelta(hours=8))


@dataclass
class AccountConfig:
    index: int
    name: str
    access_token: str = ""
    angry_dog: str = ""
    cookie: str = ""
    wxid: str = ""
    mode: str = "wxid"  # wxid | token


@dataclass
class AccountSummary:
    index: int
    name: str
    mode: str = "wxid"
    success: bool = False
    sign_status: str = "未执行"
    points_before: Optional[Any] = None
    points_after: Optional[Any] = None
    reward: str = ""
    streak: Optional[Any] = None
    error_message: str = ""
    detail_lines: List[str] = field(default_factory=list)

    def log(self, message: str = "") -> None:
        self.detail_lines.append(message)
        print(message)

    def build_notify_lines(self) -> List[str]:
        mark = "✅" if self.success else "❌"
        lines = [f"{mark}【账号{self.index}】{self.name}"]
        lines.append(f"模式: {self.mode}")
        lines.append(f"状态: {self.sign_status}")
        if self.reward:
            lines.append(f"奖励: {self.reward}")
        if self.streak is not None:
            lines.append(f"连续: {self.streak} 天")
        if self.points_before is not None or self.points_after is not None:
            lines.append(f"积分: {self.points_before} → {self.points_after}")
        if self.error_message:
            lines.append(f"错误: {self.error_message}")
        return lines


def now_text() -> str:
    return datetime.now(TZ_CN).strftime("%Y-%m-%d %H:%M:%S")


def sleep(sec: float) -> None:
    time.sleep(sec)


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def clean_header_value(value: str) -> str:
    if value is None:
        return ""
    return str(value).replace("\\r", "").replace("\\n", "").replace("\r", "").replace("\n", "").strip()


def random_trace_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "mroo" + "".join(random.choice(alphabet) for _ in range(14))


def month_range_ms(now: Optional[datetime] = None) -> Tuple[int, int]:
    """当月起止毫秒时间戳（东八区），对齐 check_in_calendar 的 beginDate/endDate。"""
    now = now or datetime.now(TZ_CN)
    start = datetime(now.year, now.month, 1, tzinfo=TZ_CN)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=TZ_CN)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=TZ_CN)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def find_notify_send() -> Optional[Callable]:
    try:
        from notify import send  # type: ignore

        return send
    except Exception:
        pass

    candidates: List[Path] = []
    ql_dir = env("QL_DIR")
    if ql_dir:
        candidates.append(Path(ql_dir))
    candidates.extend(
        [
            Path("/ql"),
            Path("/ql/data"),
            Path("/ql/scripts"),
            Path("/ql/data/scripts"),
            Path.cwd(),
            Path(__file__).resolve().parent,
        ]
    )
    for directory in candidates:
        notify_path = directory / "notify.py"
        if not notify_path.exists():
            notify_path = directory.parent / "notify.py"
            if not notify_path.exists():
                continue
        try:
            spec = importlib.util.spec_from_file_location("ql_notify_ypd", notify_path)
            if not spec or not spec.loader:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules["ql_notify_ypd"] = module
            spec.loader.exec_module(module)
            sender = getattr(module, "send", None)
            if callable(sender):
                return sender
        except Exception:
            continue
    return None


def push_notify(title: str, content: str) -> None:
    sender = find_notify_send()
    if not sender:
        print("通知: 未找到 notify.py，跳过推送")
        return
    try:
        sender(title, content)
        print("通知: 推送完成")
    except Exception as exc:
        print(f"通知: 推送失败: {exc}")


def split_accounts_raw(raw_value: str) -> List[str]:
    if not raw_value:
        return []
    parts = re.split(r"[\n@]+", raw_value)
    return [p.strip() for p in parts if p.strip() and not p.strip().startswith("#")]


def parse_token_accounts(raw_value: str) -> List[AccountConfig]:
    """
    accessToken
    accessToken#备注
    accessToken#angryDog#备注
    accessToken#angryDog#cookie#备注
    """
    global_angry = clean_header_value(env("YPD_ANGRY_DOG") or env("ypd_angry_dog"))
    global_cookie = clean_header_value(env("YPD_COOKIE") or env("ypd_cookie"))
    accounts: List[AccountConfig] = []
    for idx, item in enumerate(split_accounts_raw(raw_value), 1):
        parts = item.split("#")
        token = clean_header_value(parts[0] if parts else "")
        angry = global_angry
        cookie = global_cookie
        name = f"账号{idx}"
        if len(parts) == 2:
            second = parts[1].strip()
            if len(second) >= 40 or second.startswith("s_"):
                angry = clean_header_value(second) or angry
            else:
                name = second or name
        elif len(parts) == 3:
            angry = clean_header_value(parts[1]) or angry
            name = parts[2].strip() or name
        elif len(parts) >= 4:
            angry = clean_header_value(parts[1]) or angry
            cookie = clean_header_value(parts[2]) or cookie
            name = "#".join(parts[3:]).strip() or name
        if not token:
            print(f"跳过空 token 配置: {item[:40]}")
            continue
        accounts.append(
            AccountConfig(
                index=idx,
                name=name,
                access_token=token,
                angry_dog=angry,
                cookie=cookie,
                mode="token",
            )
        )
    return accounts


def parse_wxid_item(item: str, idx: int) -> Tuple[str, str]:
    """兼容 wxid#备注 与 备注#wxid。"""
    item = item.strip()
    if "#" not in item:
        return item, f"账号{idx}"
    first, second = [x.strip() for x in item.split("#", 1)]
    if second.startswith("wxid_") and not first.startswith("wxid_"):
        return second, first or f"账号{idx}"
    return first, second or f"账号{idx}"


def parse_wxid_accounts(raw_value: str) -> List[AccountConfig]:
    global_angry = clean_header_value(env("YPD_ANGRY_DOG") or env("ypd_angry_dog"))
    global_cookie = clean_header_value(env("YPD_COOKIE") or env("ypd_cookie"))
    accounts: List[AccountConfig] = []
    for idx, item in enumerate(split_accounts_raw(raw_value), 1):
        wxid, remark = parse_wxid_item(item, idx)
        if not wxid:
            continue
        accounts.append(
            AccountConfig(
                index=idx,
                name=remark or f"账号{idx}",
                wxid=wxid,
                angry_dog=global_angry,
                cookie=global_cookie,
                mode="wxid",
            )
        )
    return accounts


def build_code_url(raw_url: str) -> str:
    raw = (raw_url or DEFAULT_WECHAT_SERVER).strip().rstrip("/")
    if not raw:
        return ""
    if raw.endswith("/api/v1/wx/app/get/code") or raw.endswith("/get/code"):
        return raw
    return f"{raw}/api/v1/wx/app/get/code"


def build_mobile_url(code_url: str) -> str:
    if not code_url:
        return ""
    if "/get/code" in code_url:
        return code_url.replace("/get/code", "/get/all/mobile")
    if "/api/" in code_url:
        base = code_url.rsplit("/api/", 1)[0]
        return f"{base.rstrip('/')}/api/v1/wx/app/get/all/mobile"
    return f"{code_url.rstrip('/')}/api/v1/wx/app/get/all/mobile"


def extract_wx_code(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("code", "wx_code", "js_code"):
        val = data.get(key)
        if val:
            return str(val)
    for nest_key in ("Data", "data", "result"):
        nested = data.get(nest_key)
        if isinstance(nested, dict):
            for key in ("code", "wx_code", "js_code"):
                val = nested.get(key)
                if val:
                    return str(val)
        elif isinstance(nested, str) and nested and not nested.startswith("{"):
            return nested
    return ""


def wechat_success(data: Dict[str, Any]) -> bool:
    if data.get("Success") is False or data.get("success") is False:
        return False
    return True


class YiPiaoDaClient:
    def __init__(self, account: AccountConfig):
        self.account = account
        self.merchant_id = clean_header_value(
            env("YPD_MERCHANT_ID") or env("ypd_merchant_id") or DEFAULT_MERCHANT_ID
        )
        self.app_id = clean_header_value(env("YPD_APPID") or env("ypd_appid") or DEFAULT_APPID)
        self.ver = clean_header_value(env("YPD_VER") or env("ypd_ver") or DEFAULT_VER)
        self.src = DEFAULT_SRC
        self.terminal_src = DEFAULT_TERMINAL_SRC
        self.utc_offset = DEFAULT_UTC_OFFSET
        self.access_token = clean_header_value(account.access_token)
        self.angry_dog = clean_header_value(account.angry_dog)
        self.cookie = clean_header_value(account.cookie)
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "User-Agent": UA,
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "xweb_xhr": "1",
                "content-type": "application/json",
                "Referer": f"https://servicewechat.com/{self.app_id}/22/page-frame.html",
                "sec-fetch-site": "cross-site",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
            }
        )
        self.timeout = float(env("YPD_TIMEOUT") or "30")
        self.wechat_code_url = build_code_url(env("WECHAT_SERVER") or DEFAULT_WECHAT_SERVER)
        self.wechat_appid = clean_header_value(
            env("WECHAT_MINI_APPID") or env("wechat_mini_appid") or self.app_id
        )

    def _common_query(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        q: Dict[str, Any] = {
            "currency": "CNY",
            "lang": "zh",
            "terminalSrc": self.terminal_src,
            "utcOffset": self.utc_offset,
            "ver": self.ver,
        }
        if extra:
            q.update(extra)
        return q

    def _auth_headers(self, with_token: bool = True) -> Dict[str, str]:
        headers = {
            "src": self.src,
            "terminal-src": self.terminal_src,
            "merchant-id": self.merchant_id,
            "ver": self.ver,
            "utc-offset": self.utc_offset,
            "front-trace-id": random_trace_id(),
        }
        if with_token and self.access_token:
            headers["access-token"] = self.access_token
        if self.angry_dog:
            headers["angry-dog"] = self.angry_dog
        if self.cookie:
            headers["cookie"] = self.cookie
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        body: Any = None,
        with_token: bool = True,
    ) -> Dict[str, Any]:
        url = API_HOST + path
        if query:
            url = f"{url}?{urlencode(query)}"
        headers = self._auth_headers(with_token=with_token)
        resp = self.session.request(
            method.upper(),
            url,
            headers=headers,
            json=body if body is not None else None,
            timeout=self.timeout,
            proxies={"http": None, "https": None},
        )
        text = resp.text or ""
        try:
            data = resp.json()
        except Exception:
            data = {"_raw": text[:500], "_http_status": resp.status_code}
        if not isinstance(data, dict):
            data = {"_raw": data, "_http_status": resp.status_code}
        data.setdefault("_http_status", resp.status_code)
        return data

    def ok(self, data: Dict[str, Any]) -> bool:
        return int(data.get("statusCode") or 0) == 200 and int(data.get("_http_status") or 0) in (0, 200)

    def comments(self, data: Dict[str, Any]) -> str:
        return str(data.get("comments") or data.get("errorCode") or data.get("_raw") or "")

    # ---------- 微信协议服务 ----------
    def fetch_wx_code(self, summary: AccountSummary) -> str:
        summary.log("获取 code: 通过 getCode 模块获取")
        try:
            code = getCode.get_single_code(self.wechat_appid, self.account.wxid)
            summary.log(f"code 获取成功: {str(code)[:12]}... (len={len(str(code))})")
            return str(code)
        except Exception as exc:
            raise RuntimeError(f"getCode 取 code 失败: {exc}")

    def _phone_proto(self, wxid: str) -> str:
        """与 getCode 一致的协议判定：应用宝 openid / 纯数字 → yyb，其余 → wechat。"""
        raw = str(wxid).split("#")[0].strip()
        if not raw:
            return "wechat"
        if raw.isdigit():
            return "yyb"
        if re.match(r"^o[a-zA-Z0-9_-]{20,}$", raw):
            return "yyb"
        return "wechat"

    def fetch_phone_encrypted(self, summary: AccountSummary) -> Dict[str, Any]:
        """按账号协议自动路由获取手机号授权数据（与登录 code 同协议）：
        - 应用宝(yyb): getCode.get_single_phone_number → {code}（手机号授权 code）
        - 牛子(wechat): 协议服务 get/all/mobile → encryptedData/iv 或 code
        """
        proto = self._phone_proto(self.account.wxid)
        if proto == "yyb":
            summary.log("手机号协议: 应用宝(YYB)，通过 getCode 获取授权 code")
            try:
                code = getCode.get_single_phone_number(self.wechat_appid, self.account.wxid)
            except Exception as exc:
                raise RuntimeError(f"YYB 获取手机号失败: {exc}") from exc
            if not code:
                raise RuntimeError("YYB 获取手机号 code 为空，请确认该 openid 已在应用宝授权")
            summary.log(f"✅ phone code ok (len={len(str(code))})")
            return {"code": str(code)}

        summary.log("手机号协议: 牛子，调用 get/all/mobile")
        """协议服务 get/all/mobile 返回结构（实测）：
        Data.ALLMobile[0] = {mobile, show_mobile, encryptedData, iv, cloud_id, code}
        其中 code 为 64 位 hex，对应业务 authorization.wxParam.authCode。
        另有 Data.Data 字符串可能含 wx_phone，但常缺 code，优先 ALLMobile。
        """
        url = build_mobile_url(self.wechat_code_url)
        if not url:
            raise RuntimeError("无法构造手机号接口 URL，请检查 WECHAT_SERVER")
        payload = {
            "wxid": self.account.wxid,
            "appid": self.wechat_appid,
            "data": json.dumps(
                {"api_name": "webapi_getuserwxphone", "with_credentials": True},
                ensure_ascii=False,
            ),
            "opt": 0,
        }
        summary.log(f"获取手机号加密包: {url}")
        resp = requests.post(
            url,
            json=payload,
            timeout=self.timeout,
            proxies={"http": None, "https": None},
        )
        try:
            result = resp.json()
        except Exception as exc:
            raise RuntimeError(f"手机号接口非 JSON HTTP {resp.status_code}: {resp.text[:200]}") from exc
        if not isinstance(result, dict):
            raise RuntimeError(f"手机号接口响应异常: {result}")
        if not wechat_success(result):
            msg = result.get("Message") or result.get("msg") or result.get("message") or result
            raise RuntimeError(f"获取手机号失败: {msg}")

        data = result.get("Data") if isinstance(result.get("Data"), dict) else result.get("data")
        if not isinstance(data, dict):
            data = {}

        # 1) 优先 ALLMobile / allMobile
        for key in ("ALLMobile", "allMobile", "AllMobile"):
            arr = data.get(key)
            if isinstance(arr, list) and arr:
                item = arr[0]
                if isinstance(item, dict) and (
                    item.get("encryptedData")
                    or item.get("encrypted_data")
                    or item.get("encryptPhoneNumber")
                ):
                    summary.log(
                        f"手机号来源=ALLMobile keys={list(item.keys())} "
                        f"code_len={len(str(item.get('code') or ''))}"
                    )
                    return item

        # 2) Data.Data 字符串 / 嵌套 dict
        raw: Any = data.get("Data", data.get("data"))
        info: Any = {}
        if isinstance(raw, str):
            try:
                info = json.loads(raw) if raw else {}
            except Exception:
                info = {}
        elif isinstance(raw, dict):
            info = raw
        elif isinstance(data, dict):
            info = data

        if isinstance(info, dict):
            phone = info.get("wx_phone") or info.get("wxPhone")
            if isinstance(phone, dict):
                # 若嵌套包没有 code，尝试从 ALLMobile 补
                if not (phone.get("code") or phone.get("authCode")):
                    for key in ("ALLMobile", "allMobile", "AllMobile"):
                        arr = data.get(key)
                        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                            for ck in ("code", "authCode", "cloud_id", "iv", "encryptedData"):
                                if arr[0].get(ck) and not phone.get(ck):
                                    phone[ck] = arr[0].get(ck)
                            break
                summary.log(f"手机号来源=wx_phone keys={list(phone.keys())}")
                return phone
            if info.get("encryptedData") or info.get("encrypted_data") or info.get("encryptPhoneNumber"):
                summary.log(f"手机号来源=nested keys={list(info.keys())}")
                return info

        raise RuntimeError(f"手机号数据包为空: {json.dumps(result, ensure_ascii=False)[:300]}")

    def _apply_login_payload(self, payload: Dict[str, Any], summary: AccountSummary, stage: str) -> bool:
        token = clean_header_value(str(payload.get("accessToken") or ""))
        if token:
            self.access_token = token
            summary.log(f"{stage} 拿到 accessToken (len={len(token)})")
            return True
        return False

    def union_login(self, wx_code: str, summary: AccountSummary) -> Dict[str, Any]:
        volc_web_id = str(random.randint(10**18, 10**19 - 1))
        body = {
            "src": self.src,
            "merchantId": self.merchant_id,
            "ver": self.ver,
            "appId": self.app_id,
            "unionType": "WEIXIN_MINI",
            "wxParam": {"code": wx_code},
            "deviceInfo": {"volcWebId": volc_web_id},
        }
        summary.log("POST union_login ...")
        data = self.request(
            "POST",
            PATH_UNION_LOGIN,
            query=self._common_query(),
            body=body,
            with_token=False,
        )
        if not self.ok(data):
            raise RuntimeError(
                f"union_login 失败: {self.comments(data)} | {json.dumps(data, ensure_ascii=False)[:300]}"
            )
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            payload = {}
        if self._apply_login_payload(payload, summary, "union_login"):
            return payload

        auth_token = str(payload.get("authToken") or "")
        open_id = str(payload.get("openId") or "")
        summary.log(
            f"union_login 未返回 accessToken，尝试手机号 authorization。"
            f" authToken={bool(auth_token)} openId={open_id[:10] + '...' if open_id else ''}"
        )
        if not auth_token or not open_id:
            raise RuntimeError(
                "union_login 未返回 accessToken/authToken/openId，无法继续自动登录。"
                " 可改用 ypd_token 模式。"
            )
        return self.union_authorize(auth_token, open_id, volc_web_id, summary)

    def union_authorize(
        self,
        auth_token: str,
        open_id: str,
        volc_web_id: str,
        summary: AccountSummary,
    ) -> Dict[str, Any]:
        phone = self.fetch_phone_encrypted(summary)
        encrypt_phone = (
            phone.get("encryptedData")
            or phone.get("encrypted_data")
            or phone.get("encryptPhoneNumber")
            or ""
        )
        init_vector = phone.get("iv") or phone.get("initVector") or phone.get("init_vector") or ""
        # ALLMobile[].code 实测 64 位 hex，与抓包 authCode 形态一致
        auth_code = (
            phone.get("authCode")
            or phone.get("auth_code")
            or phone.get("code")
            or phone.get("phone_code")
            or phone.get("cloud_id")
            or ""
        )
        if auth_code and len(str(auth_code)) not in (32, 64) and encrypt_phone:
            # 非预期长度时仍提交原值，同时记录
            summary.log(f"authCode 长度异常 len={len(str(auth_code))}")
        if not auth_code and encrypt_phone:
            summary.log("无 authCode/code 字段，sha256(encryptedData) 兜底")
            auth_code = hashlib.sha256(str(encrypt_phone).encode("utf-8")).hexdigest()
        if not encrypt_phone and not init_vector:
            # 应用宝(YYB) 仅返回手机号授权 code，无加密包，走 code 授权路径
            if auth_code:
                summary.log("无加密包(encryptedData/iv)，使用手机号授权 code 完成 authorization")
                encrypt_phone = ""
                init_vector = ""
            else:
                raise RuntimeError(
                    "手机号 encryptedData/iv 与 authCode 均为空，无法 authorization。"
                    " 请确认协议服务支持 get/all/mobile，或改用 ypd_token。"
                )
        mobile_hint = str(phone.get("show_mobile") or phone.get("mobile") or "")
        summary.log(f"手机号包 ok mobile={mobile_hint or 'N/A'} enc_len={len(str(encrypt_phone))}")

        body = {
            "src": self.src,
            "merchantId": self.merchant_id,
            "ver": self.ver,
            "appId": self.app_id,
            "unionType": "WEIXIN_MINI",
            "authToken": auth_token,
            "openId": open_id,
            "wxParam": {
                "openId": open_id,
                "encryptPhoneNumber": encrypt_phone,
                "initVector": init_vector,
                "authCode": str(auth_code),
            },
            "invitePageId": "",
            "deviceInfo": {"volcWebId": volc_web_id},
        }
        summary.log("POST union_login/authorization ...")
        data = self.request(
            "POST",
            PATH_UNION_AUTH,
            query=self._common_query(),
            body=body,
            with_token=False,
        )
        if not self.ok(data):
            raise RuntimeError(
                f"authorization 失败: {self.comments(data)} | {json.dumps(data, ensure_ascii=False)[:300]}"
            )
        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            payload = {}
        if not self._apply_login_payload(payload, summary, "authorization"):
            raise RuntimeError(
                "authorization 未返回 accessToken。"
                f" keys={list(payload.keys())} | {json.dumps(payload, ensure_ascii=False)[:200]}"
            )
        return payload

    def login_by_wxid(self, summary: AccountSummary) -> None:
        if not self.account.wxid:
            raise RuntimeError("缺少 wxid")
        if not self.wechat_code_url:
            raise RuntimeError("缺少 WECHAT_SERVER")
        summary.log(f"wxid 登录: {self.account.wxid}")
        summary.log(f"WECHAT_SERVER => {self.wechat_code_url}")
        summary.log(f"appId => {self.wechat_appid}")
        code = self.fetch_wx_code(summary)
        self.union_login(code, summary)
        if not self.access_token:
            raise RuntimeError("wxid 登录后仍无 access-token")

    # ---------- 签到 ----------
    def get_calendar(self) -> Dict[str, Any]:
        begin_ms, end_ms = month_range_ms()
        query = self._common_query(
            {
                "src": self.src,
                "merchantId": self.merchant_id,
                "appId": self.app_id,
                "pageSource": "TASK_CENTER",
                "beginDate": str(begin_ms),
                "endDate": str(end_ms),
            }
        )
        return self.request("GET", PATH_CHECK_IN_CALENDAR, query=query, with_token=True)

    def do_check_in(self) -> Dict[str, Any]:
        body = {
            "src": self.src,
            "merchantId": self.merchant_id,
            "ver": self.ver,
            "appId": self.app_id,
        }
        query = self._common_query()
        return self.request("POST", PATH_CHECK_IN, query=query, body=body, with_token=True)

    def run(self) -> AccountSummary:
        summary = AccountSummary(
            index=self.account.index,
            name=self.account.name,
            mode=self.account.mode,
        )
        summary.log(f"\n====== 【账号{self.account.index}】{self.account.name} ({self.account.mode}) ======")
        try:
            if self.account.mode == "wxid":
                self.login_by_wxid(summary)
            if not self.access_token:
                raise RuntimeError("缺少 access-token，请配置 ypd_wxid(+WECHAT_SERVER) 或 ypd_token")

            summary.log("查询签到日历 ...")
            cal = self.get_calendar()
            if not self.ok(cal):
                raise RuntimeError(
                    f"查询日历失败: {self.comments(cal)} | {json.dumps(cal, ensure_ascii=False)[:300]}"
                )
            cal_data = cal.get("data") or {}
            today_checked = bool(cal_data.get("todayCheckedIn"))
            summary.points_before = cal_data.get("points")
            summary.streak = cal_data.get("streakCheckInDays")
            summary.log(
                f"日历: todayCheckedIn={today_checked} points={summary.points_before} "
                f"streak={summary.streak}"
            )

            if today_checked:
                summary.success = True
                summary.sign_status = "今日已签到"
                summary.points_after = summary.points_before
                summary.log("今日已签到，跳过 POST check_in")
            else:
                summary.log("执行签到 POST check_in ...")
                sign = self.do_check_in()
                if not self.ok(sign):
                    raise RuntimeError(
                        f"签到失败: {self.comments(sign)} | {json.dumps(sign, ensure_ascii=False)[:300]}"
                    )
                sign_data = sign.get("data") or {}
                rewards = sign_data.get("rewardAggPackage") or sign_data.get("rewardPackage") or []
                reward_text = []
                for r in rewards:
                    if isinstance(r, dict):
                        reward_text.append(f"{r.get('rewardType', '?')}={r.get('reward', '?')}")
                    else:
                        reward_text.append(str(r))
                summary.reward = ", ".join(reward_text) if reward_text else "成功"
                summary.streak = sign_data.get("streakCheckInDays", summary.streak)
                summary.sign_status = "签到成功"
                summary.success = True
                summary.log(f"签到成功 reward={summary.reward} streak={summary.streak}")
                sleep(0.5)
                cal2 = self.get_calendar()
                if self.ok(cal2):
                    d2 = cal2.get("data") or {}
                    summary.points_after = d2.get("points", summary.points_before)
                    summary.streak = d2.get("streakCheckInDays", summary.streak)
                    if d2.get("todayCheckedIn"):
                        summary.log(f"回读确认已签到 points={summary.points_after}")
                    else:
                        summary.log("回读日历 todayCheckedIn 仍为 false（可能延迟）")
                else:
                    summary.points_after = summary.points_before
                    summary.log(f"回读日历失败: {self.comments(cal2)}")

        except Exception as exc:
            summary.success = False
            summary.sign_status = "失败"
            summary.error_message = str(exc)
            summary.log(f"失败: {exc}")
        return summary


def load_accounts() -> List[AccountConfig]:
    """优先 ypd_wxid；无 wxid 时回退 ypd_token。"""
    wxid_raw = env("WX_ID") or env("ypd_wxid") or env("YPD_WXID") or env("ypdwxid")
    token_raw = env("ypd_token") or env("YPD_TOKEN") or env("YPDTOKEN")
    accounts: List[AccountConfig] = []
    if wxid_raw:
        accounts.extend(parse_wxid_accounts(wxid_raw))
    if token_raw:
        token_accounts = parse_token_accounts(token_raw)
        base = len(accounts)
        for i, acc in enumerate(token_accounts, 1):
            acc.index = base + i
            accounts.append(acc)
    return accounts


def main() -> None:
    print(f"壹票达签到开始 {now_text()}")
    print(f"API_HOST => {API_HOST}")
    print(f"WECHAT_SERVER => {build_code_url(env('WECHAT_SERVER') or DEFAULT_WECHAT_SERVER)}")
    accounts = load_accounts()
    if not accounts:
        msg = (
            "未配置账号。请设置环境变量 ypd_wxid + WECHAT_SERVER（推荐）。\n"
            "示例:\n"
            "  export ypd_wxid='wxid_xxx#备注'\n"
            "  export WECHAT_SERVER='http://127.0.0.1:8011'\n"
            "可选回退: ypd_token / YPD_ANGRY_DOG / YPD_COOKIE"
        )
        print(msg)
        push_notify(NOTIFY_TITLE, msg)
        return

    modes = ", ".join(sorted({a.mode for a in accounts}))
    print(f"账号数: {len(accounts)} 模式: {modes}")
    results: List[AccountSummary] = []
    for acc in accounts:
        client = YiPiaoDaClient(acc)
        results.append(client.run())
        sleep(random.uniform(0.8, 1.6))

    ok_n = sum(1 for r in results if r.success)
    fail_n = len(results) - ok_n
    print(f"\n====== 汇总 成功 {ok_n}/{len(results)} 失败 {fail_n} ======")
    notify_lines: List[str] = [
        f"壹票达签到 {now_text()}",
        f"成功 {ok_n}/{len(results)}  失败 {fail_n}",
        "",
    ]
    for r in results:
        notify_lines.extend(r.build_notify_lines())
        notify_lines.append("")
    content = "\n".join(notify_lines).strip()
    print(content)
    push_notify(NOTIFY_TITLE, content)


if __name__ == "__main__":
    main()
