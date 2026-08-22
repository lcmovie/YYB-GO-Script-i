#  修改脚本 563行的配置信息
#  脚本同文件夹放青龙面板自带的notify.py推送脚本
"""
习酒花园（微信协议版）- 统一合并版本

入口: 微信小程序 习酒 (wx489f950decfeb93e)
后端: apimallwm.exijiu.com / xcx.exijiu.com
功能: 自动签到、种高粱、酿酒、答题、抽奖、制曲

环境变量配置说明：
========================================
必填：
  YYB_SERVER      YYB-Go-Enhanced 地址@账号ref，多账号一行一个

选填：
  WX_ID/WXIDXJ    只运行指定账号，格式：ref#备注，多账号换行或 & 分隔
                  未配置时自动读取 YYB_SERVER 中的全部账号ref
  WECHAT_SERVER   旧微信协议服务回退地址
                  默认：http://127.0.0.1:8011
  OCR_SERVER      滑块验证码识别服务地址（ddddocr）
                  默认：http://localhost:7777
                  不设则遇到滑块验证时报错
  GARDEN_SEED_TYPE  播种作物类型
                  0 = 自动判断（默认）：酒曲充足种高粱，不足种小麦
                  1 = 强制种高粱
                  2 = 强制种小麦
  GARDEN_AUTO_EXCHANGE  自动兑换积分开关
                  0 = 关闭（默认）
                  1 = 开启，有酒时自动兑换积分（1L=1积分）
  GARDEN_AUTO_WINE  自动酿酒开关
                  0 = 关闭酿酒（不投粮、不制酒、不处理酒坛）
                  1 = 开启酿酒（默认）

cron: 31 8,16 * * *
"""
# name: 习酒

import os
import sys
import time
import base64
import json
import logging
import calendar
import random
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ==================== 统一微信协议 ====================
# 支持两种模式：
# 1. getCode.py 标准模式（推荐）：获取微信code
# 2. 牛子协议高级模式（可选）：获取加密密钥/云函数/手机号等
try:
    from getCode import get_single_code
    try:
        from getCode import get_single_operate_wx_data
    except ImportError:
        get_single_operate_wx_data = None
    _HAS_GETCODE = True
except ImportError:
    get_single_operate_wx_data = None
    _HAS_GETCODE = False

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

def send_notify(title, content):
    try:
        from notify import send as _notify_send
        _notify_send(title, content)
    except ImportError:
        log.warning("未找到notify.py，跳过推送")
    except Exception as e:
        log.warning(f"推送失败: {e}")


# 月度酿酒累计（跨 cron 调用累加本月总升数），存于脚本同目录的 xijiu_monthly.json
_MONTHLY_FILE = Path(__file__).resolve().parent / "xijiu_monthly.json"
# 本月起点升数:服务端不返回历史月产量,可用 GARDEN_MONTH_BASE_L 填入本月已酿数量作为基准
MONTH_BASE_L = float(os.environ.get("GARDEN_MONTH_BASE_L", "0") or 0)


def load_monthly():
    try:
        return json.loads(_MONTHLY_FILE.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def add_monthly_brewed(liters):
    """累加本月酿酒升数，返回 (月份key, 本月累计=起点+累计收获, 本次累加)。"""
    key = datetime.now().strftime("%Y-%m")
    data = load_monthly()
    # 跨月自动清零：只保留当前月份
    if key not in data:
        data = {k: v for k, v in data.items() if k == key}
    data[key] = round(float(data.get(key, 0)) + float(liters), 2)
    try:
        _MONTHLY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    total = round(MONTH_BASE_L + data[key], 2)
    return key, total, round(float(liters), 2)

# ============================================================
#  常量配置
# ============================================================
PLOT_STATUS = {-1: "未解锁", 0: "空地", 1: "已播种", 2: "生长中", 10: "可收获", 11: "可收获(熟透)"}
CROP_TYPE = {1: "高粱", 2: "小麦"}
WINE_STATUS = {0: "空坛", 1: "空坛", 2: "已酿好", 3: "酿造中", 4: "已酿好"}

BASE_URL = "https://apimallwm.exijiu.com"
MAIN_BASE_URL = "https://xcx.exijiu.com/anti-channeling/public/index.php/api/v2"
APPID = "wx489f950decfeb93e"
DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"

# 环境变量
_SEED_TYPE_FORCE = int(os.environ.get("GARDEN_SEED_TYPE", "0"))
_AUTO_EXCHANGE = os.environ.get("GARDEN_AUTO_EXCHANGE", "0") == "1"
OCR_SERVER = os.environ.get("OCR_SERVER", "")

def _calc_auto_wine():
    env_val = os.environ.get("GARDEN_AUTO_WINE", "1")
    if env_val == "0":
        return False
    now = datetime.now()
    last_day = calendar.monthrange(now.year, now.month)[1]
    if now.day >= 25:
        if now.day == last_day and now.hour >= 20:
            return True
        return False
    return True
_AUTO_WINE = _calc_auto_wine()

# ============================================================
#  DdddOcr 验证码封装
# ============================================================
class DdddOcr:
    def __init__(self, server_url="http://localhost:7777"):
        self.base = server_url.rstrip("/")
        self.session = requests.Session()
    def _post(self, path, **kwargs):
        resp = self.session.post(self.base + path, timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json()
    def slide_comparison(self, bg_image, slide_image):
        return self._post("/slideComparison", files={
            "bg": ("bg.png", bg_image, "image/png"),
            "slide": ("slide.png", slide_image, "image/png"),
        })
    def capcode(self, image):
        return self._post("/capcode", files={"image": ("img.png", image, "image/png")})
    def ocr(self, image):
        result = self._post("/classification", files={"image": ("img.png", image, "image/png")})
        return result.get("result", "")

# ============================================================
#  AES 加密（AesCrypto.js 对应）
# ============================================================
class TokenInvalidError(BaseException):
    """Token or encryption key invalid, needs re-login"""
    pass

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

class AesCrypto:
    def __init__(self, key_bytes, iv_bytes):
        if len(key_bytes) not in (16, 24, 32):
            raise ValueError(f"AES key 长度必须是 16/24/32 字节，当前: {len(key_bytes)}")
        if len(iv_bytes) != 16:
            raise ValueError(f"AES iv 长度必须是 16 字节，当前: {len(iv_bytes)}")
        self.key = key_bytes
        self.iv = iv_bytes
    def encrypt(self, payload):
        plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        return cipher.encrypt(pad(plaintext, AES.block_size)).hex()
    def decrypt(self, hex_str):
        ciphertext = bytes.fromhex(hex_str)
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        return json.loads(unpad(cipher.decrypt(ciphertext), AES.block_size).decode("utf-8"))

# ============================================================
#  微信协议适配层（兼容牛子高级功能 + getCode标准功能）
# ============================================================
class WxAdapter:
    """
    微信协议适配器 - 双模式支持

    模式1 (getCode): 使用 get_single_code() 获取 code（标准方式）
    模式2 (牛子): 使用 WECHAT_SERVER 的牛子API获取加密密钥/云函数等高级功能
    """

    def __init__(self, server_url=None):
        self.server_url = (server_url or DEFAULT_WECHAT_SERVER).rstrip("/")
        yyb_entry = (
            os.environ.get("YYB_SERVER") or
            os.environ.get("YINGYOGBAO_SERVER") or
            ""
        ).splitlines()[0].strip()
        yyb_url = yyb_entry.rsplit("@", 1)[0] if "@" in yyb_entry else yyb_entry
        if yyb_url and not yyb_url.startswith(("http://", "https://")):
            yyb_url = "http://" + yyb_url
        self.yyb_server = yyb_url.rstrip("/")
        self.base = self.server_url + "/api/v1/wx/"
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def get_wx_code(self, wxid, appid):
        """获取微信code - 优先使用 getCode.py，回退到牛子API"""
        if _HAS_GETCODE:
            try:
                code = get_single_code(appid, wxid)
                if code:
                    return {"success": True, "code": code}
            except Exception as e:
                log.warning(f"getCode获取失败，尝试牛子API: {e}")

        # 单文件运行时可能无法导入同目录 getCode.py，直接使用
        # YYB_SERVER 中与当前 ref 对应的服务获取 wx.login code。
        if self._can_use_yyb(wxid):
            try:
                result = self._yyb_call("getCode", wxid, appid)
                code = result.get("code")
                if code:
                    return {"success": True, "code": code}
                return {"success": False, "error": "YYB未返回有效code"}
            except Exception as e:
                log.warning(f"YYB直连获取code失败，尝试牛子API: {e}")

        # 回退到牛子 API
        try:
            data = self.session.post(self.base + "app/get/code",
                json={"wxid": wxid, "appid": appid}, timeout=15).json()
            if data.get("Code") == 0:
                return {"success": True, "code": data["Data"]["code"]}
            return {"success": False, "error": data.get("Message", "获取code失败")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _raw_id(self, wxid):
        return str(wxid).split("#")[0].strip()

    def _configured_yyb_entries(self):
        entries = []
        for line in (os.environ.get("YYB_SERVER") or "").splitlines():
            value = line.strip()
            if not value or "@" not in value:
                continue
            server, ref = value.rsplit("@", 1)
            server, ref = server.strip().rstrip("/"), ref.strip()
            if not server or not ref:
                continue
            if not server.startswith(("http://", "https://")):
                server = "http://" + server
            entries.append({"server": server, "ref": ref})
        return entries

    def _yyb_entry_for(self, wxid):
        entries = self._configured_yyb_entries()
        raw_id = self._raw_id(wxid)
        for entry in entries:
            if raw_id in (entry["ref"], f'{entry["server"]}@{entry["ref"]}'):
                return entry
        if len(entries) == 1:
            return entries[0]
        return None

    def _is_wxid_style(self, wxid):
        return self._raw_id(wxid).lower().startswith("wxid_")

    def _can_use_yyb(self, wxid):
        return bool(self._yyb_entry_for(wxid) or self.yyb_server) and not self._is_wxid_style(wxid)

    def _can_use_unified_wxapp(self, wxid):
        return not self._is_wxid_style(wxid) and (bool(get_single_operate_wx_data) or bool(self.yyb_server))

    def _yyb_accounts(self):
        if not self.yyb_server:
            return []
        resp = self.session.get(f"{self.yyb_server}/accounts", timeout=15)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list):
            accounts = body
        elif isinstance(body, dict):
            accounts = body.get("data", [])
        else:
            accounts = []
        return accounts if isinstance(accounts, list) else []

    def _yyb_resolve_ref(self, wxid):
        raw_id = self._raw_id(wxid)
        accounts = self._yyb_accounts()

        for acc in accounts:
            if acc.get("openid") == raw_id:
                return str(acc.get("id", "") or raw_id)

        if raw_id.isdigit():
            for acc in accounts:
                if str(acc.get("id", "")) == raw_id:
                    return raw_id

        for acc in accounts:
            openid = acc.get("openid", "") or ""
            if openid and (raw_id in openid or openid in raw_id):
                return str(acc.get("id", "") or raw_id)

        if len(accounts) == 1:
            return str(accounts[0].get("id", "") or raw_id)
        return raw_id

    def _yyb_call(self, endpoint, wxid, appid, payload=None):
        entry = self._yyb_entry_for(wxid)
        yyb_server = entry["server"] if entry else self.yyb_server
        if not yyb_server:
            raise RuntimeError("未配置 YYB_SERVER")
        body = {
            "ref": entry["ref"] if entry else self._yyb_resolve_ref(wxid),
            "app_id": appid,
        }
        if payload is not None:
            body["payload"] = payload
        resp = self.session.post(f"{yyb_server}/wxapp/{endpoint}", json=body, timeout=30)
        if resp.status_code == 409:
            raise RuntimeError("账号 login_buffer 已过期，需要重新扫码登录")
        resp.raise_for_status()
        result = resp.json()
        if not isinstance(result, dict):
            raise RuntimeError(f"YYB响应异常: {resp.text[:120]}")
        if "code" in result and result.get("code") not in (0, "0", None):
            msg = result.get("error") or result.get("msg", resp.text[:120])
            raise RuntimeError(msg)
        inner = result.get("result")
        if inner is None:
            data = result.get("data", {})
            inner = data.get("result", data) if isinstance(data, dict) else data
        if not isinstance(inner, dict):
            raise RuntimeError(f"YYB响应result异常: {str(inner)[:120]}")
        return inner

    def _yyb_operate_wx_data(self, wxid, appid, payload):
        return self._yyb_call("operateWxData", wxid, appid, payload)

    def _unified_operate_wx_data(self, wxid, appid, payload):
        if get_single_operate_wx_data:
            try:
                return get_single_operate_wx_data(appid, wxid, payload)
            except Exception as e:
                log.warning(f"getCode通用接口失败，尝试直连YYB: {e}")
        return self._yyb_operate_wx_data(wxid, appid, payload)

    def _decode_jsonish(self, value):
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value.strip():
            return value
        text = value.strip()
        if text[:1] in "{[":
            try:
                return json.loads(text)
            except Exception:
                return value
        try:
            decoded = base64.b64decode(text + "=" * (-len(text) % 4)).decode()
            if decoded[:1] in "{[":
                return json.loads(decoded)
        except Exception:
            pass
        return value

    def _extract_encrypt_key(self, data):
        data = self._decode_jsonish(data)
        if not isinstance(data, dict):
            return None

        code = data.get("Code")
        if code not in (None, 0) and data.get("Success") is not True:
            return None

        inner = data.get("Data") or data.get("data") or data.get("result") or data.get("rawData") or {}
        if isinstance(inner, dict):
            jsapi_err = inner.get("jsapiBaseresponse", {}).get("errcode")
            if jsapi_err is not None and jsapi_err != 0:
                return None

        key = data.get("encrypt_key") or data.get("encryptKey")
        iv = data.get("iv")
        if key and iv:
            return {
                "encrypt_key": key,
                "iv": iv,
                "version": data.get("version") or data.get("encryptVer") or 3,
                "expire_in": data.get("expire_in") or data.get("expireIn"),
            }

        if isinstance(inner, dict) or isinstance(inner, str):
            parsed = self._extract_encrypt_key(inner)
            if parsed:
                return parsed
        return None

    def _extract_encrypted_data(self, data):
        data = self._decode_jsonish(data)
        if not isinstance(data, dict):
            return None

        encrypted_data = data.get("encryptedData") or data.get("encrypted_data")
        iv = data.get("iv")
        if encrypted_data and iv:
            return {"encryptedData": encrypted_data, "iv": iv, "rawData": data}

        for field in ("Data", "data", "result", "rawData"):
            if field in data:
                parsed = self._extract_encrypted_data(data[field])
                if parsed:
                    return parsed
        return None

    def get_user_encrypt_key(self, wxid, appid):
        """获取用户加密密钥（webapi_getuserencryptkey）"""
        payload = {
            "api_name": "webapi_getuserencryptkey",
            "data": {},
        }

        if self._can_use_unified_wxapp(wxid):
            try:
                data = self._unified_operate_wx_data(wxid, appid, payload)
                parsed = self._extract_encrypt_key(data)
                if parsed:
                    log.info(f"YYB 获取加密密钥成功 version={parsed.get('version')}")
                    return {"success": True, **parsed}
                log.warning(f"YYB get_user_encrypt_key无法提取密钥: {data}")
            except Exception as e:
                log.warning(f"YYB get_user_encrypt_key失败，尝试牛子API: {e}")

        body = {"wxid": wxid, "appid": appid, "data": json.dumps(payload)}
        data = self._post("app/call/function", body)
        parsed = self._extract_encrypt_key(data)
        if parsed:
            log.info(f"牛子 获取加密密钥成功 version={parsed.get('version')}")
            return {"success": True, **parsed}
        return {"success": False, "error": f"无法提取加密密钥: {str(data)[:200]}"}

    def call_function(self, wxid, appid, data_str):
        """调用小程序云函数，兼容牛子与YYB"""
        if self._can_use_unified_wxapp(wxid):
            try:
                payload = json.loads(data_str) if isinstance(data_str, str) else (data_str or {})
            except Exception:
                payload = {"data": data_str}
            try:
                data = self._unified_operate_wx_data(wxid, appid, payload)
                encrypted = self._extract_encrypted_data(data)
                if encrypted:
                    return {"success": True, **encrypted}
                return {"success": True, "rawData": data}
            except Exception as e:
                log.warning(f"YYB call_function失败，尝试牛子API: {e}")

        body = {"wxid": wxid, "appid": appid, "data": data_str}
        data = self._post("app/call/function", body)
        outer_ok = data.get("Code") == 0 or data.get("Success") is True
        if not outer_ok:
            return {"success": False, "error": data.get("Message", str(data))}
        inner = data.get("Data") or data.get("data") or {}
        jsapi_err = inner.get("jsapiBaseresponse", {}).get("errcode")
        if jsapi_err is not None and jsapi_err != 0:
            return {"success": False, "error": f"jsapi errcode={jsapi_err}"}
        b64_str = inner.get("data") if isinstance(inner, dict) else None
        if b64_str and isinstance(b64_str, str):
            try:
                res = json.loads(base64.b64decode(b64_str).decode())
                return {
                    "success": True, "signature": res.get("signature"),
                    "encryptedData": res.get("encryptedData"), "iv": res.get("iv"), "rawData": res,
                }
            except Exception:
                pass
        if isinstance(inner, dict) and inner.get("encryptedData"):
            return {"success": True, "encryptedData": inner.get("encryptedData"), "iv": inner.get("iv"), "rawData": inner}
        return {"success": False, "error": "无法提取 encryptedData"}

    def get_mobile(self, wxid, appid):
        """获取手机号及加密数据 - 仅牛子支持"""
        body = {
            "wxid": wxid, "appid": appid,
            "data": '{"api_name":"webapi_getuserwxphone","with_credentials":true}', "opt": 1,
        }
        data = self._post("app/get/all/mobile", body)
        if data.get("Code") != 0:
            return {"success": False, "error": data.get("Message", "获取手机号失败")}
        item = None
        all_mobile = data["Data"].get("ALLMobile", [])
        if all_mobile:
            item = all_mobile[0]
        elif data["Data"].get("Data"):
            try:
                inner = json.loads(data["Data"]["Data"])
                phones = inner.get("custom_phone_list", [])
                item = next((p for p in phones if p.get("encryptedData")), phones[0] if phones else None)
                if item and not item.get("code") and item.get("data"):
                    try: item["code"] = json.loads(item["data"]).get("code", "")
                    except Exception: pass
            except Exception as e:
                return {"success": False, "error": f"解析手机号数据失败: {e}"}
        if not item:
            return {"success": False, "error": "未找到手机号信息"}
        return {
            "success": True, "mobile": item.get("mobile"),
            "encryptedData": item.get("encryptedData", ""), "iv": item.get("iv", ""), "code": item.get("code", ""),
        }

    def get_session_id(self, wxid, appid):
        """获取sessionid - 仅牛子支持"""
        data = self._post("app/get/sessionid", {"wxid": wxid, "appid": appid})
        outer_ok = data.get("Code") == 0 or data.get("Success") is True
        if outer_ok:
            inner = data.get("Data") or data.get("data") or {}
            session_key = (
                inner.get("session_key") or inner.get("sessionKey") or
                inner.get("SessionKey") or inner.get("sessionid") or
                inner.get("Sessionid") or inner
            )
            return {"success": True, "session_key": session_key, "raw": inner}
        return {"success": False, "error": data.get("Message", str(data))}

    # 内部方法
    def _post(self, path, body):
        resp = self.session.post(self.base + path, json=body, timeout=15)
        resp.raise_for_status()
        return resp.json()

# ============================================================
#  GardenClient 花园客户端
# ============================================================
class GardenClient:
    """
    花园种高粱游戏客户端
    两种使用方式：
      1. 手动传 token：GardenClient(token="xxx")
      2. 自动登录：client.auto_login(wxid="xxx", server_url="xxx")
    """

    def __init__(self, token=None, ocr_server=None):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 MicroMessenger MiniProgram",
        })
        self.token = token
        self.crypto = None
        self.wxid = None
        self._encrypt_version = 1
        self._crypto_set_time = 0
        self._crypto_key = ""
        self._crypto_iv = ""
        self._wx = None
        self._wx_appid = APPID
        self.ocr = DdddOcr(ocr_server) if ocr_server else None
        if token:
            self.session.headers["Authorization"] = token

    def set_token(self, token):
        self.token = token
        self.session.headers["Authorization"] = token

    def set_crypto(self, key, iv, version=3):
        key_bytes = key.encode("utf-8")
        iv_bytes = iv.encode("utf-8")
        self.crypto = AesCrypto(key_bytes, iv_bytes)
        self._encrypt_version = version
        self._crypto_set_time = time.time()
        self._crypto_key = key
        self._crypto_iv = iv

    def auto_login(self, wxid, server_url=None, appid=APPID, ocr_server=None):
        """通过微信协议自动登录"""
        if ocr_server:
            self.ocr = DdddOcr(ocr_server)
        wx = WxAdapter(server_url)
        self.wxid = wxid
        self._wx = wx
        self._wx_appid = appid

        # Step 1: 获取 login_code（主系统）
        code_res1 = wx.get_wx_code(wxid, appid)
        if not code_res1["success"]:
            raise RuntimeError(f"获取code失败: {code_res1['error']}")
        main_login_url = f"{MAIN_BASE_URL}/auth/session?code={code_res1['code']}"
        resp = self.session.get(main_login_url, timeout=15)
        resp.raise_for_status()
        main_body = resp.json()
        if main_body.get("code") == 0:
            login_code = main_body["data"].get("login_code")
            if login_code:
                self.session.headers["login_code"] = login_code
                log.info("login_code 获取成功")

        # Step 2: 再获取一个 code → garden authorized_token
        code_res2 = wx.get_wx_code(wxid, appid)
        if not code_res2["success"]:
            raise RuntimeError(f"获取garden code失败: {code_res2['error']}")
        login_result = self.login(code_res2["code"])
        token = login_result.get("authorized_token") or login_result.get("token") or login_result.get("access_token")
        if not token:
            raise RuntimeError(f"登录未返回token，响应: {login_result}")
        self.set_token(token)

        # Step 3: 获取加密密钥
        env_key = os.environ.get("GARDEN_ENCRYPT_KEY", "")
        env_iv = os.environ.get("GARDEN_ENCRYPT_IV", "")
        if env_key and env_iv:
            self.set_crypto(env_key, env_iv)
            return {"token": token, "crypto_ready": True}

        # 方式 b: webapi_getuserencryptkey
        try:
            enc_key_res = wx.get_user_encrypt_key(wxid, appid)
            if enc_key_res.get("success"):
                self.set_crypto(enc_key_res["encrypt_key"], enc_key_res["iv"], version=enc_key_res.get("version", 3))
                return {"token": token, "crypto_ready": True}
        except Exception as e:
            log.warning(f"webapi_getuserencryptkey 异常: {e}")

        # 方式 c: session_id 备选
        try:
            sess_res = wx.get_session_id(wxid, appid)
            if sess_res.get("success"):
                sk_hex = sess_res.get("session_key", "")
                if sk_hex and len(sk_hex) >= 32:
                    self.set_crypto(sk_hex[:16], sk_hex[16:32], version=1)
        except Exception:
            pass

        # 方式 d/d2: userinfo → mobile → getAuth
        encrypted_data, iv = self._try_encrypted_data_via_userinfo(wx, wxid, appid)
        if not encrypted_data or not iv:
            encrypted_data, iv = self._try_encrypted_data_via_mobile(wx, wxid, appid)
        if encrypted_data and iv:
            self._try_get_auth(encrypted_data, iv)

        return {"token": token, "crypto_ready": self.crypto is not None}

    def _try_encrypted_data_via_userinfo(self, wx, wxid, appid):
        try:
            res = wx.call_function(wxid, appid, json.dumps({
                "api_name": "webapi_getuserinfo", "data": {"lang": "zh_CN"}, "with_credentials": True
            }))
            if res.get("success"):
                return res.get("encryptedData"), res.get("iv")
        except Exception:
            pass
        return None, None

    def _try_encrypted_data_via_mobile(self, wx, wxid, appid):
        try:
            res = wx.get_mobile(wxid, appid)
            if res.get("success") and res.get("encryptedData") and res.get("iv"):
                return res["encryptedData"], res["iv"]
        except Exception:
            pass
        return None, None

    def _try_get_auth(self, encrypted_data, iv):
        try:
            auth_result = self._get_raw("/garden/wechat/auth", {"encryptedData": encrypted_data, "iv": iv})
            key = auth_result.get("encryptKey") or auth_result.get("encrypt_key")
            auth_iv = auth_result.get("iv")
            version = auth_result.get("version")
            if key and auth_iv:
                self.set_crypto(key, auth_iv, version=version or 2)
        except Exception:
            pass

    def _refresh_crypto_if_needed(self):
        if not self.crypto or not self._wx or not self.wxid:
            return
        elapsed = time.time() - self._crypto_set_time
        if elapsed < 3300:
            return
        try:
            res = self._wx.get_user_encrypt_key(self.wxid, self._wx_appid)
            if res.get("success"):
                self.set_crypto(res["encrypt_key"], res["iv"], version=res.get("version", 3))
        except Exception:
            pass

    def _encrypt_payload(self, data):
        if not self.crypto:
            return data or {}
        self._refresh_crypto_if_needed()
        result = dict(data) if data else {}
        result["ts"] = int(time.time() * 1000)
        result["encryptData"] = self.crypto.encrypt(result)
        result["version"] = getattr(self, "_encrypt_version", 3)
        return result

    def _handle_response(self, body, retry_fn):
        code = body.get("code") or body.get("err")
        msg = body.get("msg") or ""
        if code == 0:
            return body.get("data")
        if code == 5001 or "加密校验失败" in msg or "用户信息异常" in msg:
            raise TokenInvalidError(f"[5001] {msg} (加密校验失败)")
        if code == 4012 or "非法的用户 token" in msg:
            raise TokenInvalidError(f"[4012] {msg} (非法的用户 token)")
        if code == 5008:
            if self.ocr is None:
                raise RuntimeError("触发滑块验证(5008)，请设置 OCR_SERVER")
            self._solve_slide_validate()
            return retry_fn()
        raise RuntimeError(f"[{code}] {msg}")

    def _solve_slide_validate(self):
        info = self._get_raw("/garden/slide_validate/getValidateInfo")
        bg_url = info.get("bg_url") or info.get("bgUrl") or info.get("background")
        slide_url = info.get("slide_url") or info.get("slideUrl") or info.get("slider")
        bg_bytes = requests.get(bg_url, timeout=10).content
        slide_bytes = requests.get(slide_url, timeout=10).content
        result = self.ocr.slide_comparison(bg_bytes, slide_bytes)
        x = result.get("target", [0])[0] if "target" in result else result.get("x", 0)
        self._post_raw("/garden/slide_validate/toValidate", {"x": x, "y": 0})

    def _get_raw(self, path, params=None):
        resp = self.session.get(BASE_URL + path, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data") or resp.json()

    def _post_raw(self, path, data=None):
        resp = self.session.post(BASE_URL + path, json=data or {}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _get(self, path, params=None):
        url = BASE_URL + path
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        return self._handle_response(body, lambda: self._get(path, params))

    def _post(self, path, data=None):
        url = BASE_URL + path
        resp = self.session.post(url, json=data or {}, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        return self._handle_response(body, lambda: self._post(path, data))

    # ---- 认证 ----
    def login(self, code):
        return self._get("/garden/wechat/login", {"code": code})
    def get_auth(self, params):
        return self._get("/garden/wechat/auth", params)

    # ---- 用户信息 ----
    def member_info(self, params=None):
        return self._get("/garden/Gardenmemberinfo/getMemberInfo", params)
    def tasks(self):
        return self._get("/garden/tasks/index")

    # ---- 签到 & 分享 ----
    def daily_sign(self, data=None):
        return self._post("/garden/sign/dailySign", self._encrypt_payload(data or {}))
    def daily_share(self):
        return self._post("/garden/gardenmemberinfo/dailyShare", self._encrypt_payload({}))

    # ---- 高粱地块 ----
    def get_sorghum_list(self, params=None):
        return self._get("/garden/sorghum/index", params)
    def seeds(self, data):
        return self._post("/garden/sorghum/seed", self._encrypt_payload(data))
    def watering(self, data):
        return self._post("/garden/sorghum/watering", self._encrypt_payload(data))
    def manuring(self, data):
        return self._post("/garden/sorghum/manuring", self._encrypt_payload(data))
    def harvest(self, data):
        return self._post("/garden/sorghum/harvest", self._encrypt_payload(data))
    def extend(self, data):
        return self._post("/garden/sorghum/extend", self._encrypt_payload(data))

    # ---- 酿酒 ----
    def wine_list(self, params=None):
        return self._get("/garden/Gardenmemberwine/index", params)
    def discharge_grain(self, params=None):
        volumn = (params or {}).get("volumn", 0)
        resp = self.session.post(
            BASE_URL + "/garden/gardenmemberwine/makeWine",
            data={"volumn": volumn},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15,
        )
        resp.raise_for_status()
        return self._handle_response(resp.json(), lambda: self.discharge_grain(params))
    def harvest_wine(self, params=None):
        return self._get("/garden/Gardenmemberwine/harvestWine", params)
    def make_yeast(self, data):
        volumn = (data or {}).get("volumn", 0)
        resp = self.session.post(
            BASE_URL + "/garden/wheat/makeWineYeast",
            data={"volumn": volumn},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15,
        )
        resp.raise_for_status()
        return self._handle_response(resp.json(), lambda: self.make_yeast(data))

    # ---- 兑换 & 抽奖 ----
    def exchange_wine(self, wine_vol):
        payload = self._encrypt_payload({"wine": wine_vol})
        return self._get("/garden/Gardenjifenshop/exchange", payload)
    def remain_free_draw_chance(self, params=None):
        return self._get("/garden/lottery/remainFreeDrawChance", params)
    def draw(self, data=None):
        return self._post("/garden/lottery/draw", data)

    # ---- 答题 ----
    def get_question_task(self):
        return self._get("/garden/Gardenquestiontask/index")
    def answer_results(self, question_id, selected):
        answer_str = json.dumps([{"itemid": question_id, "selected": selected}], separators=(",", ":"))
        enc = self._encrypt_payload({})
        params = {"answer": answer_str}
        params.update(enc)
        url = BASE_URL + "/garden/Gardenquestiontask/answerResults"
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return self._handle_response(resp.json(), lambda: self.answer_results(question_id, selected))

# ============================================================
#  业务逻辑工具函数
# ============================================================
def decide_seed_type(sorghum, wheat, wine_yeast, active_plots):
    if _SEED_TYPE_FORCE in (1, 2):
        return _SEED_TYPE_FORCE
    plots = max(active_plots, 1)
    yeast_needed = (plots * 100 * 5) // 200
    if wine_yeast >= yeast_needed:
        return 1
    else:
        return 2

def fmt_remaining(s):
    try:
        delta = datetime.strptime(s, "%Y-%m-%d %H:%M:%S") - datetime.now()
        t = int(delta.total_seconds())
        if t <= 0: return "已成熟"
        h, r = divmod(t, 3600)
        return "%dh%02dm" % (h, r // 60)
    except Exception:
        return s or "未知"

def fmt_remaining_from_seconds(secs):
    if secs <= 0: return "已成熟"
    h, r = divmod(int(secs), 3600)
    m, s = divmod(r, 60)
    if h > 0: return "%dh%02dm%02ds" % (h, m, s)
    elif m > 0: return "%dm%02ds" % (m, s)
    else: return "%ds"

def is_ready(s, tolerance_seconds=120):
    try:
        return datetime.now() >= datetime.strptime(s, "%Y-%m-%d %H:%M:%S") - timedelta(seconds=tolerance_seconds)
    except Exception:
        return True

# ============================================================
#  账号解析
# ============================================================
MULTI_SPLIT = ["\n", "@", "&"]

def parse_accounts(raw):
    accounts = []
    sep = None
    for s in MULTI_SPLIT:
        if s in raw: sep = s; break
    items = raw.split(sep) if sep else ([raw] if raw else [])
    for item in items:
        item = (item or '').strip()
        if not item: continue
        idx = item.rfind("#")
        if idx > 0:
            accounts.append({"id": item[:idx].strip(), "note": item[idx+1:].strip()})
        else:
            accounts.append({"id": item, "note": ""})
    return accounts

def parse_yyb_server_accounts(raw):
    """从多行 YYB_SERVER（地址@ref）提取账号，保持原有顺序并去重。"""
    accounts = []
    seen = set()
    for line in (raw or "").splitlines():
        value = line.strip()
        if not value or "@" not in value:
            continue
        _, ref = value.rsplit("@", 1)
        ref = ref.strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        accounts.append({"id": ref, "note": ""})
    return accounts

# ============================================================
#  主业务逻辑 run()
# ============================================================
# 浇水有效窗口:地块距成熟不足此秒数时浇水意义不大,留水给更需要地块。
# 可通过环境变量 GARDEN_WATER_WINDOW(秒)覆盖,默认 2 小时。
WATER_EFFECTIVE_SECS = int(os.environ.get("GARDEN_WATER_WINDOW", "7200") or 7200)


def _plot_remaining(ct):
    """地块距成熟剩余秒数;无时间信息返回 None(视为新种/长期作物,值得浇)。"""
    if not ct:
        return None
    try:
        return max(0, int((datetime.strptime(ct, "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds()))
    except Exception:
        return None


def run(client, do_daily=True):
    plot_summary_lines = []
    wine_summary_lines = []
    min_harvest_secs = None
    session_brewed_l = 0.0  # 本次运行收获的酒量(升)

    # ── 会员信息 ──
    log.info("👤 获取会员信息...")
    info = client.member_info()
    log.info("   昵称: %-12s  积分: %-6s  💧水: %-4s  🌿肥: %-4s" % (
        info.get("nick_name"), info.get("integration"), info.get("water"), info.get("manure")))
    log.info("   🌾高粱: %-6s斤  🌾小麦: %-6s斤  🍺酒曲: %-4s块  🍶酒: %sL" % (
        info.get("sorghum"), info.get("wheat"), info.get("wine_yeast"), info.get("wine")))

    if do_daily:
        # ── 每日签到 ──
        log.info("📅 每日签到...")
        try:
            r = client.daily_sign()
            log.info("   ✅ 签到成功  💧+%s  🌿+%s  %s" % (r.get("water", 0), r.get("manure", 0), r.get("tips", "")))
        except RuntimeError as e:
            log.warning("   ⚠️  签到失败: %s" % e)
        # ── 每日分享 ──
        log.info("📤 每日分享...")
        for i in range(3):
            try:
                r = client.daily_share()
                w, m = r.get("water", 0), r.get("manure", 0)
                if not r.get("isTodayFirstShare") and w == 0 and m == 0:
                    log.info("   ℹ️  分享已达上限"); break
                log.info("   ✅ 第%d次分享  💧+%s  🌿+%s" % (i + 1, w, m))
                time.sleep(1)
            except RuntimeError as e:
                log.warning("   ⚠️  分享失败: %s" % e); break
    else:
        log.info("ℹ️  签到/分享今日已完成，跳过")

    # ── 地块处理 ──
    log.info("🌱 查看地块...")
    plots = client.get_sorghum_list() or []
    active = [p for p in plots if p.get("status", -1) != -1]
    log.info("   共 %d 块地，已解锁 %d 块" % (len(plots), len(active)))

    # 开垦新土地
    try:
        ss = len(active) + 1
        log.info("   🔨 尝试开垦第 %d 块田地..." % ss)
        client.extend({"serial_number": ss})
        log.info("   ✅ 开垦新地块成功！")
    except RuntimeError as e:
        if "4041" in str(e): log.warning("   ⚠️  开垦失败：收酒数量不足")
        else: log.warning("   ⚠️  开垦失败：%s" % e)
    except Exception as e:
        log.warning("   ⚠️  开垦异常：%s" % e)

    seed_type = decide_seed_type(
        sorghum=int(info.get("sorghum") or 0), wheat=int(info.get("wheat") or 0),
        wine_yeast=int(info.get("wine_yeast") or 0), active_plots=len(active),
    )
    log.info("   🌾 种植策略: %s（酒曲 %s 块，已解锁 %d 块地）" % (CROP_TYPE.get(seed_type), info.get("wine_yest"), len(active)))

    water = int(info.get("water") or 0); manure = int(info.get("manure") or 0)
    for plot in plots:
        pid = plot.get("id"); status = plot.get("status", -1)
        if status == -1 or not pid: continue
        crop = CROP_TYPE.get(plot.get("type", 1), "作物")
        sn = plot.get("serial_number", "?"); ct = plot.get("crop_time", "")
        wn, mn = plot.get("water_num", 0), plot.get("manure_num", 0)
        # 精准浇水:仅当仍有水滴、且地块距成熟仍超过有效窗口(浇水有意义)时浇;临近成熟不浇以节水
        rem = _plot_remaining(ct)
        allow_water = water > 0 and (rem is None or rem > WATER_EFFECTIVE_SECS)

        # 收获分支
        if (status in (10, 11) and is_ready(ct)) or (status == 2 and is_ready(ct)):
            log.info("   🌾 地块 %s（%s）[可收获] → 开始收获..." % (sn, crop))
            plot_summary_lines.append("🌾 地块%s(%s): 已收获并重新播种" % (sn, crop))
            harvested = False
            for attempt in range(27):
                try:
                    r = client.harvest({"id": pid}); got = int(r.get("volumn") or r.get("sorghum") or r.get("wheat") or 0)
                    log.info("      ✅ 收获成功：+%s 斤" % got if got > 0 else "      ✅ 收获成功（0斤）")
                    harvested = True; break
                except RuntimeError as e:
                    err_str = str(e)
                    if attempt < 26 and ("未成熟" in err_str or "not mature" in err_str.lower() or "时间" in err_str):
                        log.info("      ⏳ 未成熟，5秒后重试（%d/26）..." % (attempt + 1)); time.sleep(5)
                    else:
                        log.warning("      ❌ 收获失败：%s" % e); break
            time.sleep(1)
            if harvested:
                log.info("      🌱 自动播种：%s" % CROP_TYPE.get(seed_type))
                try:
                    client.seeds({"id": pid, "type": seed_type}); log.info("      ✅ 播种成功"); time.sleep(1)
                    allow_water = water > 0  # 重新播种后为新苗,距成熟远,必浇
                    if allow_water and water > 0:
                        try: client.watering({"id": pid}); log.info("      💧 浇水成功"); water -= 1
                        except RuntimeError as e: log.warning("      ⚠️  浇水失败：%s" % e)
                        time.sleep(1)
                    elif not allow_water: log.info("      💧 临近成熟,跳过浇水以节水")
                    else: log.info("      💧 水滴不足，跳过浇水")
                    if manure > 0:
                        try: client.manuring({"id": pid}); log.info("      🌿 施肥成功"); manure -= 1
                        except RuntimeError as e: log.warning("      ⚠️  施肥失败：%s" % e)
                except RuntimeError as e: log.warning("      ❌ 播种失败：%s" % e)
                time.sleep(1)
        elif status in (10, 11, 2) and not is_ready(ct):
            try: remaining_secs = max(0, int((datetime.strptime(ct, "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds())) if ct else 999
            except Exception: remaining_secs = 999
            if min_harvest_secs is None or remaining_secs < min_harvest_secs: min_harvest_secs = remaining_secs
            if remaining_secs <= 120 and remaining_secs > 0:
                log.info("   ⏳ 地块 %s（%s）[即将成熟] 剩余 %d 秒，等待后收获..." % (sn, crop, remaining_secs))
                time.sleep(remaining_secs + 2)
                try:
                    r = client.harvest({"id": pid}); got = int(r.get("volumn") or r.get("sorghum") or r.get("wheat") or 0)
                    log.info("      ✅ 等待后收获成功：+%s 斤" % got)
                    plot_summary_lines.append("🌾 地块%s(%s): 等待后收获+%s斤并重新播种" % (sn, crop, got)); time.sleep(1)
                    client.seeds({"id": pid, "type": seed_type}); log.info("      ✅ 播种成功"); time.sleep(1)
                    allow_water = water > 0  # 重新播种后为新苗,距成熟远,必浇
                    if allow_water and water > 0:
                        try: client.watering({"id": pid}); log.info("      💧 浇水成功"); water -= 1
                        except RuntimeError as e: log.warning("      ⚠️  浇水失败：%s" % e)
                    elif not allow_water: log.info("      💧 临近成熟,跳过浇水以节水")
                    if manure > 0:
                        try: client.manuring({"id": pid}); log.info("      🌿 施肥成功"); manure -= 1
                        except RuntimeError as e: log.warning("      ⚠️  施肥失败：%s" % e)
                except RuntimeError as e: log.warning("      ❌ 等待后收获失败：%s" % e)
                time.sleep(1); continue
            log.info("   🌱 地块 %s（%s）[生长中]  剩余: %s  💧已浇 %s次  🌿已施 %s次" % (sn, crop, fmt_remaining(ct), wn, mn))
            plot_summary_lines.append("🌱 地块%s(%s): 还需 %s" % (sn, crop, fmt_remaining(ct)))
            if allow_water and water > 0:
                try: client.watering({"id": pid}); log.info("      💧 浇水成功"); water -= 1
                except RuntimeError as e: log.warning("      ⚠️  浇水失败：%s" % e)
            elif not allow_water: log.info("      💧 临近成熟,跳过浇水以节水")
            else: log.info("      💧 水滴不足，跳过浇水")
            time.sleep(1)
            if manure > 0:
                try: client.manuring({"id": pid}); log.info("      🌿 施肥成功"); manure -= 1
                except RuntimeError as e: log.warning("      ⚠️  施肥失败：%s" % e)
            else: log.info("      🌿 肥料不足，跳过施肥")
            time.sleep(1)
        elif status == 0:
            log.info("   🟫 地块 %s [空地] → 播种 %s" % (sn, CROP_TYPE.get(seed_type)))
            plot_summary_lines.append("🟫 地块%s: 空地已播种%s" % (sn, CROP_TYPE.get(seed_type)))
            try:
                client.seeds({"id": pid, "type": seed_type}); log.info("      ✅ 播种成功"); time.sleep(1)
                if allow_water and water > 0:
                    try: client.watering({"id": pid}); log.info("      💧 浇水成功"); water -= 1
                    except RuntimeError as e: log.warning("      ⚠️  浇水失败：%s" % e)
                elif not allow_water: log.info("      💧 临近成熟,跳过浇水以节水")
                else: log.info("      💧 水滴不足，跳过浇水")
                time.sleep(1)
                if manure > 0:
                    try: client.manuring({"id": pid}); log.info("      🌿 施肥成功"); manure -= 1
                    except RuntimeError as e: log.warning("      ⚠️  施肥失败：%s" % e)
                else: log.info("      🌿 肥料不足，跳过施肥")
            except RuntimeError as e: log.warning("      ❌ 播种失败：%s" % e)
            time.sleep(1)
        else:
            log.info("   ❓ 地块 %s（%s）[%s]" % (sn, crop, PLOT_STATUS.get(status, "状态%s" % status)))
            plot_summary_lines.append("❓ 地块%s(%s): %s" % (sn, crop, PLOT_STATUS.get(status, "状态%s" % status)))

    # ── 酿酒总开关判断 ──
    if not _AUTO_WINE:
        now = datetime.now(); last_day = calendar.monthrange(now.year, now.month)[1]
        if os.environ.get("GARDEN_AUTO_WINE", "1") == "0":
            log.info("🍶 自动酿酒已关闭（环境变量强制关闭）")
        elif now.day == last_day:
            if now.hour < 20:
                secs = int((now.replace(hour=20, minute=0, second=0, microsecond=0) - now).total_seconds())
                log.info("🍶 自动酿酒已关闭（月末封存期）⏰ 今天 20:00 开启，还需 %s" % fmt_remaining_from_seconds(secs))
            else:
                log.info("🍶 自动酿酒已关闭，跳过酒坛、制曲、投粮")
        else:
            next_month_last = calendar.monthrange(now.year, now.month)[1]
            unlock_dt = now.replace(day=next_month_last, hour=20, minute=0, second=0, microsecond=0)
            secs = int((unlock_dt - now).total_seconds())
            log.info("🍶 自动酿酒已关闭（月末封存期 %d号~%d日）⏰ %d月%d日 20:00 开启，还需 %s" % (
                25, next_month_last, now.month, next_month_last, fmt_remaining_from_seconds(secs)))
    else:
        # ── 酒坛处理 ──
        log.info("🍶 查看酒坛...")
        wines = client.wine_list() or []
        info = client.member_info() or info
        sorghum = int(info.get("sorghum") or 0); wheat = int(info.get("wheat") or 0)
        wine_yeast = int(info.get("wine_yeast") or 0); wine_vol = int(info.get("wine") or 0)
        log.info("   共 %d 个酒坛  │  🌾高粱: %s斤  🌾小麦: %s斤  🍺酒曲: %s块  🍶酒: %sL" % (len(wines), sorghum, wheat, wine_yeast, wine_vol))
        if not wines:
            can_put = min((sorghum // 200) * 200, 5000, wine_yeast * 200)
            if can_put >= 200:
                log.info("   📭 无酒坛 → 制酒 %s 斤高粱（消耗酒曲 %s 块）" % (can_put, can_put // 200))
                try: r = client.discharge_grain({"volumn": can_put}); log.info("      ✅ 制酒成功: %s" % r); sorghum -= can_put; wine_yeast -= can_put // 200
                except RuntimeError as e: log.warning("      ❌ 制酒失败：%s" % e)
                time.sleep(1)
            elif sorghum < 200: log.info("   📭 无酒坛，高粱不足（有 %s 斤）" % sorghum)
            else: log.info("   📭 无酒坛，酒曲不足（有 %s 块）" % wine_yeast)
        for wine in wines:
            wid = wine.get("id"); wst = wine.get("status"); vol = int(wine.get("volumn") or 0)
            cur = int(wine.get("crrent_volumn") or 0); ct = wine.get("crop_time", "")
            if wst in (2, 4) and vol > 0:
                log.info("   🍶 酒坛 %s [已酿好 %sL] → 收获" % (wid, vol))
                try:
                    r = client.harvest_wine({"id": wid}); got = r.get("wine") or r.get("volumn") or 0
                    try: session_brewed_l += float(got)
                    except (TypeError, ValueError): pass
                    log.info("      ✅ 收获成功%s" % ("：+%sL" % got if got else ""))
                    info = client.member_info() or info; sorghum = int(info.get("sorghum") or 0)
                    wine_vol = int(info.get("wine") or 0); wine_yeast = int(info.get("wine_yeast") or 0)
                except RuntimeError as e: log.warning("      ❌ 收获失败：%s" % e); time.sleep(1); continue
                time.sleep(1); can_put = min((sorghum // 200) * 200, 5000, wine_yeast * 200)
                if can_put >= 200:
                    log.info("      🌾 立即投粮：%s 斤高粱（消耗酒曲 %s 块）" % (can_put, can_put // 200))
                    try: r = client.discharge_grain({"volumn": can_put}); log.info("      ✅ 投粮成功: %s" % r); sorghum -= can_put; wine_yeast -= can_put // 200
                    except RuntimeError as e: log.warning("      ❌ 投粮失败：%s" % e)
                    time.sleep(1)
                else:
                    if sorghum < 200: log.info("      ⚠️  高粱不足（有 %s 斤），跳过投粮" % sorghum)
                    else: log.info("      ⚠️  酒曲不足（有 %s 块），跳过投粮" % wine_yeast)
            elif wst == 3:
                if is_ready(ct):
                    log.info("   🍶 酒坛 %s [酿造完成 %sL] → 收获" % (wid, vol))
                    try:
                        r = client.harvest_wine({"id": wid}); got = r.get("wine") or r.get("volumn") or 0
                        try: session_brewed_l += float(got)
                        except (TypeError, ValueError): pass
                        log.info("      ✅ 收获成功%s" % ("：+%sL" % got if got else ""))
                        info = client.member_info() or info; sorghum = int(info.get("sorghum") or 0)
                        wine_vol = int(info.get("wine") or 0); wine_yeast = int(info.get("wine_yeast") or 0)
                    except RuntimeError as e: log.warning("      ❌ 收获失败：%s" % e); time.sleep(1); continue
                    time.sleep(1); can_put = min((sorghum // 200) * 200, 5000, wine_yeast * 200)
                    if can_put >= 200:
                        log.info("      🌾 立即投粮：%s 斤高粱（消耗酒曲 %s 块）" % (can_put, can_put // 200))
                        try: r = client.discharge_grain({"volumn": can_put}); log.info("      ✅ 投粮成功: %s" % r); sorghum -= can_put; wine_yeast -= can_put // 200
                        except RuntimeError as e: log.warning("      ❌ 投粮失败：%s" % e)
                        time.sleep(1)
                    else:
                        if sorghum < 200: log.info("      ⚠️  高粱不足（有 %s 斤），跳过投粮" % sorghum)
                        else: log.info("      ⚠️  酒曲不足（有 %s 块），跳过投粮" % wine_yeast)
                else:
                    try:
                        wine_remaining = max(0, int((datetime.strptime(ct, "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds()))
                        if min_harvest_secs is None or wine_remaining < min_harvest_secs: min_harvest_secs = wine_remaining
                        log.info("   🍶 酒坛 %s [酿造中 %sL]  剩余: %s" % (wid, vol, fmt_remaining_from_seconds(wine_remaining)))
                        wine_summary_lines.append("🍶 酒坛%s(%sL): 酿造中，还需 %s" % (wid, vol, fmt_remaining_from_seconds(wine_remaining)))
                    except Exception: log.info("   🍶 酒坛 %s [酿造中 %sL]  剩余: 未知" % (wid, vol)); wine_summary_lines.append("🍶 酒坛%s(%sL): 酿造中" % (wid, vol))
            elif wst in (0, 1) or (wst == 4 and vol == 0):
                max_by_sorghum = (min(sorghum, 5000) // 200) * 200; max_by_yeast = wine_yeast * 200
                can_put = min(max_by_sorghum, max_by_yeast)
                if can_put >= 200:
                    log.info("   🍶 酒坛 %s [空坛] → 投粮 %s 斤高粱（消耗酒曲 %s 块）" % (wid, can_put, can_put // 200))
                    try: r = client.discharge_grain({"id": wid, "volumn": can_put}); log.info("      ✅ 投粮成功: %s" % r); sorghum -= can_put; wine_yeast -= can_put // 200
                    except RuntimeError as e: log.warning("      ❌ 投粮失败：%s" % e)
                    time.sleep(1)
                else:
                    if sorghum < 200: log.info("   🍶 酒坛 %s [空坛]  ⚠️  高粱不足（有 %s 斤）" % (wid, sorghum))
                    else: log.info("   🍶 酒坛 %s [空坛]  ⚠️  酒曲不足（有 %s 块）" % (wid, wine_yeast))
            else: log.info("   🍶 酒坛 %s [状态: %s]" % (wid, wst))

        # ── 制曲 ──
        wheat = int((client.member_info() or info).get("wheat") or 0)
        if wheat >= 100:
            put_wheat = min((wheat // 100) * 100, 1000)
            log.info("🍺 制曲：%s 斤小麦 → 预计 +%s 块酒曲" % (put_wheat, put_wheat // 100 * 10))
            try:
                r = client.make_yeast({"volumn": put_wheat}); log.info("   ✅ 制曲成功: %s" % r)
                info2 = client.member_info() or {}; sorghum2 = int(info2.get("sorghum") or 0); wine_yeast2 = int(info2.get("wine_yeast") or 0)
                can_put = min((sorghum2 // 200) * 200, 5000, wine_yeast2 * 200)
                if can_put >= 200:
                    log.info("   🌾 制曲后投粮：%s 斤高粱（消耗酒曲 %s 块）" % (can_put, can_put // 200))
                    try: r2 = client.discharge_grain({"volumn": can_put}); log.info("      ✅ 投粮成功: %s" % r2)
                    except RuntimeError as e: log.warning("      ❌ 投粮失败：%s" % e)
                    time.sleep(1)
            except RuntimeError as e: log.warning("   ❌ 制曲失败：%s" % e)
            time.sleep(1)
        elif wheat > 0: log.info("🍺 小麦 %s 斤不足 100 斤，跳过制曲" % wheat)

    # ── 酒兑换积分 ──
    wine_vol = int((client.member_info() or info).get("wine") or 0)
    if wine_vol >= 1:
        if _AUTO_EXCHANGE:
            log.info("💰 酒兑换积分：%sL → +%s 积分" % (wine_vol, wine_vol))
            try: r = client.exchange_wine(wine_vol); log.info("   ✅ 兑换成功: %s" % r)
            except RuntimeError as e: log.warning("   ❌ 兑换失败：%s" % e)
            time.sleep(1)
        else: log.info("💰 酒 %sL 未兑换（自动兑换已关闭，设置 GARDEN_AUTO_EXCHANGE=1 开启）" % wine_vol)

    # ── 答题 ──
    if do_daily:
        log.info("📝 花园答题...")
        try:
            questions = client.get_question_task() or []; todo = [q for q in questions if q.get("id") and q.get("answer")]
            log.info("   共 %d 道题，待答 %d 道" % (len(questions), len(todo)))
            for q in todo:
                qid, answer = q.get("id"), q.get("answer", ""); log.info("   ❓ [%s] %s  →  %s" % (qid, q.get("title", "")[:25], answer))
                try: time.sleep(3); r = client.answer_results(qid, answer); log.info("      ✅ 答题成功: %s" % r)
                except RuntimeError as e: log.warning("      ❌ 答题失败：%s" % e)
                time.sleep(1)
        except RuntimeError as e: log.warning("   ❌ 获取题目失败：%s" % e)

    # ── 抽奖 ──
    if do_daily:
        log.info("🎰 检查抽奖...")
        try:
            chance = client.remain_free_draw_chance(); free_count = int((chance or {}).get("remainFreeDrawChance", 0))
            log.info("   剩余免费次数: %d" % free_count)
            for i in range(free_count):
                try: r = client.draw(); prize = r.get("prize_name") or r.get("name") or r.get("prize") or str(r); log.info("   🎁 第 %d 次：%s" % (i + 1, prize))
                except RuntimeError as e: log.warning("   ❌ 抽奖失败：%s" % e); break
                time.sleep(2)
        except RuntimeError as e: log.warning("   ❌ 抽奖异常：%s" % e)

    # ── 刷新统计 ──
    try:
        fresh_plots = client.get_sorghum_list() or []; min_harvest_secs = None
        for p in fresh_plots:
            st = p.get("status", -1); ct = p.get("crop_time", "")
            if st in (-1, 0, 10, 11): continue
            if ct:
                try:
                    remaining = max(0, int((datetime.strptime(ct, "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds()))
                    if min_harvest_secs is None or remaining < min_harvest_secs: min_harvest_secs = remaining
                except Exception: pass
            elif st == 1:
                fallback = 3600
                if min_harvest_secs is None or fallback < min_harvest_secs: min_harvest_secs = fallback
        try:
            fresh_wines = client.wine_list() or []
            for w in fresh_wines:
                if w.get("status") == 3:
                    wct = w.get("crop_time", "")
                    if wct:
                        try:
                            w_remaining = max(0, int((datetime.strptime(wct, "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds()))
                            if min_harvest_secs is None or w_remaining < min_harvest_secs: min_harvest_secs = w_remaining
                        except Exception: pass
        except Exception: pass
        if min_harvest_secs is not None: log.info("⏱️  下次最早可操作时间: %s" % fmt_remaining_from_seconds(min_harvest_secs))
    except Exception as e: log.warning("⚠️  重新获取地块状态失败: %s" % e)

    # ── 任务汇总 ──
    try:
        info = client.member_info()
        summary = "积分: %s  💧水: %s  🌾高粱: %s斤  🍺酒曲: %s块  🍶酒: %sL" % (
            info.get("integration"), info.get("water"), info.get("sorghum"), info.get("wine_yeast"), info.get("wine"))
        log.info("✅ 任务完成 │ " + summary)
        if plot_summary_lines: summary += "\n\n📋 地块状态:\n" + "\n".join(plot_summary_lines)
        if wine_summary_lines: summary += "\n\n🍶 酒坛状态:\n" + "\n".join(wine_summary_lines)
        # 本月酿酒累计(跨账号合并,始终展示,无论本次是否收获)
        mkey, month_total, sess_add = add_monthly_brewed(session_brewed_l)
        mlabel = "%d月" % datetime.now().month
        if MONTH_BASE_L > 0:
            summary += "\n\n📅 %s酿酒共计 %.2f L（起点 %.2f + 累计 %.2f）" % (
                mlabel, month_total, MONTH_BASE_L, month_total - MONTH_BASE_L)
            log.info("📅 %s酿酒共计 %.2f L（起点 %.2f + 累计 %.2f）" % (
                mlabel, month_total, MONTH_BASE_L, month_total - MONTH_BASE_L))
        else:
            summary += "\n\n📅 %s酿酒共计 %.2f L（本次 +%.2f L）" % (mlabel, month_total, sess_add)
            log.info("📅 %s酿酒共计 %.2f L（本次 +%.2f L）" % (mlabel, month_total, sess_add))
        return summary, min_harvest_secs, session_brewed_l
    except Exception:
        log.info("✅ 今日任务完成")
        if plot_summary_lines: result = "今日任务完成\n\n📋 地块状态:\n" + "\n".join(plot_summary_lines)
        else: result = "今日任务完成"
        if wine_summary_lines: result += "\n\n🍶 酒坛状态:\n" + "\n".join(wine_summary_lines)
        return result, min_harvest_secs, session_brewed_l


# ============================================================
#  青龙面板 cron 更新
# ============================================================
def update_ql_cron_time(schedule):
    import http.client; import urllib.parse
    # 青龙面板连接信息全部走环境变量，避免把私人面板地址/密码写死在代码里。
    # 未配置这些变量时自动跳过（不影响脚本主任务）。
    #   QL_HOST        青龙面板地址，如 http://192.168.6.222 或 127.0.0.1
    #   QL_PORT        端口，默认 5700
    #   QL_CLIENT_ID / QL_CLIENT_SECRET  Application 的 client_id / client_secret（推荐）
    #   QL_USERNAME / QL_PASSWORD        面板账号密码（老式登录兜底，二选一）
    host = (os.environ.get("QL_HOST") or "").strip()
    if host:
        host = host.replace("http://", "").replace("https://", "").split("/")[0]
        if ":" in host:
            host, p = host.split(":", 1); port = int(p) if p.isdigit() else 5700
        else:
            port = int(os.environ.get("QL_PORT", "5700"))
    else:
        port = int(os.environ.get("QL_PORT", "5700"))
    username = (os.environ.get("QL_USERNAME") or "").strip()
    password = (os.environ.get("QL_PASSWORD") or "").strip()
    client_id = (os.environ.get("QL_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("QL_CLIENT_SECRET") or "").strip()

    if not host or (not (client_id and client_secret) and not (username and password)):
        log.info("ℹ️  未配置青龙面板环境变量(QL_HOST/QL_CLIENT_ID等)，跳过定时任务更新")
        return False

    def _http_json(method, path, payload="", headers=None, timeout=10):
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            send_headers = dict(headers or {}); send_payload = payload
            if isinstance(send_payload, str): send_payload = send_payload.encode("utf-8")
            conn.request(method, path, send_payload, send_headers)
            res = conn.getresponse(); status = int(getattr(res, "status", 0) or 0); text = res.read().decode("utf-8", "replace")
        finally: conn.close()
        try: body = json.loads(text)
        except Exception: body = {}
        return status, text, body

    def _extract_token(resp_obj):
        if not isinstance(resp_obj, dict): return ""
        data = resp_obj.get("data")
        if isinstance(data, dict):
            token = data.get("token") or data.get("access_token")
            if token: return str(token)
        token = resp_obj.get("token") or resp_obj.get("access_token")
        return str(token) if token else ""

    def _extract_task_list(resp_obj):
        if isinstance(resp_obj, list): return resp_obj
        if not isinstance(resp_obj, dict): return []
        data = resp_obj.get("data")
        if isinstance(data, list): return data
        if isinstance(data, dict):
            for key in ("data", "list", "records", "items"):
                rows = data.get(key)
                if isinstance(rows, list): return rows
        for key in ("data", "list", "records", "items"):
            rows = resp_obj.get(key)
            if isinstance(rows, list): return rows
        return []

    def _is_success(status, resp_obj):
        if status not in (200, 201): return False
        if not isinstance(resp_obj, dict): return True
        code = resp_obj.get("code")
        if code is None: return True
        return str(code) in {"0", "200"}

    try:
        log.info("🔑 登录青龙面板获取 token...")
        open_token_path = ("/open/auth/token" + f"?client_id={urllib.parse.quote(str(client_id))}" + f"&client_secret={urllib.parse.quote(str(client_secret))}")
        status, text, token_obj = _http_json("GET", open_token_path, "", {"Content-Type": "application/json"})
        token = _extract_token(token_obj)
        if not token and username and password and "*" not in username and "*" not in password:
            legacy_headers = {"Client-ID": client_id, "Client-Secret": client_secret, "Content-Type": "application/json"}
            status, text, legacy_obj = _http_json("POST", "/api/user/login", json.dumps({"username": username, "password": password}, ensure_ascii=False), legacy_headers)
            if _is_success(status, legacy_obj): token = _extract_token(legacy_obj)
        if not token: log.error("❌ 获取青龙 token 失败: HTTP %s" % status); return False
        log.info("✅ 登录青龙面板成功"); auth_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        log.info("📋 获取青龙面板任务列表...")
        list_paths = ["/open/crons?searchValue=%E4%B9%A0%E9%85%92", "/open/crons", "/api/crons"]; all_tasks = []
        for path in list_paths:
            status, text, result = _http_json("GET", path, "", auth_headers)
            rows = _extract_task_list(result)
            if rows: all_tasks = rows; break
        if not all_tasks: log.error("❌ 获取任务列表失败"); return False
        target_task = None
        for task in all_tasks:
            if not isinstance(task, dict): continue
            name = str(task.get("name") or ""); command = str(task.get("command") or "")
            if name == "习酒" or "习酒" in name or "习酒.py" in command or "xj.py" in command:
                target_task = task; break
        if not target_task: log.warning("❌ 未找到习酒任务"); return False
        task_id = target_task.get("id") or target_task.get("_id")
        if task_id in (None, ""): log.error("❌ 找到任务但缺少 id"); return False
        log.info("✅ 找到习酒任务，ID = %s" % task_id)
        update_payload = {"id": task_id, "name": target_task.get("name", "习酒"), "command": target_task.get("command", ""), "schedule": schedule}
        update_path_main = "/open/crons"; attempts = [
            (update_path_main, update_payload), (update_path_main, [update_payload]),
            ("/open/crons", update_payload), ("/open/crons", [update_payload]),
            ("/api/crons", update_payload), ("/api/crons", [update_payload]),
        ]
        for path, body in attempts:
            status, text, resp_obj = _http_json("PUT", path, json.dumps(body, ensure_ascii=False), auth_headers)
            if _is_success(status, resp_obj): log.info("✅ 青龙面板定时任务更新成功 ⏰ 新执行时间：%s" % schedule); return True
        log.error("❌ 更新任务接口全部尝试失败"); return False
    except Exception as e: log.error("❌ 更新青龙定时任务失败: %s" % e); return False


# ============================================================
#  带自动重试的登录封装
# ============================================================
def auto_login_with_retry(client, wxid, wx_server, ocr_server=None,
                          max_retry=None, base_delay=5):
    """
    自动重试登录：对所有错误（含 login_buffer 已过期 / 数据不存在 / 需要重新扫码等）
    一律硬重试 max_retry 次，采用指数退避 + 随机抖动。即使明知是需重新扫码的永久错误，
    也会按设定次数重试后再放弃。
    重试次数可通过环境变量 LOGIN_MAX_RETRY 设置（默认 3）。
    """
    if max_retry is None:
        try:
            max_retry = int(os.environ.get("LOGIN_MAX_RETRY", "3"))
        except Exception:
            max_retry = 3
    max_retry = max(1, max_retry)

    last_err = None
    for attempt in range(1, max_retry + 1):
        try:
            result = client.auto_login(wxid=wxid, server_url=wx_server, ocr_server=ocr_server or None)
            if result and result.get("token"):
                if attempt > 1:
                    log.info("   ✅ 第 %d 次重试登录成功" % attempt)
                return result
            # 没抛异常但也没拿到 token，视为异常进行重试
            last_err = RuntimeError("登录未返回 token，请稍后重试")
            log.warning("   ⚠️  登录未返回 token（%d/%d），%ds 后重试..." % (attempt, max_retry, base_delay * attempt))
        except Exception as e:
            last_err = e
            log.warning("   ⚠️  登录失败（%d/%d）: %s，%ds 后重试..." % (attempt, max_retry, e, base_delay * attempt))
        if attempt < max_retry:
            time.sleep(base_delay * attempt + random.randint(0, 3))
    log.error("   ❌ 登录重试 %d 次仍失败" % max_retry)
    raise last_err if last_err else RuntimeError("登录失败")


# ============================================================
#  主函数
# ============================================================
if __name__ == "__main__":
    WX_SERVER = os.environ.get("WECHAT_SERVER", DEFAULT_WECHAT_SERVER)
    WX_ID_RAW = (os.getenv("WX_ID") or os.getenv("WXIDXJ", "")).strip()

    accounts = parse_accounts(WX_ID_RAW)
    if not accounts:
        accounts = parse_yyb_server_accounts(os.getenv("YYB_SERVER", ""))
        if accounts:
            print("ℹ️ 未配置 WX_ID/WXIDXJ，已从 YYB_SERVER 读取 %d 个账号" % len(accounts))
    if not accounts:
        print("❌ 未找到账号，请设置 WX_ID、WXIDXJ 或 YYB_SERVER")
        sys.exit(1)

    CACHE_FILE = Path(__file__).parent / "xijiutoken.json"

    def load_cache():
        try: return json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
        except Exception: return {}

    def save_cache(c):
        try: CACHE_FILE.write_text(json.dumps(c, ensure_ascii=False, indent=2))
        except Exception: pass

    def token_valid(token):
        try:
            p = token.split(".")[1]; p += "=" * (4 - len(p) % 4)
            return json.loads(base64.b64decode(p).decode()).get("expireTime", 0) > time.time() + 300
        except Exception: return False

    cache = load_cache()
    notify_lines = []
    all_min_harvests = []

    log.info(f"🔔 习酒花园, 开始! 共 {len(accounts)} 个账号")

    for i, acc in enumerate(accounts):
        wxid = acc["id"]; remark = acc.get("note") or wxid
        mask = (remark[:3] + "*****" + remark[-3:]) if len(remark) >= 7 else remark
        log.info("─" * 50); log.info("👤 [%d/%d] 账号: %s" % (i+1, len(accounts), mask))

        client = GardenClient(ocr_server=OCR_SERVER or None)
        cached_token = cache.get(wxid, "")

        if cached_token and token_valid(cached_token):
            log.info("   🔑 使用缓存 token"); client.set_token(cached_token)
            wx = WxAdapter(WX_SERVER)
            try:
                enc = wx.get_user_encrypt_key(wxid, APPID)
                if enc.get("success"):
                    client.set_crypto(enc["encrypt_key"], enc["iv"], version=enc.get("version", 3))
                    log.info("   🔐 加密密钥已获取  version=%s" % enc.get("version"))
                else: cached_token = ""
            except Exception as e: log.warning("   ⚠️  获取加密密钥异常: %s" % e); cached_token = ""

        if not cached_token or not token_valid(cached_token):
            log.info("   🔄 token 无效或已过期，重新登录...")
            try:
                result = auto_login_with_retry(client, wxid, WX_SERVER, OCR_SERVER, base_delay=5)
            except Exception as e:
                log.error("   ❌ 登录异常: %s，跳过" % e); notify_lines.append("👤 %s\n❌ 登录失败: %s" % (mask, e)); continue

            log.info("   🔑 登录结果: token=%s  加密=%s" % (
                "✅ 已获取" if result.get("token") else "❌ 失败",
                "✅ 就绪" if result.get("crypto_ready") else "❌ 未就绪"))

            if not result.get("token"): log.error("   ❌ 登录失败，跳过"); continue
            cache[wxid] = client.token; save_cache(cache)

        if not client.crypto: log.error("   ❌ 加密未就绪，跳过"); continue

        try:
            today = datetime.now().strftime("%Y-%m-%d"); do_daily = cache.get(wxid + "_daily") != today
            summary, min_harvest, _brewed = run(client, do_daily=do_daily)
            notify_lines.append("👤 %s\n%s" % (mask, summary))
            if do_daily: cache[wxid + "_daily"] = today; save_cache(cache)
            if min_harvest is not None: all_min_harvests.append((remark, min_harvest))
        except (Exception, TokenInvalidError) as e:
            msg = str(e)
            # 缓存 token 失效的共性表现：[5001] 加密校验失败、[4012] 非法的用户 token 参数等。
            # 直接清空该账号缓存 token 并当场重新登录重试，无需手动执行清理脚本。
            TOKEN_INVALID = ("5001" in msg or "加密校验失败" in msg
                             or "4012" in msg or "非法的用户 token" in msg
                             or "token" in msg.lower() and ("失效" in msg or "非法" in msg or "无效" in msg or "过期" in msg)
                             or isinstance(e, TokenInvalidError))
            if TOKEN_INVALID and cache.get(wxid):
                cache.pop(wxid, None); save_cache(cache)
                log.warning("   ⚠️  检测到 token 失效(%s)，立即清除缓存 token 并重新登录重试..." % msg.split("]")[0].strip("["))
                try:
                    result = auto_login_with_retry(client, wxid, WX_SERVER, OCR_SERVER, base_delay=5)
                    if result.get("token"):
                        cache[wxid] = client.token; save_cache(cache)
                        today = datetime.now().strftime("%Y-%m-%d"); do_daily = cache.get(wxid + "_daily") != today
                        summary, min_harvest, _brewed = run(client, do_daily=do_daily)
                        notify_lines.append("👤 %s\n%s" % (mask, summary))
                        if do_daily: cache[wxid + "_daily"] = today; save_cache(cache)
                        if min_harvest is not None: all_min_harvests.append((remark, min_harvest))
                        log.info("   ✅ 重新登录重试成功")
                    else:
                        log.error("   ❌ 重试登录仍未返回 token")
                        notify_lines.append("👤 %s\n❌ 执行异常: %s" % (mask, e))
                except (Exception, TokenInvalidError) as e2:
                    log.error("   ❌ 重试异常: %s" % e2, exc_info=True)
                    notify_lines.append("👤 %s\n❌ 执行异常: %s" % (mask, e))
            else:
                log.error("   ❌ 执行异常: %s" % e, exc_info=True)
                notify_lines.append("👤 %s\n❌ 执行异常: %s" % (mask, e))
        time.sleep(random.randint(2, 5))

    if notify_lines:
        content = "作者：\n\n" + "\n\n".join(notify_lines)
        # 全账号本月酿酒合计(一行汇总)
        try:
            _mdata = load_monthly(); _mkey = datetime.now().strftime("%Y-%m")
            if _mkey in _mdata or MONTH_BASE_L > 0:
                brewed = _mdata.get(_mkey, 0)
                if MONTH_BASE_L > 0:
                    content += "\n\n📅 %d月全账号酿酒共计 %.2f L（起点 %.2f + 累计收获 %.2f）" % (
                        datetime.now().month, MONTH_BASE_L + brewed, MONTH_BASE_L, brewed)
                else:
                    content += "\n\n📅 %d月全账号酿酒共计 %.2f L" % (datetime.now().month, brewed)
        except Exception:
            pass
        send_notify("习酒花园", content)

    # ── 计算下次执行时间 ──
    log.info("═" * 50)
    if all_min_harvests:
        overall_min_secs = min(harvest for _, harvest in all_min_harvests)
        log.info("📊 各账号最短剩余成熟时间:")
        for remark, secs in sorted(all_min_harvests, key=lambda x: x[1]):
            next_time = datetime.now() + timedelta(seconds=secs)
            log.info("   👤 %-12s  %s  （预计 %s 成熟）" % (remark, fmt_remaining_from_seconds(secs), next_time.strftime("%H:%M:%S")))
        next_run_secs = overall_min_secs + 90
        next_run_time = datetime.now() + timedelta(seconds=next_run_secs)
        cron_schedule = "%d %d %d %d %d *" % (next_run_time.second, next_run_time.minute, next_run_time.hour, next_run_time.day, next_run_time.month)
        log.info("📅 下次执行: %s  （间隔 %s）" % (next_run_time.strftime("%Y-%m-%d %H:%M:%S"), fmt_remaining_from_seconds(next_run_secs)))
        log.info("⏰ cron 表达式: %s" % cron_schedule)
        update_ql_cron_time(cron_schedule)
        print("NEXT_RUN_SECS=%s" % next_run_secs)
    else:
        default_secs = 1800
        next_run_time = datetime.now() + timedelta(seconds=default_secs)
        cron_schedule = "%d %d %d %d %d *" % (next_run_time.second, next_run_time.minute, next_run_time.hour, next_run_time.day, next_run_time.month)
        log.info("⚠️  未获取到地块收获时间，使用默认间隔 %s" % fmt_remaining_from_seconds(default_secs))
        log.info("📅 下次执行: %s" % next_run_time.strftime("%Y-%m-%d %H:%M:%S"))
        update_ql_cron_time(cron_schedule)
        print("NEXT_RUN_SECS=%s" % default_secs)
