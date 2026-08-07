#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cron: 9 9,14 * * *
"""
# name: 天机观
作者: ChatGPT
名称: 天机观自动任务（getCode版）
功能: 通过共享 getCode 模块自动获取 code，完成登录后自动执行签到/分享商品/观看广告

环境变量:
  WX_ID: 微信id，支持多账号，分隔符支持换行或@，格式支持 wxid 或 wxid#备注
         （由共享 getCode 模块读取并智能路由 牛子/应用宝）
  WECHAT_SERVER: 牛子协议服务地址（getCode 读取，默认 http://127.0.0.1:8011）
  YYB_SERVER: 应用宝(YYB) 服务地址（getCode 读取）
  SERVER_TYPE: 强制指定协议：wechat / yyb / auto（默认 auto 智能路由）

可选:
- TIANJITOKEN: 兼容旧 token 直登模式（单账号）
- SHARE_PRODUCT_COUNT: 分享次数，默认 10
- WATCH_AD_COUNT: 看广告次数，默认 50
"""

import os
import time
import random
import requests
import getCode  # 共享的微信小程序 code 获取模块（自动路由 牛子/应用宝，读取 WX_ID 过滤）

# 屏蔽 SSL 告警
import warnings
from urllib3.exceptions import InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

BASE_URL = "https://xcx.tianjiguan.cn"
WX_APPID = "wx7829675630d0305e"
MULTI_ACCOUNT_SPLIT = ["\n", "@"]

# 接口地址
USER_INFO_URL = f"{BASE_URL}/api/user/userinfo"
SIGN_URL = f"{BASE_URL}/api/user/sign"
SEE_AD_URL = f"{BASE_URL}/api/user/seeAd"
SHARE_URL = f"{BASE_URL}/api/user/share"
AUTO_LOGIN_URL = f"{BASE_URL}/api/user/autoLogin"


class Log:
    @staticmethod
    def info(msg):
        print(msg)

    @staticmethod
    def ok(msg):
        print(f"[OK] {msg}")

    @staticmethod
    def warn(msg):
        print(f"[WARN] {msg}")

    @staticmethod
    def err(msg):
        print(f"[ERR] {msg}")


def random_sleep(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))


def get_headers(token):
    return {
        "host": "xcx.tianjiguan.cn",
        "x-access-token": token,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254181c) XWEB/19201",
        "xweb_xhr": "1",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "accept": "*/*",
        "referer": "https://servicewechat.com/wx7829675630d0305e/8/page-frame.html",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "zh-CN,zh;q=0.9",
    }


def parse_multi_accounts(env_text):
    split_char = None
    for sep in MULTI_ACCOUNT_SPLIT:
        if sep in env_text:
            split_char = sep
            break

    items = [env_text] if not split_char else env_text.split(split_char)
    for raw in items:
        raw = raw.strip()
        if not raw:
            continue
        if "=" in raw:
            raw = raw.split("=", 1)[1].strip()
        if "#" in raw:
            wxid, remark = raw.split("#", 1)
            yield wxid.strip(), remark.strip()
        else:
            yield raw.strip(), ""


def get_code_from_wechat_loader(wxid):
    """通过共享 getCode 模块按 wxid 获取微信登录 code（自动路由牛子/应用宝，读取 WX_ID 过滤）"""
    try:
        code = getCode.get_single_code(WX_APPID, wxid)
        if code:
            return code
        Log.err("获取 code 失败: getCode 返回为空")
        return ""
    except Exception as e:
        Log.err(f"获取 code 异常: {e}")
        return ""


def get_token_by_code(code):
    try:
        resp = requests.post(AUTO_LOGIN_URL, data={"code": code}, timeout=20, verify=False)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 1:
            token = (result.get("data") or {}).get("token", "")
            if token:
                return token
        Log.err(f"code 换 token 失败: {result}")
        return ""
    except Exception as e:
        Log.err(f"code 换 token 异常: {e}")
        return ""


def get_user_info(token):
    try:
        resp = requests.get(
            USER_INFO_URL,
            headers=get_headers(token),
            params={"token": token},
            timeout=15,
            verify=False,
        )
        result = resp.json()
        if result.get("code") == 1:
            data = result.get("data", {})
            Log.info(f"用户: {data.get('nickname', '')} 手机: {data.get('mobile', '')} 积分: {data.get('score', 0)}")
            return data
        Log.err(f"查询用户信息失败: {result.get('msg', '未知错误')}")
        return None
    except Exception as e:
        Log.err(f"查询用户信息异常: {e}")
        return None


def do_sign(token):
    try:
        random_sleep(1, 2)
        resp = requests.get(
            SIGN_URL,
            headers=get_headers(token),
            params={"token": token},
            timeout=15,
            verify=False,
        )
        result = resp.json()
        if result.get("code") == 1:
            Log.ok(f"签到: {result.get('msg', '成功')}")
            return True
        Log.warn(f"签到: {result.get('msg', '失败')}")
        return False
    except Exception as e:
        Log.err(f"签到异常: {e}")
        return False


def do_share(token):
    try:
        random_sleep(1, 2)
        resp = requests.get(
            SHARE_URL,
            headers=get_headers(token),
            params={"token": token},
            timeout=15,
            verify=False,
        )
        result = resp.json()
        if result.get("code") == 1:
            Log.ok(f"分享: {result.get('msg', '成功')}")
            return True
        Log.warn(f"分享: {result.get('msg', '失败')}")
        return False
    except Exception as e:
        Log.err(f"分享异常: {e}")
        return False


def do_watch_ad(token):
    try:
        # 广告接口通常需要接近完整时长延迟
        random_sleep(20, 22)
        resp = requests.get(
            SEE_AD_URL,
            headers=get_headers(token),
            params={"token": token},
            timeout=15,
            verify=False,
        )
        result = resp.json()
        if result.get("code") == 1:
            Log.ok(f"看广告: {result.get('msg', '成功')}")
            return True
        Log.warn(f"看广告: {result.get('msg', '失败')}")
        return False
    except Exception as e:
        Log.err(f"看广告异常: {e}")
        return False


def run_one_account(token, account_name):
    share_count = int(os.getenv("SHARE_PRODUCT_COUNT", "10"))
    ad_count = int(os.getenv("WATCH_AD_COUNT", "50"))

    Log.info(f"\n========== 开始账号: {account_name} ==========")
    before = get_user_info(token)
    if not before:
        Log.err("获取初始用户信息失败，跳过该账号")
        return

    do_sign(token)

    Log.info(f"开始分享任务，共 {share_count} 次")
    for i in range(1, share_count + 1):
        Log.info(f"分享进度: {i}/{share_count}")
        do_share(token)

    Log.info(f"开始看广告任务，共 {ad_count} 次")
    for i in range(1, ad_count + 1):
        Log.info(f"广告进度: {i}/{ad_count}")
        do_watch_ad(token)

    after = get_user_info(token)
    if after:
        change = after.get("score", 0) - before.get("score", 0)
        Log.ok(f"积分变化: {before.get('score', 0)} -> {after.get('score', 0)} ({change:+d})")

    Log.info(f"========== 账号完成: {account_name} ==========\n")


def run_by_token_only():
    token = os.getenv("TIANJITOKEN", "").strip()
    if not token:
        return False
    run_one_account(token, "TIANJITOKEN")
    return True


def run_by_wechat_loader():
    wxid_env = (os.getenv("WX_ID") or "").strip()

    if not wxid_env:
        return False

    for idx, (wxid, remark) in enumerate(parse_multi_accounts(wxid_env), 1):
        account_name = f"账号{idx}" + (f"[{remark}]" if remark else "")
        Log.info(f"{account_name} 使用 wxid: {wxid}")

        code = get_code_from_wechat_loader(wxid)
        if not code:
            Log.err(f"{account_name} 获取 code 失败，跳过")
            continue

        token = get_token_by_code(code)
        if not token:
            Log.err(f"{account_name} 获取 token 失败，跳过")
            continue

        run_one_account(token, account_name)

    return True


def main():
    Log.info("天机观自动任务（wechatLoader版）启动")
    Log.info(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 优先 wechatLoader 自动模式
    if run_by_wechat_loader():
        Log.ok("wechatLoader 自动模式执行完成")
        return

    # 兼容旧 token 直登模式
    if run_by_token_only():
        Log.ok("TIANJITOKEN 模式执行完成")
        return

    Log.err("未检测到可用环境变量。请设置 WX_ID，或设置 TIANJITOKEN")


if __name__ == "__main__":
    main()
