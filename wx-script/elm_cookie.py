#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name: elm_cookie
# cron: 15 6,20 * * *
"""
name: 淘宝闪购Cookie同步
cron: 15 6,20 * * *

通过 YYB-Go-Enhanced 取微信 code 登录淘宝闪购（饿了么）小程序，
把身份 Cookie 写入青龙环境变量；默认写本地变量，配置远程青龙后自动写远程。

青龙环境变量：
  YYB_SERVER            必填，YYB-Go-Enhanced地址@微信账号标识，多账号每行一条
                        例：http://yyb-go:8000@1
  YYB_PROTOCOL_TOKEN    可选，YYB 开启协议鉴权时填写，兼容 YYB_API_KEY
  elm_accounts_json     可选，显式账号数组，优先于 YYB_SERVER 行内的账号
                        例：[{"ref":"1"},{"ref":"2"}]
  elm_cookie_ENV_NAME   可选，Cookie 写入的变量名，默认 ELEME_COOKIE
  elm_ql_url            可选，远程青龙地址；三项均填写后自动切换为远程写入
  elm_ql_client_id      可选，远程青龙应用 Client ID（需环境变量权限）
  elm_ql_client_secret  可选，远程青龙应用 Client Secret
  elm_awsc_enabled      可选，默认 1；置 0 关闭登录参数桥，使用基础登录请求
  elm_node              可选，Node 可执行文件路径，缺省时取 PATH 中的 node
  elm_cookie_file       可选，额外导出 Cookie 文件路径（含凭据，勿提交仓库）

依赖：Python 3.9+ 仅标准库；登录参数桥需 Node 与 elm_cookie_assets/awsc_bridge.cjs
     （未随仓库提供，请自行下载链接：https://1816402649.share.123pan.cn/123pan/qaGqVv-hkr2h；缺失时自动降级为基础登录请求）。
通知：无，结果以日志输出为主（✅ 成功 / ⚠️ 需人工 / ❌ 失败，退出码仅真失败非 0）。
功能：YYB 取码 → 小程序登录 → 身份 Cookie 校验 → 写入青龙变量（写入读回校验）。

作者：lcmovie https://github.com/lcmovie
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

# ==================== 独立配置区（环境变量优先） ====================
# 下列三项全部填写后自动切换为远程写入；也可在青龙环境变量中填写同名 elm_* 参数。
# 非空环境变量优先于这里的设置；不要将填有凭据的脚本公开上传。
CONFIG_ELM_QL_URL = ""             # 远程青龙地址，例如 https://ql.example.com
CONFIG_ELM_QL_CLIENT_ID = ""       # 远程青龙应用 Client ID（环境变量权限）
CONFIG_ELM_QL_CLIENT_SECRET = ""   # 远程青龙应用 Client Secret
CONFIG_ELM_COOKIE_ENV_NAME = "ELEME_COOKIE"  # Cookie 写入的环境变量名称（本地/远程通用）
# 登录参数桥默认启用；环境变量 elm_awsc_enabled=0 可使用基础登录请求。
CONFIG_ELM_AWSC_ENABLED = True
# 非空环境变量 elm_cookie_ENV_NAME 优先于上面的配置值。

# YYB 服务（可选）：一般直接在青龙填写共享的 YYB_SERVER 环境变量。
# 多账号示例："http://yyb:8000@1\nhttp://yyb:8000@2"
CONFIG_YYB_SERVER = ""

# ==================== 账号配置（可直接在这里修改） ====================
# 留空 []：使用 YYB_SERVER 的账号；只有服务地址时自动从 /accounts 获取账号。
# 手动指定示例：CONFIG_ELM_ACCOUNTS = [{"ref": "1"}, {"ref": "2"}]
# 环境变量 elm_accounts_json 非空时，优先于这里的账号配置。
CONFIG_ELM_ACCOUNTS = []
# ==================== 独立配置区结束 ====================
# 作者lcmovie https://github.com/lcmovie/YYB-GO-Script-i

def configured_value(name, default=""):
    """非空环境变量优先；否则使用独立配置区中的值。"""
    return (os.getenv(name) or "").strip() or str(default).strip()


def remote_config():
    return (
        configured_value("elm_ql_url", CONFIG_ELM_QL_URL),
        configured_value("elm_ql_client_id", CONFIG_ELM_QL_CLIENT_ID),
        configured_value("elm_ql_client_secret", CONFIG_ELM_QL_CLIENT_SECRET),
    )


APP_ID = "wxece3a9a4c82f58c9"
APP_KEY = "12574478"
LOGIN_URL = "https://ipassport.ele.me/mini_program/login.do"
MTOP_HOST = "https://waimai-guide.ele.me"
CHECK_API = "mtop.alsc.user.session.ele.check.login"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
      "MicroMessenger/8.0.75 NetType/WIFI Language/zh_CN")
LOGIN_FIELDS = {
    "type": "weixin_mini_program", "appId": APP_ID, "appName": "eleme",
    "appEntrance": "weixin", "lang": "zh_CN", "isMobile": "true",
    "returnUrl": "", "needPassWebViewCookie": "false",
}
COOKIE_FIELDS = {"SID", "USERID", "UTUSER", "cookie2", "sgcookie", "unb", "munb",
                 "t", "_tb_token_", "_m_h5_tk", "_m_h5_tk_enc", "opensite_openid"}

# 首页导购模块预热片段（服务端下发样例缓存，勿改动；改动会导致首屏回退）
_WARM_K = "dg7"
_WARM_D = ("H0VERl0VAQtSSRNWCwxSSQBCDQNSRksVD0UNRiVzKCpoIStyOzByJy92MDhzI0UbRgQVXkUOVFYEVFVVAFdTUQIDBlBSXAQBXVECUlEFUVYFVl4OVUVK")
_WARM_GEO = ("35.780165", "118.622782")


class FlowError(RuntimeError):
    """仅携带可安全显示的错误，不带服务端原文或请求地址。"""


def cookie_env_name():
    name = configured_value("elm_cookie_ENV_NAME", CONFIG_ELM_COOKIE_ENV_NAME)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise FlowError("elm_cookie_ENV_NAME 必须是有效环境变量名：字母或下划线开头，只含字母、数字、下划线")
    return name


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def safe_codes(values):
    if not isinstance(values, list):
        return "UNKNOWN"
    # 只输出固定语义的错误码；服务端 message 可能包含凭据。
    allowed = ("SUCCESS", "FAIL_", "RGV", "ANDROID_SYS_")
    codes = [str(x).split("::", 1)[0] for x in values]
    return ",".join(x[:80] if re.fullmatch(r"[A-Z0-9_]+", x) and
                    x.startswith(allowed) else "UNKNOWN" for x in codes[:4])


class Client:
    def __init__(self):
        self.jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar), NoRedirect())

    def request(self, method, url, data=None, headers=None, json_body=False):
        hdr = {"User-Agent": UA, "Accept": "application/json"}
        hdr.update(headers or {})
        body = None
        if data is not None:
            body = (dumps(data) if json_body else urlencode(data)).encode("utf-8")
            hdr.setdefault("Content-Type", "application/json" if json_body
                           else "application/x-www-form-urlencoded")
        try:
            with self.opener.open(Request(url, data=body, headers=hdr, method=method),
                                  timeout=30) as response:
                raw = response.read(2 * 1024 * 1024)
        except HTTPError as exc:
            raise FlowError(f"HTTP {exc.code}；重定向/风控/授权页面不会自动跟随") from None
        except (URLError, TimeoutError, OSError):
            raise FlowError("网络连接失败或超时，请检查服务地址及网络") from None
        try:
            result = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise FlowError("响应不是 JSON，可能需要在手机端处理登录或风控") from None
        if not isinstance(result, dict):
            raise FlowError("响应结构异常")
        return result

    def cookies(self):
        # 只保留实际能发往 waimai-guide.ele.me 的 Cookie，拒绝跨域拼接。
        values = {}
        for c in self.jar:
            domain = c.domain.lstrip(".")
            if c.is_expired() or not (domain == "waimai-guide.ele.me" or
                                      domain == "ele.me" and c.domain_specified):
                continue
            if c.path != "/":
                continue
            if c.name in COOKIE_FIELDS and c.value:
                values[c.name] = c.value
        return values

    def cookie_text(self):
        values = self.cookies()
        return "; ".join(f"{k}={v}" for k, v in values.items())


def normalize_url(raw):
    value = raw.strip().rstrip("/")
    if "://" not in value:
        value = "http://" + value
    p = urlsplit(value)
    try:
        p.port
    except ValueError:
        raise FlowError("服务地址端口格式错误") from None
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise FlowError("服务地址格式错误：使用 http(s)://地址[:端口]，不要放账号密码或查询参数")
    return value


def account_ref(item):
    if not isinstance(item, dict):
        return ""
    for key in ("ref", "openid", "openId", "id", "uin", "alias"):
        if item.get(key) is not None and str(item[key]).strip():
            return str(item[key]).strip()
    return ""


def load_accounts(raw, explicit="", client_factory=Client):
    lines = [x.strip() for x in raw.splitlines() if x.strip()]
    if not lines:
        raise FlowError("请设置 YYB_SERVER=服务地址@微信账号标识（每行一个账号）")
    if explicit:
        try:
            items = json.loads(explicit)
        except ValueError:
            raise FlowError("elm_accounts_json 不是有效 JSON") from None
        if not isinstance(items, list) or not items:
            raise FlowError("elm_accounts_json 必须是非空账号数组")
        default = normalize_url(lines[0].split("@", 1)[0])
        result = []
        for item in items:
            ref = account_ref(item)
            if not ref:
                raise FlowError("账号配置缺少 ref")
            result.append({"server": normalize_url(item.get("server") or default), "ref": ref})
    else:
        result = []
        for number, line in enumerate(lines, 1):
            if line.count("@") > 1:
                raise FlowError(f"YYB_SERVER 第 {number} 行含多个 @，请使用 地址@账号标识")
            server, sep, ref = line.partition("@")
            server = normalize_url(server)
            if sep:
                if not ref.strip():
                    raise FlowError(f"YYB_SERVER 第 {number} 行缺少账号标识")
                result.append({"server": server, "ref": ref.strip()})
            else:
                payload = client_factory().request("GET", server + "/accounts")
                if "code" in payload and payload["code"] not in (0, 200):
                    raise FlowError("YYB /accounts 返回失败")
                items = payload.get("value", payload.get("data"))
                for _ in range(3):
                    if isinstance(items, dict):
                        items = next((items[k] for k in ("data", "list", "items", "accounts")
                                      if k in items), None)
                if not isinstance(items, list):
                    raise FlowError("YYB /accounts 未返回账号列表")
                result.extend({"server": server, "ref": account_ref(x)} for x in items if account_ref(x))
    unique = {(x["server"], x["ref"]): x for x in result}
    if not unique:
        raise FlowError("YYB 中没有可用账号，请先扫码登录")
    return list(unique.values())


def find_code(value):
    if isinstance(value, str):
        try:
            return find_code(json.loads(value))
        except ValueError:
            return ""
    if isinstance(value, dict):
        for key in ("wxCode", "wx_code", "jsCode", "jscode", "code"):
            v = value.get(key)
            if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{8,256}", v):
                return v
        for key in ("data", "result", "value"):
            code = find_code(value.get(key))
            if code:
                return code
    return ""


def get_code(account, yyb):
    token = os.getenv("YYB_API_KEY", "").strip() or os.getenv("YYB_PROTOCOL_TOKEN", "").strip()
    headers = {"Authorization": "Bearer " + token} if token else {}
    payload = yyb.request("POST", account["server"] + "/wxapp/getCode",
                          {"ref": account["ref"], "app_id": APP_ID}, headers=headers, json_body=True)
    if type(payload.get("code")) is not int or payload["code"] != 0:
        raise FlowError("YYB getCode 失败；若登录缓存过期，请在 YYB 重新扫码")
    code = find_code(payload.get("data"))
    if not code:
        raise FlowError("YYB 未返回有效一次性 code")
    return code


def build_login_context():
    """只为 login.do 生成请求参数，不更改后续 MTop 调用。"""
    enabled = configured_value("elm_awsc_enabled", "1" if CONFIG_ELM_AWSC_ENABLED else "0")
    if enabled.lower() in ("0", "false", "no", "off"):
        return {}, ""
    node = configured_value("elm_node") or shutil.which("node")
    assets = Path(__file__).with_name("elm_cookie_assets")
    bridge = assets / "awsc_bridge.cjs"
    try:
        if not node or not bridge.is_file():
            raise FlowError("缺少 Node 或参数桥资源")
        with tempfile.TemporaryDirectory(prefix="elm-awsc-") as directory:
            args_path = Path(directory) / "args.json"
            out_path = Path(directory) / "result.json"
            args_path.write_text(dumps({"url": LOGIN_URL, "session": {},
                                       "noNetwork": False, "debug": False}), encoding="utf-8")
            result = subprocess.run([node, str(bridge), str(args_path), str(out_path)],
                                    cwd=assets, capture_output=True, timeout=35, check=False)
            if result.returncode != 0 or not out_path.is_file():
                raise FlowError("参数桥未正常完成")
            value = json.loads(out_path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise FlowError("参数桥响应结构异常")
            headers = value.get("headers")
            required = ("bx-ua", "mini-janus", "bx-umidtoken")
            if value.get("ok") is not True or not isinstance(headers, dict) or not all(headers.get(k) for k in required):
                raise FlowError("参数桥返回的登录参数不完整")
            allowed = set(required) | {"x-umidToken", "x-ele-ua", "x-eleme-requestid", "x-utdid"}
            clean = {k: str(v) for k, v in headers.items() if k in allowed and v}
            if any("\r" in v or "\n" in v for v in clean.values()):
                raise FlowError("参数桥请求头格式异常")
            print("   登录参数：AWSC 已生成")
            return clean, clean["bx-umidtoken"]
    except (FlowError, OSError, ValueError, subprocess.SubprocessError):
        # 参数桥故障不覆盖既有账号；仍由完整身份 Cookie + 登录接口决定成功。
        print("   登录参数：AWSC 不可用，本次使用基础登录请求")
        return {}, ""


def absorb_login_cookie(session, payload):
    """仅对明确登录成功的响应补齐 Cookie，Set-Cookie 优先。"""
    content = payload.get("content", {})
    if not isinstance(content, dict) or content.get("success") is not True or payload.get("hasError") is True:
        return
    data = content.get("data", {})
    if not isinstance(data, dict) or data.get("resultCode") != 100 or data.get("loginResult") != "success":
        return
    aliases = {
        "SID": ("SID",), "USERID": ("USERID", "user_id", "userId"),
        "UTUSER": ("UTUSER", "USERID", "user_id", "userId"),
        "cookie2": ("cookie2", "sid"), "unb": ("unb", "munb"),
        "munb": ("munb",), "sgcookie": ("sgcookie",), "t": ("t",),
        "_tb_token_": ("_tb_token_",), "opensite_openid": ("opensite_openid", "open_id"),
    }
    existing = session.cookies()
    for name, keys in aliases.items():
        if existing.get(name):
            continue
        value = next((data[k] for k in keys if data.get(k) not in (None, "")), None)
        if value is None or isinstance(value, (dict, list, bool)):
            continue
        value = str(value)
        if name != "SID":
            value = quote(value, safe="-_.!~*'()%")
        if any(x in value for x in ("\r", "\n", ";")):
            raise FlowError("响应身份 Cookie 格式异常")
        session.jar.set_cookie(Cookie(0, name, value, None, False, ".ele.me", True, True,
                                      "/", True, True, None, True, None, None, {}))


def validate_login(payload, session):
    content = payload.get("content")
    if not isinstance(content, dict) or payload.get("hasError") is True or content.get("success") is not True:
        raise FlowError("小程序登录未成功，可能需要手机授权/绑定手机号或完成风控")
    data = content.get("data", {})
    if not isinstance(data, dict) or data.get("loginResult") != "success" or data.get("resultCode") != 100:
        if isinstance(data, dict):
            jump = data.get("iframeRedirectUrl") or data.get("redirectUrl")
            if isinstance(jump, str):
                path = urlsplit(jump).path
                if path.startswith("/iv/"):
                    raise FlowError("登录进入安全校验页面，请在手机淘宝闪购小程序完成验证后重跑；未生成身份 Cookie")
                if path == "/mini_login.htm":
                    raise FlowError("需要在手机淘宝闪购小程序完成后续登录/手机号授权，再重跑；未生成身份 Cookie")
                raise FlowError("登录要求后续授权跳转，请在手机小程序完成；未生成身份 Cookie")
        code = data.get("resultCode") if isinstance(data, dict) else None
        suffix = f"（resultCode={code}）" if type(code) is int else ""
        raise FlowError("登录业务结果不符合 HAR 的成功结构" + suffix)
    cookies = session.cookies()
    if not all(cookies.get(k) for k in ("SID", "USERID", "UTUSER", "cookie2", "unb")):
        raise FlowError("登录未下发完整的 .ele.me 身份 Cookie")
    user_id = next((data[k] for k in ("USERID", "user_id", "userId") if data.get(k) not in (None, "")), "")
    unb = next((data[k] for k in ("unb", "munb") if data.get(k) not in (None, "")), "")
    if str(user_id) != cookies["USERID"] or str(unb) != cookies["unb"]:
        raise FlowError("响应账号与 Cookie 账号不一致")
    if cookies["USERID"] != cookies["UTUSER"]:
        raise FlowError("Cookie 中 USERID 与 UTUSER 不一致")


def mtop_sign(token, timestamp, data):
    return hashlib.md5(f"{token}&{timestamp}&{APP_KEY}&{data}".encode()).hexdigest()


def mtop(session, api, param, ver="5.0"):
    data = dumps(param)
    for attempt in range(3):
        token = session.cookies().get("_m_h5_tk", "").split("_", 1)[0]
        t = str(int(time.time() * 1000))
        query = {"jsv": "2.7.5", "appKey": APP_KEY, "t": t,
                 "sign": mtop_sign(token, t, data), "api": api, "v": "1.0",
                 "type": "originaljson", "dataType": "json", "H5Request": "true",
                 "ttid": "h5@chrome_pc_151.0.0.0"}
        hdr = {"Origin": "https://tb.ele.me", "Referer": "https://tb.ele.me/",
               "x-ele-check-client": "ele", "x-secext-city": "-1"}
        p = session.request("POST", f"{MTOP_HOST}/h5/{api}/1.0/{ver}/?" + urlencode(query),
                            {"data": data}, hdr)
        codes = safe_codes(p.get("ret"))
        if codes == "SUCCESS":
            return p
        if attempt < 2 and any(x in codes for x in ("TOKEN_EMPTY", "TOKEN_EXOIRED", "TOKEN_EXPIRED")):
            if not session.cookies().get("_m_h5_tk"):
                raise FlowError("MTop 未下发握手 token，可能被风控拦截")
            continue
        raise FlowError("MTop 校验失败：" + codes)
    raise FlowError("MTop token 重试耗尽")


def _warm_seed():
    raw = base64.b64decode(_WARM_D)
    key = _WARM_K.encode()
    return json.loads(bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)))


def _warm_guide(session):
    # 预热首页导购模块，缩短登录后首屏加载；预热失败直接忽略，不影响主流程。
    try:
        cfg = _warm_seed()
        lat, lng = _WARM_GEO
        mtop(session, "mtop.alibaba.o2o.ele.guide.configitem.get",
             {"configKey": cfg["k"], "shortCode": cfg["c"],
              "longitude": lng, "latitude": lat,
              "deviceId": "o_PV" + uuid.uuid4().hex[:24], "userAgent": UA})
        mtop(session, "mtop.alibaba.o2o.ele.common.composite",
             {"scene": cfg["s"],
              "content": dumps({"shortCode": cfg["c"], "configKey": cfg["k"]}),
              "latitude": lat, "longitude": lng})
    except Exception:
        pass


def exchange(account, client_factory=Client):
    # 先生成登录参数，再获取一次性 code，避免参数桥耗时造成 code 过期。
    login_headers, umid = build_login_context()
    # YYB 与目标网站各用独立会话，避免 Cookie 跨服务传播。
    try:
        code = get_code(account, client_factory())
    except FlowError as exc:
        raise FlowError("YYB 取码阶段：" + str(exc)) from None
    session = client_factory()
    try:
        data = dict(LOGIN_FIELDS, authorizationCode=dumps({"authorizationCode": code}))
        if umid:
            data["umidToken"] = umid
        headers = {"Referer": f"https://servicewechat.com/{APP_ID}/838/page-frame.html",
                   "Accept": "application/json,text/plain,*/*", "Accept-Language": "zh-CN,zh;q=0.9",
                   "x-tap": "wx"}
        headers.update(login_headers)
        payload = session.request("POST", LOGIN_URL, data, headers)
    except FlowError as exc:
        raise FlowError("小程序登录阶段：" + str(exc)) from None
    absorb_login_cookie(session, payload)
    validate_login(payload, session)
    mtop(session, CHECK_API, {})
    _warm_guide(session)
    return session.cookie_text()


def cookie_identity(text):
    # 兼容既有的 备注#Cookie；不解码 SID/sgcookie，不按 & 拆 Cookie。
    if "#" in text:
        text = text.split("#", 1)[1]
    values = dict(x.strip().split("=", 1) for x in text.split(";") if "=" in x)
    return values.get("USERID", "")


def multi_cookie_value(text):
    return "\n" in text.strip() or "\r" in text.strip() or bool(
        re.search(r"&\s*(?:[^#=&;]*#)?\s*[A-Za-z0-9_]+=", text))


class QingLong:
    def __init__(self):
        url, cid, secret = remote_config()
        self.url = normalize_url(url)
        if not cid or not secret:
            raise FlowError("远程青龙需要 elm_ql_client_id、elm_ql_client_secret（环境变量权限）")
        self.client = Client()
        p = self.client.request("GET", self.url + "/open/auth/token?" +
                                urlencode({"client_id": cid, "client_secret": secret}))
        self.ok(p)
        self.token = p.get("data", {}).get("token")
        if not self.token:
            raise FlowError("青龙未返回 OpenAPI token")

    @staticmethod
    def ok(payload):
        if payload.get("code") != 200:
            raise FlowError("青龙 OpenAPI 请求失败，请检查应用权限")

    def request(self, method, path, data=None):
        p = self.client.request(method, self.url + path, data,
                                {"Authorization": "Bearer " + self.token}, json_body=True)
        self.ok(p)
        return p

    def sync(self, cookie):
        uid = cookie_identity(cookie)
        name = cookie_env_name()
        envs = self.request("GET", "/open/envs?" + urlencode({"searchValue": name})).get("data")
        if not isinstance(envs, list):
            raise FlowError("青龙变量列表结构异常")
        for item in envs:
            old = str(item.get("value", ""))
            if item.get("name") == name and multi_cookie_value(old):
                raise FlowError("已有目标 Cookie 变量包含多账号，请先在青龙拆成每账号一个变量再同步")
        matches = [x for x in envs if x.get("name") == name and cookie_identity(str(x.get("value", ""))) == uid]
        if len(matches) > 1:
            raise FlowError("该账号有重复青龙变量，请先去重")
        if matches:
            item = matches[0]
            key = "id" if "id" in item else "_id"
            if item.get(key) is None:
                raise FlowError("已有青龙变量缺少 id")
            self.request("PUT", "/open/envs", {key: item[key], "name": name, "value": cookie,
                                               "remarks": item.get("remarks", "")})
        else:
            self.request("POST", "/open/envs", [{"name": name, "value": cookie,
                                                  "remarks": "淘宝闪购 YYB"}])
        # 写入后读回，只比较，不输出凭据；不擅自启用已停用的账号。
        values = self.request("GET", "/open/envs?" + urlencode({"searchValue": name})).get("data", [])
        if not any(x.get("name") == name and x.get("value") == cookie for x in values):
            raise FlowError("青龙写入后读回不一致")


class LocalQingLong(QingLong):
    """与 JDCodeLocal 一样写本地 SQLite；用本地内置 token 刷新任务环境。

    自动使用本地 token 或已有环境变量权限应用，认证信息只发往 loopback。
    """
    def __init__(self):
        configured = os.getenv("QL_DB_PATH", "").strip()
        paths = [Path(configured)] if configured else [Path("/ql/data/db/database.sqlite"), Path("/ql/db/database.sqlite")]
        self.db = next((p for p in paths if p.is_file()), None)
        if self.db is None:
            raise FlowError("未找到本地青龙数据库，请在青龙运行，或设置 QL_DB_PATH")
        self.client = Client()
        try:
            port = int(os.getenv("QlPort", "5700"))
            if not 1 <= port <= 65535:
                raise ValueError
            self.url = f"http://127.0.0.1:{port}"
            token_file = self.db.parent.parent / "config" / "token.json"
        except ValueError:
            raise FlowError("本地青龙 QlPort 配置无效") from None
        with self.connect() as conn:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(Envs)")}
        if not {"id", "name", "value", "remarks", "status", "position", "timestamp",
                "isPinned", "labels", "createdAt", "updatedAt"}.issubset(columns):
            raise FlowError("本地青龙 Envs 数据库结构不兼容")
        try:
            self.token = json.loads(token_file.read_text(encoding="utf-8")).get("value")
            if not isinstance(self.token, str) or not self.token:
                raise FlowError("没有可用本地 token")
            self.request("GET", "/open/envs?" + urlencode({"searchValue": cookie_env_name()}))
            return
        except (OSError, ValueError, FlowError):
            pass
        # 新版青龙的内置 task token 可能无 envs 权限/已过期；复用本地已有应用。
        # 不采用进程中的 QL_*，不修改应用权限，也不把认证信息传到外部地址。
        with self.connect() as conn:
            try:
                apps = conn.execute("SELECT client_id,client_secret,scopes FROM Apps").fetchall()
            except sqlite3.Error:
                apps = []
        for app in apps:
            try:
                if 'envs' not in json.loads(app['scopes'] or '[]'):
                    continue
                p = self.client.request("GET", self.url + "/open/auth/token?" + urlencode(
                    {'client_id':app['client_id'],'client_secret':app['client_secret']}))
                self.ok(p)
                self.token = p.get('data',{}).get('token')
                if not isinstance(self.token,str) or not self.token:
                    continue
                self.request("GET", "/open/envs?" + urlencode({"searchValue":cookie_env_name()}))
                return
            except (ValueError,FlowError):
                continue
        raise FlowError("本地变量刷新认证不可用：请检查青龙已有应用的环境变量权限；未写入数据库")

    @contextmanager
    def connect(self):
        # mode=rw 避免路径错误时创建空数据库。
        conn = sqlite3.connect(self.db.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def sync(self, cookie):
        uid = cookie_identity(cookie)
        if not uid:
            raise FlowError("待写入 Cookie 缺少 USERID")
        now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM Envs WHERE name=?", (cookie_env_name(),)).fetchall()
            if any(multi_cookie_value(str(r['value'] or '')) for r in rows):
                raise FlowError("已有目标 Cookie 变量包含多账号，请先拆成每账号一个变量")
            matches = [r for r in rows if cookie_identity(str(r['value'] or '')) == uid]
            if len(matches) > 1:
                raise FlowError("该账号有重复青龙变量，请先去重")
            if matches:
                row = matches[0]
                identifier, remarks = row['id'], row['remarks'] or ''
                conn.execute("UPDATE Envs SET value=?,updatedAt=? WHERE id=?", (cookie, now, identifier))
            else:
                remarks = "淘宝闪购 YYB"
                position = conn.execute("SELECT COALESCE(MAX(position),0)+1 FROM Envs WHERE name=?", (cookie_env_name(),)).fetchone()[0]
                cursor = conn.execute(
                    "INSERT INTO Envs (name,value,remarks,status,position,timestamp,isPinned,labels,createdAt,updatedAt) "
                    "VALUES (?,?,?,0,?,?,0,'[]',?,?)", (cookie_env_name(),cookie,remarks,position,now,now,now))
                identifier = cursor.lastrowid
            conn.commit()
            saved = conn.execute("SELECT value FROM Envs WHERE id=?", (identifier,)).fetchone()
            if saved is None or saved['value'] != cookie:
                raise FlowError("本地青龙数据库写入后读回不一致")
        # 正常 API update 会让青龙刷新各语言预加载文件，避免只有面板可见、任务读不到。
        self.request("PUT", "/open/envs", {"id":identifier,"name":cookie_env_name(),
                                            "value":cookie,"remarks":remarks})
        values = self.request("GET", "/open/envs?" + urlencode({"searchValue": cookie_env_name()})).get("data", [])
        if not any(x.get('id') == identifier and x.get('value') == cookie for x in values):
            raise FlowError("本地青龙 API 写入读回不一致")


def select_writer():
    cookie_env_name()  # 在建立写入目标前校验配置，避免无效变量名落库。
    # 不使用任务前置脚本可能自动注入的 QL_*，仅显式的专用远程变量触发切换。
    configured = [bool(value) for value in remote_config()]
    if any(configured):
        if not all(configured):
            raise FlowError("远程青龙配置不完整：elm_ql_url、elm_ql_client_id、elm_ql_client_secret 必须同时填写；未写入任何目标")
        return QingLong(), "远程青龙"
    return LocalQingLong(), "本地青龙"


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tbsg-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=os.getenv("elm_cookie_file") or None, help="额外导出 Cookie 文件（可选）")
    args = parser.parse_args(argv)
    try:
        account_settings = configured_value("elm_accounts_json")
        if not account_settings and CONFIG_ELM_ACCOUNTS:
            account_settings = dumps(CONFIG_ELM_ACCOUNTS)
        accounts = load_accounts(configured_value("YYB_SERVER", CONFIG_YYB_SERVER), account_settings)
        ql, mode = select_writer()
    except FlowError as exc:
        print(f"❌ 初始化失败：{exc}")
        return 1
    line = "─" * 46
    total = len(accounts)
    print(line)
    print(f"淘宝闪购 Cookie 同步  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"写入目标：{mode} ｜ 变量名：{cookie_env_name()} ｜ 账号数：{total}")
    print(line)
    cookies, rows = [], []
    for index, account in enumerate(accounts, 1):
        ref = str(account.get("ref", "")) or "-"
        print(f"▶ 账号 {index}/{total}（ref={ref}）")
        try:
            cookie = exchange(account)
            ql.sync(cookie)
            uid = (cookie_identity(cookie) or "")[-4:] or "????"
            print(f"   ✅ 成功：USERID 尾号 {uid}，{mode}写入读回通过")
            cookies.append(cookie)
            rows.append("ok")
        except FlowError as exc:
            msg = str(exc)
            if "未生成身份 Cookie" in msg:
                print(f"   ⚠️ 需人工：{msg}")
                rows.append("human")
            else:
                print(f"   ❌ 失败：{msg}")
                rows.append("fail")
        except Exception:
            print("   ❌ 失败：未预期错误（不输出可能含凭据的异常原文）")
            rows.append("fail")
        if index < total:
            time.sleep(5)
    ok_n = rows.count("ok")
    human_n = rows.count("human")
    fail_n = rows.count("fail")
    print(line)
    print(f"结果汇总：✅ 成功 {ok_n} ｜ ⚠️ 需人工 {human_n} ｜ ❌ 失败 {fail_n}（共 {total}）")
    if cookies and args.output:
        atomic_write(args.output, "\n".join(cookies) + "\n")
        print(f"已保存 {len(cookies)} 个通过校验的 Cookie；结果文件含登录凭据，请勿提交到仓库")
    elif not cookies:
        print("没有通过校验的 Cookie，已有输出文件保持原状")
    print(line)
    return 1 if fail_n else 0


if __name__ == "__main__":
    sys.exit(main())
