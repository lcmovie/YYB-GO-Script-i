# cron: 35 9,15 * * * *
import os
# name: 申工社
import time
import json as _json
import pathlib
import requests
from getCode import get_single_code
import logging
import random
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# 小程序 AppID
APPID = "wx63d70210fcc108fd"  # 请替换为实际的小程序 AppID

# 缓存名称
CACHE_NAME = "sgs"

"""
========================================
环境变量配置说明
========================================

必填：
  WX_ID            微信账号，多账号分隔（兼容旧变量 WXIDSGS）
                  格式：wxid#备注（备注可选）
                  示例：
                    wxid_abc123#李四
                    wxid_abc123#张三
                    wxid_xyz456

  WECHAT_SERVER   微信协议服务地址（可选，在 getCode.py 中配置）

========================================
"""


# api获取code
def fetch_wx_code(wxid: str, wx_server: str = None) -> str | None:
    """
    单独获取微信 code（使用 getCode 模块）
    成功返回 code 字符串，失败返回 None
    """
    try:
        return get_single_code(APPID, wxid)
    except Exception as e:
        log.error(f"获取 wx_code 失败: {e}")
        return None


# 获取ck
def get_ck(wx_code: str) -> str | None:
    """
    通过微信 code 换取 token
    成功返回 token 字符串，失败返回 None
    """
    url = "https://fwdt.shszgh.cn/fwdt-wechat-xc/api/wechat/oauth"

    headers = {
        "Host": "fwdt.shszgh.cn",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 NetType/WIFI MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541843) XWEB/19339 Flue",
        "Origin": "https://fwdt.shszgh.cn",
        "Connection": "keep-alive",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    }

    data = {"code": wx_code}

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=15)
        if resp.status_code == 200:
            res_data = resp.json()
            if res_data.get("code") == 0 and res_data.get("success"):
                token = res_data.get("data")
                if token:
                    log.info("✅ 获取 token 成功")
                    return token
        log.error(f"❌ 获取 token 失败: {resp.text[:200]}")
    except Exception as e:
        log.error(f"❌ 请求异常: {e}")

    return None

# 刷新token的辅助函数
def refresh_token(wxid, wx_server, remark, cache, cache_file):
    """刷新 token，成功返回新token，失败返回None"""
    log.info(f"🔄 开始刷新 {remark} 的 token...")
    
    # 删除旧缓存
    if wxid in cache:
        del cache[wxid]
        save_cache(cache, cache_file)
        log.info(f"🗑️ 已删除 {remark} 的旧 token 缓存")
    
    # 获取新的 code
    code = fetch_wx_code(wxid, wx_server)
    if not code:
        log.error(f"❌ {remark} 获取 code 失败")
        return None
    
    # 换取新的 token
    new_token = get_ck(code)
    if not new_token:
        log.error(f"❌ {remark} 换取 token 失败")
        return None
    
    # 保存新 token 到缓存
    cache[wxid] = new_token
    save_cache(cache, cache_file)
    log.info(f"✅ {remark} token 刷新成功并已缓存")
    
    return new_token

#读取缓存
def load_cache(cache_file):
    try:
        return _json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

#保存缓存
def save_cache(cache, cache_file):
    cache_file.write_text(_json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

# 获取用户信息（如果 token 失效则自动刷新）
def member_info(token, wxid=None, wx_server=None, remark=None, cache=None, cache_file=None):
    """
    获取用户信息
    如果 token 失效，会自动重新获取并更新缓存
    返回: user_data 或 None（失败时返回None）
    """
    timestamp = int(time.time() * 1000)
    url = f"https://fwdt.shszgh.cn/fwdt-wechat-xc/api/member/info/get?_t={timestamp}"
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_7_1) (KHTML, like Gecko)',
        'token': token,
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        result = resp.json()
    except Exception as e:
        log.error(f"获取用户信息请求异常: {e}")
        return None

    # 检查 token 是否失效
    if result and result.get("code") == 100 and result.get("message") == "用户未登录":
        log.warning(f"⚠️ token 已失效，尝试重新登录...")
        
        # 如果提供了必要的参数，则尝试刷新
        if wxid and wx_server and remark and cache is not None and cache_file:
            new_token = refresh_token(wxid, wx_server, remark, cache, cache_file)
            if new_token:
                # 使用新 token 重新获取用户信息
                log.info(f"🔄 使用新 token 重新获取用户信息...")
                return member_info(new_token, wxid, wx_server, remark, cache, cache_file)
        
        log.error(f"❌ token 失效且无法刷新")
        return None

    if not result or result.get("code") != 0:
        log.error(f"❌ 获取用户信息失败: {result}")
        return None

    data = result["data"]
    log.info(f"👤 用户昵称: {data['nickname']}")
    log.info(f"💰 当前积分: {data['integral']}")
    jifen = data["integral"]

    if jifen >= 21200:
        log.warning(f"\n用户昵称📙: {data['nickname']}\n当前积分📙: {data['integral']}\n🎉 当前帐号已可兑换100话费")
    
    return data

# 签到
def sign(token):
    timestamp = int(time.time() * 1000)
    url = f"https://fwdt.shszgh.cn/fwdt-wechat-xc/api/integral/sign?_t={timestamp}"
    headers = {
        'token': token,
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Mobile)',
        'Accept': 'application/json, text/plain, */*'
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        result = resp.json()
    except Exception as e:
        log.error(f"签到请求异常: {e}")
        return

    if not result:
        log.error("❌ 签到请求失败")
        return

    code = result.get("code")
    if code == 0:
        log.info(f"✅ 签到成功: {result.get('msg')}")
    elif code == 500:
        log.info(f"📙 已签到: {result.get('msg')}")
    elif code == 401:
        log.error(f"❌ 帐号 token 已过期")
    else:
        log.warning(f"⚠️ 签到失败: {result}")


# 阅读有赏
def auto_read_all(token):
    unread_ids = get_unread_ids(token)
    if not unread_ids:
        log.info("✅ 暂无未阅读文章")
        return

    log.info(f"📖 开始阅读 {len(unread_ids)} 篇文章...")
    for i, mid in enumerate(unread_ids, 1):
        log.info(f"📖 阅读第 {i}/{len(unread_ids)} 篇 ID: {mid}")
        if not read_article(token, mid):
            break
        delay = random.randint(20, 30)
        log.info(f"⏳ 等待 {delay}s 后继续...")
        time.sleep(delay)
    log.info("📘 阅读任务完成。")


def read_article(token, media_id):
    """阅读单篇文章"""
    url = "https://fwdt.shszgh.cn/fwdt-wechat-xc/api/readReward/read"
    headers = {
        'Content-Type': 'application/json;charset=utf-8',
        'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_7_1)',
        'token': token
    }
    data = {"mediaId": media_id}

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        result = resp.json()
    except Exception as e:
        log.error(f"阅读请求异常: {e}")
        return True

    if not result:
        return True

    if result.get("code") == 0 and result.get("msg") == "success":
        log.info(f"✅ 阅读成功: {media_id}")
        return True
    elif result.get("code") == 500 and "超限" in result.get("message", ""):
        log.warning("🚫 今日阅读次数超限，停止。")
        return False
    else:
        log.info(f"📙 阅读返回: {result}")
        return True


def get_unread_ids(token):
    url = "https://fwdt.shszgh.cn/fwdt-wechat-xc/api/readReward/page"
    headers = {
        'Content-Type': 'application/json;charset=utf-8',
        'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_7_1)',
        'token': token
    }

    body = {"current": 1, "size": 10}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        result = resp.json()
    except Exception as e:
        log.error(f"获取文章列表请求异常: {e}")
        return []

    if result and result.get("code") == 0:
        records = result.get("data", {}).get("records", [])
        unread_ids = [r["id"] for r in records if r.get("isRead") == 0]
        log.info(f"📚 未阅读文章ID: {unread_ids}")
        return unread_ids
    else:
        log.warning(f"⚠️ 获取文章失败: {result}")
        return []


# 公社任务
def modular_count(token):
    url = "https://fwdt.shszgh.cn/fwdt-wechat-xc/api/home/modularCount"
    headers = {
        'Content-Type': 'application/json;charset=utf-8',
        'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 14_7_1)',
        'token': token
    }

    payloads = [
        {"modularType": 1, "modularName": "文化云", "modularId": 1985022690724094000},
        {"modularType": 1, "modularName": "会缘", "modularId": 1985022690740871200},
        {"modularType": 1, "modularName": "申请参保", "modularId": 1985022690757648400},
        {"modularType": 2, "modularName": "传统文化乐游苑", "modularId": 1985349165054632000},
    ]

    for i, payload in enumerate(payloads, 1):
        log.info(f"🚀 模块访问 {i}: {payload['modularName']}")
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            result = resp.json()
            log.info(f"✅ 返回: {result}")
        except Exception as e:
            log.error(f"模块访问请求异常: {e}")
        if i < len(payloads):
            delay = random.randint(20, 30)
            log.info(f"⏳ 等待 {delay}s...")
            time.sleep(delay)

#任务完成标记
def should_run_today(wxid, remark, cache):
    """检查今天是否已经执行过任务"""
    today = datetime.now().strftime("%Y-%m-%d")
    last_run = cache.get(f"{wxid}_daily")
    if last_run == today:
        log.info(f"📅 账号 {remark} 今日任务已完成，跳过")
        return False
    return True

if __name__ == "__main__":

    WX_SERVER = os.environ.get("WECHAT_SERVER", "")
    if not WX_SERVER:
        log.warning("未配置 WECHAT_SERVER，请检查环境变量")

    # 解析多账号
    wxids_raw = os.environ.get("WX_ID") or os.environ.get("WXIDSGS", "")
    if not wxids_raw:
        log.error("未配置 WX_ID 或 WXIDSGS，请设置环境变量后重试")
        raise SystemExit(1)

    raw_lines = []
    for sep in ("\n", "@", "&", "\r\n"):
        if sep in wxids_raw:
            raw_lines = wxids_raw.split(sep)
            break
    if not raw_lines:
        raw_lines = [wxids_raw]

    WXIDS = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        if '=' in line:
            line = line.split('=', 1)[1].strip()
        if "#" in line:
            wxid, remark = line.split("#", 1)
            WXIDS.append((wxid.strip(), remark.strip()))
        else:
            WXIDS.append((line, line))

    # 缓存文件
    CACHE_FILE = pathlib.Path(__file__).parent / f"{CACHE_NAME}_token.json"
    cache = load_cache(CACHE_FILE)

    for idx, (wxid, remark) in enumerate(WXIDS):
        log.info("=" * 40)
        log.info(f"处理账号: {remark}")

        # 检查今天是否已经执行过任务
        if not should_run_today(wxid, remark, cache):
            # 账号间延迟
            if idx < len(WXIDS) - 1:
                delay = random.randint(30, 120)
                log.info(f"⏳ 等待 {delay}s 切换下一个账号...")
                time.sleep(delay)
            continue

        cached_token = cache.get(wxid)

        # 如果没有缓存token，则进行登录获取
        if not cached_token:
            log.info("🌿未识别到缓存，开始登录流程...")
            cached_token = refresh_token(wxid, WX_SERVER, remark, cache, CACHE_FILE)
            if not cached_token:
                log.error(f"❌账号 {remark} 登录失败，跳过")
                continue

        # 执行任务
        log.info(f"✅ 开始处理账号: {remark}")
        
        log.info("========= 用户信息 =========")
        user_data = member_info(cached_token, wxid, WX_SERVER, remark, cache, CACHE_FILE)
        if not user_data:
            log.error(f"❌账号 {remark} 获取用户信息失败，跳过")
            continue
        # 🔧 修复：重新从缓存获取最新的 token（可能已被刷新）
        cached_token = cache.get(wxid)    
        time.sleep(1)
        log.info("========= 签到 =========")
        sign(cached_token)
        time.sleep(1)
        
        log.info("========= 阅读有赏 =========")
        auto_read_all(cached_token)
        time.sleep(1)
        
        log.info("========= 公社 =========")
        modular_count(cached_token)
        time.sleep(1)
        
        log.info("========= 最终用户信息 =========")
        member_info(cached_token, wxid, WX_SERVER, remark, cache, CACHE_FILE)
        
        log.info("🍁 任务完成 🍁")

        # 记录今天已经执行过任务
        today = datetime.now().strftime("%Y-%m-%d")
        cache[f"{wxid}_daily"] = today
        save_cache(cache, CACHE_FILE)
        log.info(f"📝 已记录账号 {remark} 今日任务完成状态")

        # 账号间延迟
        if idx < len(WXIDS) - 1:
            delay = random.randint(30, 120)
            log.info(f"⏳ 等待 {delay}s 切换下一个账号...")
            time.sleep(delay)