#!/usr/bin/env python3
"""
iqoo社区 小程序
cron: 25 10,13 * * *
登录入口：
# name: iqoo社区
  1. 优先读取本地 iqoo_token.json 中缓存 of token
  2. 缓存缺失或不可用时，使用环境变量 WX_ID / IQOO_WXID 自动登录

本地缓存：
  iqoo_token.json

自动登录相关环境变量：

  WX_ID=wxid#备注 (或 IQOO_WXID)
  多账号使用换行或 @ 分隔
 
任务控制：
  IQOO_COMMENT=666
  IQOO_SKIP_SOCIAL=1
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import gzip
import hashlib
import hmac
import importlib
import importlib.util
import inspect
import json
import os
import requests
import getCode
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

try:
    import brotli  # type: ignore
except ImportError:
    brotli = None


SCRIPT_NAME = "iqoo-community"
APP_ID = "1002"
SIGN_SECRET = "2618194b0ebb620055e19cf9811d3c13"
BASE_URL = "https://bbs-api.iqoo.com"
DEFAULT_REFERER = "https://servicewechat.com/wxcf4266fbc9463132/248/page-frame.html"
DEFAULT_VISITOR = "b89d8b0ffa920e96f3cb4c1f69ec2c66"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf254151e) XWEB/17127"
)
DEFAULT_COMMENT = os.getenv("IQOO_COMMENT", "666")
DEFAULT_TIMEOUT_MS = 15000
TOKEN_CACHE_PATH = Path(__file__).with_name("iqoo_token.json")
SOCIAL_DISABLED = str(os.getenv("IQOO_SKIP_SOCIAL", "")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ACCEPT_ENCODING = "gzip, deflate, br" if brotli is not None else "gzip, deflate"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def read_env(name: str, default_value: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default_value
    return str(raw)


def read_positive_int_env(name: str, default_value: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default_value

    try:
        value = int(str(raw), 10)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be a positive integer, got {raw}"
        ) from exc

    if value <= 0:
        raise ValueError(f"Environment variable {name} must be a positive integer, got {raw}")
    return value


LOGIN_CONFIG = {
    "localProxy": read_env("WECHAT_SERVER", "http://192.168.1.179:8011"),
    "wxAppid": "wxcf4266fbc9463132",
    "step1Url": read_env("IQOO_STEP1_URL", "https://bbs-api.iqoo.com/api/v3/users/vivo/mini"),
    "step2Url": read_env(
        "IQOO_STEP2_URL",
        "https://bbs-api.iqoo.com/api/v3/users/vivo/mini/bind",
    ),
    "signSecret": read_env("IQOO_SIGN_SECRET", SIGN_SECRET),
    "signAppId": read_env("IQOO_SIGN_APP_ID", APP_ID),
    "visitor": read_env("IQOO_X_VISITOR", DEFAULT_VISITOR),
    "referer": read_env("IQOO_REFERER", DEFAULT_REFERER),
    "userAgent": read_env("IQOO_USER_AGENT", DEFAULT_USER_AGENT),
    "bindFrom": read_positive_int_env("IQOO_BIND_FROM", 46),
    "requestTimeoutMs": DEFAULT_TIMEOUT_MS,
}

LogFunc = Callable[[str], None]


def _iter_notify_paths() -> list[Path]:
    script_path = Path(__file__).resolve()
    candidates: list[Path] = []

    for parent in [script_path.parent, *script_path.parents]:
        candidates.append(parent / "notify.py")
        candidates.append(parent / "sendNotify.py")

    ql_dir = str(os.getenv("QL_DIR", "")).strip()
    if ql_dir:
        ql_path = Path(ql_dir)
        candidates.extend(
            [
                ql_path / "notify.py",
                ql_path / "scripts" / "notify.py",
                ql_path / "data" / "scripts" / "notify.py",
                ql_path / "scripts" / "sendNotify.py",
                ql_path / "data" / "scripts" / "sendNotify.py",
            ]
        )

    seen: set[str] = set()
    unique_paths: list[Path] = []
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_paths.append(candidate)
    return unique_paths


def _load_module_from_path(path: Path) -> Optional[Any]:
    if not path.exists():
        return None

    module_name = f"_iqoo_notify_{hashlib.md5(str(path).encode('utf-8')).hexdigest()[:8]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pick_notify_sender(module: Any) -> Optional[Callable[..., Any]]:
    for attr in ("send", "send_notify", "sendNotify"):
        sender = getattr(module, attr, None)
        if callable(sender):
            return sender
    return None


def load_notify_sender() -> Optional[Callable[..., Any]]:
    for path in _iter_notify_paths():
        try:
            module = _load_module_from_path(path)
        except Exception:
            continue
        if module is None:
            continue
        sender = _pick_notify_sender(module)
        if sender is not None:
            return sender

    for module_name in ("notify", "sendNotify"):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        sender = _pick_notify_sender(module)
        if sender is not None:
            return sender
    return None


def invoke_notify_sender(sender: Callable[..., Any], title: str, content: str) -> None:
    result = sender(title, content)
    if inspect.isawaitable(result):
        asyncio.run(result)


class Env:
    def __init__(self, name: str):
        self.name = name
        self.user_idx = 1
        self.notify_lines: list[str] = []
        self.start_time = time.time()
        self.log(f"{self.name} 已启动")

    def log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self.notify_lines.append(line)
        print(line)

    def wait(self, ms: int) -> None:
        time.sleep(ms / 1000)

    def send_msg(self) -> None:
        try:
            sender = load_notify_sender()
            if sender is None:
                return
            invoke_notify_sender(sender, self.name, "\n".join(self.notify_lines))
        except Exception as exc:
            self.log(f"通知发送失败: {exc}")

    def done(self) -> None:
        self.send_msg()
        cost = time.time() - self.start_time
        self.log(f"{self.name} 完成，耗时 {cost:.2f}秒")


_ENV: Optional[Env] = None


def env_instance() -> Env:
    global _ENV
    if _ENV is None:
        _ENV = Env(SCRIPT_NAME)
    return _ENV


def safe_json_parse(text: str) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_wxid_accounts(raw: Any) -> list[Dict[str, str]]:
    text = str(raw or "").replace("\r", "").strip()
    if not text:
        return []

    accounts: list[Dict[str, str]] = []
    for entry in re.split(r"[\n@]+", text):
        chunk = entry.strip()
        if not chunk:
            continue

        wxid, remark = (chunk.split("#", 1) + [""])[:2]
        wxid = wxid.strip()
        remark = remark.strip()
        if not wxid:
            continue

        accounts.append(
            {
                "wxid": wxid,
                "remark": remark or wxid,
            }
        )
    return accounts


def load_wxid_accounts() -> list[Dict[str, str]]:
    return parse_wxid_accounts(os.getenv("WX_ID") or os.getenv("IQOO_WXID", ""))


def normalize_token(raw: Any) -> str:
    text = str(raw or "").strip()
    if text.lower().startswith("bearer "):
        return text[7:].strip()
    return text


def normalize_auth_token(value: Any) -> str:
    return normalize_token(value)


def mask_text(value: Any, keep_start: int = 6, keep_end: int = 4) -> str:
    text = str(value or "")
    if not text:
        return "<empty>"
    if len(text) <= keep_start + keep_end:
        return text
    return f"{text[:keep_start]}...{text[-keep_end:]}"


def preview_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def sanitize_body_for_log(body: Dict[str, Any]) -> str:
    cloned = copy.copy(body)
    if cloned.get("code"):
        cloned["code"] = mask_text(cloned["code"], 6, 6)
    if cloned.get("encryptedData"):
        cloned["encryptedData"] = f"<len:{len(str(cloned['encryptedData']))}>"
    if cloned.get("iv"):
        cloned["iv"] = f"<len:{len(str(cloned['iv']))}>"
    if cloned.get("randomNum"):
        cloned["randomNum"] = mask_text(cloned["randomNum"], 6, 4)
    if cloned.get("authtoken"):
        cloned["authtoken"] = mask_text(cloned["authtoken"], 6, 4)
    return json_dumps(cloned)


def extract_auth_token(data: Any, headers: Optional[Mapping[str, Any]] = None) -> str:
    candidates: list[Any] = []

    if headers:
        for key, value in headers.items():
            if str(key).lower() == "authorization":
                candidates.append(value)

    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("Authorization"),
                data.get("authorization"),
                data.get("accessToken"),
                data.get("access_token"),
                data.get("token"),
            ]
        )

    for candidate in candidates:
        token = normalize_auth_token(candidate)
        if token:
            return token
    return ""


def _decode_base64_text(base64_value: str, *, urlsafe: bool = False) -> str:
    padding = "=" * (-len(base64_value) % 4)
    decoder = base64.urlsafe_b64decode if urlsafe else base64.b64decode
    decoded = decoder((base64_value + padding).encode("utf-8"))
    return decoded.decode("utf-8")


def decode_jwt_payload(token: Any) -> Optional[Dict[str, Any]]:
    try:
        parts = str(token or "").split(".")
        if len(parts) < 2:
            return None
        return json.loads(_decode_base64_text(parts[1], urlsafe=True))
    except Exception:
        return None


def normalize_cached_session(cache: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    normalized = as_dict(cache)
    token = normalize_token(normalized.get("token"))
    if not token:
        return None

    normalized["token"] = token
    normalized["data"] = as_dict(normalized.get("data"))
    return normalized


def load_token_cache(wxid: str, log: Optional[LogFunc] = None) -> Optional[Dict[str, Any]]:
    if not TOKEN_CACHE_PATH.exists():
        if log is not None:
            log(f"未找到本地 token 缓存: {TOKEN_CACHE_PATH.name}")
        return None

    try:
        parsed = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        if log is not None:
            log(f"读取本地 token 缓存失败: {exc}")
        return None

    root = as_dict(parsed)
    accounts = root.get("accounts")

    if isinstance(accounts, list):
        for item in accounts:
            cache = normalize_cached_session(as_dict(item))
            if cache and str(cache.get("wxid") or "").strip() == wxid:
                cache["source"] = "cache"
                return cache

        if log is not None:
            log(f"本地 token 缓存中未找到账号: {wxid}")
        return None

    legacy_cache = normalize_cached_session(root)
    if legacy_cache and len(load_wxid_accounts()) == 1:
        legacy_cache["wxid"] = wxid
        legacy_cache["source"] = "legacy-cache"
        if log is not None:
            log("检测到旧版单账号 token 缓存，已作为当前账号缓存使用")
        return legacy_cache

    if legacy_cache and log is not None:
        log("检测到旧版单账号 token 缓存，但当前为多账号配置，已忽略该缓存")

    if log is not None:
        log("本地 token 缓存格式无效")
    return None


def save_token_cache(
    account: Mapping[str, Any],
    session: Mapping[str, Any],
    log: Optional[LogFunc] = None,
) -> Dict[str, Any]:
    token = normalize_token(session.get("token"))
    if not token:
        raise RuntimeError("无法保存空 token 到本地缓存")

    wxid = str(account.get("wxid") or "").strip()
    if not wxid:
        raise RuntimeError("无法保存缺少 wxid 的 token 缓存")

    remark = str(account.get("remark") or wxid)
    payload = decode_jwt_payload(token) or {}
    cache = {
        "wxid": wxid,
        "remark": remark,
        "token": token,
        "visitor": str(session.get("visitor") or DEFAULT_VISITOR),
        "userAgent": str(session.get("userAgent") or DEFAULT_USER_AGENT),
        "referer": str(session.get("referer") or DEFAULT_REFERER),
        "source": "cache",
        "loginSource": str(session.get("source") or "cache"),
        "savedAt": datetime.now(timezone.utc).isoformat(),
        "data": as_dict(session.get("data")),
    }
    if payload:
        cache["jwtPayload"] = payload
        exp = payload.get("exp")
        if exp is not None:
            try:
                cache["expiresAt"] = datetime.fromtimestamp(float(exp), tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OSError):
                pass

    accounts: list[Dict[str, Any]] = []
    if TOKEN_CACHE_PATH.exists():
        try:
            existing = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
            existing_root = as_dict(existing)
            existing_accounts = existing_root.get("accounts")
            if isinstance(existing_accounts, list):
                for item in existing_accounts:
                    normalized = normalize_cached_session(as_dict(item))
                    if normalized and str(normalized.get("wxid") or "").strip() != wxid:
                        accounts.append(normalized)
            else:
                legacy = normalize_cached_session(existing_root)
                if legacy and str(legacy.get("wxid") or "").strip() not in {"", wxid}:
                    accounts.append(legacy)
        except Exception:
            pass

    accounts.append(cache)
    store = {
        "version": 2,
        "accounts": accounts,
    }
    TOKEN_CACHE_PATH.write_text(json_dumps(store) + "\n", encoding="utf-8")
    if log is not None:
        log(f"已写入本地 token 缓存: {TOKEN_CACHE_PATH.name} ({remark})")
    return cache


def build_query_string(data: Any) -> str:
    if not is_plain_object(data):
        return ""
    chunks = []
    for key, value in data.items():
        encoded_key = urllib.parse.quote(str(key), safe="")
        encoded_value = urllib.parse.quote(str(value), safe="")
        chunks.append(f"{encoded_key}={encoded_value}")
    return "&".join(chunks)


def inflate_body(buffer: bytes, encoding: Any) -> bytes:
    data = buffer if isinstance(buffer, bytes) else bytes(buffer or b"")
    enc = str(encoding or "").lower()
    if not enc:
        return data

    try:
        if "br" in enc and brotli is not None:
            return brotli.decompress(data)
        if "gzip" in enc:
            return gzip.decompress(data)
        if "deflate" in enc:
            try:
                return zlib.decompress(data)
            except zlib.error:
                return zlib.decompress(data, -zlib.MAX_WBITS)
    except Exception:
        return data
    return data


def parse_base64_json(base64_value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(base64_value, str) or not base64_value:
        raise RuntimeError(f"{label} 为空或缺失")

    try:
        decoded_text = _decode_base64_text(base64_value)
    except Exception as exc:
        raise RuntimeError(f"{label} base64 解码失败: {exc}") from exc

    parsed = safe_json_parse(decoded_text)
    if parsed is None:
        raise RuntimeError(f"{label} base64 解码后不是有效 JSON")
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} 解码后不是对象")
    return parsed


def parse_nested_profile(value: Any, label: str) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{label} 为空或缺失")

    json_parsed = safe_json_parse(value)
    if isinstance(json_parsed, dict):
        return json_parsed

    try:
        base64_decoded = _decode_base64_text(value)
    except Exception as exc:
        raise RuntimeError(f"{label} 既不是 JSON 文本也不是 base64 JSON") from exc

    base64_parsed = safe_json_parse(base64_decoded)
    if isinstance(base64_parsed, dict):
        return base64_parsed

    raise RuntimeError(f"{label} 既不是 JSON 文本也不是 base64 JSON")


def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"无效的 URL: {url}")


def validate_login_config() -> None:
    required_keys = [
        "localProxy",
        "wxAppid",
        "step1Url",
        "step2Url",
        "signSecret",
        "signAppId",
        "visitor",
        "referer",
        "userAgent",
    ]

    for key in required_keys:
        if not LOGIN_CONFIG.get(key):
            raise RuntimeError(f"缺少必需的登录配置值: {key}")

    _validate_url(LOGIN_CONFIG["localProxy"])
    _validate_url(LOGIN_CONFIG["step1Url"])
    _validate_url(LOGIN_CONFIG["step2Url"])


def node_request(url: str, init: Dict[str, Any]) -> Dict[str, Any]:
    method = str(init.get("method") or "GET").upper()
    headers = dict(init.get("headers") or {})
    body_text = init.get("body") or ""
    timeout_ms = int(init.get("timeoutMs") or DEFAULT_TIMEOUT_MS)

    body_bytes = body_text.encode("utf-8") if body_text else None
    request = urllib.request.Request(url=url, data=body_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=timeout_ms / 1000) as response:
            raw = response.read()
            decoded = inflate_body(raw, response.headers.get("Content-Encoding"))
            return {
                "status": response.getcode(),
                "headers": dict(response.headers.items()),
                "text": decoded.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        decoded = inflate_body(raw, exc.headers.get("Content-Encoding") if exc.headers else "")
        return {
            "status": exc.code,
            "headers": dict(exc.headers.items()) if exc.headers else {},
            "text": decoded.decode("utf-8", errors="replace"),
        }
    except urllib.error.URLError as exc:
        raise RuntimeError(f"请求失败 {url}: {exc.reason}") from exc


def do_request(url: str, init: Dict[str, Any]) -> Dict[str, Any]:
    return node_request(url, init)


def request_json(url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    opts = options or {}
    response = do_request(
        url,
        {
            "method": opts.get("method") or "POST",
            "headers": opts.get("headers") or {},
            "body": opts.get("body") or "",
            "timeoutMs": opts.get("timeoutMs") or DEFAULT_TIMEOUT_MS,
        },
    )
    parsed = safe_json_parse(response["text"])
    if response["status"] < 200 or response["status"] >= 300:
        raise RuntimeError(f"HTTP {response['status']} 请求 {url} 失败: {preview_text(response['text'])}")
    response["data"] = parsed if parsed is not None else response["text"]
    return response


def get_message(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("Message") or result.get("message") or "未知错误")
    return "未知错误"


def is_success(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return str(result.get("Code", result.get("code", ""))) == "0"


def post_local_proxy(pathname: str, body: Dict[str, Any]) -> Dict[str, Any]:
    base = f"{LOGIN_CONFIG['localProxy'].rstrip('/')}/"
    url = urllib.parse.urljoin(base, pathname.lstrip("/"))
    return request_json(
        url,
        {
            "method": "POST",
            "body": json_dumps(body),
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            "timeoutMs": LOGIN_CONFIG["requestTimeoutMs"],
        },
    )


def build_login_headers(
    path: str,
    body_text: str,
    visitor: str,
    user_agent: str,
    referer: str,
) -> Dict[str, str]:
    timestamp = int(time.time())
    plain = f"POST&{path}&&{body_text}&appid={LOGIN_CONFIG['signAppId']}&timestamp={timestamp}"
    signature = base64.b64encode(
        hmac.new(
            LOGIN_CONFIG["signSecret"].encode("utf-8"),
            plain.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return {
        "Accept": "*/*",
        "Accept-Encoding": ACCEPT_ENCODING,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": "Bearer",
        "Connection": "keep-alive",
        "Content-Nonce": "",
        "Content-Type": "application/json",
        "Referer": referer,
        "SIGN": (
            f"IQOO-HMAC-SHA256 appid={LOGIN_CONFIG['signAppId']},"
            f"timestamp={timestamp},signature={signature}"
        ),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "User-Agent": user_agent,
        "X-Platform": "mini",
        "X-Visitor": visitor,
        "xweb_xhr": "1",
    }


def get_wx_code(wxid: str, log: LogFunc) -> str:
    log(f"自动登录：正在为 {wxid} 请求微信登录码")
    try:
        code = getCode.get_single_code(LOGIN_CONFIG["wxAppid"], wxid)
        log(f"自动登录：登录码={mask_text(code, 6, 6)}")
        return str(code)
    except Exception as e:
        raise RuntimeError(f"getCode 取 code 失败: {e}")


def get_wx_user_info(wxid: str, log: LogFunc) -> Dict[str, Any]:
    log(f"自动登录：正在为 {wxid} 请求微信用户信息")

    raw_id = wxid.split('#')[0].strip()
    is_yyb = raw_id.isdigit() or bool(re.match(r'^o[a-zA-Z0-9_-]{20,}$', raw_id))
    appid = LOGIN_CONFIG["wxAppid"]
    payload = {
        "api_name": "webapi_getuserinfo",
        "data": {
            "lang": "en",
            "version": "3.10.3",
        },
        "from_component": True,
        "operate_directly": False,
        "with_credentials": True,
    }

    if is_yyb:
        inner = getCode.get_single_operate_wx_data(appid, raw_id, payload)
        if not isinstance(inner, dict):
            raise RuntimeError(f"YYB operateWxData 失败: {inner}")

        encrypted_data = inner.get("encryptedData")
        iv = inner.get("iv")
        if not encrypted_data or not iv:
            raise RuntimeError(f"YYB 未返回 encryptedData/iv: {inner}")

        profile = {}
        b64_str = inner.get("data")
        if b64_str and isinstance(b64_str, str):
            try:
                res_dec = json.loads(base64.b64decode(b64_str).decode())
                profile = res_dec.get("data", {})
                if isinstance(profile, str):
                    profile = json.loads(profile)
            except Exception:
                pass
        if not profile and inner.get("rawData"):
            try:
                raw_d = inner.get("rawData")
                if isinstance(raw_d, str):
                    raw_d = json.loads(raw_d)
                profile = raw_d.get("data", {})
                if isinstance(profile, str):
                    profile = json.loads(profile)
            except Exception:
                pass

        log(f"自动登录：昵称={profile.get('nickName', '<缺失>')}, 性别={profile.get('gender', '<缺失>')}")
        return {
            "encryptedData": encrypted_data,
            "iv": iv,
            "cloudId": inner.get("cloudId") or inner.get("cloud_id"),
            "profile": profile,
        }
    else:
        response = post_local_proxy(
            "/api/v1/wx/app/call/funtion",
            {
                "wxid": wxid,
                "appid": appid,
                "data": json_dumps(payload),
            },
        )
        result = response["data"]
        result_dict = as_dict(result)
        data_block = as_dict(result_dict.get("Data"))

        if not result_dict.get("Success") or not data_block.get("data"):
            raise RuntimeError(f"本地代理用户信息响应无效: {preview_text(json_dumps(result))}")

        outer_data = parse_base64_json(data_block["data"], "result.Data.data")
        profile = parse_nested_profile(outer_data.get("data"), "outerData.data")

        log(
            "自动登录："
            f"昵称={profile.get('nickName', '<缺失>')}, "
            f"性别={profile.get('gender', '<缺失>')}"
        )

        return {
            "encryptedData": outer_data.get("encryptedData"),
            "iv": outer_data.get("iv"),
            "cloudId": outer_data.get("cloud_id"),
            "profile": profile,
        }


def login_step1(
    code: str,
    encrypted_data: str,
    iv: str,
    visitor: str,
    user_agent: str,
    referer: str,
    log: LogFunc,
) -> Dict[str, Any]:
    path = "/api/v3/users/vivo/mini"
    body = {
        "code": code,
        "encryptedData": encrypted_data,
        "iv": iv,
        "from": LOGIN_CONFIG["bindFrom"],
    }
    body_text = json_dumps(body)
    headers = build_login_headers(path, body_text, visitor, user_agent, referer)

    log(f"自动登录：步骤1请求体={sanitize_body_for_log(body)}")

    response = request_json(
        LOGIN_CONFIG["step1Url"],
        {
            "method": "POST",
            "body": body_text,
            "headers": headers,
            "timeoutMs": LOGIN_CONFIG["requestTimeoutMs"],
        },
    )
    result = response["data"]
    if not isinstance(result, dict):
        raise RuntimeError(f"IQOO 步骤1返回非JSON: {preview_text(response['text'])}")

    data = as_dict(result.get("Data"))
    auth_token = extract_auth_token(data, response["headers"])
    log(f"自动登录：步骤1返回码={result.get('Code')}")

    if result.get("Code") != 0:
        raise RuntimeError(f"IQOO 步骤1失败: {preview_text(json_dumps(result))}")

    if auth_token:
        return {
            "mode": "final",
            "token": auth_token,
            "data": data,
        }

    if data.get("randomNum"):
        return {
            "mode": "bind",
            "data": data,
        }

    raise RuntimeError(
        "IQOO 步骤1成功但未返回 token 或 randomNum: "
        f"{preview_text(json_dumps(result))}"
    )


def login_step2(
    wxid: str,
    random_num: str,
    auth_token: str,
    visitor: str,
    user_agent: str,
    referer: str,
    log: LogFunc,
) -> Dict[str, Any]:
    log("自动登录：为绑定回退刷新微信材料")

    code = get_wx_code(wxid, log)
    user_info = get_wx_user_info(wxid, log)

    path = "/api/v3/users/vivo/mini/bind"
    body = {
        "code": code,
        "encryptedData": user_info["encryptedData"],
        "iv": user_info["iv"],
        "randomNum": random_num,
        "authtoken": auth_token or "",
    }
    body_text = json_dumps(body)
    headers = build_login_headers(path, body_text, visitor, user_agent, referer)

    log(f"自动登录：步骤2请求体={sanitize_body_for_log(body)}")

    response = request_json(
        LOGIN_CONFIG["step2Url"],
        {
            "method": "POST",
            "body": body_text,
            "headers": headers,
            "timeoutMs": LOGIN_CONFIG["requestTimeoutMs"],
        },
    )
    result = response["data"]
    if not isinstance(result, dict):
        raise RuntimeError(f"IQOO 步骤2返回非JSON: {preview_text(response['text'])}")

    token = extract_auth_token(as_dict(result.get("Data")), response["headers"])
    log(f"自动登录：步骤2返回码={result.get('Code')}")
    return {
        "result": result,
        "token": token,
    }


def auto_login(log: LogFunc, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    validate_login_config()
    opts = options or {}

    wxid = str(opts.get("wxid") or "").strip()
    visitor = str(opts.get("visitor") or LOGIN_CONFIG["visitor"])
    user_agent = str(opts.get("userAgent") or LOGIN_CONFIG["userAgent"])
    referer = str(opts.get("referer") or LOGIN_CONFIG["referer"])

    if not wxid:
        raise RuntimeError("自动登录缺少 wxid")

    log(f"自动登录：使用 visitor={mask_text(visitor, 6, 4)}")

    code = get_wx_code(wxid, log)
    user_info = get_wx_user_info(wxid, log)
    step1_result = login_step1(
        code,
        user_info["encryptedData"],
        user_info["iv"],
        visitor,
        user_agent,
        referer,
        log,
    )

    if step1_result["mode"] == "final":
        log("自动登录：步骤1返回最终 token")
        return {
            "wxid": wxid,
            "token": step1_result["token"],
            "visitor": visitor,
            "userAgent": user_agent,
            "referer": referer,
            "source": "step1",
            "data": step1_result["data"],
        }

    random_num = step1_result["data"]["randomNum"]
    log(f"自动登录：绑定回退 randomNum={mask_text(random_num, 6, 4)}")

    step2_result = login_step2(
        wxid,
        random_num,
        step1_result["data"].get("authtoken", ""),
        visitor,
        user_agent,
        referer,
        log,
    )

    if step2_result["result"].get("Code") == 0 and step2_result["token"]:
        log("自动登录：绑定返回最终 token")
        return {
            "wxid": wxid,
            "token": step2_result["token"],
            "visitor": visitor,
            "userAgent": user_agent,
            "referer": referer,
            "source": "step2",
            "data": step2_result["result"].get("Data"),
        }

    raise RuntimeError(
        "绑定未返回最终 token: "
        f"{preview_text(json_dumps(step2_result['result']))}"
    )


class Task:
    def __init__(self, account: Mapping[str, Any]):
        runtime = env_instance()
        self.index = runtime.user_idx
        runtime.user_idx += 1

        account_dict = as_dict(account)
        self.wxid = str(account_dict.get("wxid") or "").strip()
        self.remark = str(account_dict.get("remark") or self.wxid or f"account-{self.index}")
        self.account = {
            "wxid": self.wxid,
            "remark": self.remark,
        }
        self.token = ""
        self.visitor = os.getenv("IQOO_X_VISITOR") or DEFAULT_VISITOR
        self.user_agent = (
            os.getenv("IQOO_UA")
            or os.getenv("IQOO_USER_AGENT")
            or DEFAULT_USER_AGENT
        )
        self.referer = os.getenv("IQOO_REFERER") or DEFAULT_REFERER
        self.token_data: Dict[str, Any] = {}
        self.token_source = ""
        self.thread_id = ""
        self.post_id = ""

    def log(self, message: str) -> None:
        env_instance().log(f"账号 {self.index}[{self.remark}]: {message}")

    def get_sign(self, method: str, path: str, query_text: str, body_text: str) -> str:
        timestamp = str(int(time.time()))
        plain = f"{method}&{path}&{query_text}&{body_text}&appid={APP_ID}&timestamp={timestamp}"
        signature = base64.b64encode(
            hmac.new(
                SIGN_SECRET.encode("utf-8"),
                plain.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return (
            f"IQOO-HMAC-SHA256 appid={APP_ID},"
            f"timestamp={timestamp},signature={signature}"
        )

    def request(self, options: Dict[str, Any]) -> Dict[str, Any]:
        method = str(options.get("method") or "GET").upper()
        url = str(options["url"])
        data = options.get("data")
        sign_data = options.get("signData")
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path
        query_text = (
            build_query_string(sign_data or data) or parsed_url.query
            if method == "GET"
            else ""
        )
        body_text = "" if method == "GET" else json_dumps(data or {})

        headers = {
            "Accept": "*/*",
            "Accept-Encoding": ACCEPT_ENCODING,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Authorization": f"Bearer {self.token}" if self.token else "Bearer",
            "Content-Nonce": "",
            "Content-Type": "application/json",
            "Referer": self.referer,
            "SIGN": self.get_sign(method, path, query_text, body_text),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "User-Agent": self.user_agent,
            "X-Platform": "mini",
            "X-Visitor": self.visitor,
            "xweb_xhr": "1",
        }
        headers.update(options.get("headers") or {})

        request_init = {
            "method": method,
            "headers": headers,
            "timeoutMs": DEFAULT_TIMEOUT_MS,
        }
        if method != "GET":
            request_init["body"] = body_text

        response = do_request(url, request_init)
        parsed = safe_json_parse(response["text"])
        if response["status"] < 200 or response["status"] >= 300:
            raise RuntimeError(f"HTTP {response['status']}: {response['text'][:300]}")
        return {
            "status": response["status"],
            "headers": response["headers"],
            "data": parsed if parsed is not None else response["text"],
        }

    def apply_session(self, session: Mapping[str, Any]) -> None:
        self.token = normalize_token(session.get("token"))
        self.visitor = str(session.get("visitor") or self.visitor)
        self.user_agent = str(session.get("userAgent") or self.user_agent)
        self.referer = str(session.get("referer") or self.referer)
        self.token_data = as_dict(session.get("data"))
        self.token_source = str(session.get("source") or self.token_source)

    def load_cached_session(self) -> bool:
        cached = load_token_cache(self.wxid, self.log)
        if not cached:
            return False

        self.apply_session(cached)
        self.log(f"优先使用本地 token 缓存: {mask_text(self.token, 24, 16)}")
        return True

    def check_token(self) -> Dict[str, Any]:
        if not self.token:
            return {"ok": False, "reason": "missing"}

        payload = decode_jwt_payload(self.token)
        if not payload:
            self.log("token 载荷不可读，但继续执行")
            return {"ok": True, "reason": "opaque"}

        exp = payload.get("exp")
        try:
            expires_at = float(exp) if exp is not None else None
        except (TypeError, ValueError):
            expires_at = None

        if expires_at and time.time() >= expires_at:
            expiry_text = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
            self.log(f"token 已过期于 {expiry_text}")
            return {
                "ok": False,
                "reason": "expired",
                "payload": payload,
            }

        suffix = f" userId={payload.get('sub')}" if payload.get("sub") else ""
        self.log(f"token 已通过{suffix}")
        return {
            "ok": True,
            "reason": "valid",
            "payload": payload,
        }

    def ensure_token(self) -> bool:
        if not self.wxid:
            self.log("缺少 wxid，无法读取缓存或自动登录")
            return False

        if not self.token:
            self.load_cached_session()

        token_state = self.check_token()
        if token_state["ok"]:
            return True

        self.log(f"token 不可用 ({token_state['reason']})，开始自动登录")

        try:
            login_result = auto_login(
                self.log,
                {
                    "wxid": self.wxid,
                    "visitor": self.visitor,
                    "userAgent": self.user_agent,
                    "referer": self.referer,
                },
            )
        except Exception as exc:
            self.log(f"自动登录失败: {exc}")
            return False

        self.apply_session(login_result)
        try:
            save_token_cache(self.account, login_result, self.log)
        except Exception as exc:
            self.log(f"写入本地 token 缓存失败: {exc}")

        payload = decode_jwt_payload(self.token)
        suffix = f" userId={payload.get('sub')}" if payload and payload.get("sub") else ""
        self.log(f"自动登录成功，通过 {login_result['source']}{suffix}")
        self.log(f"授权={mask_text(self.token, 24, 16)}")
        return True

    def run_step(self, name: str, handler: Callable[[], None]) -> None:
        try:
            handler()
        except Exception as exc:
            self.log(f"{name} 失败: {exc}")

    def run(self) -> bool:
        if not self.ensure_token():
            return False

        self.run_step("签到", self.sign_in)
        env_instance().wait(1500)
        self.run_step("抽奖", self.get_draw_num)

        if SOCIAL_DISABLED:
            self.log("社交任务已被 IQOO_SKIP_SOCIAL 跳过")
            return True

        env_instance().wait(1500)
        self.run_step("帖子列表", self.get_thread_list)
        if not (self.thread_id and self.post_id):
            return True

        env_instance().wait(1200)
        self.run_step("点赞帖子", lambda: self.like_post(self.thread_id, self.post_id))
        env_instance().wait(1200)
        self.run_step("分享帖子", lambda: self.share_post(self.thread_id))
        env_instance().wait(1200)
        self.run_step("浏览帖子", lambda: self.view_post(self.thread_id))
        env_instance().wait(1200)
        self.run_step("评论帖子", lambda: self.comment_post(self.thread_id))
        return True

    def get_draw_num(self) -> None:
        result = self.request(
            {
                "method": "GET",
                "url": f"{BASE_URL}/api/v3/today.draw.count",
            }
        )["data"]

        if not is_success(result):
            self.log(f"抽奖次数获取失败: {get_message(result)}")
            return

        count = int(as_dict(result.get("Data")).get("count", -1))
        if count == 0:
            self.log("抽奖次数为0，尝试进行一次抽奖")
            self.draw()
            return

        self.log(f"抽奖次数={count}，跳过抽奖")

    def draw(self) -> None:
        result = self.request(
            {
                "method": "POST",
                "url": f"{BASE_URL}/api/v3/luck.draw",
                "data": {},
            }
        )["data"]

        if is_success(result):
            prize_name = as_dict(result.get("Data")).get("prize_name") or "done"
            self.log(f"抽奖成功: {prize_name}")
            return

        self.log(f"抽奖失败: {get_message(result)}")

    def sign_in(self) -> None:
        result = self.request(
            {
                "method": "POST",
                "url": f"{BASE_URL}/api/v3/sign",
                "data": {"from": "group"},
            }
        )["data"]

        if is_success(result):
            data = as_dict(result.get("Data"))
            self.log(
                "签到成功: "
                f"连续天数={data.get('serialDays', '-')}, "
                f"积分={data.get('score', '-')}, "
                f"积分总额={data.get('scoreCount', '-')}"
            )
            return

        self.log(f"签到失败: {get_message(result)}")

    def like_post(self, thread_id: str, post_id: str) -> None:
        def do_like(liked: bool) -> Any:
            return self.request(
                {
                    "method": "POST",
                    "url": f"{BASE_URL}/api/v3/posts.update",
                    "data": {
                        "id": thread_id,
                        "postId": post_id,
                        "data": {
                            "attributes": {
                                "isLiked": liked,
                            }
                        },
                    },
                }
            )["data"]

        like_result = do_like(True)
        self.log("点赞成功" if is_success(like_result) else f"点赞失败: {get_message(like_result)}")

        unlike_result = do_like(False)
        self.log(
            "取消点赞成功"
            if is_success(unlike_result)
            else f"取消点赞失败: {get_message(unlike_result)}"
        )

    def share_post(self, thread_id: str) -> None:
        result = self.request(
            {
                "method": "POST",
                "url": f"{BASE_URL}/api/v3/thread.share",
                "data": {"threadId": thread_id},
            }
        )["data"]
        self.log("分享成功" if is_success(result) else f"分享失败: {get_message(result)}")

    def view_post(self, thread_id: str) -> None:
        sign_data = {
            "threadId": thread_id,
            "type": 0,
        }
        result = self.request(
            {
                "method": "GET",
                "url": f"{BASE_URL}/api/v3/view.count?threadId={thread_id}&type=0",
                "signData": sign_data,
            }
        )["data"]
        self.log("浏览成功" if is_success(result) else f"浏览失败: {get_message(result)}")

    def comment_post(self, thread_id: str) -> None:
        result = self.request(
            {
                "method": "POST",
                "url": f"{BASE_URL}/api/v3/posts.create",
                "data": {
                    "id": thread_id,
                    "type": 0,
                    "content": DEFAULT_COMMENT,
                    "source": "",
                    "attachments": [],
                },
            }
        )["data"]
        self.log("评论成功" if is_success(result) else f"评论失败: {get_message(result)}")

    def get_thread_list(self) -> None:
        sign_data = {
            "filter[essence]": 1,
            "filter[sort]": 4,
            "page": 1,
            "perPage": 10,
            "scope": 5,
            "sequence": 0,
        }

        result = self.request(
            {
                "method": "GET",
                "url": (
                    f"{BASE_URL}/api/v3/thread.list"
                    "?scope=5&page=1&perPage=10&filter[sort]=4&filter[essence]=1&sequence=0"
                ),
                "signData": sign_data,
            }
        )["data"]

        if not is_success(result):
            self.log(f"帖子列表获取失败: {get_message(result)}")
            return

        page_data = as_dict(result.get("Data")).get("pageData") or []
        first = page_data[0] if page_data else {}
        self.thread_id = str(first.get("threadId") or "")
        self.post_id = str(first.get("postId") or "")

        if self.thread_id and self.post_id:
            self.log(f"已选择帖子: threadId={self.thread_id}, postId={self.post_id}")
            return

        self.log("帖子列表返回无可用帖子")


def print_login_config_summary(log: LogFunc, accounts: Optional[list[Dict[str, str]]] = None) -> None:
    account_list = accounts if accounts is not None else load_wxid_accounts()
    log("=== IQOO小程序登录流程 ===")
    log(f"token缓存 = {TOKEN_CACHE_PATH}")
    log(f"微信账号数 = {len(account_list)}")
    log(f"本地代理 = {LOGIN_CONFIG['localProxy']}")
    log(f"微信AppId = {LOGIN_CONFIG['wxAppid']}")
    log(f"步骤1Url = {LOGIN_CONFIG['step1Url']}")
    log(f"步骤2Url = {LOGIN_CONFIG['step2Url']}")
    log(f"访客ID = {mask_text(LOGIN_CONFIG['visitor'], 6, 4)}")
    log(f"超时毫秒 = {LOGIN_CONFIG['requestTimeoutMs']}")
    log("")


def print_token_summary(token: Any, data: Optional[Dict[str, Any]], log: LogFunc) -> None:
    normalized = normalize_token(token)
    if not normalized:
        log("授权 token 缺失。")
        return

    data_dict = as_dict(data)

    log(f"授权 = {mask_text(normalized, 24, 16)}")
    if data_dict.get("tokenType"):
        log(f"token类型 = {data_dict['tokenType']}")
    if data_dict.get("expiresIn"):
        log(f"过期时间 = {data_dict['expiresIn']}")
    if data_dict.get("userId"):
        log(f"用户ID = {data_dict['userId']}")

    payload = decode_jwt_payload(normalized)
    if not payload:
        return

    log("Token 载荷:")
    log(f"  sub = {payload.get('sub')}")
    log(f"  iss = {payload.get('iss')}")

    exp = payload.get("exp")
    if exp is not None:
        try:
            exp_text = datetime.fromtimestamp(float(exp), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            exp_text = str(exp)
        log(f"  exp = {exp_text}")


def login_only_main() -> int:
    accounts = load_wxid_accounts()
    print_login_config_summary(print, accounts)

    if not accounts:
        print("错误: 未设置 IQOO_WXID，格式应为 wxid#备注，多账号用换行或 @ 分隔。", file=sys.stderr)
        return 1

    has_failure = False
    for idx, account in enumerate(accounts, start=1):
        task = Task(account)
        if idx > 1:
            print("")
        print(f"=== 账号 {idx}: {account['remark']} ===")
        if not task.ensure_token():
            print("错误: 无法获取可用 token。", file=sys.stderr)
            has_failure = True
            continue

        print(f"token来源 = {task.token_source or 'cache'}")
        print_token_summary(task.token, task.token_data, print)

    if has_failure:
        return 1

    print("")
    print("登录成功。Token 可直接用于 IQOO API。")
    return 0


def run_main() -> int:
    runtime = env_instance()
    accounts = load_wxid_accounts()
    if not accounts:
        runtime.log("未设置 WX_ID / IQOO_WXID，格式应为 wxid#备注，多账号用换行或 @ 分隔")
        return 1

    overall_success = True
    for account in accounts:
        if not Task(account).run():
            overall_success = False
    return 0 if overall_success else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IQOO社区 Python 助手")
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="按 WX_ID / IQOO_WXID 的 wxid#备注 配置逐个检查缓存，必要时自动登录并打印 token。",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.login_only:
        return login_only_main()

    runtime = env_instance()
    exit_code = 0
    try:
        exit_code = run_main()
    except Exception:
        stack = traceback.format_exc().strip().replace("\n", " | ")
        runtime.log(f"致命错误: {stack}")
        exit_code = 1
    finally:
        runtime.done()
    return exit_code


__all__ = [
    "LOGIN_CONFIG",
    "Task",
    "auto_login",
    "decode_jwt_payload",
    "login_only_main",
    "main",
    "normalize_token",
]


if __name__ == "__main__":
    sys.exit(main())
