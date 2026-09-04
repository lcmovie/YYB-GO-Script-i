#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
name: 京东快递签到
cron: 17 8 * * *

青龙环境变量：
  YYB_SERVER  YYB-Go-Enhanced 地址@账号标识，多账号每行一条
              例：yyb-go:8000@1
  JDEXPRESS_NOTIFY  1 推送（默认），0 关闭推送
  JDEXPRESS_ACCOUNT_LIMIT  可选，仅运行前 N 个账号（用于测试）
  JDEXPRESS_REF_FILTER  可选，仅运行指定账号标识（用于测试）

依赖：requests（青龙“依赖管理”中安装 Python3 依赖 requests）
通知：优先使用青龙内置 notify.py，兼容仓库 SendNotify.py

更新日志：
  2026-09-04 v1.0  依据手机微信真实 HAR 实现登录、签到、奖励核算和通知
  2026-09-04 v1.1  登录改用 YYB-Go + 京东 PT OAuth 跳转链，修复无 pt_key/pt_pin
  2026-09-04 v1.2  增加全参数登录回退，区分未绑定京东账号与风控账号
"""

import html
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse

import requests


APP_NAME = "京东快递签到"
APP_ID = "wx73247c7819d61796"
JD_PT_APP_ID = "wx2f5d8f9715c59d10"
JD_PT_APP = "300"
JD_PT_RETURN_URL = "https://my.m.jd.com/account/index.html"
JD_LOGIN_APP_ID = "wx91d27dbf599dff74"
API_BASE = "https://lop-proxy.jd.com"
TIMEOUT = 20
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.73 NetType/WIFI Language/zh_CN "
    f"miniProgram/{APP_ID}"
)


def log(message: str) -> None:
    print(message, flush=True)


def parse_accounts() -> List[Tuple[str, str]]:
    raw = os.getenv("YYB_SERVER", "")
    accounts: List[Tuple[str, str]] = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        value = line.strip()
        if not value:
            continue
        if "@" not in value:
            log(f"❌ YYB_SERVER 第 {line_no} 行缺少 @，已跳过")
            continue
        server, ref = value.rsplit("@", 1)
        server, ref = server.strip().rstrip("/"), ref.strip()
        if not server or not ref:
            log(f"❌ YYB_SERVER 第 {line_no} 行地址或账号标识为空，已跳过")
            continue
        if not server.startswith(("http://", "https://")):
            server = "http://" + server
        accounts.append((server, ref))
    return accounts


def get_wx_code(server: str, ref: str, app_id: str = APP_ID) -> str:
    response = requests.post(
        f"{server}/wxapp/getCode",
        json={"ref": ref, "app_id": app_id},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    result = ((payload.get("data") or {}).get("result") or {})
    code = result.get("code") if isinstance(result, dict) else None
    if payload.get("code") != 0 or not isinstance(code, str) or len(code) < 8:
        keys = ",".join(sorted(str(key) for key in result.keys())) if isinstance(result, dict) else type(result).__name__
        detail = result.get("errMsg") if isinstance(result, dict) else ""
        raise RuntimeError(f"YYB-Go 未返回有效 code：{detail or payload.get('msg') or payload.get('code')}；result字段={keys}")
    return code


def extract_pt_cookie(session: requests.Session, payload: Any) -> str:
    values = session.cookies.get_dict()
    pt_key, pt_pin = values.get("pt_key"), values.get("pt_pin")
    if isinstance(payload, dict):
        pt_key = pt_key or payload.get("pt_key") or payload.get("ptKey")
        pt_pin = pt_pin or payload.get("pt_pin") or payload.get("ptPin")
        data = payload.get("data") or payload.get("result") or {}
        if isinstance(data, dict):
            pt_key = pt_key or data.get("pt_key") or data.get("ptKey")
            pt_pin = pt_pin or data.get("pt_pin") or data.get("ptPin")
    if not pt_key or not pt_pin:
        return ""
    return f"pt_key={pt_key}; pt_pin={pt_pin};"


def yyb_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg") or f"YYB-Go 返回 code={payload.get('code')}")
    data = payload.get("data") or {}
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError("YYB-Go 返回缺少 data.result")
    return result


def nested_text(value: Any, names: Tuple[str, ...]) -> str:
    wanted = {name.lower() for name in names}
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in wanted and item not in (None, ""):
                return str(item)
        for item in value.values():
            found = nested_text(item, names)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = nested_text(item, names)
            if found:
                return found
    return ""


def follow_acrj(session: requests.Session, payload: Dict[str, Any]) -> str:
    current = nested_text(payload, ("ACRJUrl", "acrjUrl"))
    state = nested_text(payload, ("ACRJState", "acrjState"))
    if not current:
        return ""
    if current.startswith("//"):
        current = "https:" + current
    elif current.startswith("/"):
        current = "https://wq.jd.com" + current
    if state and "ACRJState=" not in current:
        parsed = urlparse(current)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.append(("ACRJState", state))
        current = urlunparse(parsed._replace(query=urlencode(query)))
    for _ in range(8):
        if not allowed_jd_url(current):
            raise RuntimeError("ACRJ 刷新地址不是受信任的京东 HTTPS 域名")
        response = session.get(current, allow_redirects=False, timeout=TIMEOUT)
        cookie = extract_pt_cookie(session, {})
        if cookie:
            return cookie
        location = response.headers.get("Location", "")
        if not location or response.status_code not in {301, 302, 303, 307, 308}:
            break
        current = urljoin(current, location)
    return extract_pt_cookie(session, {})


def get_yyb_user_info(server: str, ref: str) -> Dict[str, str]:
    response = requests.post(
        f"{server}/wxapp/operateWxData",
        json={
            "ref": ref,
            "app_id": JD_LOGIN_APP_ID,
            "payload": {"api_name": "getUserInfo", "data": {"withCredentials": True}, "env": 1},
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    result = yyb_result(response.json())
    raw_data = result.get("rawData") or result.get("raw_data") or result.get("data")
    if isinstance(raw_data, (dict, list)):
        raw_data = json.dumps(raw_data, ensure_ascii=False, separators=(",", ":"))
    user_info = result.get("userInfo") or result.get("user_info")
    if not raw_data and isinstance(user_info, dict):
        raw_data = json.dumps(user_info, ensure_ascii=False, separators=(",", ":"))
    if not raw_data:
        direct_info = {
            key: result[key]
            for key in ("nickName", "gender", "language", "city", "province", "country", "avatarUrl")
            if key in result and result[key] is not None
        }
        if direct_info:
            raw_data = json.dumps(direct_info, ensure_ascii=False, separators=(",", ":"))
    encrypted = result.get("encryptedData") or result.get("encrytData") or result.get("encrypted_data")
    info = {
        "rawData": str(raw_data or ""),
        "signature": str(result.get("signature") or ""),
        "encryptedData": str(encrypted or ""),
        "iv": str(result.get("iv") or ""),
        "openid": str(result.get("openid") or ""),
    }
    missing = [key for key in ("rawData", "signature", "encryptedData", "iv") if not info[key]]
    if missing:
        keys = ",".join(sorted(str(key) for key in result.keys()))
        raise RuntimeError("YYB-Go getUserInfo 缺少字段：" + ",".join(missing) + f"；返回字段={keys}")
    return info


def full_jd_login(server: str, ref: str) -> Tuple[requests.Session, str]:
    code = get_wx_code(server, ref, JD_LOGIN_APP_ID)
    info = get_yyb_user_info(server, ref)
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "User-Agent": UA,
        "Referer": f"https://servicewechat.com/{JD_LOGIN_APP_ID}/873/page-frame.html",
        "Accept": "application/json, text/plain, */*",
    })
    params = {
        "appid": JD_LOGIN_APP_ID,
        "code": code,
        "type": "silent",
        "isPopup": "false",
        "isIgnoreCookie": "false",
        "isOfficialPin": "false",
        "loginColor": "{}",
        "returnUrl": "pages/my/index/index",
        "deviceName": "iPhone",
        "deviceOS": "iOS",
        "deviceOSVersion": "17.0",
        "deviceVersion": "8.0.49",
        "g_tk": "0",
        "g_ty": "ls",
        "rawData": info["rawData"],
        "signature": info["signature"],
        "encrytData": info["encryptedData"],
        "encryptedData": info["encryptedData"],
        "iv": info["iv"],
        "ou": info["openid"],
    }
    response = session.get(
        "https://wq.jd.com/mlogin/wxapp/login_lt",
        params=params,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        start, end = text.find("{"), text.rfind("}")
        try:
            payload = json.loads(text[start:end + 1]) if start >= 0 and end > start else {}
        except ValueError:
            payload = {}
    cookie = extract_pt_cookie(session, payload)
    if not cookie:
        cookie = follow_acrj(session, payload)
    if not cookie:
        message = nested_text(payload, ("errmsg", "errMsg", "retMsg", "message", "msg"))
        fields = ",".join(sorted(str(key) for key in payload.keys()))
        ret_code = nested_text(payload, ("retCode", "code"))
        if ret_code == "201" or "pin not exist" in message.lower():
            raise RuntimeError("该微信账号未绑定京东账号，请先在京东快递小程序完成登录/绑定（retCode=201）")
        if ret_code == "202" or "risk user" in message.lower():
            raise RuntimeError("京东判定该账号存在风险，请先在京东快递小程序完成安全验证（retCode=202）")
        suffix = f"；retCode={ret_code}" if ret_code else ""
        raise RuntimeError((message or "京东全参数登录未返回 pt_key/pt_pin") + suffix + f"；响应字段={fields}")
    session.headers.update(business_headers(cookie))
    pin = unquote(session.cookies.get("pt_pin") or cookie.split("pt_pin=", 1)[1].split(";", 1)[0])
    return session, pin


def allowed_jd_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "jd.com" or host.endswith(".jd.com")
        or host == "jd.hk" or host.endswith(".jd.hk")
        or host == "3.cn" or host.endswith(".3.cn")
    )


def html_redirect(base_url: str, body: str) -> str:
    text = html.unescape(str(body or ""))
    patterns = (
        r'<meta[^>]+url\s*=\s*["\']?([^"\' >]+)',
        r'(?:window\.)?location(?:\.href)?\s*=\s*["\']([^"\']+)',
        r'location\.(?:replace|assign)\s*\(\s*["\']([^"\']+)',
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return urljoin(base_url, match.group(1).strip())
    return ""


def login(server: str, ref: str) -> Tuple[requests.Session, str]:
    try:
        code = get_wx_code(server, ref, JD_PT_APP_ID)
    except Exception as exc:
        log(f"⚠️ JD PT 专用 code 不可用（{exc}），改用全参数登录")
        return full_jd_login(server, ref)
    session = requests.Session()
    session.trust_env = False
    session.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })

    entry = session.get(
        "https://plogin.m.jd.com/user/login.action",
        params={"appid": JD_PT_APP, "returnurl": JD_PT_RETURN_URL},
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    location = entry.headers.get("Location", "")
    if entry.status_code not in range(300, 400) or not location:
        raise RuntimeError(f"JD PT login.action 未跳转：HTTP {entry.status_code}")
    oauth_url = urljoin(entry.url, location)
    query = parse_qs(urlparse(oauth_url).query, keep_blank_values=True)
    if query.get("appid", [""])[0] != JD_PT_APP_ID:
        raise RuntimeError("JD PT OAuth appid 不匹配")
    redirect_uri = query.get("redirect_uri", [""])[0]
    state = query.get("state", [""])[0]
    if not redirect_uri or not state:
        raise RuntimeError("JD PT OAuth 缺少 redirect_uri/state")

    callback = urlparse(redirect_uri)
    callback_query = parse_qsl(callback.query, keep_blank_values=True)
    callback_query.extend([("code", code), ("state", state)])
    current = urlunparse(callback._replace(query=urlencode(callback_query)))
    cookie = ""
    last_status = 0
    for _ in range(8):
        if not allowed_jd_url(current):
            raise RuntimeError("JD PT 跳转超出允许的京东域名")
        response = session.get(current, allow_redirects=False, timeout=TIMEOUT)
        last_status = response.status_code
        cookie = extract_pt_cookie(session, {})
        if cookie:
            break
        location = response.headers.get("Location", "")
        if not location and response.status_code == 200:
            location = html_redirect(current, response.text)
        if not location or response.status_code not in {200, 301, 302, 303, 307, 308}:
            break
        current = urljoin(current, location)
    if not cookie:
        names = ",".join(sorted(session.cookies.get_dict().keys())) or "无"
        log(f"⚠️ JD PT 跳转链未完成（HTTP {last_status}，Cookie字段={names}），改用全参数登录")
        return full_jd_login(server, ref)
    session.headers.update(business_headers(cookie))
    return session, unquote(session.cookies.get("pt_pin") or cookie.split("pt_pin=", 1)[1].split(";", 1)[0])


def business_headers(cookie: str) -> Dict[str, str]:
    return {
        "Cookie": cookie,
        "User-Agent": UA,
        "Referer": "https://jingcai-h5.jd.com/",
        "Origin": "https://jingcai-h5.jd.com",
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "app-key": "jexpress",
        "appparams": '{"appid":158,"ticket_type":"m"}',
        "clientinfo": '{"appName":"jingcai","client":"m"}',
        "biz-type": "service-monitor",
        "access": "H5",
        "lop-dn": "jingcai.jd.com",
        "sdkversion": "1.0.7",
        "source-client": "2",
        "forcebot": "0",
        "screen": "428*926",
        "event-id": str(uuid.uuid4()),
    }


def api_post(session: requests.Session, path: str, body: Any) -> Dict[str, Any]:
    session.headers["event-id"] = str(uuid.uuid4())
    response = session.post(API_BASE + path, json=body, timeout=TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") is not True or payload.get("code") != 1:
        raise RuntimeError(payload.get("errorMsg") or payload.get("msg") or f"接口返回 code={payload.get('code')}")
    content = payload.get("content")
    return content if isinstance(content, dict) else {"value": content}


def query_balance(session: requests.Session, pin: str) -> Dict[str, int]:
    content = api_post(session, "/JingIntegralApi/userAccount", [{"pin": pin}])
    return {
        "jdBean": int(content.get("jdBean") or 0),
        "integral": int(content.get("integral") or 0),
    }


def query_calendar(session: requests.Session) -> Dict[str, Any]:
    return api_post(session, "/jiFenApi/signInList", [{"userNo": ""}])


def today_item(calendar: Dict[str, Any]) -> Dict[str, Any]:
    for item in calendar.get("dayList") or []:
        if isinstance(item, dict) and item.get("isToday") is True:
            return item
    return {}


def coupon_reward(item: Dict[str, Any]) -> Optional[str]:
    reward = item.get("rewardDto") or {}
    batch = reward.get("batchInfo") or {}
    if not item.get("existReward") or not isinstance(batch, dict):
        return None
    name = batch.get("restrictedCopy") or batch.get("activityName") or batch.get("remark")
    count = int(batch.get("sendNum") or 1)
    return f"{name} ×{count}" if name else f"优惠券 ×{count}"


def reward_summary(before: Dict[str, int], after: Dict[str, int], item: Dict[str, Any]) -> str:
    rewards: List[str] = []
    bean_delta = after["jdBean"] - before["jdBean"]
    integral_delta = after["integral"] - before["integral"]
    if bean_delta > 0:
        rewards.append(f"京豆 +{bean_delta}")
    if integral_delta > 0:
        rewards.append(f"积分 +{integral_delta}")
    coupon = coupon_reward(item)
    if coupon:
        rewards.append(coupon)
    return "、".join(rewards) if rewards else "无（京豆/积分未增加，当日无券奖励）"


def mask_ref(ref: str) -> str:
    return ref if ref.isdigit() else (ref[:3] + "***" + ref[-3:] if len(ref) > 8 else "***")


def run_account(index: int, server: str, ref: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"index": index, "ref": mask_ref(ref), "success": False}
    log(f"\n===== 账号 {index} ({result['ref']}) =====")
    session, pin = login(server, ref)
    log("✅ 微信 code 登录成功")
    before = query_balance(session, pin)
    calendar_before = query_calendar(session)
    today_before = today_item(calendar_before)
    already_signed = today_before.get("isCanSignIn") is False and today_before.get("signInType") == 1

    if already_signed:
        after = before
        today_after = today_before
        status = "今日已签到"
        reward = coupon_reward(today_after) or "已签到，接口无法回溯当日普通奖励"
    else:
        api_post(session, "/jiFenApi/signIn", [{
            "signInDate": datetime.now().strftime("%Y-%m-%d"),
            "userNo": "",
        }])
        time.sleep(1)
        after = query_balance(session, pin)
        calendar_after = query_calendar(session)
        today_after = today_item(calendar_after)
        if today_after.get("isCanSignIn") is not False:
            raise RuntimeError("签到接口返回成功，但日历仍显示可签到")
        status = "签到成功"
        reward = reward_summary(before, after, today_after)

    days = calendar_before.get("signedInDay") or 0
    if not already_signed:
        days = (calendar_after.get("signedInDay") or days)
    result.update({
        "success": True,
        "status": status,
        "reward": reward,
        "days": days,
        "balance": after,
    })
    log(f"✅ {status}；今日奖励：{reward}")
    return result


def notify(results: List[Dict[str, Any]]) -> None:
    if os.getenv("JDEXPRESS_NOTIFY", "1").strip().lower() in {"0", "false", "no", "off"}:
        return
    lines = []
    for r in results:
        prefix = f"账号{r['index']}({r['ref']})"
        if r.get("success"):
            b = r["balance"]
            lines.append(
                f"{prefix}：{r['status']}\n"
                f"今日奖励：{r['reward']}\n"
                f"连续签到：{r['days']}天；余额：京豆{b['jdBean']} / 积分{b['integral']}"
            )
        else:
            lines.append(f"{prefix}：失败\n原因：{r.get('error', '未知错误')}")
    content = "\n\n".join(lines)
    try:
        import notify as ql_notify
    except ImportError:
        ql_notify = None
    if ql_notify is not None:
        try:
            ql_notify.send(APP_NAME, content)
            return
        except Exception as exc:
            log(f"⚠️ 青龙 notify.py 发送失败，尝试 SendNotify.py：{exc}")
    try:
        import SendNotify
        if hasattr(SendNotify, "send"):
            SendNotify.send(APP_NAME, content)
        elif hasattr(SendNotify, "send_push_notification"):
            SendNotify.send_push_notification(APP_NAME, content)
        else:
            raise AttributeError("SendNotify 缺少可用发送函数")
    except Exception as exc:
        log(f"⚠️ 通知发送失败：{exc}")


def main() -> int:
    accounts = parse_accounts()
    if not accounts:
        log("❌ 未配置有效 YYB_SERVER，格式：yyb-go:8000@账号ID或OpenID")
        return 1
    ref_filter = os.getenv("JDEXPRESS_REF_FILTER", "").strip()
    if ref_filter:
        accounts = [item for item in accounts if item[1] == ref_filter]
        if not accounts:
            log("❌ JDEXPRESS_REF_FILTER 未匹配任何 YYB_SERVER 账号")
            return 1
    limit_raw = os.getenv("JDEXPRESS_ACCOUNT_LIMIT", "").strip()
    if limit_raw:
        try:
            limit = int(limit_raw)
            if limit > 0:
                accounts = accounts[:limit]
        except ValueError:
            log("⚠️ JDEXPRESS_ACCOUNT_LIMIT 不是有效正整数，已忽略")
    results: List[Dict[str, Any]] = []
    for index, (server, ref) in enumerate(accounts, 1):
        try:
            results.append(run_account(index, server, ref))
        except Exception as exc:
            log(f"❌ 账号 {index} 失败：{exc}")
            results.append({"index": index, "ref": mask_ref(ref), "success": False, "error": str(exc)})
    notify(results)
    ok = sum(1 for r in results if r.get("success"))
    log(f"\n===== 执行完成：成功 {ok}/{len(results)}，失败 {len(results)-ok} =====")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
