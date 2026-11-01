"""
name: 飞猪签到
入口: 飞猪微信小程序
功能: 里程签到、现金红包签到、余额满20元提醒手动提现
变量: YYB_SERVER (YYB-Go-Enhanced 地址@微信账号标识，多账号换行分隔)
变量: YYB_API_KEY / YYB_PROTOCOL_TOKEN: 启用协议鉴权时配置，二选一
定时: 每天一次
cron: 16 8 * * *
依赖: requests
作者：lcmovie https://github.com/lcmovie
------------更新日志------------
2026/8/21 V1.0 基于微信小程序 HAR 初始化，接入 YYB-Go-Enhanced 多账号取码
2026/8/21 V1.1 修正飞猪登录成功码为 100，增加登录凭据完整性校验
2026/8/21 V1.2 按 HAR 包装 authorizationCode，补齐普通账号登录参数
2026/11/1 V1.3 更新里程渠道参数，新增红包签到和满20元手动提现提醒
2026/11/1 V1.3.1 签到后重查剩余里程并写入日志和通知
"""

import hashlib
import json
import os
import random
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterator, Optional, Tuple

import requests


APP_ID = "wx6a96c49f29850eb5"
APP_KEY = "12574478"
LOGIN_URL = "https://passport.feizhu.com/mini_program/login.do"
MTOP_BASE = "https://acs-m.feizhu.com/h5"
MILEAGE_GET_API = "mtop.fliggy.ffatouch.mileage.channel.v2024.get"
MILEAGE_SIGN_API = "mtop.fliggy.ffatouch.mileage.channel.v2024.clickcollect"
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.75 NetType/WIFI Language/zh_CN"
)


class FliggyTask:
    def __init__(self) -> None:
        self.logs = []
        self.success_count = 0
        self.failed_count = 0

    def log(self, message: str) -> None:
        print(message)
        self.logs.append(message)

    def accounts(self) -> Iterator[Tuple[str, str]]:
        raw_value = os.getenv("YYB_SERVER", "")
        if not raw_value.strip():
            self.log("❌ 未配置 YYB_SERVER，格式：地址@微信账号标识（多账号换行）")
            return
        for line_no, raw in enumerate(raw_value.splitlines(), 1):
            value = raw.strip()
            if not value:
                continue
            if "@" not in value:
                self.log(f"❌ YYB_SERVER 第 {line_no} 行格式错误，已跳过")
                continue
            server, ref = value.rsplit("@", 1)
            if not server.strip() or not ref.strip():
                self.log(f"❌ YYB_SERVER 第 {line_no} 行地址或账号标识为空，已跳过")
                continue
            yield server.strip(), ref.strip()

    def get_wx_code(self, server: str, ref: str) -> Optional[str]:
        host = server.rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        headers = {
            "Content-Type": "application/json"
        }
        api_key = os.getenv("YYB_API_KEY", "").strip() or os.getenv("YYB_PROTOCOL_TOKEN", "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            response = requests.post(
                f"{host}/wxapp/getCode",
                json={"ref": ref, "app_id": APP_ID},
                timeout=20,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
            code = ((body.get("data") or {}).get("result") or {}).get("code")
            if body.get("code") != 0 or not code:
                self.log(f"❌ 获取微信 code 失败，YYB-Go 响应码：{body.get('code')}")
                return None
            self.log("✅ 获取微信 code 成功")
            return code
        except Exception as exc:
            self.log(f"❌ 获取微信 code 异常：{exc}")
            return None

    def new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh-Hans;q=0.9",
                "Origin": "https://proxy.feizhu.com",
                "Referer": f"https://servicewechat.com/{APP_ID}/475/page-frame.html",
            }
        )
        return session

    def login(self, session: requests.Session, code: str) -> bool:
        authorization = json.dumps(
            {"authorizationCode": code}, ensure_ascii=False, separators=(",", ":")
        )
        payload = {
            "appEntrance": "weixin",
            "appId": "undefined",
            "appName": "trip",
            "authorizationCode": authorization,
            "bizPassParams": "undefined",
            "isMobile": "true",
            "lang": "zh_CN",
            "needPassWebViewCookie": "false",
            "pageTraceId": str(uuid.uuid4()),
            "returnUrl": "",
            "sellerAppId": "",
            "type": "weixin_mini_program",
        }
        try:
            response = session.post(LOGIN_URL, data=payload, timeout=20)
            response.raise_for_status()
            body = response.json()
            content = body.get("content") or {}
            data = content.get("data") or {}
            if body.get("hasError") or not content.get("success") or data.get("resultCode") != 100:
                self.log(
                    "❌ 飞猪登录失败："
                    f"hasError={body.get('hasError')}，"
                    f"contentSuccess={content.get('success')}，"
                    f"contentStatus={content.get('status')}，"
                    f"resultCode={data.get('resultCode')}"
                )
                return False

            if not data.get("cookie2") or not data.get("sgcookie"):
                if data.get("redirect") is True:
                    self.log("❌ 飞猪返回绑定/授权引导，请在微信小程序内完成登录及手机号授权后重试（并非仅凭重定向就能确认未绑手机）")
                else:
                    self.log("❌ 飞猪登录响应缺少 cookie2 或 sgcookie")
                return False

            cookie_map = {
                "cookie2": data.get("cookie2"),
                "sgcookie": data.get("sgcookie"),
                "sid": data.get("sid"),
                "csg": data.get("csg"),
                "unb": data.get("unb"),
                "munb": data.get("munb"),
            }
            for name, value in cookie_map.items():
                if value is not None and value != "":
                    session.cookies.set(name, str(value), domain=".feizhu.com")
                    session.cookies.set(name, str(value), domain=".taobao.com")
            if data.get("sgcookie"):
                session.headers["sgcookie"] = str(data["sgcookie"])
            if data.get("unb"):
                session.headers["x-uid"] = str(data["unb"])
            self.log("✅ 飞猪登录成功")
            return True
        except Exception as exc:
            self.log(f"❌ 飞猪登录异常：{exc}")
            return False

    @staticmethod
    def token_from_cookie(session: requests.Session) -> str:
        cookies = [c for c in session.cookies if c.name == "_m_h5_tk" and "feizhu.com" in c.domain]
        cookies.sort(key=lambda c: (len(c.domain), len(c.path)), reverse=True)
        token_cookie = cookies[0].value if cookies else ""
        return token_cookie.split("_", 1)[0]

    def mtop_request(
        self, session: requests.Session, api: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        data_text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        url = f"{MTOP_BASE}/{api.lower()}/1.0/"
        last_body: Optional[Dict[str, Any]] = None
        for attempt in range(2):
            timestamp = str(int(time.time() * 1000))
            token = self.token_from_cookie(session)
            sign_source = f"{token}&{timestamp}&{APP_KEY}&{data_text}"
            sign = hashlib.md5(sign_source.encode("utf-8")).hexdigest()
            params = {
                "jsv": "2.7.2",
                "appKey": APP_KEY,
                "t": timestamp,
                "sign": sign,
                "api": api,
                "v": "1.0",
                "type": "originaljson",
                "dataType": "json",
                "ttid": "12wechat000002608",
                "data": data_text,
            }
            try:
                response = session.get(url, params=params, timeout=20)
                response.raise_for_status()
                last_body = response.json()
            except Exception as exc:
                self.log(f"❌ MTop 请求异常：{type(exc).__name__}，HTTP={getattr(getattr(exc, 'response', None), 'status_code', None)}")
                return None

            ret = last_body.get("ret") or []
            ret_text = " ".join(str(item) for item in ret)
            if any(key in ret_text for key in ("TOKEN_EMPTY", "TOKEN_EXPIRED", "FAIL_SYS_TOKEN")):
                if attempt == 0 and self.token_from_cookie(session):
                    continue
            return last_body
        return last_body

    @staticmethod
    def is_mtop_success(body: Optional[Dict[str, Any]]) -> bool:
        if not body:
            return False
        return any(str(item).startswith("SUCCESS::") for item in body.get("ret") or [])

    @staticmethod
    def mileage_query() -> Dict[str, Any]:
        return {"channel": "WX", "os": "IOS", "extParams": '{"channelTtid":"12wechat000002608"}', "h5Version": "1.1.28"}

    @staticmethod
    def reason(body) -> str:
        messages = []
        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in ("ret", "errorCode", "errorMessage", "errCode", "errMsg", "failCode", "failMsg", "toastReason", "message") and isinstance(value, (str, int, list)):
                        messages.append(str(value)[:200])
                    elif isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for value in node: walk(value)
        walk(body)
        return "；".join(dict.fromkeys(messages))[:800]

    def sign_in(self, session: requests.Session) -> bool:
        page = self.mtop_request(session, MILEAGE_GET_API, self.mileage_query())
        if not self.is_mtop_success(page):
            ret = (page or {}).get("ret") or []
            self.log(f"❌ [里程] 查询签到状态失败：{' '.join(map(str, ret))}")
            return False

        page_data = (page or {}).get("data") or {}
        sign_module = page_data.get("signInDataModule") or {}
        today = sign_module.get("signInDetailTodayInfoVO") or {}
        if not today:
            today = next((v for v in sign_module.get("signInDetailInfoVOList", []) if v.get("isToday") is True), {})
        if today.get("signInStatus") is True:
            self.log(
                f"✅ [里程] 今日已签到，连续 {today.get('continuousDays', 0)} 天，"
                f"累计 {today.get('cumulativeDays', 0)} 天"
            )
            return True

        bubble_module = page_data.get("bubbleDataModule") or {}
        bubbles = bubble_module.get("bubbleList") or []
        bubble = next((v for v in bubbles if v.get("type") == 1), {})
        static_data = page_data.get("staticDataModule") or {}
        nodes = ((static_data.get("tbCashConfig") or {}).get("actNodeInfos") or [])
        asac = nodes[0].get("asac", "") if nodes else ""
        mileage = today.get("mileage")
        if mileage is None:
            mileage = ((bubble.get("mileageUiConfig") or {}).get("extraParams") or {}).get(
                "mileage", None
            )
        payload = {
            "taoCash": False,
            "doubleMileage": False,
            "channel": "WX",
            "sceneId": bubble_module.get("sceneId"),
            "clickType": 2,
            "playId": sign_module.get("playId") or bubble.get("playId"),
            "taskRecordId": None,
            "currentTimeMillis": int(time.time() * 1000),
            "currentMileage": mileage,
            "asac": asac,
            "issec": "0",
            "isSec": 0,
            "h5Version": "1.1.28",
            "extParams": '{"channelTtid":"12wechat000002608"}',
        }
        if not payload["sceneId"] or not payload["playId"]:
            self.log("❌ [里程] 页面缺少 sceneId 或 playId，未提交签到；页面模块：" + ",".join(page_data.keys()))
            return False

        result = self.mtop_request(session, MILEAGE_SIGN_API, payload)
        if not self.is_mtop_success(result):
            ret = (result or {}).get("ret") or []
            self.log(f"❌ 签到请求失败：{' '.join(map(str, ret))}")
            return False
        result_data = (result or {}).get("data") or {}
        inner = (((result_data.get("clickCollectSignInResult") or {}).get("result")) or {})
        if result_data.get("allSuccess") is True and inner.get("success") is True:
            stats = ((inner.get("resultData") or {}).get("signInStatisticInfo") or {})
            self.log(
                f"✅ [里程] 签到成功，连续 {stats.get('continuousDays', 0)} 天，"
                f"累计 {stats.get('cumulativeDays', 0)} 天"
            )
            return True
        verify = self.mtop_request(session, MILEAGE_GET_API, self.mileage_query())
        verified = ((verify or {}).get("data", {}).get("signInDataModule", {}).get("signInDetailTodayInfoVO") or {})
        if self.is_mtop_success(verify) and verified.get("signInStatus") is True:
            self.log("✅ [里程] 重查确认今日已签到")
            return True
        self.log(
            "❌ 签到业务结果失败，"
            f"allSuccess={result_data.get('allSuccess')}，success={inner.get('success')}；{self.reason(result_data)}"
        )
        return False

    def mileage_balance(self, session):
        """重新读取账户里程，不使用签到前的余额或本次奖励数代替。"""
        page = self.mtop_request(session, MILEAGE_GET_API, self.mileage_query())
        if not self.is_mtop_success(page):
            self.log("⚠️ [里程] 签到后剩余里程：未获取到（余额查询失败）")
            return
        value = page
        for key in ("data", "myMileageModule", "myMileage", "content", "extraParams", "totalUserPoint"):
            value = value.get(key) if isinstance(value, dict) else None
        try:
            balance = Decimal(str(value))
            if not balance.is_finite() or balance < 0 or balance != balance.to_integral_value():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            self.log("⚠️ [里程] 签到后剩余里程：未获取到（余额字段缺失或无效）")
            return
        self.log(f"💰 [里程] 签到后剩余里程：{balance:.0f} 里程")

    def cash_page(self, session):
        body = self.mtop_request(session, "mtop.trip.nm.ssif.pattern.home", {
            "name": "fliggy_saving_center_wx", "bizType": "homepage",
            "version": "1.0.0", "platform": "h5", "h5Version": "1.0.9",
            "args": json.dumps({"_omega_req_section": ["s_vertical_homepage_saving_center_signin_wx", "s_vertical_homepage_saving_center_asset_wx"]}, separators=(",", ":")),
        })
        if not self.is_mtop_success(body):
            self.log("❌ [红包] 页面查询失败：" + self.reason(body))
            return None
        modules = (body.get("data") or {}).get("data") or {}
        def model(name):
            fields = (modules.get(name) or {}).get("fields") or {}
            return fields.get("model") if fields.get("success") is True else None
        sign = model("s_vertical_homepage_saving_center_signin_wx")
        asset = model("s_vertical_homepage_saving_center_asset_wx")
        if not isinstance(sign, dict) or not isinstance(asset, dict) or asset.get("login") is not True:
            self.log("❌ [红包] 未取得已登录的签到及资产模块")
            return None
        return sign, asset

    def cash_balance(self, asset):
        value = (asset.get("cashRedPacket") or {}).get("balance")
        try:
            balance = Decimal(str(value))
            if not balance.is_finite() or balance < 0: raise InvalidOperation
        except (InvalidOperation, ValueError):
            self.log("❌ [红包] 余额字段无效，无法判断提现门槛")
            return False
        self.log(f"💰 [红包] 当前余额：{balance:.2f} 元")
        if balance >= Decimal("20"):
            self.log(f"🔔 [手动提现提醒] 红包余额 {balance:.2f} 元，已达到20元，请打开飞猪微信小程序 → 省钱中心 → 我的资产 → 现金红包，手动提现。")
        return True

    def cash_sign_in(self, session):
        page = self.cash_page(session)
        if page is None: return False
        sign, asset = page
        if sign.get("currentDaySignStatus") is True:
            self.log(f"✅ [红包] 今日已签到，今日金额 {sign.get('todayAmount', 0)} 元")
            return self.cash_balance(asset)
        if not sign.get("taskId") or not sign.get("asac"):
            self.log("❌ [红包] 页面缺少 taskId 或 asac，未提交签到")
            self.cash_balance(asset)
            return False
        result = self.mtop_request(session, "mtop.trip.benefit.signin.execute", {
            "clientType": 1, "taskId": sign["taskId"], "asac": sign["asac"], "h5Version": "1.0.9",
        })
        page = self.cash_page(session)
        if page is None:
            self.log("❌ [红包] 提交后未能重查状态，签到结果待确认")
            self.cash_balance(asset)
            return False
        after, asset = page
        confirmed = after.get("currentDaySignStatus") is True
        if confirmed:
            self.log(f"✅ [红包] 签到后重查成功，今日金额 {after.get('todayAmount', 0)} 元")
        else:
            self.log("❌ [红包] 签到后状态未确认：" + self.reason(result))
        balance_ok = self.cash_balance(asset)
        return confirmed and balance_ok

    def notify(self) -> None:
        title = "飞猪签到"
        content = "\n".join(self.logs)
        try:
            from notify import send

            send(title, content)
            self.log("✅ 青龙通知调用完成")
        except Exception as exc:
            self.log(f"⚠️ 青龙通知未发送：{exc}")

    def run(self) -> int:
        self.log("===== 飞猪签到 V1.3.1：里程 + 现金红包（满20元提醒手动提现） =====")
        account_list = list(self.accounts())
        if not account_list:
            self.failed_count = 1
        for index, (server, ref) in enumerate(account_list, 1):
            self.log(f"\n----- 账号 {index} -----")
            session = self.new_session()
            code = self.get_wx_code(server, ref)
            ok = bool(code) and self.login(session, code)
            if ok:
                time.sleep(random.uniform(1, 2))
                results = []
                for label, action in (("里程", self.sign_in), ("红包", self.cash_sign_in)):
                    try:
                        results.append(action(session))
                    except Exception as exc:
                        self.log(f"❌ [{label}] 处理异常：{type(exc).__name__}，继续另一项任务")
                        results.append(False)
                    if label == "里程":
                        try:
                            self.mileage_balance(session)
                        except Exception as exc:
                            self.log(f"⚠️ [里程] 签到后剩余里程：未获取到（{type(exc).__name__}）")
                mileage_ok, cash_ok = results
                self.log(f"[账号 {index} 汇总] 里程={'成功/已签' if mileage_ok else '失败'}；红包={'成功/已签' if cash_ok else '失败'}")
                ok = mileage_ok and cash_ok
            if ok:
                self.success_count += 1
            else:
                self.failed_count += 1
            time.sleep(random.uniform(1, 2))

        self.log(
            f"\n===== 执行完成：成功 {self.success_count}，失败 {self.failed_count} ====="
        )
        self.notify()
        return 0 if self.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(FliggyTask().run())
