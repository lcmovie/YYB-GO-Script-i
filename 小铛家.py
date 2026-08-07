#!/usr/bin/env python3
"""
小铛家小程序
 cron: 48 8,14 * * *
环境变量:
# name: 小铛家
  WX_ID: wxid列表，格式: wxid#备注，多个账号用换行或@分隔
         （由共享 getCode 模块读取并智能路由 牛子/应用宝）
  WECHAT_SERVER: 牛子协议地址（手机号加密包 get/all/mobile 使用，getCode 读取），默认: http://127.0.0.1:8011
  YYB_SERVER: 应用宝(YYB) 服务地址（getCode 读取）
  SERVER_TYPE: 强制指定协议：wechat / yyb / auto（默认 auto 智能路由）
  PROXY_API: 品赞代理提取链接，可选
  PROXY_TYPE: 代理类型：http / socks5，默认：http
  IPZAN_CONFIG: 品赞自动加白名单，可选，格式：套餐购买编号#登录密码#套餐提取密匙#签名秘钥#1
"""

import asyncio
import hashlib
import hmac
import importlib.util
import inspect
import json
import os
import random
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests
import getCode  # 共享的微信小程序 code 获取模块（自动路由 牛子/应用宝，读取 WX_ID 过滤）



DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"
DEFAULT_WECHAT_MINI_APPID = "wx7f5bc6f204abc629"
DEFAULT_XIAODANJIA_APPID = "xiaodangjia"
DEFAULT_XIAODANJIA_BASE_URL = "https://lm.api.sujh.net"
DEFAULT_LOGIN_PATH = "/app/login/wechatLogin"
NOTIFY_TITLE = "小铛家签到"


@dataclass
class WxAccount:
    wxid: str
    remark: str = ""


@dataclass
class AccountSummary:
    index: int
    wxid: str
    remark: str = ""
    mobile: str = "N/A"
    full_mobile: str = "N/A"
    code: str = "N/A"
    user_id: str = "N/A"
    sign_status: str = "未执行"
    before_score: Optional[float] = None
    after_score: Optional[float] = None
    score_lines: List[str] = field(default_factory=list)
    success: bool = False
    error_message: str = ""
    detail_lines: List[str] = field(default_factory=list)

    def log(self, message: str = "") -> None:
        self.detail_lines.append(message)
        print(message)

    def build_notify_lines(self) -> List[str]:
        name = self.remark or self.wxid
        lines = [f"【账号{self.index}】{name}"]
        lines.append(f"手机号: {self.mobile}")
        if self.user_id != "N/A":
            lines.append(f"userId: {self.user_id}")
        lines.append(f"结果: {self.sign_status}")
        if self.before_score is not None or self.after_score is not None:
            before = self.before_score if self.before_score is not None else "?"
            after = self.after_score if self.after_score is not None else "?"
            lines.append(f"积分: {before} -> {after}")
        if self.error_message:
            lines.append(f"说明: {self.error_message}")
        lines.extend(self.score_lines[:3])
        return lines


def parse_wxid_list(raw_value: str) -> List[WxAccount]:
    accounts: List[WxAccount] = []
    if not raw_value:
        return accounts

    for item in re.split(r"[\n@]", raw_value):
        item = item.strip()
        if not item:
            continue
        if "#" in item:
            wxid, remark = item.split("#", 1)
            accounts.append(WxAccount(wxid=wxid.strip(), remark=remark.strip()))
        else:
            accounts.append(WxAccount(wxid=item, remark=""))
    return accounts


def find_notify_send() -> Optional[Callable]:
    try:
        from notify import send  # type: ignore

        return send
    except Exception:
        pass

    search_dirs = []
    script_dir = Path(__file__).resolve().parent
    ql_dir = os.environ.get("QL_DIR", "")
    if ql_dir:
        search_dirs.extend(
            [
                Path(ql_dir),
                Path(ql_dir) / "scripts",
                Path(ql_dir) / "data" / "scripts",
                Path(ql_dir) / "data" / "public",
            ]
        )
    search_dirs.extend(
        [
            script_dir,
            script_dir.parent,
            Path("/ql"),
            Path("/ql/scripts"),
            Path("/ql/data/scripts"),
            Path("/ql/data/public"),
        ]
    )

    seen: set[str] = set()
    for directory in search_dirs:
        if not directory:
            continue
        directory_str = str(directory)
        if directory_str in seen:
            continue
        seen.add(directory_str)
        notify_path = directory / "notify.py"
        if not notify_path.exists():
            continue

        spec = importlib.util.spec_from_file_location("ql_notify", notify_path)
        if spec is None or spec.loader is None:
            continue

        module = importlib.util.module_from_spec(spec)
        sys.modules["ql_notify"] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            continue

        if hasattr(module, "send"):
            return getattr(module, "send")
        if hasattr(module, "sendNotify"):
            return getattr(module, "sendNotify")

    return None


def push_notify(title: str, content: str) -> bool:
    send_func = find_notify_send()
    if not send_func:
        print("未找到青龙 notify.py，跳过消息推送")
        return False

    try:
        result = send_func(title, content)
        if inspect.isawaitable(result):
            asyncio.run(result)
        print("消息推送完成")
        return True
    except Exception as exc:
        print(f"消息推送失败: {exc}")
        return False


class XiaodangjiaWxidSign:
    def __init__(self) -> None:
        self.wechat_server = os.environ.get("WECHAT_SERVER", DEFAULT_WECHAT_SERVER)
        self.wechat_mini_appid = os.environ.get("WECHAT_MINI_APPID", DEFAULT_WECHAT_MINI_APPID)
        self.api_appid = os.environ.get("XIAODANJIA_APPID", DEFAULT_XIAODANJIA_APPID)
        self.base_url = os.environ.get("XIAODANJIA_BASE_URL", DEFAULT_XIAODANJIA_BASE_URL).rstrip("/")
        self.login_url = f"{self.base_url}{DEFAULT_LOGIN_PATH}"
        self.session = requests.Session()
        self.tmpl_ids = [
            "nhkbv6By62bsflJku6IndDncDqjmvor_x0V_2dzRoW4",
            "WztbpFu-saGJBQl_PDWCbMVV5brU3mAY4O2Y0tMN9wI",
            "rgg3A6s4bqmguHkeg7eSiBlKdwn-8dTUxQchrdIQQdQ",
        ]
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/4G MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541938) XWEB/19823",
        ]
        self.user_agent = self.user_agents[0]

        # 设备指纹配置 - 不同账号使用不同设备配置
        self.device_profiles = [
            {
                "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"10.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-CN,zh;q=0.9",
                "net_type": "WIFI",
            },
            {
                "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"10.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "net_type": "WIFI",
            },
            {
                "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="130", "Google Chrome";v="130"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"11.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-TW,zh;q=0.9,zh-CN;q=0.8,en;q=0.7",
                "net_type": "4G",
            },
            {
                "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="129", "Google Chrome";v="129"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"10.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-CN,zh;q=0.9",
                "net_type": "WIFI",
            },
            {
                "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="128", "Google Chrome";v="128"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"10.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-HK,zh;q=0.9,zh-CN;q=0.8,en;q=0.7",
                "net_type": "WIFI",
            },
            {
                "sec_ch_ua": '"Chromium";v="132", "Google Chrome";v="132"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"10.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-CN,zh;q=0.9",
                "net_type": "WIFI",
            },
            {
                "sec_ch_ua": '"Chromium";v="131", "Google Chrome";v="131"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"10.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-CN,zh;q=0.9",
                "net_type": "4G",
            },
            {
                "sec_ch_ua": '"Chromium";v="130", "Google Chrome";v="130"',
                "sec_ch_ua_mobile": "?0",
                "sec_ch_ua_platform": '"Windows"',
                "sec_ch_ua_platform_version": '"11.0.0"',
                "sec_ch_ua_model": '""',
                "sec_ch_ua_arch": '"x86"',
                "sec_ch_ua_bitness": '"64"',
                "accept_language": "zh-SG,zh;q=0.9,en;q=0.8",
                "net_type": "WIFI",
            },
        ]
        self.device_profile = self.device_profiles[0]

        # 代理配置
        self.proxy_api = os.environ.get("PROXY_API", "")
        self.proxy_type = os.environ.get("PROXY_TYPE", "http").lower()
        self.ipzan_config = os.environ.get("IPZAN_CONFIG", "")
        self.current_proxy: Optional[Dict] = None

    def _sign_ipzan(self, params: Dict[str, str]) -> str:
        """品赞代理签名"""
        sorted_params = sorted(params.items())
        sign_str = "&".join(f"{k}={v}" for k, v in sorted_params)
        secret = params.get("secretKey", "")
        return hmac.new(secret.encode(), sign_str.encode(), hashlib.md5).hexdigest().upper()

    def _get_ipzan_proxy_with_retry(self, account_name: str = "") -> Optional[Dict]:
        """从品赞代理API获取代理，支持重试和白名单处理"""
        if not self.proxy_api:
            print(f"[{account_name}] 未配置 PROXY_API，使用直连")
            return None

        print(f"[{account_name}] 正在获取品赞代理...")
        whitelist_handled_ips: set = set()
        whitelist_triggered = False
        proxy_retry_times = 3

        for index in range(1, proxy_retry_times + 1):
            try:
                resp = requests.get(self.proxy_api, timeout=15, proxies={"http": None, "https": None})
                text = resp.text.strip()

                # 尝试解析代理
                proxy_info = self._parse_proxy_response(text)

                if not proxy_info:
                    # 解析失败，检查是否白名单错误
                    whitelist_info = self._parse_ipzan_whitelist_error(text)
                    if whitelist_info and whitelist_info.get("ip"):
                        whitelist_triggered = True
                        print(f"[{account_name}] 检测到品赞白名单限制：{whitelist_info['message']}")
                        ip = whitelist_info["ip"]
                        if ip not in whitelist_handled_ips:
                            whitelist_handled_ips.add(ip)
                            if self._add_ipzan_whitelist(ip):
                                print(f"[{account_name}] 等待 2s 后重新提取代理")
                                time.sleep(2)
                                continue

                    if text:
                        print(f"[{account_name}] 第 {index} 次代理解析失败：{text[:120]}")
                    else:
                        print(f"[{account_name}] 第 {index} 次代理解析失败")
                    continue

                print(f"[{account_name}] 提取到代理：{proxy_info['host']}:{proxy_info['port']}")

                if self.ipzan_config and not whitelist_triggered:
                    print("[白名单] 当前服务器 IP 已在品赞白名单，无需自动添加")

                proxies = self._get_proxy_dict(proxy_info)

                if self._validate_proxy(proxies):
                    return proxy_info  # 返回原始代理信息，不是格式化后的

                print(f"[{account_name}] 第 {index} 次代理不可用")
            except Exception as exc:
                print(f"[{account_name}] 第 {index} 次获取代理异常：{exc}")

            if index < proxy_retry_times:
                time.sleep(2)

        print(f"[{account_name}] 获取代理失败，使用直连")
        return None

    def _parse_proxy_response(self, text: str) -> Optional[Dict]:
        """解析代理响应"""
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False)

        text = text.strip()
        if not text:
            return None

        try:
            data = json.loads(text)
            proxy_obj = None

            if isinstance(data.get("data"), list) and data["data"]:
                proxy_obj = data["data"][0]
            elif isinstance(data.get("data"), dict):
                proxy_obj = data["data"]
            elif data.get("ip") and data.get("port"):
                proxy_obj = data
            elif isinstance(data.get("result"), dict):
                proxy_obj = data["result"]

            if proxy_obj:
                host = str(proxy_obj.get("ip") or proxy_obj.get("host") or "").strip()
                port = proxy_obj.get("port")
                if self._is_valid_proxy_host(host) and port:
                    return {
                        "host": host,
                        "port": int(port),
                        "username": proxy_obj.get("user") or proxy_obj.get("username") or "",
                        "password": proxy_obj.get("pass") or proxy_obj.get("password") or "",
                    }
        except Exception:
            pass

        # 非JSON格式，直接返回文本内容作为代理
        if text and ":" in text:
            parts = text.split(":")
            if len(parts) == 2:
                host, port = parts[0].strip(), parts[1].strip()
                if self._is_valid_proxy_host(host) and port.isdigit():
                    return {"host": host, "port": int(port), "username": "", "password": ""}

        return None

    def _pkcs7_pad(self, data: bytes, block_size: int = 16) -> bytes:
        padding = block_size - len(data) % block_size
        return data + bytes([padding]) * padding

    def _build_ipzan_sign(self, timestamp: int, password: str, fetch_key: str, sign_key: str) -> str:
        """品赞代理签名（使用AES加密）"""
        try:
            from Crypto.Cipher import AES  # type: ignore
        except ImportError:
            print("缺少 pycryptodome 库，使用MD5签名")
            return self._sign_ipzan({"password": password, "fetchKey": fetch_key, "timestamp": str(timestamp), "secretKey": sign_key})

        key_bytes = sign_key.encode("utf-8")
        if len(key_bytes) not in (16, 24, 32):
            print(f"品赞签名秘钥长度无效，当前为 {len(key_bytes)} 字节")
            return ""

        plain = f"{password}:{fetch_key}:{timestamp}".encode("utf-8")
        cipher = AES.new(key_bytes, AES.MODE_ECB)
        return cipher.encrypt(self._pkcs7_pad(plain)).hex()

    def _is_valid_proxy_host(self, host: str) -> bool:
        host = str(host or "").strip()
        if not host:
            return False
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
            return all(0 <= int(part) <= 255 for part in host.split("."))
        return bool(re.fullmatch(r"[a-zA-Z0-9.-]+", host))

    def _extract_ipv4(self, text: str) -> str:
        match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", str(text or ""))
        if not match:
            return ""
        ip = match.group(0)
        return ip if self._is_valid_proxy_host(ip) else ""

    def _parse_ipzan_whitelist_error(self, raw_text: str) -> Optional[Dict]:
        """解析品赞代理API返回是否包含白名单错误"""
        text = str(raw_text or "").strip()
        if not text:
            return None

        message = text
        try:
            data = json.loads(text)
            message = str(data.get("message") or data.get("msg") or text).strip()
        except Exception:
            pass

        if not re.search(r"白名单|加入到.*白名单", message):
            if not re.search(r"白名单|加入到.*白名单", text):
                return None

        return {
            "ip": self._extract_ipv4(message or text),
            "message": message,
        }

    def _add_ipzan_whitelist(self, ip: str) -> bool:
        """品赞代理自动加白名单"""
        if not self.ipzan_config:
            return True

        if not self._is_valid_proxy_host(ip):
            print(f"[白名单] 无法识别待添加 IP: {ip or '-'}")
            return False

        try:
            parts = self.ipzan_config.split("#")
            if len(parts) < 4:
                print("IPZAN_CONFIG 格式错误，应为：套餐购买编号#登录密码#套餐提取密匙#签名秘钥#1")
                return False

            order_no, password, fetch_key, sign_key, replace = parts[0], parts[1], parts[2], parts[3], parts[4] if len(parts) > 4 else "1"

            timestamp = int(time.time())
            sign = self._build_ipzan_sign(timestamp, password, fetch_key, sign_key)

            url = "https://service.ipzan.com/whiteList-add"
            payload = {
                "no": order_no,
                "ip": ip,
                "sign": sign,
                "replace": replace,
            }
            resp = requests.post(url, json=payload, timeout=15, proxies={"http": None, "https": None})
            try:
                result = resp.json()
            except Exception:
                result = {"message": resp.text}

            message = result.get("message") or result.get("msg") or str(result)
            success = bool(
                result.get("code") == 0
                or result.get("success") is True
                or re.search(r"成功|success|已在白名单|已存在", message, re.I)
            )

            if success:
                print(f"[白名单] {ip} 添加成功")
                return True

            print(f"[白名单] {ip} 添加失败: {message}")
            return False
        except Exception as exc:
            print(f"[白名单] {ip} 添加异常: {exc}")
            return False

    def _validate_proxy(self, proxies: Dict[str, str]) -> bool:
        """验证代理是否可用"""
        try:
            resp = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=15)
            return resp.status_code == 200
        except Exception:
            return False

    def _get_proxy_dict(self, proxy_info: Dict) -> Dict[str, str]:
        """获取代理字典"""
        host = proxy_info.get("host", "")
        port = proxy_info.get("port", "")
        username = proxy_info.get("username", "")
        password = proxy_info.get("password", "")

        if username and password:
            auth = f"{username}:{password}@"
        else:
            auth = ""

        proxy_str = f"{auth}{host}:{port}"

        if self.proxy_type == "socks5":
            return {"http": f"socks5://{proxy_str}", "https": f"socks5://{proxy_str}"}
        return {"http": f"http://{proxy_str}", "https": f"http://{proxy_str}"}

    def _request_with_proxy(self, method: str, url: str, **kwargs) -> requests.Response:
        """使用代理发送请求，本地服务不走代理"""
        proxies = kwargs.pop("proxies", None)
        timeout = kwargs.pop("timeout", 30)
        server_name = kwargs.pop("server_name", "")

        # 如果有代理配置
        if self.current_proxy and proxies is not False:
            proxy_dict = self._get_proxy_dict(self.current_proxy)
            try:
                return requests.request(method, url, proxies=proxy_dict, timeout=timeout, **kwargs)
            except Exception as exc:
                print(f"[{server_name}] 代理请求失败: {exc}，切换直连")
                # 代理失败，尝试直连
                return requests.request(method, url, timeout=timeout, **kwargs)

        # 直连或明确不走代理
        return requests.request(method, url, timeout=timeout, **kwargs)

    def _setup_proxy(self, account_name: str = "") -> bool:
        """为当前账号设置代理"""
        proxy_info = self._get_ipzan_proxy_with_retry(account_name)
        self.current_proxy = proxy_info
        return True

    def build_headers(self, token: str = "") -> Dict[str, str]:
        profile = self.device_profile
        return {
            "Appid": self.api_appid,
            "Authorization": token,
            "User-Agent": self.user_agent,
            "xweb_xhr": "1",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": f"https://servicewechat.com/{self.wechat_mini_appid}/25/page-frame.html",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": profile["accept_language"],
            "Sec-CH-UA": profile["sec_ch_ua"],
            "Sec-CH-UA-Mobile": profile["sec_ch_ua_mobile"],
            "Sec-CH-UA-Platform": profile["sec_ch_ua_platform"],
            "Sec-CH-UA-Platform-Version": profile["sec_ch_ua_platform_version"],
            "Sec-CH-UA-Model": profile["sec_ch_ua_model"],
            "Sec-CH-UA-Arch": profile["sec_ch_ua_arch"],
            "Sec-CH-UA-Bitness": profile["sec_ch_ua_bitness"],
        }

    def get_code(self, wxid: str) -> Optional[str]:
        """获取微信登录code（通过共享 getCode 模块，自动路由牛子/应用宝，读取 WX_ID 过滤）"""
        try:
            return getCode.get_single_code(self.wechat_mini_appid, wxid)
        except Exception as exc:
            print(f"[{wxid}] 获取 code 异常: {exc}")
            return None

    def get_mobile_info(self, wxid: str, code: str) -> Optional[Dict]:
        if os.environ.get("YYB_SERVER", "").strip():
            result = getCode.get_single_phone_data(self.wechat_mini_appid, wxid)
            if not result:
                return None
            result.setdefault("code", code)
            wx_phone = result.get("wx_phone")
            if isinstance(wx_phone, dict):
                wx_phone.setdefault("code", code)
                return result
            return {"wx_phone": result, "code": result.get("code") or code}

        url = f"{self.wechat_server}/api/v1/wx/app/get/all/mobile"
        payload = {
            "wxid": wxid,
            "appid": self.wechat_mini_appid,
            "data": json.dumps(
                {"api_name": "webapi_getuserwxphone", "with_credentials": True},
                ensure_ascii=False,
            ),
            "opt": 0,
        }
        try:
            # 本地微信中转服务不走代理
            response = self.session.post(url, json=payload, timeout=30, proxies={"http": None, "https": None})
            result = response.json()
        except Exception as exc:
            print(f"[{wxid}] 获取手机号异常: {exc}")
            return None

        if not result.get("Success"):
            print(f"[{wxid}] 获取手机号失败: {result.get('Message', 'unknown error')}")
            return None

        raw_data = result.get("Data", {}).get("Data", "")
        if isinstance(raw_data, str):
            mobile_info = json.loads(raw_data) if raw_data else {}
        elif isinstance(raw_data, dict):
            mobile_info = raw_data
        else:
            mobile_info = {}

        mobile_info["code"] = code
        wx_phone = mobile_info.get("wx_phone")
        if isinstance(wx_phone, dict):
            wx_phone.setdefault("code", code)
        return mobile_info

    def get_login_payload(self, wxid: str) -> Optional[Dict]:
        code = self.get_code(wxid)
        if not code:
            return None

        mobile_info = self.get_mobile_info(wxid, code)
        if not mobile_info:
            return None

        wx_phone = mobile_info.get("wx_phone")
        if not isinstance(wx_phone, dict):
            wx_phone = {}

        payload = {
            "mobile": wx_phone.get("mobile") or "N/A",
            "show_mobile": wx_phone.get("show_mobile") or "N/A",
            "encryptedData": wx_phone.get("encryptedData"),
            "iv": wx_phone.get("iv"),
            "code": wx_phone.get("code") or mobile_info.get("code"),
        }

        missing = [key for key in ("encryptedData", "iv", "code") if not payload.get(key)]
        if missing:
            print(f"[{wxid}] 缺少登录参数: {', '.join(missing)}")
            return None
        return payload

    def login(self, wxid: str, login_payload: Dict) -> Optional[Dict]:
        params = {
            "encryptedData": login_payload["encryptedData"],
            "iv": login_payload["iv"],
            "code": login_payload["code"],
        }
        try:
            response = self._request_with_proxy(
                "GET",
                self.login_url,
                params=params,
                headers=self.build_headers(),
                server_name=wxid,
            )
            result = response.json()
        except Exception as exc:
            print(f"[{wxid}] 小程序登录异常: {exc}")
            return None

        if result.get("code") != 200 or not result.get("token"):
            print(f"[{wxid}] 小程序登录失败: {result.get('msg', 'unknown error')}")
            return None

        merged = dict(login_payload)
        merged["token"] = result.get("token")
        merged["userId"] = result.get("userId")
        return merged

    def get_score_info(self, token: str) -> Dict:
        try:
            response = self._request_with_proxy(
                "GET",
                f"{self.base_url}/app/score/index?platform=1",
                headers=self.build_headers(token),
            )
            result = response.json()
            if result.get("code") == 200:
                data = result.get("data", {})
                return {
                    "success": True,
                    "score": data.get("score", 0),
                    "signIn": data.get("signIn", 0),
                    "msgTip": data.get("msgTip", 0),
                }
            return {"success": False, "message": result.get("msg", "查询失败")}
        except Exception as exc:
            return {"success": False, "message": f"网络错误: {exc}"}

    def get_score_list(self, token: str, page: int = 1) -> Dict:
        try:
            response = self._request_with_proxy(
                "GET",
                f"{self.base_url}/app/score/list?pageNum={page}&platform=1",
                headers=self.build_headers(token),
            )
            result = response.json()
            if result.get("code") == 200:
                return {
                    "success": True,
                    "total": result.get("total", 0),
                    "rows": result.get("rows", []),
                }
            return {"success": False, "message": result.get("msg", "查询失败")}
        except Exception as exc:
            return {"success": False, "message": f"网络错误: {exc}"}

    def sign(self, token: str) -> Dict:
        if not token:
            return {"success": False, "message": "Authorization token is empty", "status": "失败"}

        payload = {"tmplIds": self.tmpl_ids, "platform": 1}
        try:
            response = self._request_with_proxy(
                "POST",
                f"{self.base_url}/app/score/sign",
                headers=self.build_headers(token),
                json=payload,
            )
            result = response.json()
            message = result.get("msg", "")
            if result.get("code") == 200:
                return {"success": True, "message": message or "签到成功", "status": "签到成功", "data": result}
            if "今日已签到" in message:
                return {"success": True, "message": message, "status": "今日已签到", "data": result}
            return {"success": False, "message": message or "签到失败", "status": "签到失败", "data": result}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "请求超时", "status": "请求超时"}
        except requests.exceptions.RequestException as exc:
            return {"success": False, "message": f"网络错误: {exc}", "status": "网络错误"}
        except json.JSONDecodeError:
            return {"success": False, "message": "响应解析失败", "status": "解析失败"}
        except Exception as exc:
            return {"success": False, "message": f"未知错误: {exc}", "status": "未知错误"}

    def run_account(self, account: WxAccount, index: int, delay: float = 0) -> AccountSummary:
        if delay > 0:
            wait_time = delay + random.uniform(1, 3)
            print(f"等待 {wait_time:.1f} 秒后处理账号 {index}...")
            time.sleep(wait_time)

        # 为每个账号创建新的 session，避免设备信息被关联
        self.session = requests.Session()

        # 设置代理
        account_name = account.remark or account.wxid
        self._setup_proxy(account_name)
        if self.current_proxy and isinstance(self.current_proxy, dict) and "host" in self.current_proxy:
            print(f"使用代理: {self.current_proxy['host']}:{self.current_proxy['port']}")

        # 为每个账号随机选择 User-Agent 和设备指纹
        self.user_agent = random.choice(self.user_agents)
        self.device_profile = random.choice(self.device_profiles)

        summary = AccountSummary(index=index, wxid=account.wxid, remark=account.remark)

        summary.log(f"\n【账号 {index}】")
        summary.log("-" * 50)
        summary.log(f"wxid: {account.wxid}")
        if account.remark:
            summary.log(f"备注: {account.remark}")

        login_payload = self.get_login_payload(account.wxid)
        if not login_payload:
            summary.sign_status = "获取登录参数失败"
            summary.error_message = "无法从微信中转服务获取 code 或手机号数据"
            summary.log("获取微信登录参数失败")
            return summary

        summary.mobile = login_payload.get("show_mobile", "N/A")
        summary.full_mobile = login_payload.get("mobile", "N/A")
        summary.code = login_payload.get("code", "N/A")

        summary.log(f"手机号: {summary.mobile}")
        #summary.log(f"完整手机号: {summary.full_mobile}")
        summary.log(f"Code: {summary.code}")

        login_result = self.login(account.wxid, login_payload)
        if not login_result:
            summary.sign_status = "获取 token 失败"
            summary.error_message = "小程序登录接口未返回有效 token"
            summary.log("获取 token 失败")
            return summary

        token = login_result["token"]
        summary.user_id = str(login_result.get("userId", "N/A"))
        summary.log(f"userId: {summary.user_id}")

        score_info_before = self.get_score_info(token)
        summary.log("\n正在查询签到前积分...")
        if score_info_before["success"]:
            summary.before_score = float(score_info_before["score"])
            signed_text = "是" if score_info_before["signIn"] == 1 else "否"
            summary.log(f"  当前积分: {summary.before_score}")
            summary.log(f"  今日已签到: {signed_text}")
        else:
            summary.log(f"  查询失败: {score_info_before['message']}")

        summary.log("\n开始签到...")
        sign_result = self.sign(token)
        summary.sign_status = sign_result["status"]
        if sign_result["success"]:
            summary.log(f"  签到结果: {sign_result['message']}")
        else:
            summary.error_message = sign_result["message"]
            summary.log(f"  签到失败: {sign_result['message']}")

        summary.log("\n正在查询签到后积分...")
        score_info_after = self.get_score_info(token)
        if score_info_after["success"]:
            summary.after_score = float(score_info_after["score"])
            summary.log(f"  当前积分: {summary.after_score}")
            if summary.before_score is not None:
                delta = summary.after_score - summary.before_score
                if delta > 0:
                    summary.log(f"  本次获得: +{delta}")
                elif delta < 0:
                    summary.log(f"  本次扣减: {delta}")
        else:
            summary.log(f"  查询失败: {score_info_after['message']}")
            if not summary.error_message:
                summary.error_message = score_info_after["message"]

        summary.log("\n正在查询积分记录...")
        score_list = self.get_score_list(token, page=1)
        if score_list["success"]:
            rows = score_list["rows"]
            if rows:
                summary.log("\n最近积分记录:")
                for row in rows[:3]:
                    title = row.get("title2") or row.get("title") or ""
                    score = row.get("score", 0)
                    create_time = row.get("createTime", "")
                    prefix = "+" if isinstance(score, (int, float)) and score > 0 else ""
                    score_line = f"[{create_time}] {title} {prefix}{score}"
                    summary.score_lines.append(score_line)
                    summary.log(f"  {score_line}")
            else:
                summary.log(f"  暂无积分记录 (总计: {score_list['total']} 条)")
        else:
            summary.log(f"  查询积分记录失败: {score_list['message']}")
            if not summary.error_message:
                summary.error_message = score_list["message"]

        summary.success = sign_result["success"]
        if summary.success and not summary.error_message:
            summary.error_message = sign_result["message"]
        return summary


def build_notify_content(summaries: List[AccountSummary]) -> str:
    header = [
        f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"账号数量: {len(summaries)}",
    ]
    body: List[str] = []
    for summary in summaries:
        if body:
            body.append("")
        body.extend(summary.build_notify_lines())
    return "\n".join(header + [""] + body)


def main() -> None:
    accounts = parse_wxid_list(os.environ.get("WX_ID", ""))
    if not accounts:
        print("错误: 未设置 WX_ID 环境变量")
        print("格式: wxid#备注，多个账号用换行或 @ 分隔")
        print("示例: wxid_abc123#账号1@wxid_def456#账号2")
        return

    proxy_api = os.environ.get("PROXY_API", "")
    proxy_type = os.environ.get("PROXY_TYPE", "http")
    ipzan_config = os.environ.get("IPZAN_CONFIG", "")

    print("=" * 50)
    print("小铛家签到脚本")
    print("=" * 50)
    print(f"微信中转服务端: {os.environ.get('WECHAT_SERVER', DEFAULT_WECHAT_SERVER)}")
    print(f"共 {len(accounts)} 个账号")
    if proxy_api:
        print(f"已启用品赞代理，代理类型: {proxy_type}")
        if ipzan_config:
            parts = ipzan_config.split("#")
            print(f"已启用品赞自动加白，套餐编号：{parts[0][-10:] if parts else 'N/A'}...")
    else:
        print("未配置代理，使用直连")

    runner = XiaodangjiaWxidSign()
    summaries: List[AccountSummary] = []
    for index, account in enumerate(accounts, 1):
        # 每个账号之间添加延迟，避免被识别为同一设备频繁请求
        delay = 5 if index > 1 else 0
        summaries.append(runner.run_account(account, index, delay=delay))

    notify_content = build_notify_content(summaries)
    print("\n" + "=" * 50)
    print("推送内容预览")
    print("=" * 50)
    print(notify_content)
    print("=" * 50)
    push_notify(NOTIFY_TITLE, notify_content)


if __name__ == "__main__":
    main()
