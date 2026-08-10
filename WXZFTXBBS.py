"""
作者: 临渊
日期: 2025/8/21
name: 微信支付提现笔笔省
入口: 微信小程序 (https://a.c1ns.cn/X3ucP)
功能: 领券、查询
变量: YYB_SERVER (YYB-Go-Enhanced地址@账号ref，多个账号换行分割)
        PROXY_API_URL (代理api，返回一条txt文本，内容为代理ip:端口)
定时: 一天两次
cron: 10 11,12 * * *
------------更新日志------------
2025/8/21   V1.0    初始化脚本
2026/8/7    V2.0    适配YYB-Go-Enhanced及青龙单文件运行
"""

import json
import random
import re
import time
import requests
import os
import base64
import hashlib
import traceback
import ssl
import sys
from datetime import datetime, timedelta

MULTI_ACCOUNT_SPLIT = ["\n", "@"] # 分隔符列表
MULTI_ACCOUNT_PROXY = False # 是否使用多账号代理，默认不使用，True则使用多账号代理
NOTIFY = os.getenv("LY_NOTIFY") or False # 是否推送日志，默认不推送，True则推送

class YYBGoEnhancedAdapter:
    """YYB-Go-Enhanced 的 wx.login code 客户端。"""

    def __init__(self, wx_appid):
        self.wx_appid = wx_appid
        self.log_msgs = []

    def log(self, msg, level="info"):
        self.log_msgs.append(str(msg))
        prefix = {"error": "ERROR", "warning": "WARN"}.get(level, "INFO")
        print(f"[{prefix}] {msg}")

    @staticmethod
    def parse_entry(entry):
        value = str(entry or "").strip()
        if "@" not in value:
            raise ValueError("格式应为 地址@账号ref")
        server, ref = value.rsplit("@", 1)
        server, ref = server.strip().rstrip("/"), ref.strip()
        if not server or not ref:
            raise ValueError("地址和账号ref均不能为空")
        if not server.startswith(("http://", "https://")):
            server = "http://" + server
        return server, ref

    def get_code(self, entry):
        try:
            server, ref = self.parse_entry(entry)
            session = requests.Session()
            session.trust_env = False  # 取码访问Docker内网，不继承青龙代理
            response = session.post(
                f"{server}/wxapp/getCode",
                json={"ref": ref, "app_id": self.wx_appid},
                timeout=20,
            )
            response.raise_for_status()
            body = response.json()
            if response.status_code < 200 or response.status_code >= 300:
                raise RuntimeError(body.get("error") or body.get("msg") or f"HTTP {response.status_code}")
            if "code" in body and body.get("code") not in (0, "0", None):
                raise RuntimeError(body.get("error") or body.get("msg") or "YYB请求失败")
            result = body.get("result")
            if result is None:
                result = (body.get("data") or {}).get("result")
            code = (result or {}).get("code")
            if code:
                self.log(f"[YYB] 账号 {ref} 获取code成功")
                return code
            self.log(f"[YYB] 获取code失败: {str(body)[:300]}", "error")
        except Exception as exc:
            self.log(f"[YYB] 获取code异常: {exc}", "error")
        return None

class TLSAdapter(requests.adapters.HTTPAdapter):
    """
    自定义TLS
    解决unsafe legacy renegotiation disabled
    貌似python太高版本依然会报错
    """
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.options |= 0x4   # <-- the key part here, OP_LEGACY_SERVER_CONNECT
        kwargs["ssl_context"] = ctx
        return super(TLSAdapter, self).init_poolmanager(*args, **kwargs)

class AutoTask:
    def __init__(self, script_name):
        """
        初始化自动任务类
        :param script_name: 脚本名称，用于日志显示
        """
        self.script_name = script_name
        self.proxy_url = os.getenv("PROXY_API_URL") # 代理api，返回一条txt文本，内容为代理ip:端口
        self.wx_appid = "wxdb3c0e388702f785" # 微信小程序id
        self.wechat_code_adapter = YYBGoEnhancedAdapter(self.wx_appid)
        self.host = "discount.wxpapp.wechatpay.cn"
        self.nickname = ""
        self.token = ""
        self.points = 0.00
        self.user_agent = "Mozilla/5.0 (Linux; Android 12; M2012K11AC Build/SKQ1.220303.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/134.0.6998.136 Mobile Safari/537.36 XWEB/1340129 MMWEBSDK/20240301 MMWEBID/9871 MicroMessenger/8.0.48.2580(0x28003036) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android"

    def log(self, msg, level="info"):
        self.wechat_code_adapter.log(msg, level)

    def dict_keys_to_lower(self, obj):
        """
        递归将字典的所有键名转为小写
        """
        if isinstance(obj, dict):
            return {k.lower(): self.dict_keys_to_lower(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.dict_keys_to_lower(i) for i in obj]
        else:
            return obj

    def hide_phone(self, phone):
        """
        隐藏手机号中间4位
        """
        return phone[:3] + "****" + phone[-4:]

    def get_proxy(self):
        """
        获取代理
        :return: 代理
        """
        if not self.proxy_url:
            self.log("[获取代理] 没有找到环境变量PROXY_API_URL，不使用代理", level="warning")
            return None
        url = self.proxy_url
        response = requests.get(url)
        proxy = response.text
        self.log(f"[获取代理] {proxy}")
        return proxy

    def check_proxy(self, proxy, session):
        """
        检查代理
        :param proxy: 代理
        :param session: session
        :return: 是否可用
        """
        try:
            url = f"https://{self.host}/"
            response = session.get(url, timeout=5)
            if response.status_code == 200:
                self.log(f"[检查代理] {proxy} 应该可用")
                return True
            else:
                self.log(f"[检查代理] {response.text}")
                return False
        except Exception as e:
            return False

    def check_env(self):
        """
        检查环境变量
        :return: 环境变量字符串
        """
        try:
            yyb_server = os.getenv("YYB_SERVER", "").strip()
            if not yyb_server:
                self.log("[检查环境变量] 没有找到YYB_SERVER；格式：地址@账号ref，多账号换行", level="error")
                return None
            for entry in yyb_server.splitlines():
                entry = entry.strip()
                if not entry:
                    continue
                try:
                    self.wechat_code_adapter.parse_entry(entry)
                    yield entry
                except ValueError as exc:
                    self.log(f"[检查环境变量] 跳过无效配置 {entry!r}: {exc}", level="error")
        except Exception as e:
            self.log(f"[检查环境变量] 发生错误: {str(e)}\n{traceback.format_exc()}", level="error")
            raise

    def save_account_info(self, account_info):
        """
        保存账号信息
        :param account_info: 账号信息（新获取的列表）
        """
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wxzftxbbs_account_info.json")
        # 读取旧数据
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                old_list = json.load(f)
        else:
            old_list = []
        # 构建 wx_id 到账号的映射，方便查找和更新
        old_dict = {item['wx_id']: item for item in old_list}
        # self.log(f"旧数据: {old_dict}")
        for new_item in account_info:
            old_dict[new_item['wx_id']] = new_item  # 有则更新，无则新增
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(list(old_dict.values()), f, ensure_ascii=False, indent=2)
            self.log(f"保存新数据: 成功")

    def remove_account_info(self, wx_id):
        """
        删除账号信息
        :param wx_id: 微信id
        """
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wxzftxbbs_account_info.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                old_list = json.load(f)
            old_list = [item for item in old_list if item['wx_id'] != wx_id]
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(old_list, f, ensure_ascii=False, indent=2)
            self.log(f"删除账号信息: 成功")

    def load_account_info(self):
        """
        加载账号信息
        :return: 账号信息
        """
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wxzftxbbs_account_info.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                account_info = json.load(f)
            return account_info
        else:
            return []

    def login(self, session, code):
        """
        登录
        :param session: session
        :param code: code
        :return: 登录结果
        """
        try:
            url = f"https://{self.host}/txbbs-user/user/login"
            session.headers['jscode'] = code
            response = session.get(url, timeout=15)
            response_json = response.json()
            time.sleep(random.randint(3, 5))
            if int(response_json['errcode']) == 0:
                self.token = response_json['data']['session_token']
                session.headers['Session-Token'] = self.token
                # self.log(f"[{self.nickname}] 登录成功 获取token: {self.token}")
                return self.token
            else:
                self.log(f"[登录] 失败 错误信息: {response_json.get('msg', '未知错误')}", level="warning")
                return False
        except requests.RequestException as e:
            self.log(f"[登录] 发生网络错误: {str(e)}\n{traceback.format_exc()}", level="error")
            return False
        except Exception as e:
            self.log(f"[登录] 发生错误: {str(e)}\n{traceback.format_exc()}", level="error")
            return False

    def get_balance(self, session):
        """
        获取用户余额
        :param session: session
        :return: 用户余额
        """
        try:
            url = f"https://{self.host}/txbbs-mall/cashoutfree/getbalance"
            response = session.get(url, timeout=15)
            response_json = response.json()
            time.sleep(random.randint(3, 5))
            if int(response_json['errcode']) == 0:
                self.points = int(response_json['data']['balance']) // 100
                return self.points
            else:
                self.log(f"[{self.nickname}] 获取用户余额 发生错误: {response_json.get('msg', '未知错误')}", level="warning")
                return None
        except Exception as e:
            self.log(f"[{self.nickname}] 获取用户余额 发生错误: {str(e)}\n{traceback.format_exc()}", level="error")
            return None

    def get_gifts_list(self, session):
        """
        获取优惠券列表
        :param session: session
        :return: 优惠券列表
        """
        try:
            url = f"https://{self.host}/txbbs-mall/gift/listgifts?longitude=0&latitude=0"
            response = session.get(url, timeout=15)
            response_json = response.json()
            time.sleep(random.randint(3, 5))
            if int(response_json['errcode']) == 0:
                gifts = response_json['data']['gift_info_list']
                return gifts
            else:
                self.log(f"[{self.nickname}] 获取优惠券列表 发生错误: {response_json.get('msg', '未知错误')}", level="warning")
                return []
        except Exception as e:
            self.log(f"[{self.nickname}] 获取优惠券列表 发生错误: {str(e)}\n{traceback.format_exc()}", level="error")
            return []

    def redeem_gift(self, session, gift_id):
        """
        领取优惠券
        :param session: session
        :param gift_id: 优惠券ID
        :return: 领取结果
        """
        try:
            url = f"https://{self.host}/txbbs-mall/gift/redeemgift"
            payload = {"gift_id": gift_id}
            response = session.post(url, json=payload, timeout=15)
            response_json = response.json()
            time.sleep(random.randint(3, 5))
            if int(response_json['errcode']) == 0:
                gift_info = response_json['data']['gift_info']
                gift_name = gift_info.get('coupon_info', {}).get('name', '未知名称')
                self.log(f"[{self.nickname}] 领取优惠券成功: {gift_name}")
                return True
            else:
                error_msg = response_json.get('msg', '领取失败，未获取到具体信息')
                self.log(f"[{self.nickname}] 领取优惠券失败: {error_msg}", level="warning")
                return False
        except Exception as e:
            self.log(f"[{self.nickname}] 领取优惠券发生错误: {str(e)}\n{traceback.format_exc()}", level="error")
            return False

    def run(self):
        """
        运行任务
        """
        try:
            self.log(f"【{self.script_name}】开始执行任务")
            account_info_list = []
            local_account_info = self.load_account_info()
            self.log(f"本地共{len(local_account_info)}个账号")
            entries = self.check_env()
            if entries is None:
                return
            for index, wx_id in enumerate(entries, 1):
                # 清理账号信息
                self.nickname = f"账号{index}"
                self.token = ""
                self.log("")
                self.log(f"------ 账号{index} 开始执行任务 ------")
                session = requests.Session()
                headers = {
                    "User-Agent": self.user_agent,
                    "authority": self.host
                }
                session.headers.update(headers)

                if MULTI_ACCOUNT_PROXY:
                    proxy = self.get_proxy()
                    if proxy:
                        session.proxies.update({"http": f"http://{proxy}", "https": f"http://{proxy}"})
                        # # 检查代理，不可用重新获取
                        # while not self.check_proxy(proxy, session):
                        #     proxy = self.get_proxy()
                        #     session.proxies.update({"http": f"http://{proxy}", "https": f"http://{proxy}"})

                token = None
                # 查找本地账号
                if local_account_info:
                    for info in local_account_info:
                        if info['wx_id'] == wx_id:
                            token = info['token']
                            # self.log(f"[登录] 找到本地token: {token}")
                            break
                # 本地没有则授权获取
                if not token:
                    code = self.wechat_code_adapter.get_code(wx_id)
                    if not code:
                        self.log(f"[{self.nickname}] YYB取码失败，跳过该账号", level="error")
                        session.close()
                        continue
                    token = self.login(session, code)
                    if not token:
                        self.log(f"[{self.nickname}] 登录失败，跳过该账号", level="error")
                        session.close()
                        continue
                    account_info_list.append({"wx_id": wx_id, "token": token})
                else:
                    self.token = token
                    session.headers['Session-Token'] = token
                # 检测token是否有效
                if self.get_balance(session) is None:
                    self.remove_account_info(wx_id)
                    code = self.wechat_code_adapter.get_code(wx_id)
                    if code:
                        token = self.login(session, code)
                        if not token:
                            self.log(f"[{self.nickname}] 重新登录失败，跳过该账号", level="error")
                            session.close()
                            continue
                        account_info_list.append({"wx_id": wx_id, "token": token})
                    else:
                        self.log(f"[{self.nickname}] 授权失败，跳过该账号", level="error")
                        session.close()
                        continue
                # 获取优惠券列表
                gifts_list = self.get_gifts_list(session)
                for gift in gifts_list:
                    if gift.get('gift_type') == 'GT_COUPON' and gift.get('gift_status') == 'GS_AVAILABLE':
                        gift_id = gift.get('gift_id')
                        self.redeem_gift(session, gift_id)
                # 再次获取用户余额
                self.get_balance(session)
                self.log(f"[{self.nickname}] 当前提现免费券: {self.points}元")
                # 清理session
                session.close()
                self.log(f"------ 账号{index} 执行任务结束 ------")
            # 保存新账号信息
            if account_info_list:
                self.save_account_info(account_info_list)
        except Exception as e:
            self.log(f"【{self.script_name}】执行过程中发生错误: {str(e)}\n{traceback.format_exc()}", level="error")
        finally:
            if NOTIFY:
                # 如果notify模块不存在，从远程下载至本地
                if not os.path.exists("notify.py"):
                    url = "https://raw.githubusercontent.com/whyour/qinglong/refs/heads/develop/sample/notify.py"
                    response = requests.get(url)
                    with open("notify.py", "w", encoding="utf-8") as f:
                        f.write(response.text)
                    import notify
                else:
                    import notify
                # 任务结束后推送日志
                title = f"{self.script_name} 运行日志"
                header = "作者：临渊\n"
                content = header + "\n" +"\n".join(self.wechat_code_adapter.log_msgs)
                notify.send(title, content)

if __name__ == "__main__":
    auto_task = AutoTask("微信支付提现笔笔省")
    auto_task.run()
