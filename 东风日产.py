# cron: 42 9,15 * * *
#!/usr/bin/env python3
# name: 东风日产
"""
东风日产 人车生活 小程序签到脚本（code版）

第一次要 手动签到 一次
环境变量：
  WX_ID          账号配置，格式：wxid#备注，多账号换行 / & 分隔
  WECHAT_SERVER  微信协议服务地址，默认 http://127.0.0.1:8011
  NISSAN_SKIP_COMMUNITY =1 跳过社区任务，只做签到+查询
"""

import base64
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests
from getCode import get_single_code, get_single_phone_data


# ============ 常量配置 ============
DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"
WECHAT_MINI_APPID = "wxe3fd49854884240e"          # 东风日产 人车生活 小程序 appid
ARIYA_BASE = "https://ariya-api.dongfeng-nissan.com.cn"
WXAPI_BASE = "https://wxapi.dongfeng-nissan.com.cn"
COMMUNITY_BASE = "https://community.dongfeng-nissan.com.cn"
PAGE_VERSION = "1285"
NOTIFY_TITLE = "东风日产签到"

# ariya-api 固定请求头字段
CLIENT_ID = "nissanminiapp"
APP_CODE = "nissan"
APP_SKIN = "NISSANAPP"

# 调试日志开关：True 输出 [gw调试][mid调试][签到调试] 等详细信息
# 青龙面板可通过环境变量 NISSAN_DEBUG=1 覆盖
DEBUG = os.environ.get("NISSAN_DEBUG", "").strip() in ("1", "true", "yes")


def dbg(msg: str) -> None:
    """调试日志，仅在 DEBUG=True 时输出。"""
    if DEBUG:
        print(f"[D] {msg}")

MULTI_SPLIT = ["\n", "@", "&"]


# ============ 账号数据结构 ============
@dataclass
class NissanAccount:
    wxid: str = ""
    remark: str = ""
    token: str = ""        # 手动模式：直接提供
    oneid: str = ""        # 手动模式：直接提供
    openid: str = ""       # 社区登录所需（可选，通常由协议服务返回）


@dataclass
class AccountSummary:
    index: int
    name: str = ""
    mobile: str = "N/A"
    oneid: str = "N/A"
    sign_status: str = "未执行"
    growth_score: Any = "?"
    success: bool = False
    error_message: str = ""
    detail_lines: List[str] = field(default_factory=list)

    def log(self, message: str = "") -> None:
        self.detail_lines.append(message)
        print(message)

    def build_notify_lines(self) -> List[str]:
        lines = [f"【账号{self.index}】{self.name}"]
        if self.mobile != "N/A":
            lines.append(f"手机号: {self.mobile}")
        lines.append(f"签到: {self.sign_status}")
        lines.append(f"成长值: {self.growth_score}")
        if self.error_message:
            lines.append(f"说明: {self.error_message}")
        return lines


# ============ 工具函数 ============
def parse_accounts(raw_wxid: str, raw_val: str) -> List[NissanAccount]:
    """解析 wxid 列表与可选的 token#oneid 手动列表。"""
    accounts: List[NissanAccount] = []

    def split_items(raw: str) -> List[str]:
        if not raw:
            return []
        return [x.strip() for x in re.split(r"[\n@&]", raw) if x.strip()]

    for item in split_items(raw_wxid):
        if "#" in item:
            wxid, remark = item.split("#", 1)
            accounts.append(NissanAccount(wxid=wxid.strip(), remark=remark.strip()))
        else:
            accounts.append(NissanAccount(wxid=item))

    # 手动 token#oneid 模式（降级/补充）
    for item in split_items(raw_val):
        if "#" in item:
            token, oneid = item.split("#", 1)
            accounts.append(NissanAccount(token=token.strip(), oneid=oneid.strip(),
                                          remark="手动登录"))
    return accounts


def build_code_url(raw_url: str) -> str:
    """已废弃：现使用 getCode.py 统一接口"""
    return ""


def gen_noncestr() -> str:
    """复刻小程序 getNonce：32 位大写 hex，第 13 位固定为 4。"""
    chars = "0123456789abcdef"
    arr = []
    for i in range(32):
        arr.append("4" if i == 12 else random.choice(chars))
    return "".join(arr).upper()


def random_uuid(length: int = 20) -> str:
    return "".join(random.choice("abcdef0123456789") for _ in range(length))


def mask_phone(phone: str = "") -> str:
    return re.sub(r"^(\d{3})\d{4}(\d{4})$", r"\1****\2", str(phone or ""))


def now_ms() -> int:
    return int(time.time() * 1000)


def now_s() -> int:
    return int(time.time())


def sha512(text: str) -> str:
    return hashlib.sha512(text.encode("utf-8")).hexdigest()


# ============ appletsKey 加密（H5 抽奖鉴权参数） ============
# 逆向自小程序主包 packageCommunity/app-service.js：
#   appletsKey = CryptoJS.AES.encrypt(JSON.stringify({mpToken, mid}), "lanyou1113")
# CryptoJS passphrase 模式 = OpenSSL EVP_BytesToKey(MD5) salted，输出 "Salted__"+salt+ct 的 base64
APPLETS_PASSPHRASE = b"lanyou1113"


def _evp_bytes_to_key(passphrase: bytes, salt: bytes,
                      key_len: int = 32, iv_len: int = 16) -> Tuple[bytes, bytes]:
    d = b""
    prev = b""
    while len(d) < key_len + iv_len:
        prev = hashlib.md5(prev + passphrase + salt).digest()
        d += prev
    return d[:key_len], d[key_len:key_len + iv_len]


def cryptojs_aes_encrypt(plaintext: str, passphrase: bytes = APPLETS_PASSPHRASE) -> str:
    """复刻 CryptoJS.AES.encrypt(text, passphrase)。"""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    salt = os.urandom(8)
    key, iv = _evp_bytes_to_key(passphrase, salt)
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plaintext.encode("utf-8"), 16))
    return base64.b64encode(b"Salted__" + salt + ct).decode()


def build_applets_key(mp_token: str, mid: str) -> str:
    """生成 H5 抽奖鉴权参数 appletsKey。"""
    plaintext = json.dumps({"mpToken": mp_token, "mid": str(mid)}, separators=(",", ":"))
    return cryptojs_aes_encrypt(plaintext)


# ============ 蓝友云 SM2 国密网关（抽奖 /v3/api） ============
# 逆向自 luckDrawH5 H5：doServpostV3。已用真实抓包验证 keysign 完全匹配、响应可解密。
# 业务 luckDrawH5 / 环境 iov_vit（appid 与抓包一致）：
ACTIVIT_BASE = "https://activit.dongfeng-nissan.com.cn"
GW_APPID = "appFxGW76iXHhEl4zzZQQmjIpcU53JHd54e"
GW_SERVER_PUB = ("04870FD04A487BBA9BA0F8881C5B28EB345F5C3EB43124EDEDC820B5104D5FF080"
                 "5571CBA0347C13C2EDB2469137A6F103CD58C4AB03937EB3555A94DDD8DC06E7")
GW_CLIENT_PRIV = "DFA906BB0B147EC630D987CEE4E81E9E3601B68DDDFC5DADAE9260F80FB74C80"
# appKey 是 SM2 DER 密文，需用固定私钥 handleKey 解出真实 appkey
GW_APPKEY_DER = (
    "3081EA022100E850B2FC064B52F0F490809E2E9CB30E972719C11CE331FB87CF27705C0A13F9"
    "022017D181BE3F1D1E5BA208F5645F159E057F0F9489E8DAD487B1DAE4DE35FF7D12"
    "0420C751FB9091186B17EEBAF3532EA2933589C7E79F6368B932ABCA4CAAD82DEBF4"
    "048180AC53E8631A1D0E856B75255EB0FEAA4F37A9EEC76620FBC246ECCBE4F0A8C870AE3"
    "52D2E45195D7CC055A3894AE076826964C2D11C7C052"
    "294B795C9EDE6D171D3A69EAD0D58BE9875B942E8312AD0A7B1AF3DD9A1A33188C98035FE"
    "BD151246262952E3B1A1DA50DEA457A1D202951105178DFC55FD26F49B6F18DB7E72B050")
GW_HANDLE_PRIV = "CF7E57E7887A9127467F105B65E386C8AD6714875ED3D022E3514A65B63AF888"

_GW_APPKEY_CACHE: Optional[str] = None


def _sm2_available() -> bool:
    try:
        import gmssl  # noqa
        return True
    except Exception:
        return False


def _sm2_parse_der(der_hex: str) -> Tuple[bytes, bytes, bytes]:
    """解析国密 SM2 DER 密文：SEQ{INT x, INT y, OCTET C3, OCTET C2}（C1C3C2）。返回 (C1, C3, C2)。"""
    b = bytes.fromhex(der_hex)
    i = 0
    assert b[i] == 0x30
    i += 1
    if b[i] & 0x80:
        n = b[i] & 0x7f
        i += 1 + n
    else:
        i += 1

    def rint() -> bytes:
        nonlocal i
        assert b[i] == 0x02
        i += 1
        ln = b[i]
        i += 1
        v = b[i:i + ln]
        i += ln
        if len(v) == 33 and v[0] == 0:
            v = v[1:]
        return v.rjust(32, b"\x00")

    def roct() -> bytes:
        nonlocal i
        assert b[i] == 0x04
        i += 1
        if b[i] & 0x80:
            nn = b[i] & 0x7f
            i += 1
            ln = int.from_bytes(b[i:i + nn], "big")
            i += nn
        else:
            ln = b[i]
            i += 1
        v = b[i:i + ln]
        i += ln
        return v

    x = rint()
    y = rint()
    c3 = roct()
    c2 = roct()
    return x + y, c3, c2


def _sm2_decrypt_der(der_hex: str, priv: str) -> bytes:
    """SM2 解密 DER 密文（gmssl mode=1 需 C1+C3+C2）。"""
    from gmssl import sm2
    c1, c3, c2 = _sm2_parse_der(der_hex)
    crypt = sm2.CryptSM2(public_key="", private_key=priv, asn1=False, mode=1)
    return crypt.decrypt(c1 + c3 + c2)


def _sm2_encrypt_der(plaintext: str, pub: str) -> str:
    """SM2 加密为蓝友云 DER 格式：SEQ{INT x, INT y, OCTET C3, OCTET C2}（C1C3C2）。"""
    from gmssl import sm2, func
    crypt = sm2.CryptSM2(public_key=pub, private_key="", asn1=False, mode=1)
    enc = crypt.encrypt(plaintext.encode("utf-8"))  # gmssl mode=1 输出 C1C3C2 (raw)
    c1 = enc[:64]
    c3 = enc[64:96]
    c2 = enc[96:]

    def der_int(v: bytes) -> bytes:
        if v[0] & 0x80:
            v = b"\x00" + v
        return b"\x02" + bytes([len(v)]) + v

    def der_oct(v: bytes) -> bytes:
        ln = len(v)
        if ln < 0x80:
            head = bytes([ln])
        elif ln < 0x100:
            head = b"\x81" + bytes([ln])
        else:
            head = b"\x82" + ln.to_bytes(2, "big")
        return b"\x04" + head + v

    x, y = c1[:32], c1[32:]
    body = der_int(x) + der_int(y) + der_oct(c3) + der_oct(c2)
    ln = len(body)
    if ln < 0x80:
        head = bytes([ln])
    elif ln < 0x100:
        head = b"\x81" + bytes([ln])
    else:
        head = b"\x82" + ln.to_bytes(2, "big")
    return (b"\x30" + head + body).hex()


def _gw_appkey() -> str:
    """handleKey：SM2 解密 appKey DER -> hexToUtf8。结果缓存。"""
    global _GW_APPKEY_CACHE
    if _GW_APPKEY_CACHE is None:
        pt = _sm2_decrypt_der(GW_APPKEY_DER, GW_HANDLE_PRIV)
        _GW_APPKEY_CACHE = pt.decode("utf-8", "replace")
    return _GW_APPKEY_CACHE


def _gw_noncestr() -> str:
    """复刻 H5 getNoncestr：32 位 hex。"""
    return uuid_hex32()


def uuid_hex32() -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(32))


def _gw_distinct_id() -> str:
    """前端埋点 Cookie distinct_id：32 位 hex（抓包 PART_407/420 验证）。"""
    return uuid_hex32()


def _gw_session_id() -> str:
    """前端埋点 Cookie session_id：40 位 hex（抓包 PART_407/420 验证）。"""
    return "".join(random.choice("0123456789abcdef") for _ in range(40))


def _gw_utm_traceid() -> str:
    """营销追踪 utm_traceid：13 位时间戳 + 7 位随机（抓包 PART_420 格式）。"""
    return f"{int(time.time() * 1000)}" + "".join(
        random.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(7)
    )


# ============ 青龙 notify.py 推送 ============
try:
    from notify import send as notify_send
except ImportError:
    def notify_send(title, content):
        print(f"--- 通知 ---\n{title}\n{content}\n-------------")


def push_notify(title: str, content: str) -> None:
    try:
        notify_send(title, content)
        print("消息推送完成")
    except Exception as exc:
        print(f"消息推送失败: {exc}")


# ============ 主体类 ============
class NissanSign:
    def __init__(self) -> None:
        self.wechat_server = build_code_url(
            os.environ.get("WECHAT_SERVER", DEFAULT_WECHAT_SERVER)
        )
        self.skip_community = os.environ.get("NISSAN_SKIP_COMMUNITY") == "1"
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
            "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
            "MiniProgramEnv/Windows WindowsWechat/WMPF "
            "WindowsWechat(0x63090a1b)XWEB/14185"
        )
        self.referer = f"https://servicewechat.com/{WECHAT_MINI_APPID}/{PAGE_VERSION}/page-frame.html"
        # 蓝友云网关埋点 Cookie（抓包 PART_407/420：distinct_id + session_id）
        # 整个会话复用同一组值，模拟前端 JS 行为
        self.gw_distinct_id = _gw_distinct_id()
        self.gw_session_id = _gw_session_id()

    # ---------- 微信协议服务 ----------
    def get_code(self, wxid: str) -> Optional[str]:
        """通过 getCode.py 统一接口获取微信 login code"""
        try:
            return get_single_code(WECHAT_MINI_APPID, wxid)
        except Exception as exc:
            print(f"微信: 获取 code 异常: {exc}")
            return None

    def get_phone_encrypted(self, wxid: str) -> Optional[Dict]:
        """获取微信手机号 encryptedData/iv（与海天同款协议接口）。"""
        if os.environ.get("YYB_SERVER", "").strip():
            return get_single_phone_data(WECHAT_MINI_APPID, wxid)

        url = self.wechat_server.replace("/get/code", "/get/all/mobile")
        payload = {
            "wxid": wxid,
            "appid": WECHAT_MINI_APPID,
            "data": json.dumps(
                {"api_name": "webapi_getuserwxphone", "with_credentials": True},
                ensure_ascii=False,
            ),
            "opt": 0,
        }
        try:
            resp = requests.post(url, json=payload, timeout=30,
                                 proxies={"http": None, "https": None})
            result = resp.json()
        except Exception as exc:
            print(f"微信: 获取手机号异常: {exc}")
            return None
        if not result.get("Success"):
            print(f"微信: 获取手机号失败: {result.get('Message', 'unknown')}")
            return None
        raw = result.get("Data", {}).get("Data", "")
        if isinstance(raw, str):
            info = json.loads(raw) if raw else {}
        elif isinstance(raw, dict):
            info = raw
        else:
            info = {}
        return info.get("wx_phone", {}) if isinstance(info.get("wx_phone"), dict) else info

    # ---------- 东风日产登录 ----------
    def login(self, account: NissanAccount, summary: AccountSummary) -> bool:
        """
        wxid 自动登录链路：
          1) 微信协议服务 -> code（部分协议服务同时返回 openid）
          2) wxapi: code 换 JWT token（/api/small/v4/wechat/login）
          3) 微信手机号 encryptedData/iv -> decrypt_data 绑定 -> user/info 拿手机号
          4) ariya: 拿成长体系 oneid
          5) community: phone+openid+code 换社区 JWT（已验证样本）

        注意：wxapi 的 session/decrypt_data 在抓包中为失败态(Bad Auth)，其成功响应
              字段名未能 100% 还原，第 2、4 步做了多重兼容并标 [需联调]；
              community 第 5 步有成功样本，结构已确认。
        """
        self.community_token = ""
        self.openid = account.openid or ""
        self.api_token = ""
        self.wx_uuid = ""

        wxid = account.wxid
        wx_uuid = random_uuid()
        self.wx_uuid = wx_uuid

        # ---- 手机号 encryptedData/iv（与 code 无关，单独协议接口）----
        phone = self.get_phone_encrypted(wxid)
        phone_plain = ""
        if isinstance(phone, dict):
            phone_plain = phone.get("phoneNumber") or phone.get("purePhoneNumber") or ""
            if phone_plain:
                summary.mobile = mask_phone(phone_plain)
            if not self.openid:
                self.openid = phone.get("openid") or phone.get("openId") or ""

        # ---- ariya 登录（核心）：每个微信 code 一次性，单独取一个 code ----
        # 抓包证据：ariya 业务请求头 token 是短 hex 182436cc...，与 wxapi 的 JWT 不同；
        # 接口 GET /toc-login-service/nissan/v2/user/login/{code}，Accept-Encoding: identity 避免 brotli。
        ariya_code = self.get_code(wxid)
        if not ariya_code:
            summary.error_message = "获取微信 code 失败（ariya）"
            return False
        ariya_info = self._fetch_oneid(ariya_code, wx_uuid, summary, phone=phone)
        if not ariya_info or not ariya_info.get("oneid"):
            summary.error_message = "获取 oneid 失败（成长体系标识未取到）"
            return False
        self.oneid = ariya_info["oneid"]
        summary.oneid = self.oneid
        if ariya_info.get("token"):
            self.token = ariya_info["token"]
            summary.log("登录: ariya 成功（oneid + token 已就绪）")
        # 保存 wxapi 的 JWT（签到 signSave 用）和 openid（urid 头用）
        self.api_token = ariya_info.get("api_token") or ""
        if not self.openid and ariya_info.get("openid"):
            self.openid = ariya_info["openid"]
        # ariya login 响应直接带明文手机号，补全（decrypt_data 多余）
        ariya_phone = ariya_info.get("phone") or ""
        if ariya_phone and (not phone_plain):
            phone_plain = ariya_phone
        if phone_plain:
            summary.mobile = mask_phone(phone_plain)

        # ---- community 社区登录：再取一个独立的新 code（有成功样本，结构已确认）----
        if not self.skip_community:
            phone_for_comm = phone_plain
            comm_code = self.get_code(wxid)
            if self.openid and phone_for_comm and comm_code:
                comm_token = self.community_login(self.openid, phone_for_comm, comm_code)
                if comm_token:
                    self.community_token = comm_token
                    summary.log("社区: 社区登录成功")
                else:
                    summary.log("社区: 社区登录失败（不影响签到）")
            else:
                summary.log(
                    f"社区: 跳过 openid={'有' if self.openid else '无'} "
                    f"phone={'有' if phone_for_comm else '无'} "
                    f"code={'有' if comm_code else '无'}"
                )
        return True

    def _exchange_token(self, code: str, wx_uuid: str,
                        summary: AccountSummary) -> Optional[str]:
        """
        code 换 JWT token。

        登录接口路径已根据抓包 JWT iss 字段还原：
          iss = "https://wxapi.dongfeng-nissan.com.cn/api/small/v4/session/{code}"
          即接口为 GET /api/small/v4/session/{code}，code 直接拼在 URL 中（Laravel 风格）。
        抓包中所有 wxapi 业务请求都带 wxUuid query 参数，登录接口同样带上以保持一致。
        返回结构兼容：data.token / data(str) / token / access_token。
        """
        url = f"{WXAPI_BASE}/api/small/v4/session/{code}"
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "Referer": self.referer,
            "xweb_xhr": "1",
        }
        try:
            resp = requests.get(
                url,
                params={"wxUuid": wx_uuid},
                headers=headers,
                timeout=20,
            )
            result = resp.json()
        except Exception as exc:
            summary.log(f"换 token 异常: {exc}")
            return None
        # 兼容多种返回结构（实测 wxapi 返回 data.api_token）
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        token = (
            data.get("api_token")
            or data.get("token")
            or data.get("access_token")
            or result.get("token")
            or (result.get("data") if isinstance(result.get("data"), str) else None)
        )
        if token:
            return token
        summary.log(f"换 token 失败: {str(result)[:150]}")
        return None

    def _fetch_oneid(self, code: str, wx_uuid: str, summary: AccountSummary,
                     token: str = "", phone: Optional[Dict] = None) -> Optional[Dict]:
        """
        ariya-api 登录接口：用微信 code 换 ariya 专用 token + oneid。

        抓包证据（PART_030/031/071/072/101 等）：
          GET {ARIYA_BASE}/toc-login-service/nissan/v2/user/login/{code}
          部分 URL 带 ?wxUuid=...&sourcecode=&smartcode= query（保持一致带上）
          请求头 Accept-Encoding: identity 避免 brotli 压缩（业务接口统一用 identity）
          抓包响应被 brotli 压缩未解出，但所有 ariya 业务请求头里：
            token = 182436cc6d26580561543ce524dbc208 （短 hex，非 JWT）
            oneid = 16116add342047638970c8d7dd8ce8322690
          即此接口必然同时返回 token + oneid，本方法做多种字段兼容解析。

        前置步骤：
          若协议服务返回了手机号 encryptedData/iv，先用 wxapi JWT 调 decrypt_data 绑定手机号，
          再调 ariya login（抓包 PART_100 已验证 decrypt_data 成功响应仅返回 phoneNumber）。
        """
        # 先尝试手机号解密绑定（部分账号 ariya login 依赖手机号已绑定）
        if phone and phone.get("encryptedData") and phone.get("iv") and token:
            try:
                resp = requests.post(
                    f"{WXAPI_BASE}/api/small/v4/wechat/decrypt_data",
                    params={"wxUuid": wx_uuid},
                    json={
                        "encryptedData": phone["encryptedData"],
                        "iv": phone["iv"],
                        "type": 1,
                    },
                    headers=self._wxapi_headers(token),
                    timeout=20,
                )
                decrypt_data = resp.json().get("data", {}) or {}
                # 顺便从解密结果补全手机号/openid
                if decrypt_data.get("phoneNumber"):
                    summary.mobile = mask_phone(decrypt_data.get("phoneNumber"))
            except Exception as exc:
                summary.log(f"手机号绑定异常(忽略): {exc}")

        url = f"{ARIYA_BASE}/toc-login-service/nissan/v2/user/login/{code}"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "identity",  # 关键：避免 brotli 压缩
            "User-Agent": self.user_agent,
            "Referer": self.referer,
            "xweb_xhr": "1",
        }
        try:
            resp = requests.get(
                url,
                params={"wxUuid": wx_uuid, "sourcecode": "", "smartcode": ""},
                headers=headers,
                timeout=20,
            )
            # 即便服务端仍返回压缩，尝试兜底解压
            try:
                result = resp.json()
            except Exception:
                text = resp.text
                try:
                    result = json.loads(text)
                except Exception:
                    summary.log(f"ariya login 响应非 JSON: {text[:200]}")
                    return None
        except Exception as exc:
            summary.log(f"ariya login 异常: {exc}")
            return None

        # 兼容多种返回结构（实测成功响应在 rows 里，token 字段名 api_token）
        data = {}
        for key in ("rows", "data"):
            v = result.get(key)
            if isinstance(v, dict):
                data = v
                break
        oneid = (
            data.get("oneid")
            or data.get("oneId")
            or data.get("ly_user_id")
            or data.get("uuid")
            or data.get("uid")
            or data.get("userId")
            or data.get("memberId")
            or result.get("oneid")
        )
        # ariya 业务接口需要的是短 hex token（抓包真值 182436cc...），
        # 不是 api_token（那是 wxapi 的 JWT）。短 token 字段名优先尝试 token。
        ariya_token = (
            data.get("token")
            or data.get("access_token")
            or data.get("api_token")
            or result.get("token")
        )
        if oneid:
            # 调试：打印 rows 字段名 + token 形态（短 hex / JWT），便于核对
            tok_kind = "JWT" if (ariya_token or "").count(".") == 2 else "short"
            dbg(f"ariya login rows keys={list(data.keys())}, token类型={tok_kind}")
            # api_token 是 wxapi 域名（含签到 signSave）所需的 JWT，单独返回
            return {
                "oneid": oneid,
                "token": ariya_token or "",
                "api_token": data.get("api_token") or "",
                "openid": data.get("openid") or data.get("openId") or "",
                "phone": data.get("phone") or "",
            }
        # 未取到 oneid：打印完整 rows 字段帮助定位字段名
        dbg(f"ariya login 字段待确认，rows={json.dumps(data, ensure_ascii=False)[:500]}")
        return None

    # ---------- 请求头构造 ----------
    def _wxapi_headers(self, token: str) -> Dict:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "Referer": self.referer,
            "urid": self.openid or "",
            "xweb_xhr": "1",
        }

    def wxapi_post(self, path: str, body: Optional[Dict] = None) -> Dict:
        """wxapi 域名 POST（JWT 鉴权）。签到 signSave 抓包为空 body。"""
        headers = self._wxapi_headers(self.api_token)
        sep = "&" if "?" in path else "?"
        url = f"{WXAPI_BASE}{path}{sep}wxUuid={self.wx_uuid}"
        body_str = json.dumps(body, ensure_ascii=False) if body else ""
        try:
            resp = requests.post(
                url,
                data=body_str.encode("utf-8") if body_str else None,
                headers=headers, timeout=20,
            )
            return resp.json()
        except Exception as exc:
            print(f"wxapi: POST 异常 {path}: {exc}")
            return {}

    def wxapi_get(self, path: str) -> Dict:
        """wxapi 域名 GET（JWT 鉴权）。如抽奖剩余次数 drawRemain。"""
        headers = self._wxapi_headers(self.api_token)
        sep = "&" if "?" in path else "?"
        url = f"{WXAPI_BASE}{path}{sep}wxUuid={self.wx_uuid}"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            return resp.json()
        except Exception as exc:
            print(f"wxapi: GET 异常 {path}: {exc}")
            return {}

    def _ariya_headers(self, token: str, oneid: str, ts: int, nonce: str,
                       sign: str, rng: str) -> Dict:
        return {
            "Accept": "*/*",
            "Accept-Encoding": "identity",  # 与抓包业务接口一致，避免 brotli
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "Referer": self.referer,
            "appCode": APP_CODE,
            "appSkin": APP_SKIN,
            "clientid": CLIENT_ID,
            "noncestr": nonce,
            "oneid": oneid,
            "uuid": oneid,
            "range": rng,
            "sign": sign,
            "timestamp": str(ts),
            "token": token,
            "xweb_xhr": "1",
        }

    def ariya_post(self, path: str, body: Optional[Dict] = None) -> Optional[Dict]:
        """
        ariya-api 请求（自动签名）。

        签名规则（抓包真值已复现验证 PASS）：
          range 固定为 "1"，sign = SHA512(clientid + timestamp + token + noncestr + "1" + oneid)
          —— 即使 POST 携带 body，body 也【不】参与签名（实测多个带 body 的请求均如此）。
        """
        ts = now_ms()
        nonce = gen_noncestr()
        rng = "1"
        raw = f"{CLIENT_ID}{ts}{self.token}{nonce}{rng}{self.oneid}"
        sign = sha512(raw)
        # 注意：body={} 时也要发送 "{}"（抓包 growthvalue/medal Content-Length:2）
        body_str = json.dumps(body, ensure_ascii=False, separators=(",", ":")) if body is not None else ""
        headers = self._ariya_headers(self.token, self.oneid, ts, nonce, sign, rng)
        full_url = f"{ARIYA_BASE}{path}"
        try:
            resp = requests.post(
                full_url,
                data=body_str.encode("utf-8") if body_str else None,
                headers=headers, timeout=20,
            )
            result = resp.json()
            return result
        except Exception as exc:
            print(f"ariya: 请求异常 {path}: {exc}")
            return None

    # ---------- ariya-api 业务任务 ----------
    def do_sign(self, summary: AccountSummary) -> None:
        """每日签到（taskList -> checkin）。"""
        # 查询今日签到记录（抓包 PART_521：startTime=endTime=当天）
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        sign_list = self.ariya_post(
            "/dfn-growth/rest/ly-mp-growth-service/ly/mgs/checkin/signList",
            {"brandCode": 1, "channel": "2",
             "startTime": today_str, "endTime": today_str},
        )
        dbg(f"signList result={sign_list.get('result') if isinstance(sign_list, dict) else None}, "
              f"rows_count={len(sign_list.get('rows') or []) if isinstance(sign_list, dict) else 0}")
        already = False
        if sign_list and str(sign_list.get("result")) == "1":
            for row in (sign_list.get("rows") or []):
                st = str(row.get("signTime", ""))
                if st.startswith(today_str):
                    already = True
                    break
        if already:
            summary.sign_status = "今日已签到"
            summary.success = True
            summary.log("签到: 今日已签到，跳过")
            return

        # 执行签到。真实接口（抓包 wxapi 域名 + JWT，PART_327）：
        # GET /api/small/v4/signin/mgs/checkin/signSave?wxUuid=xxx，无 body，
        # 成功 code=10000；已签 code=10010 "今天已有签到记录"。
        # 小程序源码 __APP__/app-service.js:29403 t.signIn 中 method:"GET"。
        res = self.wxapi_get("/api/small/v4/signin/mgs/checkin/signSave")
        dbg(f"signSave resp={res}")
        code = res.get("code") if isinstance(res, dict) else None
        msg = (res or {}).get("message") or (res or {}).get("msg") or str(res)[:120]
        if code == 10000:
            summary.sign_status = "签到成功"
            summary.success = True
            summary.log("签到: 成功")
        elif code == 10010 or "已" in str(msg):
            summary.sign_status = "今日已签到"
            summary.success = True
            summary.log(f"签到: 今日已签到（{msg}）")
        else:
            summary.sign_status = f"签到失败: {msg}"
            summary.log(f"签到: 失败 {msg}")

    def query_growth(self, summary: AccountSummary) -> None:
        """查询成长值（成长值+勋章接口）。
        抓包真值（PART_316/325/366/522）：
          POST ariya-api /dfn-growth/rest/ly-mp-growth-service/ly/mgs/growth/growthvalue/medal
          body {}
          -> data.growthScore
        """
        res = self.ariya_post(
            "/dfn-growth/rest/ly-mp-growth-service/ly/mgs/growth/growthvalue/medal",
            {},
        )
        dbg(f"growth resp={res}")
        if res and str(res.get("result")) == "1":
            data = res.get("data") or {}
            score = data.get("growthScore")
            level = data.get("levelName")
            if score is not None:
                summary.growth_score = f"{score}（{level}）" if level else score
                summary.log(f"成长值: {summary.growth_score}")
                return
        summary.log("成长值: 查询失败")

    # ---------- community 社区任务 ----------
    def community_login(self, openid: str, phone: str, code: str) -> Optional[str]:
        """
        社区登录换取独立 JWT（与 wxapi/ariya 的 token 不同）。
        抓包成功样本（PART_258 index 47）：
          POST community.../api/v2/user_manage/wxlogin
          body {"phone","code","avatar","name","openid"}
          -> {"msg":"登录成功","code":"200","data":{"token":"<JWT>","token_type":"bearer","expired_at":7200}}
        """
        body = {
            "phone": phone,
            "code": code,
            "avatar": "https://wxapi.dongfeng-nissan.com.cn/small/empty_headimg.png",
            "name": f"nissan{phone}",
            "openid": openid,
        }
        try:
            resp = requests.post(
                f"{COMMUNITY_BASE}/api/v2/user_manage/wxlogin",
                json=body,
                headers={
                    "Accept": "*/*",
                    "Authorization": "Bearer null",
                    "Content-Type": "application/json",
                    "From-Type": "3",
                    "User-Agent": self.user_agent,
                    "Referer": self.referer,
                    "urid": openid,
                    "xweb_xhr": "1",
                },
                timeout=20,
            )
            result = resp.json()
            data = result.get("data", {}) or {}
            token = data.get("token")
            if not token:
                dbg(f"社区登录失败响应: {str(result)[:150]}")
            return token
        except Exception as exc:
            dbg(f"社区登录异常: {exc}")
            return None

    def _community_headers(self) -> Dict:
        return {
            "Accept": "*/*",
            "Authorization": f"Bearer {self.community_token}",
            "Content-Type": "application/json",
            "From-Type": "3",
            "User-Agent": self.user_agent,
            "Referer": self.referer,
            "urid": self.openid,
            "xweb_xhr": "1",
        }

    def community_request(self, path: str, body: Optional[Dict] = None,
                          method: str = "get") -> Optional[Dict]:
        """社区接口（Bearer JWT + urid）。"""
        if not getattr(self, "community_token", ""):
            return None
        try:
            resp = requests.request(
                method.upper(), f"{COMMUNITY_BASE}{path}",
                json=body if body is not None else None,
                headers=self._community_headers(), timeout=20,
            )
            try:
                return resp.json()
            except Exception:
                return {"_raw": resp.text}
        except Exception as exc:
            dbg(f"社区请求异常 {path}: {exc}")
            return None

    def community_tasks(self, summary: AccountSummary) -> None:
        """
        社区任务（community 域名 + 独立 JWT）。
        已验证可自动化的写操作（抓包真值 PART_263）：
          浏览任务上报 POST /api/v2/user/browse-task-report
            body {"report_type":"newcar_page_browse"} -> {"code":200,"msg":"任务完成"}
        点赞/评论/关注/发帖类任务需用户真实互动触发（taskList 中"帖子被推荐"
        "粉丝增长"等），脚本无法自动完成，故只跑浏览上报 + 验证登录态。
        """
        if self.skip_community:
            return
        if not getattr(self, "community_token", ""):
            summary.log("社区: 未取得社区登录态，跳过")
            return

        # 验证社区用户信息
        user = self.community_request("/api/v2/user")
        if user and str(user.get("code")) in ("200", "0"):
            summary.log("社区: 登录态有效")

        # 浏览任务上报（已验证写接口）
        report_types = ["newcar_page_browse"]
        done = 0
        for rt in report_types:
            res = self.community_request(
                "/api/v2/user/browse-task-report",
                body={"report_type": rt}, method="post",
            )
            if res and str(res.get("code")) == "200":
                done += 1
                summary.log(f"社区: 浏览任务上报成功（{rt}）")
            else:
                msg = (res or {}).get("msg") or str(res)[:80]
                summary.log(f"社区: 浏览任务上报失败（{rt}）{msg}")
        if done:
            summary.success = True

        # 点赞任务（抓包真值 PART_278）：
        #   先拉 feeds/home 取帖子 id，再 POST /api/v2/feeds/{id}/like 空 body {}
        #   响应 {"code":200,"msg":"点赞成功","data":1}。
        #   点赞接口为全局限速（X-Ratelimit-Limit:1），连续点会"操作太频繁"，
        #   且每日点赞 1 次即可拿到成长值奖励，故只点 1 个。
        feed_ids = self._fetch_feed_ids(limit=1)
        liked = 0
        for fid in feed_ids:
            res = self.community_request(
                f"/api/v2/feeds/{fid}/like", body={}, method="post")
            if res and str(res.get("code")) == "200":
                liked += 1
                summary.log(f"社区: 点赞成功（帖子 {fid}）")
            else:
                msg = (res or {}).get("msg") or str(res)[:60]
                summary.log(f"社区: 点赞跳过（帖子 {fid}）{msg}")
        if liked:
            summary.success = True
            summary.log(f"社区: 共点赞 {liked} 个帖子")

        summary.log("社区: 任务执行完成")

    def _fetch_feed_ids(self, limit: int = 1) -> List[int]:
        """拉社区首页 feeds 列表，提取帖子 id（顶层 id 字段），随机挑 limit 个用于点赞。"""
        res = self.community_request(
            "/api/v2/feeds/home?page=1&channel_id=1")
        ids: List[int] = []
        if not isinstance(res, dict):
            return ids
        items = res.get("data")
        if isinstance(items, dict):
            items = items.get("list") or items.get("data") or []
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and isinstance(it.get("id"), int):
                    ids.append(it["id"])
        if not ids:
            return ids
        random.shuffle(ids)
        return ids[:limit]

    def query_draw_remain(self, summary: AccountSummary) -> None:
        """查询抽奖剩余次数（wxapi + JWT，抓包真值 PART_150）。
        抽奖动作是 H5 网页(luckDrawH5/egg)，需 appletsKey 加密参数。
        appletsKey 已逆向破解：CryptoJS.AES.encrypt({mpToken,mid}, "lanyou1113")。
        有剩余次数时生成 egg 抽奖 H5 的 appletsKey 并打印可直接打开的 URL。"""
        res = self.wxapi_get("/api/small/v4/drawRemain")
        try:
            remain = (((res or {}).get("data") or {}).get("rows") or {}).get("remain")
        except Exception:
            remain = None
        if remain is None:
            summary.log("抽奖: 剩余次数查询失败")
            return
        summary.log(f"抽奖: 剩余次数 {remain}")
        if not remain or int(remain) <= 0:
            return
        # 有次数：生成 appletsKey（需社区登录态 + mid）
        if not getattr(self, "community_token", ""):
            summary.log("抽奖: 无社区登录态，无法生成 appletsKey")
            return
        mid = self._fetch_community_mid()
        if not mid:
            summary.log("抽奖: 未取得社区 mid，无法生成 appletsKey")
            return
        try:
            applets_key = build_applets_key(self.community_token, mid)
        except Exception as exc:
            summary.log(f"抽奖: appletsKey 生成失败 {exc}")
            return
        # 保存 appletsKey 和 mid 供后续 generate.act.token 构造完整 Referer
        self.applets_key = applets_key
        self.community_mid = mid
        egg_url = (
            "https://activit.dongfeng-nissan.com.cn/luckDrawH5/egg"
            f"?terminal_type=wx_miniprogram&openid={self.openid}"
            f"&appletsKey={requests.utils.quote(applets_key, safe='')}"
        )
        summary.log(f"抽奖: appletsKey 已生成（剩余{remain}次），URL 前 80 字符: {egg_url[:80]}...")
        # 若配置了 SM2 网关会话凭据，则全自动抽奖（纯 HTTP，无需 CDP）
        self._try_auto_lottery(summary)

    def _try_auto_lottery(self, summary: AccountSummary) -> None:
        """SM2 网关全自动抽奖。优先用社区 mp_token+mid 调 generate.act.token 自动换 gw 凭据；
        环境变量 nissan_draw 作兜底（提供活动参数 luckydraw_code/member_card_no，或完整凭据）。

        nissan_draw 多账号按 oneid 前缀匹配（oneid=...），分隔符 \n/@/&。
        每条支持两种格式：
          新（推荐，自动换凭据）：luckydraw_code#member_card_no[#vin]
          旧（兜底完整凭据）    ：gw_uuid#gw_token#luckydraw_code#member_card_no[#vin]

        全自动路径（推荐）：不配置 nissan_draw 时，自动调用 wxapi 接口拉取
          - entranceInfo（PART_487）：返回当前可抽奖活动 luckydraw_code
          - member-card1（PART_510）：返回会员卡号 member_card_no（CARD_NO）
        再用 community_token + mid 调 generate.act.token 换 gw 凭据。
        """
        raw = os.environ.get("nissan_draw", "").strip()
        entry = ""
        if raw:
            for line in re.split(r"[\n@&]+", raw):
                line = line.strip()
                if not line:
                    continue
                if line.startswith(self.oneid + "="):
                    entry = line[len(self.oneid) + 1:]
                    break
                if not entry:
                    entry = line  # 默认取第一条
        parts = entry.split("#") if entry else []
        # 解析新旧两种格式
        if len(parts) >= 5:
            gw_uuid, gw_token = parts[0], parts[1]
            luckydraw_code = parts[2]
            member_card_no = parts[3]
            vin = parts[4] if len(parts) > 4 else ""
        elif len(parts) >= 2:
            gw_uuid = gw_token = ""
            luckydraw_code = parts[0]
            member_card_no = parts[1]
            vin = parts[2] if len(parts) > 2 else ""
        else:
            gw_uuid = gw_token = luckydraw_code = member_card_no = vin = ""

        # 全自动：nissan_draw 未配置时，从 wxapi 接口拉取活动参数
        if not luckydraw_code:
            auto = self._fetch_lottery_params(summary)
            if auto:
                luckydraw_code, member_card_no = auto
                summary.log(f"抽奖: 自动获取活动参数 code={luckydraw_code} card={member_card_no}")

        # 优先自动换 gw 凭据（社区登录态 + mid）
        full_referer = None  # 完整 egg URL（抓包 PART_407/420：服务端校验 Referer 参数）
        gw_one_id = ""
        if not gw_uuid and getattr(self, "community_token", "") and _sm2_available():
            mid = self._fetch_community_mid()
            if mid:
                # 构造完整 Referer（抓包 PART_407/420：服务端校验 Referer 参数）
                # 抓包完整参数顺序：
                #   luckydraw_code, member_card_no, cardNo, appletsKey, openid,
                #   terminal_type, smartcode, utm_traceid, pre_siteid, pre_userid
                applets_key = getattr(self, "applets_key", "") or ""
                if luckydraw_code and member_card_no and applets_key:
                    ref_params = (
                        f"luckydraw_code={luckydraw_code}"
                        f"&member_card_no={member_card_no}"
                        f"&cardNo={member_card_no}"
                        f"&appletsKey={requests.utils.quote(applets_key, safe='')}"
                        f"&openid={self.openid}"
                        f"&terminal_type=wx_miniprogram"
                        f"&smartcode=C2021-50167-5280-204-2602279"
                        f"&utm_traceid={_gw_utm_traceid()}"
                        f"&pre_siteid=dn_mp"
                        f"&pre_userid={self.openid}"
                    )
                    full_referer = f"{ACTIVIT_BASE}/luckDrawH5/egg?{ref_params}"
                else:
                    full_referer = None
                creds = self.generate_act_token(mid, self.community_token,
                                                summary=summary, referer=full_referer)
                if creds:
                    gw_uuid, gw_token, gw_one_id = creds
                    summary.log(f"抽奖: generate.act.token 成功 uuid={gw_uuid[:8]}... oneId={gw_one_id[:8]}...")
                else:
                    summary.log("抽奖: generate.act.token 失败")
            else:
                summary.log("抽奖: 未取得社区 mid，无法自动换 gw 凭据")
        if not luckydraw_code:
            summary.log("抽奖: 未获取到 luckydraw_code（活动未开启或网络异常），跳过")
            return
        if not gw_uuid or not gw_token:
            summary.log("抽奖: 无 gw 凭据（自动换失败且未配置兜底），跳过自动抽奖")
            return
        try:
            # 抓包 PART_403:943 wxSubstituteToken：generate.act.token 响应的 oneId 覆盖
            # userInfo.allObject，getLottery 的 oneid 必须用此值（非 ariya oneid）
            # 抓包 PART_420：getLottery 的 Referer 必须是完整 egg URL（含所有参数），
            # 否则返回"参数错误[26]"
            self.do_lottery(summary, gw_uuid, gw_token, luckydraw_code, member_card_no, vin,
                            oneid=gw_one_id, referer=full_referer)
        except Exception as exc:
            summary.log(f"抽奖: 自动抽奖异常 {exc}")

    def _fetch_lottery_params(self, summary: AccountSummary) -> Optional[Tuple[str, str]]:
        """全自动获取抽奖活动参数 (luckydraw_code, member_card_no)。
        来源：
          - GET wxapi /api/small/v4/entranceInfo（PART_487）：rows[*].entryHyperlink 含 luckydraw_code
          - GET wxapi /api/small/v4/member-card1（PART_510）：data[0].CARD_NO
        """
        # 1. entranceInfo 拿 luckydraw_code
        info = self.wxapi_get("/api/small/v4/entranceInfo")
        luckydraw_code = ""
        if isinstance(info, dict) and info.get("code") == 10000:
            rows = ((info.get("data") or {}).get("rows")) or []
            for row in rows:
                link = row.get("entryHyperlink", "")
                # https://activit.../luckDrawH5/egg?luckydraw_code=NI...
                m = re.search(r"luckydraw_code=([A-Za-z0-9]+)", link)
                if m and "luckDrawH5/egg" in link:
                    luckydraw_code = m.group(1)
                    break
        if not luckydraw_code:
            summary.log("抽奖: entranceInfo 未找到可抽奖活动")
            return None
        # 2. member-card1 拿会员卡号
        card = self.wxapi_get("/api/small/v4/member-card1")
        member_card_no = ""
        if isinstance(card, dict) and card.get("code") == 10000:
            rows = card.get("data") or []
            if isinstance(rows, list) and rows:
                member_card_no = rows[0].get("CARD_NO") or ""
        if not member_card_no:
            summary.log("抽奖: member-card1 未返回 CARD_NO")
            return None
        return luckydraw_code, member_card_no

    def _fetch_community_mid(self) -> Optional[str]:
        """取社区用户 mid（appletsKey 明文所需）。
        抓包 PART_475：GET /api/v2/user -> data.member_id（20位数字字符串）。
        """
        user = self.community_request("/api/v2/user")
        if not user:
            return None
        data = user.get("data") if isinstance(user.get("data"), dict) else user
        dbg(f"/api/v2/user keys={list((data or {}).keys())[:20]}")
        dbg(f"member_id={data.get('member_id')}, mid={data.get('mid')}, id={data.get('id')}")
        # 抓包真值字段为 member_id（20位），优先取；id 是短数字（如 21011146）不可用
        for key in ("member_id", "mid", "user_id", "uid"):
            v = (data or {}).get(key)
            if v:
                return str(v)
        return None

    def generate_act_token(self, mid: str, mp_token: str,
                           summary: Optional[AccountSummary] = None,
                           referer: Optional[str] = None
                           ) -> Optional[Tuple[str, str, str]]:
        """调 ly.h5.operationalactivity.generate.act.token 换取 SM2 网关会话凭据 (uuid, token, oneId)。

        逆向自 luckDrawH5/egg H5（PART_406 第171行）：
          appletsKey 解密 -> {mpToken, mid}
          payload = {appCode:"nissan_act", targetId:mid, wxToken:mpToken, autoReg:"1"}
        首次调用 uuid/token 均为空，header 走 uid 分支（空值）。
        返回 (uuid, token) 或 None。
        """
        if not _sm2_available():
            if summary:
                summary.log("抽奖: 缺少 gmssl 依赖，无法调 generate.act.token")
            return None
        api = "ly.h5.operationalactivity.generate.act.token"
        payload = {"appCode": "nissan_act", "targetId": str(mid),
                   "wxToken": mp_token, "autoReg": "1"}
        noncestr = _gw_noncestr()
        ts = str(int(time.time() * 1000))
        appkey = _gw_appkey()
        v_cipher = _sm2_encrypt_der(json.dumps(payload, separators=(",", ":")), GW_SERVER_PUB)
        body = json.dumps({"v": v_cipher}, separators=(",", ":"))
        # 首次无 uuid/token：H5 JS 中 c.uuid||c.userId||c.uid 与 c.token 均为 undefined，
        # JS 字符串拼接 "undefined" 字面量；逆向实测匹配抓包 PART_407。
        # sign = sha512("undefined" + api + noncestr + ts + "undefined" + body)
        sign = hashlib.sha512(
            ("undefined" + api + noncestr + ts + "undefined" + body).encode()
        ).hexdigest()
        keysign = hashlib.sha512((GW_APPID + appkey + api + noncestr + ts + body).encode()).hexdigest()
        # 抓包 PART_407：Referer 为完整 egg URL（含 luckydraw_code/member_card_no/appletsKey 等）
        # 服务端校验 Referer 参数，简短 Referer 会返回"非法参数信息[gw]"
        ref = referer or f"{ACTIVIT_BASE}/luckDrawH5/egg"
        headers = {
            "api": api,
            "appCode": "nissan_act",
            "appid": GW_APPID,
            "content-type": "application/json",
            "keysign": keysign,
            "sign": sign,
            "noncestr": noncestr,
            "timestamp": ts,
            "uid": "",
            "Origin": ACTIVIT_BASE,
            "Referer": ref,
            "User-Agent": self.user_agent,
            "Cookie": f"distinct_id={self.gw_distinct_id}; session_id={self.gw_session_id}",
        }
        try:
            resp = requests.post(f"{ACTIVIT_BASE}/v3/api", data=body.encode("utf-8"),
                                 headers=headers, timeout=20)
            raw = resp.json()
        except Exception as exc:
            if summary:
                summary.log(f"抽奖: generate.act.token 请求异常 {exc}")
            return None
        # 调试：输出实际请求参数与服务端响应
        dbg(f"generate.act.token payload={payload}")
        dbg(f"body={body[:60]}... (len={len(body)})")
        dbg(f"raw resp={str(raw)[:160]}")
        v = raw.get("v") if isinstance(raw, dict) else None
        if not v:
            if summary:
                summary.log(f"抽奖: generate.act.token 无 v 响应 {str(raw)[:100]}")
            return None
        try:
            pt = _sm2_decrypt_der(v, GW_CLIENT_PRIV)
            try:
                data = json.loads(pt.decode("utf-8"))
            except Exception:
                import gzip
                data = json.loads(gzip.decompress(pt).decode("utf-8"))
        except Exception as exc:
            if summary:
                summary.log(f"抽奖: generate.act.token 解密失败 {exc}")
            return None
        if str(data.get("result")) != "1":
            if summary:
                summary.log(f"抽奖: generate.act.token 失败 {data.get('msg', '')}")
            dbg(f"解密后完整响应 data={str(data)[:300]}")
            return None
        d = data.get("data") or {}
        gw_uuid = d.get("uuid", "")
        gw_token = d.get("token", "")
        gw_one_id = d.get("oneId", "") or d.get("oneid", "")
        dbg(f"解密响应 userId={d.get('userId')} oneId={gw_one_id[:8]}... uuid={gw_uuid[:8]}...")
        if gw_uuid and gw_token:
            if not getattr(self, "act_user_id", ""):
                self.act_user_id = d.get("userId", "")
            # 抓包 PART_403:943 wxSubstituteToken effect：generate.act.token 响应的
            # oneId 会覆盖 userInfo.allObject，之后 getLottery 用的 oneid 就是此值
            return gw_uuid, gw_token, gw_one_id
        if summary:
            summary.log(f"抽奖: generate.act.token 返回缺 uuid/token {str(d)[:120]}")
        return None

    # ---------- 蓝友云 SM2 网关请求（抽奖 /v3/api） ----------
    def gw_request(self, api: str, data: Optional[Dict], gw_uuid: str,
                   gw_token: str, app_code: str = "nissan_act",
                   summary: Optional[AccountSummary] = None,
                   referer: Optional[str] = None) -> Optional[Dict]:
        """调蓝友云 SM2 网关 /v3/api。复刻 doServpostV3 + De 签名。
        sign    = sha512(uuid + api + noncestr + ts + token + body)
        keysign = sha512(appid + appkey + api + noncestr + ts + body)
        无 data 时 body 为空字符串。返回已解密 JSON。"""
        if not _sm2_available():
            if summary:
                summary.log("抽奖: 缺少 gmssl 依赖（pip install gmssl），无法走 SM2 网关")
            return None
        noncestr = _gw_noncestr()
        ts = str(int(time.time() * 1000))
        appkey = _gw_appkey()
        if data is not None:
            plaintext = json.dumps(data, separators=(",", ":"))
            if "getLottery" in api or "getUser" in api or "doLottery" in api:
                dbg(f"api={api} data={plaintext} (len={len(plaintext)})")
            v_cipher = _sm2_encrypt_der(plaintext, GW_SERVER_PUB)
            body = json.dumps({"v": v_cipher}, separators=(",", ":"))
            sign = hashlib.sha512((gw_uuid + api + noncestr + ts + gw_token + body).encode()).hexdigest()
            keysign = hashlib.sha512((GW_APPID + appkey + api + noncestr + ts + body).encode()).hexdigest()
        else:
            body = ""
            sign = hashlib.sha512((gw_uuid + api + noncestr + ts + gw_token).encode()).hexdigest()
            keysign = hashlib.sha512((GW_APPID + appkey + api + noncestr + ts).encode()).hexdigest()
        # 抓包 PART_420：getLottery/getUser/doLottery 的 Referer 必须是完整 egg URL
        # （含 luckydraw_code/member_card_no/cardNo/appletsKey/openid 等），
        # 简短 Referer 会返回"参数错误[26]"
        ref = referer or f"{ACTIVIT_BASE}/luckDrawH5/egg"
        # 抓包 PART_420 对比 PART_407：
        #   generate.act.token（首次无 uuid）: header 含 uid(空)，无 uuid
        #   getLottery/getUser/doLottery（有 gw_uuid）: header 含 uuid，无 uid
        # 多余的 uid header 会导致"参数错误[26]"，此处仅发 uuid
        # Cookie 必须带 distinct_id + session_id（前端埋点，抓包验证）
        headers = {
            "api": api,
            "appCode": app_code,
            "appid": GW_APPID,
            "content-type": "application/json",
            "keysign": keysign,
            "sign": sign,
            "noncestr": noncestr,
            "timestamp": ts,
            "uuid": gw_uuid,
            "Origin": ACTIVIT_BASE,
            "Referer": ref,
            "User-Agent": self.user_agent,
            "Cookie": f"distinct_id={self.gw_distinct_id}; session_id={self.gw_session_id}",
        }
        try:
            resp = requests.post(f"{ACTIVIT_BASE}/v3/api", data=body.encode("utf-8") if body else b"",
                                 headers=headers, timeout=20)
            raw = resp.json()
        except Exception as exc:
            if summary:
                summary.log(f"抽奖: 网关请求异常 {exc}")
            return None
        # 响应 v 字段需 SM2 解密
        v = raw.get("v") if isinstance(raw, dict) else None
        if not v:
            return raw
        try:
            pt = _sm2_decrypt_der(v, GW_CLIENT_PRIV)
            try:
                return json.loads(pt.decode("utf-8"))
            except Exception:
                import gzip
                return json.loads(gzip.decompress(pt).decode("utf-8"))
        except Exception as exc:
            if summary:
                summary.log(f"抽奖: 响应解密失败 {exc} 原始 {str(raw)[:80]}")
            return raw

    def do_lottery(self, summary: AccountSummary, gw_uuid: str, gw_token: str,
                   luckydraw_code: str, member_card_no: str = "",
                   vin: str = "", oneid: str = "",
                   referer: Optional[str] = None) -> None:
        """SM2 网关全自动抽奖：getLottery -> getUser -> doLottery。
        gw_uuid/gw_token 来自 generate.act.token 返回（H5 会话凭据）。
        referer 必须是完整 egg URL（抓包 PART_420 验证，简短 Referer 返回参数错误[26]）。"""
        # 抓包 PART_410:223 Ce.current = {luckydraw_code, member_card_no, vin, oneid}
        # 抓包明文长度校验：
        #   getLottery (PART_420) 明文139字节 = 4字段 + key:""（5字段）
        #   getUser    (PART_421) 明文130字节 = 4字段（无 key）
        #   doLottery  (PART_432) 明文225字节 = 4字段 + activity_update_token + multiple + phone（无 key）
        base = {
            "luckydraw_code": luckydraw_code,
            "member_card_no": member_card_no,
            "vin": vin,
            "oneid": oneid or self.oneid,
        }
        # 1. getLottery 拿 activity_update_token（需额外 key:"" 字段，抓包 PART_420 验证）
        lot_req = dict(base)
        lot_req["key"] = ""
        lot = self.gw_request("ly.h5.luckydrawV3.getLottery", lot_req, gw_uuid, gw_token,
                              summary=summary, referer=referer)
        act_token = ""
        if isinstance(lot, dict):
            d = lot.get("data") or {}
            act_token = d.get("activity_update_token", "")
        if not act_token:
            summary.log(f"抽奖: 获取 activity_update_token 失败 {str(lot)[:100]}")
            return
        # 2. getUser 查剩余（抓包 PART_421 用 V3，4字段无 key）
        user = self.gw_request("ly.h5.luckydrawV3.getUser", dict(base), gw_uuid, gw_token,
                               summary=summary, referer=referer)
        remain = None
        if isinstance(user, dict):
            remain = (user.get("data") or {}).get("remainCount")
        summary.log(f"抽奖: 网关剩余次数 {remain}")
        try:
            times = int(remain) if remain is not None else 0
        except Exception:
            times = 0
        if times <= 0:
            summary.log("抽奖: 无剩余次数")
            return
        # 3. 循环 doLottery（抓包 PART_432 用 V2，无 key，225字节验证）
        for i in range(times):
            req = dict(base)
            req.update({"activity_update_token": act_token, "multiple": "",
                        "phone": getattr(self, "phone", "")})
            res = self.gw_request("ly.h5.luckydrawV2.doLottery", req, gw_uuid, gw_token,
                                  summary=summary, referer=referer)
            if isinstance(res, dict) and res.get("result") in ("1", "20010000"):
                prize = ((res.get("data") or {}).get("prize") or {})
                summary.log(f"抽奖: 第{i+1}次 -> {prize.get('name', res.get('msg', '成功'))}")
            else:
                summary.log(f"抽奖: 第{i+1}次失败 {str(res)[:100]}")
                break
            time.sleep(2)

    # ---------- 单账号执行 ----------
    def run_account(self, account: NissanAccount, summary: AccountSummary) -> None:
        # 每账号重置登录态
        self.token = ""
        self.oneid = ""
        self.openid = account.openid or ""
        self.community_token = ""
        # 登录态准备
        if account.token and account.oneid:
            self.token = account.token
            self.oneid = account.oneid
            summary.oneid = account.oneid
            summary.log("使用手动 token#oneid 登录态（社区任务需 wxid 自动登录）")
        else:
            if not self.login(account, summary):
                summary.log(f"登录失败: {summary.error_message}")
                return

        # 任务
        self.do_sign(summary)
        time.sleep(1)
        self.query_growth(summary)
        time.sleep(1)
        self.query_draw_remain(summary)
        time.sleep(1)
        try:
            self.community_tasks(summary)
        except Exception as exc:
            summary.log(f"社区任务异常(忽略): {exc}")


def main() -> None:
    raw_wxid = os.environ.get("WX_ID", "")
    accounts = parse_accounts(raw_wxid, "")

    print(f"## 开始执行... {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if not accounts:
        print("未找到账号，请配置环境变量 WX_ID（wxid#备注）")
        return
    print(f"共 {len(accounts)} 个账号\n")

    worker = NissanSign()
    summaries: List[AccountSummary] = []
    for idx, account in enumerate(accounts, 1):
        name = account.remark or (account.wxid[:6] + "***" if account.wxid else f"账号{idx}")
        summary = AccountSummary(index=idx, name=name)
        print(f"= {idx}. {name} =")
        try:
            worker.run_account(account, summary)
        except Exception as exc:
            summary.error_message = str(exc)
            summary.log(f"账号执行异常: {exc}")
        summaries.append(summary)
        time.sleep(random.randint(1, 3))
        print("---")

    # 推送
    notify_blocks = []
    for s in summaries:
        notify_blocks.append("\n".join(s.build_notify_lines()))
    content = "\n\n".join(notify_blocks)
    print("所有账号任务执行完毕")
    push_notify(NOTIFY_TITLE, content)


if __name__ == "__main__":
    main()
