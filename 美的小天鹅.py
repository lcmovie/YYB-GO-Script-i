"""
cron: 12 11,17 * * *
小天鹅任务自动化脚本
# name: 美的小天鹅
功能：自动完成小天鹅主任务和召唤精灵任务
环境变量：
  - WX_ID = 多账号分隔，格式：wxid#备注（备注可选，兼容旧变量 mdxte）
    示例：
      wxid_abc123#李四
      wxid_abc123#张三

  - WECHAT_SERVER = 牛子协议地址（可通过 getCode 模块配置）


卖精灵的时候出价应该是你第三个号的积分，买精灵之前把鸡蛋也转换成积分。
"""

import os
import requests
import time
import random
import json
import hashlib
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError

# ========== 配置区 ==========
from getCode import get_single_code

BASE_URL = "https://littleswanmp.midea.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541211) XWEB/16815"
CACHE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()

APPID = os.getenv("APPID", "wx33856a6b31431c6e")

# ========== Token缓存管理 ==========

def get_cache_file_path(wxid):
    """获取缓存文件路径"""
    return os.path.join(CACHE_DIR, "mdxte.json")

def load_token_cache(wxid):
    """从缓存文件加载token"""
    cache_file = get_cache_file_path(wxid)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            pass
            return cache_data
        except Exception as e:
            print(f"  [缓存] 读取缓存文件失败: {e}")
    return None

def save_token_cache(wxid, cache_data):
    """保存token到缓存文件"""
    cache_file = get_cache_file_path(wxid)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [缓存] 保存缓存文件失败: {e}")

def is_token_expired(expires_at):
    """检查token是否过期"""
    if not expires_at:
        return True
    try:
        expire_time = datetime.fromisoformat(expires_at)
        return datetime.now() >= expire_time
    except:
        return True

# ========== UcAccessToken客户端（从get_uc_token.py合并）==========

class UcAccessTokenClient:
    """ucAccessToken 获取客户端"""

    def __init__(self, appid: str):
        self.appid = appid
        self.uc_api_url = "https://mcsp.midea.com/api/cms_bff/mcsp-uc-mvip-bff/app/login/wx/mini/getLoginInfo.do"
        self.code: str = None
        self.uc_access_token: str = None
        self.openid: str = None
        self.unionid: str = None
        self.c4a_uid: str = None

    def get_wx_code(self, wxid: str) -> str:
        """通过 getCode 模块获取微信登录 code"""
        print(f"  [Step 1] 获取微信 code (wxid={wxid}, appid={self.appid})")
        try:
            self.code = get_single_code(self.appid, wxid)
            print(f"  [Step 1] 成功获取 code: {self.code}")
            return self.code
        except Exception as e:
            print(f"  [Step 1] 获取 code 失败: {e}")
            raise

    def get_uc_token(self) -> dict:
        """调用 getUcTokenByJsCode API 获取 ucAccessToken"""
        if not self.code:
            raise Exception("请先调用 get_wx_code() 获取 code")
        print(f"  [Step 2] 调用 getUcTokenByJsCode API")
        payload = {"jsCode": self.code, "platformType": "WX_LS_MINI", "loginMode": 1}
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(self.uc_api_url, json=payload, headers=headers, timeout=30)
            result = response.json()
            if result.get('code') == '000000' and result.get('data'):
                data = result['data']
                self.uc_access_token = data.get('ucAccessToken')
                self.openid = data.get('openId')
                self.unionid = data.get('unionId')
                self.c4a_uid = data.get('c4aUid')
                print(f"  [Step 2] ucAccessToken获取成功")
                return result
            else:
                raise Exception(f"获取 ucAccessToken 失败: {result}")
        except Exception as e:
            print(f"  [Step 2] 获取 ucAccessToken 失败: {e}")
            raise

    def get_token_info(self) -> dict:
        """获取完整的 token 信息"""
        return {
            "ucAccessToken": self.uc_access_token,
            "openId": self.openid,
            "unionId": self.unionid,
            "c4aUid": self.c4a_uid,
            "code": self.code
        }

def get_uc_access_token_by_wxid(wxid: str) -> str:
    """通过wxid获取ucAccessToken（从缓存或重新获取）"""
    cache_data = load_token_cache(wxid)
    if cache_data:
        expires_at = cache_data.get('expires_at')
        if not is_token_expired(expires_at):
            cached_token = cache_data.get('uc_access_token')
            if cached_token:
                return cached_token

    client = UcAccessTokenClient(APPID)
    client.get_wx_code(wxid)
    client.get_uc_token()

    new_cache_data = {
        'uc_access_token': client.uc_access_token,
        'openid': client.openid,
        'unionid': client.unionid,
        'c4a_uid': client.c4a_uid,
        'expires_at': (datetime.now() + timedelta(hours=2)).isoformat(),
        'wxid': wxid,
        'updated_at': datetime.now().isoformat()
    }
    save_token_cache(wxid, new_cache_data)

    return client.uc_access_token

# ========== 工具函数 ==========

def urly(u, h, m="GET", d=None, retries=3, retry_delay=3):
    """通用请求函数"""
    for i in range(retries + 1):
        try:
            mu = m.upper()
            data = None
            if mu in ("POST", "POST_DA") and d is not None:
                if mu == "POST": 
                    data = json.dumps(d).encode('utf-8') if isinstance(d, dict) else (d.encode('utf-8') if isinstance(d, str) else d)
                else: 
                    data = urlencode(d).encode('utf-8') if isinstance(d, dict) else (d.encode('utf-8') if isinstance(d, str) else d)
            req = Request(u, data=data, headers=(h or {}).copy())
            with urlopen(req, timeout=15) as response: 
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            if i < retries: 
                time.sleep(retry_delay)
            else: 
                return None

def get_access_token(uc_access_token):
    """获取access_token"""
    url = f'{BASE_URL}/api/auth/login/uc_token'
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/x-www-form-urlencoded',
        'ucAccessToken': uc_access_token,
    }
    body = {'uc_token': uc_access_token}
    
    res = urly(url, headers, m="POST_DA", d=body)
    if res is None:
        print("❌ 获取access_token请求失败")
        return None
    
    code = res.get('code')
    if code == 200:
        access_token = res.get('content', {}).get('access_token')
        if access_token:
            return access_token
    print("❌ 获取access_token失败")
    return None

# ========== 召唤精灵任务函数 ==========

def hs(uc_access_token, bearer_token):
    """构造精灵任务请求头"""
    return {
        "User-Agent": USER_AGENT,
        'Content-Type': 'application/json',
        'ucAccessToken': uc_access_token,
        'authorization': f'Bearer {bearer_token}',
    }

def get_user_points(uc_access_token, bearer_token):
    """获取用户积分"""
    url = f"{BASE_URL}/api/web/mobile/avatar/getUserPoints"
    headers = hs(uc_access_token, bearer_token)
    res = urly(url, headers, m="POST", d={})
    
    if res and res.get('code') == 200:
        points = res.get('content', 0)
        print(f"  当前积分: {points}")
        return points
    return 0

def rwlb(uc_access_token, bearer_token):
    """新活动 - 任务中心列表"""
    url = f"{BASE_URL}/api/web/mobile/avatarRule/queryPrizeRuleUserComplete"
    headers = hs(uc_access_token, bearer_token)
    body = {"ruleTypeId": "1", "ruleClassId": "2", "seq": 0}
    res = urly(url, headers, m="POST", d=body)
    
    if res and res.get('code') in (0, 200, '0', '200'):
        content = res.get('content', [])
        if isinstance(content, list):
            print(f"  发现 {len(content)} 个任务")
            uncompleted = [task for task in content if not task.get('isUserCompleted')]
            
            for i, task in enumerate(content, 1):
                rule_name = task.get('ruleName')
                completed = '是' if task.get('isUserCompleted') else '否'
                print(f"  [{i}] {rule_name} | {completed}")
            
            for task in uncompleted:
                rid = str(task.get('id'))
                rname = task.get('ruleName', '')
                ti = int(task.get('timeInterval', 0) or 0)
                wait_time = max(1, ti) + random.randint(1, 3)
                
                print(f"  开始任务: {rname}")
                ksrw_tj1(uc_access_token, bearer_token, rid)
                
                if wait_time > 0:
                    time.sleep(wait_time)
                ksrw_dd2(uc_access_token, bearer_token, rid)
        else:
            print("  无任务数据")
    return res

def ksrw_tj1(uc_access_token, bearer_token, rule_id):
    """新活动 - 开始任务第一步"""
    url = f"{BASE_URL}/api/web/mobile/avatarRule/beginTask"
    headers = hs(uc_access_token, bearer_token)
    body = {"ruleId": str(rule_id)}
    urly(url, headers, m="POST", d=body)

def ksrw_dd2(uc_access_token, bearer_token, rule_id):
    """新活动 - 完成任务"""
    url = f"{BASE_URL}/api/web/mobile/avatarRule/completeTask"
    headers = hs(uc_access_token, bearer_token)
    body = {"ruleId": str(rule_id)}
    res = urly(url, headers, m="POST", d=body)
    
    if res and res.get('code') in (0, 200, '0', '200'):
        content = res.get('content', {})
        rule_name = content.get('ruleName', '')
        change_value = content.get('changeValue')
        print(f"  领取成功: {rule_name} -> +{change_value}")

def wan_gain_prize_by_rule(uc_access_token, bearer_token):
    """新活动 - 奖励汇总"""
    url = f"{BASE_URL}/api/web/mobile/avatarRule/userGainPrizeByRule"
    headers = hs(uc_access_token, bearer_token)
    res = urly(url, headers, m="POST", d={})
    
    if res and res.get('code') in (0, 200, '0', '200'):
        content = res.get('content', [])
        if isinstance(content, list):
            for item in content:
                rule_name = item.get('ruleName')
                delta = item.get('changeValue')
                print(f"  [+{delta}] {rule_name}")
        else:
            print("  无额外奖励")

def call_elf(uc_access_token, bearer_token):
    """执行召唤精灵任务"""
    print("\n任务二：召唤精灵任务...")
    rwlb(uc_access_token, bearer_token)
    wan_gain_prize_by_rule(uc_access_token, bearer_token)
    points = get_user_points(uc_access_token, bearer_token)
    print("  召唤精灵任务完成")
    return points

# ========== 小天鹅主任务函数 ==========

def get_swan_info(headers):
    """获取天鹅信息"""
    try:
        response = requests.get(f"{BASE_URL}/api/web/mobile/swan/getSwanByToken", headers=headers, timeout=30)
        result = response.json()
        if result.get('code') == 200:
            swan_info = result.get('content', {})
            return swan_info
    except Exception as e:
        print(f"  获取天鹅信息失败: {e}")
    return None

def auto_feed_grass(headers):
    """自动喂草功能"""
    print("  开始自动喂草...")
    
    swan_info = get_swan_info(headers)
    if not swan_info:
        print("  无法获取天鹅信息，跳过喂草")
        return 0, 0
    
    grass_amount = swan_info.get('grassAmount', 0)
    shell_amount = swan_info.get('shellAmount', 0)
    
    print(f"  当前草数量: {grass_amount}, 当前贝壳数量: {shell_amount}")
    
    if grass_amount <= 0:
        print("  草数量不足，无法喂草")
        return 0, shell_amount
    
    # 计算可喂草次数（最多5次）
    feed_times = min(int(grass_amount), 5)
    print(f"  可喂草次数: {feed_times}")
    
    total_shells_earned = 0
    
    for i in range(feed_times):
        try:
            response = requests.post(
                f"{BASE_URL}/api/web/mobile/swan/feedGrass",
                headers=headers,
                json={},
                timeout=30
            )
            result = response.json()
            
            if result.get('code') == 200:
                content = result.get('content', {})
                new_grass = content.get('grassAmount', 0)
                new_shell = content.get('shellAmount', 0)
                shells_earned = new_shell - shell_amount
                
                if shells_earned > 0:
                    total_shells_earned += shells_earned
                    shell_amount = new_shell
                    print(f"  第{i+1}次喂草成功! 获得贝壳: {shells_earned}, 剩余草: {new_grass}, 总贝壳: {new_shell}")
                else:
                    print(f"  第{i+1}次喂草成功! 剩余草: {new_grass}, 总贝壳: {new_shell}")
            else:
                print(f"  第{i+1}次喂草失败: {result.get('chnDesc', '未知错误')}")
            
            # 喂草间隔
            if i < feed_times - 1:
                time.sleep(1)
                
        except Exception as e:
            print(f"  第{i+1}次喂草请求出错: {e}")
    
    print(f"  ✅ 自动喂草完成! 总共获得贝壳: {total_shells_earned}")
    return total_shells_earned, shell_amount

def exchange_shells(headers, current_shells):
    """兑换功能"""
    if datetime.now().day != 2:
        print(f"  今天不是2号，跳过兑换")
        return 0, current_shells
    
    if current_shells < 2:
        print("  蛋壳数量不足2个，无法兑换")
        return 0, current_shells
    
    exchange_times = current_shells // 2
    total_to_exchange = exchange_times * 2
    
    try:
        requests.post(f"{BASE_URL}/api/web/mobile/swanPageRemainRecord/createRoUpdate",
                     headers=headers, json={"pageName": "货币转化", "type": 1}, timeout=30)
        
        response = requests.post(f"{BASE_URL}/api/web/mobile/swan/resource/shell:exchange",
                               headers=headers, json={"value": total_to_exchange}, timeout=30)
        
        if response.json().get('code') == 200:
            new_shells = current_shells - total_to_exchange
            print(f"  ✅ 兑换成功! 消耗{total_to_exchange}个蛋壳")
            return total_to_exchange, new_shells
    except:
        pass
    return 0, current_shells

def main_swan_task(uc_access_token, bearer_token):
    """执行小天鹅主任务"""
    print("\n任务一：小天鹅任务开始...")
    
    headers = {
        'Content-Type': 'application/json',
        'ucAccessToken': uc_access_token,
        'authorization': f'Bearer {bearer_token}',
        'User-Agent': USER_AGENT
    }

    # 任务模块
    try:
        response = requests.post(f"{BASE_URL}/api/web/mobile/swanPrize/queryPrizeRuleUserComplete",
                               headers=headers, json={"ruleType": "1", "ruleClass": "3"}, timeout=30)
        result = response.json()
        
        if result.get('code') == 200:
            tasks = result.get('content', [])
            uncompleted_tasks = [task for task in tasks if not task.get('isUserCompleted')]
            
            print(f"  获取到 {len(tasks)} 个任务ID")
            print(f"  其中 {len(uncompleted_tasks)} 个任务未完成")
            
            for task in uncompleted_tasks:
                task_id = task.get('id')
                task_name = task.get('ruleName')
                print(f"  处理任务: {task_name}")
                
                try:
                    requests.post(f"{BASE_URL}/api/web/mobile/swanPrize/beginTask",
                                headers=headers, json={"ruleId": task_id}, timeout=30)
                    
                    response = requests.post(f"{BASE_URL}/api/web/mobile/swanPrize/completeTask",
                                           headers=headers, json={"ruleId": task_id}, timeout=30)
                    
                    if response.json().get('code') == 200:
                        content = response.json().get('content', {})
                        prize_name = content.get('prizeName', '未知')
                        change_value = content.get('changeValue', 0)
                        if change_value > 0:
                            print(f"  获得{change_value}个{prize_name}")
                    
                    time.sleep(1)
                except:
                    continue
    except:
        pass

    # 自动喂草
    shells_earned, current_shells = auto_feed_grass(headers)

    # 鸡场工作
    try:
        requests.post(f"{BASE_URL}/api/web/mobile/swanPageRemainRecord/createRoUpdate",
                     headers=headers, json={"pageName": "工作间", "type": 1}, timeout=30)
        
        swan_info = get_swan_info(headers)
        if swan_info:
            print(f"  天鹅昵称: {swan_info.get('swanNick', '未知')}, 贝壳数量: {swan_info.get('shellAmount', 0)}")
            print(f"  开始工作时间: {swan_info.get('startWorkingTime', '未知')}")
        
        requests.post(f"{BASE_URL}/api/web/mobile/swan/userGainWorkPrize", headers=headers, data='{}', timeout=30)
        requests.post(f"{BASE_URL}/api/web/mobile/swan/swanStartWorking", headers=headers, data='{}', timeout=30)
    except:
        pass

    # 兑换功能
    current_shells = swan_info.get('shellAmount', 0) if swan_info else current_shells
    exchange_shells(headers, current_shells)
    
    # 获取最终蛋壳数量
    final_swan_info = get_swan_info(headers)
    final_shells = final_swan_info.get('shellAmount', 0) if final_swan_info else current_shells
    
    print("  小天鹅任务完成")
    return final_shells

# ========== 主程序 ==========

def main():
    """主执行函数"""
    mdxte_raw = os.getenv('WX_ID') or os.getenv('mdxte')
    if not mdxte_raw:
        print("未找到环境变量 WX_ID 或 mdxte")
        return

    raw_lines = []
    for sep in ("\n", "@", "&", "\r\n"):
        if sep in mdxte_raw:
            raw_lines = mdxte_raw.split(sep)
            break
    if not raw_lines:
        raw_lines = [mdxte_raw]

    accounts = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        if '=' in line:
            line = line.split('=', 1)[1].strip()
        if '#' in line:
            wxid, remark = line.split('#', 1)
            accounts.append({'wxid': wxid.strip(), 'remark': remark.strip()})
        else:
            accounts.append({'wxid': line, 'remark': '默认账户'})

    print(f"🌍 从环境变量 WX_ID 加载账号")
    print(f"📊 共发现 {len(accounts)} 个账号")

    account_results = []

    for account_index, account in enumerate(accounts, 1):
        wxid = account['wxid']
        remark = account['remark']
        print(f"\n{'='*40}")
        print(f"[{account_index}/{len(accounts)}] 处理账户: {remark} (wxid={wxid})")
        print(f"{'='*40}")

        uc_access_token = get_uc_access_token_by_wxid(wxid)

        if not uc_access_token:
            print(f"❌ uc_access_token 获取失败，跳过此账户")
            account_results.append({'remark': remark, 'shell_count': 0, 'points': 0})
            continue

        access_token = get_access_token(uc_access_token)

        if access_token:
            shell_count = main_swan_task(uc_access_token, access_token)
            points = call_elf(uc_access_token, access_token)

            account_results.append({'remark': remark, 'shell_count': shell_count, 'points': points})
        else:
            print("❌ access_token 获取失败，跳过此账户")
            account_results.append({'remark': remark, 'shell_count': 0, 'points': 0})

        if account_index < len(accounts):
            wait_time = random.randint(3, 7)
            print(f"\n等待{wait_time}秒后处理下一个账户...")
            time.sleep(wait_time)

    print(f"\n{'='*40}")
    print("📊 任务执行汇总")
    print(f"{'='*40}")
    print(f"{'序号':<4} {'备注':<12} {'蛋壳数':<8} {'积分':<8}")
    print("-" * 40)

    for index, result in enumerate(account_results, 1):
        print(f"{index:<4} {result['remark']:<12} {result['shell_count']:<8} {result['points']:<8}")

    print(f"\n🎉 所有账户处理完成!")

if __name__ == "__main__":
    main()