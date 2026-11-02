#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# name: 移动云盘
# cron: 0 0 8,16,20 * * *
"""
移动云盘自动签到_code版v5.3.3

包含以下功能:
1. 每日自动签到 (签到/抽奖/摇一摇/新版云朵领取)
2. 多账号支持 (YYB 授权账号 + 环境变量账号，串联执行)
3. 云朵中心新版任务自动处理 (上传/分享/AI相机/月任务补传等)
4. 临时文件智能清理与详细日志推送

执行顺序:
默认先依次登录全部 YYB 账号并跑完，再跑 ydyp 环境变量里的账号。
两种来源按手机号去重，同一手机号优先使用 YYB 换发的新凭证。

配置说明:

变量名: ydyp
赋值方式:
格式：Authorization值#手机号
抓包获取 Authorization方法：
1.登录https://yun.139.com，cookie中找到Authorization字段，复制其值。
2.登陆网址抓取https://sm.linzixuan.top/

YYB 登录：
YYB_SERVER：每行一个 服务地址@账号ref。
YDYP_YYB_SERVER：可选，仅覆盖本脚本的服务与账号列表。
YDYP_YYB_REFS：可选，账号ref白名单，以 &、逗号或换行分隔。
YDYP_YYB_TOKEN：可选，优先于 YYB_PROTOCOL_TOKEN / YYB_API_KEY。
微信账号须具备目标小程序手机号授权能力；本脚本不发送短信或自动开户。
登录手机号由 YYB 的授权结果决定；脚本不支持任选微信内的其他手机号。

YDYP_LOGIN_MODE：
不设置 / mixed = YYB 账号优先，跑完后继续跑 ydyp 账号（默认）
yyb   = 只跑 YYB 账号
cookie = 只跑 ydyp 账号

⚠️ 依赖安装:
pip3 install requests pycryptodome

定时规则建议 (Cron):
0 0 8,16,20 * * * (每日早中晚执行)
"""

import base64
import hashlib
import json
import os
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from os import path
from pathlib import Path
from urllib.parse import unquote

import requests

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    AES = None
    pad = None
    unpad = None

SCRIPT_VERSION = '5.3.3'

YDYP_WX_APPID = 'wx4e4ed37286c816c2'
YDYP_WX_VERSION = '5.14.4'
# 小程序 142 包 common/config/index.js / components/verifyModal/utils.js。
# 这是客户端协议常量，不是账号凭据。
YDYP_COOL_FLAG_KEY = b'taNk805XxEM4uDWvVTMo+BVe'
YDYP_USER_ZONE_KEY = b'qPqDw263XgFgL3u8'
YDYP_USER_BASE_URL = 'https://user-njs.yun.139.com/user'

TOKEN_STORAGE_FILENAME = 'ydyp_token_storage.json'
DEVICE_ID_STORAGE_FILENAME = ''

# ============ v5.2.0 鉴权网关（移动云盘 13.2.5 逆向结果）============
# 云朵中心已整体迁移到 gp 网关；ssoToken -> jwtToken 的换取接口从
# 旧 caiyun.feixin.10086.cn:7071/portal/auth/tyrzLogin.action（已下线 404）
# 变更为 gp.mcloud.139.com/ycloud/auth-service/auth/tyrzLogin，并新增
# x-request-id / x-timestamp / x-nonce / x-signature 四段式签名校验。
# 签名算法（app 内置 H5 newsignin 静态包，module 4192）：
#   md5(secret + requestId + timestamp + nonce + "" + secret)  小写 hex
# secret 由 H5 代码 String.fromCodePoint 数组还原，属客户端协议常量。
YDYP_GATEWAY_HOST = 'https://gp.mcloud.139.com'
YDYP_SIGN_SECRET = 'sekaMdYYLIZfbCfm'
YDYP_MARKET_NAME = 'sign_in_3'
YDYP_AUTH_PATH = '/ycloud/auth-service/auth/tyrzLogin'
YDYP_TIMESTAMP_PATH = '/ycloud/api/timestamp'
# 云朵中心现役网关移动端 UA（13.2.5 内嵌 H5 实测值），空 ua 时兜底使用。
DEFAULT_MOBILE_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) '
                     'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 mcloud/13.2.5')

# ⭐ 统一设备信息：iPhone 16 Pro + iOS 18_7 + 版本 12.5.4（抓包真实值）
ua = DEFAULT_MOBILE_UA
market_ua = DEFAULT_MOBILE_UA
cloud_file_dummy_content = b'0'
cloud_file_dummy_hash = hashlib.sha256(cloud_file_dummy_content).hexdigest()
TOKEN_VALID_TIME = 21600000
TOKEN_REFRESH_ADVANCE = 24 * 60 * 60 * 1000
TOKEN_REFRESH_COOLDOWN = 864000
REFRESH_TOKEN_AES_KEY = 'c7lXOigXahPnTViq'
AI_TOOL_ACCOUNT_AES_KEY = 'xuL97!x7GGxG%8V4'
AI_TOOL_ACCOUNT_AES_IV = '5OuCxk4XNu0NA*%x'
TOKEN_EXPIRE_SECONDS_FALLBACK = 2592000

err_accounts = ''  # 异常账号
all_logs = ''  # 所有用户的详细运行日志 (原 err_message)
user_amount = ''  # 用户云朵·数量
GLOBAL_DEBUG = False


def current_millis():
    return int(time.time() * 1000)


def normalize_authorization(token):
    token = (token or '').strip()
    if token and not token.startswith('Basic '):
        return f'Basic {token}'
    return token


def random_string(length=16):
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(random.choice(chars) for _ in range(length))


def generate_uuid():
    return ''.join([random_string(8), '-', random_string(4), '-4', random_string(3), '-', random.choice('89ab'), random_string(3), '-', random_string(12)])


# 真实抓包 deviceId（base64 格式，iOS iPhone 16 Pro + iOS 18_7）
REAL_DEVICE_ID = ''

DEVICE_PROFILE_URL = "https://slw.h5cmpassport.com:9090/deviceprofile/v4"
DEVICE_PROFILE_PAYLOAD = {
    "appId": "default",
    "organization": "FXlyfmWg2AzwbrxDKSv5",
    "ep": "WydTnuOv+Rtg/Qj8Q4vnhSXJN4UHQPF2jjs+LVJkD3u8HXglndPAndOgrlmg2Q8q0FUQRZpN0N7e61ebhjw/Gba22ydgOMbBRfbSmKSnNWaACA+MzAX5Q4dd980zPqelMxGVzB3jkr1wGE6cVQkwWFq/xbdnkK/Sh6xrPDjYvho=",
    "data": "5b5f2054405d6155102ed35a134758f768e60b7c1ac7af66acb16871d78a099cbcbabb3fb5ebeefe6cbae063407fca585a343ce5bef4f4e4588df42ca8ae8a6504b3646066fd7dc46465a83d510fbb477ba72f7375db7cbcba9b712ec88d85fc8d410536b96ca644c8ca3afbca00e0084ad9709b93b86923bf1fadef48be3e888b52dd2775c180b5b8e7bae139fadf2944f73010be9704daa6f4cf596b4adccff7b5de84e45698b781d963b69fa8ec28e43083512ab5749ea05c4efce14945d647c9f33d6296750ff2ba59bff5b7fcf698ffa146b7fe7e5c405b13100818b53fd034d05edea63c8365d9113bc7d4c0652892fcae75cdb491ae0215fbd822b1877b209fc8c68710badc6915080b7b994fa4b86a8f7b37e929cecbd1c590ad7382beb3ae8b9cc56ed84e927cbe41d8b4b15bbeecc69f5463d402cc2732fe5b76ec201632afbc16228531a65c1810482e4eb48157bc8b23cd363c6809a3fd629e3520514c06a720616e1788fe10203f9ebfa1de24c66213e334e3a3b3ff8a8866b7aefd9b4f2c88d216f45b551d693433940569092f0c7aca25019dc2003e8eab1967ac1dc32b0912701b0abc17e0509bada0cf0fcbe3c5fb64f0d5c6f02303b1540829a301673da89f7460d00190bda07c9b82c263277066f8e7e91c4916f247f9d9fe295a46d16cd087cee865d9e50edeb8e88842c560b09f853b5f89d2d0c4ed160f5bc293f7c69ece9e2d64d7217857fd2d64d57bea1ccea1b52896bb9aaf2ec3baa2421bce8d011813a1b26f0acb3a3cf594298bd725f8da17717b965f85e46a52c758ed1e95218e06f7e96a9f13e4855a0bb4bcf8b5f571887ec58c7438e99f06562414bcb274038fe6ffc1b8991021e35866cef5010184e3fbbd49c19d6020315731e9e57b7cd6a1e8b33c97746a782f9b4a26696966f40324f1ff76d3d1d24bf544230438dc32ab26d6dc107adf9feac34ffbbaa8814cec674e9469de54a714273a47f4fd06561e611f6741a4f0362a3b8821b0c69a3a04ced876fbf1b5fdc58097b1d7087aa2c0df556f8a06288db8c306cda4525d91c0452a0d2747982bd70b31c6905d4e483e8519d4d605af776be2a81224e3a6cc0b6ec49ad2cdb434bd85b5079ff86f68bf5ebb41336f30ec84fe19fabbd10a4422a274a3749d70c6b39cf7cdc1eb0cb228abee2475d16c57635a332628727b76a1fac0b26bf7bbdf4c5b956261919e7d2bd67733656855503670d48fe3680d04b65aac48d99bd47aedb6091c0a6df53be5bd662c1130feb6b469578cb146e1ae004471641fbc028cc06b80cfcdc50f8231e58b4126ab750b1d02eb8ac417b53a5ae50846db9aeadf4f1c98e33228db5143cb3d928217b769eaf32d181320a0bee4805334c28a03995d925b52fda358d19c52e3838c243b8c7d3256337943705c1311526c290fad975b7d7ade4bbc9292dbd7b9c0314715ef3c785a720e674dc23538af333cc6ff541aea70086287a8b4407c66ce673c9a47268de014c876a3a6a577d501285f6f489e2519f51bf4feafe307333a9e077f613527bbe1ce632127df654588410f713bb4a61e050cae618e98cc9adbb77d9df95733449c06e62094f3cdaf2ba39f94223ed7ca63ea4dec37d7283bdd0d2015511e7e57212073a540b308b10d7f85de73865fc2ffbf05a85ae25a7b52f0292236ee75f738add8144c7b2767a2100451363a47c12dfb674bd3ee000fa41565e9fbc60440a629160a2d2a99ec23dccc6815f644a2dd1eb059ab8593d9b04b1b81f5e427570cfc06eba8456b68159e6886843bcf4374b02de2e5be8d900882f78a71c2f3819d2e9c45e64b5d006c7a5914d1482f01ed5c0cfb44c3543656e96b5d91b39cd667af4dc60f44752da28eda57d2453d26a099529a2a38c9b9b2f0a73a69445030321b0a87287f6469f4d585739cded2e79c66df9c949eb7b2b8a8ff78e80a88ca494f3410195e021ec5009f8cd29781f09d58e6f866102072f1cee202c6ce21d72795b47a0ab8464fa54836c36a28ff73828e7a39dd1203d5a051ac4cd22b4f8c9f1e4e9c42f0c85b101b1eb495c0a767697dccab920489fae867ff38c5f917aec269d0ac9a1d6005407db762349d77e990581e19b1912fc975a9cdd2",
    "os": "web",
    "encode": 5,
    "compress": 2,
}


def fetch_device_id():
    """从设备指纹接口获取 deviceId，加 B 前缀"""
    try:
        resp = requests.post(
            DEVICE_PROFILE_URL,
            json=DEVICE_PROFILE_PAYLOAD,
            headers={
                "Content-Type": "application/json;charset=utf-8",
                "Origin": "https://m.mcloud.139.com",
                "Referer": "https://m.mcloud.139.com/",
            },
            timeout=15,
        )
        data = resp.json()
        raw_id = data.get("detail", {}).get("deviceId", "")
        if raw_id:
            return "B" + raw_id
    except Exception as e:
        print(f"  获取设备指纹失败: {e}")
    return ""


def generate_device_id():
    if REAL_DEVICE_ID:
        return REAL_DEVICE_ID
    device_info = {'deviceId': uuid.uuid4().hex.upper(), 'brand': 'Apple', 'model': 'iPhone 16 Pro', 'system': 'iOS 18.7', 'timestamp': current_millis()}
    raw = json.dumps(device_info, ensure_ascii=False, separators=(',', ':'))
    return base64.b64encode(raw.encode('utf-8')).decode('utf-8')


def get_env_device_id():
    return ''


def build_x_device_info(device_id, net_type='wifi', terminal_type='8', version='12.5.4', brand='Apple', model='iPhone 16 Pro', system='iOS 18.7'):
    """构造 x-DeviceInfo 头，与 UA 保持一致"""
    return f"{net_type}||{terminal_type}|{version}|{brand}|{model}|{device_id}||{system.lower()}|||||"


def fetch_gateway_timestamp(session=None, timeout=8):
    """取 gp 网关服务端毫秒时间戳；失败时回退本地时钟。

    网关要求 x-timestamp 与服务端偏差在允许窗口内，本地时钟漂移会导致
    签名校验 401，因此优先取服务端时间。
    """
    requester = session or requests
    try:
        resp = requester.get(YDYP_GATEWAY_HOST + YDYP_TIMESTAMP_PATH, timeout=timeout)
        data = resp.json()
        result = data.get('result')
        if isinstance(result, int) and result > 0:
            return str(result)
        if isinstance(result, str) and result.isdigit():
            return result
    except Exception:
        pass
    return str(int(time.time() * 1000))


def build_gateway_sign_headers(session=None, extra=None):
    """生成 tyrzLogin 所需的签名头。

    与 H5 实现一一对应：
        requestId  = uuid4()
        timestamp  = 服务端毫秒时间戳（字符串）
        nonce      = uuid4()
        signature  = md5(secret + requestId + timestamp + nonce + "" + secret)
    注意：crypto-js 的 MD5().toString() 输出小写 hex，服务端按小写比对。
    """
    request_id = str(uuid.uuid4())
    timestamp = fetch_gateway_timestamp(session)
    nonce = str(uuid.uuid4())
    raw = YDYP_SIGN_SECRET + request_id + timestamp + nonce + '' + YDYP_SIGN_SECRET
    signature = hashlib.md5(raw.encode('utf-8')).hexdigest()
    headers = {
        'Content-Type': 'application/json;charset=UTF-8',
        'x-request-id': request_id,
        'x-timestamp': timestamp,
        'x-nonce': nonce,
        'x-signature': signature,
        'X-Requested-With': 'XMLHttpRequest',
    }
    if extra:
        headers.update(extra)
    return headers





def is_transient_error(msg):
    """判断错误是否为上游瞬时故障（可用重试/下轮恢复），而非凭证或配置问题。"""
    text = str(msg or '').lower()
    markers = ('connection refused', 'timeout', 'timed out', 'bad gateway',
               'service unavailable', 'server error', '接口无响应',
               '502', '503', '504', '501', '429', '上游')
    return any(m in text for m in markers)


def build_builtin_jpeg_sample(width=320, height=240):
    """零依赖生成一张可解码的纯色 JPEG（AI 相机识图最小素材）。

    不依赖 PIL：手写 JPEG 基线编码（灰度单分量、4 个 Huffman 表、
    8x8 DCT 全零 AC + 固定 DC），结构合法可被服务端正常解码。
    """
    try:
        out = bytearray()
        out += b'\xff\xd8'  # SOI

        # DQT: 全 1 量化表，保证 DC 系数解码后为平滑色块
        out += b'\xff\xdb' + (67).to_bytes(2, 'big') + b'\x00' + bytes([1] * 64)

        # SOF0: 8bit 灰度单分量
        out += b'\xff\xc0' + (11).to_bytes(2, 'big') + b'\x08'
        out += height.to_bytes(2, 'big') + width.to_bytes(2, 'big')
        out += b'\x01' + b'\x01\x11\x00'

        # DHT: DC 表（标准表 0）+ AC 表（标准表 0）
        dc_bits = bytes([0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0])
        dc_vals = bytes(range(12))
        out += b'\xff\xc4' + (2 + 1 + 16 + 12).to_bytes(2, 'big') + b'\x00' + dc_bits + dc_vals

        ac_bits = bytes([0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7d])
        ac_vals = bytes([
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12,
            0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
            0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xa1, 0x08,
            0x23, 0x42, 0xb1, 0xc1, 0x15, 0x52, 0xd1, 0xf0,
            0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0a, 0x16,
            0x17, 0x18, 0x19, 0x1a, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2a, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39,
            0x3a, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
            0x4a, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5a, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
            0x6a, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
            0x7a, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8a, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98,
            0x99, 0x9a, 0xa2, 0xa3, 0xa4, 0xa5, 0xa6, 0xa7,
            0xa8, 0xa9, 0xaa, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6,
            0xb7, 0xb8, 0xb9, 0xba, 0xc2, 0xc3, 0xc4, 0xc5,
            0xc6, 0xc7, 0xc8, 0xc9, 0xca, 0xd2, 0xd3, 0xd4,
            0xd5, 0xd6, 0xd7, 0xd8, 0xd9, 0xda, 0xe1, 0xe2,
            0xe3, 0xe4, 0xe5, 0xe6, 0xe7, 0xe8, 0xe9, 0xea,
            0xf1, 0xf2, 0xf3, 0xf4, 0xf5, 0xf6, 0xf7, 0xf8,
            0xf9, 0xfa,
        ])
        out += b'\xff\xc4' + (2 + 1 + 16 + len(ac_vals)).to_bytes(2, 'big') + b'\x10' + ac_bits + ac_vals

        # SOS
        out += b'\xff\xda' + (8).to_bytes(2, 'big') + b'\x01\x01\x00\x00\x3f\x00'

        # 熵编码数据：每个 MCU 的 DC 差分为 0（码字 '00'），AC 全 EOB（'1010'）
        mcu_cols = (width + 7) // 8
        mcu_rows = (height + 7) // 8
        bits = ('00' + '1010') * (mcu_cols * mcu_rows)
        bits += '1' * ((8 - len(bits) % 8) % 8)
        data = bytearray()
        for i in range(0, len(bits), 8):
            byte = int(bits[i:i + 8], 2)
            data.append(byte)
            if byte == 0xFF:
                data.append(0x00)
        out += bytes(data)
        out += b'\xff\xd9'  # EOI
        return bytes(out)
    except Exception:
        return b''


def aes_encrypt(data, key):
    if AES is None or pad is None:
        raise ImportError('未安装 pycryptodome，无法执行 Token 自动刷新')
    key_bytes = key.encode('utf-8')
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
    return base64.b64encode(encrypted).decode('utf-8')


def extract_raw_token(token, account):
    token = normalize_authorization(token)
    if token.startswith('Basic '):
        token = token[6:]
    try:
        decoded = base64.b64decode(token).decode('utf-8')
        parts = decoded.split(':')
        if len(parts) >= 3:
            return parts[2]
    except Exception:
        pass
    return token


def build_authorization(account, raw_token):
    return f"Basic {base64.b64encode(f'mobile:{account}:{raw_token}'.encode()).decode()}"


def encrypt_cloud_login_body(data, iv=None):
    """复现小程序 aesEncrypt：Base64(16字节IV + AES-CBC密文)。"""
    if AES is None or pad is None:
        raise RuntimeError('YYB 登录需要安装 pycryptodome')
    iv = iv if iv is not None else random_string(16).encode('ascii')
    if not isinstance(iv, bytes) or len(iv) != 16:
        raise ValueError('云盘登录 IV 必须为16字节')
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    cipher = AES.new(YDYP_COOL_FLAG_KEY, AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(pad(text, AES.block_size))).decode('ascii')


def decrypt_cloud_login_response(text):
    if AES is None or unpad is None:
        raise RuntimeError('YYB 登录需要安装 pycryptodome')
    try:
        # 兼容服务器直接返回 JSON 的错误响应；正常响应为 CBC 密文。
        if text.lstrip().startswith('{'):
            result = json.loads(text)
        else:
            raw = base64.b64decode(text.strip(), validate=True)
            if len(raw) < 32 or (len(raw) - 16) % 16:
                raise ValueError('invalid ciphertext')
            cipher = AES.new(YDYP_COOL_FLAG_KEY, AES.MODE_CBC, raw[:16])
            result = json.loads(unpad(cipher.decrypt(raw[16:]), AES.block_size).decode('utf-8'))
        if not isinstance(result, dict):
            raise ValueError('invalid response')
        return result
    except (ValueError, TypeError, UnicodeError) as exc:
        raise RuntimeError('云盘登录响应解码失败') from exc


def decode_cloud_login_data(data):
    """当前小程序登录结果的 data 是 userZoneKey 加密的十六进制密文。"""
    if isinstance(data, dict):
        return data
    try:
        raw = bytes.fromhex(data)
        cipher = AES.new(YDYP_USER_ZONE_KEY, AES.MODE_ECB)
        result = json.loads(unpad(cipher.decrypt(raw), AES.block_size).decode('utf-8'))
        if not isinstance(result, dict):
            raise ValueError('invalid data')
        return result
    except (ValueError, TypeError, UnicodeError, AttributeError) as exc:
        raise RuntimeError('云盘登录结果解密失败') from exc


def parse_yyb_accounts(value, allowed_refs=None):
    accounts, seen = [], set()
    for line_no, raw in enumerate((value or '').splitlines(), 1):
        item = raw.strip()
        if not item:
            continue
        if '@' not in item:
            raise ValueError(f'YYB 配置第 {line_no} 行缺少 @')
        server, ref = (x.strip() for x in item.rsplit('@', 1))
        if not server or not ref:
            raise ValueError(f'YYB 配置第 {line_no} 行地址或账号为空')
        if not server.startswith(('http://', 'https://')):
            server = 'http://' + server
        server = server.rstrip('/')
        if allowed_refs is not None and ref not in allowed_refs:
            continue
        # 同一微信账号不重复取码；同一云盘手机号在登录后再次去重。
        if ref not in seen:
            seen.add(ref)
            accounts.append((server, ref))
    return accounts


def login_with_yyb(server, ref, session=None):
    """复现当前生产页面的 phoneCode/pintype=27，不使用遗留公众号登录。"""
    if AES is None or unpad is None:
        raise RuntimeError('YYB 登录需要安装 pycryptodome')
    owned_session = session is None
    session = session or requests.Session()
    if owned_session:
        session.trust_env = False
    try:
        protocol_token = (os.getenv('YDYP_YYB_TOKEN') or os.getenv('YYB_PROTOCOL_TOKEN') or os.getenv('YYB_API_KEY') or '').strip()
        code_headers = {'Content-Type': 'application/json'}
        if protocol_token:
            code_headers['Authorization'] = 'Bearer ' + protocol_token
        code_response = session.post(
            server + '/wxapp/getPhoneNumber',
            json={'ref': ref, 'app_id': YDYP_WX_APPID},
            headers=code_headers, timeout=45,
        )
        if code_response.status_code != 200:
            raise RuntimeError(f'YYB 手机号授权 HTTP {code_response.status_code}')
        try:
            envelope = code_response.json()
        except ValueError as exc:
            raise RuntimeError('YYB 返回的不是 JSON，请检查服务地址') from exc
        data = envelope.get('data') if isinstance(envelope, dict) else None
        result = data.get('result') if isinstance(data, dict) else None
        code = result.get('code') if isinstance(result, dict) and str(envelope.get('code')) == '0' else None
        if not isinstance(code, str) or not code.strip() or code.lower() in ('null', 'none'):
            raise RuntimeError('YYB 未返回有效的手机号授权 code')

        login_body = {
            'clienttype': '634', 'version': YDYP_WX_VERSION, 'cpid': '255',
            'msisdn': '', 'dycpwd': code, 'pintype': '27',
            'extInfo': {'ifOpenAccount': 0},
        }
        headers = {
            'Content-Type': 'application/json', 'hcy-cool-flag': '1',
            'x-request-model': 'nk',
            'x-huawei-channelSrc': '10214200', 'x-inner-ntwk': '2',
            'x-NetType': 'wifi', 'mcloud-channel': '1000101',
            'mcloud-client': '10801', 'mcloud-version': YDYP_WX_VERSION,
            'mcloud-network': 'WIFI', 'x-yun-client-info': '||8||||||||||||',
            'INNER-HCY-ROUTER-HTTPS': '1', 'x-yun-tid': generate_uuid(),
            'Referer': f'https://servicewechat.com/{YDYP_WX_APPID}/142/page-frame.html',
            'User-Agent': 'Mozilla/5.0 MicroMessenger/8.0.47 miniProgram/' + YDYP_WX_APPID,
            'x-DeviceInfo': build_x_device_info(generate_device_id(), version=YDYP_WX_VERSION),
        }
        # 不发送RSA旧链路的encryptMsg，也不重放已消费的微信code。
        response = session.post(
            YDYP_USER_BASE_URL + '/thirdlogin',
            data=encrypt_cloud_login_body(login_body), headers=headers, timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f'云盘登录 HTTP {response.status_code}')
        body = decrypt_cloud_login_response(response.text)
        status = str(body.get('code', ''))
        if status not in ('0000', '0') or body.get('success') is False:
            # 不输出业务message，它可能包含账号、票据或其他私人字段。
            safe_status = status if re.fullmatch(r'[A-Za-z0-9_-]{1,24}', status) else 'unknown'
            raise RuntimeError(f'云盘手机号授权登录失败 code={safe_status}')
        info = decode_cloud_login_data(body.get('data'))
        account = info.get('account')
        if not account and info.get('encryptAccount'):
            account = base64.b64decode(info['encryptAccount']).decode('utf-8')
        account = str(account or '').strip()
        raw_token = info.get('authToken')
        if not re.fullmatch(r'\d{11}', account) or not isinstance(raw_token, str) or not raw_token:
            raise RuntimeError('云盘登录结果缺少已绑定手机号或 authToken')
        return {
            'cookie': build_authorization(account, raw_token) + '#' + account,
            'account': account, 'source': 'yyb',
            'user_domain_id': info.get('userDomainId') or '',
            'expires_at': parse_expire_time_to_millis(info.get('atExpiretime') or info.get('expiretime')),
        }
    except requests.RequestException as exc:
        raise RuntimeError(f'登录网络请求失败（{type(exc).__name__}）') from exc
    finally:
        if owned_session:
            session.close()


def normalize_phone(value):
    """手机号归一化：去空格/连字符/括号，剥离 +86 / 86 国家码。

    去重必须在归一化后比较，否则「151 6396 0550」「+8615163960550」
    与「15163960550」会被判定成三个不同账号，导致重复执行。
    """
    digits = re.sub(r'[^\d]', '', str(value or ''))
    if len(digits) == 13 and digits.startswith('86'):
        digits = digits[2:]
    if len(digits) == 15 and digits.startswith('0086'):
        digits = digits[4:]
    return digits


def extract_account_from_cookie(cookie):
    """从 Authorization 值里还原手机号，用于跨来源去重。

    支持两种配置习惯：
    1) 纯 Authorization：Basic base64("mobile:{account}:{token}")
    2) 手工拼接：Authorization值#手机号（取 # 后为主，回退解析 Authorization）
    解析失败返回 ''。
    """
    raw = str(cookie or '').strip()
    # 优先用用户显式写在 # 后面的手机号
    if '#' in raw:
        tail = raw.rsplit('#', 1)[1].strip()
        if re.fullmatch(r'[\d\s\-+()]{7,20}', tail):
            phone = normalize_phone(tail)
            if len(phone) == 11:
                return phone
    token = normalize_authorization(raw)
    if token.startswith('Basic '):
        token = token[6:]
    # 补齐 base64 padding，容忍被截断/去填充的配置
    token = token.split('#', 1)[0].strip()
    try:
        token += '=' * (-len(token) % 4)
        decoded = base64.b64decode(token).decode('utf-8')
    except Exception:
        return ''
    parts = decoded.split(':')
    if len(parts) >= 2:
        phone = normalize_phone(parts[1])
        if len(phone) == 11 and phone.startswith('1'):
            return phone
    return ''


def parse_cookie_records(cookie_config):
    """把 ydyp 变量拆成 cookie 记录列表。"""
    records = []
    for value in re.split(r'[&\n]', cookie_config or ''):
        value = value.strip()
        if not value:
            continue
        records.append({
            'cookie': value,
            'source': 'cookie',
            'account': extract_account_from_cookie(value),
        })
    return records


def load_login_records():
    """加载待执行账号。

    默认 mixed 模式：先依次登录全部 YYB 账号，再追加 ydyp 环境变量里的账号。
    两种来源按手机号去重，YYB 优先（YYB 拿到的是刚换发的新凭证，更可靠）。
    显式设置 YDYP_LOGIN_MODE=yyb / cookie 时退回单一来源行为。
    """
    cookie_config = os.getenv('ydyp', '').strip()
    dedicated_server = os.getenv('YDYP_YYB_SERVER', '').strip()
    yyb_config = dedicated_server or os.getenv('YYB_SERVER', '').strip()
    mode = os.getenv('YDYP_LOGIN_MODE', 'auto').strip().lower() or 'auto'
    if mode not in ('auto', 'mixed', 'cookie', 'yyb'):
        raise ValueError('YDYP_LOGIN_MODE 只支持 auto、mixed、cookie、yyb')
    if mode == 'auto':
        mode = 'mixed'
    print(f'凭证获取模式: {mode}')

    # 单一来源：cookie
    if mode == 'cookie':
        records = parse_cookie_records(cookie_config)
        if not records:
            raise ValueError('未配置 ydyp；使用 YYB 时请配置 YYB_SERVER 并设置 YDYP_LOGIN_MODE=yyb')
        return records

    if not yyb_config:
        if mode == 'mixed' and parse_cookie_records(cookie_config):
            print('未配置 YYB_SERVER，仅执行 ydyp 环境变量账号')
            return parse_cookie_records(cookie_config)
        raise ValueError('YYB 模式缺少 YDYP_YYB_SERVER 或 YYB_SERVER')

    raw_refs = os.getenv('YDYP_YYB_REFS', '').strip()
    allowed_refs = {x.strip() for x in re.split(r'[&,，\n]', raw_refs) if x.strip()} if raw_refs else None
    accounts = parse_yyb_accounts(yyb_config, allowed_refs)
    if not accounts:
        if mode == 'mixed' and parse_cookie_records(cookie_config):
            print('YYB 配置中没有匹配本脚本的账号，仅执行 ydyp 环境变量账号')
            return parse_cookie_records(cookie_config)
        raise ValueError('YYB 配置中没有匹配本脚本的账号')

    records, seen_accounts = [], set()
    for index, (server, ref) in enumerate(accounts, 1):
        try:
            record = login_with_yyb(server, ref)
            if record['account'] in seen_accounts:
                print(f'YYB账号{index}: 云盘账号重复，跳过')
                continue
            seen_accounts.add(record['account'])
            records.append(record)
            print(f'YYB账号{index}: 云盘登录成功，已获得新凭证')
        except (RuntimeError, ValueError, TypeError) as exc:
            print(f'YYB账号{index}: {exc}')

    if mode == 'yyb':
        if not records:
            raise RuntimeError('全部 YYB 账号登录失败；未使用旧 Cookie 回退')
        return records

    # mixed：小程序（YYB）全部跑完后，再追加环境变量里的 token 账号
    cookie_records = parse_cookie_records(cookie_config)
    appended = 0
    skipped = 0
    for record in cookie_records:
        account = record.get('account')
        if account and account in seen_accounts:
            print(f"环境变量账号 {account[:3]}****{account[-4:]}: 已在YYB中执行，跳过")
            skipped += 1
            continue
        records.append(record)
        appended += 1
        if account:
            seen_accounts.add(account)
    if cookie_records:
        print(f'环境变量账号: 追加 {appended} 个，去重跳过 {skipped} 个（共配置 {len(cookie_records)} 个）')
    if not records:
        raise RuntimeError('YYB 与 ydyp 均未取得可用账号')
    return records


def parse_expire_time_to_millis(expire_time):
    try:
        expire_seconds = int(float(expire_time))
    except (TypeError, ValueError):
        expire_seconds = TOKEN_EXPIRE_SECONDS_FALLBACK
    if expire_seconds <= 0:
        expire_seconds = TOKEN_EXPIRE_SECONDS_FALLBACK
    return current_millis() + expire_seconds * 1000


def get_storage_base_dir():
    return Path(path.abspath(path.dirname(__file__)))


def get_storage_file_path(filename):
    return get_storage_base_dir() / filename


def get_token_storage_path():
    return get_storage_file_path(TOKEN_STORAGE_FILENAME)


def load_token_storage():
    storage_path = get_token_storage_path()
    if not storage_path.exists():
        return {'accounts': {}}
    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {'accounts': {}}
        if 'accounts' not in data:
            data['accounts'] = {}
        return data
    except Exception:
        return {'accounts': {}}


def save_token_storage(data):
    try:
        storage_path = get_token_storage_path()
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存Token存储失败: {e}")


# ============ 简易存储兼容层（不再写入 deviceId 缓存文件）============
def get_device_id_storage_path():
    return get_storage_file_path(DEVICE_ID_STORAGE_FILENAME)


def load_device_id_storage():
    storage_path = get_device_id_storage_path()
    if not storage_path.exists():
        return {}
    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_device_id(device_id, account):
    try:
        storage = load_token_storage()
        accounts = storage.setdefault('accounts', {})
        record = accounts.get(account, {})
        record['deviceId'] = device_id
        accounts[account] = record
        save_token_storage(storage)
    except Exception as e:
        print(f"保存DeviceId失败: {e}")


def save_token_info(account, token, expires_at, last_refresh_at):
    try:
        storage = load_token_storage()
        accounts = storage.setdefault('accounts', {})
        record = accounts.get(account, {})
        record['token'] = normalize_authorization(token)
        record['expiresAt'] = int(expires_at)
        record['lastRefreshAt'] = int(last_refresh_at)
        record['updatedAt'] = current_millis()
        accounts[account] = record
        save_token_storage(storage)
    except Exception as e:
        print(f"保存Token信息失败: {e}")


def ensure_account_storage_entry(account, token=''):
    try:
        storage = load_token_storage()
        accounts = storage.setdefault('accounts', {})
        if account not in accounts:
            accounts[account] = {'account': account}
            if token:
                accounts[account]['token'] = normalize_authorization(token)
            save_token_storage(storage)
    except Exception:
        pass


def get_token_info(account):
    try:
        storage = load_token_storage()
        return (storage.get('accounts') or {}).get(account, {})
    except Exception:
        return {}


def get_device_id(account):
    try:
        storage = load_token_storage()
        record = (storage.get('accounts') or {}).get(account, {})
        return record.get('deviceId', '')
    except Exception:
        return ''


def print_startup_info(account_count):
    print(f"移动云盘自动签到 v{SCRIPT_VERSION}")
    print(f"移动云盘共获取到{account_count}个账号")


def print_device_id_notice():
    print("变量格式: Authorization值#手机号")


def print_storage_path_notice():
    pass


# 发送通知
def load_send():
    cur_path = path.abspath(path.dirname(__file__))
    notify_dirs = [cur_path, '/ql/data/scripts', '/ql/scripts']

    for notify_dir in notify_dirs:
        notify_file = path.join(notify_dir, 'notify.py')
        if not path.isfile(notify_file):
            continue
        try:
            import sys

            if notify_dir not in sys.path:
                sys.path.insert(0, notify_dir)
            from notify import send

            print(f"加载青龙通知模块成功: {notify_file}")
            return send
        except Exception as e:
            print(f"加载青龙通知模块失败: {e}")

    print("加载青龙通知模块失败: 未找到 notify.py")
    return False


def send_notification(title, content):
    """通知是旁路能力，发送失败不影响主任务结果。"""
    send = load_send()
    if not send:
        return False
    try:
        send(title, content)
        print("青龙通知请求已提交")
        return True
    except Exception as e:
        print(f"青龙通知发送失败: {e}")
        return False


class YP:
    def __init__(self, cookie):
        self.account = ''
        self.Authorization = None
        try:
            self.notebook_id = None
            self.note_token = None
            self.note_auth = None
            self.auth_token = None
            self.click_num = 15
            self.draw = 1
            self.client_version = '12.5.4'
            self.market_base_url = YDYP_GATEWAY_HOST
            self.market_source_id = '1097'
            self.sso_token = None
            self.user_domain_id = ''
            self.market_device_id = ''
            self.market_x_device_info = ''
            self.market_device_from_env = False
            self.market_device_is_placeholder = False
            self.market_headers = {}
            self.market_cookies = {}
            self.session = requests.Session()
            self.user_log_lines = []

            self.timestamp = str(int(round(time.time() * 1000)))
            self.cookies = {'sensors_stay_time': self.timestamp}

            parts = cookie.split("#")
            if len(parts) < 2:
                raise ValueError(f"⚠️ 变量值格式错误，需要: Authorization值#手机号")

            self.Authorization = normalize_authorization(parts[0])
            self.configured_authorization = self.Authorization
            self.account = parts[1].strip()
            self.init_device_id = parts[2].strip() if len(parts) >= 3 else ''
            self.token_storage = load_token_storage()
            self.refresh_capable = AES is not None and pad is not None
            self.load_persisted_authorization()
            self.load_or_create_market_device_profile()
            self.auth_token = extract_raw_token(self.Authorization, self.account)

            if len(self.account) >= 11:
                self.encrypt_account = self.account[:3] + "****" + self.account[-4:]
            else:
                self.encrypt_account = self.account

            self.fruit_url = 'https://happy.mail.10086.cn/jsp/cn/garden/'

            # 云朵中心 cn 段接口已迁到 gp 网关：Host 必须与请求目标一致，
            # 否则 nginx 按虚拟主机路由会返回 404（backupgift / taskList 等）。
            self.jwtHeaders = {
                'User-Agent': ua,
                'Accept': '*/*',
                'Host': 'gp.mcloud.139.com',
            }
            self.treeHeaders = {
                'Host': 'happy.mail.10086.cn',
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': ua,
                'Referer': 'https://happy.mail.10086.cn/jsp/cn/garden/wap/index.html?sourceid=1003',
                'Cookie': '',
            }

        except Exception as e:
            print(f"{e}")
            self.Authorization = None

    def get_storage_record(self):
        """获取存储记录，优先从新版简易存储读取"""
        # 优先从新版简易存储读取
        new_storage = get_token_info(self.account)
        if new_storage.get('token') or new_storage.get('deviceId'):
            return new_storage
        # 后备：从旧版 token_storage 读取
        return (self.token_storage.get('accounts') or {}).get(self.account, {}) or {}

    def load_persisted_authorization(self):
        """仅在环境变量未提供 Authorization 时使用缓存。

        QingLong 环境变量是用户最新抓取的凭据，不能被历史缓存覆盖。
        """
        if normalize_authorization(getattr(self, 'configured_authorization', '')):
            return
        # 优先从新版简易存储读取
        new_storage = get_token_info(self.account)
        stored_token = normalize_authorization(new_storage.get('token', ''))
        if stored_token:
            self.Authorization = stored_token
            # 同时也写入旧版存储，保持兼容
            token_storage = load_token_storage()
            if self.account not in token_storage.get('accounts', {}):
                token_storage['accounts'][self.account] = {}
            token_storage['accounts'][self.account]['token'] = stored_token
            save_token_storage(token_storage)
            return
        # 后备：从旧版 token_storage 读取
        stored = self.get_storage_record()
        stored_token = normalize_authorization(stored.get('token', ''))
        if stored_token:
            self.Authorization = stored_token

    def load_or_create_market_device_profile(self):
        """加载 deviceId：强制从设备指纹接口获取，忽略环境变量和缓存"""
        ensure_account_storage_entry(self.account, self.Authorization)

        fetched_id = fetch_device_id()
        if fetched_id:
            self.market_device_id = fetched_id
            self.market_x_device_info = build_x_device_info(fetched_id)
            self.market_device_from_env = False
            self.market_device_is_placeholder = False
            save_device_id(fetched_id, self.account)
            return

        self.market_device_id = generate_device_id()
        self.market_x_device_info = build_x_device_info(self.market_device_id)
        self.market_device_is_placeholder = False
        if self.market_device_id:
            save_device_id(self.market_device_id, self.account)

    def save_authorization_record(self, token=None, user_domain_id=None, refreshed=False, expires_at=None, market_device_id=None, x_device_info=None, market_device_generated=None):
        token = normalize_authorization(token or self.Authorization)
        accounts = self.token_storage.setdefault('accounts', {})
        old_record = accounts.get(self.account, {}) or {}
        if not token:
            token = normalize_authorization(old_record.get('token', ''))
        last_refresh_at = old_record.get('lastRefreshAt', 0)
        if refreshed:
            last_refresh_at = current_millis()
        record_expires_at = expires_at or old_record.get('expiresAt') or (current_millis() + TOKEN_VALID_TIME)
        record = {
            **old_record,
            'account': self.account,
            'token': token,
            'authToken': extract_raw_token(token, self.account),
            'expiresAt': int(record_expires_at),
            'updatedAt': current_millis(),
            'lastRefreshAt': last_refresh_at,
        }
        if user_domain_id or old_record.get('userDomainId'):
            record['userDomainId'] = user_domain_id or old_record.get('userDomainId')
        final_market_device_id = market_device_id or old_record.get('marketDeviceId')
        final_x_device_info = x_device_info or old_record.get('xDeviceInfo')
        if final_market_device_id:
            record['marketDeviceId'] = final_market_device_id
        if final_x_device_info:
            record['xDeviceInfo'] = final_x_device_info
        if market_device_generated is None:
            if 'marketDeviceGenerated' in old_record:
                record['marketDeviceGenerated'] = old_record.get('marketDeviceGenerated')
        else:
            record['marketDeviceGenerated'] = bool(market_device_generated)
        accounts[self.account] = record
        save_token_storage(self.token_storage)

    def should_refresh_authorization(self, force=False):
        if force:
            return True, '强制刷新'
        stored = self.get_storage_record()
        now = current_millis()
        expires_at = int(stored.get('expiresAt') or 0)
        if not stored.get('token'):
            return True, '本地无缓存Token'
        if now >= expires_at:
            return True, '缓存Token已过期'
        if expires_at - now <= TOKEN_REFRESH_ADVANCE:
            hours = (expires_at - now) / 3600000
            return True, f'将在 {hours:.1f} 小时后过期'
        days = (expires_at - now) / 86400000
        return False, f'Token 状态良好（剩余 {days:.1f} 天）'

    def refresh_authorization_token(self, force=False):
        need_refresh, reason = self.should_refresh_authorization(force=force)
        if not need_refresh:
            self.log(f'-Authorization状态: {reason}')
            return True
        if not self.refresh_capable:
            self.log('-未安装 pycryptodome，跳过Authorization自动刷新')
            return True

        # 使用微信小程序UA刷新Token（源码：miniprogram|||1.0）
        refresh_headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.47(0x18002f2c) NetType/WIFI Language/zh_CN miniProgram/wx4e4ed37286c816c2',
            'x-yun-tid': generate_uuid(),
            'Authorization': self.Authorization,
            'x-yun-api-version': 'v1',
            'x-yun-module-type': '100',
            'x-yun-op-type': '1',
            'x-yun-app-channel': '10214200',
            'x-yun-client-info': '||8||||||||||||',
            'hcy-cool-flag': '1',
        }
        stored = self.get_storage_record()
        if stored.get('userDomainId'):
            refresh_headers['x-yun-uni'] = stored['userDomainId']

        encrypted_data = aes_encrypt({'phoneNumber': self.account}, REFRESH_TOKEN_AES_KEY)
        refresh_data = self.request_json('https://user-njs.yun.139.com/user/auth/refreshToken', headers=refresh_headers, data={'data': encrypted_data}, method='POST', retries=1)
        if not refresh_data:
            self.log(f'-Authorization刷新失败: 接口无响应 ({reason})')
            return True
        code = str(refresh_data.get('code', ''))
        data = refresh_data.get('data')
        success = refresh_data.get('success', False)
        is_success = (code in ('0', '00', '000', '0000')) or bool(success) or (code.startswith('0') and len(code) <= 4)
        if not is_success or not isinstance(data, dict):
            self.log(f"-Authorization刷新失败: {refresh_data.get('message') or refresh_data.get('msg', '未知错误')} (code={code or 'unknown'})")
            return True
        raw_token = data.get('token')
        if not raw_token:
            self.log('-Authorization刷新失败: 响应缺少token')
            return True
        expires_at = parse_expire_time_to_millis(data.get('expireTime'))
        self.Authorization = build_authorization(self.account, raw_token)
        self.auth_token = raw_token
        self.save_authorization_record(token=self.Authorization, refreshed=True, expires_at=expires_at)
        self.log(f'-Authorization自动刷新成功: {reason}')
        self.log(f"-Authorization有效期: {datetime.fromtimestamp(expires_at / 1000).strftime('%Y-%m-%d %H:%M:%S')}")
        return True

    def sync_token_storage(self):
        """同步存储 token 和 deviceId 到简易存储"""
        # 保存 token 刷新信息到简易存储
        stored = self.get_storage_record()
        expires_at = stored.get('expiresAt', current_millis() + TOKEN_VALID_TIME)
        last_refresh_at = stored.get('lastRefreshAt', 0)
        save_token_info(self.account, self.Authorization, expires_at, last_refresh_at)
        # 仅当账号已手动配置真实 deviceId 时才回写缓存；
        # 运行时兜底 deviceId 不落盘，避免覆盖成自动值。
        if self.market_device_id and not self.market_device_is_placeholder:
            save_device_id(self.market_device_id, self.account)
        # 同时保持旧版存储兼容
        self.save_authorization_record(token=self.Authorization, user_domain_id=self.user_domain_id)

    def log(self, content):
        print(content)
        self.user_log_lines.append(content)

    @staticmethod
    def catch_errors(func):
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                err_str = f"错误: {str(e)}"
                print(err_str)
                self.user_log_lines.append(err_str)
            return None

        return wrapper

    @catch_errors
    def run(self):
        self.refresh_authorization_token()
        if self.jwt():
            self.signin_status()
            self.click()
            self.get_tasklist(url='sign_in_3', app_type='cloud_app')
            self.log(f'\n🔥 热门任务')
            self.backup_cloud()
            self.log(f'\n📧 139邮箱任务')
            self.get_tasklist(url='newsign_139mail', app_type='email_app')
            self.receive()
            # 收尾兜底清理：任何中途失败遗留的临时文件都在这里统一删除
            try:
                self.cleanup_uploaded_files()
            except Exception:
                pass
            global all_logs
            user_log_str = "\n".join(self.user_log_lines)
            all_logs += f"用户【{self.encrypt_account}】日志:\n{user_log_str}\n\n"

        else:
            global err_accounts
            # 失效账号
            err_accounts += f'{self.encrypt_account}\n'

    @catch_errors
    def send_request(self, url, headers=None, cookies=None, data=None, params=None, method='GET', debug=None, retries=5, backoff=False):

        debug = debug if debug is not None else GLOBAL_DEBUG

        request_headers = dict(headers or {})
        request_cookies = dict(cookies or {})
        request_args = {'json': data} if isinstance(data, dict) else {'data': data}

        # 5xx 属上游瞬时故障，值得退避重试；4xx 是确定性错误，重试无意义。
        transparent_status = (500, 501, 502, 503, 504, 429)
        for attempt in range(retries):
            try:
                response = self.session.request(method, url, params=params, headers=request_headers or None, cookies=request_cookies or None, **request_args)
                if response.status_code in transparent_status:
                    if attempt >= retries - 1:
                        print(f"请求异常: {response.status_code} Server Error 已达最大重试次数")
                        return None
                    delay = min(2 ** attempt, 8) if backoff else 1
                    print(f"请求异常: {response.status_code} Server Error，{delay}s 后重试({attempt+1}/{retries})")
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                if debug:
                    print(f'\n【{url}】响应数据:\n{response.text}')
                return response
            except (requests.RequestException, ConnectionError, TimeoutError) as e:
                print(f"请求异常: {e}")
                if attempt >= retries - 1:
                    print("达到最大重试次数。")
                    return None
                time.sleep(min(2 ** attempt, 8) if backoff else 1)

    def request_json(self, url, headers=None, cookies=None, data=None, params=None, method='GET', debug=None, retries=5, backoff=False):
        response = self.send_request(url, headers=headers, cookies=cookies, data=data, params=params, method=method, debug=debug, retries=retries, backoff=backoff)
        if response is None:
            return None
        try:
            return response.json()
        except ValueError as e:
            self.log(f'响应解析失败: {e}')
            return None

    @staticmethod
    def get_today_sign_state(result):
        today_sign_in = result.get('todaySignIn')
        if isinstance(today_sign_in, bool):
            return today_sign_in
        for day in result.get('cal') or []:
            if day.get('t'):
                return bool(day.get('s'))
        return None

    @staticmethod
    def extract_user_domain_id(jwt_token):
        try:
            payload = jwt_token.split('.')[1]
            payload += '=' * (-len(payload) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload).decode())
            sub = data.get('sub', '')
            if isinstance(sub, str):
                sub = json.loads(sub)
            return sub.get('userDomainId', '')
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ''

    def build_market_context(self, jwt_token):
        self.user_domain_id = self.extract_user_domain_id(jwt_token)
        self.market_headers = {
            'User-Agent': market_ua,
            'Accept': '*/*',
            'jwtToken': jwt_token,
            'X-Requested-With': 'com.chinamobile.mcloud',
            'Referer': self.build_market_page_url(),
        }
        self.market_cookies = {'jwtToken': jwt_token}
        if self.user_domain_id:
            self.market_cookies['userDomainId'] = self.user_domain_id
        self.seed_market_device_cookie()
        self.sync_token_storage()

    def build_market_page_url(self, source_id=None):
        current_source_id = source_id or self.market_source_id
        return f'{self.market_base_url}/portal/mobilecloud/index.html?path=newsignin&sourceid={current_source_id}&enableShare=1&token={self.sso_token or ""}&targetSourceId=001005'

    def get_market_device_id(self):
        if self.market_device_id:
            return self.market_device_id
        for cookie in self.session.cookies:
            if cookie.name.startswith('.thumbcache_') and cookie.value:
                return unquote(cookie.value)
        return ''

    def seed_market_device_cookie(self):
        device_id = self.market_device_id
        if not device_id:
            return
        cookie_value = device_id[1:] if self.market_device_from_env and device_id.startswith('B') else device_id
        if any(cookie.name.startswith('.thumbcache_') and unquote(cookie.value) == cookie_value for cookie in self.session.cookies):
            return
        # 云朵中心已迁到 gp 网关，cookie 需同时播种到新旧两个域
        for domain in ('gp.mcloud.139.com', 'm.mcloud.139.com'):
            self.session.cookies.set(f'.thumbcache_{self.account}', cookie_value, domain=domain, path='/')

    def build_market_headers(self, extra_headers=None, referer=None):
        headers = dict(self.market_headers)
        headers['Referer'] = referer or headers.get('Referer') or self.build_market_page_url()
        device_id = self.get_market_device_id()
        if device_id:
            headers['deviceId'] = device_id
        if self.market_x_device_info:
            headers['x-DeviceInfo'] = self.market_x_device_info
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def build_receive_headers(self, source_id=None):
        return self.build_market_headers(
            {
                'showLoading': 'true',
                'appVersion': f'{self.client_version}.0',
                'activityId': 'sign_in_3',
            },
            referer=self.build_market_page_url(source_id),
        )

    def request_market_json(self, url, params=None, data=None, method='GET', debug=None, retries=5, headers=None, cookies=None):
        request_cookies = dict(self.market_cookies)
        if cookies:
            request_cookies.update(cookies)
        return self.request_json(url, headers=self.build_market_headers(headers), cookies=request_cookies, data=data, params=params, method=method, debug=debug, retries=retries)

    def post_signin_journaling(self, keyword, source_id=None):
        current_source_id = source_id or self.market_source_id
        payload = f'module=uservisit&optkeyword={keyword}&sourceid={current_source_id}&marketName=sign_in_3'
        response = self.send_request(
            f'{self.market_base_url}/ycloud/visitlog/journaling',
            headers=self.build_market_headers({'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'}, referer=self.build_market_page_url(current_source_id)),
            cookies=self.market_cookies,
            data=payload,
            method='POST',
            retries=1,
        )
        return response is not None

    def prepare_signin_center_session(self, for_receive=False, source_id=None):
        current_source_id = source_id or self.market_source_id
        page_url = self.build_market_page_url(current_source_id)
        self.send_request(page_url, headers=self.build_market_headers(referer=page_url), cookies=self.market_cookies, retries=1)
        for keyword in (
            'newsignin_index_pv',
            'newsignin_index_client',
            'newsignin_index_app_client',
            'newsignin_index_cookie_login',
            'newsignin_index_cookie',
            'newsignin_index_app_cookie_login',
        ):
            self.post_signin_journaling(keyword, current_source_id)
        if for_receive:
            self.post_signin_journaling('newsignin_index_receive_type', current_source_id)
        return True

    def click_task(self, task_id, key='task'):
        return self.request_market_json(f'{self.market_base_url}/ycloud/signin/task/click?key={key}&id={task_id}')

    def get_notice_status(self):
        send_data = self.request_json(f'{self.market_base_url}/ycloud/msgPushOn/task/status', headers=self.jwtHeaders) or {}
        if send_data.get('code') != 0:
            return {}
        return send_data.get('result', {}) or {}

    def format_notice_task_log(self, task_name, notice_status):
        if not notice_status:
            return f'-需手动完成: {task_name}'
        push_on = int(notice_status.get('pushOn') or 0)
        first_status = int(notice_status.get('firstTaskStatus') or 0)
        second_status = int(notice_status.get('secondTaskStatus') or 0)
        on_duration = int(notice_status.get('onDuaration') or 0)
        total = int(notice_status.get('total') or 31)
        if push_on != 1:
            return f'-需手动完成: {task_name} (通知未开启)'
        if second_status == 3:
            return f'-已完成: {task_name}'
        if first_status != 3:
            return f'-待领取: {task_name} (首日奖励可领取)'
        if second_status == 2:
            return f'-待领取: {task_name} (已开启{on_duration}/{total}天)'
        return f'-进行中: {task_name} (已开启{on_duration}/{total}天)'

    def build_cloud_file_headers(self):
        """云盘文件操作请求头：沿用 v5.0.3 已验证可用的上传头，避免 00010014"""
        return {
            'x-yun-op-type': '1',
            'x-yun-sub-op-type': '100',
            'x-yun-api-version': 'v1',
            'x-yun-client-info': '6|127.0.0.1|1|12.1.0|realme|RMX5060|BCFF2BBA6881DD8E4971803C63DDB5E4|02-00-00-00-00-00|android 15|1264X2592|zh||||032|0|',
            'x-yun-app-channel': '10000023',
            'Authorization': self.Authorization,
            'Content-Type': 'application/json; charset=UTF-8',
            'User-Agent': 'okhttp/4.12.0',
            'Host': 'personal-kd-njs.yun.139.com',
            'Connection': 'Keep-Alive',
        }

    def build_share_headers(self):
        """分享文件请求头：沿用 v5.0.3 已验证可用的分享头"""
        return {
            'Authorization': self.Authorization,
            'x-yun-api-version': 'v1',
            'x-yun-app-channel': '10000023',
            'x-yun-client-info': f'||9|{self.client_version}|Chrome|143.0.7499.146|codextestshare||Windows 10||zh-CN|||Q2hyb21l||',
            'x-yun-module-type': '100',
            'x-yun-svc-type': '1',
            'x-SvcType': '1',
            'x-yun-channel-source': '10000023',
            'x-huawei-channelSrc': '10000023',
            'Content-Type': 'application/json;charset=UTF-8',
            'CMS-DEVICE': 'default',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Referer': 'https://yun.139.com/shareweb/',
            'Origin': 'https://yun.139.com',
        }

    def create_cloud_file(self, prefix, extension='txt'):
        """真实上传一个小文件到云盘根目录。

        v5.3.1：改用随机内容 + 真实分片上传（create → getUploadUrl → PUT → complete）。
        原因：固定内容 b'0' 会命中云盘秒传（rapidUpload=True），文件虽然出现在列表里，
        但服务端不把它记成一次真实上传，导致「当月上传满100个」等任务进度始终为 0，
        而带 sendsms/interfacecallback 步骤的任务也无法被满足。
        """
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)
        content = (uuid.uuid4().hex * 4).encode('utf-8')  # 64 字节唯一内容
        file_size = len(content)
        content_hash = hashlib.sha256(content).hexdigest()
        file_name = f"{prefix}{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.{extension.lstrip('.')}"

        payload = {
            "contentHash": content_hash,
            "contentHashAlgorithm": "SHA256",
            "contentType": "application/oct-stream",
            "fileRenameMode": "force_rename",
            "localCreatedAt": now.isoformat(timespec='milliseconds'),
            "name": file_name,
            "parallelUpload": True,
            "parentFileId": "/",
            "partInfos": [{"end": file_size, "partNumber": 1, "partSize": file_size, "start": 0}],
            "size": file_size,
            "type": "file",
        }
        response = self.send_request('https://personal-kd-njs.yun.139.com/hcy/file/create',
                                     headers=self.build_cloud_file_headers(),
                                     data=payload, method='POST', retries=3)
        if not response or response.status_code != 200:
            return None
        try:
            res_json = response.json()
        except ValueError:
            return None
        if not res_json.get("success"):
            return None
        data = res_json.get("data", {})
        file_id = data.get("fileId")
        upload_id = data.get("uploadId")
        result = {
            "fileId": file_id,
            "fileName": data.get("fileName", file_name),
        }
        if data.get("rapidUpload") or not upload_id:
            return result

        # 取分片上传地址
        url_resp = self.request_json('https://personal-kd-njs.yun.139.com/hcy/file/getUploadUrl',
                                     headers=self.build_cloud_file_headers(),
                                     data={'fileId': file_id, 'uploadId': upload_id,
                                           'partInfos': [{"partNumber": 1, "partSize": file_size,
                                                          "start": 0, "end": file_size}]},
                                     method='POST', retries=2)
        parts = ((url_resp or {}).get('data') or {}).get('partInfos') or []
        upload_url = parts[0].get('uploadUrl') if parts else ''
        if not upload_url:
            return result

        # 上传真实字节
        try:
            put_resp = self.session.put(upload_url, data=content, timeout=60)
            if put_resp.status_code not in (200, 201):
                return result
            etag = (put_resp.headers.get('ETag') or '').strip('"')
        except Exception:
            return result

        # 完成上传，让文件真正落库
        self.request_json('https://personal-kd-njs.yun.139.com/hcy/file/complete',
                          headers=self.build_cloud_file_headers(),
                          data={'fileId': file_id, 'uploadId': upload_id,
                                'contentHash': content_hash,
                                'contentHashAlgorithm': 'SHA256',
                                'size': file_size, 'name': file_name,
                                'parentFileId': '/', 'type': 'file',
                                'partETagList': [{"partNumber": 1, "etag": etag,
                                                  "partSize": file_size,
                                                  "start": 0, "end": file_size}]},
                          method='POST', retries=2)
        return result

    def list_cloud_root_files(self):
        items = []
        page_cursor = ''
        while True:
            response = self.request_json(
                'https://personal-kd-njs.yun.139.com/hcy/file/list',
                headers=self.build_cloud_file_headers(),
                data={
                    'imageThumbnailStyleList': ['Small', 'Large'],
                    'orderBy': 'updated_at',
                    'orderDirection': 'DESC',
                    'pageInfo': {'pageCursor': page_cursor, 'pageSize': 100},
                    'parentFileId': '/',
                },
                method='POST',
            )
            if not response:
                return items
            if not response.get('success'):
                self.log(f"获取云盘文件列表失败: {response.get('message', '未知错误')}")
                return items
            data = response.get('data', {})
            items.extend(data.get('items', []))
            page_cursor = data.get('nextPageCursor') or ''
            if not page_cursor:
                return items

    @staticmethod
    def is_cleanup_upload_file(item):
        if item.get('type') != 'file' or item.get('parentFileId') != '/':
            return False
        name = item.get('name', '')
        # 本脚本产生的临时文件一律按前缀识别并清理。
        # v5.3.1 起真实上传的文件内容是随机字节（避免秒传导致任务不计数），
        # 所以不能再只靠 size<=1 / 固定 hash 判断，否则会残留。
        prefixes = ('auto_upload_', 'auto_share_', 'auto_mayday_',
                    'auto_up_', 'realupload_', 'probe_', 'cmpl_', 'cnt_test_')
        if name.endswith(('.txt', '.jpg')) and name.startswith(prefixes):
            return True
        return False

    def trash_cloud_files(self, file_ids):
        if not file_ids:
            return True
        response = self.request_json('https://personal-kd-njs.yun.139.com/hcy/recyclebin/batchTrash', headers=self.build_cloud_file_headers(), data={'fileIds': file_ids}, method='POST')
        if not response:
            self.log('清理上传文件失败: 接口无响应')
            return False
        if response.get('success'):
            return True
        self.log(f"清理上传文件失败: {response.get('message', '未知错误')}")
        return False

    def cleanup_uploaded_files(self, current_file=None):
        file_ids = []
        if current_file and current_file.get('fileId'):
            file_ids.append(current_file['fileId'])
        for item in self.list_cloud_root_files():
            if self.is_cleanup_upload_file(item):
                file_ids.append(item.get('fileId'))
        seen = set()
        unique_file_ids = []
        for file_id in file_ids:
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            unique_file_ids.append(file_id)
        if not unique_file_ids:
            return True
        if self.trash_cloud_files(unique_file_ids):
            self.log(f'-已清理上传文件: {len(unique_file_ids)}个')
            return True
        return False

    def complete_share_file_task(self, task):
        share_file = self.create_cloud_file('auto_share_')
        if not share_file:
            self.log('分享文件失败: 创建临时文件失败')
            return None
        try:
            response = self.request_json(
                'https://yun.139.com/orchestration/personalCloud-rebuild/outlink/v1.0/getOutLink',
                headers=self.build_share_headers(),
                data={
                    'getOutLinkReq': {
                        'subLinkType': 0,
                        'encrypt': 1,
                        'coIDLst': [share_file.get('fileId')],
                        'caIDLst': [],
                        'pubType': 1,
                        'dedicatedName': share_file.get('fileName', ''),
                        'period': 1,
                        'periodUnit': 1,
                        'viewerLst': [],
                        'extInfo': {'isWatermark': 0, 'shareChannel': '3001'},
                        'commonAccountInfo': {'account': self.account, 'accountType': 1},
                    }
                },
                method='POST',
                retries=1,
            )
        finally:
            self.trash_cloud_files([share_file.get('fileId')])
        data = response.get('data', {}) if response else {}
        result = data.get('result', {}) or data.get('getOutLinkRes', {})
        outlinks = result.get('getOutLinkResSet') or []
        success = False
        if response:
            success = (response.get('success') and result.get('resultCode') == '0') or (str(response.get('code')) == '0' and bool(outlinks))
        if not success:
            if response:
                msg = result.get('resultDesc') or response.get('message') or response.get('msg', '未知错误')
            else:
                msg = '接口无响应'
            self.log(f'分享文件失败: {msg}')
            return None
        return self.query_cloud_task(task.get('id', 434), 'month') or task

    def build_ai_headers(self, use_client_info=False):
        """AI相机请求头，与主UA保持一致"""
        device_id = self.market_device_id or generate_device_id()
        headers = {
            'Connection': 'keep-alive',
            'sec-ch-ua-platform': '"iOS"',
            'Authorization': self.Authorization,
            'x-yun-api-version': 'v1',
            'x-yun-tid': str(uuid.uuid4()),
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="130", "Mobile Safari";v="130"',
            'sec-ch-ua-mobile': '?1',
            'X-Requested-With': 'com.chinamobile.mcloud',
            'Origin': 'https://frontend.mcloud.139.com',
            'Referer': 'https://frontend.mcloud.139.com/',
            'User-Agent': market_ua,
            'Content-Type': 'application/json',
            'Sec-Fetch-Site': 'same-site',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'zh,zh-CN;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        if use_client_info:
            headers['Accept'] = 'text/event-stream'
            headers['x-yun-client-info'] = f'4||1|{self.client_version}|Apple|iPhone 16 Pro|{device_id.lstrip("B")}|iOS 18.7|||||'
            headers['x-yun-app-channel'] = '101'
            return headers
        headers['Accept'] = '*/*'
        headers['x-DeviceInfo'] = f'||36|{self.client_version}|Apple|iPhone 16 Pro|{device_id.lstrip("B")}|iOS 18.7|||||'
        return headers

    def encrypt_ai_tool_account(self):
        if AES is None or pad is None:
            raise ImportError('未安装 pycryptodome，无法加密AI工具账号')
        cipher = AES.new(AI_TOOL_ACCOUNT_AES_KEY.encode('utf-8'), AES.MODE_CBC, AI_TOOL_ACCOUNT_AES_IV.encode('utf-8'))
        encrypted = cipher.encrypt(pad(self.account.encode('utf-8'), AES.block_size))
        raw = AI_TOOL_ACCOUNT_AES_IV + base64.b64encode(encrypted).decode('utf-8')
        return base64.b64encode(raw.encode('utf-8')).decode('utf-8')

    def build_ai_tool_ad_headers(self):
        return {
            'Authorization': self.Authorization,
            'User-Agent': market_ua,
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://yun.139.com',
            'Referer': 'https://yun.139.com/aiTools/',
            'x-yun-tid': str(uuid.uuid4()),
        }

    def get_ai_camera_sample_base64(self):
        sample_path = path.join(path.abspath(path.dirname(__file__)), 'assets', 'ai_camera_sample.jpg')
        if path.exists(sample_path):
            with open(sample_path, 'rb') as file:
                return f"data:image/jpg;base64,{base64.b64encode(file.read()).decode()}"
        # assets/ 样图缺失时的内置兜底：现场合成 320x240 纯色 JPEG，
        # 满足 aiRecognize 对可解码图片的最低要求，避免任务因缺素材直接跳过。
        builtin = build_builtin_jpeg_sample()
        if builtin:
            return f"data:image/jpg;base64,{base64.b64encode(builtin).decode()}"
        return ''

    @staticmethod
    def is_ai_chat_success(text):
        payloads = []
        for line in (text or '').splitlines():
            if line.startswith('data:'):
                payloads.append(line[5:].strip())
        if not payloads and text:
            payloads.append(text.strip())
        for payload in payloads:
            if not payload or payload == '[DONE]':
                continue
            try:
                data = json.loads(payload)
            except ValueError:
                continue
            if data.get('success') or data.get('code') == '0000':
                return True
        return False

    def complete_ai_camera_task(self):
        if not self.user_domain_id:
            self.log('AI相机任务失败: 缺少用户信息')
            return False
        image_data = self.get_ai_camera_sample_base64()
        if not image_data:
            self.log('AI相机任务失败: 缺少样图')
            return False
        recognize_payload = json.dumps(
            {
                'channelId': '101',
                'userId': self.user_domain_id,
                'recognizeType': '1',
                'base64': image_data,
                'sendType': '2',
                'imageExt': 'jpg',
                'uploadToCloud': True,
                'timeout': 30000,
            },
            ensure_ascii=False,
            separators=(',', ':'),
        )
        recognize_data = self.request_json('https://ai.yun.139.com/api/image/aiRecognize', headers=self.build_ai_headers(), data=recognize_payload, method='POST')
        if not recognize_data:
            self.log('AI相机识图失败: 接口无响应')
            return False
        if not recognize_data.get('success'):
            self.log(f"AI相机识图失败: {recognize_data.get('message', '未知错误')}")
            return False
        recognize_result = recognize_data.get('data') or {}
        file_id = recognize_result.get('fileId')
        if not file_id:
            self.log('AI相机识图失败: 缺少文件ID')
            return False
        task_id = str(recognize_result.get('taskId') or int(time.time() * 1000))
        file_name = f'{int(task_id) + 1}.jpeg' if task_id.isdigit() else f'{task_id}.jpeg'
        input_time = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='milliseconds')
        chat_payload = json.dumps(
            {
                'userId': self.user_domain_id,
                'sessionId': '',
                'applicationType': 'chat',
                'applicationId': '',
                'sourceChannel': '101',
                'dialogueInput': {
                    'dialogue': '？',
                    'prompt': '',
                    'inputTime': input_time,
                    'enableForceLlm': False,
                    'enableForceNetworkSearch': True,
                    'enableModelThinking': False,
                    'enableAllNetworkSearch': False,
                    'enableKnowledgeAndNetworkSearch': False,
                    'enableRegenerate': False,
                    'versionInfo': {'h5Version': '2.7.6'},
                    'extInfo': '{}',
                    'sortInfo': {},
                    'toolSetting': {'imageToolSetting': {'enableLlmDescribe': True}},
                    'attachment': {
                        'attachmentTypeList': [3],
                        'fileList': [{'fileId': file_id, 'name': file_name}],
                    },
                },
            },
            ensure_ascii=False,
            separators=(',', ':'),
        )
        chat_response = self.send_request('https://ai.yun.139.com/api/outer/assistant/chat/v2/add', headers=self.build_ai_headers(use_client_info=True), data=chat_payload, method='POST')
        if not chat_response:
            self.log('AI相机对话失败: 接口无响应')
            return False
        if self.is_ai_chat_success(chat_response.text):
            return True
        try:
            chat_data = chat_response.json()
        except ValueError:
            chat_data = None
        if chat_data and (chat_data.get('success') or chat_data.get('code') == '0000'):
            return True
        if chat_data:
            self.log(f"AI相机对话失败: {chat_data.get('message') or chat_data.get('msg', '未知错误')}")
            return False
        self.log('AI相机对话失败: 响应解析失败')
        return False

    def complete_travel_guide_ai_task(self):
        if not self.user_domain_id:
            self.log('出行攻略问AI失败: 缺少用户信息')
            return False
        input_time = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='milliseconds')
        chat_payload = json.dumps(
            {
                'userId': self.user_domain_id,
                'sessionId': '',
                'applicationType': 'chat',
                'applicationId': '',
                'sourceChannel': '101',
                'dialogueInput': {
                    'dialogue': '给我一份五一出行攻略',
                    'prompt': '',
                    'inputTime': input_time,
                    'enableForceLlm': False,
                    'enableForceNetworkSearch': True,
                    'enableModelThinking': False,
                    'enableAllNetworkSearch': False,
                    'enableKnowledgeAndNetworkSearch': False,
                    'enableRegenerate': False,
                    'versionInfo': {'h5Version': '2.7.6'},
                    'extInfo': '{}',
                    'sortInfo': {},
                    'toolSetting': {'imageToolSetting': {'enableLlmDescribe': True}},
                    'attachment': {},
                },
            },
            ensure_ascii=False,
            separators=(',', ':'),
        )
        chat_response = self.send_request('https://ai.yun.139.com/api/outer/assistant/chat/v2/add', headers=self.build_ai_headers(use_client_info=True), data=chat_payload, method='POST')
        if not chat_response:
            self.log('出行攻略问AI失败: 接口无响应')
            return False
        response_text = chat_response.text or ''
        if chat_response.status_code == 200 and not response_text.strip():
            return True
        if self.is_ai_chat_success(response_text):
            return True
        try:
            chat_data = chat_response.json()
        except ValueError:
            chat_data = None
        if chat_data and (chat_data.get('success') or chat_data.get('code') == '0000'):
            return True
        if chat_data:
            self.log(f"出行攻略问AI失败: {chat_data.get('message') or chat_data.get('msg', '未知错误')}")
            return False
        self.log('出行攻略问AI失败: 响应解析失败')
        return False

    @staticmethod
    def get_task_progress(task):
        progress_parts = []
        currstep = task.get('currstep', 0)
        process = task.get('process', 0)
        if currstep:
            progress_parts.append(f'阶段{currstep}')
        if process:
            progress_parts.append(f'进度{process}')
        if not progress_parts:
            return ''
        return f" ({'，'.join(progress_parts)})"

    @staticmethod
    def strip_task_name(task):
        return re.sub(r'<[^>]+>', '', task.get('name', ''))

    @staticmethod
    def get_task_step_types(task):
        return set(task.get('stepTypeSet') or [])

    def get_task_click_keys(self, task):
        task_id = task.get('id')
        currstep = task.get('currstep', 0)
        step_types = self.get_task_step_types(task)
        if task_id == 409:
            if currstep > 0:
                return ['task2']
            return ['task', 'task2']
        if 'click' in step_types and currstep == 0:
            return ['task']
        return []

    def get_cloud_task_groups(self):
        return [
            ('beiyong1', '\n🎁 五一福利任务'),
            ('cloudEmail', '\n📮 联动任务'),
            ('time', '\n✨ 新版热门任务'),
            ('day', '\n📆 云盘每日任务'),
            ('month', '\n📆 云盘每月任务'),
        ]

    def query_cloud_task(self, task_id, group='time'):
        return_data = self.request_market_json(
            f'{self.market_base_url}/ycloud/signin/task/taskListV2',
            method="POST",
            data={
                'marketname': 'sign_in_3',
                'clientVersion': self.client_version,
                'group': group,
            },
        )
        if not return_data or return_data.get('code') != 0:
            return None
        for task in return_data.get('result', {}).get(group, []):
            if task.get('id') == task_id:
                return task
        return None

    def complete_monthly_upload_task(self, task):
        target_count = 100
        current_process = int(task.get('process') or 0)
        for attempt in range(3):
            remaining = max(0, target_count - current_process)
            if remaining == 0:
                return True
            self.log(f'-{"开始" if attempt == 0 else "继续"}补上传进度: 当前{current_process}/{target_count}，还需{remaining}次')
            success = 0
            for _ in range(remaining):
                if self.create_cloud_file('auto_upload_'):
                    success += 1
            if success:
                self.log(f'-批量上传完成: {success}次')
            refreshed_task = self.query_cloud_task(task.get('id', 522), 'time')
            if not refreshed_task:
                return False
            refreshed_process = int(refreshed_task.get('process') or 0)
            if refreshed_task.get('state') == 'FINISH' or refreshed_process >= target_count:
                return True
            if refreshed_process <= current_process:
                self.log(f'-月上传任务进度: {refreshed_process}/{target_count}')
                return False
            current_process = refreshed_process
        self.log(f'-月上传任务进度: {current_process}/{target_count}')
        return False

    def complete_mayday_memory_task(self, task):
        target_count = 10
        task_id = task.get('id', 587)
        current_process = int(task.get('process') or 0)
        remaining = max(0, target_count - current_process)
        if remaining == 0:
            return True
        self.log(f'-开始补五一回忆上传: 当前{current_process}/{target_count}，还需{remaining}张')
        success = 0
        for _ in range(remaining):
            if self.create_cloud_file('auto_mayday_', extension='jpg'):
                success += 1
        if success:
            self.log(f'-五一回忆上传完成: {success}张')
            self.click_task(task_id)
        refreshed_task = self.query_cloud_task(task_id, 'beiyong1')
        if not refreshed_task:
            return False
        refreshed_process = int(refreshed_task.get('process') or 0)
        if refreshed_task.get('state') == 'FINISH' or refreshed_process >= target_count:
            return True
        self.log(f'-五一回忆任务进度: {refreshed_process}/{target_count}')
        return False

    def complete_holiday_nine_grid_task(self):
        try:
            encrypted_account = self.encrypt_ai_tool_account()
        except ImportError:
            self.log('生成假期九宫格失败: 缺少加密依赖')
            return False
        template_data = self.request_json(
            'https://ad.mcloud.139.com/advertapi/adv-config/adv-config/AdInfoFilter/getAdInfos',
            headers=self.build_ai_tool_ad_headers(),
            data={
                'account': encrypted_account,
                'adpostid': '66340',
                'channel': '10000023',
                'version': '10.5.0',
                'client': 'iphone',
            },
            method='POST',
        )
        if not template_data:
            self.log('生成假期九宫格失败: 模板接口无响应')
            return False
        if str(template_data.get('returnCode')) != '0':
            self.log(f"生成假期九宫格失败: {template_data.get('returnMsg', '未知错误')}")
            return False
        click_data = self.click_task(589)
        if click_data and str(click_data.get('code')) == '0':
            return True
        msg = click_data.get('msg', '未知错误') if click_data else '接口无响应'
        self.log(f'生成假期九宫格失败: {msg}')
        return False

    def get_cloud_tasklist_v2(self):
        for group, title in self.get_cloud_task_groups():
            return_data = self.request_market_json(
                f'{self.market_base_url}/ycloud/signin/task/taskListV2',
                method="POST",
                data={
                    'marketname': 'sign_in_3',
                    'clientVersion': self.client_version,
                    'group': group,
                },
            )
            if not return_data:
                self.log(f'获取任务列表失败: {group}')
                continue
            if return_data.get('code') != 0:
                self.log(f"获取任务列表失败: {group} {return_data.get('msg', '未知错误')}")
                continue
            tasks = return_data.get('result', {}).get(group, [])
            if not tasks:
                continue
            self.log(title)
            for task in tasks:
                self.handle_cloud_v2_task(group, task)
        self.cleanup_uploaded_files()

    def handle_cloud_v2_task(self, group, task):
        task_id = task.get('id')
        task_name = self.strip_task_name(task)
        task_status = task.get('state', '')
        if task_status == 'FINISH':
            print(f'-已完成: {task_name}')
            return
        if group == 'day' and task_id == 106:
            self.log(f'-去完成: {task_name}')
            self.do_task(task_id, task_type='day', app_type='cloud_app')
            return
        if task_id == 522:
            self.log(f'-去完成: {task_name}')
            if self.complete_monthly_upload_task(task):
                self.log(f'-已完成: {task_name}')
                return
            refreshed_task = self.query_cloud_task(task_id, group) or task
            # self.log(f'-需手动完成: {task_name}{self.get_task_progress(refreshed_task)}')
            return
        if task_id == 434:
            self.log(f'-去完成: {task_name}')
            refreshed_task = self.complete_share_file_task(task)
            if refreshed_task:
                refreshed_name = self.strip_task_name(refreshed_task)
                if refreshed_task.get('state') == 'FINISH':
                    self.log(f'-已完成: {refreshed_name}')
                    return
                self.log(f'-分享成功: {refreshed_name}{self.get_task_progress(refreshed_task)}')
                return
            # self.log(f'-需手动完成: {task_name}{self.get_task_progress(task)}')
            return
        if task_id == 585:
            self.log(f'-去完成: {task_name}')
            if 'click' in self.get_task_step_types(task) and int(task.get('currstep') or 0) == 0:
                click_data = self.click_task(task_id)
                if not click_data or click_data.get('code') != 0:
                    msg = click_data.get('msg', '未知错误') if click_data else '接口无响应'
                    self.log(f'-任务登记失败: {task_name} {msg}')
                    return
            if self.complete_ai_camera_task():
                refreshed_task = self.query_cloud_task(task_id, group) or task
                refreshed_name = self.strip_task_name(refreshed_task)
                if refreshed_task.get('state') == 'FINISH':
                    self.log(f'-已完成: {refreshed_name}')
                else:
                    self.log(f'-AI相机已体验: {refreshed_name}{self.get_task_progress(refreshed_task)}')
                return
            refreshed_task = self.query_cloud_task(task_id, group) or task
            # self.log(f'-需手动完成: {task_name}{self.get_task_progress(refreshed_task)}')
            return
        if task_id == 587:
            self.log(f'-去完成: {task_name}')
            if 'click' in self.get_task_step_types(task) and int(task.get('currstep') or 0) == 0:
                click_data = self.click_task(task_id)
                if not click_data or click_data.get('code') != 0:
                    msg = click_data.get('msg', '未知错误') if click_data else '接口无响应'
                    self.log(f'-任务登记失败: {task_name} {msg}')
                    return
            if self.complete_mayday_memory_task(task):
                refreshed_task = self.query_cloud_task(task_id, group) or task
                refreshed_name = self.strip_task_name(refreshed_task)
                if refreshed_task.get('state') == 'FINISH':
                    self.log(f'-已完成: {refreshed_name}')
                else:
                    self.log(f'-五一回忆已上传: {refreshed_name}{self.get_task_progress(refreshed_task)}')
                return
            refreshed_task = self.query_cloud_task(task_id, group) or task
            # self.log(f'-需手动完成: {task_name}{self.get_task_progress(refreshed_task)}')
            return
        if task_id == 588:
            self.log(f'-去完成: {task_name}')
            if 'click' in self.get_task_step_types(task) and int(task.get('currstep') or 0) == 0:
                click_data = self.click_task(task_id)
                if not click_data or click_data.get('code') != 0:
                    msg = click_data.get('msg', '未知错误') if click_data else '接口无响应'
                    self.log(f'-任务登记失败: {task_name} {msg}')
                    return
            if self.complete_travel_guide_ai_task():
                refreshed_task = self.query_cloud_task(task_id, group) or task
                refreshed_name = self.strip_task_name(refreshed_task)
                if refreshed_task.get('state') == 'FINISH':
                    self.log(f'-已完成: {refreshed_name}')
                else:
                    self.log(f'-出行攻略已生成: {refreshed_name}{self.get_task_progress(refreshed_task)}')
                return
            refreshed_task = self.query_cloud_task(task_id, group) or task
            # self.log(f'-需手动完成: {task_name}{self.get_task_progress(refreshed_task)}')
            return
        if task_id == 589:
            self.log(f'-去完成: {task_name}')
            if 'click' in self.get_task_step_types(task) and int(task.get('currstep') or 0) == 0:
                click_data = self.click_task(task_id)
                if not click_data or click_data.get('code') != 0:
                    msg = click_data.get('msg', '未知错误') if click_data else '接口无响应'
                    self.log(f'-任务登记失败: {task_name} {msg}')
                    return
            if self.complete_holiday_nine_grid_task():
                refreshed_task = self.query_cloud_task(task_id, group) or task
                refreshed_name = self.strip_task_name(refreshed_task)
                if refreshed_task.get('state') == 'FINISH':
                    self.log(f'-已完成: {refreshed_name}')
                else:
                    self.log(f'-假期九宫格已生成: {refreshed_name}{self.get_task_progress(refreshed_task)}')
                return
            refreshed_task = self.query_cloud_task(task_id, group) or task
            # self.log(f'-需手动完成: {task_name}{self.get_task_progress(refreshed_task)}')
            return
        if group == 'beiyong1':
            # self.log(f'-需手动完成: {task_name}{self.get_task_progress(task)}')
            return
        if task_id == 406:
            self.complete_notice_task(task_name)
            return
        task_keys = self.get_task_click_keys(task)
        if task_keys:
            self.log(f'-去完成: {task_name}')
            for task_key in task_keys:
                click_data = self.click_task(task_id, task_key)
                if click_data and click_data.get('code') == 0:
                    continue
                msg = click_data.get('msg', '未知错误') if click_data else '接口无响应'
                self.log(f'-任务登记失败: {task_name} {msg}')
                return
            self.log(f'-已登记任务: {task_name}')
            return
        # self.log(f'-需手动完成: {task_name}{self.get_task_progress(task)}')

    def sleep(self, min_delay=1, max_delay=1.5):
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)

    def sso(self):
        # 2026-09 HAR 中网页端使用 querySpecTokenV2；保留旧编排接口回退。
        # v5.3.2：上游抖动会出现 5xx，这里用退避重试而非一次就放弃。
        common_headers = {
            'Authorization': self.Authorization,
            'User-Agent': ua,
            'Content-Type': 'application/json',
            'Accept': '*/*',
        }
        sso_data = self.request_json(
            'https://user-njs.yun.139.com/user/querySpecTokenV2',
            headers={**common_headers, 'Host': 'user-njs.yun.139.com'},
            data={"toSourceId": "001005"},
            method='POST',
            retries=4,
            backoff=True,
        )
        if not sso_data or not sso_data.get('success') or not isinstance(sso_data.get('data'), dict) or not sso_data['data'].get('token'):
            sso_data = self.request_json(
                'https://orches.yun.139.com/orchestration/auth-rebuild/token/v1.0/querySpecToken',
                headers={**common_headers, 'Host': 'orches.yun.139.com'},
                data={"account": self.account, "toSourceId": "001005"},
                method='POST',
                retries=4,
                backoff=True,
            )
        if not sso_data:
            self.log('刷新Token失败: 接口无响应')
            return None
        if sso_data.get('success') and isinstance(sso_data.get('data'), dict) and sso_data['data'].get('token'):
            refresh_token = sso_data['data']['token']
            self.sso_token = refresh_token
            return refresh_token
        else:
            self.log(f"刷新Token失败: {sso_data.get('message', '未知错误')}")
            return None

    def _exchange_jwt_via_gateway(self, sso_token):
        """用 ssoToken 在 gp 网关换取 jwtToken（13.2.5 现役链路）。

        返回 (jwt_token, error_msg)。成功时 jwt_token 非空。

        v5.3.2：该接口在上游抖动时会返回 501 Connection refused / 502 / 503，
        属瞬时故障。改用 6 次指数退避重试（总窗口约 30s），显著降低误判为
        「ck 失效」的概率；signature 每次重试都重新生成，避免时间戳过期。
        """
        payload = {
            'token': sso_token,
            'openAccount': 0,
            'marketName': YDYP_MARKET_NAME,
        }
        extra = {
            'User-Agent': ua or DEFAULT_MOBILE_UA,
            'Origin': YDYP_GATEWAY_HOST,
            'Referer': self.build_market_page_url(),
        }
        last_err = ''
        for attempt in range(6):
            # 每次重试重新签名：x-timestamp/x-nonce/x-signature 都需新鲜值
            headers = build_gateway_sign_headers(self.session, extra)
            data = self.request_json(
                YDYP_GATEWAY_HOST + YDYP_AUTH_PATH,
                headers=headers,
                data=payload,
                method='POST',
                retries=1,
            )
            if data:
                code = data.get('code')
                if code == 0:
                    result = data.get('result') or {}
                    token = result.get('token') if isinstance(result, dict) else None
                    if token:
                        return token, ''
                    last_err = '响应缺少 token'
                else:
                    msg = data.get('msg') or data.get('message') or f'code={code}'
                    last_err = msg
                    # 业务态失败（token 失效等）重试无益，直接返回
                    if code not in (501, 502, 503, 504, -1):
                        return None, msg
            else:
                last_err = '接口无响应'
            if attempt < 5:
                delay = min(2 ** attempt, 8)
                print(f'-网关换取JWT第{attempt+1}次失败({last_err})，{delay}s 后重试')
                time.sleep(delay)
        return None, last_err

    def _exchange_jwt_legacy(self, sso_token):
        """旧版 tyrzLogin.action 链路（2026-10 起返回 404，仅作降级兜底）。"""
        jwt_url = f"https://caiyun.feixin.10086.cn:7071/portal/auth/tyrzLogin.action?ssoToken={sso_token}"
        jwt_data = self.request_json(jwt_url, headers=self.jwtHeaders, method='POST', retries=2)
        if not jwt_data:
            return None, '接口无响应'
        if jwt_data.get('code') != 0:
            return None, jwt_data.get('msg', '未知错误')
        result = jwt_data.get('result') or {}
        token = result.get('token') if isinstance(result, dict) else None
        if not token:
            return None, '响应缺少 token'
        return token, ''

    def jwt(self):
        token = self.sso()
        if token is None:
            self.log('-尝试强制刷新Authorization后重试')
            self.refresh_authorization_token(force=True)
            token = self.sso()
        if token is None:
            # ssoToken 拿不到：可能是凭证失效，也可能是上游抖动。
            # 这里只描述事实，不武断下「ck 失效」结论。
            self.log('-ssoToken 获取失败（凭证失效或上游不可用）')
            return False

        jwt_token, err = self._exchange_jwt_via_gateway(token)
        if not jwt_token:
            self.log(f'-网关换取JWT失败({err})，尝试刷新Authorization')
            self.refresh_authorization_token(force=True)
            refreshed_sso = self.sso()
            if refreshed_sso:
                token = refreshed_sso
                jwt_token, err = self._exchange_jwt_via_gateway(token)
            if not jwt_token:
                # 最后兜底：旧版接口（多数情况下已下线，保留以兼容灰度回滚）
                jwt_token, legacy_err = self._exchange_jwt_legacy(token)
                if not jwt_token:
                    if is_transient_error(err) or is_transient_error(legacy_err):
                        self.log(f"JWT获取失败: 上游服务暂不可用（网关={err} 旧接口={legacy_err}），本轮跳过")
                    else:
                        self.log(f"JWT获取失败: 网关={err} 旧接口={legacy_err}")
                    return False

        self.jwtHeaders['jwtToken'] = jwt_token
        self.cookies['jwtToken'] = jwt_token
        self.build_market_context(jwt_token)
        self.save_authorization_record(token=self.Authorization, user_domain_id=self.user_domain_id)
        return True

    @catch_errors
    def signin_status(self):
        self.sleep()
        self.prepare_signin_center_session()
        check_url = f'{self.market_base_url}/ycloud/signin/page/infoV3'
        check_data = self.request_market_json(check_url, params={'client': 'app'})
        if not check_data:
            self.log('查询签到失败: 接口无响应')
            return
        if check_data.get('code') != 0:
            self.log(f"查询签到失败: {check_data.get('msg', '未知错误')}")
            return
        if self.get_today_sign_state(check_data.get('result', {})):
            self.log('✅已签到')
            return
        signin_data = self.request_market_json(f'{self.market_base_url}/ycloud/signin/page/startSignIn', params={'client': 'app'})
        if not signin_data:
            self.log('签到失败: 接口无响应')
            return
        if signin_data.get('code') == 0 and self.get_today_sign_state(signin_data.get('result', {})):
            self.log('✅签到成功')
            return
        latest_data = self.request_market_json(check_url, params={'client': 'app'})
        if latest_data and latest_data.get('code') == 0 and self.get_today_sign_state(latest_data.get('result', {})):
            self.log('✅签到成功')
            return
        self.log(f"签到失败: {signin_data.get('msg', '未知错误')}")
        if signin_data.get('code') in (614, 615) and not get_env_device_id() and not get_device_id(self.account):
            self.log('-请检查变量中 deviceId 是否正确')

    def click(self):
        successful_click = 0

        try:
            for _ in range(self.click_num):
                return_data = self.click_task(319) or {}
                time.sleep(0.2)

                # 13.2.5 起 /ycloud/signin/task/click 成功仅返回 {"code":0,"msg":"success"}，
                # 不再带回 result 文案；以 code==0 判定成功，兼容旧版带 result 的响应。
                if return_data.get('code') == 0:
                    tip = return_data.get('result') or 'success'
                    self.log(f'✅戳一戳: {tip}')
                    successful_click += 1
                elif return_data.get('code') is not None:
                    self.log(f'❌戳一戳: {return_data.get("msg", "未知错误")}')

            if successful_click == 0:
                print(f'❌戳一戳: 未获得 x {self.click_num}')
        except Exception as e:
            print(f'错误信息:{e}')

    @catch_errors
    def refresh_notetoken(self):
        note_url = 'http://mnote.caiyun.feixin.10086.cn/noteServer/api/authTokenRefresh.do'
        note_payload = {"authToken": self.auth_token, "userPhone": self.account}
        note_headers = {
            'X-Tingyun-Id': 'p35OnrDoP8k;c=2;r=1122634489;u=43ee994e8c3a6057970124db00b2442c::8B3D3F05462B6E4C',
            'Charset': 'UTF-8',
            'Connection': 'Keep-Alive',
            'User-Agent': 'mobile',
            'APP_CP': 'ios',
            'CP_VERSION': '3.2.0',
            'x-huawei-channelsrc': '10001400',
            'Host': 'mnote.caiyun.feixin.10086.cn',
            'Content-Type': 'application/json; charset=UTF-8',
            'Accept-Encoding': 'gzip',
        }

        try:
            response = self.send_request(note_url, headers=note_headers, data=note_payload, method="POST")
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print('出错了:', e)
            return

        self.note_token = response.headers.get('NOTE_TOKEN')
        self.note_auth = response.headers.get('APP_AUTH')

    def get_tasklist(self, url, app_type):
        if url == 'sign_in_3' and app_type == 'cloud_app':
            self.get_cloud_tasklist_v2()
            return
        url = f'{self.market_base_url}/ycloud/signin/task/taskList?marketname={url}'
        return_data = self.send_request(url, headers=self.jwtHeaders, cookies=self.cookies).json()
        self.sleep()
        task_list = return_data.get('result', {})

        try:
            for task_type, tasks in task_list.items():
                if task_type in ["new", "hidden", "hiddenabc"]:
                    continue
                if app_type == 'cloud_app':
                    if task_type == "month":
                        self.log('\n📆 云盘每月任务')
                        for month in tasks:
                            task_id = month.get('id')
                            if task_id in [110, 113, 417, 409]:
                                continue
                            task_name = re.sub(r'<[^>]+>', '', month.get('name', ''))
                            task_status = month.get('state', '')

                            if task_status == 'FINISH':
                                print(f'-已完成: {task_name}')
                                continue
                            self.log(f'-去完成: {task_name}')
                            self.do_task(task_id, task_type='month', app_type='cloud_app')
                            time.sleep(2)
                    elif task_type == "day":
                        self.log('\n📆 云盘每日任务')
                        for day in tasks:
                            task_id = day.get('id')
                            if task_id == 404:
                                continue
                            task_name = re.sub(r'<[^>]+>', '', day.get('name', ''))
                            task_status = day.get('state', '')

                            if task_status == 'FINISH':
                                print(f'-已完成: {task_name}')
                                continue
                            self.log(f'-去完成: {task_name}')
                            self.do_task(task_id, task_type='day', app_type='cloud_app')
                elif app_type == 'email_app':
                    if task_type == "month":
                        self.log('\n📆 139邮箱每月任务')
                        for month in tasks:
                            task_id = month.get('id')
                            task_name = re.sub(r'<[^>]+>', '', month.get('name', ''))
                            task_status = month.get('state', '')
                            if task_id in [1004, 1005, 1015, 1020]:
                                continue

                            if task_status == 'FINISH':
                                print(f'-已完成: {task_name}')
                                continue
                            self.log(f'-去完成: {task_name}')
                            self.do_task(task_id, task_type='month', app_type='email_app')
                            time.sleep(2)
        except Exception as e:
            self.log(f'获取任务列表错误:{e}')

    @catch_errors
    def do_task(self, task_id, task_type, app_type):
        self.sleep()
        if app_type == 'cloud_app':
            self.click_task(task_id)
        else:
            task_url = f'{self.market_base_url}/ycloud/signin/task/click?key=task&id={task_id}'
            self.send_request(task_url, headers=self.jwtHeaders, cookies=self.cookies)

        if app_type == 'cloud_app':
            if task_type == 'day':
                if task_id == 106:
                    self.log('-开始上传文件，默认0kb')
                    self.updata_file()
                elif task_id == 107:
                    self.refresh_notetoken()
                    print('-获取默认笔记id')
                    note_url = 'http://mnote.caiyun.feixin.10086.cn/noteServer/api/syncNotebookV3.do'
                    headers = {
                        'X-Tingyun-Id': 'p35OnrDoP8k;c=2;r=1122634489;u=43ee994e8c3a6057970124db00b2442c::8B3D3F05462B6E4C',
                        'Charset': 'UTF-8',
                        'Connection': 'Keep-Alive',
                        'User-Agent': 'mobile',
                        'APP_CP': 'ios',
                        'CP_VERSION': '3.2.0',
                        'x-huawei-channelsrc': '10001400',
                        'APP_NUMBER': self.account,
                        'APP_AUTH': self.note_auth,
                        'NOTE_TOKEN': self.note_token,
                        'Host': 'mnote.caiyun.feixin.10086.cn',
                        'Content-Type': 'application/json; charset=UTF-8',
                        'Accept': '*/*',
                    }
                    payload = {"addNotebooks": [], "delNotebooks": [], "notebookRefs": [], "updateNotebooks": []}
                    return_data = self.send_request(url=note_url, headers=headers, data=payload, method='POST').json()
                    if return_data is None:
                        return print('出错了')
                    self.notebook_id = return_data['notebooks'][0]['notebookId']
                    print('开始创建笔记')
                    self.create_note(headers)

    @catch_errors
    def updata_file(self):
        upload_info = self.create_cloud_file('auto_upload_')
        if not upload_info:
            self.log('-上传失败: 接口无响应')
            return
        self.log(f"-上传文件成功，文件名: {upload_info.get('fileName', '')}")
        self.cleanup_uploaded_files(upload_info)

    def create_note(self, headers):
        note_id = self.get_note_id(32)
        createtime = str(int(round(time.time() * 1000)))
        time.sleep(3)
        updatetime = str(int(round(time.time() * 1000)))
        note_url = 'http://mnote.caiyun.feixin.10086.cn/noteServer/api/createNote.do'
        payload = {
            "archived": 0,
            "attachmentdir": note_id,
            "attachmentdirid": "",
            "attachments": [],
            "audioInfo": {"audioDuration": 0, "audioSize": 0, "audioStatus": 0},
            "contentid": "",
            "contents": [{"contentid": 0, "data": "<font size=\"3\">000000</font>", "noteId": note_id, "sortOrder": 0, "type": "RICHTEXT"}],
            "cp": "",
            "createtime": createtime,
            "description": "ios",
            "expands": {"noteType": 0},
            "latlng": "",
            "location": "",
            "noteid": note_id,
            "notestatus": 0,
            "remindtime": "",
            "remindtype": 1,
            "revision": "1",
            "sharecount": "0",
            "sharestatus": "0",
            "system": "mobile",
            "tags": [{"id": self.notebook_id, "orderIndex": "0", "text": "默认笔记本"}],
            "title": "00000",
            "topmost": "0",
            "updatetime": updatetime,
            "userphone": self.account,
            "version": "1.00",
            "visitTime": "",
        }
        create_note_data = self.send_request(note_url, headers=headers, data=payload, method="POST")
        if create_note_data.status_code == 200:
            self.log('-创建笔记成功')
        else:
            self.log('-创建失败')

    def get_note_id(self, length):
        characters = '19f3a063d67e4694ca63a4227ec9a94a19088404f9a28084e3e486b928039a299bf756ebc77aa4f6bfa250308ec6a8be8b63b5271a00350d136d117b8a72f39c5bd15cdfd350cba4271dc797f15412d9f269e666aea5039f5049d00739b320bb9e8585a008b52c1cbd86970cae9476446f3e41871de8d9f6112db94b05e5dc7ea0a942a9daf145ac8e487d3d5cba7cea145680efc64794d43dd15c5062b81e1cda7bf278b9bc4e1b8955846e6bc4b6a61c28f831f81b2270289e5a8a677c3141ddc9868129060c0c3b5ef507fbd46c004f6de346332ef7f05c0094215eae1217ee7c13c8dca6d174cfb49c716dd42903bb4b02d823b5f1ff93c3f88768251b56cc'
        note_id = ''.join(random.choice(characters) for _ in range(length))
        return note_id

    @catch_errors
    def do_fruit_task(self, task_name, task_id, water_num):
        self.log(f'-去完成: {task_name}')
        do_task_url = f'{self.fruit_url}task/doTask.do?taskId={task_id}'
        do_task_data = self.send_request(do_task_url, headers=self.treeHeaders).json()

        if do_task_data.get('success'):
            get_water_url = f'{self.fruit_url}task/givenWater.do?taskId={task_id}'
            get_water_data = self.send_request(get_water_url, headers=self.treeHeaders).json()

            if get_water_data.get('success'):
                self.log(f'-已完成任务获得水滴: {water_num}')
            else:
                self.log(f'❌领取失败: {get_water_data.get("msg", "")}')
        else:
            self.log(f'❌参与任务失败: {do_task_data.get("msg", "")}')

    @catch_errors
    def cloud_game(self):
        game_info_url = 'https://caiyun.feixin.10086.cn/market/signin/hecheng1T/info?op=info'
        bigin_url = 'https://caiyun.feixin.10086.cn/market/signin/hecheng1T/beinvite'
        end_url = 'https://caiyun.feixin.10086.cn/market/signin/hecheng1T/finish?flag=true'

        game_info_data = self.send_request(game_info_url, headers=self.jwtHeaders, cookies=self.cookies).json()
        if game_info_data and game_info_data.get('code', -1) == 0:
            currnum = game_info_data.get('result', {}).get('info', {}).get('curr', 0)
            count = game_info_data.get('result', {}).get('history', {}).get('0', {}).get('count', '')
            rank = game_info_data.get('result', {}).get('history', {}).get('0', {}).get('rank', '')

            self.log(f'今日剩余游戏次数: {currnum} 合成次数: {count}')

            for _ in range(currnum):
                self.send_request(bigin_url, headers=self.jwtHeaders, cookies=self.cookies).json()
                print('-开始游戏,等待10-15秒完成游戏')
                time.sleep(random.randint(10, 15))
                end_data = self.send_request(end_url, headers=self.jwtHeaders, cookies=self.cookies).json()
                if end_data and end_data.get('code', -1) == 0:
                    self.log('游戏成功')
        else:
            print("-获取游戏信息失败")

    @catch_errors
    def receive(self):
        prize_url = f"{self.market_base_url}/ycloud/prizeApi/checkPrize/getUserPrizeLogPage?currPage=1&pageSize=15&_={self.timestamp}"
        self.prepare_signin_center_session(for_receive=True)
        info_data = self.request_market_json(f'{self.market_base_url}/ycloud/signin/page/infoV3', params={'client': 'app'})
        if not info_data:
            self.log('查询云朵失败: 接口无响应')
            return
        if info_data.get('code') != 0:
            self.log(f"查询云朵失败: {info_data.get('msg', '未知错误')}")
            return
        info_result = info_data.get('result', {})
        pending_amount = info_result.get('toReceive', 0)
        total_amount = info_result.get('total', '')
        if pending_amount:
            receive_headers = self.build_receive_headers()
            receive_cookies = dict(self.market_cookies)
            # receiveV3 为 POST + JSON，cloudId/cloudType 为空表示领取签到累积云朵。
            # H5 的 axios 拦截器对 isDeviceId 接口会把 deviceId 注入 body，
            # 缺失时服务端返回 614「锁定失败」，必须带上。
            receive_body = {'client': 'app', 'cloudId': '', 'cloudType': ''}
            device_id = self.get_market_device_id()
            if device_id:
                receive_body['deviceId'] = device_id
            receive_data = self.request_json(
                f'{self.market_base_url}/ycloud/signin/page/receiveV3',
                headers=receive_headers,
                cookies=receive_cookies,
                data=receive_body,
                method='POST',
                retries=2,
            )
            if not receive_data:
                self.log('领取云朵失败: 接口无响应')
                self.log(f'-当前待领取:{pending_amount}云朵')
            elif receive_data.get('code') == 0:
                receive_result = receive_data.get('result', {})
                self.log(f'-领取云朵:{receive_result.get("receive", pending_amount)}云朵')
                total_amount = receive_result.get('total', total_amount)
            else:
                latest_info_data = self.request_market_json(f'{self.market_base_url}/ycloud/signin/page/infoV3', params={'client': 'app'})
                latest_result = latest_info_data.get('result', {}) if latest_info_data and latest_info_data.get('code') == 0 else {}
                latest_pending = latest_result.get('toReceive', pending_amount)
                latest_total = latest_result.get('total', total_amount)
                pending_delta = pending_amount - latest_pending if isinstance(pending_amount, int) and isinstance(latest_pending, int) else 0
                total_delta = latest_total - total_amount if isinstance(total_amount, int) and isinstance(latest_total, int) else 0
                claimed_amount = total_delta or pending_delta or (pending_amount if latest_pending == 0 else 0)
                if claimed_amount > 0:
                    self.log(f'-领取云朵:{claimed_amount}云朵')
                    total_amount = latest_total
                else:
                    # 614/615 在新协议下多为「奖品池已抢空 / 无可领份额」的业务性拒绝，
                    # 与 deviceId 无关，不再误导性地提示检查 deviceId。
                    code = receive_data.get('code')
                    if code in (614, 615):
                        self.log(f"-本轮无可领份额（code={code}），保留待领取:{pending_amount}云朵")
                    else:
                        self.log(f"领取云朵失败: {receive_data.get('msg', '未知错误')}")
                        self.log(f'-当前待领取:{pending_amount}云朵')
        else:
            self.log('-当前待领取:0云朵')
        self.sleep()
        prize_data = self.request_json(prize_url, headers=self.jwtHeaders, cookies=self.cookies) or {}
        result = prize_data.get('result', {}).get('result') or []
        rewards = ''
        for value in result:
            if value.get('flag') == 1:
                rewards += f'待领取奖品: {value.get("prizeName")}\n'
        self.log(f'-当前云朵数量:{total_amount}云朵')
        if rewards:
            self.log(rewards)
        global user_amount
        user_amount += f'用户【{self.encrypt_account}】:{total_amount}云朵\n'

    @catch_errors
    def backup_cloud(self):
        backup_url = f'{self.market_base_url}/ycloud/backupgift/info'
        backup_data = self.send_request(backup_url, headers=self.jwtHeaders).json()
        state = backup_data.get('result', {}).get('state', '')
        if state == -1:
            self.log('本月未备份,暂无连续备份奖励')

        elif state == 0:
            self.log('-领取本月连续备份奖励')
            cur_url = f'{self.market_base_url}/ycloud/backupgift/receive'
            cur_data = self.send_request(cur_url, headers=self.jwtHeaders).json()
            self.log(f'-获得云朵数量:{cur_data.get("result").get("result")}')

        elif state == 1:
            print('-已领取本月连续备份奖励')
        self.sleep()
        expend_url = f'{self.market_base_url}/ycloud/signin/page/taskExpansion'
        expend_data = self.send_request(expend_url, headers=self.jwtHeaders, cookies=self.cookies).json()
        curMonthBackup = expend_data.get('result', {}).get('curMonthBackup', '')
        preMonthBackup = expend_data.get('result', {}).get('preMonthBackup', '')
        curMonthBackupTaskAccept = expend_data.get('result', {}).get('curMonthBackupTaskAccept', '')
        nextMonthTaskRecordCount = expend_data.get('result', {}).get('nextMonthTaskRecordCount', '')
        acceptDate = expend_data.get('result', {}).get('acceptDate', '')

        if curMonthBackup:
            self.log(f'- 本月已备份，下月可领取膨胀云朵: {nextMonthTaskRecordCount}')
        else:
            self.log('- 本月还未备份，下月暂无膨胀云朵')

        if preMonthBackup:
            if curMonthBackupTaskAccept:
                print('- 上月已备份，膨胀云朵已领取')
            else:

                receive_url = f'{self.market_base_url}/ycloud/signin/page/receiveTaskExpansion?acceptDate={acceptDate}'
                receive_data = self.send_request(receive_url, headers=self.jwtHeaders, cookies=self.cookies).json()
                if receive_data.get("code") != 0:
                    self.log(f'-领取失败:{receive_data.get("msg")}')
                else:
                    cloudCount = receive_data.get('result', {}).get('cloudCount', '')
                    self.log(f'- 膨胀云朵领取成功: {cloudCount}朵')
        else:
            print('-上月未备份，本月无膨胀云朵领取')

    @catch_errors
    def complete_notice_task(self, task_name):
        notice_status = self.get_notice_status()
        if not notice_status:
            self.log(f'-需手动完成: {task_name}')
            return
        push_on = int(notice_status.get('pushOn') or 0)
        first_status = int(notice_status.get('firstTaskStatus') or 0)
        second_status = int(notice_status.get('secondTaskStatus') or 0)
        on_duration = int(notice_status.get('onDuaration') or 0)
        total = int(notice_status.get('total') or 31)
        if push_on != 1:
            self.log(f'-需手动完成: {task_name} (通知未开启)')
            return
        reward_url = f'{self.market_base_url}/ycloud/msgPushOn/task/obtain'
        if first_status != 3:
            reward1_data = self.request_json(reward_url, headers=self.jwtHeaders, data={"type": 1}, method='POST')
            if reward1_data and reward1_data.get('code') == 0:
                self.log(f'-已领取: {task_name} (首日奖励)')
            else:
                self.log(f'-待领取: {task_name} (首日奖励)')
        if second_status == 2:
            reward2_data = self.request_json(reward_url, headers=self.jwtHeaders, data={"type": 2}, method='POST')
            if reward2_data and reward2_data.get('code') == 0:
                self.log(f'-已领取: {task_name} (连续奖励，已开启{on_duration}/{total}天)')
            else:
                self.log(f'-待领取: {task_name} (已开启{on_duration}/{total}天)')
        elif second_status == 3:
            self.log(f'-已完成: {task_name}')
        else:
            self.log(f'-进行中: {task_name} (已开启{on_duration}/{total}天)')


if __name__ == "__main__":
    try:
        login_records = load_login_records()
    except (RuntimeError, ValueError) as exc:
        print(f'⛔️ {exc}')
        raise SystemExit(1)
    print_startup_info(len(login_records))
    has_cookie = any(r.get('source') == 'cookie' for r in login_records)
    has_yyb = any(r.get('source') == 'yyb' for r in login_records)
    if has_cookie and has_yyb:
        print(f"执行顺序: YYB 账号 {sum(1 for r in login_records if r.get('source') == 'yyb')} 个"
              f" → 环境变量账号 {sum(1 for r in login_records if r.get('source') == 'cookie')} 个")
    if has_cookie:
        print_device_id_notice()
    print_storage_path_notice()

    # 记录已实际执行的归一化手机号，供运行期去重使用
    executed_accounts = set()

    for i, login_record in enumerate(login_records, start=1):
        source = login_record.get('source')
        source_label = {'yyb': 'YYB', 'cookie': '环境变量'}.get(source, source or '未知')
        yp_instance = YP(login_record['cookie'])
        account_label = getattr(yp_instance, 'encrypt_account', '') or f'格式错误-{i}'

        if not yp_instance.Authorization:
            print(f"\n======== ▷ 第 {i} 个账号 [{source_label}] 【{account_label}】◁ ========")
            print(f"⛔️ 账号 {i} 无效（Authorization 无法解析），跳过执行")
            continue

        # 运行期二次去重：环境变量里的 cookie 若在 load 阶段解析不出手机号，
        # 这里用已构造实例的真实账号再判一次，避免与小程序账号重复执行。
        real_account = normalize_phone(getattr(yp_instance, 'account', ''))
        if source == 'cookie' and real_account and real_account in executed_accounts:
            print(f"\n======== ▷ 第 {i} 个账号 [{source_label}] 【{account_label}】◁ ========")
            print(f"⏭️ 该账号已在前面执行过，跳过（去重）")
            continue

        print(f"\n======== ▷ 第 {i} 个账号 [{source_label}] 【{account_label}】◁ ========")
        if real_account:
            executed_accounts.add(real_account)

        if login_record.get('source') == 'yyb':
            yp_instance.user_domain_id = login_record['user_domain_id']
            yp_instance.save_authorization_record(
                token=yp_instance.Authorization,
                user_domain_id=login_record['user_domain_id'],
                expires_at=login_record['expires_at'], refreshed=True,
            )
        yp_instance.run()
        print("\n准备进行下一个账号")
        time.sleep(random.randint(1, 3))

    msg = ""
    if err_accounts:
        msg += f"失效账号:\n{err_accounts}\n"

    # msg += f"任务详情:\n{all_logs}\n"
    msg += f"云朵汇总:\n{user_amount}"

    print("\n================ 运行总结 ================")
    if err_accounts:
        print(f"❌ 失效账号:\n{err_accounts}")
    if user_amount:
        print(f"☁️ 云朵汇总:\n{user_amount}")

    msg = msg.replace('-', ' ').replace('.', ' ').replace('!', '！').replace('(', '（').replace(')', '）')
    msg = msg.replace('_', ' ').replace('=', ' ').replace('~', ' ').replace('{', ' ').replace('}', ' ').replace('|', ' ')

    send_notification('中国移动云盘任务信息', msg or '任务已执行，本次无汇总数据')
