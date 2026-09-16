#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
name: 华润通签到
cron: 18 8 * * *

青龙环境变量：
  YYB_SERVER  必填，YYB-Go-Enhanced地址@微信账号标识，多账号每行一条
              例：yyb-go:8000@1
  HRT_TOKEN   可选，仅用于首次迁移旧登录态；多账号每行一条并与 YYB_SERVER 对应

依赖：requests、pycryptodome（仓库 requirements.txt 已声明）
通知：使用青龙内置 notify.py；通知失败不影响签到任务结果。
缓存：/ql/data/config/hrt_tokens.json，失效后会自动通过 YYB-Go-Enhanced 重新登录。
功能：自动登录、查询签到状态、签到领积分，并通知签到前积分、本次增加积分、签到后积分。

作者：lcmovie https://github.com/lcmovie
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import random
import string
import sys
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Hash import SHA1
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad

APP_ID = "wx66c62601b987e69d"
HRT_BASE = "https://mid.huaruntong.cn"
MINI_AUTH = "API_AUTH_MINI"
MINI_SECRET = "addebd90-15e9-4817-a531-1fdd0c7d5230"
MINI_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCKAJ+rCtCbtr4KmkSVnDZq6c38
0R1TFO9KPJiFtC/DvG3ZVi5aeaRb6XcJCeQbmKA4LA4u8ZFNn5xzCu0/tsSwsKFu
/rM/DHtrD3GGaaq3gV27g620dnEiSZrTZ6QV+OOWIELYekl13O/GF7swqrnC2Xak
d3kfPKITQEpRsjCsKwIDAQAB
-----END PUBLIC KEY-----"""
WEB_AUTH = "API_AUTH_WEB"
WEB_SECRET = "c274fc67-19f9-47ba-bb84-585a2e3a1f6a"
WEB_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDuAiqDmvn9Rf15o21qkDxN0rUf
ZsX6rVBrtfgY6tamN2Yn+1D3eHZJuKNlucyqeBr6nmfN2srYAX+oyCXr5vWwFclj
PuWh8aSASqyk7MfbAv5Q4VqYS7lsYUQRdw4plZG0NASDeBvHWi3lsHjGfNb7iUv
grk312EDfBHtRgDvB0QIDAQAB
-----END PUBLIC KEY-----"""
H5_APP_ID = "API_AUTH_H5"
H5_AUTH_SECRET = "1c6120fd-5ad3-4c2d-8cb7-b87a707f416d"
SUCCESS = "S0A00000"
TIMEOUT = 25
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.75(0x18004b21) NetType/WIFI Language/zh_CN"
)
CACHE_FILE = Path(os.getenv("HRT_CACHE_FILE", "/ql/data/config/hrt_tokens.json"))


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def safe_message(value: Any, limit: int = 160) -> str:
    text = str(value or "未知错误").replace("\n", " ").strip()
    return text[:limit]


def nested(data: Any, *names: str) -> Any:
    queue = [data]
    while queue:
        item = queue.pop(0)
        if isinstance(item, dict):
            for name in names:
                if item.get(name) not in (None, ""):
                    return item[name]
            queue.extend(item.values())
        elif isinstance(item, list):
            queue.extend(item)
    return None


def crypto4mid(path: str, payload: Dict[str, Any], auth_id: str, secret: str, public_key: str) -> Dict[str, str]:
    # 小程序 fetch 封装先拼接请求 URL，再仅对 queryData 中的相对 apiPath 编码。
    plain: Dict[str, Any] = {
        "apiPath": urllib.parse.quote(path, safe=""),
        "timestamp": int(time.time() * 1000),
        "appId": auth_id,
        **payload,
    }
    parts = []
    for key in sorted(plain):
        value = plain[key]
        if isinstance(value, (dict, list)):
            value = compact(value)
        elif isinstance(value, bool):
            value = "true" if value else "false"
        parts.append(f"{key}={value}")
    plain["signature"] = hmac.new(secret.encode(), "&".join(parts).encode(), hashlib.md5).hexdigest()
    aes_key = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(16)).encode()
    ciphertext = AES.new(aes_key, AES.MODE_CBC, iv=b"\0" * 16).encrypt(pad(compact(plain).encode(), 16))
    wrapped = PKCS1_OAEP.new(RSA.import_key(public_key), hashAlgo=SHA1).encrypt(aes_key)
    return {
        "key": base64.b64encode(wrapped).decode(),
        "data": base64.b64encode(ciphertext).decode(),
    }


@dataclass
class Account:
    server: str
    ref: str
    index: int

    @property
    def label(self) -> str:
        return f"账号{self.index}"


def parse_accounts() -> List[Account]:
    accounts: List[Account] = []
    for line in os.getenv("YYB_SERVER", "").splitlines():
        line = line.strip()
        if not line or "@" not in line:
            continue
        server, ref = line.rsplit("@", 1)
        server, ref = server.strip().rstrip("/"), ref.strip()
        if not server.startswith(("http://", "https://")):
            server = "http://" + server
        if server and ref:
            accounts.append(Account(server, ref, len(accounts) + 1))
    if not accounts:
        raise RuntimeError("未配置 YYB_SERVER（格式：地址@微信账号标识，多账号换行）")
    # YYB_SERVER 每一条配置都对应一个微信账号，按原顺序全部执行。
    return accounts


def load_cache() -> Dict[str, Any]:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(cache: Dict[str, Any]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = CACHE_FILE.with_suffix(".tmp")
    temp.write_text(compact(cache), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(CACHE_FILE)
    os.chmod(CACHE_FILE, 0o600)


class HRT:
    def __init__(self, account: Account):
        self.account = account
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self.token = ""

    def yyb(self, endpoint: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"ref": self.account.ref, "app_id": APP_ID}
        if extra:
            body.update(extra)
        response = self.session.post(self.account.server + endpoint, json=body, timeout=TIMEOUT)
        response.raise_for_status()
        outer = response.json()
        if int(outer.get("code", -1)) != 0:
            raise RuntimeError(f"YYB {endpoint}：{safe_message(outer.get('msg') or outer.get('message'))}")
        result = outer.get("data", {}).get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                pass
        if not isinstance(result, dict):
            raise RuntimeError(f"YYB {endpoint} 未返回有效对象")
        return result

    def encrypted_post(self, path: str, payload: Dict[str, Any], *, mini: bool = False) -> Dict[str, Any]:
        auth_id, secret, public_key = (
            (MINI_AUTH, MINI_SECRET, MINI_PUBLIC_KEY)
            if mini
            else (WEB_AUTH, WEB_SECRET, WEB_PUBLIC_KEY)
        )
        body = crypto4mid(path, payload, auth_id, secret, public_key)
        headers = {
            "Content-Type": "application/json",
            "x-Hrt-Mid-Appid": auth_id,
            "X-HRT-MID-NEWRISK": "NEWRISK" if mini else "newRisk",
            "Referer": f"https://servicewechat.com/{APP_ID}/160/page-frame.html" if mini else "https://cloud.huaruntong.cn/",
        }
        response = self.session.post(HRT_BASE + path, json=body, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        result = response.json()
        if result.get("code") != SUCCESS:
            raise RuntimeError(f"{path}：{safe_message(result.get('msg') or result.get('code'))}")
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def h5_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        nonce, timestamp = str(uuid.uuid4()), int(time.time() * 1000)
        signature = hashlib.md5("".join(sorted([H5_APP_ID, H5_AUTH_SECRET, str(timestamp), nonce])).encode()).hexdigest()
        body = {
            "auth": {"appid": H5_APP_ID, "nonce": nonce, "timestamp": timestamp, "signature": signature},
            **payload,
        }
        response = self.session.post(
            HRT_BASE + path,
            json=body,
            headers={"Content-Type": "application/json;charset=UTF-8", "Origin": "https://cloud.huaruntong.cn", "Referer": "https://cloud.huaruntong.cn/"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != SUCCESS:
            raise RuntimeError(f"{path}：{safe_message(result.get('msg') or result.get('code'))}")
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def valid_token(self, token: str) -> bool:
        if not token:
            return False
        self.token = token
        try:
            # 业务接口成功才视为有效；checkLogined 对请求上下文字段更敏感。
            self.points()
            return True
        except Exception:
            return False

    def get_user_info(self) -> Dict[str, str]:
        result = self.yyb(
            "/wxapp/operateWxData",
            {"payload": {"api_name": "getUserInfo", "data": {"withCredentials": True}, "env": 1}},
        )
        raw = result.get("rawData") or result.get("raw_data") or result.get("data") or ""
        return {
            "rawData": str(raw),
            "signature": str(nested(result, "signature") or ""),
            "encryptedData": str(nested(result, "encryptedData", "encrytData", "encrypted_data") or ""),
            "iv": str(nested(result, "iv") or ""),
            "cloudID": str(nested(result, "cloudID", "cloudId", "cloud_id") or ""),
        }

    def yyb_login(self) -> str:
        # HAR 中的真实登录是两段式：自动登录检查返回 token 或 randomCode；
        # 返回 randomCode 时，再用微信手机号授权 code 调 miniProgramLogin。
        code_result = self.yyb("/wxapp/getCode")
        code = str(nested(code_result, "code") or "")
        if len(code) < 8:
            raise RuntimeError("YYB getCode 未返回有效微信 code")
        info = self.get_user_info()
        if not all(info.get(key) for key in ("rawData", "signature", "encryptedData", "iv")):
            raise RuntimeError("YYB 用户资料字段不完整")
        payload = {
            "code": code,
            "userInfoEncryptedData": {
                "rawData": info["rawData"],
                "signature": info["signature"],
                "encryptedData": info["encryptedData"],
                "iv": info["iv"],
            },
            # 小程序源码先传 WECHAT，但 fetch 封装在加密前会统一覆盖为 APP。
            "channelId": "APP",
            "businessChannel": "WeChatAPP_Member",
            "deviceChannel": "WECHAT",
            "merchantCode": "1651200000001",
            "shopId": "A606",
            "typeId": "10005",
        }
        data = self.encrypted_post("/api/user/member/login/upgraded/miniProgramAutoLoginCheck", payload, mini=True)
        token = str(data.get("token") or "")
        if token:
            return token
        random_code = str(data.get("randomCode") or "")
        if not random_code:
            raise RuntimeError("自动登录检查既未返回 token，也未返回 randomCode")

        phone = self.yyb("/wxapp/getPhoneNumber")
        phone_code = str(nested(phone, "code") or "")
        if not phone_code:
            raise RuntimeError("YYB getPhoneNumber 未返回有效微信手机号授权 code")
        login_payload = {
            "code": phone_code,
            "randomCode": random_code,
            "channelId": "APP",
            "businessChannel": "WeChatAPP_Member",
            "deviceChannel": "WECHAT",
            "merchantCode": "1999000000001",
            "shopId": "117",
            "typeId": "10005",
        }
        login_data = self.encrypted_post(
            "/api/user/member/login/upgraded/miniProgramLogin", login_payload, mini=True
        )
        token = str(login_data.get("token") or "")
        if token:
            return token
        raise RuntimeError("手机号授权登录成功响应中未返回 token")

    def login(self, cached: str, imported: str) -> str:
        for source, token in (("缓存", cached), ("HRT_TOKEN", imported)):
            if token and self.valid_token(token):
                print(f"  登录：{source}有效")
                return token
        token = self.yyb_login()
        if not self.valid_token(token):
            raise RuntimeError("业务登录校验失败")
        print("  登录：YYB-Go-Enhanced 成功")
        return token

    def points(self) -> int:
        data = self.h5_post(
            "/api/points/querySummary",
            {"channelId": "APP", "sysId": "T0000001", "transactionUuid": str(uuid.uuid4()), "pointsType": "100000", "token": self.token},
        )
        value = nested(data, "availablePoints", "points")
        if value is None:
            raise RuntimeError("积分接口未返回可用积分")
        return int(value)

    def sign_state(self) -> Dict[str, Any]:
        return self.h5_post(
            "/api/points/queryWeekSignin",
            {"token": self.token, "transactionUuid": str(uuid.uuid4())},
        )

    def sign(self) -> int:
        data = self.h5_post(
            "/api/points/saveQuestionSignin",
            {
                "token": self.token,
                "answerResult": 1,
                "channelId": "APP",
                "merchantCode": "1641000001532",
                "storeCode": "qiandaosonjifen",
                "sysId": "T0000001",
                "transactionUuid": str(uuid.uuid4()),
                "inviteCode": "",
            },
        )
        return int(data.get("point") or 0)

    def run(self) -> Dict[str, Any]:
        before = self.points()
        state = self.sign_state()
        already = str(state.get("isTodaySignin") or "").upper() == "S"
        api_added = 0 if already else self.sign()
        if not already:
            for wait in (1, 2, 4):
                time.sleep(wait)
                if str(self.sign_state().get("isTodaySignin") or "").upper() == "S":
                    break
            else:
                raise RuntimeError("签到接口已提交，但复查状态仍未签到")
        after = before
        for wait in (0, 2, 4):
            if wait:
                time.sleep(wait)
            after = self.points()
            if already or after - before >= api_added:
                break
        added = after - before
        if not already and api_added > 0 and added == 0:
            added = api_added
        return {"before": before, "added": added, "after": after, "already": already}


def load_notify():
    candidates = [
        Path("/ql/data/scripts/notify.py"),
        Path("/ql/data/notify.py"),
        Path(__file__).with_name("notify.py"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("hrt_qinglong_notify", path)
            module = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(module)
            for name in ("send", "sendNotify"):
                func = getattr(module, name, None)
                if callable(func):
                    return func
        except Exception as exc:
            print(f"通知模块加载失败：{safe_message(exc)}")
    return None


def notify(text: str) -> None:
    func = load_notify()
    if not func:
        print("未找到青龙 notify.py，跳过通知")
        return
    try:
        func("华润通签到", text)
        print("青龙通知模块调用完成")
    except Exception as exc:
        print(f"青龙通知发送失败（不影响签到结果）：{safe_message(exc)}")


def main() -> int:
    try:
        accounts = parse_accounts()
    except Exception as exc:
        print(f"配置错误：{safe_message(exc)}")
        return 1
    cache = load_cache()
    imported = [x.strip() for x in os.getenv("HRT_TOKEN", "").splitlines() if x.strip()]
    messages: List[str] = []
    failures = 0
    for account in accounts:
        print(f"\n===== {account.label} =====")
        client = HRT(account)
        try:
            cached_entry = cache.get(account.ref) or cache.get(f"__account_{account.index}__") or {}
            token = client.login(str(cached_entry.get("token") or ""), imported[account.index - 1] if account.index <= len(imported) else "")
            client.token = token
            cache[account.ref] = {"token": token, "updated_at": int(time.time())}
            save_cache(cache)
            result = client.run()
            status = "今日已签到" if result["already"] else "签到成功"
            line = (
                f"{account.label}：{status}\n"
                f"签到前积分：{result['before']}\n"
                f"本次增加积分：{result['added']}\n"
                f"签到后积分：{result['after']}"
            )
            print(line)
            messages.append(line)
        except Exception as exc:
            failures += 1
            line = f"{account.label}：失败\n原因：{safe_message(exc)}"
            print(line)
            messages.append(line)
    content = "\n\n".join(messages)
    notify(content)
    print("\n===== 汇总 =====\n" + content)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
