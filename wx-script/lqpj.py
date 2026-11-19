#!/usr/bin/env python3
# name: 漓泉啤酒生态营地
# cron: 30 9 * * *
# YYB-Go-Enhanced 适配说明：配置多行 YYB_SERVER=地址@账号标识；通知使用青龙 notify.py。
# -*- coding: utf-8 -*-
"""
name: 漓泉啤酒生态营地
cron: 30 9 * * *
"""
# 漓泉啤酒生态营地 - 每日签到得积分
# 入口: 微信小程序「漓泉啤酒生态营地」-> 会员中心 -> 每日签到
# 说明: 通过 yyb_go 自动获取存活账号并换取 wx.login code, 复刻小程序的
#       会员静默登录 (mbr/members/wxLogin/{code}) 拿到 Token, 再完成每日签到。
# 接口契约 (来自小程序主包 common/vendor.js 反编译):
#   登录  GET  /api/mbr/members/wxLogin/{code}?appId=<appid>
#            -> errcode==0 且 data.b2cMemberId/openid 存在; data.token 为会话凭证
#   鉴权  请求头 Token: <token>   (响应拦截器: errcode||code, 200 成功, 401 会话失效)
#   状态  GET  /api/b2c/member/sign/task/list  -> data.signRes.{sign, signNum,
#            taskSignDtoList[{signTime, signStatus}]}   sign==true / 今日行
#            signStatus=="sign" 即今日已签 (幂等预检依据)
#   验证  POST /api/smhd/captcha/get、/api/smhd/captcha/check -> 自动匹配拼图并校验
#   签到  POST /api/b2c/member/sign/task  body {captchaVerification: 验证结果}
#            -> code==200, data.signRes.sign==true
#   积分  GET  /api/b2c/member/pointsAndCouponCardNumAndShopCardInfo?unionId=<unionId>
#            -> data.MemberCouponShopPointsVo.pointsNum   (仅用于上报余额)
# 环境变量：
#   自动完成拼图验证；依赖 requests、Pillow、numpy、pycryptodome（或 cryptography）
#   YYB_SERVER      YYB-Go-Enhanced 路由，每行：地址@账号标识
#   账号直接来自 YYB_SERVER；无需配置 WX_ID / lqpj
#   YYB_API_KEY / YYB_PROTOCOL_TOKEN       启用协议鉴权时配置，二选一

import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# 将脚本所在目录加入搜索路径（确保能找到 yyb.py 等同目录模块）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ===== YYB-Go-Enhanced + QingLong standalone adapter =====
def _yyb_routes():
    routes = []
    for number, line in enumerate(os.getenv("YYB_SERVER", "").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if "@" not in line:
            raise RuntimeError(f"YYB_SERVER 第 {number} 行格式错误，应为 地址@账号标识")
        server, ref = line.rsplit("@", 1)
        if not server.strip() or not ref.strip():
            raise RuntimeError(f"YYB_SERVER 第 {number} 行格式错误，应为 地址@账号标识")
        server = server.strip().rstrip("/")
        if not server.lower().startswith(("http://", "https://")):
            server = "http://" + server
        routes.append({"server": server, "ref": ref.strip()})
    if not routes:
        raise RuntimeError("未配置 YYB_SERVER（每行：地址@账号标识）")
    return routes


def _yyb_clean_ref(value):
    text = str(value or "").split("#", 1)[0].strip()
    for prefix in ("wx:", "yyb:", "wmpf:", "syzs:"):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _yyb_route(identifier):
    routes = _yyb_routes()
    wanted = _yyb_clean_ref(identifier)
    for route in routes:
        if _yyb_clean_ref(route["ref"]) == wanted:
            return route
    if wanted.isdigit() and 0 < int(wanted) <= len(routes):
        return routes[int(wanted) - 1]
    if len(routes) == 1:
        return routes[0]
    raise RuntimeError(f"YYB_SERVER 中找不到账号标识：{wanted or '(空)'}")


def _yyb_call(endpoint, app_id, identifier):
    import requests as _requests
    route = _yyb_route(identifier)
    headers = {
            "Content-Type": "application/json"
        }
    api_key = os.getenv("YYB_API_KEY", "").strip() or os.getenv("YYB_PROTOCOL_TOKEN", "").strip()
    if api_key:
        headers["Authorization"] = api_key if " " in api_key else "Bearer " + api_key
    response = _requests.post(route["server"] + endpoint,
                              json={"ref": route["ref"], "app_id": app_id}, timeout=30, headers=headers)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or int(body.get("code", -1)) != 0:
        raise RuntimeError(f"{endpoint} 返回失败：{body.get('msg') or body.get('message') or body}")
    result = (body.get("data") or {}).get("result")
    if result is None:
        raise RuntimeError(f"{endpoint} 未返回 data.result")
    return result


class _YybClient:
    def get_online_accounts(self):
        return [{"id": x["ref"], "openid": x["ref"], "wxid": x["ref"],
                 "remark": f"YYB账号{i}", "status": "online", "login_type": "WX"}
                for i, x in enumerate(_yyb_routes(), 1)]

    def get_accounts(self, force_refresh=False):
        return self.get_online_accounts()


class _YybCompat:
    YYBClient = _YybClient

    @staticmethod
    def load_accounts(*_args, **_kwargs):
        return _YybClient().get_online_accounts()

    @staticmethod
    def resolve_accounts(env_name=""):
        return [x["ref"] for x in _yyb_routes()]

    @staticmethod
    def get_global_server_url():
        return _yyb_routes()[0]["server"]

    @staticmethod
    def get_single_code(app_id, identifier):
        result = _yyb_call("/wxapp/getCode", app_id, identifier)
        code = result if isinstance(result, str) else result.get("code")
        if not code:
            raise RuntimeError("/wxapp/getCode 未返回 data.result.code")
        return str(code)

    @staticmethod
    def get_single_phone_code(app_id, identifier, login_type=None):
        result = _yyb_call("/wxapp/getPhoneNumber", app_id, identifier)
        return str(result if isinstance(result, str) else result.get("code") or "")

    @staticmethod
    def normalize_login_type(value):
        return str(value or "WX").upper()

    @staticmethod
    def login_type_label(value):
        return {"WX": "应用宝", "WMPF": "微信小程序", "SYZS": "手游助手"}.get(
            _YybCompat.normalize_login_type(value), "应用宝")

    @staticmethod
    def _cache_path(name):
        import pathlib
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        return pathlib.Path(os.getenv("QL_DIR", "/ql/data")) / "config" / "yyb_token_caches" / f"{safe}.json"

    @classmethod
    def _read_cache(cls, name):
        try:
            return json.loads(cls._cache_path(name).read_text(encoding="utf-8"))
        except Exception:
            return {}

    @classmethod
    def get_cached_token(cls, name, identifier, options=None):
        item = cls._read_cache(name).get(_yyb_clean_ref(identifier))
        if not item:
            return None
        max_age = int((options or {}).get("max_age_ms", 0))
        if max_age and int(time.time() * 1000) - int(item.get("_saved_at", 0)) > max_age:
            return None
        return item

    @classmethod
    def save_cached_token(cls, name, identifier, value):
        data = cls._read_cache(name)
        data[_yyb_clean_ref(identifier)] = dict(value, _saved_at=int(time.time() * 1000))
        path = cls._cache_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    @classmethod
    def remove_cached_token(cls, name, identifier):
        data = cls._read_cache(name)
        data.pop(_yyb_clean_ref(identifier), None)
        path = cls._cache_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


yyb = _YybCompat()


def _send_qinglong_notify(title, content):
    import sys as _sys
    for path in (os.path.dirname(os.path.abspath(__file__)), "/ql/data/scripts", "/ql/scripts"):
        if path not in _sys.path:
            _sys.path.insert(0, path)
    try:
        from notify import send as _ql_send
        _ql_send(title, content)
        return True
    except Exception as exc:
        print(f"青龙通知失败（不影响任务结果）：{exc}")
        return False
# ===== adapter end =====


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    send = _send_qinglong_notify
except Exception:
    def send(title, content):
        print(f"\n===== {title} =====\n{content}")

# ---------------------------------------------------------------------------
# 常量 (均来自小程序反编译源码, 非机密)
# ---------------------------------------------------------------------------
MINI_APP_ID = "wx08dabaec2783f4e9"
BASE_URL = "https://api.mbr.liquan.com/api"          # vendor.js api_HOST
SUCCESS_CODE = 200
SESSION_INVALID_CODE = 401                            # 拦截器: 清 token 并重新登录
SIGNED = "sign"                                       # taskSignDtoList[].signStatus

# 账号列表：自动从 yyb_go 同步存活账号（可用 lqpj / WX_ID 指定白名单）
ACCOUNT_REFS = yyb.resolve_accounts("lqpj")

TOKEN_CACHE_PATH = Path(__file__).with_name("liquanpijiu_token_cache.json")
DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-G9910 Build/TP1A.220624.014) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36 "
    "MicroMessenger/8.0.49.2600(0x28003137) NetType/WIFI Language/zh_CN "
    "miniProgram/" + MINI_APP_ID
)

session = requests.Session()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def bj_now():
    return datetime.now(timezone(timedelta(hours=8)))


def mask(value):
    if not value:
        return ""
    value = str(value)
    if len(value) <= 12:
        return value[:2] + "***"
    return f"{value[:6]}***{value[-4:]}"


def read_token_cache():
    try:
        if TOKEN_CACHE_PATH.exists():
            return json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def write_token_cache(cache):
    try:
        TOKEN_CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ 写入token缓存失败: {e}")


def get_cached_session(openid):
    return read_token_cache().get(openid) or {}


def save_cached_session(openid, token, union_id):
    cache = read_token_cache()
    cache[openid] = {"token": token, "unionId": union_id,
                     "updatedAt": int(time.time())}
    write_token_cache(cache)


def remove_cached_session(openid):
    cache = read_token_cache()
    if openid in cache:
        del cache[openid]
        write_token_cache(cache)


# ---------------------------------------------------------------------------
# yyb_go: 账号标识 -> wx.login code
# ---------------------------------------------------------------------------
def get_wx_code(openid):
    """从 yyb_go 获取一次性微信 code（openid 为账号标识）"""
    try:
        code = yyb.get_single_code(MINI_APP_ID, str(openid).split("#")[0].strip())
        if code:
            print("✅ [授权] code 获取成功")
            return str(code)
        print("❌ [授权] code 获取失败")
        return None
    except Exception as exc:
        print(f"❌ [授权] code 获取异常: {exc}")
        return None


# ---------------------------------------------------------------------------
# 漓泉会员 API
# ---------------------------------------------------------------------------
def api_headers(token=None):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": DEFAULT_UA,
        "Referer": f"https://servicewechat.com/{MINI_APP_ID}/0/page-frame.html",
    }
    if token:
        headers["Token"] = token            # 请求拦截器: headers.Token = 本地 token
    return headers


def api_get(path, token=None, params=None):
    resp = session.get(f"{BASE_URL}{path}", params=params or {},
                       headers=api_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(path, body, token=None):
    resp = session.post(f"{BASE_URL}{path}",
                        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                        headers=api_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()


def resp_code(resp):
    """拦截器口径: errcode 优先, 否则 code。"""
    node = resp if isinstance(resp, dict) else {}
    for key in ("errcode", "code"):
        v = node.get(key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return -1


def resp_msg(resp):
    node = resp if isinstance(resp, dict) else {}
    for key in ("errmsg", "message", "msg"):
        v = node.get(key)
        if v:
            return str(v)
    data = node.get("data")
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return ""


# ---------------------------------------------------------------------------
# 登录 / 会话
# ---------------------------------------------------------------------------
def login(openid):
    """wx.login code -> wxLogin -> (token, unionId)。code 放在 URL 路径中。"""
    code = get_wx_code(openid)
    resp = api_get(f"/mbr/members/wxLogin/{code}", params={"appId": MINI_APP_ID})
    if resp_code(resp) != 0:
        raise RuntimeError(f"登录失败: {resp_msg(resp) or resp_code(resp)}")
    data = resp.get("data") or {}
    token = data.get("token")
    union_id = data.get("unionid") or (data.get("wxUserInfo") or {}).get("unionId")
    if not (token and data.get("b2cMemberId")):
        raise RuntimeError("登录响应缺少 token/b2cMemberId, 需在小程序内登录一次后重试")
    return token, union_id


def obtain_session(openid, index, force=False):
    if force:
        remove_cached_session(openid)
    else:
        cached = get_cached_session(openid)
        if cached.get("token"):
            print(f"账号 {index} 使用缓存 token: {mask(cached['token'])}")
            return cached["token"], cached.get("unionId")
    token, union_id = login(openid)
    save_cached_session(openid, token, union_id)
    print(f"账号 {index} 静默登录成功: {mask(token)}")
    return token, union_id


# ---------------------------------------------------------------------------
# 签到业务
# ---------------------------------------------------------------------------
def sign_state(token):
    return api_get("/b2c/member/sign/task/list", token=token)


def match_puzzle(original_base64, jigsaw_base64):
    import numpy as np
    from PIL import Image, ImageFilter

    def decode(value):
        raw = base64.b64decode(value.split(",", 1)[-1], validate=True)
        if len(raw) > 5_000_000:
            raise ValueError("验证码图片过大")
        result = Image.open(io.BytesIO(raw))
        if not (10 <= result.width <= 1000 and 10 <= result.height <= 1000):
            raise ValueError("验证码图片尺寸异常")
        return result

    bg = np.asarray(decode(original_base64).convert("RGB"), dtype=np.float64)
    piece = decode(jigsaw_base64).convert("RGBA")
    if piece.height != bg.shape[0] or piece.width >= bg.shape[1]:
        raise ValueError("验证码图片布局变化，需要更新匹配逻辑")
    # 消除拼图白色描边后，按各颜色通道去均值，匹配暗化缺口中的原图纹理。
    mask = np.asarray(piece.getchannel("A").filter(ImageFilter.MinFilter(5))) > 240
    ys, xs = np.where(mask)
    if len(xs) < 50:
        raise ValueError("验证码拼图缺少有效像素")
    template = np.asarray(piece, dtype=np.float64)[ys, xs, :3]
    template -= template.mean(axis=0)
    norm = np.linalg.norm(template)
    if norm < 1:
        raise ValueError("验证码拼图纹理不足")
    scores = []
    for x in range(5, bg.shape[1] - piece.width + 1):
        candidate = bg[ys, xs + x].copy()
        candidate -= candidate.mean(axis=0)
        score = float(np.sum(template * candidate) / (norm * np.linalg.norm(candidate) + 1e-9))
        scores.append((score, x))
    scores.sort(reverse=True)
    score, x = scores[0]
    competing = max((s for s, pos in scores if abs(pos - x) > 4), default=-1)
    if score < 0.45 or score - competing < 0.08:
        raise ValueError(f"拼图匹配置信度不足 ({score:.3f}/{competing:.3f})")
    return int(x * 310 / bg.shape[1] + 0.5), score


def captcha_encrypt(text, secret_key):
    if not secret_key:
        return text
    key = secret_key.encode("utf-8")
    data = text.encode("utf-8")
    size = 16 - len(data) % 16
    padded = data + bytes([size]) * size
    try:
        from Crypto.Cipher import AES
        encrypted = AES.new(key, AES.MODE_ECB).encrypt(padded)
    except ImportError:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")


def solve_captcha(token, post, attempts=3):
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            challenge = post("/smhd/captcha/get", {"captchaType": "blockPuzzle"}, token=token)
            if str(challenge.get("repCode")) != "0000":
                raise RuntimeError(challenge.get("repMsg") or "获取验证码失败")
            data = challenge.get("repData") or {}
            if not data.get("token"):
                raise ValueError("验证码响应缺少 token")
            x, score = match_puzzle(data["originalImageBase64"], data["jigsawImageBase64"])
            point = json.dumps({"x": x, "y": 5}, separators=(",", ":"))
            key = data.get("secretKey") or ""
            result = post("/smhd/captcha/check", {
                "captchaType": "blockPuzzle", "token": data["token"],
                "pointJson": captcha_encrypt(point, key),
            }, token=token)
            if str(result.get("repCode")) != "0000":
                raise RuntimeError(result.get("repMsg") or "滑块校验失败")
            print(f"✅ 滑块验证通过（第 {attempt} 次，匹配度 {score:.3f}）")
            return captcha_encrypt(data["token"] + "---" + point, key)
        except (ImportError, ModuleNotFoundError) as exc:
            raise RuntimeError("自动滑块缺少依赖，请安装 Pillow、numpy、pycryptodome") from exc
        except (ValueError, KeyError, RuntimeError) as exc:
            last_error = str(exc)
            print(f"⚠️ 滑块验证第 {attempt}/{attempts} 次失败：{last_error}")
            if attempt < attempts:
                time.sleep(1)
    raise RuntimeError(f"自动滑块验证失败（已尝试 {attempts} 次）：{last_error}")


def do_sign(token):
    verification = solve_captcha(token, api_post)
    return api_post("/b2c/member/sign/task", {"captchaVerification": verification}, token=token)


def points_balance(token, union_id):
    """仅读取积分余额用于上报, 失败返回 None (不影响签到结论)。"""
    if not union_id:
        return None
    try:
        resp = api_get("/b2c/member/pointsAndCouponCardNumAndShopCardInfo",
                       token=token, params={"unionId": union_id})
        if resp_code(resp) != SUCCESS_CODE:
            return None
        vo = (resp.get("data") or {}).get("MemberCouponShopPointsVo") or {}
        return vo.get("pointsNum")
    except Exception:
        return None


def sign_res(resp):
    data = resp.get("data") if isinstance(resp, dict) else None
    if isinstance(data, dict) and isinstance(data.get("signRes"), dict):
        return data["signRes"]
    return {}


def signed_today(res):
    """今日已签: signRes.sign 为真, 或今日日期行 signStatus == 'sign'。"""
    if res.get("sign") is True:
        return True
    today = bj_now().strftime("%Y-%m-%d")
    for row in res.get("taskSignDtoList") or []:
        if row.get("signTime") == today and row.get("signStatus") == SIGNED:
            return True
    return False


def fmt_num(value):
    """服务端 signNum 为浮点(1.0), 展示成整数更自然。"""
    try:
        f = float(value)
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(value)


def run_account(openid, index):
    lines = [f"【账号 {index}】"]

    token, union_id = obtain_session(openid, index)

    # 读取签到状态 (首个鉴权调用); 会话失效则强制重登重试一次
    state = sign_state(token)
    if resp_code(state) == SESSION_INVALID_CODE:
        print(f"账号 {index} 会话失效, 重新登录...")
        token, union_id = obtain_session(openid, index, force=True)
        state = sign_state(token)

    scode = resp_code(state)
    if scode != SUCCESS_CODE:
        msg = resp_msg(state) or f"获取签到状态失败 code={scode}"
        print(f"❌ 账号 {index} {msg}")
        lines.append(f"❌ {msg}")
        return "\n".join(lines), False

    res = sign_res(state)

    # 幂等预检: 今日已签则不再提交
    if signed_today(res):
        msg = f"今日已签到, 无需重复 (本周已签 {fmt_num(res.get('signNum'))} 天)"
        print(f"✅ 账号 {index} {msg}")
        lines.append(f"✅ {msg}")
        pts = points_balance(token, union_id)
        if pts is not None:
            lines.append(f"当前积分: {pts}")
            print(f"账号 {index} 当前积分: {pts}")
        return "\n".join(lines), True

    # 执行一次签到
    result = do_sign(token)
    rcode = resp_code(result)
    if rcode == SESSION_INVALID_CODE:
        print(f"账号 {index} 会话失效, 重新登录后重试签到...")
        token, union_id = obtain_session(openid, index, force=True)
        result = do_sign(token)
        rcode = resp_code(result)

    if rcode != SUCCESS_CODE:
        msg = resp_msg(result) or f"签到失败 code={rcode}"
        print(f"❌ 账号 {index} {msg}")
        lines.append(f"❌ {msg}")
        return "\n".join(lines), False

    res = sign_res(result)
    if not signed_today(res) and res.get("sign") is not True:
        msg = resp_msg(result) or "签到接口返回成功但未标记已签, 请稍后重试"
        print(f"⚠️ 账号 {index} {msg}")
        lines.append(f"⚠️ {msg}")
        return "\n".join(lines), False

    msg = f"签到成功, 本周已签 {fmt_num(res.get('signNum'))} 天"
    print(f"🎉 账号 {index} {msg}")
    lines.append(f"🎉 {msg}")

    pts = points_balance(token, union_id)
    if pts is not None:
        lines.append(f"当前积分: {pts}")
        print(f"账号 {index} 当前积分: {pts}")
    return "\n".join(lines), True


def main():
    entries = ACCOUNT_REFS

    if not entries:
        print("❌ 未从 yyb_go 获取到存活账号(可配置环境变量 lqpj 指定白名单), 退出。")
        return

    print("=============== 漓泉啤酒 签到开始 ===============")
    summaries = []
    ok_count = 0
    for i, entry in enumerate(entries, 1):
        parts = entry.split("#", 1)
        openid = parts[0].strip()
        remark = parts[1].strip() if len(parts) > 1 else ""
        print(f"\n-------------- 账号 {i}{('/' + remark) if remark else ''} --------------")
        try:
            summary, ok = run_account(openid, i)
            summaries.append(summary)
            ok_count += 1 if ok else 0
        except Exception as e:
            print(f"❌ 账号 {i} 执行异常: {e}")
            summaries.append(f"【账号 {i}】\n❌ 执行异常: {e}")
        time.sleep(1)

    print("\n=============== 漓泉啤酒 签到结束 ===============")
    title = f"漓泉啤酒签到 {ok_count}/{len(entries)} 成功"
    try:
        send(title, "\n\n".join(summaries))
    except Exception as e:
        print(f"⚠️ 通知发送失败: {e}")


if __name__ == "__main__":
    main()
