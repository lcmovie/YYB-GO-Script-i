#!/usr/bin/env python3
# cron: 22 8,14 * * *
"""
# name: 绿蜜蜂
绿蜜蜂小程序签到脚本 - 青龙面板版

功能：
1. 从缓存文件读取 access-token 和 user-token
2. 缓存失效时，通过中转服务器重新登录
3. 自动缓存 token 到 lmf_token.json
4. 执行签到并查询用户信息
5. 自动提现（余额>=最低提现金额时，默认开启）
6. 优先使用青龙 notify/sendNotify，失败时回退到常见推送通道

【青龙面板配置说明】

环境变量（在青龙面板 -> 环境变量中添加）：
- WX_ID=wxid123#备注1@wxid456#备注2    (必填，支持多账号，用@分隔，支持 getcode 协议)
- WECHAT_SERVER=http://127.0.0.1:8011  (微信协议服务地址)
- LMF_CASH=true              (是否开启自动提现，默认true)
- LMF_CASH_AMOUNT=0          (指定提现金额，0表示全额提现)
- LMF_NO_SIGN=false          (是否跳过签到，默认false)
- LMF_NO_NOTIFY=false        (是否跳过推送，默认false)

定时任务配置（青龙面板 -> 定时任务）：
- 名称：绿蜜蜂签到
- 命令：python3 /scripts/绿蜜蜂.py
- 定时规则：0 7 * * *    (每天早上7点执行)


"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import importlib.util
import inspect
import json
import os
import random
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Any, Optional

import requests

from getCode import get_single_code

BASE_URL = "https://lmf.lvmifo.com/api"
APP_TYPE = "WX_APP"
APP_ID = "75762944"
APP_SECRET = "ZNsLuCwAnnrDuQuyvTQcGpthsmASHSeG"
RAND_STR = "lv_mi_feng_uni_app"
VERSION = "v1.1.0"  # 小程序版本
API_VERSION = "v1.0.0"  # 接口请求版本，固定为 v1.0.0，修改会导致 "API版本不匹配"
REFERER_VERSION = "320"  # 小程序版本号，如果提现提示"小程序版本过低"，可尝试调大此值（如 320, 330）
REFERER = f"https://servicewechat.com/wx6fcde446296d9588/{REFERER_VERSION}/page-frame.html"
SCRIPT_NAME = "绿蜜蜂小程序"

ACCESS_TOKEN_URL = f"{BASE_URL}/5a60c77b79875?appType={APP_TYPE}"
USER_TOKEN_URL = f"{BASE_URL}/5e05692405c63"
USER_INFO_URL = f"{BASE_URL}/5dca57afa379e?m=getUserInfo"
SIGN_URL = f"{BASE_URL}/5dca57afa379e?m=toSign"
CASH_CHECK_URL = f"{BASE_URL}/62b2bafcd77cc?m=cashCheck"
CASH_APPLY_URL = f"{BASE_URL}/5e12a7e1848ba?m=cashApplyTwo"

DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"
WX_APPID = "wx6fcde446296d9588"

CACHE_FILE = "lmf_token.json"
CACHE_EXPIRE_HOURS = 2
DEFAULT_TIMEOUT = 20.0


@dataclass
class HttpResult:
    status: int
    text: str
    data: Any


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def get_env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    form: Optional[dict[str, Any]] = None,
    json_body: Optional[dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> HttpResult:
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            data=form,
            json=json_body,
            timeout=timeout,
        )
        return HttpResult(response.status_code, response.text, parse_json(response.text))
    except requests.RequestException as exc:
        return HttpResult(0, str(exc), None)


def summarize_error(result: HttpResult) -> str:
    if isinstance(result.data, dict):
        for key in ("msg", "message", "error"):
            value = result.data.get(key)
            if value:
                return str(value)
    return result.text[:200].strip() or f"HTTP {result.status}"


def push_message(title: str, content: str, timeout: float) -> bool:
    """发送通知"""
    try:
        from notify import send
        send(title, content)
        print("[OK] 通知已发送")
        return True
    except Exception as e:
        print(f"[WARN] 发送通知失败: {e}")
        return False


def load_cache() -> dict[str, Any]:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 读取缓存文件失败: {exc}")
        return {}


def save_cache(data: dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        print(f"[OK] Token已保存到 {CACHE_FILE}")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 保存缓存文件失败: {exc}")


def is_cache_valid(cache: dict[str, Any]) -> bool:
    if not cache:
        return False
    if "access_token" not in cache or "user_tokens" not in cache or "expire_time" not in cache:
        return False
    if time.time() > cache["expire_time"]:
        print("[WARN] access-token 已过期")
        return False
    return True


def parse_wxid_from_env() -> list[tuple[str, str]]:
    env_value = (os.environ.get("WX_ID") or os.environ.get("lmfwxid") or "").strip()
    if not env_value:
        return []

    parts: list[str] = []
    for sep in ("\n", "@", "&", "\r\n"):
        if sep in env_value:
            parts = env_value.split(sep)
            break
    if not parts:
        parts = [env_value]

    result: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            part = part.split("=", 1)[1].strip()
        if "#" in part:
            wxid, remark = part.split("#", 1)
            result.append((wxid.strip(), remark.strip()))
        else:
            result.append((part, ""))
    return result


def generate_device_id(timestamp: int) -> str:
    return f"{timestamp}{random.randint(1000, 9999)}"


def build_signature(timestamp: int, device_id: str) -> str:
    material = (
        f"app_id={APP_ID}"
        f"&app_secret={APP_SECRET}"
        f"&device_id={device_id}"
        f"&rand_str={RAND_STR}"
        f"&timestamp={timestamp}"
    )
    return hashlib.md5(material.encode("utf-8")).hexdigest()


def build_headers(access_token: str = "", user_token: str = "") -> dict[str, str]:
    return {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": REFERER,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "MicroMessenger/7.0.20.1781(0x6700143B) "
            "MiniProgramEnv/Windows"
        ),
        "access-token": access_token,
        "user-token": user_token,
        "version": API_VERSION,
        "xweb_xhr": "1",
        "lat": "",
        "lng": "",
        "this-shop-id": "0",
    }


def validate_token(access_token: str, user_token: str, timeout: float) -> bool:
    try:
        response = requests.get(
            USER_INFO_URL,
            headers=build_headers(access_token=access_token, user_token=user_token),
            timeout=timeout,
        )
        result = response.json()
        return result.get("code") == 1
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 验证 token 时发生异常: {exc}")
        return False


def get_access_token(device_id: str, timestamp: int, timeout: float) -> Optional[str]:
    signature = build_signature(timestamp, device_id)
    payload = {
        "app_id": APP_ID,
        "device_id": device_id,
        "rand_str": RAND_STR,
        "timestamp": timestamp,
        "signature": signature,
    }
    try:
        response = requests.post(
            ACCESS_TOKEN_URL,
            headers=build_headers(),
            data=payload,
            timeout=timeout,
        )
        result = response.json()
        if result.get("code") == 1 and "data" in result:
            return result["data"].get("access_token")
        print(f"[ERR] 获取 access-token 失败: {result.get('msg', '未知错误')}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] 获取 access-token 异常: {exc}")
        return None


def get_wx_code_via_relay(wxid: str, wechat_server: str, timeout: float) -> Optional[str]:
    if wechat_server:
        os.environ["WECHAT_SERVER"] = wechat_server
    try:
        print(f"[+] 使用 getCode 获取 code: appid={WX_APPID}, wxid={wxid}")
        return get_single_code(WX_APPID, wxid)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] 获取微信 code 异常: {exc}")
        return None


def get_user_token(access_token: str, wx_code: str, timeout: float) -> Optional[str]:
    try:
        response = requests.post(
            USER_TOKEN_URL,
            headers=build_headers(access_token=access_token),
            data={"code": wx_code},
            timeout=timeout,
        )
        result = response.json()
        if result.get("code") == 1 and "data" in result:
            return result["data"].get("utoken")
        print(f"[ERR] 获取 user-token 失败: {result.get('msg', '未知错误')}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] 获取 user-token 异常: {exc}")
        return None


def sign(access_token: str, user_token: str, timeout: float) -> dict[str, Any]:
    try:
        response = requests.get(
            SIGN_URL,
            headers=build_headers(access_token=access_token, user_token=user_token),
            timeout=timeout,
        )
        result = response.json()
        if result.get("code") == 1:
            data = result.get("data", {})
            return {
                "success": True,
                "msg": (
                    "签到成功，获得积分："
                    f"{data.get('get_integral', 0)}，获得余额：{data.get('get_red_packet', 0)}"
                ),
            }
        return {
            "success": False,
            "msg": f"签到失败，{result.get('msg', '未知错误')}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "msg": f"请求签到接口失败，{exc}",
        }


def get_user_info(access_token: str, user_token: str, timeout: float) -> dict[str, Any]:
    try:
        response = requests.get(
            USER_INFO_URL,
            headers=build_headers(access_token=access_token, user_token=user_token),
            timeout=timeout,
        )
        result = response.json()
        if result.get("code") == 1:
            data = result.get("data", {})
            return {
                "success": True,
                "msg": (
                    f"用户信息：{data.get('nick_name', '未知')}\n"
                    f"积分：{data.get('integral', 0)} | 余额：{data.get('amount', 0)}"
                ),
                "integral": data.get("integral", 0),
                "amount": float(data.get("amount", 0)),
            }
        return {
            "success": False,
            "msg": f"获取用户信息失败，{result.get('msg', '未知错误')}",
            "integral": 0,
            "amount": 0,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "msg": f"请求用户信息接口失败，{exc}",
            "integral": 0,
            "amount": 0,
        }


def cash_check(access_token: str, user_token: str, timeout: float) -> dict[str, Any]:
    """查询提现资格，返回最低提现金额"""
    try:
        response = requests.get(
            CASH_CHECK_URL,
            headers=build_headers(access_token=access_token, user_token=user_token),
            timeout=timeout,
        )
        result = response.json()
        if result.get("code") == 1 and "data" in result:
            min_amount = result["data"].get("min_amount", 0)
            return {
                "success": True,
                "min_amount": min_amount,
                "msg": f"提现资格检查通过，最低提现金额：{min_amount}元",
            }
        return {
            "success": False,
            "min_amount": 0,
            "msg": f"提现资格检查失败，{result.get('msg', '未知错误')}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "min_amount": 0,
            "msg": f"请求提现资格检查失败，{exc}",
        }


def cash_apply(access_token: str, user_token: str, amount: float, timeout: float) -> dict[str, Any]:
    """发起提现申请"""
    url = f"{CASH_APPLY_URL}&amount={amount}"
    try:
        response = requests.get(
            url,
            headers=build_headers(access_token=access_token, user_token=user_token),
            timeout=timeout,
        )
        result = response.json()
        if result.get("code") == 1:
            return {
                "success": True,
                "msg": f"提现成功，提现金额：{amount}元（微信提示：需要手动在微信中确认收款才能真正到账，请注意查收微信服务通知）",
            }
        return {
            "success": False,
            "msg": f"提现申请失败，{result.get('msg', '未知错误')}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "success": False,
            "msg": f"请求提现申请失败，{exc}",
        }


def get_env_bool(name: str, default: bool = False) -> bool:
    """从环境变量获取布尔值"""
    value = os.environ.get(name, "").strip().lower()
    if not value:  # 环境变量不存在或为空
        return default
    return value in ("true", "1", "yes", "on")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="绿蜜蜂小程序登录+签到脚本")
    parser.add_argument("--wxid", help="微信用户ID，若不指定则从环境变量 WX_ID/lmfwxid 获取")
    parser.add_argument("--device-id", help="自定义设备ID")
    parser.add_argument("--timestamp", type=int, help="自定义时间戳")
    parser.add_argument("--wechat-server", help="中转服务器地址，覆盖环境变量")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP 超时时间，单位秒")
    parser.add_argument("--no-sign", action="store_true", help="跳过签到步骤")
    parser.add_argument("--force-refresh", action="store_true", help="强制刷新 token，忽略缓存")
    parser.add_argument("--no-notify", action="store_true", help="跳过推送")
    parser.add_argument("--no-push", action="store_true", help="跳过推送")
    parser.add_argument("--push-test", action="store_true", help="只测试推送链路")
    parser.add_argument("--cash", action="store_true", help="执行自动提现")
    parser.add_argument("--no-cash", action="store_true", help="关闭自动提现")
    parser.add_argument("--cash-amount", type=float, default=float(os.environ.get("LMF_CASH_AMOUNT", "0")), help="指定提现金额，0表示全额提现（可通过环境变量 LMF_CASH_AMOUNT 控制）")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    # 参数优先级处理（命令行 > 环境变量）
    # 提现逻辑：--no-cash 优先级最高，其次是 --cash，最后是环境变量 LMF_CASH
    if args.no_cash:
        args.cash = False
    elif args.cash:
        pass  # 保持默认值
    else:
        args.cash = get_env_bool("LMF_CASH", True)
    
    # 跳过签到：命令行 --no-sign > 环境变量 LMF_NO_SIGN
    if not args.no_sign:
        args.no_sign = get_env_bool("LMF_NO_SIGN", False)
    
    # 跳过推送：命令行 --no-notify/--no-push > 环境变量 LMF_NO_NOTIFY
    if not (args.no_notify or args.no_push):
        if get_env_bool("LMF_NO_NOTIFY", False):
            args.no_notify = True

    if args.push_test:
        title = f"{SCRIPT_NAME} 推送测试"
        content = f"{title}\n时间: {now_text()}\n如果你收到了这条消息，说明推送链路已经生效。"
        print("开始测试推送链路...")
        return 0 if push_message(title, content, args.timeout) else 1

    print("=" * 60)
    print("=" * 60)
    
    # 打印配置信息
    print(f"[CONFIG] 自动提现: {'开启' if args.cash else '关闭'}")
    if args.cash:
        print(f"[CONFIG] 提现金额: {'全额' if args.cash_amount == 0 else f'{args.cash_amount}元'}")
    print(f"[CONFIG] 签到: {'开启' if not args.no_sign else '关闭'}")
    print(f"[CONFIG] 推送: {'开启' if not (args.no_notify or args.no_push) else '关闭'}")

    wxid_list: list[tuple[str, str]]
    if args.wxid:
        wxid_list = [(args.wxid, "")]
    else:
        wxid_list = parse_wxid_from_env()
        if not wxid_list:
            error_msg = (
                "[ERR] 错误：未提供 wxid\n"
                "    请通过 --wxid 参数或设置环境变量 WX_ID\n"
                "    环境变量格式: WX_ID=wxid123#备注@wxid456#备注2"
            )
            print(error_msg)
            if not (args.no_notify or args.no_push):
                push_message(SCRIPT_NAME, error_msg, args.timeout)
            return 1

    wechat_server = args.wechat_server or os.environ.get("WECHAT_SERVER", DEFAULT_WECHAT_SERVER)

    cache = load_cache()
    need_refresh = args.force_refresh
    if not need_refresh:
        if is_cache_valid(cache):
            print("[OK] 缓存文件有效，尝试使用缓存的 token")
        else:
            print("[WARN] 缓存无效或已过期，需要重新获取 token")
            need_refresh = True

    timestamp = args.timestamp or int(time.time())
    device_id = args.device_id or str(cache.get("device_id") or generate_device_id(timestamp))

    access_token: Optional[str] = None
    user_tokens_cache: dict[str, str] = {}

    if not need_refresh and cache.get("access_token"):
        access_token = str(cache["access_token"])
        user_tokens_cache = dict(cache.get("user_tokens", {}))
        print(f"[+] 使用缓存的 access-token: {access_token[:20]}...")
    else:
        print("[+] 正在获取 access-token...")
        access_token = get_access_token(device_id, timestamp, args.timeout)
        if not access_token:
            error_msg = "[ERR] 无法获取 access-token，退出"
            print(error_msg)
            if not (args.no_notify or args.no_push):
                push_message(SCRIPT_NAME, error_msg, args.timeout)
            return 1
        print(f"[OK] access-token 获取成功: {access_token[:20]}...")

    success_count = 0
    failed_count = 0
    new_user_tokens: dict[str, str] = {}
    all_messages: list[str] = []

    for idx, (wxid, remark) in enumerate(wxid_list, 1):
        account_title = f"账号{idx}"
        if remark:
            account_title += f"({remark})"

        print(f"\n{'=' * 60}")
        print(f" {account_title}: {wxid}")
        print("=" * 60)

        account_messages = [f"【{account_title}】"]
        user_token: Optional[str] = None

        if not need_refresh and wxid in user_tokens_cache:
            cached_token = user_tokens_cache[wxid]
            print(f"[+] 尝试使用缓存的 user-token: {cached_token[:20]}...")
            if validate_token(access_token, cached_token, args.timeout):
                print("[OK] 缓存的 user-token 有效")
                user_token = cached_token
            else:
                print("[WARN] 缓存的 user-token 失效，需要重新获取")

        if not user_token:
            print("[+] 正在获取微信 code...")
            wx_code = get_wx_code_via_relay(wxid, wechat_server, args.timeout)
            if not wx_code:
                msg = "无法获取微信 code"
                print(f"[ERR] {msg}")
                account_messages.append(msg)
                failed_count += 1
                all_messages.extend(account_messages)
                continue

            print("[+] 正在换取 user-token...")
            user_token = get_user_token(access_token, wx_code, args.timeout)
            if not user_token:
                msg = "无法获取 user-token"
                print(f"[ERR] {msg}")
                account_messages.append(msg)
                failed_count += 1
                all_messages.extend(account_messages)
                continue

            print(f"[OK] user-token 获取成功: {user_token[:20]}...")

        new_user_tokens[wxid] = user_token

        if not args.no_sign:
            print("[+] 正在执行签到...")
            sign_result = sign(access_token, user_token, args.timeout)
            print(f"[{sign_result['msg']}")
            account_messages.append(sign_result["msg"])
        else:
            account_messages.append("已按要求跳过签到")

        print("[+] 正在获取用户信息...")
        user_info_result = get_user_info(access_token, user_token, args.timeout)
        print(f"[{user_info_result['msg']}")
        account_messages.append(user_info_result["msg"])

        if args.cash:
            print("[+] 正在检查提现资格...")
            cash_check_result = cash_check(access_token, user_token, args.timeout)
            print(f"[{cash_check_result['msg']}")
            account_messages.append(cash_check_result["msg"])
            
            if cash_check_result["success"]:
                balance = user_info_result.get("amount", 0)
                min_amount = cash_check_result.get("min_amount", 3)
                
                if balance >= min_amount:
                    # cash_amount 为 0 表示全额提现，否则使用指定金额
                    cash_amount = balance if args.cash_amount == 0 else args.cash_amount
                    print(f"[+] 余额 {balance} 元 >= 最低提现 {min_amount} 元，执行提现 {cash_amount} 元...")
                    cash_apply_result = cash_apply(access_token, user_token, cash_amount, args.timeout)
                    print(f"[{cash_apply_result['msg']}")
                    account_messages.append(cash_apply_result["msg"])
                else:
                    msg = f"余额 {balance} 元 < 最低提现 {min_amount} 元，跳过提现"
                    print(f"[{msg}")
                    account_messages.append(msg)
            else:
                account_messages.append("提现资格检查失败，跳过提现")
        else:
            account_messages.append("已按要求跳过提现")

        all_messages.extend(account_messages)
        success_count += 1

    if success_count > 0:
        cache_data = {
            "access_token": access_token,
            "user_tokens": new_user_tokens,
            "expire_time": time.time() + CACHE_EXPIRE_HOURS * 3600,
            "update_time": time.time(),
            "device_id": device_id,
        }
        save_cache(cache_data)

    summary = [
        f"{SCRIPT_NAME}执行结果",
        f"成功: {success_count} 个",
        f"失败: {failed_count} 个",
        f"执行时间: {now_text()}",
        "",
    ]
    summary.extend(all_messages)

    print("\n" + "=" * 60)
    print("                    执行结果汇总")
    print("=" * 60)
    for line in summary:
        print(line)
    print("=" * 60)

    if not (args.no_notify or args.no_push):
        notify_title = SCRIPT_NAME
        if failed_count > 0:
            notify_title += " (有失败)"
        notify_message = "\n".join(summary)
        if len(notify_message) > 2000:
            notify_message = notify_message[:2000] + "\n...(内容过长已截断)"
        push_message(notify_title, notify_message, args.timeout)

    return 0 if success_count > 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"\n[ERR] 脚本执行异常: {exc}")
        print(traceback.format_exc())
        try:
            push_message(
                f"{SCRIPT_NAME}异常",
                f"脚本执行异常: {exc}\n{traceback.format_exc()[:500]}",
                DEFAULT_TIMEOUT,
            )
        except Exception:
            pass
        sys.exit(1)
