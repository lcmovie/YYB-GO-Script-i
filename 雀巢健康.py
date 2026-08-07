
# cron: 55 10,16 * * *
#!/usr/bin/env python3
# name: 雀巢健康
# -*- coding: utf-8 -*-
"""
青龙脚本：雀巢健康科学会员中心小程序每日签到

环境变量：
  WX_ID           必填，格式：wxid#别名（兼容别名#wxid），多账号换行 / & 分隔
  WECHAT_SERVER   必填，用于通过 wxid 获取 wx.login code
  NESTLE_SANXIA_MONSTER_TASK 可选，默认开启，0/false/off 关闭小怪兽限定任务
  NESTLE_SANXIA_MONSTER_REGISTER
                   可选，默认开启，未报名 180 天敏宝活动时自动报名
  NESTLE_SANXIA_MONSTER_GOODS_TYPE
                   可选，默认 Althera
  NESTLE_SANXIA_MONSTER_GOODS_DAYS
                   可选，默认 90

定时建议：
  15 8 * * *
"""

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from getCode import get_single_code

try:
    from notify import send as notify_send
except ImportError:
    def notify_send(title, content):
        print(f"--- 通知 ---\n{title}\n{content}\n-------------")


WX_APP_ID = "wx853b3ae8d25c1dd3"
BASE_URL = "https://nhssanxia.nestlechinese.com"
API_PREFIX = "/member-mini"
STAFF_PREFIX = "/staff-api"
REFERER = "https://servicewechat.com/wx853b3ae8d25c1dd3/312/page-frame.html"
ACTIVITY_PLAN_CODE = "Nestle_Thrive_Companion_180_Days"

DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"

WECHAT_SERVER = os.getenv("WECHAT_SERVER", DEFAULT_WECHAT_SERVER).rstrip("/")
WX_CODE_API = ""  # 已废弃：现使用 getCode.py 统一接口
ENABLE_MONSTER_TASK = os.getenv("NESTLE_SANXIA_MONSTER_TASK", "1").lower() not in {"0", "false", "no", "off"}
ENABLE_MONSTER_REGISTER = os.getenv("NESTLE_SANXIA_MONSTER_REGISTER", "1").lower() not in {"0", "false", "no", "off"}
MONSTER_GOODS_TYPE = os.getenv("NESTLE_SANXIA_MONSTER_GOODS_TYPE", "Althera")
MONSTER_GOODS_DAYS_RAW = os.getenv("NESTLE_SANXIA_MONSTER_GOODS_DAYS", "90")

TOKEN_STORE_FILE = Path(__file__).with_name("wx853b3ae8d25c1dd3_tokens.json")
RETRY_TIMES = 3
RETRY_BACKOFF = 2

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254191e) XWEB/19841",
    "Mozilla/5.0 (Linux; Android 12; SM-G9980) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/8.0.40.2420(0x2800283B) NetType/WIFI MiniProgramEnv/Android",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.38(0x1800262f) NetType/WIFI Language/zh_CN MiniProgramEnv/iOS",
]

log_messages: List[str] = []


def log(msg: str) -> None:
    print(msg)
    log_messages.append(msg)


def mask(value: str, left: int = 8, right: int = 6) -> str:
    if not value:
        return ""
    if len(value) <= left + right:
        return value[:left] + "..."
    return f"{value[:left]}...{value[-right:]}"


def sleep_random(min_seconds: float = 0.8, max_seconds: float = 2.0) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def build_headers(token: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json",
        "Referer": REFERER,
        "User-Agent": random.choice(UA_LIST),
        "xweb_xhr": "1",
    }
    headers["Authorization"] = f"Bearer {token}" if token else "Bearer"
    return headers


def build_staff_headers(activity_token: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json",
        "Referer": REFERER,
        "User-Agent": random.choice(UA_LIST),
        "xweb_xhr": "1",
    }
    if activity_token:
        headers["Activity-Management-Platform-Token"] = activity_token
    return headers


def load_tokens() -> Dict[str, Dict[str, str]]:
    if not TOKEN_STORE_FILE.exists():
        return {}
    try:
        return json.loads(TOKEN_STORE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"读取 token 缓存失败：{exc}")
        return {}


def save_tokens(tokens: Dict[str, Dict[str, str]]) -> None:
    try:
        TOKEN_STORE_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log(f"保存 token 缓存失败：{exc}")


def request_json(method: str, url: str, **kwargs) -> Optional[dict]:
    for attempt in range(1, RETRY_TIMES + 1):
        try:
            resp = requests.request(method, url, timeout=30, **kwargs)
            if resp.status_code != 200:
                log(f"HTTP {resp.status_code}：{url}")
                if attempt < RETRY_TIMES:
                    time.sleep(RETRY_BACKOFF ** (attempt - 1))
                    continue
                return None
            return resp.json()
        except Exception as exc:
            log(f"请求异常（{attempt}/{RETRY_TIMES}）：{exc}")
            if attempt < RETRY_TIMES:
                time.sleep(RETRY_BACKOFF ** (attempt - 1))
    return None


def is_success(data: Optional[dict]) -> bool:
    return bool(data and data.get("success") is True and data.get("code") == 20000)


def is_activity_success(data: Optional[dict]) -> bool:
    return bool(data and data.get("success") is True and data.get("code") == 0)


def get_code(wxid: str) -> Optional[str]:
    """通过 getCode.py 统一接口获取微信 login code"""
    try:
        return get_single_code(WX_APP_ID, wxid)
    except Exception as exc:
        log(f"获取 code 异常：{exc}")
        return None


def login_with_code(code: str) -> Optional[dict]:
    url = f"{BASE_URL}{API_PREFIX}/open/login"
    data = request_json("GET", url, params={"loginCode": code}, headers=build_headers(None))
    if not is_success(data):
        log(f"登录失败：{data}")
        return None
    login_data = data.get("data") or {}
    if not login_data.get("token"):
        log(f"登录响应缺少 token：{data}")
        return None
    return login_data


def api_get(path: str, token: str, params: Optional[dict] = None) -> Optional[dict]:
    return request_json("GET", f"{BASE_URL}{API_PREFIX}{path}", params=params or {}, headers=build_headers(token))


def api_post(path: str, token: str, params: Optional[dict] = None, payload: Optional[dict] = None) -> Optional[dict]:
    return request_json("POST", f"{BASE_URL}{API_PREFIX}{path}", params=params or {}, json=payload or {}, headers=build_headers(token))


def staff_post(path: str, payload: dict, activity_token: Optional[str] = None) -> Optional[dict]:
    return request_json(
        "POST",
        f"{BASE_URL}{STAFF_PREFIX}{path}",
        json=payload,
        headers=build_staff_headers(activity_token),
    )


def authenticate_activity(token: str) -> Optional[str]:
    data = staff_post(
        "/ActivityManagementPlatformService/authenticate",
        {"bizToken": token, "activityPlanCode": ACTIVITY_PLAN_CODE},
    )
    if not is_activity_success(data):
        log(f"小怪兽活动鉴权失败：{data}")
        return None
    activity_token = ((data.get("data") or {}).get("activityToken") or "").strip()
    if not activity_token:
        log(f"小怪兽活动鉴权响应缺少 activityToken：{data}")
        return None
    return activity_token


def activity_execute(activity_token: str, event_code: str, args: Optional[dict] = None) -> Optional[dict]:
    payload = {
        "activityPlanCode": ACTIVITY_PLAN_CODE,
        "activityPlanEventCode": event_code,
        "activityPlanEventArgs": json.dumps(args or {}, ensure_ascii=False, separators=(",", ":")),
    }
    data = staff_post("/ActivityManagementPlatformService/execute", payload, activity_token)
    if not is_activity_success(data):
        log(f"小怪兽活动事件 {event_code} 失败：{data}")
        return None
    return data


def get_activity_callback(data: Optional[dict]) -> dict:
    return (((data or {}).get("data") or {}).get("callback") or {})


def extract_progress_data(data: Optional[dict]) -> dict:
    callback = get_activity_callback(data)
    return (
        ((callback.get("action") or {}).get("setLevelProgressData"))
        or ((callback.get("data") or {}).get("levelProgressData"))
        or {}
    )


def extract_question_data(data: Optional[dict]) -> dict:
    callback = get_activity_callback(data)
    return (
        ((callback.get("action") or {}).get("setQuestion"))
        or ((callback.get("data") or {}).get("questionData"))
        or {}
    )


def extract_level_stats(data: Optional[dict]) -> dict:
    callback = get_activity_callback(data)
    return (
        ((callback.get("action") or {}).get("setLevelStats"))
        or ((callback.get("data") or {}).get("levelStatsData"))
        or {}
    )


def compact_text(value: Any) -> str:
    return "".join(str(value or "").split())


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_seconds(seconds: Any) -> str:
    total = parse_int(seconds)
    if total <= 0:
        return "0 秒"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分钟"
    if minutes:
        return f"{minutes}分钟{secs}秒"
    return f"{secs}秒"


def choose_correct_answer_ids(question: dict) -> List[int]:
    answers = question.get("answerList") or []
    answer_constraint = max(1, parse_int(question.get("answerConstraint"), 1))
    matched: List[int] = []
    for answer in answers:
        answer_id = answer.get("answerId")
        answer_content = compact_text(answer.get("answerContent"))
        answer_comment = compact_text(answer.get("answerComment"))
        if not answer_id or not answer_content or not answer_comment:
            continue
        if answer_content == answer_comment or answer_content in answer_comment:
            matched.append(answer_id)
    return matched[:answer_constraint]


def ensure_monster_registered(activity_token: str) -> bool:
    data = activity_execute(activity_token, "checkRegister")
    if not data:
        return False

    callback = get_activity_callback(data)
    navigate = ((callback.get("action") or {}).get("navigateTo") or {})
    registration_state = ((callback.get("data") or {}).get("registrationState") or {})
    status = navigate.get("status") or registration_state.get("status")
    if status != "no_data":
        return True

    if not ENABLE_MONSTER_REGISTER:
        log("小怪兽活动未报名，且已关闭自动报名")
        return False

    goods_days = parse_int(MONSTER_GOODS_DAYS_RAW, 90)
    log(f"小怪兽活动未报名，自动报名：goodsType={MONSTER_GOODS_TYPE}，goodsConsumedDays={goods_days}")
    register_data = activity_execute(
        activity_token,
        "register",
        {"goodsType": MONSTER_GOODS_TYPE, "goodsConsumedDays": goods_days, "finalPrizeCode": ""},
    )
    return bool(register_data)


def run_monster_task(token: str) -> bool:
    if not ENABLE_MONSTER_TASK:
        log("小怪兽限定任务已关闭")
        return True

    log("\n---- 限定任务：快来打赢过敏小怪兽 ----")
    activity_token = authenticate_activity(token)
    if not activity_token:
        return False
    log(f"小怪兽活动鉴权成功：{mask(activity_token)}")

    if not ensure_monster_registered(activity_token):
        return False

    activity_execute(activity_token, "getLatestLevelPage")
    progress_data = extract_progress_data(activity_execute(activity_token, "checkLevelProgress"))
    if not progress_data:
        log("未获取到小怪兽关卡进度")
        return False

    stage_level = progress_data.get("stageLevel")
    current_level = progress_data.get("currentLevel")
    current_status = progress_data.get("currentLevelStatus")
    next_wait = progress_data.get("nextLevelTimeLeft")
    level_point_map = progress_data.get("levelPointMap") or {}
    log(
        "小怪兽进度："
        f"阶段 {stage_level or '-'}，关卡 {current_level or '-'}，"
        f"状态 {current_status if current_status is not None else '-'}，"
        f"血量 {progress_data.get('levelBlood', '-')}/{progress_data.get('levelMaxBlood', '-')}"
    )
    if level_point_map:
        log(f"已获积分记录：{level_point_map}")

    if current_status != 2:
        if parse_int(next_wait) > 0:
            log(f"当前关卡暂未开放，预计等待：{format_seconds(next_wait)}")
        else:
            log("当前没有可挑战的小怪兽关卡")
        return True

    sleep_random()
    level_info = activity_execute(activity_token, "getLevelInfo")
    question = extract_question_data(level_info)
    if not question:
        log("未获取到小怪兽题目，可能今日已完成或关卡状态变化")
        return True

    question_title = question.get("questionTitle") or question.get("questionContent") or "-"
    answer_ids = choose_correct_answer_ids(question)
    if not answer_ids:
        log(f"无法自动判断正确答案，题目：{question_title}")
        return False

    selected_codes = [
        answer.get("answerCode") or answer.get("answerTitle") or str(answer.get("answerId"))
        for answer in question.get("answerList") or []
        if answer.get("answerId") in answer_ids
    ]
    log(f"小怪兽题目：{question_title}")
    log(f"提交答案：{','.join(selected_codes) if selected_codes else answer_ids}")

    sleep_random()
    submit_data = activity_execute(activity_token, "submitLevelAnswer", {"answerList": answer_ids})
    stats = extract_level_stats(submit_data)
    if stats.get("correct") is True:
        point = stats.get("correctPoint") or stats.get("prizePointCode") or "-"
        log(f"小怪兽挑战成功，获得积分：{point}")
        sleep_random()
        after_progress = extract_progress_data(activity_execute(activity_token, "checkLevelProgress"))
        if after_progress:
            log(
                "小怪兽挑战后进度："
                f"当前关卡 {after_progress.get('currentLevel', '-')}，"
                f"下次等待 {format_seconds(after_progress.get('nextLevelTimeLeft'))}"
            )
        return True

    if stats.get("correct") is False:
        log(f"小怪兽答题未通过：{stats.get('encourageWord') or stats.get('referenceAnswer') or stats}")
        return False

    log(f"小怪兽提交答案后未识别结果：{submit_data}")
    return False


def get_summary(token: str) -> Optional[dict]:
    data = api_get("/member/summary", token)
    if not is_success(data):
        return None
    return data.get("data") or {}


def get_month_first_day() -> str:
    now = datetime.now()
    return f"{now.year}-{now.month:02d}-01"


def get_sign_list(token: str) -> Optional[dict]:
    data = api_get("/point/sign/list", token, {"statDate": get_month_first_day()})
    if not is_success(data):
        log(f"获取签到列表失败：{data}")
        return None
    return data.get("data") or {}


def today_signed(token: str) -> bool:
    sign_data = get_sign_list(token)
    if not sign_data:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    for item in sign_data.get("signResults") or []:
        if item.get("date") == today:
            return item.get("flag") == 1
    return False


def do_sign(token: str) -> Tuple[bool, str]:
    data = api_post("/point/sign", token, params={"edition": "Child"}, payload={})
    if is_success(data):
        return True, f"获得积分：{data.get('data')}"
    message = (data or {}).get("message") or str(data)
    return False, message


def parse_accounts() -> List[Tuple[str, str]]:
    raw = os.getenv("WX_ID", "")
    accounts: List[Tuple[str, str]] = []
    for line in raw.replace("&", "\n").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "#" not in line:
            continue
        # 兼容两种格式：wxid#备注 或 备注#wxid
        parts = line.split("#", 1)
        part_a, part_b = parts[0].strip(), parts[1].strip()
        if part_b.startswith("wxid_") and not part_a.startswith("wxid_"):
            alias, wxid = part_a, part_b
        else:
            alias, wxid = part_b, part_a
        if alias and wxid:
            accounts.append((alias, wxid))
    return accounts


def get_valid_token(alias: str, wxid: str, tokens_cache: Dict[str, Dict[str, str]]) -> Optional[str]:
    token_info = tokens_cache.get(alias) or {}
    token = token_info.get("token", "")
    if token and get_summary(token):
        log(f"缓存 token 有效：{mask(token)}")
        return token

    code = get_code(wxid)
    if not code:
        return None
    log(f"获取微信 code 成功：{mask(code, 10, 4)}")

    sleep_random()
    login_data = login_with_code(code)
    if not login_data:
        return None

    token = login_data["token"]
    tokens_cache[alias] = {
        "token": token,
        "wxid": wxid,
        "openid": login_data.get("openid", ""),
        "unionid": login_data.get("unionid", ""),
        "type": login_data.get("type", ""),
        "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_tokens(tokens_cache)
    log(f"登录成功：{mask(token)}，用户类型：{login_data.get('type', '-')}")
    return token


def process_account(alias: str, wxid: str, tokens_cache: Dict[str, Dict[str, str]], idx: int, total: int) -> bool:
    log(f"\n========== 账号 {idx}/{total}：{alias} ==========")
    token = get_valid_token(alias, wxid, tokens_cache)
    if not token:
        log("账号处理失败：未获得有效 token")
        return False

    summary_before = get_summary(token) or {}
    points_before = summary_before.get("points")
    log(f"当前积分：{points_before if points_before is not None else '-'}")

    sleep_random()
    if today_signed(token):
        log("今日已签到，跳过")
        sign_ok = True
    else:
        sleep_random()
        sign_ok, detail = do_sign(token)
        if not sign_ok:
            log(f"签到失败：{detail}")
        else:
            log(f"签到成功，{detail}")

    sleep_random()
    monster_ok = run_monster_task(token)

    sleep_random()
    summary_after = get_summary(token) or {}
    points_after = summary_after.get("points")
    if points_after is not None:
        log(f"任务后积分：{points_after}")
    return sign_ok and monster_ok


def push_notification(success_count: int, total: int) -> None:
    try:
        notify_send("雀巢健康科学会员签到结果", "\n".join(log_messages))
        print("消息推送完成")
    except Exception as exc:
        print(f"推送异常：{exc}")


def main() -> None:
    print("雀巢健康科学会员小程序每日签到")
    print(f"运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    accounts = parse_accounts()
    if not accounts:
        print("未找到账号变量，请配置环境变量 WX_ID，格式：wxid#别名")
        return

    print(f"账号数量：{len(accounts)}")
    tokens_cache = load_tokens()

    success_count = 0
    for idx, (alias, wxid) in enumerate(accounts, 1):
        try:
            if process_account(alias, wxid, tokens_cache, idx, len(accounts)):
                success_count += 1
        except Exception as exc:
            log(f"账号 {alias} 异常：{exc}")
        if idx < len(accounts):
            wait = random.uniform(2.0, 4.0)
            log(f"等待 {wait:.1f} 秒后处理下一个账号")
            time.sleep(wait)

    log(f"\n全部处理完成：成功 {success_count}/{len(accounts)}")
    push_notification(success_count, len(accounts))


if __name__ == "__main__":
    main()
