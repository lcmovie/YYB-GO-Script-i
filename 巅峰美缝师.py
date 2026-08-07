# cron: 58 11,16 * * *
# -*- coding: utf-8 -*-
# name: 巅峰美缝师
"""
巅峰美缝师 青龙自动任务脚本
功能：自动登录、获取手机号（新用户）、签到、获取积分，支持多账号
版本：1.0.8
更新日期：2026-07-04

环境变量：
    WX_ID            - 账号列表，格式"wxid#别名"，多账号用换行或 @ 或 & 分隔
    WECHAT_SERVER    - 自建微信服务地址（含一号协议、二号协议）

缓存文件：
    tokens/DFMFS_tokens.json
    caches/DFMFS_points_history.json

调度建议：
    每天 8:00-9:00 随机时间执行一次
"""

import json
import os
import re
import sys
import time
import random
import hashlib
import datetime
import requests
from getCode import get_single_code
from typing import Optional, Dict, Any, List, Tuple

# 通知模块
try:
    import notify
except ImportError:
    print("未找到 notify.py，将仅在控制台输出日志。")
    class notify:
        @staticmethod
        def send(title, content):
            print(f"--- 通知 ---\n{title}\n{content}\n-------------")

# ============================================================
# 配置区
# ============================================================

WX_APP_ID = "wx444ddc3d46767f9d"
API_BASE = "https://api.dfmeifeng.com"

PATH_LOGIN = "/wechat/miniapp/wechat/login"
PATH_GET_PHONE = "/wechat/miniapp/wechat/getPhoneNoInfo"
PATH_GET_INFO = "/wechat/miniapp/member/getInfo"
PATH_GET_IDENTITY = "/wechat/miniapp/member/getMemberIdentity"
PATH_GET_PROFILE_AWARD = "/wechat/miniapp/operate/getProfileAward"
PATH_GET_SIGN_INFO = "/wechat/miniapp/signin/getSignInfo"
PATH_GET_SIGN_SETTING = "/wechat/miniapp/operate/getSignInSetting"
PATH_SIGN_IN = "/wechat/miniapp/signin/signIn"

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2

DELAY_MIN = 1.0
DELAY_MAX = 5.0

DEBUG_MODE = False
TEST_MODE = False

BLACKLIST_ALIASES = []

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541939) XWEB/25047",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.31 NetType/WIFI Language/zh_CN miniProgram",
]

TOKEN_DIR = "tokens"
CACHE_DIR = "caches"
TOKEN_FILE = f"{TOKEN_DIR}/DFMFS_tokens.json"
POINTS_HISTORY_FILE = f"{CACHE_DIR}/DFMFS_points_history.json"

ENV_WXCODE_CK = "WX_ID"
ENV_WECHAT_SERVER = "WECHAT_SERVER"

# ============================================================
# 工具函数
# ============================================================

def ensure_dirs():
    for d in [TOKEN_DIR, CACHE_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)

def random_delay():
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    print(f"│ ⏱️  随机延时 {delay:.2f}s")
    time.sleep(delay)

def debug_log(msg: str):
    if DEBUG_MODE:
        print(f"[DEBUG] {msg}")

def get_random_ua() -> str:
    return random.choice(USER_AGENTS)

def get_date_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def generate_t_param(access_token: str) -> str:
    if not access_token:
        return ""
    raw = f"{access_token}{get_date_str()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest().lower()

def build_headers(access_token: str = None) -> Dict[str, str]:
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Host": "api.dfmeifeng.com",
        "Referer": f"https://servicewechat.com/{WX_APP_ID}/71/page-frame.html",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "User-Agent": get_random_ua(),
        "xweb_xhr": "1",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
        headers["t"] = generate_t_param(access_token)
    return headers

def request_with_retry(method: str, url: str, headers: Dict, data: Any = None,
                       timeout: int = REQUEST_TIMEOUT) -> Optional[Dict]:
    for attempt in range(MAX_RETRIES):
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=timeout)
            else:
                resp = requests.post(url, headers=headers, json=data, timeout=timeout)

            if resp.status_code != 200:
                debug_log(f"HTTP {resp.status_code}，重试 {attempt+1}/{MAX_RETRIES}")
                time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
                continue

            result = resp.json()
            if result.get("code") in [200, 0] or result.get("Success") is True:
                return result

            debug_log(f"接口返回错误: {result}")
            return result

        except Exception as e:
            debug_log(f"请求异常: {e}，重试 {attempt+1}/{MAX_RETRIES}")
            time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))
            continue

    return None

# ============================================================
# Token 缓存读写
# ============================================================

def load_tokens() -> Dict[str, Dict]:
    ensure_dirs()
    if not os.path.exists(TOKEN_FILE):
        return {}
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_tokens(tokens: Dict[str, Dict]):
    ensure_dirs()
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

def validate_token(alias: str, access_token: str) -> bool:
    if not access_token:
        return False
    url = f"{API_BASE}{PATH_GET_INFO}"
    headers = build_headers(access_token)
    result = request_with_retry("GET", url, headers)
    return bool(result and result.get("code") in [200, 0])

# ============================================================
# 积分历史缓存读写
# ============================================================

def load_points_history() -> Dict[str, Dict[str, int]]:
    ensure_dirs()
    if not os.path.exists(POINTS_HISTORY_FILE):
        return {}
    try:
        with open(POINTS_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_points_history(history: Dict[str, Dict[str, int]]):
    ensure_dirs()
    with open(POINTS_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def get_today_date() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def get_yesterday_date() -> str:
    return (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

def get_day_before_yesterday() -> str:
    return (datetime.datetime.now() - datetime.timedelta(days=2)).strftime("%Y-%m-%d")

# ============================================================
# 微信 Code 获取（一号协议 / 牛子 Niuzi）
# ============================================================

def get_wx_code(wxid: str) -> Optional[str]:
    """通过 getCode.py 统一接口获取微信登录 code（牛子/应用宝双协议）"""
    actual_wxid = str(wxid).split('#')[0].strip()
    try:
        return get_single_code(WX_APP_ID, actual_wxid)
    except Exception as e:
        print(f"⚠️ 获取登录code异常: {e}")
        return None


def get_wx_phone_code(wxid: str) -> Optional[str]:
    """
    从中转服务获取手机号授权 code（二号协议）
    接口: POST {WECHAT_SERVER}/api/v1/wx/app/get/all/mobile
    """
    raw_server = os.environ.get(ENV_WECHAT_SERVER, "").strip()
    if not raw_server:
        return None

    base = raw_server.rstrip("/")
    if base.endswith("/get/code"):
        url = base.replace("/get/code", "/get/all/mobile")
    elif base.endswith("/code"):
        url = base.replace("/code", "/get/all/mobile")
    else:
        url = f"{base}/api/v1/wx/app/get/all/mobile"

    payload = {"wxid": wxid, "appid": WX_APP_ID, "data": "", "opt": 0}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                proxies={"http": None, "https": None},
            )
            if resp.status_code != 200:
                time.sleep(RETRY_BACKOFF_BASE * attempt)
                continue

            data = resp.json()

            # 方式1：Data.Data → wx_phone.code
            data_str = data.get("Data", {}).get("Data")
            if data_str:
                try:
                    inner = json.loads(data_str)
                    code = inner.get("wx_phone", {}).get("code")
                    if code:
                        return str(code)
                except (json.JSONDecodeError, AttributeError):
                    pass

            # 方式2：Data.ALLMobile[0].code
            all_mobile = data.get("Data", {}).get("ALLMobile")
            if all_mobile and len(all_mobile) > 0:
                code = all_mobile[0].get("code")
                if code:
                    return str(code)

            # 方式3：Data.code 兜底
            code = data.get("Data", {}).get("code") if isinstance(data.get("Data"), dict) else None
            if code:
                return str(code)

            debug_log(f"手机号code响应异常 (第{attempt+1}次)")

        except Exception as e:
            debug_log(f"获取手机号code异常: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_BASE * (2 ** attempt))

    return None

# ============================================================
# 登录及业务函数
# ============================================================

def login(alias: str, wxid: str, code: str) -> Optional[Dict]:
    url = f"{API_BASE}{PATH_LOGIN}?code={code}&memberId="
    headers = build_headers()
    result = request_with_retry("GET", url, headers)
    if not result:
        return None
    data = result.get("data", {})
    if data.get("login") is True:
        return {
            "access_token": data.get("access_token"),
            "isNew": data.get("isNew", False),
            "sessionKey": data.get("sessionKey"),
        }
    return None

def get_phone_info(access_token: str, phone_code: str) -> Optional[str]:
    """
    获取手机号信息，同时刷新 token
    返回: 新的 access_token（如果成功）
    """
    url = f"{API_BASE}{PATH_GET_PHONE}?code={phone_code}&openid=&memberId="
    headers = build_headers(access_token)
    result = request_with_retry("GET", url, headers)
    if not result:
        return None
    data = result.get("data", {})
    new_token = data.get("access_token")
    if new_token:
        debug_log("获取手机号成功，token已刷新")
        return new_token
    return None

def get_member_info(access_token: str) -> Optional[Dict]:
    url = f"{API_BASE}{PATH_GET_INFO}"
    headers = build_headers(access_token)
    result = request_with_retry("GET", url, headers)
    if result and result.get("code") in [200, 0]:
        return result.get("data", {})
    return None

def get_profile_award(access_token: str) -> Optional[int]:
    url = f"{API_BASE}{PATH_GET_PROFILE_AWARD}"
    headers = build_headers(access_token)
    result = request_with_retry("GET", url, headers)
    if result and result.get("code") in [200, 0]:
        return result.get("improveDataAward")
    return None

def get_sign_info(access_token: str) -> Optional[Dict]:
    url = f"{API_BASE}{PATH_GET_SIGN_INFO}"
    headers = build_headers(access_token)
    result = request_with_retry("GET", url, headers)
    if result and result.get("code") in [200, 0]:
        return result.get("data", {})
    return None

def get_sign_setting(access_token: str) -> Optional[Dict]:
    url = f"{API_BASE}{PATH_GET_SIGN_SETTING}"
    headers = build_headers(access_token)
    result = request_with_retry("GET", url, headers)
    if result and result.get("code") in [200, 0]:
        return result.get("data", {})
    return None

def do_sign_in(access_token: str) -> bool:
    url = f"{API_BASE}{PATH_SIGN_IN}"
    headers = build_headers(access_token)
    result = request_with_retry("POST", url, headers, data={})
    return bool(result and result.get("code") in [200, 0])

# ============================================================
# 推送函数
# ============================================================

def send_notify(title: str, content: str):
    """调用青龙面板的 notify.py 发送通知"""
    try:
        notify.send(title, content)
        return True
    except Exception:
        return False

# ============================================================
# 处理单个账号
# ============================================================

def process_account(alias: str, wxid: str, idx: int, total: int) -> Dict:
    print(f"┌─ 👤  [{idx}/{total}]: {alias} ─────────────────────")
    result = {
        "alias": alias,
        "wxid": wxid,
        "success": False,
        "points_before": None,
        "points_after": None,
        "points_change": None,
        "is_new": False,
        "signed_in": False,
        "error": None,
        "points_history": {},
    }
    start_time = time.time()

    try:
        random_delay()

        # 1. 获取登录 code（使用 getCode 公共模块）
        print(f"│ 📱 获取登录 code...", end=" ")
        code = get_wx_code(wxid)
        if not code:
            print("❌ 获取失败")
            result["error"] = "获取登录code失败"
            print(f"└─────────────────────────────────────")
            return result
        print("✅")

        # 2. 登录
        print(f"│ 🔐 登录...", end=" ")
        login_data = login(alias, wxid, code)
        if not login_data:
            print("❌ 登录失败")
            result["error"] = "登录失败"
            print(f"└─────────────────────────────────────")
            return result
        access_token = login_data.get("access_token")
        is_new = login_data.get("isNew", False)
        result["is_new"] = is_new
        print("✅")

        # 3. 如果是新用户，走完整注册流程（获取手机号→绑定→刷新token）
        if is_new:
            print(f"│ 🆕 新用户，执行注册流程...")
            # 3.1 获取手机号授权 code（二号协议）
            print(f"│ 📞 获取手机号授权 code...", end=" ")
            phone_code = get_wx_phone_code(wxid)
            if not phone_code:
                print("❌ 获取失败，跳过手机号绑定")
            else:
                print("✅")
                # 3.2 调用 getPhoneNoInfo 获取手机号并刷新token
                print(f"│ 📞 绑定手机号并刷新token...", end=" ")
                new_token = get_phone_info(access_token, phone_code)
                if new_token:
                    access_token = new_token
                    result["access_token"] = access_token
                    print("✅ (token已刷新)")
                else:
                    print("❌ 绑定失败")

            # 3.3 查询完善资料奖励（现在可能已绑定手机号，可以领取）
            print(f"│ 🎁 查询完善资料奖励...", end=" ")
            award = get_profile_award(access_token)
            if award is not None and award > 0:
                print(f"✅ {award} 积分可领")
            else:
                print("ℹ️  无奖励或需手动领取")

        # 4. 保存 token 到缓存
        all_tokens = load_tokens()
        all_tokens[alias] = {
            "access_token": access_token,
            "wxid": wxid,
            "updated_at": datetime.datetime.now().isoformat(),
        }
        save_tokens(all_tokens)

        # 5. 任务前积分
        print(f"│ 📊 任务前查询积分...", end=" ")
        info_before = get_member_info(access_token)
        if not info_before:
            print("❌ 查询失败")
            result["error"] = "查询积分失败"
            print(f"└─────────────────────────────────────")
            return result
        points_before = info_before.get("balancePoints", 0)
        result["points_before"] = points_before
        print(f"✅ {points_before}")

        # 6. 签到状态
        print(f"│ 📅 检查签到状态...", end=" ")
        sign_info = get_sign_info(access_token)
        if not sign_info:
            print("❌ 查询失败")
            result["error"] = "查询签到状态失败"
            print(f"└─────────────────────────────────────")
            return result
        today_signed = sign_info.get("todaySignIn", False)
        continuous_day = sign_info.get("continuousDay", 0)
        print(f"{'✅ 已签到' if today_signed else '⏳ 未签到'} (连续 {continuous_day} 天)")

        # 7. 执行签到
        if not today_signed:
            sign_setting = get_sign_setting(access_token)
            sign_points = sign_setting.get("signInPoints", 50) if sign_setting else 50
            extra_points = sign_setting.get("extraPoints", 0) if sign_setting else 0
            total_reward = sign_points + extra_points
            print(f"│ ✍️  执行签到 (奖励 {total_reward} 积分)...", end=" ")
            sign_ok = do_sign_in(access_token)
            if sign_ok:
                result["signed_in"] = True
                print("✅")
            else:
                print("❌ 签到失败")
        else:
            print(f"│ 📅 今日已签到，跳过")

        # 8. 任务后积分
        print(f"│ 📊 任务后查询积分...", end=" ")
        info_after = get_member_info(access_token)
        if not info_after:
            print("❌ 查询失败")
            result["error"] = "任务后查询积分失败"
            print(f"└─────────────────────────────────────")
            return result
        points_after = info_after.get("balancePoints", 0)
        result["points_after"] = points_after
        result["points_change"] = points_after - points_before
        print(f"✅ {points_after} (+{result['points_change']})")

        # 9. 更新历史
        history = load_points_history()
        today = get_today_date()
        if alias not in history:
            history[alias] = {}
        history[alias][today] = points_after
        save_points_history(history)
        result["points_history"] = history.get(alias, {})
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        print(f"│ ❌ 异常: {str(e)[:50]}")

    elapsed = time.time() - start_time
    status = "✅" if result["success"] else "❌"
    print(f"│ {status} 处理完成 (耗时 {elapsed:.2f}s)")
    print(f"└─────────────────────────────────────")
    return result

# ============================================================
# 主程序
# ============================================================

def main():
    print("=" * 60)
    print(" 巅峰美缝师 青龙自动任务脚本 v1.0.8")
    print(f" 执行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    wxcode_ck = os.environ.get(ENV_WXCODE_CK)
    if not wxcode_ck:
        print("❌ 环境变量 WX_ID 未设置")
        return

    accounts = []
    for line in re.split(r"[\r\n@&]+", wxcode_ck.strip()):
        line = line.strip()
        if not line or "#" not in line:
            continue
        parts = line.split("#", 1)
        wxid, alias = parts[0].strip(), parts[1].strip()
        if alias and wxid:
            accounts.append((alias, wxid))

    if not accounts:
        print("❌ 未解析到有效账号")
        return

    print(f"📋 共 {len(accounts)} 个账号")
    if BLACKLIST_ALIASES:
        print(f"📋 黑名单: {BLACKLIST_ALIASES}")

    filtered = [(a, w) for a, w in accounts if a not in BLACKLIST_ALIASES]
    if not filtered:
        print("❌ 所有账号均在黑名单中")
        return

    print(f"📋 实际处理: {len(filtered)} 个账号")
    print("-" * 60)

    results = []
    for idx, (alias, wxid) in enumerate(filtered, 1):
        result = process_account(alias, wxid, idx, len(filtered))
        results.append(result)

    # 汇总表格
    print("\n" + "=" * 60)
    print("📊 汇总结果")
    print("=" * 60)

    today = get_today_date()
    yesterday = get_yesterday_date()
    day_before = get_day_before_yesterday()
    print(f"{'序号':<4} {'别名':<12} {day_before:<12} {yesterday:<12} {today:<12} {'变化':<8}")
    print("-" * 60)
    for idx, r in enumerate(results, 1):
        alias = r.get("alias", "未知")
        history = r.get("points_history", {})
        p1 = history.get(day_before, "-")
        p2 = history.get(yesterday, "-")
        p3 = history.get(today, "-")
        change = r.get("points_change") or 0
        change_str = f"+{change}" if change > 0 else str(change) if change != 0 else "0"
        status = "✅" if r.get("success") else "❌"
        print(f"{idx:<4} {alias:<12} {str(p1):<12} {str(p2):<12} {str(p3):<12} {change_str:<8} {status}")

    # 推送
    success_count = sum(1 for r in results if r.get("success"))
    content_lines = [f"执行结果: {success_count}/{len(results)} 成功\n"]
    for r in results:
        alias = r.get("alias", "未知")
        status = "成功" if r.get("success") else f'失败: {r.get("error", "")}'
        change = r.get("points_change") or 0
        points = r.get("points_after", "-")
        if isinstance(change, (int, float)):
            line = f"【{alias}】积分: {points} 变化: {change:+d} 状态: {status}"
        else:
            line = f"【{alias}】状态: {status}"
        content_lines.append(line)

    title = f"巅峰美缝师任务完成"
    send_notify(title, "\n".join(content_lines))

    print("\n" + "=" * 60)
    print("🎯 脚本执行完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
