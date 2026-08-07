// name:每天有乐
// cron:57 9,13 * * *

/**
 * 每天有乐每日签到
 *
 * 变量：
 * 1. WX_ID
 *    格式：wxid#备注
 *    多账号用换行、& 或 @ 分隔
 *    账号来源统一通过 getCode 获取 code（牛子/应用宝双协议）
 *    如需指定协议可配置环境变量 SERVER_TYPE / WECHAT_SERVER / YYB_SERVER
 *
 * 可选变量：
 * - MTYL_TENANT_ID：默认 2
 * - MTYL_TIMEOUT_MS：默认 15000
 * - MTYL_VALIDATE_ONLY=1：只做账号解析自检，不发请求
 * - MTYL_EXTRA_HEADERS_JSON：额外请求头 JSON
 */

const { createHash } = require('crypto');
const fs = require('fs');
const path = require('path');
const dayjs = require('dayjs');
const { getSingleCode } = require('./getCode.js');

const APP_NAME = '每天有乐';
const APPID = 'wxd84920ac8965ee21';
const PAGE_FRAME = '338';
const HOST = 'https://bcportal.app.swirecocacola.com/portal-gateway-prod/portal-applets';
const TENANT_ID = String(process.env.MTYL_TENANT_ID || '2').trim() || '2';
const TIMEOUT_MS = Math.max(5000, Number(process.env.MTYL_TIMEOUT_MS || 15000));
const VALIDATE_ONLY = String(process.env.MTYL_VALIDATE_ONLY || '').trim() === '1';
const MINI_REFERER = `https://servicewechat.com/${APPID}/${PAGE_FRAME}/page-frame.html`;
const MOBILE_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Mac MacWechat/WMPF MacWechat/3.8.7(0x13080712) UnifiedPCMacWechat(0xf264191d) XWEB/19778';

let notifyMsg = '';
let cacheValidityMsgs = [];

function log(msg) {
  console.log(msg);
}

function getLoginCacheFile() {
  return path.join(__dirname, 'json', APP_NAME, 'login_cache.json');
}

function readLoginCache() {
  try {
    const data = JSON.parse(fs.readFileSync(getLoginCacheFile(), 'utf8'));
    return data && typeof data === 'object' ? data : {};
  } catch {
    return {};
  }
}

function writeLoginCache(cache) {
  const file = getLoginCacheFile();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(cache, null, 2));
}

function clearCachedLogin(account) {
  const cache = readLoginCache();
  if (cache[account.wxid]) {
    delete cache[account.wxid];
    writeLoginCache(cache);
  }
}


function formatLoginTime(timestamp) {
  return dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss');
}

function formatCacheDuration(ms) {
  if (!ms || ms <= 0) return '';
  const totalHours = Math.floor(ms / 3600000);
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  if (days > 0) return days + '天' + hours + '小时';
  return hours + '小时';
}

function addCacheValidityMsg(remark, cached) {
  if (!cached) return;
  const lastLoginAt = Number(cached.lastLoginAt || cached.cachedAt || Date.now());
  const elapsed = Math.max(0, Date.now() - lastLoginAt);
  const elapsedText = formatCacheDuration(elapsed) || '0小时';
  const lastLogin = formatLoginTime(lastLoginAt);
  if (cached.minValidityMs) {
    cacheValidityMsgs.push(remark + ' 缓存最小有效期：' + formatCacheDuration(cached.minValidityMs) + '，上次登录：' + lastLogin + '，已持续：' + elapsedText);
  } else {
    cacheValidityMsgs.push(remark + ' 缓存未失效，已持续' + elapsedText + '，上次登录：' + lastLogin);
  }
}

function addNewLoginCacheMsg(remark, cached) {
  if (!cached) return;
  const label = remark || cached.remark || cached.wxid || '账号';
  const lastLoginAt = Number(cached.lastLoginAt || cached.cachedAt || Date.now());
  const lastLogin = formatLoginTime(lastLoginAt);
  const parts = [label + ' 本次已重新登录并写入缓存，上次登录：' + lastLogin];
  if (cached.minValidityMs) parts.push('历史最小有效期：' + formatCacheDuration(cached.minValidityMs));
  cacheValidityMsgs.push(parts.join('，'));
}


function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function md5(text) {
  return createHash('md5').update(String(text)).digest('hex');
}

function mask(text, left = 3, right = 3) {
  const value = String(text || '');
  if (value.length <= left + right) return value;
  return `${value.slice(0, left)}***${value.slice(-right)}`;
}

function parseAccounts(raw) {
  return String(raw || '')
    .split(/[@\n&]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const parts = item.split('#').map((part) => part.trim());
      const wxid = parts[0] || '';
      const remark = parts[1] || wxid;
      return { wxid, remark };
    })
    .filter((item) => item.wxid);
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

function toQueryString(obj = {}) {
  return Object.entries(obj)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&');
}

function buildHeaders(token = '', extra = {}) {
  const headers = {
    Accept: '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Content-Type': 'application/json',
    Referer: MINI_REFERER,
    'User-Agent': MOBILE_UA,
    'X-Requested-With': 'XMLHttpRequest',
    'env-version': 'release',
    xweb_xhr: '1',
    ...parseJsonEnv('MTYL_EXTRA_HEADERS_JSON'),
    ...extra,
  };

  if (token) headers.token = token;
  Object.keys(headers).forEach((key) => {
    if (headers[key] === undefined || headers[key] === null || headers[key] === '') delete headers[key];
  });
  return headers;
}

async function requestJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
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

function extractErrorMsg(data) {
  if (!data) return '未知错误';
  if (typeof data === 'string') return data;
  return String(data.msg || data.message || data.error || JSON.stringify(data));
}

function assertApiOk(resp, action) {
  if (resp.status !== 200) {
    throw new Error(`${action} HTTP ${resp.status}: ${extractErrorMsg(resp.data)}`);
  }
  if (Number(resp.data?.code) !== 200) {
    throw new Error(`${action}失败: ${extractErrorMsg(resp.data)}`);
  }
  return resp.data;
}

async function apiRequest(method, pathname, token = '', payload = null) {
  const upperMethod = method.toUpperCase();
  const isGet = upperMethod === 'GET';
  const query = isGet && payload ? toQueryString(payload) : '';
  const url = `${HOST}${pathname}${query ? `${pathname.includes('?') ? '&' : '?'}${query}` : ''}`;
  const options = {
    method: upperMethod,
    headers: buildHeaders(token),
  };

  if (!isGet) {
    options.body = JSON.stringify(payload ?? {});
  }

  return requestJson(url, options);
}

async function getCodeByWeChatServer(wxid) {
  try {
    return await getSingleCode(APPID, wxid);
  } catch (e) {
    throw new Error(`getCode 取 code 失败: ${e.message || e}`);
  }
}

async function loginByCode(code) {
  const resp = await requestJson(`${HOST}/wechat/userLoginByCode`, {
    method: 'POST',
    headers: buildHeaders('', { token: undefined }),
    body: JSON.stringify({ code, sync: 1 }),
  });
  const data = assertApiOk(resp, '登录').data || {};
  const token = String(data.token || '').trim();
  const openid = String(data.thirdAccount || '').trim();
  const koOpenid = String((data.elseOpenid || []).find((item) => item?.type === 'zfj')?.koOpenid || '').trim();

  if (!token) throw new Error('登录成功但未返回 token');
  if (!openid) throw new Error('登录成功但未返回 openid');
  if (!koOpenid) throw new Error('登录成功但未返回 koOpenid，账号可能未完成每天有乐会员链路');

  return {
    token,
    openid,
    koOpenid,
    memberId: data.memberId,
    phone: data.phone,
  };
}

async function login(account) {
  const code = await getCodeByWeChatServer(account.wxid);
  return loginByCode(code);
}

async function loginWithCache(account) {
  const cache = readLoginCache();
  const cached = cache[account.wxid];
  if (cached?.cred?.token && cached?.cred?.koOpenid) {
    try {
      await getMemberPoint(cached.cred);
      log(`📂 ${account.remark} 使用本地登录缓存`);
      addCacheValidityMsg(cached.remark || cached.wxid || '', cached);
      return cached.cred;
    } catch (e) {
      if (cached && cached.cachedAt) {
        var cachedAtMs = typeof cached.cachedAt === 'string' ? new Date(cached.cachedAt).getTime() : cached.cachedAt;
        if (cachedAtMs) {
          var validityMs = Date.now() - cachedAtMs;
          if (!cached.minValidityMs || validityMs < cached.minValidityMs) {
            var cacheKey = cached.wxid || cached.remark || '';
            if (cacheKey) {
              var cache2 = readLoginCache();
              if (cache2[cacheKey]) {
                cache2[cacheKey].minValidityMs = validityMs;
                writeLoginCache(cache2);
              }
            }
          }
        }
      }
      log(`⚠️ ${account.remark} 本地登录缓存失效: ${e.message || e}`);
      clearCachedLogin(account);
    }
  }

  const cred = await login(account);
  var _prevMin = (account.wxid || {}).minValidityMs || 0;
cache[account.wxid] = {
    wxid: account.wxid,
    remark: account.remark,
    cred,
    cachedAt: new Date().toISOString(),
    lastLoginAt: Date.now(),
    minValidityMs: _prevMin,
  };
  writeLoginCache(cache);
  addNewLoginCacheMsg('', cache[account.wxid]);
  return cred;
}

async function getMemberPoint(cred) {
  const resp = await apiRequest('GET', '/applets/getMemberPoint', cred.token, { details: 1 });
  return assertApiOk(resp, '查询积分').data || {};
}

async function getQuests(cred) {
  const resp = await apiRequest('GET', '/applets/quests/list', cred.token, { tenantId: TENANT_ID });
  return assertApiOk(resp, '查询任务').data || [];
}

async function signIn(cred) {
  const resp = await apiRequest('GET', '/applets/sign', cred.token, { koOpenid: cred.koOpenid });
  return assertApiOk(resp, '签到').data || {};
}

async function recordSign(cred, score) {
  const payload = {
    openid: cred.openid,
    record_no: md5(`${Date.now()}${cred.openid}`),
    interact: '签到有礼',
    action: '签到打卡',
    integral: Number(score) || 1,
  };
  const resp = await apiRequest('POST', '/member_center/api/record', cred.token, payload);
  return assertApiOk(resp, '记录签到行为');
}

function findDailyQuest(quests) {
  return quests.find((item) => item?.tag === 'sign_board') || quests.find((item) => /每日签到|签到/.test(String(item?.name || '')));
}

function formatPoint(pointInfo) {
  const point = pointInfo.point ?? pointInfo.score ?? '-';
  const level = pointInfo.levelName || pointInfo.nextName || '-';
  const exp = pointInfo.exp || '';
  return `积分 ${point}，等级 ${level}${exp ? `，经验 ${exp}` : ''}`;
}

async function runOne(account) {
  const cred = await loginWithCache(account);
  const beforePoint = await getMemberPoint(cred);
  const quests = await getQuests(cred).catch((e) => {
    log(`⚠️ ${account.remark} 查询任务列表失败，继续尝试签到: ${e.message}`);
    return [];
  });
  const dailyQuest = findDailyQuest(quests);

  if (beforePoint.signStatus === true || Number(dailyQuest?.isComplete) === 1) {
    return `【${account.remark}】今日已签到，${formatPoint(beforePoint)}`;
  }

  const signResult = await signIn(cred);
  const score = signResult.score ?? dailyQuest?.score ?? 1;
  await recordSign(cred, score).catch((e) => {
    log(`⚠️ ${account.remark} 签到记录上报失败: ${e.message}`);
  });
  await sleep(randomInt(800, 1500));

  const afterPoint = await getMemberPoint(cred);
  const day = signResult.day ? `，连续 ${signResult.day} 天` : '';
  return `【${account.remark}】签到成功，+${score} 积分${day}，${formatPoint(afterPoint)}`;
}

async function sendNotify(title, content) {
  try {
    const notify = require('./sendNotify');
    await notify.sendNotify(title, content);
  } catch (e) {
    log(`⚠️ 通知发送失败: ${e.message}`);
  }
}

async function validateAccounts(accounts) {
  log('账号解析自检通过：');
  accounts.forEach((account, index) => {
    log(`${index + 1}. remark=${account.remark} | wxid=${mask(account.wxid)}`);
  });
}

async function main() {
  const rawAccounts = String(process.env.WX_ID || '').trim();
  if (!rawAccounts) {
    throw new Error('未配置账号变量 WX_ID');
  }

  const accounts = parseAccounts(rawAccounts);
  if (!accounts.length) {
    throw new Error('账号变量解析后为空');
  }

  if (VALIDATE_ONLY) {
    await validateAccounts(accounts);
    return;
  }

  log(`共 ${accounts.length} 个账号`);

  for (let i = 0; i < accounts.length; i += 1) {
    const account = accounts[i];
    try {
      const result = await runOne(account);
      log(result);
      notifyMsg += `${result}\n\n`;
    } catch (e) {
      const failText = `【${account.remark}】失败：${e.message}`;
      log(failText);
      notifyMsg += `${failText}\n\n`;
    }

    if (i < accounts.length - 1) {
      const waitSeconds = randomInt(5, 10);
      log(`⏳ ${account.remark} 执行完成，等待 ${waitSeconds} 秒后处理下一个账号`);
      await sleep(waitSeconds * 1000);
    }
  }

  if (cacheValidityMsgs.length) {
    notifyMsg += '\n📋 登录缓存有效期：\n' + cacheValidityMsgs.join('\n');
  }
  if (notifyMsg.trim()) {
    await sendNotify(APP_NAME, notifyMsg.trim());
  }
}

main().catch((e) => {
  console.error('FATAL:', e && (e.stack || e.message || JSON.stringify(e)));
  process.exit(1);
});
