# cron: 57 8,16 * * *
#!/usr/bin/env python3
# name: 嘉立创
# -*- coding: utf-8 -*-

"""
JLC 小程序签到脚本（青龙面板版 / 多账号 / 推送 / 查询豆豆总数）
【环境变量】
- WX_ID / JLC:  账号配置，格式：wxid#备注，多账号用换行或 & 分隔
- WECHAT_SERVER: 微信协议服务地址，默认：http://192.168.31.196:8787
【依赖】
- requests
【第七天逻辑说明】
- 状态接口返回 data.day == 7 且 haveSignIn==True 且 haveReceive==False 时，
  自动调用 receiveVoucher 领取"8 豆豆"。
"""

import os
import sys
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ===================== 通知推送 =====================
try:
    from notify import send as notify_send
except ImportError:
    def notify_send(title, content):
        print(f"--- 通知 ---\n{title}\n{content}\n-------------")

# 日志收集
log_lines = []
SCRIPT_NAME = "JLC 嘉立创签到"
# ===================================================

# ===================== 手动调试开关 =====================
DEBUG = False
DEBUG_ENV = {
    "JLC": "wxid_xxxxxxxx#测试号",
    "WECHAT_SERVER": "http://192.168.31.196:8787",
}
if DEBUG:
    for _k, _v in DEBUG_ENV.items():
        os.environ.setdefault(_k, _v)
    print("⚠️ 调试模式已开启（DEBUG=True），使用脚本内置 DEBUG_ENV 配置")
# =======================================================

BASE_URL = "https://m.jlc.com"
PLATFORM_TYPE = os.getenv("JLC_PLATFORM_TYPE", "MP-WEIXIN").strip()
SOURCE = os.getenv("JLC_SOURCE", "2").strip()

# 微信协议服务地址
DEFAULT_WECHAT_SERVER = "http://192.168.31.196:8787"
WECHAT_SERVER = os.getenv("WECHAT_SERVER", DEFAULT_WECHAT_SERVER).strip().rstrip("/")
WX_AUTH = os.getenv("WX_ID", "")

# 嘉立创小程序 appid
JLC_MINI_APPID = os.getenv("JLC_MINI_APPID", "wx6c7b851c877dba42").strip()
# secretkey 固定值
DEFAULT_SECRET_KEY = "34343232636134362d646135612d346335662d386464382d356237633937623132413437"

# Token 缓存路径
TOKEN_CACHE_PATH = Path(__file__).with_name("JLC_token_cache.json")

# 默认 UA
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF"
)

session = requests.Session()


def read_token_cache():
    try:
        if not TOKEN_CACHE_PATH.exists():
            return {}
        return json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def write_token_cache(cache):
    try:
        TOKEN_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ 写入token缓存失败: {e}")


def mask_token(token):
    if not token:
        return ""
    return f"{token[:6]}***{token[-6:]}"


# ===================== 登录相关 =====================
import getCode


def get_wx_code(account_id):
    """通过微信协议服务获取小程序 code"""
    try:
        return getCode.get_single_code(JLC_MINI_APPID, account_id)
    except Exception as e:
        raise RuntimeError(f"获取code失败: {e}")


def _extract_login_auth(resp):
    """兼容从响应头或 JSON 响应体读取登录凭据。"""
    token = resp.headers.get("X-Jlc-Accesstoken") or resp.headers.get("x-jlc-accesstoken")
    secret = resp.headers.get("secretkey") or resp.headers.get("Secretkey") or DEFAULT_SECRET_KEY
    try:
        payload = resp.json()
    except (ValueError, TypeError):
        payload = {}

    candidates = [payload]
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        candidates.insert(0, payload["data"])
    for item in candidates:
        if not isinstance(item, dict):
            continue
        token = token or item.get("accessToken") or item.get("token") or item.get("access_token")
        secret = item.get("secretkey") or item.get("secretKey") or secret

    if token and str(token).upper() != "NONE":
        return str(token), str(secret)
    return None, None


def login_with_code(account_id):
    """使用一次性 code 登录；按小程序常见请求格式依次兼容。"""
    url = BASE_URL + "/api/login/login-by-code"
    headers = {
        "accept": "application/json, text/plain, */*",
        "referer": f"https://servicewechat.com/{JLC_MINI_APPID}/141/page-frame.html",
        "X-JLC-AccessToken": "NONE",
        "X-JLC-ClientType": "MP-WEIXIN",
        "X-JLC-MP-AppId": JLC_MINI_APPID,
        "X-JLC-MP-Env": os.getenv("JLC_MP_ENV", "release"),
        "X-JLC-MP-Version": os.getenv("JLC_MP_VERSION", "1.113.0"),
        "secretkey": DEFAULT_SECRET_KEY,
        "xweb_xhr": "1",
        "user-agent": DEFAULT_UA,
    }

    # wx.request 默认发送 JSON。旧脚本使用 multipart，服务端升级后可能不再兼容；
    # 每次重试必须重新获取 code，因为 wx.login code 只能使用一次。
    attempts = (
        ("JSON", lambda code: {"json": {"code": code}}),
        ("表单", lambda code: {"data": {"code": code}}),
        ("multipart", lambda code: {"files": {"code": (None, code)}}),
    )
    errors = []
    for mode, build_request in attempts:
        try:
            code = get_wx_code(account_id)
            resp = session.post(url, headers=headers, timeout=30, **build_request(code))
            token, secret = _extract_login_auth(resp)
            if token:
                print(f"[{account_id}] login-by-code 登录成功（{mode}）")
                return {
                    "token": token,
                    "secret": secret,
                    "updatedAt": int(time.time()),
                }
            body = resp.text.replace("\r", " ").replace("\n", " ")[:300]
            detail = f"{mode}: status={resp.status_code}, body={body}"
            errors.append(detail)
            print(f"[{account_id}] login-by-code 未通过（{detail}）")
        except Exception as e:
            detail = f"{mode}: 请求异常={e}"
            errors.append(detail)
            print(f"[{account_id}] login-by-code {detail}")

    raise RuntimeError("code登录失败；" + "；".join(errors))


def get_cached_token(account_id):
    return read_token_cache().get(account_id)


def save_cached_token(account_id, auth_info):
    cache = read_token_cache()
    cache[account_id] = auth_info
    write_token_cache(cache)


def remove_cached_token(account_id):
    cache = read_token_cache()
    if account_id in cache:
        del cache[account_id]
        write_token_cache(cache)


def validate_token(token):
    """验证 token 是否有效"""
    try:
        url = BASE_URL + "/api/activity/sign/getCurrentUserSignInConfig"
        headers = {
            "x-jlc-accesstoken": token,
            "secretkey": DEFAULT_SECRET_KEY,
            "user-agent": DEFAULT_UA,
        }
        resp = session.get(url, params={"platformType": PLATFORM_TYPE}, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("success") is True
        return False
    except Exception:
        return False


def get_token_for_account(account_id, remark):
    """获取账号的 token（优先使用缓存）"""
    cached = get_cached_token(account_id)
    if cached and cached.get("token"):
        print(f"[{remark}] 使用缓存token: {mask_token(cached['token'])}")
        if validate_token(cached["token"]):
            return cached["token"], cached.get("secret", DEFAULT_SECRET_KEY)
        print(f"[{remark}] 缓存token失效，重新登录")
        remove_cached_token(account_id)

    auth_info = login_with_code(account_id)
    save_cached_token(account_id, auth_info)
    print(f"[{remark}] 登录成功")
    return auth_info["token"], auth_info.get("secret", DEFAULT_SECRET_KEY)


# ===================== 工具函数 =====================


def _env(key: str, default: str = "") -> str:
    v = os.environ.get(key, "")
    v = v.strip()
    return v if v else default


def _split_accounts(s: str) -> List[str]:
    """支持 & 或换行 分隔"""
    if not s:
        return []
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    parts: List[str] = []
    for chunk in s.split("\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts.extend([p.strip() for p in chunk.split("&") if p.strip()])
    return parts


def parse_accounts() -> List[Dict[str, str]]:
    """
    账号解析：
    - WX_ID / JLC（推荐）：wxid#备注，通过微信协议服务自动登录换 token
    """
    remarks_raw = _env("JLC_REMARKS")
    remarks = _split_accounts(remarks_raw)
    accounts: List[Dict[str, str]] = []

    # 1) wxid 自动登录模式（推荐）
    wxid_raw = os.getenv("WX_ID") or os.getenv("JLC", "")
    if wxid_raw:
        items = _split_accounts(wxid_raw)
        for idx, item in enumerate(items):
            if "#" in item:
                wxid, remark = item.split("#", 1)
                wxid, remark = wxid.strip(), remark.strip()
            else:
                wxid, remark = item.strip(), ""
            if not wxid:
                continue
            accounts.append({
                "mode": "wxid",
                "wxid": wxid,
                "remark": remark or (remarks[idx] if idx < len(remarks) else f"账号{idx+1}"),
            })
        if accounts:
            return accounts

    # 兼容旧的 JLC_AUTH 模式
    auth_raw = _env("JLC_AUTH")
    if auth_raw:
        items = _split_accounts(auth_raw)
        for idx, item in enumerate(items):
            sep = "#" if "#" in item else ("|" if "|" in item else ("," if "," in item else None))
            if not sep:
                raise RuntimeError("JLC_AUTH 格式错误，应为 token#secret（多账号用 & 或换行分隔）。")
            token, secret = item.split(sep, 1)
            token, secret = token.strip(), secret.strip()
            if not token or not secret:
                raise RuntimeError("JLC_AUTH 中存在空的 token 或 secret。")
            accounts.append({
                "mode": "token",
                "token": token,
                "secret": secret,
                "remark": remarks[idx] if idx < len(remarks) else f"账号{idx+1}",
            })
        return accounts

    raise RuntimeError("缺少环境变量：请设置 WX_ID 或 JLC（推荐）或 JLC_AUTH。")


def build_headers(token: str, secret: str) -> Dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "x-jlc-accesstoken": token,
        "secretkey": secret,
        "origin": BASE_URL,
        "referer": BASE_URL + "/",
        "user-agent": DEFAULT_UA,
    }
    return {k: v for k, v in headers.items() if v}


def api_get(session: requests.Session, path: str, params: Optional[Dict[str, Any]] = None, 
            token: str = "", secret: str = "") -> Dict[str, Any]:
    url = BASE_URL + path
    headers = build_headers(token, secret) if token else {}
    r = session.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"接口返回非 JSON：{url}\n{r.text[:300]}")


def get_sign_status(s, token, secret) -> Dict[str, Any]:
    return api_get(s, "/api/activity/sign/getCurrentUserSignInConfig", 
                   params={"platformType": PLATFORM_TYPE}, token=token, secret=secret)


def do_signin(s, token, secret) -> Dict[str, Any]:
    return api_get(s, "/api/activity/sign/signIn", 
                   params={"platformType": PLATFORM_TYPE, "source": SOURCE}, token=token, secret=secret)


def receive_voucher(s, token, secret) -> Dict[str, Any]:
    return api_get(s, "/api/activity/sign/receiveVoucher", 
                   params={"platformType": PLATFORM_TYPE}, token=token, secret=secret)


def get_doudou_total(s, token, secret) -> Dict[str, Any]:
    return api_get(s, "/api/activity/front/getCustomerIntegral", token=token, secret=secret)


def try_send_notify(title: str, content: str) -> None:
    """青龙通知（兼容）"""
    try:
        notify_send(title, content)
    except Exception as e:
        print(f"（推送失败：{e}）")


def format_line(ok: bool, text: str) -> str:
    return ("✅ " if ok else "❌ ") + text


def _extract_streak_day(st_data: Dict[str, Any]) -> Optional[int]:
    for k in ("day", "continuousDay", "continueDay", "signDay"):
        v = st_data.get(k)
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None


def run_one_account(idx: int, remark: str, token: str, secret: str) -> Tuple[bool, str, Dict[str, Any]]:
    result: Dict[str, Any] = {
        "remark": remark,
        "signed": None,
        "gain_signin": None,
        "gain_day7": None,
        "total": None,
        "expireTime": None,
        "streak_day": None,
    }

    log_lines: List[str] = []
    ok_all = True

    with requests.Session() as s:
        # 1) 查状态
        st = get_sign_status(s, token, secret)
        if not st.get("success", False):
            ok_all = False
            log_lines.append(format_line(False, f"[{remark}] 查询签到状态失败：{json.dumps(st, ensure_ascii=False)}"))
            return ok_all, "\n".join(log_lines), result

        st_data = st.get("data") or {}
        have_signin = st_data.get("haveSignIn") is True
        have_receive = st_data.get("haveReceive") is True
        streak_day = _extract_streak_day(st_data)
        result["streak_day"] = streak_day

        if streak_day is not None:
            log_lines.append(format_line(True, f"[{remark}] 当前连续签到天数：{streak_day} 天"))
        else:
            log_lines.append(format_line(True, f"[{remark}] 当前连续签到天数：未知"))

        # 2) 签到（若未签）
        if have_signin:
            result["signed"] = True
            log_lines.append(format_line(True, f"[{remark}] 今日已签到"))
        else:
            si = do_signin(s, token, secret)
            if not si.get("success", False):
                ok_all = False
                result["signed"] = False
                log_lines.append(format_line(False, f"[{remark}] 签到失败：{json.dumps(si, ensure_ascii=False)}"))
            else:
                si_data = si.get("data") or {}
                gain = si_data.get("gainNum") or 0
                result["signed"] = True
                result["gain_signin"] = gain
                log_lines.append(format_line(True, f"[{remark}] 签到成功，本次获得：{gain} 豆豆"))

                # 签到后刷新状态
                st2 = get_sign_status(s, token, secret)
                if st2.get("success", False):
                    st_data = st2.get("data") or {}
                    have_signin = st_data.get("haveSignIn") is True
                    have_receive = st_data.get("haveReceive") is True
                    streak_day = _extract_streak_day(st_data)
                    result["streak_day"] = streak_day

        # 3) 第七天领取 8 豆豆
        if streak_day == 7 and have_signin and (not have_receive):
            log_lines.append(format_line(True, f"[{remark}] 检测到连续签到第 7 天且未领取，开始领取..."))
            rv = receive_voucher(s, token, secret)
            if not rv.get("success", False):
                ok_all = False
                log_lines.append(format_line(False, f"[{remark}] 第七天领取失败：{json.dumps(rv, ensure_ascii=False)}"))
            else:
                got = rv.get("data")
                result["gain_day7"] = got
                log_lines.append(format_line(True, f"[{remark}] 第七天领取成功：+{got} 豆豆"))
        elif streak_day == 7 and have_signin and have_receive:
            log_lines.append(format_line(True, f"[{remark}] 连续签到第 7 天奖励已领取"))

        # 4) 查豆豆总数
        ct = get_doudou_total(s, token, secret)
        if not ct.get("success", False):
            ok_all = False
            log_lines.append(format_line(False, f"[{remark}] 查询豆豆总数失败：{json.dumps(ct, ensure_ascii=False)}"))
        else:
            data = ct.get("data") or {}
            total = data.get("integralVoucher")
            expire_time = data.get("expireTime")
            result["total"] = total
            result["expireTime"] = expire_time
            extra = f"，有效期至：{expire_time}" if expire_time else ""
            log_lines.append(format_line(True, f"[{remark}] 当前豆豆总数：{total}{extra}"))

    return ok_all, "\n".join(log_lines), result


def main() -> int:
    global log_lines
    
    accounts = parse_accounts()
    any_fail = False

    log_lines.append(f"\n{' ' * 5}{SCRIPT_NAME}")
    log_lines.append("-------- 开 始 执 行 --------")
    log_lines.append(f"账号数量：{len(accounts)}")
    print(f"\n{' ' * 5}{SCRIPT_NAME}")
    print("-------- 开 始 执 行 --------")
    print(f"账号数量：{len(accounts)}")

    for idx, acc in enumerate(accounts, start=1):
        remark = acc["remark"]

        log_lines.append(f"\n📋 账号 [{idx}/{len(accounts)}]")
        log_lines.append(f"📋 当前账号：{remark or f'账号{idx}'}")
        print(f"\n📋 账号 [{idx}/{len(accounts)}]")
        print(f"📋 当前账号：{remark or f'账号{idx}'}")

        # wxid 模式：先用微信协议服务登录换取 token
        if acc.get("mode") == "wxid":
            try:
                token, secret = get_token_for_account(acc["wxid"], remark)
                log_lines.append("✅ 登录成功")
            except Exception as e:
                any_fail = True
                log_lines.append(format_line(False, f"❌ 登录失败: {e}"))
                print(format_line(False, f"❌ 登录失败: {e}"))
                if idx < len(accounts):
                    time.sleep(2)
                continue
        else:
            token, secret = acc["token"], acc["secret"]
            log_lines.append("📌 手动模式，跳过登录")

        ok, log_text, res = run_one_account(idx, remark, token, secret)
        log_lines.append(log_text)

        if not ok:
            any_fail = True

        # 账号间延迟
        if idx < len(accounts):
            time.sleep(2)

    log_lines.append("\n-------- 执 行 结 束 --------")
    print("\n-------- 执 行 结 束 --------")

    # 推送完整日志
    try:
        notify_send(f"{SCRIPT_NAME} 运行日志", "\n".join(log_lines))
    except Exception:
        pass

    return 1 if any_fail else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("❌ 脚本异常：", str(e))
        traceback.print_exc()
        try_send_notify("JLC 签到脚本异常", str(e))
        sys.exit(1)
