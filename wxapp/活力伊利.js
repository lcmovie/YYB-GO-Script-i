// name:活力伊利
// cron:57 9,16 * * *

/**
 * 活力伊利每日签到任务
 * 变量：
 * 1. WX_ID
 *    格式：wxid#备注
 *    多账号用换行或 @ 分隔（兼容旧变量 wxhlyili）
 * 2. WECHAT_SERVER
 *    协议服务（可选，在 getCode.js 中配置）
 *
 * 逻辑：
 * 1. 读取 hlylck.txt 缓存（格式：token#备注，每行一个）
 * 2. 按备注匹配账号，用缓存 token 验证，有效则跳过 code 登录
 * 3. 缓存失效则走 code → 登录 → 更新缓存
 * 4. 执行每日签到（isUseNewLogic=1）
 * 5. 刷新积分、签到状态并走 sendNotify 通知
 */

const fs = require('fs');
const path = require('path');
const { getSingleCode } = require('./getCode');

const APP_NAME = '活力伊利';
const CACHE_FILE = path.join(__dirname, 'hlylck.txt');
const APPID = 'wx06af0ef532292cd3';
const HOST = 'https://msmarket.msx.digitalyili.com/gateway/api';
const GATEWAY_DOMAIN = 'a1d5c552d-wx06af0ef532292cd3.sh.wxgateway.com';
const MINI_REFERER = `https://servicewechat.com/${APPID}/release/page-frame.html`;
const MOBILE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.58(0x18003a35) NetType/WIFI Language/zh_CN MiniProgramEnv/iOS';
const DEFAULT_SCENE = '1008';
const TENANT_ID = '1559474730809618433';

let notifyMsg = '';

function log(msg) {
  console.log(msg);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function parseAccounts(raw) {
  return String(raw || '')
    .split(/[\n@&\r]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      let x = item;
      if (x.includes('=')) {
        x = x.split('=', 2)[1].trim();
      }
      const parts = x.split('#');
      const wxid = (parts[0] || '').trim();
      const remark = (parts[1] || wxid).trim();
      return { wxid, remark };
    })
    .filter((item) => item.wxid);
}

// ── Token 缓存（hlylck.txt，格式：token#备注，每行一个）──────────────────

function readTokenCache() {
  try {
    const content = fs.readFileSync(CACHE_FILE, 'utf8');
    const map = {};
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const idx = trimmed.indexOf('#');
      if (idx < 1) continue;
      const token = trimmed.slice(0, idx).trim();
      const remark = trimmed.slice(idx + 1).trim();
      if (token && remark) map[remark] = token;
    }
    return map;
  } catch {
    return {};
  }
}

function writeTokenCache(map) {
  const content = Object.entries(map)
    .map(([remark, token]) => `${token}#${remark}`)
    .join('\n');
  fs.writeFileSync(CACHE_FILE, content, 'utf8');
}

// 内存中维护一份，整个运行周期共享
let tokenCache = readTokenCache();

function getCachedToken(remark) {
  return tokenCache[remark] || null;
}

function setCachedToken(remark, token) {
  tokenCache[remark] = token;
  writeTokenCache(tokenCache);
}

function removeCachedToken(remark) {
  delete tokenCache[remark];
  writeTokenCache(tokenCache);
}

function toQueryString(obj = {}) {
  return Object.entries(obj)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&');
}

function parseJsonEnv(name) {
  const raw = String(process.env[name] || '').trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (e) {
    log(`⚠️ ${name} 不是合法 JSON，已忽略: ${e.message}`);
    return {};
  }
}

function createGatewayCallId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function getGatewaySimHeaders() {
  const routeTag = String(process.env.HLYILI_ROUTE_TAG || GATEWAY_DOMAIN);
  const source = String(process.env.HLYILI_WX_SOURCE || 'wx_client');
  const callId = createGatewayCallId();
  const timeoutMs = String(process.env.HLYILI_TIMEOUT_MS || '15000');

  return {
    'X-WX-HTTP-MODE': 'REROUTE',
    'X-WX-CONF-VERSION': '0',
    'x-wx-call-id': callId,
    'x-wx-route-tag': routeTag,
    'x-wx-source': source,
    'x-wx-appid': APPID,
    'x-envoy-expected-rq-timeout-ms': timeoutMs,
  };
}

function buildHeaders(token = '', extra = {}) {
  return {
    Accept: 'application/json, text/plain, */*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Content-Type': 'application/json',
    Origin: 'https://servicewechat.com',
    Referer: MINI_REFERER,
    'User-Agent': MOBILE_UA,
    'access-token': String(token || ''),
    'atv-page': '',
    'forward-appid': '',
    'register-source': '',
    scene: DEFAULT_SCENE,
    'source-type': '',
    'tenant-id': TENANT_ID,
    xweb_xhr: '1',
    ...getGatewaySimHeaders(),
    ...parseJsonEnv('HLYILI_EXTRA_HEADERS_JSON'),
    ...extra,
  };
}

async function requestJson(url, options = {}, timeoutMs = 20_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...options, signal: controller.signal });
    const text = await resp.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
    return { status: resp.status, data, text };
  } finally {
    clearTimeout(timer);
  }
}

function isSuccess(data) {
  return Boolean(data && (data.status === true || data.success === true));
}

function extractErrorMsg(data) {
  if (!data) return '未知错误';
  if (typeof data === 'string') return data;
  if (typeof data.message === 'string' && data.message) return data.message;
  if (typeof data.msg === 'string' && data.msg) return data.msg;
  if (data.error) {
    if (typeof data.error === 'string') return data.error;
    if (typeof data.error.msg === 'string' && data.error.msg) return data.error.msg;
    if (typeof data.error.message === 'string' && data.error.message) return data.error.message;
    if (data.error.code !== undefined) return `错误码 ${data.error.code}`;
  }
  return JSON.stringify(data);
}

function isAlreadyDoneMessage(message) {
  return /已签到|已领取|已完成|今日已|已经|重复/.test(String(message || ''));
}

async function apiRequest(pathname, method = 'GET', token = '', payload = null, extraHeaders = {}) {
  const isGet = method.toUpperCase() === 'GET';
  const query = isGet && payload ? toQueryString(payload) : '';
  const url = `${HOST}${pathname}${query ? `?${query}` : ''}`;
  const options = {
    method,
    headers: buildHeaders(token, extraHeaders),
  };
  if (!isGet) {
    options.body = JSON.stringify(payload ?? {});
  }
  return requestJson(url, options);
}

async function getWxCode(wxid) {
  try {
    return await getSingleCode(APPID, wxid);
  } catch (e) {
    throw new Error(`wx.login失败: ${e.message || e}`);
  }
}

// POST /auth/account/login  { jsCode }
async function loginByCode(code) {
  const { data } = await apiRequest('/auth/account/login', 'POST', '', { jsCode: code });
  return data;
}

// GET /auth/account/user/info
async function getUserInfo(token) {
  const { data } = await apiRequest('/auth/account/user/info', 'GET', token);
  return data;
}

// GET /member/point
async function getScore(token) {
  const { data } = await apiRequest('/member/point', 'GET', token);
  return data;
}

// GET /member/sign/status
async function getSignStatus(token) {
  const { data } = await apiRequest('/member/sign/status', 'GET', token);
  return data;
}

// GET /member/sign/config
async function getSignConfig(token) {
  const { data } = await apiRequest('/member/sign/config', 'GET', token);
  return data;
}

// POST /member/daily/sign?isUseNewLogic=1  — 源码里 signin() 就是这个接口
async function dailySign(token) {
  const { data } = await apiRequest('/member/daily/sign?isUseNewLogic=1', 'POST', token, {});
  return data;
}

function maskMobile(mobile) {
  const text = String(mobile || '');
  return text.replace(/^(\d{3})\d{4}(\d{4})$/, '$1****$2');
}

function formatBonusParts(items = []) {
  return items.filter(Boolean).join('，') || '无';
}

function getDailySignRewardText(config) {
  const daily = config?.dailySignConfig || {};
  const cont = config?.continuousSignConfig || {};
  return {
    daily: formatBonusParts([
      Number(daily.bonusPoint) ? `${daily.bonusPoint}积分` : '',
      Number(daily.bonusGrowth) ? `${daily.bonusGrowth}成长值` : '',
    ]),
    continuous: formatBonusParts([
      Number(cont.bonusPoint) ? `${cont.bonusPoint}积分` : '',
      Number(cont.bonusGrowth) ? `${cont.bonusGrowth}成长值` : '',
    ]),
  };
}

async function runSignTask(token) {
  const beforeStatus = await getSignStatus(token);
  if (!isSuccess(beforeStatus)) {
    throw new Error(`查询签到状态失败: ${extractErrorMsg(beforeStatus)}`);
  }

  const configResp = await getSignConfig(token);
  const rewardText = isSuccess(configResp)
    ? getDailySignRewardText(configResp.data)
    : { daily: '未知', continuous: '未知' };

  if (beforeStatus.data?.signed) {
    return {
      message: '今日已签到',
      signed: true,
      signedDays: Number(beforeStatus.data?.signedDays || 0),
      rewardText,
      changed: false,
    };
  }

  const signResp = await dailySign(token);
  if (!isSuccess(signResp)) {
    const errorMsg = extractErrorMsg(signResp);
    if (isAlreadyDoneMessage(errorMsg)) {
      const afterStatus = await getSignStatus(token);
      return {
        message: '今日已签到',
        signed: Boolean(afterStatus?.data?.signed),
        signedDays: Number(afterStatus?.data?.signedDays || beforeStatus.data?.signedDays || 0),
        rewardText,
        changed: false,
      };
    }
    throw new Error(`签到失败: ${errorMsg}`);
  }

  const daily = signResp.data?.dailySign || {};
  const continuation = signResp.data?.continuationSign || {};
  const messageParts = ['签到成功'];
  if (Number(daily.bonusPoint)) messageParts.push(`+${daily.bonusPoint}积分`);
  if (Number(daily.bonusGrowth)) messageParts.push(`+${daily.bonusGrowth}成长值`);
  if (Number(continuation.bonusPoint)) messageParts.push(`连签额外+${continuation.bonusPoint}积分`);
  if (Number(continuation.bonusGrowth)) messageParts.push(`连签额外+${continuation.bonusGrowth}成长值`);

  const afterStatus = await getSignStatus(token);
  return {
    message: messageParts.join('，'),
    signed: Boolean(afterStatus?.data?.signed),
    signedDays: Number(afterStatus?.data?.signedDays || beforeStatus.data?.signedDays || 0),
    rewardText,
    changed: true,
  };
}

async function runOne(account) {
  log(`\n================ ${account.remark} ================`);

  // 1. 尝试使用缓存 token
  let token = getCachedToken(account.remark);
  if (token) {
    log(`🔑 ${account.remark} 使用缓存 token`);
    const testResp = await getUserInfo(token);
    if (!isSuccess(testResp)) {
      log(`⚠️ ${account.remark} 缓存 token 已失效，重新登录`);
      removeCachedToken(account.remark);
      token = null;
    } else {
      log(`✅ ${account.remark} 缓存 token 有效`);
    }
  }

  // 2. 缓存无效则走 code 登录
  if (!token) {
    log(`🧩 ${account.remark} 使用微信 code 服务登录`);
    const code = await getWxCode(account.wxid);
    const loginResp = await loginByCode(code);
    if (!isSuccess(loginResp) || !loginResp?.data?.accessToken) {
      throw new Error(`登录失败: ${extractErrorMsg(loginResp)}`);
    }
    token = String(loginResp.data.accessToken);
    setCachedToken(account.remark, token);
    log(`💾 ${account.remark} token 已缓存`);
  }

  const [beforeUser, beforeScoreResp] = await Promise.all([
    getUserInfo(token),
    getScore(token),
  ]);

  if (!isSuccess(beforeUser)) {
    throw new Error(`查询用户信息失败: ${extractErrorMsg(beforeUser)}`);
  }
  if (!isSuccess(beforeScoreResp)) {
    throw new Error(`查询积分失败: ${extractErrorMsg(beforeScoreResp)}`);
  }

  const userInfo = beforeUser.data || {};
  const beforeScore = Number(beforeScoreResp.data || 0);

  const signResult = await runSignTask(token);

  const [afterUser, afterScoreResp, afterSignStatus] = await Promise.all([
    getUserInfo(token),
    getScore(token),
    getSignStatus(token),
  ]);

  if (!isSuccess(afterUser)) {
    throw new Error(`刷新用户信息失败: ${extractErrorMsg(afterUser)}`);
  }
  if (!isSuccess(afterScoreResp)) {
    throw new Error(`刷新积分失败: ${extractErrorMsg(afterScoreResp)}`);
  }
  if (!isSuccess(afterSignStatus)) {
    throw new Error(`刷新签到状态失败: ${extractErrorMsg(afterSignStatus)}`);
  }

  const afterInfo = afterUser.data || {};
  const afterScore = Number(afterScoreResp.data || 0);

  const line = [
    `【${account.remark}】${afterInfo.nickname || afterInfo.nickName || userInfo.nickname || userInfo.nickName || ''} ${maskMobile(afterInfo.mobile || userInfo.mobile || '')}`.trim(),
    `签到结果：${signResult.message}`,
    `签到状态：${afterSignStatus.data?.signed ? '已签到' : '未签到'}`,
    `签到天数：${Number(afterSignStatus.data?.signedDays || signResult.signedDays || 0)}`,
    `签到奖励：日签${signResult.rewardText.daily}${signResult.rewardText.continuous !== '无' ? `；连签${signResult.rewardText.continuous}` : ''}`,
    `当前积分：${afterScore}`,
    `积分变化：${beforeScore}->${afterScore}`,
  ].join('\n');

  log(line);
  return line;
}

async function sendNotify(title, content) {
  try {
    const notify = require('../sendNotify');
    await notify.sendNotify(title, content);
  } catch (e) {
    log(`⚠️ 通知发送失败: ${e.message}`);
  }
}

async function main() {
  const rawAccounts = process.env.WX_ID || process.env.wxhlyili || '';
  if (!rawAccounts.trim()) {
    throw new Error('未配置账号变量 WX_ID 或 wxhlyili');
  }

  const accounts = parseAccounts(rawAccounts);
  if (!accounts.length) {
    throw new Error('账号变量解析后为空');
  }

  log(`共 ${accounts.length} 个账号`);

  for (let i = 0; i < accounts.length; i += 1) {
    const account = accounts[i];
    try {
      const line = await runOne(account);
      notifyMsg += `${line}\n\n`;
    } catch (e) {
      const line = `【${account.remark}】失败: ${e.message}`;
      log(line);
      notifyMsg += `${line}\n\n`;
    }

    if (i < accounts.length - 1) {
      const waitSeconds = randomInt(5, 9);
      log(`⏳ ${account.remark} 执行完成，等待 ${waitSeconds} 秒后处理下一个账号`);
      await sleep(waitSeconds * 1000);
    }
  }

  if (notifyMsg.trim()) {
    await sendNotify(APP_NAME, notifyMsg.trim());
  }
}

main().catch((e) => {
  console.error('FATAL:', e && (e.stack || e.message || JSON.stringify(e)));
  process.exit(1);
});
