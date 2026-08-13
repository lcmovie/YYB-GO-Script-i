# -*- coding: utf-8 -*-
# cron: 30 9,16 * * *
# @Time     : 2025-12-25
# name: 蒙娜丽莎
# @Author   : 凉白开（修订版本）
# @Version  ：5.0
# @Desc     : 蒙娜丽莎小程序：自动获取token → 自动签到，一体化脚本（使用 WX_ID 变量与 getCode 模块）
#             环境变量：
#               - WX_ID: 微信账号ID列表，多账号分割（兼容旧变量 soy_wxid_data）
#               - OCR_SERVER: OCR识别服务地址，例如 http://192.168.6.222:7777
#                 （未配置时默认使用 http://192.168.6.222:7777）

import os
import time
import random
import requests
from getCode import get_single_code

try:
    from notify import send
except ImportError:
    print("未找到 notify.py，将仅在控制台输出日志。")
    def send(title, content):
        print(f"--- 通知 ---\n{title}\n{content}\n-------------")


# ======================================================
#                 第 1 部分：获取 code → tokenStr (使用 WX_ID 与 getCode)
# ======================================================

message_list = []

def get_wxid_list():
    import re
    data = os.getenv("WX_ID", "").strip() or os.getenv("soy_wxid_data", "").strip()
    if not data:
        message_list.append("❌ 环境变量[WX_ID 或 soy_wxid_data]为空！")
        return []
    # 支持换行、&、@、逗号、空格等多种分隔符
    raw_lines = [x.strip() for x in re.split(r'[\n&@,\s]+', data) if x.strip()]
    cleaned = []
    for line in raw_lines:
        if '=' in line:
            line = line.split('=', 1)[1].strip()
        cleaned.append(line)
    return cleaned

def get_code(wxid):
    """用 wxid 换取 code（使用 getCode 模块）"""
    try:
        code = get_single_code("wxce6a8f654e81b7a4", wxid)
        if code:
            print(f"[INFO] wxid[{wxid}] 获取 code 成功")
            return code
    except Exception as e:
        print(f"[ERROR] wxid[{wxid}] 获取 code 失败：{e}")
    return None

def get_customer_token(code):
    """调用 doAction 获取 CustomerID + tokenStr"""
    url = "https://mcs.monalisagroup.com.cn/member/doAction"
    headers = {
    "Host": "mcs.monalisagroup.com.cn",
    "Connection": "keep-alive",
    "xweb_xhr": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090c2d)XWEB/14315",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "*/*",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://servicewechat.com/wxce6a8f654e81b7a4/468/page-frame.html",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9"
}

    data = {
        "brand": "MON",
        "webChatName": "微信用户",
        "telephone": "",
        "code": code,
        "remarks": "",
        "operationType":"",
        "action": "addCustomer",
        "customerName": "微信用户",
        "storeID": "",
        "address": "-",
        "Province": "",
        "City": "",
        "Region": ""
    }
    # r = requests.post(url, headers=headers, data=data, timeout=15).json()
    # print(r)
    try:
        r = requests.post(url, headers=headers, data=data, timeout=15).json()
        # print(r)
        if "tokenStr" in r and r.get("resultInfo"):
            customer_id = r["resultInfo"][0]["CustomerID"]
            tokenStr = r["tokenStr"]
            print(f"[INFO] 获取成功：CustomerID={customer_id} tokenStr={tokenStr}")
            return f"{customer_id}#{tokenStr}"
    except Exception as e:
        print(f"[ERROR] 获取 tokenStr 失败：{e}")

    return None


# ======================================================
#                   第 2 部分：签到模块
# ======================================================
class MNLS:
    def __init__(self, index, account):
        self.index = index
        self.customerId, self.tokenStr = account.split("#")
        self.mobile = ""
        self.score = 0
        self.msg = ""

        self.headers = {
    "Host": "mcs.monalisagroup.com.cn",
    "Connection": "keep-alive",
    "xweb_xhr": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090c2d)XWEB/14315",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "*/*",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://servicewechat.com/wxce6a8f654e81b7a4/468/page-frame.html",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9"
}

    def hide_phone(self, phone):
        if not phone or len(phone) != 11:
            return phone
        return phone[:3] + "****" + phone[7:]

    def get_info(self):
        url = "https://mcs.monalisagroup.com.cn/member/doAction"
        # data = f"brand=MON&customerID={self.customerId}&action=getCustInfoByID"
        data = {
            "brand": "MON",
            "customerID": self.customerId,  # 假设self.customerId已在类中定义
            "action": "getCustInfoByID"
        }
        try:
            r = requests.post(url, headers=self.headers, data=data).json()
            if r.get("status") == 0:
                info = r["resultInfo"][0]
                self.mobile = self.hide_phone(info["Telephone"])
                self.score = info["Integral"]
                print(f"[INFO] 账号{self.index} 信息获取成功：手机号={self.mobile} 积分={self.score}")
                return True
        except Exception as e:
            print(f"[ERROR] 账号{self.index} 获取信息失败：{e}")
        return False

    def getCaptcha(self):
        url = "https://mcs.monalisagroup.com.cn/member/doAction"
        # data = f"brand=MON&action=generateCaptcha&tokenStr={self.tokenStr}"
        data = {
            "brand": "MON",
            "action": "generateCaptcha",
            "tokenStr": self.tokenStr  # 假设self.tokenStr已在类中定义
        }
        n=0
        while n < 3:
            try:
                r = requests.post(url, headers=self.headers, data=data).json()
                # print(r)
                image = r["resultInfo"]
                print(f"[INFO] 账号{self.index} 获取验证码...")
                self.getocr(image)

                # 如果签到成功或已签到，直接返回
                if hasattr(self, 'msg') and ("签到成功" in self.msg or "今天已经签到过了" in self.msg):
                    return
                else:
                    # 签到失败但不是因为验证码问题，可能需要重试
                    n += 1
                    if n < 3:
                        print(f"[INFO] 账号{self.index} 第{n}次重试签到流程...")
                        continue
                    else:
                        break

            except Exception as e:
                n += 1
                if n < 3:
                    print(f"[INFO] 账号{self.index} 第{n}次重试获取验证码...")
                    continue
                else:
                    self.msg = f"重试3次后仍然失败：{e}"
                    print(f"[ERROR] 账号{self.index} {self.msg}")

    def getocr(self,image):
        url = os.getenv("OCR_SERVER", "http://192.168.6.222:7777").rstrip("/") + "/calculate"
        data = {"image": image}
        # OCR服务重试
        ocr_retry = 0
        while ocr_retry < 2:  # OCR最多重试2次
            try:
                res = requests.post(url, json=data).json()
                result = res["result"]
                print(f"[INFO] 账号{self.index} 识别验证码计算结果：{result}")
                self.sign(result)
                return  # OCR成功并签到后直接返回
            except Exception as e:
                ocr_retry += 1
                if ocr_retry < 2:
                    print(f"[INFO] 账号{self.index} OCR识别失败，第{ocr_retry}次重试...")
                    continue
                else:
                    raise Exception(f"OCR识别失败: {e}")

    def sign(self,i):
        url = "https://mcs.monalisagroup.com.cn/member/doAction"
        # data = (
        #     f"brand=MON&action=sign&CustomerID={self.customerId}&CustomerName=%E5%BE%AE%E4%BF%A1%E7%94%A8%E6%88%B7&"
        #     f"StoreID=0&OrganizationID=0&ItemType=002&Brand=MON&tokenStr={self.tokenStr}&correctAnswer={i}"
        # )
        data = {
            "brand": "MON",
            "action": "sign",
            "CustomerID": self.customerId,
            "CustomerName": "微信用户",
            "StoreID": "0",
            "OrganizationID": "0",
            "ItemType": "002",
            "Brand": "MON",
            "tokenStr": self.tokenStr,
            "correctAnswer": i  # 假设i是循环变量或已定义
        }
        try:
            r = requests.post(url, headers=self.headers, data=data).json()
            if r.get("status") == 0:
                self.msg = f"签到成功，获得积分：{r.get('resultInfo')}"
            elif r.get("status") == 7:
                self.msg = "今天已经签到过了"
            else:
                self.msg = f"签到失败：{r}"
            print(f"[INFO] 账号{self.index} 签到状态：{self.msg}")
        except Exception as e:
            self.msg = f"签到异常：{e}"
            print(f"[ERROR] 账号{self.index} 签到异常：{e}")
            raise

    def run(self):
        self.get_info()
        self.getCaptcha()
        # self.sign()
        self.get_info()  # 更新积分
        return f"账号{self.index} → {self.msg}，积分：{self.score}"


# ======================================================
#                   主流程整合
# ======================================================
if __name__ == "__main__":
    wxid_list = get_wxid_list()

    if not wxid_list:
        print("\n".join(message_list))
        exit(0)

    account_list = []

    print("\n===== 开始获取 CustomerID#tokenStr =====")
    for wxid in wxid_list:
        code = get_code(wxid)
        if not code:
            continue
        account = get_customer_token(code)
        print(account)
        if account:
            account_list.append(account)
        time.sleep(random.uniform(1, 2))
    print(account_list)

    if not account_list:
        print("❌ 未获取到任何账号 tokenStr")
        exit(0)

    # ======================================================
    #                     进入自动签到
    # ======================================================
    print("\n===== 开始签到 =====")
    msg_final = []
    for idx, acc in enumerate(account_list, start=1):
        result = MNLS(idx, acc).run()
        msg_final.append(result)
        time.sleep(random.uniform(2, 4))

    # 控制台输出完整日志
    output = "\n".join(message_list + msg_final)
    print(output)

    # 最终推送：只包含签到结果和积分
    send("蒙娜丽莎自动签到结果", "\n".join(msg_final))
