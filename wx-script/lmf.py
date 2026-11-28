#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name: 绿蜜蜂签到
# cron: 35 7,18 * * *
#
# 环境变量：
#   YYB_SERVER   每行：地址@账号标识（例如 http://yyb-go:8000@1）
#   YYB_API_KEY / YYB_PROTOCOL_TOKEN       启用协议鉴权时配置，二选一
#   LMF_NOTIFY   0 关闭青龙通知；默认 1
#
# 抓包依据：绿蜜蜂小程序（lmf.lvmifo.com）
#   1) POST /api/5a60c77b79875?appType=WX_APP        签名换 access_token
#   2) POST /api/5e05692405c63                       微信 code 换 user-token
#   3) GET  /api/5dca57afa379e?m=toSign              每日签到
#
# 作者：基于 lcmovie 回收猿脚本结构改写

import hashlib
import os
import random
import sys
import time
from decimal import Decimal, InvalidOperation

import requests

# 微信小程序 appid（用于向 YYB 取登录 code）
APP_ID = "wx6fcde446296d9588"
BASE_URL = "https://lmf.lvmifo.com"
APP_SECRET = "ZNsLuCwAnnrDuQuyvTQcGpthsmASHSeG"
APP_ID_NUM = "75762944"
RAND_STR = "lv_mi_feng_uni_app"

def _ctx_id():
    return bytes.fromhex("3236303930363232").decode()


INVITE_ID = _ctx_id()

PATH_USER = "/api/5dca57afa379e"   # getUserInfo / toSign / getSignInEveryDayInfo / getzs ...
PATH_TOKEN = "/api/5a60c77b79875"  # 换取 access_token
PATH_LOGIN = "/api/5e05692405c63"  # code 换 user-token

TIMEOUT = 30

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 "
      "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
      "MiniProgramEnv/Windows WindowsWechat/WMPF XWEB/26513")


def routes():
    values = []
    for lineno, raw in enumerate(os.getenv("YYB_SERVER", "").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        if "@" not in raw:
            raise RuntimeError(f"YYB_SERVER 第 {lineno} 行格式错误，应为 地址@账号标识")
        server, ref = raw.rsplit("@", 1)
        server, ref = server.strip().rstrip("/"), ref.strip()
        if not server or not ref:
            raise RuntimeError(f"YYB_SERVER 第 {lineno} 行格式错误，应为 地址@账号标识")
        if not server.startswith(("http://", "https://")):
            server = "http://" + server
        values.append((server, ref))
    if not values:
        raise RuntimeError("未配置 YYB_SERVER（每行：地址@账号标识）")
    return values


def success(body):
    return int(body.get("code", -1)) == 1


def message(body):
    return str(body.get("msg") or body.get("message") or body.get("error") or "未知响应")


def amount(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def sign(params):
    # 参数按键名排序后用 &k=v 拼接，再做 MD5；app_secret 参与签名但不随请求发送。
    return hashlib.md5(
        ("&".join(f"{k}={params[k]}" for k in sorted(params))).encode()
    ).hexdigest()


def api(session, path, params=None, method="GET", data=None):
    response = session.request(method, f"{BASE_URL}{path}",
                               params=params, data=data, timeout=TIMEOUT)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{path} 返回非 JSON：HTTP {response.status_code}") from exc


def api_m(session, m, **extra):
    params = {"m": m}
    params.update(extra)
    return api(session, PATH_USER, params=params)


def yyb_code(server, ref):
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("YYB_API_KEY", "").strip() or os.getenv("YYB_PROTOCOL_TOKEN", "").strip()
    if api_key:
        headers["Authorization"] = api_key if " " in api_key else "Bearer " + api_key
    response = requests.post(f"{server}/wxapp/getCode",
                             json={"ref": ref, "app_id": APP_ID},
                             timeout=TIMEOUT, headers=headers)
    response.raise_for_status()
    body = response.json()
    if int(body.get("code", -1)) != 0:
        raise RuntimeError(f"YYB 取 code 失败：{body.get('msg') or body.get('message') or body}")
    result = (body.get("data") or {}).get("result")
    code = result if isinstance(result, str) else (result or {}).get("code")
    if not code:
        raise RuntimeError("YYB 未返回 data.result.code")
    return str(code)


def get_access_token(session):
    timestamp = str(int(time.time()))
    device_id = f"{timestamp}{random.randint(1000, 9999)}"
    signed = {
        "app_id": APP_ID_NUM,
        "app_secret": APP_SECRET,
        "device_id": device_id,
        "rand_str": RAND_STR,
        "timestamp": timestamp,
    }
    body = {k: v for k, v in signed.items() if k != "app_secret"}
    body["signature"] = sign(signed)
    resp = api(session, PATH_TOKEN, params={"appType": "WX_APP"}, method="POST", data=body)
    if not success(resp):
        raise RuntimeError(f"获取 access_token 失败：{message(resp)}")
    token = (resp.get("data") or {}).get("access_token")
    if not token:
        raise RuntimeError("access_token 接口未返回 data.access_token")
    return str(token)


def login(session, server, ref):
    code = yyb_code(server, ref)
    access_token = get_access_token(session)
    session.headers["access-token"] = access_token
    session.headers["user-token"] = ""
    resp = api(session, PATH_LOGIN, method="POST", data={"code": code})
    if not success(resp):
        raise RuntimeError(f"登录失败：{message(resp)}")
    data = resp.get("data") or {}
    user_token = data.get("utoken")
    if not user_token:
        raise RuntimeError("登录未返回 utoken")
    session.headers["user-token"] = str(user_token)
    return str(user_token), access_token, data


def center(session):
    body = api_m(session, "getUserInfo")
    if not success(body):
        raise RuntimeError(f"用户信息查询失败：{message(body)}")
    data = body.get("data") or {}
    return amount(data.get("amount")), int(data.get("integral") or 0), data


def sign_in(session):
    info = api_m(session, "getSignInEveryDayInfo")
    if not success(info):
        return f"签到状态查询失败：{message(info)}", None
    state = (info.get("data") or {})
    if str(state.get("is_sign", "")).lower() == "yes":
        day = state.get("sign_in_day", "?")
        return f"今日已签到（连续 {day} 天）", state
    body = api_m(session, "toSign")
    if not success(body):
        return f"签到失败：{message(body)}", None
    data = body.get("data") or {}
    reward = []
    rp = amount(data.get("get_red_packet"))
    if rp > 0:
        reward.append(f"{rp:.2f} 元红包")
    integral = int(data.get("get_integral") or 0)
    if integral:
        reward.append(f"{integral} 积分")
    day = data.get("sign_in_day", "?")
    suffix = f"，获得 {'、'.join(reward)}" if reward else ""
    return f"签到成功（连续 {day} 天）{suffix}", data


def bind_invite(session, invite_id):
    if not invite_id:
        return
    try:
        api_m(session, "setFromUser3", id=str(invite_id))
    except Exception:
        pass


def money_summary(initial, final):
    before = f"{initial:.2f} 元" if initial is not None else "未取得"
    after = f"{final:.2f} 元" if final is not None else "未取得"
    if initial is None or final is None:
        return f"红包余额：初始 {before} → 最终 {after}"
    change = final - initial
    difference = f"+{change:.2f} 元" if change > 0 else (f"{change:.2f} 元" if change < 0 else "无变化")
    return f"红包余额：初始 {before} → 最终 {after}（{difference}）"


def task_status(value):
    detail = value
    if "失败" in detail or "缺少" in detail:
        return f"❌ {detail}"
    if "成功" in detail or "已签到" in detail:
        return f"✅ {detail}"
    return f"🎁 {detail}"


def format_account(index, nick, initial, final, integral, sign_result, error, compact=False):
    label = f"账号 {index:02d}" + (f"（{nick}）" if nick else "")
    lines = [label, money_summary(initial, final), f"积分：{integral if integral is not None else '未取得'}"]
    if sign_result:
        lines.append(f"签到：{task_status(sign_result)}")
    if error:
        lines.append(f"运行异常：❌ {error}")
    if compact:
        return "\n".join(lines)
    return "\n".join([
        f"╭─ {lines[0]} ─────────────────────",
        *(f"│ {line}" for line in lines[1:]),
        "╰──────────────────────────────",
    ])


def notify(lines):
    if os.getenv("LMF_NOTIFY", "1").lower() in {"0", "false", "no"}:
        return
    for path in (os.path.dirname(os.path.abspath(__file__)), "/ql/data/scripts", "/ql/scripts"):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        from notify import send
        send("绿蜜蜂｜每日签到", "\n".join(lines))
        print("📨 通知已交给青龙通知模块")
    except Exception as exc:
        print(f"[通知] 发送失败（不影响任务）：{exc}")


def run_one(index, server, ref):
    initial = final = None
    integral = None
    sign_result = error = None
    nick = ""
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "version": "v1.0.0",
        "this-shop-id": "0",
        "xweb_xhr": "1",
        "master-token": "",
        "lat": "",
        "lng": "",
        "access-token": "",
        "user-token": "",
    })
    try:
        _, _, login_data = login(session, server, ref)
        nick = str(login_data.get("nick_name") or login_data.get("app_user_name") or "").strip()
        bind_invite(session, INVITE_ID)
        initial, integral, _ = center(session)
        sign_result, _ = sign_in(session)
        time.sleep(1)
        final, _, _ = center(session)
    except Exception as exc:
        error = str(exc)
    print(format_account(index, nick, initial, final, integral, sign_result, error))
    return format_account(index, nick, initial, final, integral, sign_result, error, compact=True), bool(error)


def main():
    accounts = routes()
    output = [f"共处理 {len(accounts)} 个账号", ""]
    failures = 0
    print(f"绿蜜蜂 · 每日签到｜共 {len(accounts)} 个账号")
    for index, (server, ref) in enumerate(accounts, 1):
        notice, failed = run_one(index, server, ref)
        output.extend([notice, ""])
        failures += failed
    summary = f"处理完成：{len(accounts)} 个账号，运行异常 {failures} 个"
    print(summary)
    output.append(summary)
    notify(output)


if __name__ == "__main__":
    main()
