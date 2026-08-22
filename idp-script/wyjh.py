# -*- coding: utf-8 -*-

"""
name: 无忧计划

入口: 无忧计划APP

无忧计划注册链接：https://dgccvi.com/#/register?ref=IPFLKEH
邀请码：IPFLKEH            必须填写邀请码注册
只支持安卓下载

功能: 无忧计划 App 自动签到 + 看广告
新用户首日送1天会员当天可以看20个广告。
免费用户每天为7个广告，单广告0.26-0.28元。

变量说明：
  环境变量名：WY_ACCOUNTS
  单账号格式：备注#账号#密码[#device_id]
  多账号格式：每行一个账号，换行分隔
  - device_id 可选，未填写时自动生成并本地缓存，下次直接复用
  - 自动生成格式：17开头13位数字 - 10位字母数字
  示例（单账号）：
    小号1#13800138000#abc123
  示例（单账号带自定义 device_id）：
    主力号#13800138000#abc123#1701234567890-abcdef1234
  示例（多账号，换行分隔）：
    小号1#13800138000#abc123
    小号2#13900139000#def456
    主力号#13700137000#ghi789#1709876543210-xyz1234567
cron: 16 9,21 * * *
"""
import argparse
import hashlib
import hmac
import json
import logging
import os
import random
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
BASE_URL = "https://api.dgccvi.com"
DEFAULT_ATTEST_KEY = "aac0ab40d0612c8549f88e87e476751a348f910156e9e73590ddaece2a4288d5"
HEARTBEAT_INTERVAL = 30         # 服务端心跳间隔（秒）
SESSION_TTL = 1800              # attest 会话有效期（秒），超过需重新 attest

# 常见 Android WebView User-Agent 池，随机切换降低被封风险
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; SM-S918B Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.153 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6 Build/SQ1D.220205.003; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/105.0.5195.136 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Redmi K40 Build/RKQ1.200826.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/96.0.4664.104 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 10; V2031A Build/QP1A.190711.020; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 9; ASUS_AI2401_A Build/PQ3B.190801.07131748; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Mobile Safari/537.36",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("wuyou")

# ---------------------------------------------------------------------------
# 工具函数
def generate_device_id(account: str) -> str:
    """
    基于账号名生成固定的 device_id
    格式: <17开头的13位数字>-<10位字母数字>
    """
    h = hashlib.md5(account.encode()).hexdigest()
    # 13位数字部分：固定以 17 开头，后接 11 位数字（共13位）
    num_part = "17" + str(int(h[:7], 16) % 100000000000).zfill(11)
    # 10位字母数字部分
    rand_part = h[8:18]
    return f"{num_part}-{rand_part}"

def get_random_ua() -> str:
    """从 User-Agent 池中随机选取一个，降低被检测封禁风险"""
    return random.choice(USER_AGENTS)

def http_request(method: str, url: str, headers: dict, data: bytes = None, timeout: int = 20) -> tuple:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误 {method} {url}: {e.reason}") from e

def quote(s: str) -> str:
    return urllib.parse.quote(str(s))

# ---------------------------------------------------------------------------
# 账号配置
class Account:
    """单个账号的完整配置。"""
    def __init__(self, remark: str, account: str, password: str, device_id: str = ""):
        self.remark = remark.strip()
        self.account = account.strip()
        self.password = password.strip()
        self.device_id = device_id.strip()

        # 其余参数使用默认值，如需自定义可在此处修改
        self.ua = ""                      # 空则启用随机 UA 池
        self.attest_key = DEFAULT_ATTEST_KEY
        self.token = ""
        self.max_ads = 0                  # 0=当日全部额度
        self.watch_min = 40
        self.watch_max = 50
        self.gap_min = 50
        self.gap_max = 60

        # 缓存文件命名（基于账号，不受备注变化影响）
        tag = self.account or self.device_id or "default"
        safe = "".join(c if c.isalnum() else "_" for c in tag)[:24]
        self.token_file = Path(__file__).with_name(f"wuyou_token_{safe}.txt")
        self.device_id_file = Path(__file__).with_name(f"wuyou_device_{safe}.txt")

        # 初始化 device_id：配置 > 本地缓存 > 自动生成并保存
        self._init_device_id()

    @property
    def label(self) -> str:
        """日志显示标签：优先备注，其次账号"""
        return self.remark or self.account or self.device_id or "(未配置账号)"

    def _init_device_id(self) -> None:
        """device_id 优先级：手动配置 > 本地缓存文件 > 自动生成并持久化"""
        # 1. 手动配置了 device_id
        if self.device_id:
            log.info("[%s] 使用手动配置的 device_id: %s", self.label, self.device_id)
            self._save_device_id_cache(self.device_id)
            return

        # 2. 读取本地缓存
        if self.device_id_file.exists():
            cached_id = self.device_id_file.read_text(encoding="utf-8").strip()
            if cached_id:
                self.device_id = cached_id
                log.info("[%s] 读取本地缓存 device_id: %s", self.label, self.device_id)
                return

        # 3. 自动生成并保存
        if not self.account:
            raise RuntimeError(f"[{self.label}] 无账号信息，无法自动生成 device_id")
        self.device_id = generate_device_id(self.account)
        log.info("[%s] 自动生成新 device_id: %s", self.label, self.device_id)
        self._save_device_id_cache(self.device_id)

    def _save_device_id_cache(self, device_id: str) -> None:
        """将 device_id 写入本地缓存文件"""
        try:
            self.device_id_file.write_text(device_id, encoding="utf-8")
        except Exception as e:
            log.warning("[%s] device_id 缓存保存失败: %s", self.label, e)

    def check_required(self) -> None:
        missing = []
        if not self.device_id:
            missing.append("device_id")
        if not self.account and not self.token:
            missing.append("账号或 token")
        if missing:
            raise RuntimeError(f"账号 {self.label} 缺少必填项: {', '.join(missing)}")

def parse_accounts() -> list:
    """
    解析环境变量 WY_ACCOUNTS
    格式：备注#账号#密码[#device_id]，多账号用换行分隔
    """
    accounts = []
    raw = os.environ.get("WY_ACCOUNTS", "").strip()
    if not raw:
        return accounts

    # 按换行分割，逐行处理
    lines = raw.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue  # 跳过空行
        parts = line.split("#")
        if len(parts) < 3:
            log.warning("账号格式错误，已跳过: %s（需至少包含 备注#账号#密码）", line)
            continue
        remark = parts[0].strip()
        acc = parts[1].strip()
        pwd = parts[2].strip()
        did = parts[3].strip() if len(parts) >= 4 else ""
        accounts.append(Account(remark, acc, pwd, did))
    return accounts

# ---------------------------------------------------------------------------
# 密码学与签名
def hmac_hex(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def body_str_of(body) -> str:
    """与 App JSON.stringify 一致：dict 转紧凑 JSON，str 原样，None 为空串。"""
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))

class Session:
    """attest 会话：负责获取/持有 session_id / session_secret 并签发请求。"""
    def __init__(self, account: Account):
        self.account = account
        self.session_id = None
        self.session_secret = None
        self.session_at = 0.0
        self.token = account.token

    def attest(self) -> None:
        ts = str(int(time.time()))
        nonce = secrets.token_hex(16)
        proof = hmac_hex(self.account.attest_key, f"attest\n{ts}\n{nonce}\n{self.account.device_id}")
        body = json.dumps({"integrity_token": "", "device_id": self.account.device_id,
                           "ts": ts, "nonce": nonce, "native_proof": proof}, ensure_ascii=False)
        status, raw = http_request("POST", f"{BASE_URL}/api/app/attest",
                                   {"Content-Type": "application/json"}, body.encode())
        if status != 200:
            raise RuntimeError(f"attest 失败 HTTP {status}: {raw[:200]}")
        data = json.loads(raw)
        if not (data.get("ok") and data.get("session_id") and data.get("session_secret")):
            raise RuntimeError(f"attest 失败: {data}")
        self.session_id = data["session_id"]
        self.session_secret = data["session_secret"]
        self.session_at = time.time()
        log.info("[%s] attest 成功，session 有效期 %s 秒", self.account.label, data.get("expires_in", SESSION_TTL))

    def ensure_session(self) -> None:
        """会话不存在或临近过期时重新 attest。"""
        if not self.session_secret or time.time() - self.session_at > SESSION_TTL - 60:
            self.attest()

    def sign(self, method: str, path: str, ts: str, nonce: str, body: str) -> str:
        msg = f"{method.upper()}\n{path}\n{ts}\n{nonce}\n{sha256_hex(body)}"
        return hmac_hex(self.session_secret, msg)

    def api(self, method: str, path: str, query: dict = None, body=None) -> dict:
        """签名并发送业务请求，path 为 URL pathname（不含查询串）。返回响应 JSON。"""
        self.ensure_session()
        ts = str(int(time.time()))
        nonce = secrets.token_hex(16)
        body_str = body_str_of(body)
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": self.account.ua or get_random_ua(),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://localhost",
            "Referer": "https://localhost/",
            "X-Requested-With": "com.dgccvi.app",
            "X-App-Session": self.session_id,
            "X-App-Ts": ts,
            "X-App-Nonce": nonce,
            "X-App-Sign": self.sign(method, path, ts, nonce, body_str),
            "Content-Type": "application/json",
        }
        url = f"{BASE_URL}{path}"
        if query:
            url += "?" + "&".join(f"{k}={quote(str(v))}" for k, v in query.items())
        status, raw = http_request(method, url, headers,
                                   body_str.encode() if body_str else None)
        if status == 401:
            raise TokenExpiredError("登录 token 已失效（HTTP 401）")
        if status == 403:
            raise RuntimeError(f"签名被拒（403）: {raw[:200]}")
        try:
            data = json.loads(raw)
        except ValueError:
            data = {"_raw": raw[:300]}
        if status != 200:
            raise RuntimeError(f"请求失败 {status} {method} {path}: {data}")
        return data

# ---------------------------------------------------------------------------
# 登录与 token 管理
class TokenExpiredError(RuntimeError):
    """登录 token 失效（业务接口返回 401）。"""

def load_token(account: Account) -> str:
    """读取 token：优先配置中 token，其次该账号的本地缓存文件。"""
    t = account.token.strip()
    if t:
        return t
    if account.token_file.exists():
        t = account.token_file.read_text(encoding="utf-8").strip()
        if t:
            return t
    return ""

def save_token(account: Account, token: str) -> None:
    account.token_file.write_text(token, encoding="utf-8")
    log.info("[%s] 新 token 已缓存到 %s", account.label, account.token_file)

def login(sess: Session) -> str:
    """账号密码登录（登录接口同样需要 attest 签名），返回新 token。"""
    account = sess.account
    if not account.account or not account.password:
        raise RuntimeError(f"[{account.label}] 未配置账号密码，且无可用 token")
    body = {"account": account.account, "password": account.password,
            "device_id": account.device_id, "platform": "android", "app_version": "1.0.8"}
    sess.ensure_session()
    ts = str(int(time.time()))
    nonce = secrets.token_hex(16)
    body_str = body_str_of(body)
    headers = {
        "User-Agent": account.ua or get_random_ua(),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://localhost",
        "Referer": "https://localhost/",
        "X-Requested-With": "com.dgccvi.app",
        "X-App-Session": sess.session_id,
        "X-App-Ts": ts,
        "X-App-Nonce": nonce,
        "X-App-Sign": sess.sign("POST", "/api/app/auth/login", ts, nonce, body_str),
        "Content-Type": "application/json",
    }
    status, raw = http_request("POST", f"{BASE_URL}/api/app/auth/login", headers, body_str.encode())
    if status == 401:
        raise RuntimeError(f"[{account.label}] 登录失败：账号或密码错误（HTTP 401）")
    if status != 200:
        raise RuntimeError(f"[{account.label}] 登录失败 HTTP {status}: {raw[:200]}")
    data = json.loads(raw)
    token = data.get("token") or (data.get("data") or {}).get("token")
    if not token:
        raise RuntimeError(f"[{account.label}] 登录响应中未找到 token 字段: {raw[:200]}")
    log.info("[%s] 登录成功，获取新 token（%s...）", account.label, token[:24])
    return token

def ensure_token(sess: Session) -> str:
    """验证已有 token 有效性，无效或缺失时账号密码登录并缓存。"""
    account = sess.account
    token = load_token(account)
    if token:
        sess.token = token
        try:
            sess.api("GET", "/api/app/checkin/status")
            log.info("[%s] 已有 token 有效，无需重新登录", account.label)
            return token
        except TokenExpiredError:
            log.warning("[%s] 已有 token 已失效，改用账号密码登录", account.label)
    token = login(sess)
    save_token(account, token)
    sess.token = token
    return token

# ---------------------------------------------------------------------------
# 通知（青龙面板 notify.py；非青龙环境退化为控制台输出）
def send_notify(title: str, content: str) -> None:
    for p in ("/ql/scripts", "/ql/data/scripts"):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    try:
        import importlib
        notify = importlib.import_module("notify")
        notify.send(title, content)
        log.info("通知已发送: %s", title)
    except Exception:
        log.info("通知[%s]: %s", title, content.replace("\n", " | "))

# ---------------------------------------------------------------------------
# 业务流程
def do_checkin(sess: Session, summary: dict) -> None:
    log.info("==== 签到流程 ====")
    status = sess.api("GET", "/api/app/checkin/status")
    if status.get("checked_today"):
        log.info("今日已签到，跳过（doubled_today=%s）", status.get("doubled_today"))
        summary["checkin"] = "今日已签到，跳过"
        return
    result = sess.api("POST", "/api/app/checkin")
    msg = result.get("message", str(result))
    log.info("签到成功: %s", msg)
    summary["checkin"] = msg

# ------------------------------ 每日任务 ------------------------------
def get_daily_tasks(sess: Session) -> dict:
    """获取每日任务列表"""
    return sess.api("GET", "/api/app/daily-tasks")

def show_tasks(sess: Session, data: dict) -> None:
    """格式化展示任务信息"""
    tasks = data.get("tasks", [])
    today = data.get("today", "")
    pending = data.get("pending_claim", 0)
    log.info("📅 任务日期: %s | 待领取奖励: %s个", today, pending)
    log.info("-" * 60)
    total_daily = 0
    total_weekly = 0
    for task in tasks:
        icon = task.get("icon", "📌")
        title = task.get("title", "未知任务")
        reward = task.get("reward_coins", 0)
        progress = task.get("current_progress", 0)
        target = task.get("condition_value", 0)
        completed = task.get("is_completed", False)
        claimed = task.get("is_claimed", False)
        period = task.get("period_type", "")
        task_key = task.get("task_key", "")
        if claimed:
            status = "✅ 已领取"
        elif completed:
            status = "🎁 可领取"
        else:
            status = f"⏳ 进度 {progress}/{target}"
        log.info("  %s %-20s | %-12s | +%4s金币 | [%s] [%s]",
                 icon, title, status, reward, period, task_key)
        if period == "daily":
            total_daily += reward
        else:
            total_weekly += reward
    log.info("-" * 60)
    log.info("💰 每日任务总奖励: %s金币 | 每周任务总奖励: %s金币", total_daily, total_weekly)

def claim_task(sess: Session, task_key: str) -> dict:
    """领取指定任务的奖励"""
    return sess.api("POST", f"/api/app/daily-tasks/{task_key}/claim")
# --------------------------------------------------------------------

def fetch_ads_state(sess: Session) -> dict:
    return sess.api("GET", "/api/app/alliance-ads", query={"device_id": sess.account.device_id})

def heartbeat(sess: Session, play_token: str, progress: float) -> None:
    body = {"play_token": play_token, "progress_seconds": round(progress, 2)}
    resp = sess.api("POST", "/api/app/alliance-ads/session/heartbeat", body=body)
    log.info("  心跳 progress=%.2f -> watched=%.2f", progress, resp.get("watched_seconds", 0))

def simulate_watch(sess: Session, play_token: str, duration: int) -> float:
    """模拟观看：按 30s 心跳节奏上报进度，总时长 = max(广告时长, watch_min~watch_max 随机)。"""
    watch_seconds = max(duration, random.uniform(sess.account.watch_min, sess.account.watch_max))
    log.info("  模拟观看 %.1f 秒（广告时长 %d 秒）", watch_seconds, duration)
    heartbeat(sess, play_token, 0.02)          # 开始播放
    remaining = watch_seconds
    while remaining > HEARTBEAT_INTERVAL:      # 每满 30s 上报一次进度
        time.sleep(HEARTBEAT_INTERVAL)
        remaining -= HEARTBEAT_INTERVAL
        heartbeat(sess, play_token, watch_seconds - remaining)
    time.sleep(remaining)
    final = round(watch_seconds + 0.1, 2)      # 播放结束（略超时长，服务端会截断）
    heartbeat(sess, play_token, final)
    return final

def watch_one_ad(sess: Session) -> dict:
    state = fetch_ads_state(sess)
    if not state.get("enabled"):
        log.warning("联盟广告未开启")
        return {}
    wait = state.get("next_request_available_in", 0) or 0
    if wait > 0:
        log.info("服务端限流，等待 %d 秒", wait)
        time.sleep(wait)
    started = sess.api("POST", "/api/app/alliance-ads/session/start",
                       body={"device_id": sess.account.device_id, "client": "app"})
    session = started.get("session") or {}
    play_token = session.get("play_token")
    if not play_token:
        log.warning("session/start 未返回 play_token: %s", started)
        return {}
    ad = session.get("ad") or {}
    duration = int(session.get("duration_seconds") or ad.get("duration_seconds") or 30)
    log.info("广告[%s] %s，时长 %d 秒，奖励 %s 金币",
             session.get("session_id"), ad.get("title", "?"), duration, session.get("reward_coins"))
    final = simulate_watch(sess, play_token, duration)
    done = sess.api("POST", "/api/app/alliance-ads/session/complete",
                    body={"play_token": play_token, "progress_seconds": final})
    log.info("观看完成: %s（金币 +%s，record_id=%s）",
             done.get("message", ""), done.get("gold_coins", 0), done.get("record_id"))
    return done

def run_ads(sess: Session, max_ads: int = None, summary: dict = None) -> None:
    log.info("==== 广告流程（目标 %s 个）====", max_ads if max_ads else "当日全部")
    state = fetch_ads_state(sess)
    cap = state.get("max_views_per_day") or state.get("max_views_per_account_per_day") or 0
    limit = min(max_ads, cap) if max_ads else cap
    earned, watched = 0, 0
    if not state.get("enabled") or limit <= 0:
        log.info("今日无可观看广告（enabled=%s, 上限=%s）", state.get("enabled"), cap)
        summary["ads"] = "今日无可观看广告"
        return
    for i in range(1, limit + 1):
        log.info("--- 第 %d/%d 个广告 ---", i, limit)
        try:
            done = watch_one_ad(sess)
            if done.get("duplicate"):
                log.info("该广告重复计费，停止本日广告")
                break
            earned += done.get("gold_coins", 0) or 0
            watched += 1
        except RuntimeError as e:
            log.error("广告观看失败: %s", e)
            break
        if i < limit:
            gap = random.uniform(sess.account.gap_min, sess.account.gap_max)
            wait = done.get("next_request_available_in", 0) or 0
            gap = max(gap, wait)
            log.info("广告间隔 %.0f 秒", gap)
            time.sleep(gap)
    summary["ads"] = f"观看 {watched}/{limit} 个广告，获得 {earned} 金币"

# ---------------------------------------------------------------------------
# 入口
def run_account(account: Account, args) -> dict:
    """执行单个账号的签到与广告，返回结果摘要。"""
    sess = Session(account)
    summary = {}
    try:
        account.check_required()
        sess.attest()
        ensure_token(sess)

        # 1. 展示初始每日任务状态
        if not args.skip_daily_tasks:
            log.info("==== 每日任务初始状态 ====")
            tasks_data = get_daily_tasks(sess)
            show_tasks(sess, tasks_data)

        # 2. 每日签到
        if not args.skip_checkin:
            do_checkin(sess, summary)

        # 3. 看广告赚金币
        if not args.skip_ads:
            max_ads = args.ads if args.ads is not None else (account.max_ads or None)
            run_ads(sess, max_ads, summary)

        # 4. 领取所有可领取的每日任务奖励
        if not args.skip_daily_tasks:
            log.info("==== 领取每日任务奖励 ====")
            tasks_data = get_daily_tasks(sess)
            tasks = tasks_data.get("tasks", [])
            claimed_count = 0
            claimed_coins = 0
            for task in tasks:
                task_key = task.get("task_key", "")
                task_title = task.get("title", "未知任务")
                if task.get("is_completed") and not task.get("is_claimed"):
                    log.info("🎁 领取: %s", task_title)
                    try:
                        result = claim_task(sess, task_key)
                        if result.get("ok"):
                            coins = result.get("coins", 0)
                            msg = result.get("message", "领取成功")
                            claimed_count += 1
                            claimed_coins += coins
                            log.info("   %s | +%s金币", msg, coins)
                        else:
                            log.warning("   失败: %s", result)
                    except RuntimeError as e:
                        log.warning("   异常: %s", e)
            summary["daily_tasks"] = f"领取 {claimed_count} 个任务，合计 {claimed_coins} 金币"

    except TokenExpiredError as e:
        log.error("[%s] 执行过程中登录失效: %s", account.label, e)
        summary["error"] = "登录 token 失效，重新登录未成功"
    except RuntimeError as e:
        log.error("[%s] 执行异常: %s", account.label, e)
        summary["error"] = str(e)
    return summary

def main() -> None:
    parser = argparse.ArgumentParser(description="无忧计划自动签到 + 看广告（青龙面板兼容，多账号）")
    parser.add_argument("--ads", type=int, default=None, help="本次每个账号观看广告数量（默认当日全部额度）")
    parser.add_argument("--skip-checkin", action="store_true", help="跳过签到")
    parser.add_argument("--skip-ads", action="store_true", help="跳过广告")
    parser.add_argument("--skip-daily-tasks", action="store_true", help="跳过每日任务展示与领取")
    parser.add_argument("--no-notify", action="store_true", help="完成不发送通知")
    args = parser.parse_args()

    accounts = parse_accounts()
    if not accounts:
        log.error("未配置环境变量 WY_ACCOUNTS（格式：备注#账号#密码[#device_id]，多账号换行分隔）")
        sys.exit(1)

    log.info("========== 无忧计划自动执行开始 %s ==========", datetime.now())
    log.info("运行环境: %s，共 %d 个账号", "青龙面板" if os.path.isdir("/ql") else "本机", len(accounts))
    started = time.time()
    results = []
    for idx, account in enumerate(accounts, 1):
        log.info("========== 账号 %d/%d: %s ==========", idx, len(accounts), account.label)
        results.append((account.label, run_account(account, args)))
    elapsed = int(time.time() - started)
    log.info("========== 全部完成，耗时 %d 秒 %s ==========", elapsed, datetime.now())

    if not args.no_notify:
        lines = [f"共 {len(accounts)} 个账号，耗时 {elapsed} 秒"]
        for label, summary in results:
            lines.append(f"--- {label} ---")
            for k, v in summary.items():
                lines.append(f"{k}: {v}")
        send_notify("无忧计划自动执行", "\n".join(lines))

if __name__ == "__main__":
    main()