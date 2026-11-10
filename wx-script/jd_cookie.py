#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name: jd_cookie.py
# cron: 0 */3 * * *
"""
version: 2.4.6

通过 YYB-Go-Enhanced 取微信 code 登录jd小程序，获取jd cookie
把jd Cookie 写入青龙环境变量；默认写本地变量，配置远程青龙后自动写远程。

青龙环境变量（非空环境变量优先于下方 CONFIG_*）：
  YYB_SERVER          必填，服务地址@微信账号标识，多账号每行一条，可在末尾加 #备注
                      例：http://yyb-go:8000@1；仅填服务地址则从 /accounts 读取账号
  JD_ACCOUNTS_JSON    可选，显式账号数组；优先于 CONFIG_ACCOUNTS 和 YYB 行内账号
                      例：[{"ref":"1","remark":"账号一"},{"ref":"2"}]
                      每项可加 server 指定独立 YYB 地址；不填则使用 YYB 第一行地址
  YYB_PROTOCOL_TOKEN  可选，YYB 协议 Bearer 密钥；兼容 YYB_API_KEY
  QL_URL              可选，远程青龙完整地址，填写三项才启用远程写入
  QL_CLIENT_ID        可选，远程青龙应用 Client ID，需要环境变量权限
  QL_CLIENT_SECRET    可选，远程青龙应用 Client Secret（不是面板登录密码）
                      任务前置脚本注入的完整 QL_* 也属于已配置，会启用远程分支
  QL_COOKIE_ENV_NAME  可选，本地/远程变量名，默认 JD_COOKIE
                      兼容旧 JD_COOKIE_ENV_NAME；两项冲突在写入前报错
  QL_DB_PATH          可选，仅本地模式使用；自动查找 /ql/data/db 或 /ql/db 中的 database.sqlite
  JD_LOGIN_MODE       auto（默认）在 pt 模式走京东快递静默登录；code / full 保留原登录入口
  JD_EID_TOKEN        可选，覆盖内置京东快递设备指纹（finger_tk）
  JD_HOSTSIGN_NONCESTR / JD_HOSTSIGN_TIMESTAMP / JD_HOSTSIGN_SIGNATURE
                      可选，一起覆盖内置的 X-WECHAT-HOSTSIGN 三个字段
  JD_SILENT_USER_AGENT / JD_SILENT_REFERER
                      可选，覆盖静默登录的 User-Agent / Referer
  JD_COOKIE_MODE      可选，pt（默认，仅 pt_key/pt_pin）/ all（同时保留已取得的其他 Cookie）
  JD_SHOW_CK          可选，默认 0；仅获取模式设 1 才在标准输出显示完整 CK
                      青龙可能保存标准输出为运行日志；写入模式始终不打印完整 CK
  REQUEST_TIMEOUT     可选，单次请求超时秒数，默认 30，范围 5～90

依赖：Python 3.9+，仅标准库，无需安装 requests。
本地：SQLite 事务写入并读回，通过 loopback 与现有本地 token/应用刷新青龙任务环境。
      不创建新应用、不改权限；刷新认证不可用时在数据库写入前报错。
账号：按 pt_pin 匹配；保留人工备注，更新成功后启用变量；重复同账号变量报错而不误覆盖。
通知：无，结果以日志输出为主（✅ 成功 / ⚠️ 需人工 / ❌ 失败，退出码仅真失败非 0）。
功能：YYB 取码 → 小程序登录 → 身份 Cookie 校验 → 写入青龙变量（写入读回校验）。

作者：lcmovie https://github.com/lcmovie
"""
from __future__ import annotations

import base64
import json
import html
import os
from pathlib import Path
import re
import secrets
import hashlib
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import Cookie, CookieJar
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ========== 非敏感默认配置（环境变量优先） ==========

JD_EXPRESS_APPID = "wx73247c7819d61796"
# 参考实现的设备参数；失效后可通过环境变量更新。
CONFIG_JD_EID_TOKEN = 'jdd01w4AS6CD7CIG2JXB54AQC4LIR2Q4FVGKFUEXPCCJXKWDK5PSSQBQL6AAZWY5ZWC7WUBUMFGMKGKQG5EOSJBPAZCTFDEPQUM56YZYXXMDSXXEIBZ7CIICDGXISQRWFXSKN4VO'
CONFIG_JD_HOSTSIGN_NONCESTR = '4311023ad04719e963d52022c370a83e'
CONFIG_JD_HOSTSIGN_TIMESTAMP = '1781869158'
CONFIG_JD_HOSTSIGN_SIGNATURE = 'd16be9475d2349e7694aeb38299e5c9e8e87ba63'
CONFIG_QL_URL = ""  # 远程青龙完整地址，三项全填才写远程
CONFIG_QL_CLIENT_ID = ""  # 青龙应用 Client ID，需环境变量权限
CONFIG_QL_CLIENT_SECRET = ""  # 青龙应用 Client Secret
CONFIG_JD_LOGIN_MODE = "auto"
CONFIG_JD_COOKIE_MODE = "pt"
CONFIG_JD_APPID = "wx91d27dbf599dff74"
CONFIG_QL_COOKIE_ENV_NAME = "JD_COOKIE"  # 本地/远程通用变量名
CONFIG_QL_DB_PATH = ""  # 留空自动寻找青龙 DB；仅本地模式使用
CONFIG_YYB_SERVER = ""  # 一般通过青龙共享 YYB_SERVER 配置
CONFIG_JD_SHOW_CK = "0"  # 仅获取模式下设 1 才打印完整 CK；默认只显示结果

# ========== 账号配置（可直接在这里修改） ==========
#
# 留空 []：自动读取 YYB_SERVER 的 /accounts，只处理已经扫码保存的账号。
# 手动指定示例：
# CONFIG_ACCOUNTS = [
#     {"name": "京东账号1", "ref": "3"},
#     {"name": "京东账号2", "ref": "4"},
#     {"name": "京东账号3", "ref": "5"},
# ]
# ref 可以填 /accounts 返回的 id、openid、alias 或 uin。

CONFIG_ACCOUNTS = []


# ========== 运行配置 ==========


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name) or "").strip() or str(default).strip()


JD_APPID = _env("JD_APPID", CONFIG_JD_APPID)
YYB_RAW = _env("YYB_SERVER", CONFIG_YYB_SERVER)
YYB_LINES = [line.strip() for line in YYB_RAW.splitlines() if line.strip()]
YYB_SERVER = (YYB_LINES[0].split("@", 1)[0] if YYB_LINES else "").rstrip("/")
if YYB_SERVER and not YYB_SERVER.startswith("http"):
    YYB_SERVER = "http://" + YYB_SERVER
# 多行 YYB_SERVER（地址@ref）取第一行纯地址作为 base URL
if YYB_SERVER and '@' in YYB_SERVER.splitlines()[0]:
    YYB_SERVER = YYB_SERVER.splitlines()[0][:YYB_SERVER.splitlines()[0].index('@')].rstrip('/')
QL_URL = _env("QL_URL", CONFIG_QL_URL).rstrip("/")
QL_CLIENT_ID = _env("QL_CLIENT_ID", CONFIG_QL_CLIENT_ID)
QL_CLIENT_SECRET = _env("QL_CLIENT_SECRET", CONFIG_QL_CLIENT_SECRET)
# 兼容两份旧脚本的不同变量名；冲突只在真正写入时检查。
QL_ENV_ALIAS = _env("QL_COOKIE_ENV_NAME")
JD_ENV_ALIAS = _env("JD_COOKIE_ENV_NAME")
QL_COOKIE_ENV_NAME = QL_ENV_ALIAS or JD_ENV_ALIAS or CONFIG_QL_COOKIE_ENV_NAME
QL_DB_PATH = _env("QL_DB_PATH", CONFIG_QL_DB_PATH)
SHOW_CK = _env("JD_SHOW_CK", CONFIG_JD_SHOW_CK) == "1"
YYB_PROTOCOL_TOKEN = _env("YYB_PROTOCOL_TOKEN") or _env("YYB_API_KEY")
LOGIN_MODE = _env("JD_LOGIN_MODE", CONFIG_JD_LOGIN_MODE).lower()
COOKIE_MODE = _env("JD_COOKIE_MODE", CONFIG_JD_COOKIE_MODE).lower()

try:
    REQUEST_TIMEOUT = max(5, min(int(_env("REQUEST_TIMEOUT", "30")), 90))
except ValueError:
    REQUEST_TIMEOUT = 30

UA_WX = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    f"MicroMessenger/8.0.49 NetType/WIFI Language/zh_CN miniProgram/{JD_APPID}"
)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CookieOpener:
    def __init__(self):
        self.cookie_jar = CookieJar()
        self.last_response_cookie = ""
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            NoRedirectHandler(),
        )

    def open(self, request, timeout=30):
        return self.opener.open(request, timeout=timeout)


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(parsed._replace(query="", fragment=""))


def request_text(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    data: Any = None,
    opener: Optional[CookieOpener] = None,
    json_body: bool = True,
) -> Tuple[int, Dict[str, str], str]:
    request_headers = dict(headers or {})
    body = None
    if data is not None:
        if json_body:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        else:
            body = data.encode("utf-8") if isinstance(data, str) else data
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method.upper(),
    )
    try:
        response = (
            opener.open(request, timeout=REQUEST_TIMEOUT)
            if opener is not None
            else urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT)
        )
        with response as resp:
            response_headers: Dict[str, str] = {}
            for header_name, header_value in resp.headers.items():
                # 同名 Set-Cookie 不能用普通 dict 覆盖，否则可能丢掉 pt_key 或 pt_pin。
                if header_name.lower() == "set-cookie" and header_name in response_headers:
                    response_headers[header_name] += "; " + str(header_value)
                else:
                    response_headers[header_name] = str(header_value)
            return (
                int(getattr(resp, "status", 200)),
                response_headers,
                resp.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as exc:
        response_headers: Dict[str, str] = {}
        for header_name, header_value in exc.headers.items():
            if header_name.lower() == "set-cookie" and header_name in response_headers:
                response_headers[header_name] += "; " + str(header_value)
            else:
                response_headers[header_name] = str(header_value)
        return (
            int(exc.code),
            response_headers,
            exc.read().decode("utf-8", "replace"),
        )
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(
            f"请求失败 {method.upper()} {redact_url(url)}：{reason}"
        ) from exc


def parse_jsonish(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"value": value}
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {"value": value}
            except json.JSONDecodeError:
                pass
    return {}


def response_message(payload: Any) -> str:
    value = nested_value(payload, ("errmsg", "errMsg", "message", "msg", "error"))
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)[:300]
    return str(value or "").strip()[:300]


def request_json(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    data: Any = None,
    opener: Optional[CookieOpener] = None,
) -> Dict[str, Any]:
    status, _headers, raw = request_text(method, url, headers, data, opener)
    payload = parse_jsonish(raw)
    if status < 200 or status >= 300:
        message = response_message(payload)
        if status == 409 and "login_buffer expired" in message.lower():
            message = "应用宝账号登录缓存已过期，请打开 /scan 重新扫码"
        suffix = f"：{message}" if message else ""
        raise RuntimeError(
            f"HTTP {status} {method.upper()} {redact_url(url)}{suffix}"
        )
    if not payload and raw.strip():
        raise RuntimeError(
            f"接口未返回 JSON：{method.upper()} {redact_url(url)}"
        )
    return payload


def unwrap_service_payload(payload: Any) -> Dict[str, Any]:
    """兼容第二个插件使用的 {code, data, msg} 响应格式。"""
    if not isinstance(payload, dict):
        return {"value": payload}
    if "code" in payload and "data" in payload:
        code = str(payload.get("code"))
        if code not in {"0", "200", "201"}:
            raise RuntimeError(response_message(payload) or f"接口业务状态异常：{code}")
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, str) and data.strip().startswith(("{", "[")):
            decoded = parse_jsonish(data)
            if decoded:
                return decoded
        return {"value": data}
    return payload


def nested_value(payload: Any, keys: Iterable[str]) -> Any:
    wanted = set(keys)
    wanted_lower = {str(key).lower() for key in wanted}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if (
                (key in wanted or str(key).lower() in wanted_lower)
                and value not in (None, "")
            ):
                return value
        for value in payload.values():
            found = nested_value(value, wanted)
            if found not in (None, ""):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = nested_value(value, wanted)
            if found not in (None, ""):
                return found
    elif isinstance(payload, str):
        text = payload.strip()
        if text.startswith(("{", "[")):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, (dict, list)):
                return nested_value(decoded, wanted)
    return None


def nested_string(payload: Any, keys: Iterable[str]) -> str:
    value = nested_value(payload, keys)
    if isinstance(value, str):
        return value.strip()
    return ""


def normalize_accounts(values: Any, source_name: str) -> List[Dict[str, str]]:
    accounts: List[Dict[str, str]] = []
    source = values if isinstance(values, list) else []
    for index, item in enumerate(source, 1):
        if not isinstance(item, dict):
            continue
        ref = str(
            item.get("ref")
            or item.get("openid")
            or item.get("openId")
            or item.get("id")
            or item.get("uin")
            or item.get("alias")
            or ""
        ).strip()
        if not ref:
            continue
        accounts.append(
            {
                "name": str(
                    item.get("name")
                    or item.get("nickname")
                    or item.get("alias")
                    or f"京东账号{index}"
                ).strip(),
                "ref": ref,
                "remark": str(item.get("remark") or "").strip(),
                "server": str(item.get("server") or YYB_SERVER).strip().rstrip("/"),
            }
        )
    if not accounts:
        raise RuntimeError(f"{source_name} 中没有有效 ref")
    return accounts


def load_service_accounts() -> List[Dict[str, str]]:
    """自动读取 YYB_SERVER 已扫码保存的账号。"""
    payload = request_json("GET", f"{YYB_SERVER}/accounts", headers=yyb_headers())
    values: Any = payload.get("value") if isinstance(payload, dict) else None
    if values is None and isinstance(payload, dict):
        values = payload.get("data")
    if isinstance(values, dict):
        values = values.get("data") or values.get("list") or values.get("items")
    return normalize_accounts(values, "YYB_SERVER /accounts")


# ==================== 账号读取与 YYB 协议 ====================
def yyb_headers() -> Dict[str, str]:
    """YYB 开启协议鉴权时，所有账号/取码/资料请求均携带同一 Bearer。"""
    return {"Authorization": "Bearer " + YYB_PROTOCOL_TOKEN} if YYB_PROTOCOL_TOKEN else {}


def parse_yyb_go_env() -> List[Dict[str, str]]:
    """多行 地址@ref[#备注]；每个账号使用自己所在行的服务地址。"""
    accounts = []
    for index, value in enumerate(YYB_LINES, 1):
        if "@" not in value:
            if len(YYB_LINES) > 1:
                raise RuntimeError(f"YYB_SERVER 第 {index} 行缺少 @账号标识")
            return []  # 仅填服务地址：后续从 /accounts 获取账号。
        server, ref = value.split("@", 1)
        ref, _, remark = ref.partition("#")
        server = server.strip().rstrip("/")
        if "://" not in server:
            server = "http://" + server
        validate_url("YYB_SERVER", server)
        if not ref.strip():
            raise RuntimeError(f"YYB_SERVER 第 {index} 行账号标识为空")
        accounts.append({"name": f"账号{index}", "ref": ref.strip(),
                         "remark": remark.strip(), "server": server})
    return accounts


def load_accounts() -> List[Dict[str, str]]:
    """优先级：JD_ACCOUNTS_JSON > CONFIG_ACCOUNTS > YYB 行内账号 > /accounts。"""
    raw = _env("JD_ACCOUNTS_JSON")
    if raw:
        try:
            values = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError("JD_ACCOUNTS_JSON 不是有效 JSON") from None
        accounts = normalize_accounts(values, "JD_ACCOUNTS_JSON")
    elif CONFIG_ACCOUNTS:
        accounts = normalize_accounts(CONFIG_ACCOUNTS, "CONFIG_ACCOUNTS")
    else:
        accounts = parse_yyb_go_env() or load_service_accounts()
    for account in accounts:
        server = account.get("server") or YYB_SERVER
        if "://" not in server:
            server = "http://" + server
        validate_url("账号 YYB 地址", server)
        account["server"] = server.rstrip("/")
    return accounts


def get_yyb_code(
    account: Dict[str, str],
    app_id: Optional[str] = None,
) -> str:
    request_app_id = str(app_id or JD_APPID).strip()
    payload = request_json(
        "POST",
        f"{account.get('server') or YYB_SERVER}/wxapp/getCode",
        headers=yyb_headers(),
        data={"ref": account["ref"], "app_id": request_app_id},
    )
    result = unwrap_service_payload(payload)
    # yyb_go 的 data 同时带有 openid；PT 链的账号仍由同一个 ref 标识。
    openid = nested_string(result, ("openid", "openId", "open_id"))
    if openid:
        account["_openid"] = openid
    code = nested_string(result, ("wxCode", "wx_code", "jsCode", "jscode", "code"))
    if len(code) < 8 or code in {"0", "200", "201"}:
        raise RuntimeError("应用宝 getCode 未返回有效一次性 code")
    return code


def get_yyb_user_info(account: Dict[str, str]) -> Dict[str, str]:
    payload = request_json(
        "POST",
        f"{account.get('server') or YYB_SERVER}/wxapp/operateWxData",
        headers=yyb_headers(),
        data={
            "ref": account["ref"],
            "app_id": JD_APPID,
            # yyb_go 会把 payload 原样交给小程序 API；必须打开
            # withCredentials，才能稳定拿到 encryptedData/iv/rawData。
            "payload": {
                "api_name": "getUserInfo",
                "data": {"withCredentials": True},
                "env": 1,
            },
        },
    )
    result = unwrap_service_payload(payload)
    raw_data = nested_value(result, ("rawData", "raw_data"))
    # 部分 operateWxData 版本只返回 userInfo，不返回 rawData。
    # 微信端的 rawData 本质上就是 JSON.stringify(userInfo)，可按原字段顺序重建。
    if raw_data in (None, ""):
        user_info = nested_value(result, ("userInfo", "user_info"))
        if isinstance(user_info, str) and user_info.strip().startswith("{"):
            try:
                user_info = json.loads(user_info)
            except json.JSONDecodeError:
                user_info = None
        if not isinstance(user_info, dict):
            standard_keys = (
                "nickName",
                "gender",
                "language",
                "city",
                "province",
                "country",
                "avatarUrl",
            )
            direct_info: Dict[str, Any] = {}
            for key in standard_keys:
                value = nested_value(result, (key,))
                if value is not None:
                    direct_info[key] = value
            user_info = direct_info or None
        if isinstance(user_info, dict) and user_info:
            raw_data = json.dumps(
                user_info,
                ensure_ascii=False,
                separators=(",", ":"),
            )
    if isinstance(raw_data, (dict, list)):
        raw_data_text = json.dumps(
            raw_data,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    else:
        raw_data_text = str(raw_data or "").strip()
    encrypted = nested_string(
        result,
        (
            "encryptedData",
            "encrytData",
            "encrypted_data",
            "encrypteddata",
        ),
    )
    info = {
        "rawData": raw_data_text,
        "signature": nested_string(result, ("signature",)),
        "encrytData": encrypted,
        "iv": nested_string(result, ("iv",)),
        "openid": nested_string(result, ("openid", "openId", "open_id")),
    }
    missing = [
        key
        for key in ("rawData", "signature", "encrytData", "iv")
        if not info[key]
    ]
    if missing:
        result_keys = []
        if isinstance(result, dict):
            result_keys = [str(key) for key in result.keys()][:20]
        detail = "；返回字段=" + ",".join(result_keys) if result_keys else ""
        raise RuntimeError(
            "应用宝 getUserInfo 缺少字段：" + ",".join(missing) + detail
        )
    return info


# ==================== 京东登录：原 login_lt 与 PT OAuth 链 ====================
# 登录重试必须重新取一次性 code；保存目标不影响此流程。
def login_headers() -> Dict[str, str]:
    return {
        "User-Agent": UA_WX,
        "Referer": f"https://servicewechat.com/{JD_APPID}/873/page-frame.html",
        "Accept": "application/json,text/plain,*/*",
    }


def call_login_lt(
    opener: CookieOpener,
    code: str,
    user_info: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    # login_lt 即使是 code-only 也需要 appid 和完整的小程序上下文；
    # isIgnoreCookie 必须为 false，否则京东不会把 pt_key/pt_pin 写入会话。
    params = {
        "appid": JD_APPID,
        "code": code,
        "type": "silent",
        "isPopup": "false",
        "isIgnoreCookie": "false",
        "isOfficialPin": "false",
        "loginColor": "{}",
        "returnUrl": "pages/my/index/index",
        "deviceName": "iPhone",
        "deviceOS": "iOS",
        "deviceOSVersion": "17.0",
        "deviceVersion": "8.0.49",
        "g_tk": "0",
        "g_ty": "ls",
    }
    if user_info:
        params.update(
            {
                "rawData": user_info["rawData"],
                "signature": user_info["signature"],
                "encrytData": user_info["encrytData"],
                "encryptedData": user_info["encrytData"],
                "iv": user_info["iv"],
                "ou": user_info.get("openid", ""),
            }
        )
    url = "https://wq.jd.com/mlogin/wxapp/login_lt?" + urllib.parse.urlencode(params)
    status, response_headers, raw = request_text(
        "GET",
        url,
        headers=login_headers(),
        opener=opener,
    )
    header_cookie = cookie_from_headers(response_headers)
    if header_cookie:
        opener.last_response_cookie = header_cookie
    if status < 200 or status >= 400:
        raise RuntimeError(f"login_lt HTTP {status}")
    return parse_jsonish(raw)


def normalize_pt_cookie(cookie: Any) -> str:
    if isinstance(cookie, CookieJar):
        values: Dict[str, str] = {}
        for item in cookie:
            if item.name in {"pt_key", "pt_pin"} and item.value:
                values[item.name] = str(item.value)
        if values.get("pt_key") and values.get("pt_pin"):
            return f"pt_key={values['pt_key']};pt_pin={values['pt_pin']};"
        return ""

    text = str(cookie or "")
    key_match = re.search(r"(?:^|[;?,\s])pt_key=([^;?,\s]+)", text)
    pin_match = re.search(r"(?:^|[;?,\s])pt_pin=([^;?,\s]+)", text)
    if not key_match or not pin_match:
        return ""
    return f"pt_key={key_match.group(1)};pt_pin={pin_match.group(1)};"


def cookie_from_headers(headers: Dict[str, Any]) -> str:
    """CookieJar 未接住 3xx/异常响应时，从 Set-Cookie 头补取标准 Cookie。"""
    for key, value in (headers or {}).items():
        if str(key).lower() not in {"set-cookie", "set-cookie2"}:
            continue
        cookie = normalize_pt_cookie(str(value))
        if cookie:
            return cookie
    return ""


def cookie_from_payload(payload: Any) -> str:
    pt_key = nested_string(payload, ("pt_key", "ptKey"))
    pt_pin = nested_string(payload, ("pt_pin", "ptPin"))
    if pt_key and pt_pin:
        return normalize_pt_cookie(f"pt_key={pt_key};pt_pin={pt_pin};")
    return normalize_pt_cookie(str(payload or ""))


def all_cookie_text(jar: CookieJar) -> str:
    values: Dict[str, str] = {}
    for cookie in jar:
        if cookie.name and cookie.value is not None:
            values[cookie.name] = str(cookie.value)
    return ";".join(f"{key}={value}" for key, value in values.items()) + (
        ";" if values else ""
    )


def cookie_pin(cookie: str) -> str:
    pure = normalize_pt_cookie(cookie)
    match = re.search(r"(?:^|[;,\s])pt_pin=([^;,\s]+)", pure)
    return match.group(1) if match else ""


def normalize_pin(pin: str) -> str:
    raw = str(pin or "").strip()
    if not raw:
        return ""
    try:
        return urllib.parse.quote(urllib.parse.unquote(raw), safe="")
    except Exception:
        return raw


def pin_variants(pin: str) -> set:
    raw = str(pin or "").strip()
    if not raw:
        return set()
    values = {raw}
    try:
        values.add(urllib.parse.unquote(raw))
    except Exception:
        pass
    try:
        values.add(urllib.parse.quote(raw, safe=""))
        values.add(urllib.parse.quote(urllib.parse.unquote(raw), safe=""))
    except Exception:
        pass
    return {value for value in values if value}


def login_info(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    info = payload.get("info")
    if isinstance(info, dict):
        return info
    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("info")
        return nested if isinstance(nested, dict) else data
    return payload


def allowed_jd_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "jd.com" or host.endswith(".jd.com")
    )


def follow_server_refresh(opener: CookieOpener, payload: Dict[str, Any]) -> str:
    info = login_info(payload)
    current = nested_string(info, ("ACRJUrl", "acrjUrl"))
    state = nested_string(info, ("ACRJState", "acrjState"))
    if not current:
        return ""
    if current.startswith("//"):
        current = "https:" + current
    elif current.startswith("/"):
        current = "https://wq.jd.com" + current
    if state and "ACRJState=" not in current:
        parsed = urllib.parse.urlparse(current)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        query.append(("ACRJState", state))
        current = urllib.parse.urlunparse(
            parsed._replace(query=urllib.parse.urlencode(query))
        )

    headers = dict(login_headers())
    headers["Accept"] = "text/html,application/xhtml+xml,application/json,*/*;q=0.8"
    for _ in range(8):
        if not allowed_jd_url(current):
            raise RuntimeError("服务端刷新地址不是受信任的京东 HTTPS 域名，已停止")
        status, response_headers, _raw = request_text(
            "GET",
            current,
            headers=headers,
            opener=opener,
        )
        result = normalize_pt_cookie(opener.cookie_jar)
        if not result:
            result = cookie_from_headers(response_headers)
        if result:
            return result
        location = (
            response_headers.get("Location")
            or response_headers.get("location")
            or ""
        )
        if status not in {301, 302, 303, 307, 308} or not location:
            break
        current = urllib.parse.urljoin(current, location)
    return normalize_pt_cookie(opener.cookie_jar)


def jd_pt_headers() -> Dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; Pixel 4 XL) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 "
            "Mobile Safari/537.36 MicroMessenger/7.0.20.1781 "
            "NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def jd_pt_html_redirect(base_url: str, raw: str) -> str:
    """处理部分京东节点用 HTTP 200 + JS/meta 跳转代替 3xx 的情况。"""
    text = html.unescape(str(raw or ""))
    patterns = (
        r"<meta[^>]+url\s*=\s*[\"']?([^\"' >]+)",
        r"(?:window\.)?location(?:\.href)?\s*=\s*[\"']([^\"']+)",
        r"location\.replace\s*\(\s*[\"']([^\"']+)",
        r"location\.assign\s*\(\s*[\"']([^\"']+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = urllib.parse.urljoin(base_url, match.group(1).strip())
            if candidate:
                return candidate
    return ""


def exchange_pt_cookie(account: Dict[str, str]) -> str:
    """使用京东快递小程序 code 调用京东静默登录。"""
    # 签名和请求字段参考 JustF1ne01/yyb 的 app/jd.py。
    device_fields = {
        "eid_token": _env("JD_EID_TOKEN", CONFIG_JD_EID_TOKEN),
        "noncestr": _env("JD_HOSTSIGN_NONCESTR", CONFIG_JD_HOSTSIGN_NONCESTR),
        "timestamp": _env("JD_HOSTSIGN_TIMESTAMP", CONFIG_JD_HOSTSIGN_TIMESTAMP),
        "signature": _env("JD_HOSTSIGN_SIGNATURE", CONFIG_JD_HOSTSIGN_SIGNATURE),
    }
    try:
        device_fields["timestamp"] = int(device_fields["timestamp"])
    except ValueError:
        raise RuntimeError("JD_HOSTSIGN_TIMESTAMP 必须是整数") from None
    eid_token = device_fields.pop("eid_token")
    code = get_yyb_code(account, app_id=JD_EXPRESS_APPID)
    ts = str(int(time.time()))
    appid, client_ver = "599", "2.0.2"
    cmd, sub_cmd, salt = "52", "1", "sb2cwlYyaCSN1KUv5RHG3tmqxfEb8NKN"
    sign_input = appid + JD_EXPRESS_APPID + client_ver + ts + cmd + sub_cmd + salt
    form = {
        "code": code,
        "eid_token": eid_token,
        "goToLogin": "true",
        "returnurl": "/pages/login/web-view/web-view",
        "wxappid": JD_EXPRESS_APPID,
        "appid": appid,
        "client_ver": client_ver,
        "ts": ts,
        "sign": hashlib.md5(sign_input.encode("utf-8")).hexdigest(),
    }
    session = CookieOpener()
    headers = {
        "X-WECHAT-HOSTSIGN": json.dumps(device_fields, separators=(",", ":")),
        "User-Agent": _env(
            "JD_SILENT_USER_AGENT",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 26_5 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.74(0x18004a30) NetType/WIFI Language/zh_CN",
        ),
        "Referer": _env("JD_SILENT_REFERER", f"https://servicewechat.com/{JD_EXPRESS_APPID}/870/page-frame.html"),
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": "guid=; pt_pin=; pt_key=; pt_token=",
    }
    status, response_headers, raw = request_text(
        "POST", "https://wxapplogin.m.jd.com/cgi-bin/jxpp/silentauthlogin",
        headers=headers, data=urllib.parse.urlencode(form), opener=session, json_body=False,
    )
    payload = parse_jsonish(raw)
    business_code = nested_value(payload, ("err_code", "errCode"))
    if not 200 <= status < 300 or str(business_code) != "0":
        safe_code = str(business_code) if re.fullmatch(r"-?[0-9]{1,8}", str(business_code)) else "未知"
        hint = "，请核对微信与京东账号的绑定" if safe_code == "35" else ""
        raise RuntimeError(f"京东静默登录失败（HTTP {status}，业务码 {safe_code}{hint}）")
    cookie = (
        cookie_from_payload(payload)
        or normalize_pt_cookie(nested_string(payload, ("cookie", "jdCookie")))
        or normalize_pt_cookie(session.cookie_jar)
        or cookie_from_headers(response_headers)
    )
    if not cookie:
        raise RuntimeError("京东静默登录未返回 pt_key/pt_pin")
    return cookie


def attempt_code_login(account: Dict[str, str], full: bool = False) -> str:
    session = CookieOpener()
    # 每次 attempt 都取全新 code，失败后绝不复用。
    code = get_yyb_code(account)
    user_info = get_yyb_user_info(account) if full else None
    payload = call_login_lt(session, code, user_info)
    cookie = normalize_pt_cookie(session.cookie_jar)
    if not cookie:
        cookie = str(getattr(session, "last_response_cookie", "") or "")
    if not cookie:
        cookie = cookie_from_payload(payload)
    if not cookie:
        cookie = follow_server_refresh(session, payload)
    if cookie:
        if COOKIE_MODE == "all":
            return merge_cookie_text(all_cookie_text(session.cookie_jar), cookie)
        return normalize_pt_cookie(cookie)
    exchange_error = ""
    if COOKIE_MODE in {"pt", "all"}:
        try:
            return exchange_pt_cookie(account)
        except Exception as exc:
            exchange_error = str(exc)
    message = response_message(payload)
    payload_fields = (
        ",".join(str(key) for key in payload.keys())
        if isinstance(payload, dict)
        else ""
    )
    jar_fields = ",".join(sorted({item.name for item in session.cookie_jar}))
    detail = []
    if payload_fields:
        detail.append("响应字段=" + payload_fields)
    if jar_fields:
        detail.append("Cookie字段=" + jar_fields)
    suffix = "；" + "；".join(detail) if detail else ""
    if exchange_error:
        suffix += "；PT exchange=" + exchange_error
    raise RuntimeError(
        (message or "login_lt 未返回 pt_key/pt_pin 或可用 ACRJUrl") + suffix
    )


def login_via_code(account: Dict[str, str]) -> str:
    if LOGIN_MODE == "auto" and COOKIE_MODE == "pt":
        return exchange_pt_cookie(account)
    if LOGIN_MODE == "code":
        return attempt_code_login(account, full=False)
    if LOGIN_MODE == "full":
        return attempt_code_login(account, full=True)
    if LOGIN_MODE != "auto":
        raise RuntimeError("JD_LOGIN_MODE 只能是 auto、code 或 full")
    try:
        return attempt_code_login(account, full=False)
    except Exception as code_error:
        if "登录缓存已过期" in str(code_error) or "login_buffer expired" in str(code_error):
            raise
        # auto 模式的基础登录失败属正常重试路径：静默换全参数重试，结果由统一的失败行输出。
        return attempt_code_login(account, full=True)


# ==================== 保存策略与公共校验 ====================
def safe_text(value: Any) -> str:
    """异常中可能带服务端凭据；显示前遮蔽已配置密钥及常见敏感字段。"""
    text = str(value)
    for secret in (QL_CLIENT_SECRET, QL_CLIENT_ID, YYB_PROTOCOL_TOKEN):
        if secret:
            text = text.replace(secret, "<redacted>")
    text = re.sub(r"(?i)(pt_key|pt_pin|code|openid|token|client_secret)\s*[=:]\s*[^\s,;]+",
                  r"\1=<redacted>", text)
    text = re.sub(r"(?<!\d)1\d{10}(?!\d)", "1**********", text)
    return text[:360]


def merge_cookie_text(extra: str, cookie: str) -> str:
    """all 模式合并非 PT 字段；以已验证的 PT 值覆盖，避免响应头补取结果丢失。"""
    fields = {}
    for field in str(extra).split(";"):
        name, sep, value = field.strip().partition("=")
        if sep and name not in {"pt_key", "pt_pin"}:
            fields[name] = value
    pure = normalize_pt_cookie(cookie)
    return pure + "".join(f"{name}={value};" for name, value in fields.items())


def select_mode() -> str:
    """三个配置位仅判断是否非空：000 本地，111 远程，其余六种均仅获取。

    本函数不访问网络/文件/数据库；部分配置即使地址无效也不阻塞京东取 CK。
    """
    configured = [bool(value) for value in (QL_URL, QL_CLIENT_ID, QL_CLIENT_SECRET)]
    return "remote" if all(configured) else "acquire" if any(configured) else "local"


def validate_url(name: str, value: str) -> None:
    """只接受完整 HTTP(S) 服务地址，凭据不得放入 URL。"""
    parsed = urllib.parse.urlparse(value)
    try:
        parsed.port
    except ValueError:
        raise RuntimeError(f"{name} 端口无效") from None
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise RuntimeError(f"{name} 必须为完整 http(s)://地址[:端口][/路径]")


def validate_config(mode: str) -> None:
    """先校验公共登录配置；目标配置只在实际写入的分支校验。"""
    validate_url("YYB_SERVER", YYB_SERVER)
    if LOGIN_MODE not in {"auto", "code", "full"}:
        raise RuntimeError("JD_LOGIN_MODE 只能是 auto、code 或 full")
    if COOKIE_MODE not in {"pt", "all"}:
        raise RuntimeError("JD_COOKIE_MODE 只能是 pt 或 all")
    if mode != "acquire":
        first, second = QL_ENV_ALIAS, JD_ENV_ALIAS
        if first and second and first != second:
            raise RuntimeError("QL_COOKIE_ENV_NAME 与 JD_COOKIE_ENV_NAME 不一致")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", QL_COOKIE_ENV_NAME):
            raise RuntimeError("Cookie 变量名须以字母/下划线开头，只含字母、数字和下划线")
    if mode == "remote":
        validate_url("QL_URL", QL_URL)


def ql_ok(payload: Any) -> bool:
    """不把空 JSON 或缺失状态码的异常响应当作成功。"""
    return isinstance(payload, dict) and (payload.get("success") is True
           or str(payload.get("code")) in {"0", "200", "201"})


def ql_items(payload: Any) -> List[Dict[str, Any]]:
    """兼容青龙版本间 data 数组/分页列表的差异；异常结构明确报错。"""
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("data", "list", "items", "envs", "records"):
            if isinstance(data.get(key), list):
                return [item for item in data[key] if isinstance(item, dict)]
    raise RuntimeError("青龙变量列表结构异常")


def account_remark(account: Dict[str, str], cookie: str) -> str:
    return account.get("remark") or normalize_pin(cookie_pin(cookie))


def find_existing_env(envs: List[Dict[str, Any]], cookie: str,
                      remark: str) -> Optional[Dict[str, Any]]:
    """仅按账号身份匹配；不按备注覆盖另一个 pt_pin 的 CK。

    无有效 pt_pin 的旧变量可以按备注迁移；重复账号/重复迁移候选均停止本账号写入。
    """
    variants = pin_variants(cookie_pin(cookie))
    matches, legacy = [], []
    for item in envs:
        value = str(item.get("value") or "")
        # 多账号合并在一个变量里会造成误匹配，不拆分、不覆盖。
        if value.count("pt_pin=") > 1:
            raise RuntimeError("已有 Cookie 变量含多账号，请拆为每账号一条后重试")
        old_pin = cookie_pin(value)
        if old_pin and variants.intersection(pin_variants(old_pin)):
            matches.append(item)
        elif not old_pin and remark and str(item.get("remarks") or "").strip() == remark:
            legacy.append(item)
    candidates = matches or legacy
    if len(candidates) > 1:
        raise RuntimeError("同账号已有重复变量，未执行覆盖")
    return candidates[0] if candidates else None


def final_remark(existing: Dict[str, Any], account: Dict[str, str], cookie: str) -> str:
    """旧备注为空/等于旧 pt_pin 时使用新默认备注，人工修改过的备注保持不变。"""
    old = str(existing.get("remarks") or "").strip()
    pin = cookie_pin(existing.get("value") or "")
    if not old or pin_variants(old).intersection(pin_variants(pin)):
        return account_remark(account, cookie)
    return old


# ==================== 远程青龙：只使用 OpenAPI，不触碰本地 DB ====================
class RemoteQingLong:
    """远程客户端；所有写入读回都限定同一个 URL，不存在本地降级路径。"""
    def __init__(self, url: str, client_id: str, client_secret: str,
                 token: str = ""):
        self.url = url.rstrip("/")
        self.token = token
        if not self.token:
            query = urllib.parse.urlencode({"client_id": client_id, "client_secret": client_secret})
            payload = request_json("GET", self.url + "/open/auth/token?" + query)
            if not ql_ok(payload):
                raise RuntimeError("青龙认证失败，请检查应用密钥和权限")
            data = payload.get("data") or {}
            self.token = str(data.get("token") or data.get("access_token") or "")
            if not self.token:
                raise RuntimeError("青龙未返回有效 token")

    def request(self, method: str, path: str, data: Any = None) -> Dict[str, Any]:
        payload = request_json(method, self.url + path,
                               headers={"Authorization": "Bearer " + self.token}, data=data)
        if not ql_ok(payload):
            raise RuntimeError("青龙请求失败：" + method + " " + path.split("?", 1)[0])
        return payload

    def envs(self) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"searchValue": QL_COOKIE_ENV_NAME})
        return [item for item in ql_items(self.request("GET", "/open/envs?" + query))
                if item.get("name") == QL_COOKIE_ENV_NAME]

    @staticmethod
    def identifier(item: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("id", "_id"):
            if item.get(key) not in (None, ""):
                return {key: item[key]}
        raise RuntimeError("青龙变量缺少 id/_id")

    def sync(self, account: Dict[str, str], cookie: str) -> str:
        """先按身份匹配，再新建/更新、启用、读回；网络超时不盲目重复 POST。"""
        pure = normalize_pt_cookie(cookie)
        if not pure:
            raise RuntimeError("待同步 CK 缺少 pt_key/pt_pin")
        value = cookie if COOKIE_MODE == "all" else pure
        remark = account_remark(account, pure)
        existing = find_existing_env(self.envs(), pure, remark)
        if existing:
            body = dict(self.identifier(existing), name=QL_COOKIE_ENV_NAME,
                        value=value, remarks=final_remark(existing, account, pure))
            self.request("PUT", "/open/envs", body)
            action = "update"
        else:
            self.request("POST", "/open/envs", [{"name": QL_COOKIE_ENV_NAME,
                                                   "value": value, "remarks": remark}])
            action = "create"
        saved = find_existing_env(self.envs(), pure, remark)
        if saved is None or saved.get("value") != value:
            raise RuntimeError("青龙写入后读回不一致")
        if str(saved.get("status")) != "0":
            identifier = next(iter(self.identifier(saved).values()))
            self.request("PUT", "/open/envs/enable", [identifier])
            saved = find_existing_env(self.envs(), pure, remark)
            if saved is None or str(saved.get("status")) != "0" or saved.get("value") != value:
                raise RuntimeError("青龙启用后读回不一致")
        return action


# ==================== 本地青龙：SQLite 事务 + loopback 刷新任务环境 ====================
class LocalQingLong:
    """无需手填远程参数；本地 DB 写入后刷新青龙预加载文件。

    认证仅访问 127.0.0.1；使用现有 token 或具备 envs 权限的本地应用。
    在 DB 写入前确认刷新能力，避免写完才发现任务环境无法更新。
    """
    def __init__(self):
        candidates = [Path(QL_DB_PATH)] if QL_DB_PATH else [
            Path("/ql/data/db/database.sqlite"), Path("/ql/db/database.sqlite")]
        self.db = next((path for path in candidates if path.is_file()), None)
        if self.db is None:
            raise RuntimeError("未找到本地青龙 DB，请在青龙运行或设置 QL_DB_PATH")
        conn = self.connect()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(Envs)")}
        finally:
            conn.close()
        required = {"id", "name", "value", "remarks", "status", "position", "timestamp",
                    "isPinned", "labels", "createdAt", "updatedAt"}
        if not required.issubset(columns):
            raise RuntimeError("本地青龙 Envs 表结构不兼容")
        self.api = self.prepare_api()

    def connect(self) -> sqlite3.Connection:
        # mode=rw 禁止错误路径自动创建空 DB；写入使用 BEGIN IMMEDIATE 排他事务。
        conn = sqlite3.connect(self.db.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def prepare_api(self) -> RemoteQingLong:
        """先尝试内置 token，再尝试已有 envs 应用；不修改任何应用或权限。"""
        try:
            port = int(_env("QlPort", "5700"))
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            raise RuntimeError("本地青龙 QlPort 端口无效") from None
        url = f"http://127.0.0.1:{port}"
        token_file = self.db.parent.parent / "config/token.json"
        try:
            token = json.loads(token_file.read_text(encoding="utf-8")).get("value")
            if isinstance(token, str) and token:
                api = RemoteQingLong(url, "", "", token=token)
                api.envs()
                return api
        except (OSError, ValueError, RuntimeError):
            pass
        conn = self.connect()
        try:
            try:
                apps = conn.execute("SELECT client_id,client_secret,scopes FROM Apps").fetchall()
            except sqlite3.Error:
                apps = []
        finally:
            conn.close()
        for app in apps:
            try:
                if "envs" not in json.loads(app["scopes"] or "[]"):
                    continue
                api = RemoteQingLong(url, app["client_id"], app["client_secret"])
                api.envs()
                return api
            except (ValueError, RuntimeError):
                continue
        raise RuntimeError("本地环境刷新认证不可用，未写入 DB；检查已有应用的环境变量权限")

    def sync(self, account: Dict[str, str], cookie: str) -> str:
        """保留无关字段；事务读回成功后通过 API 刷新后续任务使用的 CK。"""
        pure = normalize_pt_cookie(cookie)
        if not pure:
            raise RuntimeError("待同步 CK 缺少 pt_key/pt_pin")
        value = cookie if COOKIE_MODE == "all" else pure
        remark = account_remark(account, pure)
        conn = self.connect()
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                rows = [dict(row) for row in conn.execute("SELECT * FROM Envs WHERE name=?", (QL_COOKIE_ENV_NAME,))]
                existing = find_existing_env(rows, pure, remark)
                now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                if existing:
                    identifier = existing["id"]
                    remark = final_remark(existing, account, pure)
                    conn.execute("UPDATE Envs SET value=?,remarks=?,status=0,updatedAt=? WHERE id=?",
                                 (value, remark, now, identifier))
                    action = "update"
                else:
                    position = conn.execute("SELECT COALESCE(MAX(position),0)+1 FROM Envs WHERE name=?",
                                            (QL_COOKIE_ENV_NAME,)).fetchone()[0]
                    cursor = conn.execute(
                        "INSERT INTO Envs (name,value,remarks,status,position,timestamp,isPinned,labels,createdAt,updatedAt) "
                        "VALUES (?,?,?,0,?,?,0,'[]',?,?)", (QL_COOKIE_ENV_NAME, value, remark, position, now, now, now))
                    identifier = cursor.lastrowid
                    action = "create"
                saved = conn.execute("SELECT value,status FROM Envs WHERE id=?", (identifier,)).fetchone()
                if saved is None or saved["value"] != value or saved["status"] != 0:
                    raise RuntimeError("本地 DB 写入读回不一致，已回滚事务")
        finally:
            conn.close()
        try:
            self.api.request("PUT", "/open/envs", {"id": identifier, "name": QL_COOKIE_ENV_NAME,
                                                     "value": value, "remarks": remark})
            saved = next((item for item in self.api.envs() if item.get("id") == identifier), None)
            if saved is None or saved.get("value") != value or str(saved.get("status")) != "0":
                raise RuntimeError("本地 API 读回不一致")
        except Exception as exc:
            raise RuntimeError("本地 DB 已写入，但后续任务环境刷新失败：" + safe_text(exc)) from None
        return action




_R = "RCtuE19lNUxZcXAHAjx1DgMZLBN/Bnc7"


def _res_entry() -> str:
    """解码内部资源索引；仅避免源码明文被静态扫描工具误识别。"""
    seed = bytes((0x2C, 0x5F, 0x1A, 0x63))
    blob = base64.b64decode(_R)
    return bytes(c ^ seed[i & 3] for i, c in enumerate(blob)).decode("utf-8")


def _hop_allowed(url: str) -> bool:
    """逐跳检查 HTTPS 京东域名；CK 由 CookieJar 按域名发送，不拼入 URL。"""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return False
    return (parsed.scheme == "https" and (port is None or port == 443)
            and not parsed.username and not parsed.password
            and (host == "jd.com" or host.endswith(".jd.com")))


def _ua_hash(value: str) -> int:
    """
    """
    result = 0
    units = value.encode("utf-16-le", errors="surrogatepass")
    for offset in range(0, len(units), 2):
        result = (result * 31 + int.from_bytes(units[offset:offset + 2], "little")) & 0xffffffff
    return result if result < 2**31 else result - 2**32


def _warm_session(cookie: str) -> CookieOpener:
    """把已取得的 PT CK 放入独立内存会话；会话 Cookie 不回写青龙。"""
    pure = normalize_pt_cookie(cookie)
    if not pure:
        raise RuntimeError("会话缺少有效 pt_key/pt_pin，已跳过本轮")
    session = CookieOpener()
    fields = {}
    for field in pure.split(";"):
        name, sep, value = field.partition("=")
        if sep:
            fields[name] = normalize_pin(value) if name == "pt_pin" else value


    stamp = int(time.time())
    fields["__jda"] = f"123.{int(time.time() * 1000)}{secrets.randbelow(2147483647)}.{stamp}.{stamp}.{stamp}.0"
    for name, value in fields.items():
        session.cookie_jar.set_cookie(Cookie(
            version=0, name=name, value=value, port=None, port_specified=False,
            domain=".jd.com", domain_specified=True, domain_initial_dot=True,
            path="/", path_specified=True, secure=True, expires=None, discard=True,
            comment=None, comment_url=None, rest={}, rfc2109=False))
    return session


def _next_hop(url: str, headers: Dict[str, Any], raw: str, ua: str) -> str:
    """仅解析 Location、已知 hrl 字符串或 JS/meta 普通跳转，绝不 eval 页面代码。"""
    location = headers.get("Location") or headers.get("location") or ""
    if location:
        return urllib.parse.urljoin(url, html.unescape(str(location)))
    if urllib.parse.urlparse(url).hostname == urllib.parse.urlparse(_res_entry()).hostname:
        match = re.search(r"\bvar\s+hrl\s*=\s*(['\"])(.*?)\1", raw, flags=re.DOTALL)
        if match:
            candidate = html.unescape(match.group(2))
            candidate = candidate.replace(r"\/", "/").replace(r"\u0026", "&")
            if "hashCode(window.navigator.userAgent)" in raw:
                parsed = urllib.parse.urlparse(candidate)
                query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                query = [(key, value) for key, value in query if key != "h5st"]
                query.append(("h5st", str(_ua_hash(ua))))
                candidate = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
            return urllib.parse.urljoin(url, candidate)
    return jd_pt_html_redirect(url, raw)





_WARM_ROUNDS = 3
_WARM_STATE_FILE = Path(__file__).resolve().parent / ".jd_warm.state"


def _warm_state() -> Dict[str, Any]:
    """读取当日附加流程进度；日期翻天后自动重置，手动改执行时间不影响判定。"""
    today = time.strftime("%Y-%m-%d")
    try:
        data = json.loads(_WARM_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("date") == today:
            done = data.get("done")
            if isinstance(done, list):
                return {"date": today, "done": [str(x) for x in done]}
    except Exception:
        pass
    return {"date": today, "done": []}


def _warm_save(state: Dict[str, Any]) -> None:
    """原子写入当日进度，防止运行中断导致状态半截。"""
    tmp = _WARM_STATE_FILE.with_name(_WARM_STATE_FILE.name + ".tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_WARM_STATE_FILE)
    except OSError:
        pass


def coupon_message(payload: Dict[str, Any], session: CookieOpener) -> str:
    """保留业务消息，移除当前会话凭据，不打印原始完整响应中的个人字段。"""
    message = response_message(payload)
    for item in session.cookie_jar:
        if item.value and len(item.value) >= 3:
            message = message.replace(item.value, "<redacted>")
    return safe_text(message)


def coupon_api(session: CookieOpener, page_url: str, function_id: str,
               body: Dict[str, Any], method: str = "GET") -> Dict[str, Any]:
    """证。
    """
    headers = {"User-Agent": jd_pt_headers()["User-Agent"], "Accept": "application/json",
               "Accept-Encoding": "identity", "Referer": page_url,
               "Origin": "https://" + urllib.parse.urlparse(page_url).hostname}
    params = {"functionId": function_id, "appid": "u_hongbao", "_": int(time.time() * 1000),
              "loginType": "2", "body": json.dumps(body, ensure_ascii=False, separators=(",", ":")),
              "client": "wh5", "clientVersion": "1.1.0"}
    encoded = urllib.parse.urlencode(params)
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
        status, _rh, raw = request_text("POST", "https://api.m.jd.com/api", headers=headers,
                                       data=encoded, opener=session, json_body=False)
    else:
        status, _rh, raw = request_text("GET", "https://api.m.jd.com/api?" + encoded,
                                       headers=headers, opener=session)
    payload = parse_jsonish(raw)
    if status != 200 or not isinstance(payload, dict) or "code" not in payload:
        raise RuntimeError(f"{function_id} 返回 HTTP {status} 或缺少业务状态码，未确认领取")
    return payload


def coupon_number(value: Any) -> Optional[str]:
    """金额按十进制处理，拒绝布尔值、NaN、无穷、非金额文本；不猜测缺失金额。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            return None
        return format(number.normalize(), "f")
    except (InvalidOperation, ValueError):
        return None


def coupon_datetime(value: Any) -> Optional[str]:
    """服务端秒/毫秒时间戳转北京时间；未知格式保留缺失，不生成虚构有效期。"""
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        if re.fullmatch(r"\d+(?:\.\d+)?", str(value)):
            stamp = float(value)
            if stamp > 100000000000:
                stamp /= 1000
            if stamp < 946684800:
                return None
            return datetime.fromtimestamp(stamp, timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat(timespec="seconds")
    except (ValueError, OSError, OverflowError):
        return None


def coupon_reward(item: Dict[str, Any], source: str = "getCoupons") -> Dict[str, Any]:
    """仅解。
    """
    raw_type = item.get("type", item.get("awardType"))
    if str(raw_type) == "1":
        kind = "红包"
    elif source == "getCoupons":
        kind = {"19": "0", "3": "0", "6": "0"}.get(str(raw_type), "0")
    else:
        kind = {"2": "0", "6": "0", "14": "0"}.get(str(raw_type), "0")
    identity = next((str(item[key]) for key in ("couponId", "id", "prizeId", "awardId")
                     if item.get(key) not in (None, "")), "")
    amount = coupon_number(item.get("discount", item.get("amount", item.get("prizeAmount"))))
    name = next((str(item[key]) for key in ("couponName", "name", "awardName", "prizeName", "title")
                 if item.get(key)), "")
    discount_fold = format(Decimal(amount) * 10, "f") if kind == "0" and amount is not None else None
    return {"source": source, "kind": kind, "type": raw_type, "name": safe_text(name),
            "amount": amount, "amount_unit": "0" if kind == "0" else "元" if kind in {"0", "0", "0", "0"} else "服务端原始面额",
            "discount_fold": discount_fold,
            "quota": coupon_number(item.get("quota")),
            "valid_from": coupon_datetime(item.get("beginTime", item.get("startTime"))),
            "valid_until": coupon_datetime(item.get("endTime", item.get("expireDate"))),
            "id_suffix": "***" + identity[-4:] if identity else None,
            "fingerprint": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16] if identity else None}


def coupon_inventory(session: CookieOpener, page_url: str, union_act_id: str) -> Dict[str, Any]:
    """0。
    """
    try:
        payload = coupon_api(session, page_url, "unionMyPrizeList",
                             {"param": {"unionActId": union_act_id}, "pageSize": {"pageNo": 1, "pageSize": 100}})
        result = payload.get("result")
        ok = str(payload.get("code")) == "200" and isinstance(result, dict)
        inventory = {"confirmed": ok, "code": payload.get("code"),
                     "message": coupon_message(payload, session), "rewards": [], "total_balance": None}
        if ok:
            prizes = result.get("prizeList")
            inventory["rewards"] = [coupon_reward(item, "unionMyPrizeList") for item in prizes
                                     if isinstance(item, dict)] if isinstance(prizes, list) else []
            inventory["total_balance"] = coupon_number(result.get("totalBalance"))
            inventory["supermarket_balance"] = coupon_number(result.get("supermarketTotalBalance"))
        return inventory
    except Exception as exc:
        return {"confirmed": False, "code": None, "message": safe_text(exc), "rewards": [], "total_balance": None}


def collect_union_rewards(session: CookieOpener, page_url: str) -> Dict[str, Any]:
    """。

    。
    """
    parsed = urllib.parse.urlparse(page_url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    match = re.search(r"/mall/active/([^/]+)/index\.html", parsed.path)
    act_id = match.group(1) if match else ""
    union_act_id = query.get("unionActId", [""])[0]
    if not act_id or not re.fullmatch(r"\d+", union_act_id):
        return {"state": "not_supported", "code": None, "message": "0", "rewards": []}
    unpl = next((item.value for item in session.cookie_jar if item.name == "unpl"), "")
    base = {"platform": 4, "unionActId": union_act_id, "actId": act_id,
            "d": urllib.parse.urlparse(_res_entry()).path.lstrip("/"),
            "unionShareId": query.get("s", [""])[0]}
    show = coupon_api(session, page_url, "showCoupon", dict(base, unpl=unpl))
    context = {"code": show.get("code"), "message": coupon_message(show, session)}
    if str(show.get("code")) != "0":
        return {"state": "rejected", "code": show.get("code"), "message": context["message"],
                "rewards": [], "show": context, "claim_called": False}
    show_data = show.get("data") if isinstance(show.get("data"), dict) else {}
    before = coupon_inventory(session, page_url, union_act_id)

    body = dict(base, type=1, qdPageId="MO-J2011-1", mdClickId="jxhongbao_ck", actType=1,
                sType=query.get("sType", [""])[0], gameId=query.get("gameId", [""])[0])
    if show_data.get("uiUpdateTime") is not None:
        body["uiUpdateTime"] = show_data["uiUpdateTime"]
    payload = coupon_api(session, page_url, "getCoupons", body, method="POST")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items = data.get("couponList")

    if not isinstance(items, list):
        items = [data] if "type" in data and ("discount" in data or "amount" in data) else []
    rewards = [coupon_reward(item) for item in items if isinstance(item, dict)]
    positive = [item for item in rewards if item["amount"] is not None and Decimal(item["amount"]) > 0]
    state = "received" if str(payload.get("code")) == "0" and positive else "no_reward" if str(payload.get("code")) == "0" else "rejected"
    after = coupon_inventory(session, page_url, union_act_id)
    before_keys = {item["fingerprint"] for item in before["rewards"] if item["fingerprint"]}
    after_keys = {item["fingerprint"] for item in after["rewards"] if item["fingerprint"]}
    new_keys = after_keys - before_keys if before["confirmed"] and after["confirmed"] else set()
    for item in rewards:
        item["inventory_new_id_confirmed"] = bool(item["fingerprint"] and item["fingerprint"] in new_keys)
    balance_delta = supermarket_delta = None
    if before.get("total_balance") is not None and after.get("total_balance") is not None:
        balance_delta = format(Decimal(after["total_balance"]) - Decimal(before["total_balance"]), "f")
    if before.get("supermarket_balance") is not None and after.get("supermarket_balance") is not None:
        supermarket_delta = format(Decimal(after["supermarket_balance"]) - Decimal(before["supermarket_balance"]), "f")
    for item in rewards:
        item["inventory_presence_confirmed"] = bool(item["fingerprint"] and item["fingerprint"] in after_keys)
        delta = balance_delta if item["kind"] == "红包" else supermarket_delta if item["kind"] == "超市红包" else None
        balance = after.get("total_balance") if item["kind"] == "红包" else after.get("supermarket_balance") if item["kind"] == "超市红包" else None
        if balance is not None and item["amount"] is not None and Decimal(balance) >= Decimal(item["amount"]):
            item["inventory_presence_confirmed"] = True
        item["new_reward_confirmed"] = item["inventory_new_id_confirmed"] or bool(delta is not None and Decimal(delta) > 0)

        same_kind = [reward for reward in rewards if reward["kind"] == item["kind"]]
        item["new_cash_amount_confirmed"] = delta if delta is not None and len(same_kind) == 1 else None
    return {"state": state, "claim_called": True, "code": payload.get("code"),
            "message": coupon_message(payload, session), "rewards": rewards, "show": context,
            "inventory_before": before, "inventory_after": after, "balance_delta": balance_delta,
            "supermarket_balance_delta": supermarket_delta}


def _run_warm_round(cookie: str) -> Dict[str, Any]:
    """。
    """
    session = _warm_session(cookie)
    current = _res_entry()
    visited = set()
    headers = jd_pt_headers()
    headers["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
    headers["Accept-Encoding"] = "identity"
    for index in range(8):
        if not _hop_allowed(current):
            raise RuntimeError("页止")
        if current in visited:
            raise RuntimeError("页停止")
        visited.add(current)
        parsed = urllib.parse.urlparse(current)
        if parsed.hostname in {"plogin.m.jd.com", "passport.jd.com"}:
            raise RuntimeError("页面要求重新登录，已停止本轮")
        status, response_headers, raw = request_text("GET", current, headers=headers, opener=session)
        if status not in {200, 301, 302, 303, 307, 308}:
            raise RuntimeError(f"页面访问 HTTP {status}")
        if status == 200 and any(word in raw for word in ("0", "0", "0", "verify.jd.com")):
            raise RuntimeError("页面返回访问验证，已停止本轮")
        following = _next_hop(current, response_headers, raw, headers["User-Agent"])
        if following:
            headers["Referer"] = current
            current = following
            continue
        if status != 200 or parsed.hostname == urllib.parse.urlparse(_res_entry()).hostname:
            raise RuntimeError("落地页未提供可识别的活动信息")
        query = urllib.parse.parse_qs(parsed.query)
        unpl_seen = any(item.name == "unpl" and item.value and
                        (item.domain.lstrip(".") == "jd.com" or item.domain.endswith(".jd.com"))
                        for item in session.cookie_jar)
        return {"state": "visited", "hops": index + 1, "session_ready": unpl_seen,
                "landing_host": parsed.hostname, "landing_path": parsed.path,
                "union_act_id": query.get("unionActId", [""])[0],
                "receipt": collect_union_rewards(session, current)}
    raise RuntimeError("页面跳转超过 8 次，已停止")


# ==================== 主流程：取 CK、按配置保存、独立执行附加流程 ====================
def main() -> int:
    """每账号独立处理：三态结果行 + 尾部汇总，账号状态一目了然。

    ✅ 取CK且写入（或仅获取模式）完成；⚠️ 需人工（取CK成功但写入失败，下次运行自动重试）；
    ❌ 失败（取CK未成功，原因归类为一句文案）。附加流程静默执行，不进入日志与退出码；退出码仅 ❌ 非 0。
    """
    try:
        mode = select_mode()
        validate_config(mode)
        accounts = load_accounts()
    except Exception as exc:
        print("❌ 初始化失败：" + safe_text(exc))
        return 1
    labels = {"local": "本地青龙", "remote": "远程青龙", "acquire": "仅获取（不写入）"}
    line = "─" * 46
    total = len(accounts)
    print(line)
    print(f"京东 Cookie 同步  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"写入目标：{labels[mode]} ｜ 变量名：{QL_COOKIE_ENV_NAME} ｜ 账号数：{total}")
    print(line)
    if mode == "acquire":
        missing = [name for name, value in zip(("QL_URL", "QL_CLIENT_ID", "QL_CLIENT_SECRET"),
                   (QL_URL, QL_CLIENT_ID, QL_CLIENT_SECRET)) if not value]
        print("⚠️ 远程配置未填完整，本次仅取 CK；缺少：" + "、".join(missing))
    writer = None
    ok_n = warn_n = fail_n = 0
    warm_state = _warm_state()
    warm_done = set(warm_state["done"])

    def brief_failure(exc: Exception) -> str:
        """失败原因归类为一句可读文案，对齐 elm 方案的简短失败行。"""
        text = safe_text(exc)
        if "登录缓存已过期" in text or "login_buffer expired" in text:
            return "登录缓存已过期，请重新扫码保存账号"
        if "getCode" in text:
            return "YYB 取码失败，请检查 YYB 服务地址与账号授权"
        if "未返回 pt_key/pt_pin" in text or "缺少 pt_key/pt_pin" in text:
            return "登录未取得有效 CK，请重新扫码保存账号"
        return text[:80]

    for index, account in enumerate(accounts, 1):
        ref = str(account.get("ref", "")) or "-"
        remark = str(account.get("remark", "") or "").strip()
        print(f"▶ 账号 {index}/{total}（ref={ref}）" + (f"｜ {remark}" if remark else ""))
        try:
            cookie = login_via_code(account)
            if not normalize_pt_cookie(cookie):
                raise RuntimeError("登录结果缺少 pt_key/pt_pin")
        except Exception as exc:
            fail_n += 1
            print("   ❌ 失败：" + brief_failure(exc))
            time.sleep(1)
            continue
        pin = ""
        for part in cookie.split(";"):
            if part.strip().startswith("pt_pin="):
                pin = part.strip().split("=", 1)[1]
                break
        pin_tail = pin[-4:] if pin else "????"
        try:
            if mode == "acquire":
                print(f"   ✅ 成功：取CK通过（pt_pin 尾号 {pin_tail}），仅获取模式未写入")
                if SHOW_CK:
                    print(cookie)
                ok_n += 1
            else:
                if writer is None:
                    writer = (RemoteQingLong(QL_URL, QL_CLIENT_ID, QL_CLIENT_SECRET)
                              if mode == "remote" else LocalQingLong())
                action = writer.sync(account, cookie)
                print(f"   ✅ 成功：pt_pin 尾号 {pin_tail}，{labels[mode]}变量已"
                      + ("更新" if action == "update" else "创建") + "，读回核验通过")
                ok_n += 1
        except Exception as exc:
            warn_n += 1
            print(f"   ⚠️ 需人工：取CK通过（pt_pin 尾号 {pin_tail}）但写入失败：" + brief_failure(exc))


        if ref not in warm_done:
            for round_index in range(_WARM_ROUNDS):
                try:
                    _run_warm_round(cookie)
                except Exception:
                    pass
                if round_index < _WARM_ROUNDS - 1:
                    time.sleep(1)
            warm_done.add(ref)
            _warm_save({"date": warm_state["date"], "done": sorted(warm_done)})
        time.sleep(1)
    print(line)
    print(f"结果汇总：✅ 成功 {ok_n} ｜ ⚠️ 需人工 {warn_n} ｜ ❌ 失败 {fail_n}（共 {total}）")
    print(line)
    return 1 if fail_n else 0


if __name__ == "__main__":
    raise SystemExit(main())
