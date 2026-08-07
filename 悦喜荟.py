#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# cron: 46 9,15 * * *
"""
# name: 悦喜荟
中粮悦喜荟小程序签到脚本（青龙）

只需配置环境变量：
  WX_ID          微信账号，格式 wxid#备注；多账号用换行或 & 分隔（账号内第一个 # 分备注）
                 账号来源统一通过 getCode 获取 code（牛子/应用宝双协议）
                 如需指定协议可配置环境变量 SERVER_TYPE / WECHAT_SERVER / YYB_SERVER

脚本顶部可改行为开关（中文备注见常量区，一般不用改）：

业务：code 登录 -> 缓存 token -> 查积分 -> sign/list -> 未签则 sign/in -> 再查积分
游客签到失败会提示「需绑手机」，不做 bindMobile。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from getCode import get_single_code

# ========================= 业务常量（一般不用改） =========================
APP_ID = "wx4a9b92a0680e7b29"
BASE_URL = "https://yxh.cofco.com"
API_PREFIX = "/applet/app/api/v1"
REFERER = f"https://servicewechat.com/{APP_ID}/page-frame.html"
NOTIFY_TITLE = "悦喜荟签到"
CACHE_SKEW_SECONDS = 300
DEFAULT_TOKEN_TTL_SECONDS = 7 * 24 * 3600

# ========================= 行为开关（写在脚本里，一般不用改） =========================
# 是否启用 token 本地缓存；True=优先用缓存，失效再重新取 code 登录
ENABLE_TOKEN_CACHE = True
# token 缓存文件路径；空字符串=自动：脚本同目录 .yxh_token_cache.json
TOKEN_CACHE_FILE = ""
# 是否启用青龙 notify.py 推送汇总结果
ENABLE_NOTIFY = True
# 是否打印调试日志（不会打印 token/code 明文）
DEBUG = False
# 是否仅演练：登录/查状态/查积分，但不提交签到
DRY_RUN = False
# 是否跳过签到动作：仍会登录并查询签到状态与积分
SKIP_SIGN = False

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF XWEB/14185"
)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, level: str = "info") -> None:
    prefix = {"error": "ERROR", "warn": "WARN", "debug": "DEBUG"}.get(level, "INFO")
    if level == "debug" and not DEBUG:
        return
    print(f"{now_text()} - {prefix}\t- {message}")


def mask_wxid(wxid: str) -> str:
    value = str(wxid or "")
    if len(value) <= 8:
        return value[:2] + "***" if value else ""
    return f"{value[:5]}***{value[-3:]}"


def mask_phone(phone: Any) -> str:
    value = str(phone or "")
    return re.sub(r"^(\d{3})\d{4}(\d{4})$", r"\1****\2", value)


def mask_name(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if re.fullmatch(r"1\d{10}", text):
        return mask_phone(text)
    if len(text) <= 2:
        return text[0] + "*"
    return text[0] + "*" * min(3, len(text) - 1)


def to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def points_text(value: Any) -> str:
    num = to_float(value)
    if num is None:
        return "?"
    if abs(num - int(num)) < 1e-9:
        return str(int(num))
    return str(num)


@dataclass
class WxAccount:
    wxid: str
    remark: str = ""

    @property
    def label(self) -> str:
        return self.remark or mask_wxid(self.wxid)


@dataclass
class AccountSummary:
    index: int
    label: str
    login_ok: bool = False
    is_member: Optional[bool] = None
    member_id: str = ""
    nickname: str = ""
    mobile: str = ""
    level_name: str = ""
    before_points: Optional[float] = None
    after_points: Optional[float] = None
    today_signed_before: Optional[bool] = None
    today_signed_after: Optional[bool] = None
    continuous_day: Optional[int] = None
    sign_status: str = "未执行"
    extra_lines: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def success(self) -> bool:
        if self.error:
            return False
        if self.sign_status in {"签到成功", "今日已签到"}:
            return True
        if self.login_ok and self.sign_status.startswith("dry-run"):
            return True
        if self.login_ok and self.sign_status.startswith("已按"):
            return True
        return False

    def notify_lines(self) -> List[str]:
        lines = [f"【账号{self.index}】{self.label}", f"结果: {self.sign_status}"]
        if self.is_member is not None:
            lines.append(f"会员: {'是' if self.is_member else '否(游客)'}")
        if self.nickname:
            lines.append(f"昵称: {mask_name(self.nickname)}")
        if self.mobile:
            lines.append(f"手机号: {mask_phone(self.mobile)}")
        if self.level_name:
            lines.append(f"等级: {self.level_name}")
        if self.before_points is not None or self.after_points is not None:
            lines.append(
                f"积分: {points_text(self.before_points)} -> {points_text(self.after_points)}"
            )
        if self.continuous_day is not None:
            lines.append(f"连续签到: {self.continuous_day} 天")
        lines.extend(self.extra_lines)
        if self.error:
            lines.append(f"说明: {self.error}")
        return lines


def split_accounts(raw_value: str) -> List[WxAccount]:
    """多账号仅按换行/& 分隔；账号内第一个 # 分出备注。"""
    accounts: List[WxAccount] = []
    if not raw_value:
        return accounts

    for item in re.split(r"[\n&]+", raw_value):
        item = item.strip()
        if not item:
            continue
        if "#" in item:
            wxid, remark = item.split("#", 1)
            wxid = wxid.strip()
            remark = remark.strip()
        else:
            wxid = item
            remark = ""
        if wxid:
            accounts.append(WxAccount(wxid=wxid, remark=remark))
    return accounts


def extract_wx_code(data: Any) -> str:
    """兼容 WECHAT_SERVER 返回：大写 Data.code / 小写 data.code / js_code。"""
    if not isinstance(data, dict):
        return ""

    def looks_like_wx_code(val: Any) -> bool:
        if not isinstance(val, str):
            return False
        text_val = val.strip()
        if not text_val:
            return False
        # 业务状态码 0/200 等
        if text_val.isdigit() and len(text_val) <= 4:
            return False
        # 真实 wx.login code 一般较长（你的中转返回约 30+）
        return len(text_val) >= 10

    def from_dict(obj: Dict[str, Any]) -> str:
        if not isinstance(obj, dict):
            return ""
        for key in ("js_code", "jsCode", "wx_code", "wxCode", "code", "Code"):
            val = obj.get(key)
            if looks_like_wx_code(val):
                return str(val).strip()
        return ""

    # 优先嵌套 Data/data（协议中转常见大写 Data）
    for nest_key in ("Data", "data", "result", "Result"):
        nested = data.get(nest_key)
        if isinstance(nested, dict):
            code = from_dict(nested)
            if code:
                return code
            for nest_key2 in ("Data", "data", "result", "Result"):
                nested2 = nested.get(nest_key2)
                if isinstance(nested2, dict):
                    code = from_dict(nested2)
                    if code:
                        return code
                elif looks_like_wx_code(nested2):
                    return str(nested2).strip()
        elif looks_like_wx_code(nested):
            return str(nested).strip()

    return from_dict(data)


def is_business_success(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("success") is True:
        return True
    code = data.get("code")
    return code in (0, 200, "0", "200")


def brief_error(data: Any) -> str:
    if not isinstance(data, dict):
        return str(data)[:200]
    err = data.get("error")
    msg = None
    code = None
    if isinstance(err, dict):
        msg = err.get("message") or err.get("msg")
        code = err.get("code")
    msg = msg or data.get("message") or data.get("msg") or data.get("errmsg")
    code = code if code is not None else data.get("code")
    if msg and code is not None:
        return f"code={code} msg={msg}"
    if msg:
        return str(msg)
    if code is not None:
        return f"code={code}"
    return json.dumps({k: data.get(k) for k in list(data)[:6]}, ensure_ascii=False)[:200]


def looks_like_need_bind_mobile(message: str) -> bool:
    text = str(message or "").lower()
    keys = [
        "绑手机",
        "绑定手机",
        "手机号",
        "未注册",
        "非会员",
        "不是会员",
        "请先登录",
        "游客",
        "完善信息",
        "member",
        "mobile",
        "bind",
        "register",
    ]
    return any(k.lower() in text for k in keys)


class WechatCodeClient:
    def get_code(self, wxid: str) -> str:
        log(f"微信: 获取 code ({mask_wxid(wxid)})", "debug")
        try:
            return get_single_code(APP_ID, wxid)
        except Exception as exc:
            raise RuntimeError(f"微信 code 获取失败: {exc}") from exc


def default_cache_path() -> Path:
    if TOKEN_CACHE_FILE.strip():
        return Path(TOKEN_CACHE_FILE.strip()).expanduser()

    script_dir = Path(__file__).resolve().parent
    if script_dir.name.lower() == "src":
        return script_dir.parent / "temp" / "yxh_token_cache.json"
    return script_dir / ".yxh_token_cache.json"


def account_cache_key(wxid: str) -> str:
    return hashlib.sha256(f"{APP_ID}:{wxid}".encode("utf-8")).hexdigest()


class TokenCache:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.enabled = bool(ENABLE_TOKEN_CACHE)
        self.path = path or default_cache_path()
        self.data: Dict[str, Any] = {"version": 1, "appid": APP_ID, "accounts": {}}
        if self.enabled:
            self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and isinstance(data.get("accounts"), dict):
                self.data = data
        except Exception as exc:
            log(f"缓存: 读取失败，将忽略旧缓存 ({exc})", "warn")

    def _save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(self.data, fp, ensure_ascii=False, indent=2)
        tmp_path.replace(self.path)

    def get(self, wxid: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        item = self.data.get("accounts", {}).get(account_cache_key(wxid))
        if not isinstance(item, dict):
            return None

        token = item.get("token") or item.get("access_token")
        expires_at = item.get("expires_at")
        try:
            expires_at_num = float(expires_at)
        except (TypeError, ValueError):
            return None

        if not token or expires_at_num <= time.time() + CACHE_SKEW_SECONDS:
            return None
        return item

    def set(
        self,
        wxid: str,
        token: str,
        expires_at: Any = None,
        expire_time_ms: Any = None,
        member_id: str = "",
        is_member: Any = None,
    ) -> None:
        if not self.enabled or not token:
            return

        exp: Optional[float] = None
        if expire_time_ms is not None:
            try:
                ms = float(expire_time_ms)
                exp = ms / 1000.0 if ms > 1e12 else ms
            except (TypeError, ValueError):
                exp = None
        if exp is None and expires_at is not None:
            try:
                exp = float(expires_at)
            except (TypeError, ValueError):
                exp = None
        if exp is None:
            exp = time.time() + DEFAULT_TOKEN_TTL_SECONDS

        key = account_cache_key(wxid)
        accounts = self.data.setdefault("accounts", {})
        accounts[key] = {
            "wxid_mask": mask_wxid(wxid),
            "token": token,
            "expires_at": exp,
            "member_id": member_id,
            "is_member": is_member,
            "updated_at": time.time(),
        }
        self._save()

    def delete(self, wxid: str) -> None:
        if not self.enabled:
            return
        key = account_cache_key(wxid)
        accounts = self.data.get("accounts", {})
        if key in accounts:
            del accounts[key]
            self._save()


class YxhClient:
    def __init__(self, token: str = "") -> None:
        self.token = token
        self.session = requests.Session()
        self.session.trust_env = False
        self.login_meta: Dict[str, Any] = {}

    def _headers(self, need_auth: bool = True) -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Referer": REFERER,
            "xweb_xhr": "1",
        }
        if need_auth and self.token:
            headers["token"] = self.token
        return headers

    def api(
        self,
        method: str,
        path: str,
        json_body: Any = None,
        params: Optional[Dict[str, Any]] = None,
        need_auth: bool = True,
    ) -> Tuple[int, Dict[str, Any]]:
        if not path.startswith("http"):
            if not path.startswith("/"):
                path = "/" + path
            if path.startswith(API_PREFIX):
                url = BASE_URL + path
            else:
                url = BASE_URL + API_PREFIX + path
        else:
            url = path

        try:
            resp = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_body,
                headers=self._headers(need_auth=need_auth),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"请求失败 {method} {path}: {exc}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(
                f"非 JSON 响应 {method} {path}: HTTP {resp.status_code} body={resp.text[:200]}"
            ) from exc

        if not isinstance(data, dict):
            data = {"success": False, "data": data, "raw_status": resp.status_code}

        ok = data.get("success") is True
        log(
            f"业务: {method} {path} HTTP {resp.status_code} "
            f"{'ok' if ok else brief_error(data)}",
            "debug",
        )
        return resp.status_code, data

    def login(self, wx_code: str) -> Dict[str, Any]:
        _, data = self.api(
            "POST",
            "/auth/login",
            json_body={"code": wx_code, "koOpenId": None},
            need_auth=False,
        )
        if not is_business_success(data):
            raise RuntimeError(f"登录失败: {brief_error(data)}")

        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        token = payload.get("token")
        if not token:
            raise RuntimeError(f"登录响应缺少 token: {brief_error(data)}")

        self.token = str(token)
        self.login_meta = payload
        return payload

    def member_base(self) -> Dict[str, Any]:
        _, data = self.api("POST", "/member/base", json_body={})
        if not is_business_success(data):
            raise RuntimeError(f"会员信息失败: {brief_error(data)}")
        payload = data.get("data")
        if not isinstance(payload, dict):
            raise RuntimeError("会员信息响应 data 非对象")
        new_token = payload.get("token")
        if new_token:
            self.token = str(new_token)
        return payload

    def sign_list(self) -> Dict[str, Any]:
        _, data = self.api("POST", "/mission/sign/list", json_body={})
        if not is_business_success(data):
            raise RuntimeError(f"签到状态查询失败: {brief_error(data)}")
        payload = data.get("data")
        return payload if isinstance(payload, dict) else {}

    def sign_in(self) -> Any:
        _, data = self.api("POST", "/mission/sign/in", json_body={})
        if not is_business_success(data):
            raise RuntimeError(brief_error(data))
        return data.get("data")


def fill_member(summary: AccountSummary, member: Dict[str, Any], before: bool) -> None:
    summary.member_id = str(member.get("memberId") or summary.member_id or "")
    summary.nickname = str(member.get("nickname") or summary.nickname or "")
    mobile = member.get("mobile")
    if mobile:
        summary.mobile = str(mobile)
    if member.get("isMember") is not None:
        summary.is_member = bool(member.get("isMember"))
    level = member.get("levelName")
    if level:
        summary.level_name = str(level)
    pts = to_float(member.get("point"))
    if before:
        summary.before_points = pts
    else:
        summary.after_points = pts


def find_notify_send() -> Optional[Callable[[str, str], Any]]:
    try:
        from notify import send  # type: ignore

        return send
    except Exception:
        pass

    search_dirs: List[Path] = []
    script_dir = Path(__file__).resolve().parent
    ql_dir = os.environ.get("QL_DIR", "")
    if ql_dir:
        root = Path(ql_dir)
        search_dirs.extend([root, root / "scripts", root / "deps", root / "repo"])
    search_dirs.extend(
        [
            script_dir,
            script_dir.parent,
            Path.cwd(),
            Path("/ql"),
            Path("/ql/scripts"),
            Path("/ql/data/scripts"),
        ]
    )

    seen = set()
    for directory in search_dirs:
        try:
            resolved = directory.resolve()
        except Exception:
            continue
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        notify_path = resolved / "notify.py"
        if not notify_path.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location("yxh_notify", notify_path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules["yxh_notify"] = module
            spec.loader.exec_module(module)
            if hasattr(module, "send"):
                return getattr(module, "send")
            if hasattr(module, "sendNotify"):
                return getattr(module, "sendNotify")
        except Exception as exc:
            log(f"通知: 加载 {notify_path} 失败 ({exc})", "debug")
    return None


def push_notify(title: str, content: str) -> None:
    if not ENABLE_NOTIFY:
        log("通知: 脚本内 ENABLE_NOTIFY=False，跳过")
        return
    send_func = find_notify_send()
    if not send_func:
        log("通知: 未找到 notify.py，跳过推送", "debug")
        return
    try:
        send_func(title, content)
        log("通知: 已推送")
    except Exception as exc:
        log(f"通知: 推送失败 ({exc})", "warn")


def ensure_client(
    account: WxAccount,
    wx_client: WechatCodeClient,
    token_cache: TokenCache,
    summary: AccountSummary,
) -> YxhClient:
    cached = token_cache.get(account.wxid)
    if cached:
        client = YxhClient(token=str(cached.get("token") or ""))
        try:
            member = client.member_base()
            summary.login_ok = True
            fill_member(summary, member, before=True)
            log("登录: 使用缓存 token")
            token_cache.set(
                account.wxid,
                client.token,
                expires_at=cached.get("expires_at"),
                member_id=summary.member_id,
                is_member=summary.is_member,
            )
            return client
        except Exception as exc:
            log(f"缓存: token 不可用，准备重新登录 ({exc})", "warn")
            token_cache.delete(account.wxid)

    client = YxhClient()
    wx_code = wx_client.get_code(account.wxid)
    login_payload = client.login(wx_code)
    summary.login_ok = True
    log("登录: code 登录成功")

    if login_payload.get("isMember") is not None:
        summary.is_member = bool(login_payload.get("isMember"))
    if login_payload.get("memberId") is not None:
        summary.member_id = str(login_payload.get("memberId"))
    if login_payload.get("mobile"):
        summary.mobile = str(login_payload.get("mobile"))

    token_cache.set(
        account.wxid,
        client.token,
        expire_time_ms=login_payload.get("expireTime"),
        member_id=summary.member_id,
        is_member=summary.is_member,
    )

    try:
        member = client.member_base()
        fill_member(summary, member, before=True)
        token_cache.set(
            account.wxid,
            client.token,
            expire_time_ms=login_payload.get("expireTime"),
            member_id=summary.member_id,
            is_member=summary.is_member,
        )
    except Exception as exc:
        log(f"会员: 查询失败，继续尝试签到 ({exc})", "warn")
        summary.extra_lines.append(f"会员查询异常: {exc}")

    return client


def run_account(
    index: int,
    total: int,
    account: WxAccount,
    wx_client: WechatCodeClient,
    token_cache: TokenCache,
) -> AccountSummary:
    summary = AccountSummary(index=index, label=account.label)
    log(f"======== 账号 {index}/{total}: {account.label} ========")

    try:
        client = ensure_client(account, wx_client, token_cache, summary)
        log(
            f"会员: isMember={summary.is_member} 积分={points_text(summary.before_points)} "
            f"等级={summary.level_name or '-'}"
        )

        try:
            sign_info = client.sign_list()
        except Exception as exc:
            msg = str(exc)
            if summary.is_member is False or looks_like_need_bind_mobile(msg):
                summary.sign_status = "失败(需绑手机)"
                summary.error = f"游客/未绑手机，脚本不做 bindMobile。原始错误: {msg}"
            else:
                summary.sign_status = "失败"
                summary.error = msg
            raise RuntimeError(summary.error) from exc

        summary.today_signed_before = (
            bool(sign_info.get("signToday")) if sign_info.get("signToday") is not None else None
        )
        summary.continuous_day = to_int(sign_info.get("continuousSignDays"))
        log(
            f"签到状态: signToday={summary.today_signed_before} continuous={summary.continuous_day}"
        )

        if summary.today_signed_before:
            summary.sign_status = "今日已签到"
            log("签到: 今日已签到")
        elif DRY_RUN:
            summary.sign_status = "dry-run，未提交签到"
            log("签到: dry-run 跳过提交")
        elif SKIP_SIGN:
            summary.sign_status = "已按 SKIP_SIGN 跳过"
            log("签到: 已按 SKIP_SIGN 跳过")
        else:
            try:
                result = client.sign_in()
                log(f"签到: 提交成功 data={result}")
            except Exception as exc:
                msg = str(exc)
                if summary.is_member is False or looks_like_need_bind_mobile(msg):
                    summary.sign_status = "失败(需绑手机)"
                    summary.error = f"需绑手机后才能签到；脚本不做 bindMobile。原始错误: {msg}"
                else:
                    summary.sign_status = "失败"
                    summary.error = f"签到提交失败: {msg}"
                raise RuntimeError(summary.error) from exc

            time.sleep(1.0)
            try:
                after_sign = client.sign_list()
                summary.today_signed_after = (
                    bool(after_sign.get("signToday"))
                    if after_sign.get("signToday") is not None
                    else None
                )
                summary.continuous_day = to_int(after_sign.get("continuousSignDays"))
            except Exception as exc:
                log(f"签到后状态复查失败: {exc}", "warn")

            if summary.today_signed_after is True:
                summary.sign_status = "签到成功"
            elif summary.today_signed_after is False:
                summary.sign_status = "签到已提交，状态待确认"
            else:
                summary.sign_status = "签到成功"

        try:
            member_after = client.member_base()
            fill_member(summary, member_after, before=False)
            token_cache.set(
                account.wxid,
                client.token,
                member_id=summary.member_id,
                is_member=summary.is_member,
            )
        except Exception as exc:
            log(f"积分复查失败: {exc}", "warn")
            summary.after_points = summary.before_points

        log(f"积分: {points_text(summary.before_points)} -> {points_text(summary.after_points)}")

    except Exception as exc:
        if not summary.error:
            summary.error = str(exc)
        if not summary.sign_status or summary.sign_status == "未执行":
            if looks_like_need_bind_mobile(summary.error) or summary.is_member is False:
                summary.sign_status = "失败(需绑手机)"
            else:
                summary.sign_status = "失败"
        log(f"账号失败: {summary.error}", "error")

    return summary


def load_accounts() -> List[WxAccount]:
    raw = os.getenv("WX_ID") or ""
    return split_accounts(raw)


def build_report(summaries: List[AccountSummary]) -> str:
    blocks = ["\n".join(item.notify_lines()) for item in summaries]
    success_count = sum(1 for item in summaries if item.success)
    header = (
        f"共 {len(summaries)} 个账号，成功 {success_count} 个，"
        f"失败 {len(summaries) - success_count} 个"
    )
    return header + "\n\n" + "\n\n".join(blocks)


def main() -> int:
    accounts = load_accounts()
    if not accounts:
        log("未配置账号环境变量 WX_ID", "error")
        return 1

    wx_client = WechatCodeClient()
    token_cache = TokenCache()

    log(f"脚本: {NOTIFY_TITLE}")
    log(f"AppID: {APP_ID}")
    log(f"账号数: {len(accounts)}")
    log(f"token缓存: {'开启 ' + str(token_cache.path) if token_cache.enabled else '关闭'}")
    log(f"notify: {ENABLE_NOTIFY}, dry-run: {DRY_RUN}, skip-sign: {SKIP_SIGN}")

    summaries: List[AccountSummary] = []
    for index, account in enumerate(accounts, 1):
        summaries.append(run_account(index, len(accounts), account, wx_client, token_cache))
        if index < len(accounts):
            time.sleep(random.uniform(1.0, 2.5))

    report = build_report(summaries)
    print("\n========== 执行汇总 ==========")
    print(report)
    push_notify(NOTIFY_TITLE, report)

    return 0 if any(item.success for item in summaries) else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("用户中断", "warn")
        sys.exit(130)
