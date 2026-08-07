
# cron: 39 10,14 * * *

"""
# name: 毛铺草本荟
青龙脚本：毛铺草本荟小程序每日签到 + 抽奖

环境变量：
  WX_ID           必填，格式：wxid#别名（兼容别名#wxid），多账号换行 / & 分隔
  WECHAT_SERVER   必填，用于通过 wxid 获取 wx.login code

定时建议：
  15 8 * * *
#小程序://毛铺草本荟/lxJAUyTkGwBivyj
"""
import requests, json, re, os, sys, time, random, datetime, hashlib, base64
from getCode import get_single_code

try:
    from notify import send as notify_send
except ImportError:
    def notify_send(title, content):
        print(f"--- 通知 ---\n{title}\n{content}\n-------------")

retrycount = 1
environ = "WX_ID"
name = "꧁༺ 毛铺༒草本 ༻꧂"
WX_APPID = "wxefd0fe341e06b815"
DEFAULT_WECHAT_SERVER = "http://127.0.0.1:8011"
LOGIN_URL = "https://mpb.jingjiu.com/proxy-he/jp/api/loginauto"
TOKEN_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mpcbh_wxid_tokens.json")
MINI_REFERER = f"https://servicewechat.com/{WX_APPID}/741/page-frame.html"
MINI_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a1b)XWEB/14185"
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

def calculate_appsign(data, auth_token, sign_secret, param_order):
    """计算appsign"""
    apptime = str(int(datetime.datetime.now().timestamp()))
    sign_str = apptime
    for key in param_order:
        if key in data:
            sign_str += f"{key}{data[key]}"
    sign_str += sign_secret + auth_token
    md5_obj = hashlib.md5(sign_str.encode("utf-8"))
    md5_hex = md5_obj.hexdigest().upper()
    appsign = md5_hex[-10:]
    return apptime, appsign

def random_wait(min_sec=3, max_sec=8, print_log=False):
    """随机等待"""
    wait_time = random.randint(min_sec, max_sec)
    if print_log:
        print(f"⏳ 随机等待 {wait_time} 秒...")
    time.sleep(wait_time)

def split_multi(raw):
    """拆分多账号变量，兼容换行、&、@。"""
    return [item.strip() for item in re.split(r"[\n&@]+", raw or "") if item.strip()]

def mask_text(value, left=3, right=3):
    if not value:
        return ""
    if len(value) <= left + right:
        return value
    return value[:left] + "*****" + value[-right:]

def parse_wxid_item(item):
    """兼容 wxid#备注 和 备注#wxid 两种写法。"""
    if "#" not in item:
        return item.strip(), item.strip()
    first, second = [x.strip() for x in item.split("#", 1)]
    if second.startswith("wxid_") and not first.startswith("wxid_"):
        return second, first
    return first, second or first

def build_code_url():
    """已废弃：现使用 getCode.py 统一接口"""
    return ""

def extract_wx_code(data):
    if not isinstance(data, dict):
        return ""
    nested = data.get("Data") or data.get("data") or {}
    if isinstance(nested, dict) and nested.get("code"):
        return str(nested.get("code"))
    return str(data.get("code") or "")

def load_token_cache():
    if not os.path.exists(TOKEN_CACHE_FILE):
        return {"accounts": {}}
    try:
        with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("accounts"), dict):
            return data
        return {"accounts": {}}
    except Exception as e:
        print(f"⭕读取token缓存失败，将忽略缓存：{str(e)}")
        return {"accounts": {}}

def save_token_cache(cache):
    try:
        with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⭕保存token缓存失败：{str(e)}")

def decode_jwt_payload(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception:
        return {}

def token_expire_time(token):
    payload = decode_jwt_payload(token)
    try:
        return int(payload.get("exp") or 0)
    except Exception:
        return 0

def token_user_id(token):
    payload = decode_jwt_payload(token)
    return str(payload.get("user_id") or "")

def get_cached_auth_token(cache, wxid):
    record = (cache.get("accounts") or {}).get(wxid) or {}
    token = record.get("auth_token") or ""
    expires_at = int(record.get("expires_at") or token_expire_time(token) or 0)
    if not token:
        return ""
    if expires_at and expires_at > int(time.time()) + 600:
        expire_text = datetime.datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
        print(f"☁️使用缓存token：有效期至 {expire_text}")
        return token
    print("☁️缓存token已过期或无有效期，重新登录")
    remove_cached_auth_token(cache, wxid, save=False)
    return ""

def save_cached_auth_token(cache, wxid, comment, auth_token):
    cache.setdefault("accounts", {})[wxid] = {
        "comment": comment,
        "auth_token": auth_token,
        "user_id": token_user_id(auth_token),
        "expires_at": token_expire_time(auth_token),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_token_cache(cache)

def remove_cached_auth_token(cache, wxid, save=True):
    accounts = cache.setdefault("accounts", {})
    if wxid in accounts:
        accounts.pop(wxid, None)
        if save:
            save_token_cache(cache)

def get_wx_code(wxid):
    """通过 getCode.py 统一接口获取毛铺小程序 wx.login code。"""
    try:
        code = get_single_code(WX_APPID, wxid)
        return code if code else ""
    except Exception as e:
        print(f"⭕获取微信code异常：{str(e)}")
        return ""

def build_login_system():
    """按抓包补齐 loginauto 的 system 字段。"""
    return {
        "albumAuthorized": True,
        "benchmarkLevel": -1,
        "bluetoothEnabled": False,
        "brand": "microsoft",
        "cameraAuthorized": True,
        "fontSizeSetting": 15,
        "language": "zh_CN",
        "locationAuthorized": True,
        "locationEnabled": True,
        "microphoneAuthorized": True,
        "model": "microsoft",
        "notificationAuthorized": True,
        "notificationSoundEnabled": True,
        "pixelRatio": 1,
        "platform": "windows",
        "power": 100,
        "safeArea": {"bottom": 780, "height": 780, "left": 0, "right": 414, "top": 0, "width": 414},
        "screenHeight": 780,
        "screenWidth": 414,
        "statusBarHeight": 20,
        "system": "Windows 11 x64",
        "theme": "light",
        "version": "3.9.10",
        "wifiEnabled": True,
        "windowHeight": 780,
        "windowWidth": 414,
        "SDKVersion": "3.10.3",
        "enableDebug": False,
        "host": {"appId": "", "env": "WeChat"},
        "appName": "wechat",
        "devicePixelRatio": 1,
    }

def login_by_wxid(wxid, session):
    """wxid -> wx.login code -> 毛铺 access_token。"""
    code = get_wx_code(wxid)
    if not code:
        return ""
    now_ts = int(datetime.datetime.now().timestamp())
    login_data = {
        "code": code,
        "unionid": "",
        "user_id": "",
        "user_sources": "0",
        "system": build_login_system(),
        "itime": now_ts,
        "isource": hashlib.md5(f"{wxid}{now_ts}{random.random()}".encode("utf-8")).hexdigest().upper(),
    }
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Referer": MINI_REFERER,
        "User-Agent": MINI_UA,
        "x-version": "0.0.1",
        "xweb_xhr": "1",
        "Authorization": "",
    }
    try:
        response = session.post(
            LOGIN_URL,
            headers=headers,
            data=json.dumps(login_data, ensure_ascii=False),
            timeout=15,
        )
        result = response.json()
        if result.get("code") != 0:
            print(f"⭕自动登录失败：{result.get('message') or json.dumps(result, ensure_ascii=False)[:200]}")
            return ""
        token = ((result.get("data") or {}).get("access_token") or "").strip()
        if not token:
            print(f"⭕自动登录失败：响应缺少access_token {json.dumps(result, ensure_ascii=False)[:200]}")
            return ""
        print(f"☁️自动登录成功：token={token[:8]}...")
        return token
    except Exception as e:
        print(f"⭕自动登录异常：{str(e)}")
        return ""

log_messages = []

def log(msg):
    print(msg)
    log_messages.append(msg)

def parse_accounts():
    """优先读取 WX_ID 自动登录；同时保留手动 token 兼容。"""
    accounts = []
    raw_wxid = os.environ.get(environ, "")
    for item in split_multi(raw_wxid):
        wxid, comment = parse_wxid_item(item)
        if wxid:
            accounts.append({"mode": "wxid", "wxid": wxid, "comment": comment or wxid})
    return accounts

def daily_sign_in(auth_token, session):
    """每日签到"""
    try:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        sign_data = {"date": current_date}
        #print(f"☁️签到日期：{current_date}")
        apptime, appsign = calculate_appsign(sign_data, auth_token, SIGN_SECRET, ["date"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url = "https://mpb.jingjiu.com/proxy-he/api/FlanSignInDaily/adds"
        response = session.post(url=url,headers=base_headers,data=json.dumps(sign_data, ensure_ascii=False),timeout=15)
        result = response.json()
        if result.get("code") != 0:
            print(f"❌ 签到失败：{result.get('message', '未知错误')}")
            return result.get('message', '未知错误')
        point_today = result["data"].get("point_today", 0)
        point_tomorrow = result["data"].get("point_tomorrow", 0)
        if point_today > 0 or point_tomorrow > 0:
            print(f"☁️签到状态：{point_today} 积分")
        else:
            print(f"☁️签到状态：今日已签到")
        return "ok"
    except Exception as e:
        print(f"⭕签到异常：{str(e)}")

def haoyoubangbang_draw(auth_token, session):
    """好友帮帮"""
    try:
        print("☼ ――――  帮  帮  ―――― ☼")
        current_timestamp = int(datetime.datetime.now().timestamp())
        # 获取抽奖资格
        draw_get_data = {"activity_id": "5001","latitude":30.032270431518555,"longitude":120.86858367919922,"play_time_start": current_timestamp}
        apptime, appsign = calculate_appsign(draw_get_data, auth_token, SIGN_SECRET, ["activity_id", "latitude", "longitude", "play_time_start"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_get = "https://mpb.jingjiu.com/proxy-he/api/BlzLongcaobenActivity/bangOnlineUserDrawGet"
        response_get = session.post(url=url_get,headers=base_headers,data=json.dumps(draw_get_data, ensure_ascii=False),timeout=15)
        result_get = response_get.json()
        if result_get.get("code") != 0:
            if "今日已参与" in result_get.get('message', '未知错误'):
                print(f"☁️活动游戏：已完成")
            else:
                print(f"⭕活动游戏：{result_get.get('message', '未知错误')}")
            return
        user_record_id = result_get["data"].get("user_record_id")
        if not user_record_id:
            print("⭕活动游戏：未获取到user_record_id，无法继续抽奖")
            return
        print(f"☁️活动游戏：游戏完成")
        #print(f"⏳ 等待{wait_time}秒，满足活动时间要求...")
        time.sleep(random.randint(3, 8))
        # 执行抽奖
        draw_do_data = {"user_record_id": user_record_id,"play_time_finish": int(datetime.datetime.now().timestamp())}
        apptime, appsign = calculate_appsign(draw_do_data, auth_token, SIGN_SECRET, ["user_record_id", "play_time_finish"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_do = "https://mpb.jingjiu.com/proxy-he/api/BlzLongcaobenActivity/bangOnlineUserDraws"
        response_do = session.post(url=url_do,headers=base_headers,data=json.dumps(draw_do_data, ensure_ascii=False),timeout=15)
        result_do = response_do.json()
        if result_do.get("code") != 0:
            print(f"⭕抽奖失败：{result_do.get('message', '未知错误')}")
            return
        award_title = result_do["data"].get("awardLocal", {}).get("title", "")
        if not award_title:
            award_title = result_do["data"].get("award", {}).get("AwardName", "未知奖励")
        award_money = result_do["data"].get("awardLocal", {}).get("money", "0")
        print(f"🌈抽奖获得：{award_title}（{award_money}元）")
        try:
            award_code = result_do["data"].get("ucodeAward", {}).get("code", "")
            if award_code:
                #print(f"📌 奖励编码：{award_code}")
                pass
        except:
            #print(f"{result_do}")
            pass
    except Exception as e:
        print(f"❌ 抽奖任务异常：{str(e)}")

def shicaoxunyuan_draw(auth_token, session):
    """识草寻源"""
    try:
        print("☼ ――――  识  草  ―――― ☼")
        current_timestamp = int(datetime.datetime.now().timestamp())
        # 获取抽奖资格
        draw_get_data = {"play_time_start": current_timestamp,"use_type": "free"}
        apptime, appsign = calculate_appsign(draw_get_data, auth_token, SIGN_SECRET, ["play_time_start", "use_type"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_get = "https://mpb.jingjiu.com/proxy-he/api/BlzLonglActivity/shicaoxunyuanUserDrawGet"
        response_get = session.post(url=url_get,headers=base_headers,data=json.dumps(draw_get_data, ensure_ascii=False),timeout=10)
        result_get = response_get.json()
        if result_get.get("code") != 0:
            if "今日游戏已完成" in result_get.get('message', '未知错误'):
                print(f"☁️活动游戏：已完成")
            else:
                print(f"⭕活动游戏：{result_get.get('message', '未知错误')}")
            return
        user_record_id = result_get["data"].get("user_record_id")
        if not user_record_id:
            print("⭕活动游戏：未获取到user_record_id，无法继续抽奖")
            return
        print(f"☁️活动游戏：游戏完成")
        #print(f"⏳ 等待{wait_time}秒，满足活动时间要求...")
        time.sleep(36)
        # 执行抽奖
        draw_do_data = {"play_time_finish": int(datetime.datetime.now().timestamp()),"user_record_id": user_record_id}
        apptime, appsign = calculate_appsign(draw_do_data, auth_token, SIGN_SECRET, ["play_time_finish", "user_record_id"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_do = "https://mpb.jingjiu.com/proxy-he/api/BlzLonglActivity/shicaoxunyuanUserDraws"
        response_do = session.post(url=url_do,headers=base_headers,data=json.dumps(draw_do_data, ensure_ascii=False),timeout=15)
        result_do = response_do.json()
        if result_do.get("code") != 0:
            print(f"⭕抽奖失败：{result_do.get('message', '未知错误')}")
            return
        award_title = result_do["data"].get("awardLocal", {}).get("title", "")
        if not award_title:
            award_title = result_do["data"].get("award", {}).get("AwardName", "未知奖励")
        award_money = result_do["data"].get("awardLocal", {}).get("money", "0")
        print(f"🌈抽奖获得：{award_title}（{award_money}元）")
        try:
            award_code = result_do["data"].get("ucodeAward", {}).get("code", "")
            if award_code:
                #print(f"📌 奖励编码：{award_code}")
                pass
        except:
            #print(f"{result_do}")
            pass
    except Exception as e:
        print(f"⭕抽奖任务异常：{str(e)}")


def caobenshiyanshi_draw(auth_token, session):
    """草本实验室"""
    try:
        print("☼ ――――  草  本  ―――― ☼")
        current_timestamp = int(datetime.datetime.now().timestamp())
        # 获取抽奖资格
        draw_get_data = {"play_time_start": current_timestamp,"use_type": "free"}
        apptime, appsign = calculate_appsign(draw_get_data, auth_token, SIGN_SECRET, ["play_time_start", "use_type"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_get = "https://mpb.jingjiu.com/proxy-he/api/BlzLonglActivity/caobenshiyanshiUserDrawGet"
        response_get = session.post(url=url_get,headers=base_headers,data=json.dumps(draw_get_data, ensure_ascii=False),timeout=15)
        result_get = response_get.json()
        if result_get.get("code") != 0:
            if "今日游戏已完成" in result_get.get('message', '未知错误'):
                print(f"☁️活动游戏：已完成")
            else:
                print(f"⭕活动游戏：{result_get.get('message', '未知错误')}")
            return
        user_record_id = result_get["data"].get("user_record_id")
        if not user_record_id:
            print("⭕活动游戏：未获取到user_record_id，无法继续抽奖")
            return
        print(f"☁️活动游戏：游戏完成")
        #print(f"⏳ 等待{wait_time}秒，满足活动时间要求...")
        time.sleep(36)
        # 执行抽奖
        draw_do_data = {"play_time_finish": int(datetime.datetime.now().timestamp()),"user_record_id": user_record_id}
        apptime, appsign = calculate_appsign(draw_do_data, auth_token, SIGN_SECRET, ["play_time_finish", "user_record_id"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_do = "https://mpb.jingjiu.com/proxy-he/api/BlzLonglActivity/caobenshiyanshiUserDraws"
        response_do = session.post(url=url_do,headers=base_headers,data=json.dumps(draw_do_data, ensure_ascii=False),timeout=15)
        result_do = response_do.json()
        if result_do.get("code") != 0:
            print(f"⭕抽奖失败：{result_do.get('message', '未知错误')}")
            return
        award_title = result_do["data"].get("awardLocal", {}).get("title", "")
        if not award_title:
            award_title = result_do["data"].get("award", {}).get("AwardName", "未知奖励")
        award_jifen = result_do["data"].get("awardLocal", {}).get("jifen", "0")
        print(f"🌈抽奖获得：{award_title}（{award_jifen}积分）")
        try:
            award_code = result_do["data"].get("ucodeAward", {}).get("code", "")
            if award_code:
                #print(f"📌 奖励编码：{award_code}")
                pass
        except:
            #print(f"{result_do}")
            pass
    except Exception as e:
        print(f"⭕抽奖任务异常：{str(e)}")


def wumian_draw(auth_token, session):
    """无冕之王"""
    try:
        print("☼ ――――  无  冕  ―――― ☼")
        current_timestamp = int(datetime.datetime.now().timestamp())
        # 获取抽奖资格
        draw_get_data = {"activity_id": "1001","play_time_start": current_timestamp}
        apptime, appsign = calculate_appsign(draw_get_data, auth_token, SIGN_SECRET, ["activity_id", "play_time_start"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_get = "https://mpb.jingjiu.com/proxy-he/api/BlzLongcaobenActivity/wumianUserDrawGet"
        response_get = session.post(url=url_get,headers=base_headers,data=json.dumps(draw_get_data, ensure_ascii=False),timeout=15)
        result_get = response_get.json()
        if result_get.get("code") != 0:
            if "今日游戏已完成" in result_get.get('message', '未知错误'):
                print(f"☁️活动游戏：已完成")
            else:
                print(f"⭕活动游戏：{result_get.get('message', '未知错误')}")
            return
        user_record_id = result_get["data"].get("user_record_id")
        if not user_record_id:
            print("⭕活动游戏：未获取到user_record_id，无法继续抽奖")
            return
        print(f"☁️活动游戏：游戏完成")
        #print(f"⏳ 等待{wait_time}秒，满足活动时间要求...")
        time.sleep(random.randint(3, 8))
        # 执行抽奖
        draw_do_data = {"user_record_id": user_record_id,"play_time_finish": int(datetime.datetime.now().timestamp())}
        apptime, appsign = calculate_appsign(draw_do_data, auth_token, SIGN_SECRET, ["user_record_id", "play_time_finish"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url_do = "https://mpb.jingjiu.com/proxy-he/api/BlzLongcaobenActivity/wumianUserDraws"
        response_do = session.post(url=url_do,headers=base_headers,data=json.dumps(draw_do_data, ensure_ascii=False),timeout=15)
        result_do = response_do.json()
        if result_do.get("code") != 0:
            print(f"⭕抽奖失败：{result_do.get('message', '未知错误')}")
            return
        award_title = result_do["data"].get("awardLocal", {}).get("title", "")
        if not award_title:
            award_title = result_do["data"].get("award", {}).get("AwardName", "未知奖励")
        award_money = result_do["data"].get("awardLocal", {}).get("money", "0")
        print(f"🌈抽奖获得：{award_title}（{award_money}元）")
        try:
            award_code = result_do["data"].get("ucodeAward", {}).get("code", "")
            if award_code:
                #print(f"📌 奖励编码：{award_code}")
                pass
        except:
            #print(f"{result_do}")
            pass
    except Exception as e:
        print(f"❌ 抽奖任务异常：{str(e)}")


def subscribe_task(auth_token, session, tag):
    """订阅任务"""
    try:
        url = "https://mpb.jingjiu.com/proxy-he/api/BlzAppletIndex/taskSubscribeMessage"
        data = {"tag": tag}
        apptime, appsign = calculate_appsign(data, auth_token,SIGN_SECRET,["tag"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        response = session.post(url, headers=base_headers, data=json.dumps(data), timeout=10)
        result = response.json()
        if result.get("code") == 0:
            if "data" in result and "task" in result["data"]:
                task_name = result["data"]["task"].get("name", "未知任务")
                point = result["data"].get("point", 0)
                print(f"☁️【订阅_{task_name[-6:]}】： {point} 积分")
            else:
                print(f"⭕【订阅_{tag[-6:]}】：缺少数据字段")
        else:
            if "已达到上限" in result.get('message', '未知错误'):
                print(f"☁️【订阅_{tag[-6:]}】：已订阅")
            else:
                print(f"⭕【订阅_{tag[-6:]}】：{result.get('message', '未知错误')}")
    except Exception as e:
        print(f"⭕【订阅_{tag[-6:]}】：{str(e)}")


def view_video_task(auth_token, session, video_id):
    """观看视频任务"""
    try:
        url = "https://mpb.jingjiu.com/proxy-he/api/BlzAppletIndex/taskViewVideoView"
        data = {"video_id": video_id}
        apptime, appsign = calculate_appsign(data, auth_token,SIGN_SECRET,["video_id"])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        response = session.post(url, headers=base_headers, data=json.dumps(data), timeout=10)
        result = response.json()
        if result.get("code") != 0:
            print(f"⭕【视频_{video_id[-6:]}】：{result.get('message', '接口返回错误')}")
            return
        if "data" not in result:
            print(f"⭕【视频_{video_id[-6:]}】：缺少data字段")
            return
        data = result["data"]
        if "task" not in data :
            if "point" in data:
                print(f"☁️【视频_{video_id[-6:]}】：已观看")
            else:
                print(f"⭕【视频_{video_id[-6:]}】：缺少task字段")
                print(f"⭕【视频_{video_id[-6:]}】接口返回内容：{json.dumps(result, ensure_ascii=False)}")
            return
        task_name = data["task"].get("name", "未知视频任务")
        point = data.get("point", 0)
        print(f"☁️【视频_{task_name[-6:]}】：{point} 积分")
    except Exception as e:
        print(f"⭕【视频_{video_id[-6:]}】：{str(e)}")


def query_user_points(auth_token, session):
    """查询用户积分"""
    try:
        user_info_data = {}
        apptime, appsign = calculate_appsign(user_info_data, auth_token, SIGN_SECRET, [])
        base_headers["apptime"] = apptime
        base_headers["appsign"] = appsign
        url = "https://mpb.jingjiu.com/proxy-he/api/BlzAppletIndex/userInfoV2025"
        response = session.post(url=url,headers=base_headers,data=json.dumps(user_info_data, ensure_ascii=False),timeout=15)
        result = response.json()
        if result.get("code") != 0:
            print(f"⭕当前积分：{result.get('message', '未知错误')}")
            return "未知"
        return result["data"].get("user_show", {}).get("point", "未知")
    except Exception as e:
        print(f"⭕积分查询异常：{str(e)}")
        return "查询失败"

def lottery(auth_token, session):
    """抽奖"""
    try:
        for _ in range(5):
            user_info_data = {}
            url = "https://mpb.jingjiu.com/proxy-he/api/game/FlanTurntable/awardDraw"
            response = session.post(url=url,headers=base_headers,data=json.dumps(user_info_data, ensure_ascii=False),timeout=15)
            result = response.json()
            #print(result)
            if "成功" in result["message"]:
                name = result["data"]["award"]["name"]
                if "积分" in name:
                    print(f"☁️【积分抽奖】：{name}")
                elif "谢谢参与" in name:
                    print(f"☁️【积分抽奖】：谢谢参与")
                else:
                    print(f"🌈【积分抽奖】：{name}")
                time.sleep(3)
            else:
                print(f"☁️【积分抽奖】：次数用尽")
                break
    except Exception as e:
        print(f"⭕积分查询异常：{str(e)}")
        return "查询失败"


def run(auth_token, session):
    """执行单个账号的所有任务"""
    # 执行签到任务
    result = daily_sign_in(auth_token, session)
    if result and "授权过期" in result:
        return "auth_expired"
    #------------活动-----------
    #好友帮帮
    random_wait()
    haoyoubangbang_draw(auth_token, session)
    #识草寻源
    random_wait()
    shicaoxunyuan_draw(auth_token, session)
    #草本实验室
    random_wait()
    caobenshiyanshi_draw(auth_token, session)
    #无冕之王
    random_wait()
    wumian_draw(auth_token, session)
    #------------日常-----------
    print("☼ ――――  订  阅  ―――― ☼")
    random_wait()
    SUBSCRIBE_TAGS = ["subscribe_message_202410","subscribe_message_suyuan","subscribe_message_applet"]
    for tag in SUBSCRIBE_TAGS:
        subscribe_task(auth_token, session, tag)
        if tag != SUBSCRIBE_TAGS[-1]:
            random_wait(1, 3)
    print("☼ ――――  视  频  ―――― ☼")
    random_wait()
    VIDEO_IDS = ["video-117"]
    for video_id in VIDEO_IDS:
        view_video_task(auth_token, session, video_id)
        if video_id != VIDEO_IDS[-1]:
            random_wait(1, 3)
    print("☼ ――――  抽  奖  ―――― ☼")
    # 抽奖
    random_wait(1, 3)
    lottery(auth_token, session)
    print("☼ ――――  信  息  ―――― ☼")
    # 查询最终积分
    points = query_user_points(auth_token, session)
    print(f"☁️当前积分：{points} 积分")
    return "ok"

def push_notification():
    try:
        notify_send("毛铺草本荟签到结果", "\n".join(log_messages))
        print("消息推送完成")
    except Exception as exc:
        print(f"推送异常：{exc}")

def main():
    global id,base_headers
    accounts = parse_accounts()
    if not accounts:
        log(f"⭕请设置变量：{environ}=wxid#别名")
        sys.exit()
    log(f"{' ' * 7}{name}\n\n")
    log(f"-------- ☁️ 开 始 执 行 ☁️ --------")
    base_headers = {
        "content-type": "application/json",
        "x-version": "0.0.1",
        "Authorization": "",
        "charset": "utf-8",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; MI 8 Build/QKQ1.190828.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.180 Mobile Safari/537.36 XWEB/1380327 MMWEBSDK/20250904 MMWEBID/6533 MicroMessenger/8.0.65.2960(0x28004151) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android",
    }
    token_cache = load_token_cache()
    for i, account in enumerate(accounts):
        try:
            session = requests.session()
            comment = account.get("comment") or f"账号{i + 1}"
            used_cache = False
            if account["mode"] == "wxid":
                log(f"\n\n 账号 [{i + 1}/{len(accounts)}]:")
                id = mask_text(comment)
                log(f"☁️当前账号：{id}")
                log(f"☁️登录方式：wxid自动登录")
                auth_token = get_cached_auth_token(token_cache, account["wxid"])
                used_cache = bool(auth_token)
                if not auth_token:
                    auth_token = login_by_wxid(account["wxid"], session)
                    if auth_token:
                        save_cached_auth_token(token_cache, account["wxid"], comment, auth_token)
                if not auth_token:
                    log("⭕账号跳过：自动登录未获取到auth_token")
                    continue
            else:
                auth_token = account["auth_token"]
                log(f"\n\n 账号 [{i + 1}/{len(accounts)}]:")
                id = mask_text(comment)
                log(f"☁️当前账号：{id}")
                log(f"☁️登录方式：手动auth_token")
            base_headers["Authorization"] = auth_token
            run_status = run(auth_token, session)
            if account["mode"] == "wxid" and run_status == "auth_expired":
                log("☁️缓存/登录token已授权过期，清理缓存后重登一次")
                remove_cached_auth_token(token_cache, account["wxid"])
                if used_cache:
                    auth_token = login_by_wxid(account["wxid"], session)
                    if auth_token:
                        save_cached_auth_token(token_cache, account["wxid"], comment, auth_token)
                        base_headers["Authorization"] = auth_token
                        run(auth_token, session)
        except Exception as e:
            log(f"❌ 账号处理异常：{str(e)}")
    log(f"\n\n-------- ☁️ 执 行 结 束 ☁️ --------\n\n")
    push_notification()


if __name__ == '__main__':
    SIGN_SECRET = "DYSHJS^M&.YXZRGS"
    main()
