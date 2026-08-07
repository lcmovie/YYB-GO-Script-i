# cron: 10 9,13 * * *

"""
# name: 汤星球
作者: 吉吉国王大人
日期: 2026/6/30
name: ꧁༺ 汤汤༒星球 ༻꧂ (微信协议版)
入口: 微信小程序 - 汤臣倍健 (wx9bb6d5ac457bd69d)
后端: vip.by-health.com
功能: 自动签到

环境变量配置:
  WX_ID           账号配置，格式：wxid#备注，多账号换行 / & 分隔
  WECHAT_SERVER   微信协议服务地址，默认 http://127.0.0.1:8011
  txq             手动模式兼容，每行 备注#Authorization

说明:
  自动登录模式：通过微信协议服务器获取 OAuth code，再换取 Authorization（JWT）
  手动模式：直接填写抓包获取的 Authorization，跳过登录步骤
  
  如果自动登录失败，切换手动模式：
    1. 微信打开「汤臣倍健」小程序 → 抓包找到 Authorization 请求头
    2. 青龙面板添加环境变量 txq，格式：备注#Authorization值
    3. 多账号换行分割
"""

import json
import os
import random
import re
import time
import traceback

import requests

from getCode import get_single_code

try:
    from notify import send as notify_send
except ImportError:
    def notify_send(title, content):
        print(f"--- 通知 ---\n{title}\n{content}\n-------------")

retrycount = 3
name = "꧁༺ 汤汤༒星球 ༻꧂"

WX_APPID = "wx9bb6d5ac457bd69d"
HOST = "https://vip.by-health.com"
DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"

SIGN_PATH = "/vip-api/sign/daily/create"
SIGN_ACTIVITY_ID = 11
LOGIN_PATH = "/vip-api/auth/ma/login"


# build_code_url 和 get_code 已统一到 getCode.py，此处保留兼容
def build_code_url(raw_url):
    """已废弃，保留兼容"""
    return ""

def get_code(wxid, _server=None):
    """通过 getCode.py 统一接口获取微信 code"""
    try:
        return get_single_code(WX_APPID, wxid)
    except Exception as exc:
        print(f"微信: 获取 code 异常: {exc}")
        return None

    data = result.get("Data") if isinstance(result.get("Data"), dict) else result.get("data")
    code = data.get("code") if isinstance(data, dict) else None
    if code:
        return code
    msg = result.get("Message") or result.get("msg") or result.get("message") or "unknown"
    print(f"微信: 获取 code 失败: {msg}")
    return None


def get_nested(data, path, default=None):
    """按点号路径取嵌套字段，如 data.token"""
    current = data
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def build_headers(authorization="", appid=WX_APPID):
    headers = {
        "Host": "vip.by-health.com",
        "Content-Type": "application/json;charset=utf-8",
        "Referer": f"https://servicewechat.com/{appid}/devtools/page-frame.html",
        "sec-ch-ua-mobile": "?1",
        "Accept": "*/*",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; MI 8 Build/QKQ1.190828.002; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/134.0.6998.136 "
            "Mobile Safari/537.36 XWEB/1340129 MMWEBSDK/20250201 MMWEBID/6533 "
            "MicroMessenger/8.0.60.2860(0x28003C51) WeChat/arm64 Weixin NetType/WIFI "
            "Language/zh_CN ABI/arm64 miniProgram/wx9bb6d5ac457bd69d"
        ),
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "sec-ch-ua-platform": "Android",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Android WebView";v="134"',
        "x-requested-with": "com.tencent.mm",
        "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if authorization:
        headers["Authorization"] = authorization
        headers["Origin"] = "https://vip.by-health.com"
    return headers


def login_by_code(wx_id, wechat_server):
    """用微信 OAuth code 换取 Authorization token。返回 token 字符串或 None。"""
    url = f"{HOST}{LOGIN_PATH}"
    print(f"🔑 获取微信授权 code...")
    code = get_code(wx_id, wechat_server)
    if not code:
        print("❌ 获取 code 失败")
        return None

    body = {"appId": WX_APPID, "code": code}
    print(f"🔑 登录: {LOGIN_PATH}")

    try:
        resp = requests.post(url, headers=build_headers(), json=body, timeout=10)
        data = resp.json() if resp.text else {}
    except (json.JSONDecodeError, requests.RequestException) as e:
        print(f"❌ 登录请求异常: {e}")
        return None

    if not data.get("success"):
        print(f"❌ 登录失败: {json.dumps(data, ensure_ascii=False)[:200]}")
        return None

    token = get_nested(data, "data.result.token")
    if token:
        print(f"✅ 登录成功! token={token[:8]}...")
        return str(token)

    print(f"❌ 未找到 token: {json.dumps(data, ensure_ascii=False)[:200]}")
    return None


def do_sign(authorization, label=""):
    """执行签到，返回 True/False"""
    for retry in range(int(retrycount)):
        try:
            url = f"{HOST}{SIGN_PATH}"
            header = build_headers(authorization)
            resp = requests.post(url, headers=header, json={"activityId": SIGN_ACTIVITY_ID}, timeout=10)
            data = resp.json()
        except Exception as e:
            if retry >= int(retrycount) - 1:
                print(f"{label}⭕ 签到异常: {e}")
                return False
            time.sleep(1)
            continue

        if not data.get("success"):
            msg = json.dumps(data, ensure_ascii=False)[:120]
            print(f"{label}⚠️ 签到失败: {msg}")
            return False

        result = get_nested(data, "data.result", {})
        rsp_msg = get_nested(data, "data.rspMsg", "")
        rsp_code = get_nested(data, "data.rspCode", "")

        if rsp_code == "00":
            coins = result.get("dailyPointReward", "?")
            print(f"{label}☁️ 签到成功：+{coins} 金币")
            return True
        elif "已签" in rsp_msg or "已完成" in rsp_msg:
            print(f"{label}☁️ 签到：{rsp_msg}")
            return True
        else:
            print(f"{label}⚠️ {rsp_msg or json.dumps(data, ensure_ascii=False)[:80]}")
            return False

    return False


def main():
    wechat_server = build_code_url(
        os.environ.get("WECHAT_SERVER", DEFAULT_WECHAT_SERVER)
    )

    log_lines = []
    log_lines.append(f"\n{' ' * 7}{name}")
    log_lines.append("-------- ☁️ 开 始  执 行 ☁️ --------")

    # 解析账号
    accounts = []
    wxid_raw = (os.getenv("WX_ID") or "").strip()
    if wxid_raw:
        items = [x.strip() for x in re.split(r"[\n&]", wxid_raw) if x.strip()]
        for item in items:
            idx = item.rfind("#")
            if idx > 0:
                accounts.append({"mode": "auto", "wxid": item[:idx].strip(), "note": item[idx + 1:].strip()})
            else:
                accounts.append({"mode": "auto", "wxid": item, "note": ""})

    # 手动模式
    ck_raw = (os.getenv("txq") or "").strip()
    if ck_raw and not accounts:
        items = [x.strip() for x in ck_raw.split("\n") if x.strip()]
        for item in items:
            try:
                mark, arg1 = item.split("#", 1)
                accounts.append({"mode": "manual", "note": mark.strip(), "authorization": arg1.strip()})
            except ValueError:
                print(f"⚠️ txq 格式错误，跳过: {item}")

    if not accounts:
        print("⭕ 未找到账号变量，请设置 WX_ID（自动登录）或 txq（手动模式）")
        return

    log_lines.append(f"共 {len(accounts)} 个账号")

    for i, acc in enumerate(accounts, 1):
        note = acc.get("note", "")
        label = f"☁️ 账号 [{i}/{len(accounts)}]"
        mask = (note[:3] + "*****" + note[-3:]) if len(note) >= 7 else note
        log_lines.append(f"\n{label}")
        log_lines.append(f"☁️ 当前账号：{mask or f'账号{i}'}")
        print(f"\n{label}")
        print(f"☁️ 当前账号：{mask or f'账号{i}'}")

        if acc["mode"] == "manual":
            authorization = acc["authorization"]
            log_lines.append("📌 手动模式，跳过登录直接签到")
            print("📌 手动模式，跳过登录直接签到")
            ok = do_sign(authorization, label="  ")
            log_lines.append(f"{'签到成功' if ok else '签到失败'}")
        else:
            wx_id = acc["wxid"]
            time.sleep(random.randint(1, 2))
            authorization = login_by_code(wx_id, wechat_server)
            if not authorization:
                msg = "❌ 自动登录失败，可切换手动模式：设置环境变量 txq = 备注#Authorization值"
                log_lines.append(msg)
                print(msg)
                continue

            log_lines.append("✅ 登录成功，获取 Authorization")
            print("✅ 登录成功，获取 Authorization")
            time.sleep(random.randint(1, 2))
            ok = do_sign(authorization, label="  ")
            log_lines.append(f"{'签到成功' if ok else '签到失败'}")

        time.sleep(random.randint(1, 2))

    log_lines.append("\n-------- ☁️ 执 行  结 束 ☁️ --------")
    print("\n-------- ☁️ 执 行  结 束 ☁️ --------")

    # 推送
    try:
        notify_send(f"{name} 运行日志", "作者：吉吉国王大人\n\n" + "\n".join(log_lines))
    except Exception:
        pass


if __name__ == "__main__":
    main()
