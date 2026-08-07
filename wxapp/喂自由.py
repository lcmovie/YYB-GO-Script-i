"""
# cron: 16 10,14 * * *
========================================
# name: 喂自由
环境变量配置说明
========================================

必填：
  WX_ID           微信账号，多账号换行或 & 分隔
                  格式：wxid#备注（备注可选）
                  示例：
                    wxid_abc123#李四
                    wxid_abc123#张三
                    wxid_xyz456
                  该变量同时被 getCode 模块用于账号过滤

  （以下变量由共享模块 getCode 读取，按需在青龙环境变量中设置）
  WECHAT_SERVER   牛子协议服务地址（默认 http://192.168.6.222:8011）
  YYB_SERVER      应用宝(YYB) 服务地址（默认 http://127.0.0.1:8000）
  ADMIN_KEY       牛子协议管理密钥（WeChatPadPro/iwechat 需要）
  SERVER_TYPE     强制指定协议：wechat / yyb / auto（默认 auto 智能路由）


选填：
  WZY_SIGN        签到开关
                  0 = 关闭
                  1 = 开启（默认）

  WZY_TASK        做任务开关
                  0 = 关闭
                  1 = 开启（默认）

  WZY_LOTTERY     抽奖开关
                  0 = 关闭
                  1 = 开启（默认）

  WZY_EXCHANGE    自动兑换开关
                  0 = 关闭（默认）
                  1 = 开启，自由金充足时自动兑换商品

  WZY_DRY_RUN     测试模式
                  1 = 只做查询不执行签到/任务/兑换

========================================
"""

import os, time, base64, logging, requests, calendar
from datetime import datetime, timedelta

import getCode  # 共享的微信小程序 code 获取模块（自动路由 牛子/应用宝，读取 WX_ID 过滤）

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

BASE_URL = "https://phapi.nutriciaeln.com.cn"
TOOLS_URL = "https://api.digital4danone.com.cn/babyera/v1"
APPID = "wx75813e4a771649e5"
CA_KEY = "203753385"
VERSION = "1.0"
ACTIVITY_CODE = "MGM_SIGN"

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.75(0x18004b2b) NetType/WIFI "
    "Language/zh_CN"
)

_SIGN_ENABLED = os.environ.get("WZY_SIGN", "1").strip() != "0"
_TASK_ENABLED = os.environ.get("WZY_TASK", "1").strip() != "0"
_LOTTERY_ENABLED = os.environ.get("WZY_LOTTERY", "1").strip() != "0"
_EXCHANGE_ENABLED = os.environ.get("WZY_EXCHANGE", "0").strip() == "1"
_DRY_RUN = os.environ.get("WZY_DRY_RUN", "0").strip() == "1"


def send_notify(title, content):
    try:
        import sys
        sys.path.insert(0, "/ql/data/scripts")
        from notify import send
        send(title, content)
    except ImportError:
        log.warning("未找到青龙面板自带的notify.py，跳过推送")
    except Exception as e:
        log.warning(f"推送失败: {e}")


def is_token_valid(token):
    try:
        p = token.split(".")[1]
        p += "=" * (4 - len(p) % 4)
        payload = base64.b64decode(p).decode()
        import json
        d = json.loads(payload)
        exp = d.get("expireTime", d.get("exp", d.get("expires_in", 0)))
        if exp > 1e12:
            exp = exp / 1000
        return exp > time.time() + 300
    except Exception:
        return False


def get_wx_code(wxid):
    """通过共享 getCode 模块获取登录 code（自动路由 牛子/应用宝，读取 WX_ID 过滤）。"""
    try:
        return getCode.get_single_code(APPID, wxid)
    except Exception as e:
        raise RuntimeError(f"getCode 取 code 失败: {e}")


class WzyClient:
    def __init__(self):
        self.token = ""
        self.token_uuid = ""
        self.token_expir_time = ""
        self.wxid = ""
        self.openid = ""
        self.unionid = ""

    def set_token(self, token, token_uuid="", token_expir_time=""):
        self.token = token
        self.token_uuid = token_uuid
        self.token_expir_time = token_expir_time

    def _build_headers(self, target_type=""):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": UA,
            "Accept-Encoding": "gzip, deflate",
            "x-ca-key": CA_KEY,
            "x-ca-signature-method": "HmacSHA256",
            "x-ca-timestamp": str(int(time.time() * 1000)),
            "x-ca-nonce": "",
            "x-ca-signature": "",
            "x-ca-signature-headers": "x-ca-timestamp,x-ca-key,x-ca-nonce,x-ca-signature-method",
            "version": VERSION,
            "web_id": "",
            "deviceId": "",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if target_type == "tools":
            headers["channel"] = "Parenting-hub"
            headers["x-access-token"] = self.token
            headers["token-uuid"] = self.token_uuid
            headers["token-expir-time"] = self.token_expir_time
        return headers

    def _get_base_url(self, target_type=""):
        if target_type == "tools":
            return TOOLS_URL
        return BASE_URL

    def _request(self, method, pathname, data=None, target_type=""):
        url = f"{self._get_base_url(target_type)}{pathname}"
        headers = self._build_headers(target_type)
        for attempt in range(3):
            try:
                if method.upper() == "GET":
                    resp = requests.get(url, params=data, headers=headers, timeout=15)
                else:
                    resp = requests.post(url, json=data, headers=headers, timeout=15)
                resp.raise_for_status()
                result = resp.json()
                msg = result.get("msg") or ""
                if any(k in msg for k in ["点击过快", "频繁", "操作频率过快"]):
                    wait = 5 + attempt * 3
                    log.warning(f"  限流，等待 {wait}s 后重试 ({attempt+1}/3)")
                    time.sleep(wait)
                    continue
                if result.get("code") not in (200, None) and msg:
                    log.warning(f"  接口返回异常: {result.get('code')} - {msg}")
                return result
            except Exception as e:
                if attempt < 2:
                    log.warning(f"  请求失败，等待重试 ({attempt+1}/3): {e}")
                    time.sleep(3 + attempt)
                    continue
                log.error(f"请求失败 {method} {pathname}: {e}")
                return {"code": -1, "success": False, "message": str(e)}

    def _get(self, pathname, data=None, target_type=""):
        return self._request("GET", pathname, data, target_type)

    def _post(self, pathname, data=None, target_type=""):
        return self._request("POST", pathname, data, target_type)

    def auto_login(self, wxid=""):
        self.wxid = wxid

        log.info("获取登录code...")
        code = get_wx_code(wxid)
        log.info(f"code获取成功: {code[:8]}...")

        log.info("登录...")
        resp = self._post("/auth/v1/miniapp/login", {"code": code, "appid": APPID})
        if resp.get("code") != 200 or not resp.get("data"):
            raise RuntimeError(f"登录失败: {resp.get('msg') or resp}")
        data = resp["data"]
        self.token = data.get("access_token", "")
        self.token_uuid = data.get("uuid", "")
        self.token_expir_time = data.get("expirTime", "")
        self.openid = data.get("openId", "")
        self.unionid = data.get("unionId", "")
        log.info(f"登录成功: token={self.token[:12]}...")
        return {"token": self.token, "crypto_ready": bool(self.token)}

    def get_user_info(self):
        resp = self._get("/user/v1/miniapp/member/my")
        if resp.get("code") == 200:
            data = resp.get("data", {})
            return data.get("member", data) if isinstance(data, dict) else data
        return {}

    def get_user_credit(self):
        resp = self._get("/activity/v1/miniapp/credit/getUserCredit")
        if resp.get("code") == 200:
            data = resp.get("data", {})
            return data.get("credit", 0), data
        return 0, {}

    def get_sign_detail(self):
        resp = self._post(f"/activity/v1/miniapp/sign/{ACTIVITY_CODE}", {})
        return resp.get("data", {}) if resp.get("code") == 200 else {}

    def sign(self):
        resp = self._post(f"/activity/v1/miniapp/sign/sign/{ACTIVITY_CODE}", {})
        return resp

    def get_task_list(self):
        resp = self._post("/activity/v1/miniapp/task/getList", {"pageNum": 1, "pageSize": 20})
        data = resp.get("data", [])
        return data if isinstance(data, list) else data.get("list", []) if isinstance(data, dict) else []

    def finish_task(self, task_code=None, task_id=None, tool_name=None):
        data = {"serialNo": None}
        if task_id is not None:
            data["taskId"] = task_id
        if tool_name is not None:
            data["toolName"] = tool_name
        if task_code and "taskId" not in data:
            data = {"taskCode": task_code}
        resp = self._post("/activity/v1/miniapp/task/finishTask", data)
        return resp

    def get_mot_list(self, code="chanjian_mot"):
        resp = self._post(f"/content/v1/miniapp/content/mot/{code}", {})
        if resp.get("code") == 200:
            data = resp.get("data", [])
            if data and isinstance(data, list) and len(data) > 0:
                cl = data[0].get("collectionList", [])
                result = []
                for c in cl:
                    result.extend(c.get("contentList", []))
                return result
        return []

    def get_equity_task(self):
        resp = self._post("/activity/v1/miniapp/task/equityTask", {})
        return resp.get("data", {}).get("list", []) if resp.get("code") == 200 else []

    def get_goods_list(self, page_num=1, page_size=100):
        resp = self._post("/product/v1/miniapp/goods/list", {
            "pageNum": page_num,
            "pageSize": page_size,
            "sortType": "",
            "sortOrder": "",
            "range": ""
        })
        return resp.get("data", {}).get("list", []) if resp.get("code") == 200 else []

    def get_goods_detail(self, goods_id):
        resp = self._post(f"/product/v1/miniapp/goods/{goods_id}", {"id": goods_id})
        return resp.get("data", {}) if resp.get("code") == 200 else {}

    def exchange_goods(self, goods_info):
        data = {
            "goodsId": goods_info.get("id"),
            "prizeName": goods_info.get("name"),
            "prizeType": goods_info.get("type"),
            "prizeImage": goods_info.get("image"),
            "prizeSource": 2,
            "amount": goods_info.get("exchangeValue"),
            "expirationDays": goods_info.get("expirationDays"),
            "surplusCount": goods_info.get("surplusCount"),
        }
        resp = self._post("/activity/v1/miniapp/lottery/myPrize", data)
        return resp

    def get_lottery_list(self):
        resp = self._post("/activity/v1/miniapp/lottery/list", {})
        return resp.get("data", []) if resp.get("code") == 200 else []

    def lottery(self, activity_code="MGM_ACTIVITY"):
        resp = self._post("/activity/v1/miniapp/lottery/lottery", {"activityCode": activity_code})
        return resp

    def get_lottery_detail(self):
        resp = self._get("/activity/v1/miniapp/lottery/detail")
        return resp.get("data", {}) if resp.get("code") == 200 else {}

    def get_jackpot_list(self):
        resp = self._get("/activity/v1/miniapp/lottery/jackpotList")
        return resp.get("data", []) if resp.get("code") == 200 else []

    def get_my_prize_list(self):
        resp = self._get("/activity/v1/miniapp/lottery/myPrizeList")
        return resp.get("data", []) if resp.get("code") == 200 else []

    def get_rank_detail(self):
        resp = self._get("/activity/v1/miniapp/rank/detail")
        return resp.get("data", {}) if resp.get("code") == 200 else {}

    def get_credit_list(self, page_num=1, page_size=20):
        resp = self._post("/activity/v1/miniapp/credit/list", {
            "pageNum": page_num,
            "pageSize": page_size,
            "status": 1
        })
        return resp.get("data", {}) if resp.get("code") == 200 else {}

    def get_equity_task_home(self):
        resp = self._post("/activity/v1/miniapp/equityTask/home", {})
        return resp.get("data", {}) if resp.get("code") == 200 else {}

    def find_credit_and_four_total(self):
        resp = self._post("/activity/v1/miniapp/equityTask/findCreditAndFourTotal", {})
        return resp.get("data", {}) if resp.get("code") == 200 else {}


def run(client, do_daily=True):
    notify_lines = []

    log.info("获取用户信息...")
    user_info = client.get_user_info()
    nick_name = user_info.get("nickName") or user_info.get("nick_name") or user_info.get("nickname") or user_info.get("name") or user_info.get("memberName") or "用户"
    log.info(f"  昵称: {nick_name}")

    credit, credit_data = client.get_user_credit()
    log.info(f"  自由金: {credit}")

    if not _DRY_RUN:
        if not do_daily:
            try:
                tasks = client.get_task_list()
                pending = sum(1 for t in tasks if t.get("recordStatus", t.get("status", 0)) != 1)
                if pending > 0:
                    log.info(f"检测到 {pending} 个未完成任务，自动执行")
                    do_daily = True
                else:
                    sign_detail = client.get_sign_detail()
                    sign_list = sign_detail.get("signList", [])
                    today_signed = False
                    if sign_list:
                        last = sign_list[-1]
                        today_signed = last.get("status") == 1
                    if not today_signed:
                        log.info("今日未签到，自动执行")
                        do_daily = True
            except Exception:
                pass

    if _DRY_RUN:
        log.info("🧪 测试模式，跳过签到/任务/兑换")
    else:
        if _SIGN_ENABLED:
            log.info("查看签到状态...")
            try:
                sign_detail = client.get_sign_detail()
                continue_days = sign_detail.get("continueDays", 0)
                sign_list = sign_detail.get("signList", [])
                today_signed = False
                if sign_list:
                    last = sign_list[-1]
                    today_signed = last.get("status") == 1
                log.info(f"  已连续签到: {continue_days} 天，今日: {'已签' if today_signed else '未签'}")

                if do_daily and not today_signed:
                    r = client.sign()
                    data = r.get("data", {})
                    code = data.get("code")
                    text = data.get("text", "")
                    value = data.get("value", 0)
                    if r.get("code") == 200:
                        if code == "10002":
                            log.info(f"  签到: {text}")
                        elif code == 200 and value == 1:
                            log.info(f"  签到成功: {text}")
                        else:
                            log.info(f"  签到结果: {text}")
                    else:
                        log.warning(f"  签到失败: {r.get('msg', r)}")
                time.sleep(1)
            except Exception as e:
                log.warning(f"  签到异常: {e}")

        if _TASK_ENABLED:
            log.info("查看任务列表...")
            try:
                tasks = client.get_task_list()
                log.info(f"  共 {len(tasks)} 个任务")

                for task in tasks:
                    task_code = task.get("taskCode")
                    task_name = task.get("title") or task.get("taskName") or task.get("name") or "未知任务"
                    status = task.get("recordStatus", task.get("status", 0))
                    reward = task.get("credit") or task.get("rewardValue") or 0
                    task_id = task.get("id")
                    tag_name_list = task.get("tagNameList", "")
                    done_tags = tag_name_list.split(",") if tag_name_list else []

                    if status == 1:
                        log.info(f"  ✓ {task_name}: 已完成")
                        continue

                    if not do_daily:
                        log.info(f"  ○ {task_name}: 未完成 (今日已执行过任务，跳过)")
                        continue

                    log.info(f"  → {task_name}: 尝试完成 (奖励: {reward}自由金)")
                    try:
                        if task_code == "KNOWLEDGE":
                            mot_codes = ["chanjian_mot", "momdiet_mot", "pregnancy_mot", "weiyang_mot", "changdao_mot", "fushi_mot"]
                            done_count = 0
                            max_count = 3
                            for code in mot_codes:
                                if done_count >= max_count:
                                    break
                                mot_list = client.get_mot_list(code)
                                for mot in mot_list:
                                    if done_count >= max_count:
                                        break
                                    mot_id = mot.get("id")
                                    if str(mot_id) in done_tags or mot_id in done_tags:
                                        continue
                                    log.info(f"    选择知识: {mot.get('title', mot_id)}")
                                    r = client.finish_task(task_id=task_id, tool_name=mot_id)
                                    if r.get("code") == 200:
                                        done_count += 1
                                        log.info(f"    完成成功 ({done_count})")
                                        done_tags.append(str(mot_id))
                                    time.sleep(2)
                            if done_count == 0:
                                log.info(f"    无可用知识内容")
                        elif task_code == "TOOLS":
                            tool_names = ["待产包", "智能配餐", "AR孕期饮食", "喂养规律", "AI时光机"]
                            done_count = 0
                            max_count = 3
                            for tool_name in tool_names:
                                if done_count >= max_count:
                                    break
                                if tool_name in done_tags:
                                    continue
                                r = client.finish_task(task_id=task_id, tool_name=tool_name)
                                code = r.get("code")
                                if code == 200:
                                    done_count += 1
                                    log.info(f"    {tool_name} 完成成功 ({done_count})")
                                    done_tags.append(tool_name)
                                elif code == 300:
                                    log.info(f"    {tool_name} 需要手动完成")
                                else:
                                    log.info(f"    {tool_name} 结果: {r.get('msg', r)}")
                                time.sleep(2)
                        elif task_code == "ZHIXUAN":
                            r = client.finish_task(task_id=task_id)
                            code = r.get("code")
                            if code == 200:
                                log.info(f"    完成成功")
                            elif code == 300:
                                log.info(f"    需要手动完成，跳过")
                            else:
                                log.info(f"    完成结果: {r.get('msg', r)}")
                        else:
                            log.info(f"    需跳转页面完成，跳过")
                    except Exception as e:
                        log.warning(f"    完成任务异常: {e}")
                    time.sleep(2)
            except Exception as e:
                log.warning(f"  任务异常: {e}")

        if _LOTTERY_ENABLED and do_daily:
            log.info("查看抽奖...")
            try:
                detail = client.get_lottery_detail()
                remain = detail.get("remainFreeDrawChance", detail.get("remainCount", 0))
                log.info(f"  剩余免费抽奖次数: {remain}")

                for i in range(remain):
                    try:
                        r = client.lottery()
                        data = r.get("data", {})
                        prize = data.get("prizeName") or data.get("name") or data.get("prize") or str(r)
                        log.info(f"  第{i+1}次抽奖: {prize}")
                    except Exception as e:
                        log.warning(f"  抽奖失败: {e}")
                        break
                    time.sleep(2)
            except Exception as e:
                log.warning(f"  抽奖异常: {e}")

    if _EXCHANGE_ENABLED and credit > 0:
        log.info("检查可兑换商品...")
        try:
            goods = client.get_goods_list()
            exchangeable = [g for g in goods
                          if g.get("exchangeValue", 99999) <= credit
                          and g.get("surplusCount", 0) > 0
                          and g.get("flag") != 1
                          and g.get("buttonStatus") == 1]
            log.info(f"  可兑换商品: {len(exchangeable)} 件 (自由金余额: {credit})")

            exchangeable.sort(key=lambda x: x.get("exchangeValue", 0), reverse=True)
            if exchangeable:
                target = exchangeable[0]
                g_name = target.get("name", "未知商品")
                g_price = target.get("exchangeValue", 0)
                log.info(f"  目标兑换: {g_name} ({g_price}自由金)")
                if not _DRY_RUN:
                    r = client.exchange_goods(target)
                    if r.get("code") == 200:
                        log.info(f"  兑换成功!")
                    else:
                        log.warning(f"  兑换失败: {r.get('msg', r)}")
        except Exception as e:
            log.warning(f"  兑换异常: {e}")

    credit, _ = client.get_user_credit()
    summary = f"自由金: {credit}"
    log.info(f"任务完成 | {summary}")
    notify_lines.append(f"👤 {nick_name}\n{summary}")

    return "\n".join(notify_lines)


if __name__ == "__main__":
    import json as _json
    import pathlib

    WX_SERVER = os.environ.get("WECHAT_SERVER", "")
    WXIDS = []
    for line in os.environ.get("WX_ID", "").replace("&", "\n").splitlines():
        line = line.strip()
        if not line: continue
        if "#" in line:
            wxid, remark = line.split("#", 1)
            WXIDS.append((wxid.strip(), remark.strip()))
        else:
            WXIDS.append((line, line))

    if not WXIDS:
        log.error("未配置环境变量 WX_ID")
        exit(1)

    CACHE_FILE = pathlib.Path(__file__).parent / "wzy_token.json"

    def load_cache():
        try:
            return _json.loads(CACHE_FILE.read_text())
        except Exception:
            return {}

    def save_cache(c):
        CACHE_FILE.write_text(_json.dumps(c, ensure_ascii=False, indent=2))

    cache = load_cache()
    notify_lines = []

    for wxid, remark in WXIDS:
        log.info("=" * 40)
        log.info(f"处理账号: {remark}")
        client = WzyClient()
        cached = cache.get(wxid, {})
        cached_token = cached.get("token", "")
        fresh_login = False
        use_cached = False

        if cached_token:
            expir_time = cached.get("token_expir_time", 0)
            try:
                expir_ts = float(expir_time)
                if expir_ts > 1e12:
                    expir_ts = expir_ts / 1000
                if expir_ts > time.time() + 300:
                    use_cached = True
            except (ValueError, TypeError):
                pass
            if not use_cached and is_token_valid(cached_token):
                use_cached = True

        if use_cached:
            log.info("使用缓存 token")
            client.set_token(
                cached_token,
                cached.get("token_uuid", ""),
                cached.get("token_expir_time", "")
            )
        else:
            if WX_SERVER:
                log.info(f"使用协议服务: {WX_SERVER}")
            log.info("token 无效或已过期，重新登录（通过 getCode 取 code）...")
            try:
                result = client.auto_login(wxid=wxid)
            except Exception as e:
                log.error(f"账号 {remark} 登录异常: {e}，跳过")
                continue
            if not result.get("token"):
                log.error(f"账号 {remark} 登录失败，跳过")
                continue
            fresh_login = True
            cache[wxid] = {
                "token": client.token,
                "token_uuid": client.token_uuid,
                "token_expir_time": client.token_expir_time,
            }
            save_cache(cache)

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            force_daily = os.environ.get("WZY_FORCE_DAILY", "0") == "1"
            do_daily = force_daily or fresh_login or cache.get(wxid + "_daily") != today
            if not do_daily:
                log.info("今日任务已执行过，跳过 (设置 WZY_FORCE_DAILY=1 可强制执行)")
            summary = run(client, do_daily=do_daily)
            notify_lines.append(summary)
            if do_daily:
                cache[wxid + "_daily"] = today
                save_cache(cache)
        except Exception as e:
            log.error(f"账号 {remark} 执行异常: {e}", exc_info=True)
            notify_lines.append(f"👤 {remark}\n❌ 执行异常: {e}")
        time.sleep(5)

    if notify_lines:
        send_notify("喂自由协议", "\n\n".join(notify_lines))
