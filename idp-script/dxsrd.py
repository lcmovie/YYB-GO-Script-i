#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name: 电信星享会员日
# cron: 20 9 * * *
"""
电信星享会员日 v2026.11.17.3
活动页：https://apps.telefen.com/mallactive/starday
活动期：2026-11-17 ~ 2026-11-23

功能：
1、完成 4 项跳转任务：浏览星享会员日活动 / 浏览网龄回馈活动 / 登录云智手机网页端 / 浏览积分好物商品；
2、完成当日全部开星盒（抽奖）次数，中奖后自动领取（实物奖品需本人填写地址，脚本不代填）；
3、仅在本次有奖品时调用青龙通知模块推送，未中奖完全不推送；
4、翻卡折扣兑（seckill 秒杀）按要求不操作，脚本不产生任何秒杀、下单、兑换、支付请求；
5、不开通云智手机会员业务（仅当账号本身已开通时，按活动接口补登记该任务，不产生费用）。

环境变量：
必填 TELEFEN_AUTH：备注#手机号#服务密码#clientType#androidId
获取地址：https://dx.lcmovie.qzz.io/

依赖：requests、pycryptodome、certifi。通知复用青龙 notify.py。

"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
import xml.etree.ElementTree as ET

import requests

CST = timezone(timedelta(hours=8))
BASE = "https://apps.telefen.com"
LOGIN_URL = "https://fnostelecomlogin.iepose.cn/api/step1_login"
TICKET_URL = "https://appgologin.189.cn:9031/map/clientXML"
DES_KEY = b"1234567`90koiuyhgtfrdews"

HOME_PROMO = "e4aaf9573aa5dff9"          # 商城首页 promoid，用于换取 newmallsession
STAR_PROMO = "6bba5426bce3a557"          # 星享会员日活动页 promoid
SWX_PROMO = "79adb300942e51fd"           # 微信渠道活动页 promoid
DEFAULT_CHANNEL = "HGOKHD"
CHANNEL_IDS = {"SWX": 37, "HGOKHD": 21}
DEFAULT_CHANNEL_ID = 21

GAME_APP_LOW = "JGSUDOKU-EEHaPbbr"       # 1-4 星抽奖池
GAME_APP_HIGH = "JGSUDOKU-4ewImwd2"      # 6-7 星抽奖池
GAME_MCHID = "0"

MAX_DRAWS = 20
DRAW_GAP = 1.2
QUERY_TRIES = 3
QUERY_GAP = 2.0

TASKS = (
    ("VIEW_PAGE_STARDAY", "浏览星享会员日"),
    ("VIEW_PAGE_IAGE", "浏览网龄回馈"),
    ("YUNZHI_LOGIN", "登录云智网页"),
    ("VIEW_PAGE_HAOWU", "浏览积分好物"),
)
TASK_NAMES = dict(TASKS)
SKIP_TASKS = {"YUNZHI_OPEN"}             # 云智会员开通：仅对已开通账号补登记，不做业务办理

RECORD_PATTERN = re.compile(
    r"(?P<remark>[^#\r\n]+)#(?P<phone>1[3-9]\d{9})#(?P<password>[^#\r\n]+)#"
    r"(?P<client_type>#[^#\r\n]+#[^#\r\n]+#[^#\r\n]+#)#"
    r"(?P<encoded_id>[2-9:;c-h]{16})"
)
UA_TEMPLATE = "CtClient;{ver};Android;13;{model};{tag}!#!{suffix}"
REWARD_KEYS = ("productName", "rewardName", "couponName", "prizeName", "goodsName", "name", "title")


class TaskError(Exception):
    """统一异常，stage 定位环节，code 只输出短标识。"""

    def __init__(self, stage: str, code: str):
        self.stage = stage
        self.code = str(code)[:48] if re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fa5]{1,48}", str(code)) else "UNKNOWN"
        super().__init__("%s失败 [%s]" % (stage, self.code))


class BusinessError(TaskError):
    def __init__(self, code: str, message: str = ""):
        self.code, self.message = str(code), str(message)
        super().__init__("业务接口", code)


# ------------------------------------------------------------------ 账号
@dataclass(frozen=True)
class Account:
    remark: str = field(repr=False)
    phone: str = field(repr=False)
    password: str = field(repr=False)
    client_type: str = field(repr=False)
    encoded_id: str = field(repr=False)
    sso_cookie: str = field(default="", repr=False)

    @property
    def masked(self) -> str:
        return self.phone[:3] + "****" + self.phone[-4:]

    @property
    def label(self) -> str:
        name = re.sub(r"[\r\n\x00-\x1f]", "", self.remark or "")[:24]
        name = name.replace(self.phone, "账号").replace(self.password, "***")
        return name or self.masked


def parse_accounts(text: str) -> list[Account]:
    """兼容青龙同名变量合并（&）与多行写法，逐段严格校验。"""
    result, phones = [], set()
    for lineno, line in enumerate(str(text or "").replace("\r", "").split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        pos = 0
        while pos < len(line):
            match = RECORD_PATTERN.match(line, pos)
            if not match:
                raise TaskError("配置", "LINE_%d_FORMAT" % lineno)
            values = match.groupdict()
            raw = "".join(chr(ord(c) - 2) for c in values["encoded_id"])
            if not re.fullmatch(r"[0-9a-f]{16}", raw) or "".join(chr(ord(c) + 2) for c in raw) != values["encoded_id"]:
                raise TaskError("配置", "LINE_%d_ANDROID_ID" % lineno)
            if values["phone"] in phones:
                raise TaskError("配置", "LINE_%d_DUPLICATE" % lineno)
            phones.add(values["phone"])
            result.append(Account(**values))
            pos = match.end()
            while pos < len(line) and line[pos].isspace():
                pos += 1
            if pos >= len(line):
                break
            if line[pos] != "&":
                raise TaskError("配置", "LINE_%d_TRAILING" % lineno)
            pos += 1
            while pos < len(line) and line[pos].isspace():
                pos += 1
    if not result:
        raise TaskError("配置", "TELEFEN_AUTH_MISSING")
    return result


def read_env(name: str) -> str:
    """青龙命令行手工运行时 env 不在容器环境里，兜底从数据库取同名变量。"""
    value = os.getenv(name, "")
    if str(value).strip():
        return value
    for db in ("/ql/data/db/database.sqlite", "/ql/data/db/database.sqlite3"):
        if not os.path.isfile(db):
            continue
        try:
            import sqlite3
            conn = sqlite3.connect(db)
            rows = [v for (v,) in conn.execute(
                "select value from Envs where name=? and status=0 order by id", (name,))]
            conn.close()
        except Exception:
            continue
        if rows:
            return "\n".join(rows)
    return ""


def parse_sso(text: str) -> dict:
    """TELEFEN_SSO: 每行 备注#newmallsession；按备注/手机号末 4 位绑定账号。"""
    result = {}
    for line in str(text or "").replace("\r", "").split("\n"):
        line = line.strip()
        if not line or "#" not in line:
            continue
        remark, _, value = line.partition("#")
        remark, value = remark.strip(), value.strip()
        if remark and value:
            result[remark[-4:]] = value
    return result


def bind_sso(accounts: list[Account], sso: dict) -> list[Account]:
    if not sso:
        return accounts
    bound = []
    for account in accounts:
        cookie = sso.get(account.remark[-4:]) or sso.get(account.phone[-4:]) or ""
        bound.append(Account(account.remark, account.phone, account.password,
                             account.client_type, account.encoded_id, cookie))
    return bound


# ------------------------------------------------------------------ 加密
def encode(value: str) -> str:
    """电信登录名混淆：每字符 +2。"""
    return "".join(chr(ord(c) + 2) for c in str(value))


def des(value: str, decrypt: bool = False) -> str:
    """3DES/CBC/零 IV，与官方 App 一致；解密返明文，加密返 hex。"""
    from Crypto.Cipher import DES3
    from Crypto.Util.Padding import pad, unpad
    cipher = DES3.new(DES_KEY, DES3.MODE_CBC, b"\0" * 8)
    if decrypt:
        return unpad(cipher.decrypt(bytes.fromhex(value)), 8).decode("utf-8")
    return cipher.encrypt(pad(value.encode("utf-8"), 8)).hex()


def build_user_agent(account: Account) -> str:
    parts = account.client_type.split("#")
    ver = parts[1] if len(parts) > 1 and parts[1] else "13.5.0"
    model = parts[3] if len(parts) > 3 and parts[3] else "iPhone 13 Pro Max"
    tag = base64.b64encode("".join(secrets.choice("0123456789abcdef") for _ in range(12)).encode()).decode()
    suffix = base64.b64encode("".join(secrets.choice("0123456789abcdef") for _ in range(8)).encode()).decode()
    return UA_TEMPLATE.format(ver=ver, model=model, tag=tag, suffix=suffix)


def today_active() -> str:
    forced = os.getenv("XXHY_ACTIVE_CODE", "").strip()
    if re.fullmatch(r"\d{6,12}", forced):
        return forced
    return datetime.now(CST).strftime("%Y%m%d")


# ------------------------------------------------------------------ 存储 / 日志
def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


class Store:
    """按号码缓存 newmallsession 与 App 票据，减少登录桥调用次数。"""

    def __init__(self, root: str):
        self.root = Path(root)

    def load(self) -> dict:
        try:
            data = json.loads((self.root / "auth.json").read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def get(self, account: Account) -> dict:
        entry = self.load().get(account.phone)
        return entry if isinstance(entry, dict) else {}

    def put(self, account: Account, payload: dict):
        data = self.load()
        data[account.phone] = payload
        atomic_json(self.root / "auth.json", data)


class Logger:
    def __init__(self):
        self.lines: list[str] = []
        self.lock = threading.Lock()

    def clean(self, value) -> str:
        text = str(value or "")
        text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "手机号", text)
        return re.sub(r"[A-Za-z0-9_+/=]{40,}", "[长标识]", text)

    def __call__(self, message: str, account: Account | None = None):
        text = str(message)
        prefix = ""
        if account is not None:
            text = text.replace(account.phone, account.masked).replace(account.password, "***")
            prefix = "[" + account.label + "] "
        line = "[%s] %s%s" % (datetime.now(CST).strftime("%m-%d %H:%M:%S"), prefix, self.clean(text))
        with self.lock:
            print(line, flush=True)
            self.lines.append(line)


# ------------------------------------------------------------------ 业务客户端
class Client:
    def __init__(self, account: Account, store: Store, logger: Logger):
        self.account = account
        self.store = store
        self.logger = logger
        self.ua = build_user_agent(account)
        self.channel = DEFAULT_CHANNEL
        self.session = requests.Session()
        self.active = today_active()
        self.rewards: list[str] = []
        self.draws: int = 0
        self.commodity: dict = {}
        self.home_ok = False

    # -------------------------------------------------- 请求
    def _headers(self) -> dict:
        return {"appCode": self.channel, "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8", "Origin": BASE,
                "Referer": BASE + "/mallactive/starday?promoid=" + STAR_PROMO + "&channel=" + self.channel}

    def request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", (5, 20))
        kwargs.setdefault("allow_redirects", False)
        return self.session.request(method, url, **kwargs)

    def business(self, method: str, path: str, params=None, payload=None) -> dict:
        """返回原始响应体（含 errCode），由调用方决定 0000/0099/0001 的处理方式。"""
        try:
            response = self.session.request(method, BASE + path, params=params, json=payload,
                                            headers=self._headers(), timeout=(5, 20),
                                            allow_redirects=False)
        except requests.RequestException:
            raise TaskError("业务请求", "NETWORK") from None
        if response.status_code != 200:
            raise TaskError("业务请求", "HTTP_%d" % response.status_code)
        try:
            data = response.json()
        except ValueError:
            raise TaskError("业务响应", "INVALID_JSON") from None
        if not isinstance(data, dict):
            raise TaskError("业务响应", "STRUCTURE")
        return data

    def strict(self, method: str, path: str, params=None, payload=None):
        """errCode 非 0000 直接抛 BusinessError，返回 data。"""
        body = self.business(method, path, params=params, payload=payload)
        code = str(body.get("errCode"))
        if code != "0000":
            raise BusinessError(code if re.fullmatch(r"[A-Za-z0-9_-]{1,16}", code) else "未知",
                                self.logger.clean(body.get("errMsg", "")))
        return body.get("data")

    def warm(self):
        """先访问活动页，mallactive 子系统才会把会话识别为已登录（实测必需）。"""
        try:
            self.request("GET", BASE + "/mallactive/starday",
                         params={"channel": self.channel, "promoid": SWX_PROMO if self.channel == "SWX" else STAR_PROMO})
        except requests.RequestException:
            pass

    # -------------------------------------------------- 认证
    def _password_login(self) -> dict:
        payload = {"phone": self.account.phone, "password": self.account.password,
                   "remark": self.account.remark, "clientType": self.account.client_type,
                   "androidId": self.account.encoded_id, "androidVersion": "13", "userAgent": self.ua}
        try:
            resp = requests.post(LOGIN_URL, json=payload, timeout=(5, 35), allow_redirects=False,
                                 headers={"User-Agent": self.ua})
        except requests.RequestException:
            raise TaskError("登录", "NETWORK") from None
        if resp.status_code != 200:
            raise TaskError("登录", "HTTP_%d" % resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            raise TaskError("登录", "INVALID_JSON") from None
        if data.get("success") is not True:
            if data.get("needVerifyCode"):
                raise TaskError("登录", "MANUAL_VERIFICATION")
            raise TaskError("登录", data.get("resultCode") or "FAILED")
        if not data.get("token") or not data.get("userId"):
            raise TaskError("登录", "MISSING_TOKEN")
        return {"token": data["token"], "userId": str(data["userId"])}

    def _ticket_xml(self, login: dict) -> bytes:
        doc = ET.Element("Request")
        header = ET.SubElement(doc, "HeaderInfos")
        fields = {
            "Code": "getSingle",
            "Timestamp": datetime.now(CST).strftime("%Y%m%d%H%M%S"),
            "BroadAccount": "", "BroadToken": "",
            "ClientType": self.account.client_type,
            "ShopId": "20002", "Source": "110003", "SourcePassword": "Sid98s",
            "Token": login["token"], "UserLoginName": encode(self.account.phone),
        }
        for key, value in fields.items():
            ET.SubElement(header, key).text = str(value)
        content = ET.SubElement(doc, "Content")
        ET.SubElement(content, "Attach").text = "test"
        field_data = ET.SubElement(content, "FieldData")
        ET.SubElement(field_data, "TargetId").text = des(str(login["userId"]))
        ET.SubElement(field_data, "Url").text = des(
            BASE + "/home/tparse?ticket=$ticket$&promoid=" + HOME_PROMO + "&shareid=")
        return ET.tostring(doc, encoding="utf-8")

    def _exchange(self, login: dict) -> str:
        """App 票据换一次性 Ticket，再走 tparse 换商城 newmallsession。"""
        try:
            resp = requests.post(TICKET_URL, data=self._ticket_xml(login),
                                 headers={"Content-Type": "application/xml;charset=UTF-8",
                                          "User-Agent": self.ua},
                                 timeout=(5, 35), allow_redirects=False)
        except requests.RequestException:
            raise TaskError("取票", "NETWORK") from None
        if resp.status_code != 200:
            raise TaskError("取票", "HTTP_%d" % resp.status_code)
        try:
            xml = ET.fromstring(resp.content)
        except ET.ParseError:
            raise TaskError("取票", "INVALID_XML") from None
        node = next((n for n in xml.iter() if n.tag.rsplit("}", 1)[-1].lower() == "ticket" and n.text), None)
        if node is None:
            raise TaskError("取票", "NO_TICKET")
        ticket = des(node.text.strip(), decrypt=True)

        session = requests.Session()
        session.headers.update({"User-Agent": self.ua})
        url = BASE + "/home/tparse?" + urlencode({"ticket": ticket, "promoid": HOME_PROMO, "shareid": ""})
        channel = DEFAULT_CHANNEL
        for _ in range(5):
            uri = urlsplit(url)
            if uri.scheme != "https" or uri.hostname != "apps.telefen.com":
                raise TaskError("商城跳转", "DOMAIN")
            hop = session.get(url, timeout=(5, 20), allow_redirects=False)
            if hop.status_code not in (301, 302, 303, 307, 308):
                break
            location = hop.headers.get("Location")
            if not location:
                break
            url = urljoin(url, location)
            channel = parse_qs(urlsplit(url).query).get("channel", [channel])[0]
        cookie = next((c.value for c in session.cookies
                       if c.name == "newmallsession" and c.domain.lstrip(".") == "apps.telefen.com"), "")
        session.close()
        if not cookie:
            raise TaskError("商城会话", "NO_SESSION")
        if not re.fullmatch(r"[A-Za-z0-9+/=_-]{8,128}", channel):
            channel = DEFAULT_CHANNEL
        self.channel = channel
        self.session.cookies.set("newmallsession", cookie, domain="apps.telefen.com", path="/", secure=True)
        return cookie

    def _probe(self) -> bool:
        """用 gameInfo 探活商城会话，并建立奖品名映射。"""
        try:
            body = self.business("GET", "/mallactive/api/game/gameInfo",
                                 params={"noload": "true", "appId": GAME_APP_LOW, "mchId": GAME_MCHID,
                                         "channel": self.channel})
        except TaskError:
            return False
        if str(body.get("errCode")) != "0000":
            return False
        data = body.get("data") or {}
        for item in ((data.get("gameData") or {}).get("commodityList") or []):
            if isinstance(item, dict) and item.get("rewardId") is not None:
                self.commodity[str(item["rewardId"])] = str(item.get("productName") or "")
        return True

    def _use_cookie(self, cookie: str, channel: str) -> bool:
        self.channel = channel if channel in CHANNEL_IDS else DEFAULT_CHANNEL
        self.session.cookies.set("newmallsession", cookie, domain="apps.telefen.com", path="/", secure=True)
        self.warm()
        return self._probe()

    def home(self):
        """活动首页：只认 H5/微信 SSO 会话，商城会话会被判定未登录。"""
        try:
            body = self.business("GET", "/mallactive/api/v917/activity/home",
                                 params={"noload": "true", "activeCode": self.active})
        except TaskError:
            return None
        if str(body.get("errCode")) != "0000" or not isinstance(body.get("data"), dict):
            return None
        data = body["data"]
        code = str(data.get("activeCode") or "").strip()
        if re.fullmatch(r"\d{6,12}", code):
            self.active = code
        self.home_ok = True
        return data

    def authenticate(self):
        cached = self.store.get(self.account)
        # 1) TELEFEN_SSO（H5 会话，可读活动首页）
        if self.account.sso_cookie:
            if self._use_cookie(self.account.sso_cookie, DEFAULT_CHANNEL) and self.home() is not None:
                self.logger("活动会话（TELEFEN_SSO）有效", self.account)
                self.store.put(self.account, {"cookie": self.account.sso_cookie, "channel": self.channel,
                                              "app_login": cached.get("app_login"),
                                              "updated": datetime.now(CST).isoformat()})
                return
            self.session.cookies.clear()
            self.logger("TELEFEN_SSO 已失效，改用 TELEFEN_AUTH 登录链", self.account)
        # 2) 本地缓存会话
        cookie = str(cached.get("cookie") or "")
        if cookie and cookie != self.account.sso_cookie:
            if self._use_cookie(cookie, str(cached.get("channel") or DEFAULT_CHANNEL)):
                self.logger("商城会话缓存有效", self.account)
                self.home()
                return
            self.session.cookies.clear()
        # 3) 缓存的 App 票据换会话
        login = cached.get("app_login") if isinstance(cached.get("app_login"), dict) else None
        if login and login.get("token") and login.get("userId"):
            try:
                cookie = self._exchange(login)
                if self._probe():
                    self.home()
                    self.store.put(self.account, {"cookie": cookie, "channel": self.channel,
                                                  "app_login": login, "updated": datetime.now(CST).isoformat()})
                    self.logger("App 票据换取商城会话成功", self.account)
                    return
            except (TaskError, ET.ParseError):
                pass
            self.session.cookies.clear()
        # 4) 密码登录
        login = self._password_login()
        cookie = self._exchange(login)
        if not self._probe():
            raise TaskError("会话校验", "NOT_LOGIN")
        self.home()
        self.store.put(self.account, {"cookie": cookie, "channel": self.channel,
                                      "app_login": login, "updated": datetime.now(CST).isoformat()})
        self.logger("新登录参数换取商城会话成功", self.account)

    # -------------------------------------------------- 任务
    def task_list(self) -> list[tuple[str, str]]:
        home = self.home()
        if home is not None:
            items = []
            for task in (home.get("taskList") or []):
                if not isinstance(task, dict):
                    continue
                task_type = str(task.get("taskType") or "")
                if task_type in SKIP_TASKS or task_type not in TASK_NAMES:
                    continue
                if int(task.get("isFinished") or 0) == 1:
                    continue
                items.append((task_type, TASK_NAMES[task_type]))
            self.logger("活动首页可用：%s 编码 %s，待办 %d 项"
                        % (home.get("title") or "星享会员日", self.active, len(items)), self.account)
            return items
        return list(TASKS)

    def run_tasks(self) -> tuple[int, int]:
        items = self.task_list()
        if self.home_ok and not items:
            self.logger("4 项跳转任务今日均已完成", self.account)
            return 0, 0
        done, failed = 0, 0
        for task_type, name in items:
            body = None
            for attempt in range(2):
                try:
                    body = self.business("POST", "/mallactive/api/v917/complete",
                                         payload={"activityId": self.active, "taskType": task_type,
                                                  "channelId": CHANNEL_IDS.get(self.channel, DEFAULT_CHANNEL_ID)})
                    break
                except TaskError as error:
                    if attempt == 1:
                        self.logger("%s：%s" % (name, error), self.account)
                    body = None
            if body is None:
                failed += 1
                continue
            code = str(body.get("errCode"))
            if code != "0000":
                self.logger("%s：%s %s" % (name, code, self.logger.clean(body.get("errMsg"))), self.account)
                failed += 1
                continue
            data = body.get("data") or {}
            done += 1
            self.logger("%s：完成 %s/%s" % (name, data.get("completedTimes", "-"), data.get("maxTimes", "-")),
                        self.account)
            time.sleep(0.6)
        return done, failed

    # -------------------------------------------------- 开星盒
    def free_count(self, app_id: str) -> int:
        try:
            data = self.strict("GET", "/mallactive/api/game/freeCount",
                               params={"appId": app_id, "mchId": GAME_MCHID, "channel": self.channel})
        except (BusinessError, TaskError):
            return -1
        try:
            return int(data or 0)
        except (TypeError, ValueError):
            return -1

    def pick_pool(self) -> tuple[str, int]:
        low = self.free_count(GAME_APP_LOW)
        if low > 0:
            return GAME_APP_LOW, low
        high = self.free_count(GAME_APP_HIGH)
        if high > 0:
            self.logger("1-4 星池无次数，改用 6-7 星池", self.account)
            return GAME_APP_HIGH, high
        return GAME_APP_LOW, max(low, 0)

    def reward_text(self, data) -> str:
        if isinstance(data, dict):
            for key in REWARD_KEYS:
                value = data.get(key)
                if value:
                    return re.sub(r"\s+", " ", str(value))[:48]
            reward_id = data.get("rewardId")
            if reward_id is not None and self.commodity.get(str(reward_id)):
                return self.commodity[str(reward_id)][:48]
        text = json.dumps(data, ensure_ascii=False) if data is not None else ""
        return re.sub(r"\s+", " ", text)[:120] or "未知奖品"

    def draw_all(self) -> str:
        """完成任务后服务端次数有延迟，先轮询确认；0001 连续两次视为次数已用尽。"""
        app_id, count = "", 0
        for _ in range(QUERY_TRIES):
            time.sleep(QUERY_GAP)
            app_id, count = self.pick_pool()
            if count > 0:
                break
        if count <= 0:
            self.logger("开星盒当日可用次数为 0", self.account)
            return ""
        busy = 0
        for _ in range(MAX_DRAWS):
            try:
                body = self.business("GET", "/mallactive/api/game/lottery",
                                     params={"appId": app_id, "mchId": GAME_MCHID,
                                             "channel": self.channel, "jgg": True})
            except TaskError as error:
                self.logger("抽奖请求%s，本账号停止抽奖" % error, self.account)
                break
            code = str(body.get("errCode"))
            if code == "0000":
                busy = 0
                self.draws += 1
                prize = self.reward_text(body.get("data"))
                self.rewards.append(prize)
                self.logger("第 %d 次开星盒：中奖 %s" % (self.draws, prize), self.account)
            elif code == "0099":
                busy = 0
                self.draws += 1
                self.logger("第 %d 次开星盒：未中奖" % self.draws, self.account)
            elif code == "0001":
                busy += 1
                if busy >= 2:
                    break
            else:
                self.logger("抽奖返回 %s %s，本账号停止抽奖"
                            % (code, self.logger.clean(body.get("errMsg"))), self.account)
                break
            time.sleep(DRAW_GAP)
            if code in ("0000", "0099") and self.free_count(app_id) <= 0:
                break
        return app_id

    def receive_awards(self, app_id: str):
        """中奖后领取；实物奖品需本人填地址，脚本不代填。"""
        if not app_id or not self.rewards:
            return
        try:
            records = self.strict("GET", "/mallactive/api/game/getRecord",
                                  params={"appId": app_id, "mchId": GAME_MCHID,
                                          "channel": self.channel, "numMonths": 1})
        except (BusinessError, TaskError) as error:
            self.logger("中奖记录查询失败：%s" % error, self.account)
            return
        if not isinstance(records, list) or not records:
            self.logger("暂无待领取记录", self.account)
            return
        for item in records:
            if not isinstance(item, dict):
                continue
            name = self.reward_text(item)
            token = item.get("acceptToken")
            if not token:
                continue
            try:
                kind = int(item.get("commodityType") or 0)
            except (TypeError, ValueError):
                kind = 0
            if kind == 1:
                self.logger("%s 为实物奖品，需本人填写地址，未代填" % name, self.account)
                continue
            try:
                self.strict("POST", "/mallactive/api/game/receive",
                            payload={"appId": app_id, "channel": self.channel, "token": token})
                self.logger("%s 已领取" % name, self.account)
            except (BusinessError, TaskError) as error:
                self.logger("%s 领取失败：%s" % (name, error), self.account)
            time.sleep(0.5)

    def close(self):
        self.session.close()


# ------------------------------------------------------------------ 通知
def notify(title: str, message: str) -> bool:
    try:
        try:
            module = importlib.import_module("notify")
        except ImportError:
            module = None
            for path in (Path(__file__).resolve().parent / "notify.py", Path("/ql/data/scripts/notify.py"),
                         Path("/ql/scripts/notify.py"), Path("/ql/data/notify.py")):
                if path.is_file():
                    spec = importlib.util.spec_from_file_location("telefen_ql_notify", path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    break
            if module is None:
                raise ImportError("notify module absent")
        module.send(title, message)
        return True
    except ImportError:
        print("[提示] 未找到青龙 notify.py，中奖结果仅打印在日志中", flush=True)
    except Exception:
        print("[提示] 青龙通知发送失败，中奖结果仅打印在日志中", flush=True)
    return False


# ------------------------------------------------------------------ 主流程
def run_account(account: Account, store: Store, logger: Logger, dry_run: bool) -> Client | None:
    client = None
    try:
        client = Client(account, store, logger)
        client.authenticate()
        if dry_run:
            logger("会话校验通过（dry-run 不执行任务与抽奖）", account)
            return client
        done, failed = client.run_tasks()
        app_id = client.draw_all()
        if client.rewards:
            client.receive_awards(app_id)
        logger("活动编码 %s，任务完成 %d 项、失败 %d 项，开星盒 %d 次" % (client.active, done, failed, client.draws),
               account)
        return client
    except TaskError as error:
        logger(str(error), account)
    except requests.RequestException:
        logger("网络异常，未继续该账户任务", account)
    except Exception as error:
        logger("脚本异常（%s），未继续该账户任务" % type(error).__name__, account)
    if client:
        client.close()
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="电信星享会员日：4 项跳转任务 + 每日开星盒，中奖才通知")
    parser.add_argument("--auth", default=None, help="账号串，默认读 TELEFEN_AUTH")
    parser.add_argument("--cookie", default=None, help="单独调试用 newmallsession")
    parser.add_argument("--no-notify", action="store_true", help="不调用青龙通知，仅打印")
    parser.add_argument("--dry-run", action="store_true", help="只做登录与会话校验，不做任务和抽奖")
    args = parser.parse_args(argv)

    logger = Logger()
    store = Store(os.getenv("TELEFEN_STATE_DIR") or str(Path(__file__).resolve().parent / ".telefen_starday"))
    try:
        accounts = parse_accounts(args.auth if args.auth is not None else read_env("TELEFEN_AUTH"))
    except TaskError as error:
        logger(str(error))
        return 1
    accounts = bind_sso(accounts, parse_sso(read_env("TELEFEN_SSO")))
    if args.cookie:
        accounts = [Account("调试", accounts[0].phone if accounts else "调试",
                            accounts[0].password if accounts else "",
                            accounts[0].client_type if accounts else "",
                            accounts[0].encoded_id if accounts else "",
                            args.cookie)]

    logger("活动编码 %s；共 %d 个账号；只做 4 项跳转任务与开星盒，翻卡折扣兑不操作"
           % (today_active(), len(accounts)))
    results: list[tuple[Account, Client]] = []
    for account in accounts:
        client = run_account(account, store, logger, args.dry_run)
        if client is not None:
            results.append((account, client))

    logger("——汇总——成功 %d，失败 %d" % (len(results), len(accounts) - len(results)))
    total_draws, winners = 0, []
    for account, client in results:
        total_draws += client.draws
        tail = "；奖品：" + "、".join(client.rewards) if client.rewards else ""
        logger("%s 开星盒 %d 次%s" % (account.label, client.draws, tail))
        if client.rewards:
            winners.append((account, client))
        client.close()

    if args.no_notify:
        return 0 if results else 1
    if winners:
        lines = ["活动：电信星享会员日",
                 "开星盒 %d 次，%d 个账号中奖" % (total_draws, len(winners))]
        for account, client in winners:
            lines.append("%s：%s" % (account.masked, "、".join(client.rewards)))
        if notify("电信星享会员日", "\n".join(lines)):
            logger("中奖通知已推送")
    else:
        logger("本次无奖品，未发送通知")
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
