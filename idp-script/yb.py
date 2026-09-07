#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
# 注册连接：https://www.ybai168.com/#/pages/register/register?invite=HSG54
# 脚本名称: 元宝AI多账户打卡脚本
# 功能描述: 支持多账户自动登录打卡 + 元宝自动回收
# 版本: v2.0
# 日期: 2026-08-22
# 定时任务: cron: 51 8,18 * * *
#
# 环境变量:
#   LOGIN_ACCOUNTS    - 账号#密码&账号#密码
#   PAY_PASSWORD      - 账号#支付密码&账号#支付密码 (建议配置，配置后自动回收)
# ============================================================


import os
import json
import requests
from datetime import datetime
from typing import Optional, Dict
import time
import hashlib
import urllib3
import random
import string
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 配置 ====================
BASE_URL = 'https://admin.ybai168.com'
ENV_ACCOUNTS = 'LOGIN_ACCOUNTS'
ENV_PAY_PASSWORD = 'PAY_PASSWORD'

DATA_DIR = '/ql/data/'
TOKEN_DIR = os.path.join(DATA_DIR, 'tokens')
CHECKIN_LOG_FILE = os.path.join(DATA_DIR, 'multi_checkin_log.json')

MAX_WAIT_TIME = 1800
RETRY_DELAY = 3
RECYCLE_QTY = 1
# ==============================================


def generate_device_id():
    return ''.join(random.choices(string.hexdigits.upper(), k=32))


def get_app_headers(token: str = None, extra: dict = None):
    headers = {
        'user-agent': 'Mozilla/5.0 (Linux; Android 15; 25053RT47C Build/AQ3A.250107.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.181 Mobile Safari/537.36 (Immersed/40.615383) Html5Plus/1.0',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'admin.ybai168.com',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Origin': 'https://admin.ybai168.com',
        'Referer': 'https://admin.ybai168.com/',
        'X-Requested-With': 'XMLHttpRequest'
    }
    if token:
        headers['token'] = token
    if extra:
        headers.update(extra)
    return headers


class AccountManager:
    def __init__(self):
        self.accounts = []
        self.results = []

    def load_accounts_from_env(self) -> bool:
        accounts_str = os.getenv(ENV_ACCOUNTS)
        if not accounts_str:
            print(f'❌ 请设置环境变量 {ENV_ACCOUNTS}')
            print(f'📝 格式: 账号1#密码1&账号2#密码2')
            return False

        for pair in accounts_str.split('&'):
            pair = pair.strip()
            if not pair or '#' not in pair:
                continue
            acc, pwd = pair.split('#', 1)
            acc, pwd = acc.strip(), pwd.strip()
            if acc and pwd:
                self.accounts.append({'account': acc, 'password': pwd})

        if not self.accounts:
            print('❌ 未找到有效账户')
            return False

        print(f'✅ 成功加载 {len(self.accounts)} 个账户')
        for i, acc in enumerate(self.accounts, 1):
            print(f'   {i}. {acc["account"][:3]}****{acc["account"][-4:]}')
        return True

    def get_pay_password(self, account: str) -> Optional[str]:
        config_str = os.getenv(ENV_PAY_PASSWORD, '')
        if not config_str:
            return None

        for item in config_str.split('&'):
            item = item.strip()
            if not item:
                continue
            parts = item.split('#')
            if len(parts) >= 2:
                acc = parts[0].strip()
                pwd = parts[1].strip()
                if acc == account and pwd:
                    return pwd
        return None

    def get_account_md5(self, account: str) -> str:
        return hashlib.md5(account.encode()).hexdigest()[:16]

    def get_token_path(self, account: str) -> str:
        os.makedirs(TOKEN_DIR, exist_ok=True)
        return os.path.join(TOKEN_DIR, f'{self.get_account_md5(account)}.json')

    def add_result(self, account: str, success: bool, msg: str, data: Dict = None):
        self.results.append({
            'account': account,
            'success': success,
            'msg': msg,
            'data': data or {},
            'time': datetime.now().isoformat()
        })


def login(account: str, password: str) -> Optional[str]:
    print(f'  🔑 登录中...')

    url = f'{BASE_URL}/api/account/login'
    data = {
        'account': account,
        'password': password,
        'turnstile_token': ''
    }

    headers = get_app_headers()
    device_id = generate_device_id()
    headers['Device-Id'] = device_id

    try:
        response = requests.post(url, data=data, headers=headers, timeout=30, verify=False)

        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 1 and result.get('data'):
                return result['data']['token']
            else:
                print(f'  ❌ 登录失败: {result.get("msg")}')
                return None
        else:
            print(f'  ❌ HTTP错误: {response.status_code}')
            return None

    except Exception as e:
        print(f'  ❌ 异常: {str(e)[:80]}')
        return None


def checkin(token: str) -> dict:
    url = f'{BASE_URL}/api/checkin/doCheckin'

    headers = get_app_headers(token)
    headers.pop('Content-Type', None)

    try:
        response = requests.post(url, headers=headers, timeout=30, verify=False)
        if response.status_code == 200:
            return response.json()
        else:
            return {'code': -1, 'msg': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'code': -1, 'msg': str(e)[:80]}


def get_recycle_ticket(token: str) -> Optional[str]:
    url = f'{BASE_URL}/api/yuanbao/bootstrap'
    headers = get_app_headers(token)
    headers['Device-Id'] = generate_device_id()

    try:
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        if response.status_code == 200:
            result = response.json()
            if result.get('code') == 1:
                info = result.get('data', {}).get('info', {})
                return info.get('recycle_ticket')
        return None
    except:
        return None


def recycle_submit(token: str, pay_password: str, recycle_ticket: str) -> Optional[Dict]:
    url = f'{BASE_URL}/api/yuanbao/recycleSubmit'
    request_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=20))

    data = {
        'qty': str(RECYCLE_QTY),
        'pay_password': pay_password,
        'recycle_ticket': recycle_ticket,
        'request_id': request_id
    }

    headers = get_app_headers(token)
    headers['Device-Id'] = generate_device_id()

    try:
        response = requests.post(url, data=data, headers=headers, timeout=30, verify=False)
        if response.status_code in [200, 202]:
            result = response.json()
            if result.get('code') == 1:
                return result.get('data', {})
        return None
    except:
        return None


def recycle_check_status(token: str, request_id: str) -> Dict:
    url = f'{BASE_URL}/api/yuanbao/recycleRequestStatus'
    params = {'request_id': request_id}
    headers = get_app_headers(token)

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30, verify=False)
        if response.status_code == 200:
            return response.json()
        return {'code': -1}
    except:
        return {'code': -1}


def wait_with_timer(prefix: str, elapsed: int):
    """动态计时器 - 在同一行更新"""
    sys.stdout.write(f'\r  ⏳ {prefix} {elapsed}s')
    sys.stdout.flush()


def checkin_with_retry(token: str, account: str, account_manager: AccountManager) -> bool:
    """打卡 - 持续重试，动态计时"""
    print('  📌 打卡中...')
    start_time = time.time()

    while True:
        elapsed = int(time.time() - start_time)

        if elapsed > MAX_WAIT_TIME:
            print(f'\n  ❌ 打卡超时{MAX_WAIT_TIME}秒')
            account_manager.add_result(account, False, f'打卡超时{MAX_WAIT_TIME}秒')
            return False

        result = checkin(token)
        code = result.get('code', -1)

        if code == 1:
            data = result.get('data', {})
            print(f'\n  ✅ 打卡成功！连续 {data.get("consecutive", 0)} 天，+{data.get("yuanbao", 0)} 元宝')
            account_manager.add_result(account, True, '打卡成功', data)
            return True

        if code == 0:
            print(f'\n  ℹ️ 今日已打卡')
            account_manager.add_result(account, True, '今日已打卡', {})
            return True

        wait_with_timer(f'打卡重试中...', elapsed)
        time.sleep(RETRY_DELAY)


def recycle_yuanbao(token: str, pay_password: str) -> Dict:
    """回收 - 持续重试，动态计时"""
    print('  ♻️ 回收中...')

    # 1. 获取 recycle_ticket
    start_time = time.time()
    recycle_ticket = None

    while True:
        elapsed = int(time.time() - start_time)

        if elapsed > 60:
            print(f'\n  ❌ 获取凭证超时60秒')
            return {'code': -1, 'msg': '获取凭证超时'}

        recycle_ticket = get_recycle_ticket(token)
        if recycle_ticket:
            print(f'\n  ✅ 获取凭证成功 ({elapsed}s)')
            break

        wait_with_timer('获取凭证中...', elapsed)
        time.sleep(RETRY_DELAY)

    # 2. 提交回收
    start_time = time.time()
    submit_result = None

    while True:
        elapsed = int(time.time() - start_time)

        if elapsed > 60:
            print(f'\n  ❌ 提交回收超时60秒')
            return {'code': -1, 'msg': '提交回收超时'}

        submit_result = recycle_submit(token, pay_password, recycle_ticket)
        if submit_result:
            print(f'\n  ✅ 提交成功 ({elapsed}s)')
            break

        wait_with_timer('提交回收中...', elapsed)
        time.sleep(RETRY_DELAY)

    request_id = submit_result.get('request_id')
    if not request_id:
        return {'code': -1, 'msg': '未获取到请求ID'}

    # 3. 轮询查询状态
    max_checks = 30

    for i in range(max_checks):
        time.sleep(2)

        status_result = recycle_check_status(token, request_id)

        if status_result.get('code') != 1:
            continue

        data = status_result.get('data', {})
        business_status = data.get('business_status', '')

        if business_status == 'done':
            total = data.get('total', 0)
            print(f'\n  ✅ 回收成功，到账 {total} 元')
            return {'code': 1, 'msg': '回收成功', 'data': data}

        status = data.get('status', '')
        if status in ['failed', 'cancelled']:
            print(f'\n  ❌ 回收失败: {data.get("message", "未知错误")}')
            return {'code': -1, 'msg': data.get('message', '回收失败'), 'data': data}

        # 显示状态
        status_text = data.get('status_text', '处理中')
        sys.stdout.write(f'\r  📋 {status_text}... {i+1}/{max_checks}')
        sys.stdout.flush()

    print('\n  ❌ 查询超时')
    return {'code': -1, 'msg': '查询超时'}


def process_account(account: str, password: str, account_manager: AccountManager) -> bool:
    print(f'\n{"="*50}')
    print(f'📱 {account[:3]}****{account[-4:]}')

    token_path = account_manager.get_token_path(account)
    token = None

    if os.path.exists(token_path):
        try:
            with open(token_path, 'r') as f:
                data = json.load(f)
                if data.get('account') == account:
                    expire = data.get('expire_time', 0)
                    if expire - 3600 > datetime.now().timestamp():
                        token = data.get('token')
                        print('  ✅ Token有效')
        except:
            pass

    if not token:
        token = login(account, password)
        if not token:
            account_manager.add_result(account, False, '登录失败')
            return False

        with open(token_path, 'w') as f:
            json.dump({
                'account': account,
                'token': token,
                'expire_time': int(time.time()) + 2592000,
                'nickname': account[:3] + '****' + account[-4:],
                'updated_at': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        print('  💾 Token已保存')

    # 打卡
    if not checkin_with_retry(token, account, account_manager):
        return False

    # 回收
    pay_password = account_manager.get_pay_password(account)
    if pay_password:
        recycle_result = recycle_yuanbao(token, pay_password)
        if recycle_result.get('code') == 1:
            account_manager.add_result(
                account,
                True,
                f'回收成功 {RECYCLE_QTY} 个元宝',
                recycle_result.get('data', {})
            )
        else:
            print(f'  ❌ 回收失败: {recycle_result.get("msg")}')
            account_manager.add_result(account, False, f'回收失败: {recycle_result.get("msg")}')
    else:
        print('  ⏭️ 未配置支付密码，跳过回收')

    return True


def save_summary_log(account_manager: AccountManager):
    os.makedirs(DATA_DIR, exist_ok=True)
    logs = []
    if os.path.exists(CHECKIN_LOG_FILE):
        try:
            with open(CHECKIN_LOG_FILE, 'r') as f:
                logs = json.load(f)
        except:
            pass

    logs.append({
        'date': datetime.now().isoformat(),
        'total': len(account_manager.results),
        'success': sum(1 for r in account_manager.results if r['success']),
        'failed': sum(1 for r in account_manager.results if not r['success']),
        'details': account_manager.results
    })

    with open(CHECKIN_LOG_FILE, 'w') as f:
        json.dump(logs[-30:], f, ensure_ascii=False, indent=2)


def send_notification(account_manager: AccountManager):
    total = len(account_manager.results)
    success = sum(1 for r in account_manager.results if r['success'])
    failed = total - success

    content = f"📊 打卡汇总 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
    content += f"总账户: {total}  ✅成功: {success}  ❌失败: {failed}\n\n"
    content += "📋 详情:\n"
    for i, r in enumerate(account_manager.results, 1):
        status = "✅" if r['success'] else "❌"
        reward = f" (+{r['data']['yuanbao']}元宝)" if r['success'] and r['data'].get('yuanbao') else ""
        content += f"  {i}. {status} {r['account'][:3]}****{r['account'][-4:]}{reward} - {r['msg']}\n"

    print(f'\n📢 {content}')
    try:
        import notify
        sender = getattr(notify, 'send', None) or getattr(notify, 'sendNotify', None)
        if not callable(sender):
            raise AttributeError('notify 模块未提供 send 或 sendNotify 接口')
        sender('元宝AI打卡', content)
    except Exception as exc:
        print(f'⚠️ 通知发送失败（不影响打卡结果）: {exc}')


def show_banner():
    """显示脚本横幅"""
    print('=' * 60)
    print('  元宝AI 多账户打卡脚本 v2.0')
    print('  作者: 柏油马路')
    print('  功能: 自动打卡 + 元宝回收')
    print(f'  时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 60)
    print('  ⏳ 重试时自动计时，不刷屏')
    #print('  ♻️ 配置 PAY_PASSWORD 后自动回收')
    print('=' * 60)


def main():
    show_banner()

    account_manager = AccountManager()
    if not account_manager.load_accounts_from_env():
        return

    print(f'\n🔄 开始处理 {len(account_manager.accounts)} 个账户...')

    for acc in account_manager.accounts:
        try:
            process_account(acc['account'], acc['password'], account_manager)
        except Exception as e:
            print(f'  ❌ 异常: {e}')
            account_manager.add_result(acc['account'], False, f'异常: {str(e)}')

    save_summary_log(account_manager)
    send_notification(account_manager)

    success = sum(1 for r in account_manager.results if r['success'])
    print(f'\n{"="*60}')
    print(f'📊 完成: ✅ {success} 成功, ❌ {len(account_manager.results) - success} 失败')
    print('=' * 60)


if __name__ == '__main__':
    main()
