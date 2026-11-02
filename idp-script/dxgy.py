# -*- coding: utf-8 -*-
# cron: 0 58 9,13 * * *
# name: 电信光耀网龄
"""
电信光耀网龄 v2026.11.02.1（2026.11.1-30）：签到、10/14点领取实物资格、通知。
活动网址：https://apps.telefen.com/nstars/iage?promoid=63db914eb803c94c&channel=SWX
环境变量：
必填 TELEFEN_AUTH：备注#手机号#服务密码#clientType#androidId
获取地址：https://dx.lcmovie.qzz.io/
依赖：requests、pycryptodome、certifi。通知复用青龙 notify.py。
默认真实签到；仅09:58~10:00、13:58~14:00进入定点抢券。
首签100积分商城优惠券；7日签到奖励按网龄分为生活好物3选1/音视频月卡7选1资格券。
11月状态独立保存，只复用10月认证缓存；签到奖励不占随心领抢购停抢状态。
脚本不兑换、不支付、不提交地址。
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import hmac
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import statistics
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
ACTIVITY = "iage2026"
SIGN_ID = "iage202611"
CYCLE = "2026-11"
SECKILL_ID = "202388"
MERCHANT_PROMO = "e4aaf9573aa5dff9"
ACTIVITY_PROMO = "63db914eb803c94c"
COUPONS = ("NCA5DD942278280DB75549C099B", "NCA5C4E4DE1A6D7E82A4934DA3A", "NCA56644B08AE431441DB8C7FA0")
OTHER_COUPONS = ("NCA10D547CEAB703F06B4AB4FD8", "NCA19B04468B945F9A7D31710C1", "NCA11B443AA891C97DC6771CE1D")
SIGN_COUPONS = ("NCA54C842A98F57DE9EA7A9879B", "NCA5AF240289A684C18D0CB9F99")
ALL_COUPONS = COUPONS + OTHER_COUPONS
YZ_PROVINCES = set("02,27,08,29,12,14,18,17,28,06,16,20,13,07,11,23,31,04,21,19,10,30,26,09,15,22,24".split(","))
START_DAY, END_DAY = "2026-11-01", "2026-11-30"
PATTERN = re.compile(r"(?P<remark>[^#\r\n]+)#(?P<phone>1[3-9]\d{9})#(?P<password>[^#\r\n]+)#(?P<client_type>#[^#\r\n]+#[^#\r\n]+#[^#\r\n]+#)#(?P<encoded_id>[^#\r\n]+)")
RECORD_PATTERN = re.compile(PATTERN.pattern.replace(r"(?P<encoded_id>[^#\r\n]+)", r"(?P<encoded_id>[2-9:;c-h]{16})"))
DES_KEY = b"1234567`90koiuyhgtfrdews"


class TaskError(Exception):
    pass


class AuthenticationError(TaskError):
    pass


class BusinessError(TaskError):
    def __init__(self, code, message=""):
        self.code, self.message = str(code), str(message)
        super().__init__("业务接口未成功")


@dataclass(frozen=True)
class Account:
    remark: str = field(repr=False)
    phone: str = field(repr=False)
    password: str = field(repr=False)
    client_type: str = field(repr=False)
    encoded_id: str = field(repr=False)

    @property
    def label(self):
        value = self.remark.replace(self.phone, "账号").replace(self.password, "[隐藏]")
        return re.sub(r"[\r\n\x00-\x1f]", "", value)[:32] or "账户"


def parse_accounts(text):
    result, phones = [], set()
    for number, line in enumerate(str(text or "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        position = 0
        while position < len(line):
            match = RECORD_PATTERN.match(line, position)
            if not match:
                raise TaskError(f"第{number}行格式错误；支持换行及青龙同名变量&合并，请保留clientType中的双#，androidId需复制网站编码值")
            values = match.groupdict()
            value = values["encoded_id"]
            raw = "".join(chr(ord(c) - 2) for c in value)
            if not re.fullmatch(r"[0-9a-f]{16}", raw) or "".join(chr(ord(c) + 2) for c in raw) != value:
                raise TaskError(f"第{number}行androidId不是网站当前导出的编码值")
            if values["phone"] in phones:
                raise TaskError(f"第{number}行手机号重复；同一号码只配置一次")
            phones.add(values["phone"])
            result.append(Account(**values))
            position = match.end()
            while position < len(line) and line[position].isspace():
                position += 1
            if position == len(line):
                break
            if line[position] != "&":
                raise TaskError(f"第{number}行账号末尾存在非分隔内容；请完整复制导出信息")
            position += 1
            while position < len(line) and line[position].isspace():
                position += 1
            if position == len(line):
                raise TaskError(f"第{number}行末尾有空账号分隔符&")
    if not result:
        raise TaskError("未配置TELEFEN_AUTH，请每行粘贴一个网站完整导出信息")
    return result


def masked_match(observed, expected):
    value = str(observed or "")
    return bool(len(value) == 11 and value.count("*") <= 4 and all(a == "*" or a == b for a, b in zip(value, expected)))


def encode(value):
    return "".join(chr(ord(c) + 2) for c in str(value))


def des(value, decrypt=False):
    try:
        from Crypto.Cipher import DES3
        from Crypto.Util.Padding import pad, unpad
        cipher = DES3.new(DES_KEY, DES3.MODE_CBC, b"\0" * 8)
        return unpad(cipher.decrypt(bytes.fromhex(value)), 8).decode("utf-8") if decrypt else cipher.encrypt(pad(value.encode("utf-8"), 8)).hex()
    except ImportError:
        try:
            from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
        except ImportError:
            from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
        from cryptography.hazmat.primitives.ciphers import Cipher, modes
        from cryptography.hazmat.primitives import padding
        cipher = Cipher(TripleDES(DES_KEY), modes.CBC(b"\0" * 8))
        if decrypt:
            worker = cipher.decryptor()
            padded = worker.update(bytes.fromhex(value)) + worker.finalize()
            p = padding.PKCS7(64).unpadder()
            return (p.update(padded) + p.finalize()).decode("utf-8")
        p = padding.PKCS7(64).padder()
        padded = p.update(value.encode("utf-8")) + p.finalize()
        worker = cipher.encryptor()
        return (worker.update(padded) + worker.finalize()).hex()


def number(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def coupon_for_age(age):
    if age is None or age < 0:
        raise TaskError("账户网龄数据缺失")
    tier = 2 if age >= 10 else 1 if age >= 5 else 0
    return COUPONS[tier], ("3选1", "6选1", "9选1")[tier]


def scheduled_target(now):
    for hour in (10, 14):
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if target - timedelta(minutes=2) <= now < target:
            return target
    return None


class Clock:
    def __init__(self):
        self.offsets, self.lock = [], threading.Lock()

    def now(self):
        with self.lock:
            offset = statistics.median(self.offsets) if self.offsets else 0
        return datetime.now(CST) + timedelta(seconds=offset)

    def observe(self, response, start, end):
        try:
            server = parsedate_to_datetime(response.headers["Date"]).timestamp() + 0.5
            offset = server - (start + end) / 2
            if end - start <= 3 and abs(offset) <= 30:
                with self.lock:
                    self.offsets.append(offset)
                    self.offsets[:] = self.offsets[-15:]
        except (KeyError, TypeError, ValueError, OverflowError):
            pass

    def wait_until(self, target):
        while True:
            remain = (target - self.now()).total_seconds()
            if remain <= 0:
                return
            time.sleep(min(remain, 0.2))


class Logger:
    def __init__(self, accounts=()):
        self.lock, self.lines = threading.Lock(), []
        self.private = [v for a in accounts for v in (a.phone, a.password, a.encoded_id) if v]

    def clean(self, value):
        text = str(value)
        for secret in self.private:
            text = text.replace(secret, "[隐藏]")
        text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号]", text)
        text = re.sub(r"(?<!\d)\d{12,}(?!\d)", "[标识隐藏]", text)
        return re.sub(r"[A-Za-z0-9+/=]{40,}", "[凭据隐藏]", text)[:600]

    def log(self, value):
        text = self.clean(value)
        with self.lock:
            self.lines.append(text)
            print(datetime.now(CST).strftime("[%H:%M:%S] ") + text, flush=True)


def atomic_json(path, data):
    temporary = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        with open(temporary, "x", encoding="utf-8") as handle:
            if os.name != "nt":
                os.chmod(temporary, 0o600)
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self.root, 0o700)
        salt = self.root / ".salt"
        try:
            fd = os.open(salt, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
        self.salt = salt.read_bytes()
        if len(self.salt) != 32:
            raise TaskError("状态目录密钥异常；请保留原文件排查")

    def key(self, account):
        return hmac.new(self.salt, account.phone.encode(), hashlib.sha256).hexdigest()

    def fingerprint(self, account):
        value = "\0".join((account.phone, account.password, account.client_type, account.encoded_id))
        return hmac.new(self.salt, value.encode(), hashlib.sha256).hexdigest()

    def path(self, account, kind):
        return self.root / (self.key(account) + "." + kind + ".json")

    def read(self, account, kind):
        path = self.path(account, kind)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, OSError):
            raise TaskError("账户状态文件损坏；未覆盖原文件，已暂停该账户") from None

    def save(self, account, kind, data):
        atomic_json(self.path(account, kind), data)


class AccountLease:
    def __init__(self, store, account):
        self.path = store.root / (store.key(account) + ".lock")
        self.acquired = False

    def acquire(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                old = json.loads(self.path.read_text(encoding="utf-8"))
                age = time.time() - float(old.get("time", time.time()))
                pid = number(old.get("pid"))
                dead = False
                if pid and os.name != "nt":
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        dead = True
                if age > 900 or dead:
                    self.path.unlink()
                    return self.acquire()
            except (OSError, ValueError, TypeError):
                pass
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "time": time.time()}, handle)
        self.acquired = True
        return True

    def release(self):
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self.acquired = False


class Client:
    def __init__(self, account, store, clock, logger, deadline=None):
        self.account, self.store, self.clock, self.logger = account, store, clock, logger
        self.deadline, self.session = deadline, requests.Session()
        self.channel, self.info = "HGOKHD", None
        self.cache = store.read(account, "auth")
        # Reuse authentication only. October's completed/claimed state stays untouched.
        legacy_root = store.root.parent / ".telefen_iage_202610"
        if not self.cache and store.root.name == ".telefen_iage_202611" and (legacy_root / ".salt").is_file():
            legacy = Store(legacy_root)
            cached = legacy.read(account, "auth")
            if cached.get("fingerprint") == legacy.fingerprint(account):
                self.cache = dict(cached, fingerprint=store.fingerprint(account))
                store.save(account, "auth", self.cache)
        if self.cache.get("fingerprint") != store.fingerprint(account):
            self.cache = {}
        model, version = account.client_type.split("#")[3], account.client_type.split("#")[1]
        rnd = lambda n: "".join(secrets.choice("0123456789abcdef") for _ in range(n))
        b64 = lambda text: base64.b64encode(text.encode()).decode()
        self.ua = self.cache.get("user_agent") or f"CtClient;{version};Android;13;{model};{b64(rnd(12))}!#!{b64(rnd(8))}"
        self.session.headers.update({"User-Agent": self.ua, "Accept": "application/json", "Referer": BASE + "/nstars/iage"})

    def ensure_time(self):
        if self.deadline and self.clock.now() >= self.deadline:
            raise TaskError("准备超时，已跳过本场抢券；其它就绪账户不受影响")

    def request(self, method, url, **kwargs):
        self.ensure_time()
        if self.deadline:
            remaining = (self.deadline - self.clock.now()).total_seconds()
            kwargs.setdefault("timeout", (min(5, max(0.5, remaining)), min(20, max(0.5, remaining))))
        else:
            kwargs.setdefault("timeout", (5, 20))
        start = time.time()
        response = self.session.request(method, url, allow_redirects=False, **kwargs)
        self.clock.observe(response, start, time.time())
        return response

    def call(self, method, path, params=None, payload=None):
        if not path.startswith("/nstars/") or "?" in path:
            raise TaskError("业务路径异常")
        self.session.headers["appCode"] = self.channel
        try:
            response = self.request(method, BASE + path, params=params, json=payload)
            if response.status_code != 200:
                raise TaskError(f"业务接口HTTP {response.status_code}")
            data = response.json()
        except requests.RequestException:
            raise TaskError("业务请求连接失败/超时；结果可能未知") from None
        except ValueError:
            raise TaskError("业务响应不是可识别JSON") from None
        if not isinstance(data, dict):
            raise TaskError("业务响应结构异常")
        code = str(data.get("errCode", ""))
        if code != "0000":
            safe = code if re.fullmatch(r"[A-Za-z0-9_-]{1,16}", code) else "未知"
            raise BusinessError(safe, self.logger.clean(data.get("errMsg", "")))
        return data.get("data")

    def validate(self):
        data = self.call("GET", "/nstars/api/account/userinfo", params={"noload": "true"})
        if not isinstance(data, dict) or not masked_match((data.get("userInfo") or {}).get("loginName"), self.account.phone):
            raise AuthenticationError("活动会话失效或号码不匹配；不会执行该账户任务")
        self.info = data
        return data

    def authenticate(self):
        cookie = self.cache.get("cookie")
        if cookie:
            self.channel = self.cache.get("channel", "HGOKHD")
            self.session.cookies.set("newmallsession", cookie, domain="apps.telefen.com", path="/", secure=True)
            try:
                self.validate()
                self.logger.log(f"[{self.account.label}] 活动Cookie缓存有效")
                return
            except (TaskError, requests.RequestException):
                self.session.cookies.clear()
        cached_login = self.cache.get("app_login")
        if isinstance(cached_login, dict) and cached_login.get("token") and cached_login.get("userId"):
            try:
                self.exchange(cached_login)
                self.logger.log(f"[{self.account.label}] APP缓存换取活动Cookie成功")
                return
            except (TaskError, requests.RequestException, ValueError, ET.ParseError):
                self.session.cookies.clear()
        self.ensure_time()
        # Exactly one password login attempt per account/run; no captcha solver/SMS calls.
        with requests.Session() as login_session:
            response = login_session.post(LOGIN_URL, json={"phone": self.account.phone, "password": self.account.password,
                "remark": self.account.remark, "clientType": self.account.client_type,
                "androidId": self.account.encoded_id, "androidVersion": "13", "userAgent": self.ua}, timeout=(5, 35), allow_redirects=False)
        if response.status_code != 200:
            raise AuthenticationError(f"登录站HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            raise AuthenticationError("登录站响应无效") from None
        if not isinstance(data, dict) or data.get("success") is not True:
            if isinstance(data, dict) and data.get("needVerifyCode"):
                raise AuthenticationError("登录需要人工验证码；请在网站用同一设备参数完成验证后重试")
            code = str(data.get("resultCode", "")) if isinstance(data, dict) else "未知"
            code = code if re.fullmatch(r"[A-Za-z0-9_-]{1,16}", code) else "未知"
            raise AuthenticationError("登录未成功，返回码" + code)
        if not isinstance(data.get("token"), str) or not data["token"] or not data.get("userId"):
            raise AuthenticationError("登录成功标志缺少票据所需字段")
        self.exchange({"token": data["token"], "userId": str(data["userId"])})
        self.logger.log(f"[{self.account.label}] 新登录参数换取活动Cookie成功")

    def ticket_xml(self, login):
        doc = ET.Element("Request")
        header = ET.SubElement(doc, "HeaderInfos")
        fields = {"Code": "getSingle", "Timestamp": self.clock.now().strftime("%Y%m%d%H%M%S"),
            "BroadAccount": "", "BroadToken": "", "ClientType": self.account.client_type,
            "ShopId": "20002", "Source": "110003", "SourcePassword": "Sid98s",
            "Token": login["token"], "UserLoginName": encode(self.account.phone)}
        for key, value in fields.items():
            ET.SubElement(header, key).text = str(value)
        content = ET.SubElement(doc, "Content")
        ET.SubElement(content, "Attach").text = "test"
        field_data = ET.SubElement(content, "FieldData")
        ET.SubElement(field_data, "TargetId").text = des(str(login["userId"]))
        ET.SubElement(field_data, "Url").text = des(BASE + "/home/tparse?ticket=$ticket$&promoid=" + MERCHANT_PROMO + "&shareid=")
        return ET.tostring(doc, encoding="utf-8")

    def exchange(self, login):
        response = self.request("POST", TICKET_URL, data=self.ticket_xml(login), headers={"Content-Type": "application/xml;charset=UTF-8"})
        if response.status_code != 200:
            raise AuthenticationError(f"取票HTTP {response.status_code}")
        xml = ET.fromstring(response.content)
        node = next((n for n in xml.iter() if n.tag.rsplit("}", 1)[-1].lower() == "ticket" and n.text), None)
        if node is None:
            raise AuthenticationError("取票未返回Ticket，未进入活动任务")
        ticket = des(node.text.strip(), decrypt=True)
        self.session.cookies.clear()
        url = BASE + "/home/tparse?" + urlencode({"ticket": ticket, "promoid": MERCHANT_PROMO, "shareid": ""})
        for _ in range(4):
            uri = urlsplit(url)
            if uri.scheme != "https" or uri.hostname != "apps.telefen.com":
                raise AuthenticationError("商城跳转域名异常")
            response = self.request("GET", url)
            if response.status_code not in (301, 302, 303, 307, 308):
                break
            location = response.headers.get("Location")
            if not location:
                break
            url = urljoin(url, location)
            self.channel = parse_qs(urlsplit(url).query).get("channel", ["HGOKHD"])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", self.channel):
            raise AuthenticationError("商城渠道格式异常")
        cookie = next((c.value for c in self.session.cookies if c.name == "newmallsession" and c.domain.lstrip(".") == "apps.telefen.com"), "")
        if not cookie:
            raise AuthenticationError("商城未下发活动Cookie")
        self.validate()
        self.cache = {"fingerprint": self.store.fingerprint(self.account), "cookie": cookie,
                      "channel": self.channel, "user_agent": self.ua, "app_login": login,
                      "updated": self.clock.now().isoformat()}
        self.store.save(self.account, "auth", self.cache)

    def close(self):
        self.session.close()


@dataclass
class Context:
    account: Account
    client: Client
    store: Store
    lease: AccountLease
    logger: Logger
    clock: Clock
    state: dict
    query_only: bool = False
    coupon: str = ""
    tier: str = ""
    summary: str = "进度未知"
    ready: bool = False

    def save(self):
        self.store.save(self.account, "state", self.state)

    def log(self, text):
        self.logger.log(f"[{self.account.label}] {text}")

    def close(self):
        self.client.close()
        self.lease.release()


def sign_reward_status(ctx):
    age = number((ctx.client.info.get("prodInfo") or {}).get("ageYear"), 0)
    coupon = SIGN_COUPONS[int(age >= 15)]
    reward = "音视频会员月卡7选1" if age >= 15 else "生活好物3选1"
    android_tip = "请手动使用安卓手机登录中国电信APP，进入该账号的光耀网龄活动页，查看并领取/兑换签到奖励"
    try:
        rows = ctx.client.call("GET", "/nstars/api/coupon/usedcoupon", params={"couponIds": coupon, "noload": "true"})
        row = next((r for r in rows if isinstance(r, dict) and r.get("couponId") == coupon), None) if isinstance(rows, list) else None
        if row is None:
            raise TaskError("签到奖励券查询缺项")
        received = number(row.get("userReceivedCount"), 0) > 0 or number(row.get("userUnusedCount"), 0) > 0
        ctx.state["sign_reward_confirmed"] = received
        ctx.save()
        if received:
            return f"已确认{reward}资格券；{android_tip}，兑换需支付1积分，有效期以券面为准"
        return f"{reward}资格券尚未确认到账；签到完成不代表获奖，名额有限；{android_tip}，实际到账以我的优惠券/订单为准"
    except (TaskError, requests.RequestException):
        return f"{reward}资格券查询未完成；{android_tip}，以我的优惠券/订单实际到账为准"


def sign_progress(ctx):
    client, state = ctx.client, ctx.state
    data = client.call("POST", "/nstars/api/active/getSignIn", payload={"appId": SIGN_ID})
    if not isinstance(data, dict) or number(data.get("totalCount")) is None or number(data.get("canSignIn")) not in (0, 1):
        raise TaskError("签到查询字段异常，未提交签到")
    count, today = number(data["totalCount"]), number(data["canSignIn"])
    day = ctx.clock.now().strftime("%Y-%m-%d")
    state.update(sign_count=count, sign_today=bool(today), sign_observed_at=ctx.clock.now().isoformat())
    if count >= 7:
        state["sign_pending_day"] = ""
        state["sign_complete"] = True
        ctx.save()
        ctx.summary = f"签到{count}/7，已完成7日；" + sign_reward_status(ctx)
        ctx.log(ctx.summary)
        return
    if today:
        state["sign_pending_day"] = ""
        ctx.summary = f"签到{count}/7，今天已签"
        ctx.save()
        ctx.log(ctx.summary)
        return
    age = number((client.info.get("prodInfo") or {}).get("ageYear"))
    star = number((client.info.get("starInfo") or {}).get("starLevel"))
    if age is None or star is None or age < 1 or not 1 <= star <= 7:
        ctx.summary = f"签到{count}/7，未满足签到网龄/星级条件"
        ctx.save()
        ctx.log(ctx.summary)
        return
    if ctx.query_only:
        ctx.summary = f"签到{count}/7，今天未签（仅查询，不提交）"
        ctx.save()
        ctx.log(ctx.summary)
        return
    if state.get("sign_pending_day") == day:
        ctx.summary = f"签到{count}/7，上次今日签到结果待核验，不重复提交"
        ctx.save()
        ctx.log(ctx.summary)
        return
    province = str((client.info.get("userInfo") or {}).get("provinceID") or "")
    if not province:
        ctx.summary = f"签到{count}/7，省份信息缺失，跳过签到提交"
        ctx.log(ctx.summary)
        return
    if province in YZ_PROVINCES:
        membership = client.call("POST", "/nstars/activenew/api/fromyzactive/yzOrderIsBuy", payload={"noload": True})
        if number(membership) != 2:
            ctx.summary = f"签到{count}/7，需要本人完成云智体验会员前置；脚本不代开通"
            ctx.log(ctx.summary)
            return
    state["sign_pending_day"] = day
    ctx.save()
    try:
        submitted = client.call("POST", "/nstars/api/active/signInN", payload={"activeIdWeb": SIGN_ID, "commoditys": SIGN_ID, "appCode": client.channel})
        if isinstance(submitted, dict) and submitted.get("outOrderId"):
            state["sign_reward_order_seen"] = True
            state["sign_reward_order_day"] = number(submitted.get("totalCount"))
        checked = client.call("POST", "/nstars/api/active/getSignIn", payload={"appId": SIGN_ID})
        if not isinstance(checked, dict) or number(checked.get("canSignIn")) != 1 or number(checked.get("totalCount")) is None:
            raise TaskError("签到返回后尚未核实今日状态，保留待核验标记")
        state.update(sign_count=number(checked["totalCount"]), sign_today=True, sign_pending_day="")
        ctx.save()
        if state["sign_count"] >= 7:
            state["sign_complete"] = True
            ctx.save()
            ctx.summary = f"签到{state['sign_count']}/7，7日全部完成；" + sign_reward_status(ctx)
        else:
            ctx.summary = f"签到成功，累计{state['sign_count']}/7"
            if state["sign_count"] == 1:
                has_order = isinstance(submitted, dict) and bool(submitted.get("outOrderId"))
                ctx.summary += "；首签100积分商城优惠券已返回订单，请查我的优惠券" if has_order else "；首签优惠券未返回奖励订单，可能名额已满，请查我的优惠券"
        ctx.log(ctx.summary)
    except BusinessError as error:
        state["sign_pending_day"] = ""
        ctx.save()
        ctx.summary = f"签到{count}/7，签到未成功：{error.code} {error.message}"
        if count == 0 and (error.code == "0010" or "火爆" in error.message):
            ctx.summary += "；请先手动使用安卓手机登录中国电信APP，进入该账号的光耀网龄活动页，再运行脚本签到"
        ctx.log(ctx.summary)
    except (TaskError, requests.RequestException):
        ctx.summary = f"签到{count}/7，提交结果待核验；本日不重复签到"
        ctx.log(ctx.summary)


def qualification_snapshot(ctx):
    rows = ctx.client.call("GET", "/nstars/api/coupon/usedcoupon", params={"couponIds": ",".join(ALL_COUPONS), "noload": "true"})
    records = ctx.client.call("GET", "/nstars/api/active/getRecord", params={"activityId": ACTIVITY, "seckillId": SECKILL_ID})
    if not isinstance(rows, list) or records is not None and not isinstance(records, list):
        raise TaskError("资格查询结构异常，不猜测可领取状态")
    available = {str(row.get("couponId")): row for row in rows if isinstance(row, dict)}
    if any(cid not in available for cid in ALL_COUPONS):
        raise TaskError("本周期权益券查询缺项，暂停该账户抢券")
    claimed = any(number(available.get(cid, {}).get("userReceivedCount"), 0) > 0 or number(available.get(cid, {}).get("userUnusedCount"), 0) > 0 for cid in COUPONS)
    used = any(number(available.get(cid, {}).get("userReceivedCount"), 0) > 0 for cid in OTHER_COUPONS)
    for row in records or []:
        if not isinstance(row, dict):
            continue
        commodity = str(row.get("commodityId") or "")
        claimed = claimed or commodity in COUPONS
        used = used or commodity in OTHER_COUPONS or commodity == "265732"
    # Washer is another monthly mutually exclusive selection, not the physical tier qualification check.
    participation = ctx.client.call("GET", "/nstars/api/seckill/queryUserSeckillParticipate", params={"seckillId": SECKILL_ID, "noload": "true"})
    if not isinstance(participation, dict) or number(participation.get("buyedNum")) is None:
        raise TaskError("本周期参与记录缺失，暂停该账户抢券")
    if number(participation.get("buyedNum"), 0) > 0:
        used = True
    return {"claimed": claimed, "cycle_used": used, "target": available[ctx.coupon]}


def mark_claimed(ctx, snapshot=None):
    ctx.state.update(rush_status="claimed", rush_pending=False, claimed_at=ctx.clock.now().isoformat(), coupon=ctx.coupon, tier=ctx.tier)
    if snapshot:
        expiry = snapshot.get("target", {}).get("userAssetEndTime")
        if expiry:
            ctx.state["coupon_expiry"] = str(expiry)
    ctx.save()  # Persist BEFORE notification; notification failure never re-enables buying.
    ctx.log(f"已确认获得{ctx.tier}实物资格券；本周期永久停抢。请本人去活动兑换入口/我的优惠券，支付1积分选择实物并填写地址；脚本不代兑换。")


def prepare_rush(ctx):
    if ctx.state.get("rush_status") == "claimed":
        ctx.coupon, ctx.tier = ctx.state.get("coupon", ""), ctx.state.get("tier", "实物")
        ctx.log(f"本周期已获{ctx.tier}资格，持续停抢；签到独立处理")
        return False
    if ctx.state.get("rush_status") == "cycle_used":
        ctx.log("本周期已领取其他互斥权益，持续停抢")
        return False
    age = number((ctx.client.info.get("prodInfo") or {}).get("ageYear"))
    star = number((ctx.client.info.get("starInfo") or {}).get("starLevel"))
    ctx.coupon, ctx.tier = coupon_for_age(age)
    if star is None or not 1 <= star <= 7:
        ctx.log("不满足权益星级条件，本场不抢")
        return False
    snapshot = qualification_snapshot(ctx)
    if snapshot["claimed"]:
        mark_claimed(ctx, snapshot)
        return False
    if snapshot["cycle_used"]:
        ctx.state.update(rush_status="cycle_used", rush_pending=False)
        ctx.save()
        ctx.log("服务端记录本周期其他权益已领取，本周期不再抢实物资格")
        return False
    light = ctx.client.call("GET", "/nstars/api/active/litUpAgeN")
    if not isinstance(light, dict) or number(light.get("receiveCount"), 0) < 1:
        ctx.log("本月随心领资格/次数尚未就绪，请本人到活动页核对，本场不抢")
        return False
    limits = ctx.client.call("POST", "/nstars/api/active/limitcoupon", payload={"appCode": ctx.client.channel,
        "promoId": ACTIVITY_PROMO, "noload": True, "couponIds": ",".join(ALL_COUPONS)})
    limit = next((r for r in limits if isinstance(r, dict) and str(r.get("spId")) == ctx.coupon), None) if isinstance(limits, list) else None
    if limit is None or number(limit.get("status")) is None:
        raise TaskError("11月资格券库存查询缺项，暂停该账户抢券")
    if number(limit["status"]) != 0:
        ctx.log("当前资格券库存不足；定点前不据此停抢，等待10/14点补量后提交")
    if ctx.state.get("rush_pending"):
        ctx.log("上次领取结果待核验，资产尚未确认；不重复抢，请本人核对后再解除待核验状态")
        return False
    if ctx.query_only:
        ctx.log(f"{ctx.tier}资格未领取（仅查询）")
        return False
    ctx.log(f"准备{ctx.tier}资格券；不会选择/支付具体实物")
    return True


def rush(ctx, gate, target, cancelled=None):
    gate.wait()
    if cancelled is not None and cancelled.is_set():
        ctx.log("本场放行前任务中断，未提交领取")
        return
    ctx.client.deadline = None
    slot = target.strftime("%Y-%m-%d %H:%M")
    if ctx.state.get("rush_status") in ("claimed", "cycle_used") or ctx.state.get("rush_pending"):
        return
    if ctx.state.get("last_attempt_slot") == slot:
        ctx.log("本场已尝试，重复任务不再次提交")
        return
    ctx.state["last_attempt_slot"] = slot
    ctx.save()
    expires = target + timedelta(seconds=15)
    for attempt in range(3):
        if ctx.clock.now() > expires:
            break
        ctx.state["rush_pending"] = True
        ctx.save()
        ctx.log(f"{slot} 第{attempt+1}次领取{ctx.tier}资格")
        try:
            ctx.client.call("POST", "/nstars/api/active/createN", payload={"seckillId": SECKILL_ID,
                "commoditys": ctx.coupon, "activeIdWeb": ACTIVITY, "appCode": ctx.client.channel})
        except BusinessError as error:
            ctx.state["rush_pending"] = False
            ctx.save()
            ctx.log(f"领取未成功：{error.code} {error.message}")
            if error.code == "1020" or any(w in error.message for w in ("抢光", "库存不足", "已领完")):
                ctx.log("本场库存已结束；下一场仍会检查，不永久停抢")
                return
            if any(w in error.message for w in ("已领取", "领取过", "已参与", "已经购买")):
                try:
                    snap = qualification_snapshot(ctx)
                    if snap["claimed"]:
                        mark_claimed(ctx, snap)
                    else:
                        ctx.state.update(rush_status="cycle_used", rush_pending=False)
                        ctx.save()
                        ctx.log("平台已限制本周期参与，本周期暂停，请核对权益记录")
                except TaskError:
                    ctx.state["rush_pending"] = True
                    ctx.save()
                return
            if any(w in error.message for w in ("未开始", "火爆", "繁忙", "稍后")):
                time.sleep(0.5)
                continue
            return
        except (TaskError, requests.RequestException):
            ctx.log("领取请求结果未知，先对账，不重复提交")
        for delay in (0.2, 0.8, 1.5):
            time.sleep(delay)
            try:
                snap = qualification_snapshot(ctx)
                if snap["claimed"]:
                    mark_claimed(ctx, snap)
                    return
                if snap["cycle_used"]:
                    ctx.state.update(rush_status="cycle_used", rush_pending=False)
                    ctx.save()
                    return
            except (TaskError, requests.RequestException):
                break
        ctx.log("券资产暂未确认，已保留待核验标记并停发；请到我的优惠券/权益记录核对，避免重复领取")
        return


def prepare(account, store, clock, logger, deadline, query_only):
    lease = AccountLease(store, account)
    if not lease.acquire():
        logger.log(f"[{account.label}] 同一号码已有任务运行，本次跳过")
        return None
    client = None
    try:
        state = store.read(account, "state")
        if state.get("cycle") not in (None, CYCLE):
            raise TaskError("状态属于其他活动周期，不自动清零或覆盖")
        state["cycle"] = CYCLE
        client = Client(account, store, clock, logger, deadline)
        ctx = Context(account, client, store, lease, logger, clock, state, query_only)
        client.authenticate()
        sign_progress(ctx)
        ctx.ready = prepare_rush(ctx)
        return ctx
    except Exception as error:
        message = str(error) if isinstance(error, TaskError) else "请求/协议异常（" + type(error).__name__ + "），未继续该账户任务"
        logger.log(f"[{account.label}] {message}")
        if client:
            client.close()
        lease.release()
        return None


def notify(logger):
    message = "\n".join(logger.lines)
    try:
        try:
            module = importlib.import_module("notify")
        except ImportError:
            module = None
            for path in (Path(__file__).resolve().parent / "notify.py", Path("/ql/data/scripts/notify.py"), Path("/ql/scripts/notify.py")):
                if path.is_file():
                    spec = importlib.util.spec_from_file_location("telefen_ql_notify", path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    break
            if module is None:
                raise ImportError("notify module absent")
        module.send("电信光耀网龄活动", message)
        logger.log("已调用青龙通知模块，送达以配置的推送渠道为准")
        return True
    except ImportError:
        logger.log("未找到青龙notify.py，结果已完整打印；上传脚本后需配置青龙通知")
    except Exception:
        logger.log("青龙通知发送失败；已领/停抢状态仍保留，不因通知失败重复抢券")
    return False


def main(argv=None, auth_text=None, state_dir=None, clock=None):
    ap = argparse.ArgumentParser(description="11月光耀网龄：签到、定时抢资格券；不代兑换")
    ap.add_argument("--query-only", action="store_true", help="只认证/查询，不签到、不领取")
    ap.add_argument("--no-notify", action="store_true", help="不调用青龙通知，仅打印")
    ap.add_argument("--clear-pending", metavar="备注", help="本人核对未领取后解除指定备注的未知领取锁；本次只查询")
    args = ap.parse_args(argv)
    clock = clock or Clock()
    logger = Logger()
    if not START_DAY <= clock.now().strftime("%Y-%m-%d") <= END_DAY:
        logger.log("不在2026年11月1日至30日活动期，未登录、未签到、未领券")
        return 0
    try:
        accounts = parse_accounts(auth_text if auth_text is not None else os.environ.get("TELEFEN_AUTH", ""))
        logger = Logger(accounts)
        root = state_dir or os.environ.get("TELEFEN_STATE_DIR") or str(Path(__file__).resolve().parent / ".telefen_iage_202611")
        store = Store(root)
        if args.clear_pending:
            selected = [a for a in accounts if a.remark == args.clear_pending]
            if len(selected) != 1:
                raise TaskError("解除锁备注未唯一匹配，不修改状态")
            lease = AccountLease(store, selected[0])
            if not lease.acquire():
                raise TaskError("该号码正在运行，未修改待核验状态")
            try:
                state = store.read(selected[0], "state")
                state["rush_pending"] = False
                store.save(selected[0], "state", state)
            finally:
                lease.release()
            args.query_only = True
            logger.log("已按本人核对指令解除未知结果锁；本次只查询")
        target = None if args.query_only else scheduled_target(clock.now())
        deadline = target - timedelta(seconds=3) if target else None
        logger.log(f"共{len(accounts)}个账户；" + (f"准备{target.strftime('%H:%M:%S')}并发领取，已领号码不入池" if target else "当前非抢券准备窗口，只处理签到/状态查询；不提前或延后抢券"))
        pool = ThreadPoolExecutor(max_workers=len(accounts), thread_name_prefix="telefen_prepare")
        futures = {pool.submit(prepare, a, store, clock, logger, deadline, args.query_only): a for a in accounts}
        contexts, ready = [], []
        failed_accounts = 0
        try:
            timeout = max(0, (deadline - clock.now()).total_seconds()) if deadline else None
            done, pending = wait(futures, timeout=timeout)
            for future in done:
                ctx = future.result()
                if ctx:
                    contexts.append(ctx)
                    if ctx.ready and target and (not deadline or clock.now() <= target):
                        ready.append(ctx)
                else:
                    failed_accounts += 1
            for future in pending:
                logger.log(f"[{futures[future].label}] 未在本场截止前准备完成，剔除本场，不拖延其它账户")
            if ready:
                gate = threading.Event()
                cancelled = threading.Event()
                with ThreadPoolExecutor(max_workers=len(ready), thread_name_prefix="telefen_rush") as workers:
                    runs = [workers.submit(rush, ctx, gate, target, cancelled) for ctx in ready]
                    logger.log(f"{len(ready)}个待抢账户已就绪，等待统一放行")
                    try:
                        clock.wait_until(target)
                        gate.set()
                        for future in runs:
                            try:
                                future.result()
                            except Exception as error:
                                logger.log("抢券处理异常（" + type(error).__name__ + "）；保留账户状态等待核验")
                    finally:
                        if not gate.is_set():
                            cancelled.set()
                            gate.set()
            elif target:
                logger.log("没有待抢账户，未等待或发送领取请求")
            # Slow preparation cannot hold the release barrier, but its final progress is collected.
            for future in pending:
                ctx = future.result()
                if ctx:
                    contexts.append(ctx)
                    ctx.log("准备超过本场截止，本场未参与领取")
                else:
                    failed_accounts += 1
        finally:
            pool.shutdown(wait=True)
            for ctx in contexts:
                ctx.close()
        logger.log("——账户汇总——")
        for ctx in contexts:
            status = ctx.state.get("rush_status", "未领")
            tail = "已领实物资格，本周期停抢；请本人兑换" if status == "claimed" else "本周期已用权益资格" if status == "cycle_used" else "领取结果待核验，暂停重抢" if ctx.state.get("rush_pending") else "实物资格未领"
            logger.log(f"[{ctx.account.label}] {ctx.summary}；{tail}")
    except Exception as error:
        logger.log(str(error) if isinstance(error, TaskError) else "脚本异常（" + type(error).__name__ + "），未继续业务")
        if not args.no_notify:
            notify(logger)
        return 1
    if not args.no_notify:
        notify(logger)
    return 1 if failed_accounts else 0


if __name__ == "__main__":
    raise SystemExit(main())
