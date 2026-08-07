// name:霖久智服
/** cron: 35 8,17 * * *
霖久智服 微信协议版

变量：
  WECHAT_SERVER  微信协议服务地址，默认 http://192.168.6.222:8011
  WX_ID         微信账号，多账号支持换行、& 分隔，必须配置

WX_ID 格式：
  手机号#wxid#appid#备注
  手机号#wxid#备注
  备注#wxid#appid#手机号
  wxid#备注#手机号
  wxid#备注
  openid#备注          （openid 格式自动走应用宝 yyb，如 owNAX6...#156）


可选：
  LJZF_DELAY_MS          任务间隔毫秒，默认 3000
  LJZF_RUN_NON_POINT     是否执行“去领取/非直接积分”任务，默认 1；填 0 跳过
  LJZF_FORCE_LOGIN       填 1 忽略缓存，每次重新 quickLogin
  LJZF_NOTIFY            通知开关，默认 1；填 0 关闭 sendNotify
*/

const { getSingleCode } = require('./getCode.js');
const getWxCode = (wxid, appid) => getSingleCode(appid, String(wxid).split('#')[0].trim());
const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const zlib = require('zlib');
const crypto = require('crypto');
const { URL } = require('url');

const APP_NAME = '霖久智服';
const NOTIFY_TITLE = '霖久智服_微信协议版';
const API_BASE = 'https://linjiucloud-api.ysservice.com.cn';
const DEFAULT_WECHAT_SERVER = 'http://192.168.6.222:8011';
const DEFAULT_APPID = 'wx0a9f159eddb2c5f8';
const DEFAULT_TENANT_ID = '10111';
const DEFAULT_CLIENT_ID = '64';
const DEFAULT_PAGE_FRAME = '105';
const CACHE_FILE = path.join(__dirname, 'ljzf_wx_cache.json');

const CONFIG = {
  wechatServer: trimRightSlash(process.env.WECHAT_SERVER || DEFAULT_WECHAT_SERVER),
  rawAccounts: process.env.WX_ID || process.env.WX_ID || process.env.WX_ID || '',
  ljzfData: process.env.ljzfData || '',
  delayMs: toInt(process.env.LJZF_DELAY_MS, 3000),
  runNonPoint: process.env.LJZF_RUN_NON_POINT !== '0',
  forceLogin: ['1', 'true', 'yes'].includes(String(process.env.LJZF_FORCE_LOGIN || '').toLowerCase()),
  notify: !['0', 'false', 'off', 'no'].includes(String(process.env.LJZF_NOTIFY || '1').toLowerCase()),
  timeout: toInt(process.env.LJZF_TIMEOUT, 20000),
};

const DEFAULT_UA =
  'Mozilla/5.0 (Linux; Android 14; M2012K11AC Build/UKQ1.230804.001; wv) ' +
  'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/142.0.7444.173 Mobile Safari/537.36 ' +
  'XWEB/1420113 MMWEBSDK/20251006 MMWEBID/2787 MicroMessenger/8.0.66.2980(0x28004279) ' +
  'WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64 MiniProgramEnv/android';

const RSA_PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAgDjIfkejLVzxwxqP29PA
6ugWJmpXPNK7yFHioPJQRTlvI0Cx++95v/0hWTitPqOaGJp6zDu6QdCuAHF/wXVU
HSQQL7tJUCNhBNqe/0CsAaAq2HlAUHTNKB4mg02JmpWZB/lpGSkbgjuF7HBpBd2W
L2xPpyI7E8SaYBzU7RHXtpVWoxLMsP/OvL1HH8N5oMx+Zz1y+OaDIcFG4WMzN17h
o1V/TT3EgdfTirdtxg9usw8xNj9Q3pkafBQT0lnHdzvUjEmZNoP3MBczjy6iZyor
EoT/GbwnNdB2DqTeJmEdEYJ6YFsvIl/XV7YEdy/Cr7ngNK8793lj031zEFx0eb5+
uQIDAQAB
-----END PUBLIC KEY-----`;

const stats = {
  accounts: 0,
  ok: 0,
  fail: 0,
  earned: 0,
  actionEarned: 0,
  totalPoints: 0,
  lines: [],
  accountDetails: [],
  issueCounts: {},
  currentAccount: null,
};

main().catch(async (error) => {
  log(`❌ 脚本异常：${error.stack || error.message || error}`);
  await sendNotifySafe(`${NOTIFY_TITLE}异常`, String(error.stack || error.message || error));
  process.exitCode = 1;
});

async function main() {
  const wxAccounts = parseAccounts(CONFIG.rawAccounts);
  const manualAccounts = parseManualAccounts(CONFIG.ljzfData);
  const accounts = [...wxAccounts, ...manualAccounts];

  if (!accounts.length) throw new Error('未配置 WX_ID 或 ljzfData，请至少填写一项配置');
  wxAccounts
    .filter((account) => !account.mobile)
    .forEach((account) => log(`⚠️ 账号 ${account.remark} 未从变量解析到手机号，将尝试使用 quickLogin/缓存返回的手机号`));
  if (manualAccounts.length) {
    log(`✅ 成功从 ljzfData 读取到 ${manualAccounts.length} 个抓包配置`);
  }

  const cache = loadCache();
  stats.accounts = accounts.length;
  log(`🚀 ${APP_NAME} 微信协议版开始，共 ${accounts.length} 个账号`);
  log(`🌐 WECHAT_SERVER=${CONFIG.wechatServer}`);

  for (let index = 0; index < accounts.length; index += 1) {
    const account = accounts[index];
    log(`\n========== 账号 ${index + 1}/${accounts.length}：${account.remark} ==========`);

    try {
      const auth = await getAuth(account, cache);
      await runAccount(account, auth, cache);
      stats.ok += 1;
    } catch (error) {
      stats.fail += 1;
      const message = `账号 ${account.remark} 失败：${error.message}`;
      log(`❌ ${message}`);
      stats.lines.push(message);
    }

    if (index < accounts.length - 1) await sleep(CONFIG.delayMs);
  }

  const summary = buildNotifySummary();
  log(`\n${summary}`);
  await sendNotifySafe(NOTIFY_TITLE, summary);
}

async function runAccount(account, auth, cache) {
  const detail = {
    remark: account.remark,
    mobile: account.mobile || auth.mobile || '',
    before: null,
    after: null,
    delta: 0,
    deltaSource: 'point',
    actionEarned: 0,
    issues: [],
  };
  stats.currentAccount = detail;

  try {
    detail.before = await safeFetchPoint(account, auth, cache, '开始积分');

    const tasks = await fetchTaskList(account, auth, cache);
    if (!tasks.length) {
      log('ℹ️ 未获取到任务列表');
      return;
    }

    printTaskList(tasks);

    const visibleTasks = tasks.filter((task) => task && task.isShow !== false);
    const orderedTasks = [...visibleTasks].sort((a, b) => {
      const aSign = getTaskType(a) === 'SIGN_IN' ? 0 : 1;
      const bSign = getTaskType(b) === 'SIGN_IN' ? 0 : 1;
      return aSign - bSign;
    });

    let signHandled = false;
    for (let index = 0; index < orderedTasks.length; index += 1) {
      const task = orderedTasks[index];
      const type = getTaskType(task);
      const name = getTaskName(task);

      if (!type) {
        log(`⚠️ 跳过未知任务：${name}`);
        continue;
      }
      if (task.isCompleted === true) {
        log(`✅ 已完成，跳过：${name}`);
        continue;
      }
      if (task.issuedPoints === false && !CONFIG.runNonPoint) {
        log(`ℹ️ 非直接积分任务，已按配置跳过：${name}`);
        continue;
      }

      if (type === 'SIGN_IN') {
        if (signHandled) {
          log(`ℹ️ 签到已处理，跳过重复签到任务：${name}`);
          continue;
        }
        signHandled = true;
        log(`\n📝 签到：${name}`);
        await doAction(account, auth, cache, type, name, '签到');
        await sleep(CONFIG.delayMs);
        continue;
      }

      const progress = getTaskProgress(task);
      const remaining = Math.max(0, progress.max - progress.done);
      if (remaining <= 0) {
        log(`✅ 进度已满，跳过：${name} (${progress.done}/${progress.max})`);
        continue;
      }

      log(`\n🎯 ${name} [${type}] 剩余 ${remaining} 次 (${progress.done}/${progress.max})`);
      for (let count = 1; count <= remaining; count += 1) {
        const serial = progress.done + count;
        const label = `${name} ${serial}/${progress.max}`;
        const result = await doAction(account, auth, cache, type, name, label);

        if (result.reachedLimit) {
          log(`ℹ️ ${name} 已达上限，停止该任务`);
          break;
        }
        if (count < remaining) await sleep(CONFIG.delayMs);
      }

      await sleep(1200);
    }
  } finally {
    detail.after = await safeFetchPoint(account, auth, cache, '结束积分');
    if (Number.isFinite(detail.before) && Number.isFinite(detail.after)) {
      detail.delta = detail.after - detail.before;
    } else {
      detail.delta = detail.actionEarned;
    }
    if (detail.delta === 0 && detail.actionEarned > 0) {
      log(`ℹ️ 积分接口未体现本次变化，按任务接口累计：+${detail.actionEarned}积分`);
      detail.delta = detail.actionEarned;
      detail.deltaSource = 'action';
    }
    stats.earned += detail.delta;
    if (Number.isFinite(detail.after)) stats.totalPoints += detail.after;
    stats.accountDetails.push(detail);
    stats.currentAccount = null;
  }
}

async function getAuth(account, cache) {
  if (account.isManual) {
    log(`🔐 使用抓包配置凭证：token=${mask(account.token)}`);
    return {
      token: account.token,
      accountId: account.accountId,
      sessionKey: account.sessionKey,
      openId: account.openId,
      memberId: account.memberId,
      mobile: account.mobile || '',
      appid: account.appid,
    };
  }

  const cached = normalizeAuth(cache[account.wxid]);
  let useCache = false;
  if (!CONFIG.forceLogin && cached.token && cached.accountId && cached.sessionKey && cached.openId && cached.memberId) {
    const cachedMobile = cached.mobile || '';
    if (account.mobile) {
      // 如果配置了手机号，只有当缓存的手机号未脱敏且完全一致时，才使用缓存
      if (cachedMobile && !cachedMobile.includes('*') && cachedMobile === account.mobile) {
        useCache = true;
      }
    } else {
      // 如果未配置手机号，只要缓存里有手机号（即便脱敏）也允许使用缓存
      if (cachedMobile) {
        useCache = true;
      }
    }
  }

  if (useCache) {
    const finalMobile = account.mobile || cached.mobile || '';
    log(`🔐 使用缓存登录态：token=${mask(cached.token)} mobile=${maskPhone(finalMobile)}`);
    return { ...cached, appid: account.appid, mobile: finalMobile };
  }

  log(`🔐 重新 quickLogin 登录，以获取/刷新指定手机号的正确凭证`);

  const code = await getWxCode(account.wxid, account.appid);
  log(`🔑 获取 jsCode 成功：${mask(code, 5, 4)}`);

  const quick = await quickLogin(account, code);
  let auth = normalizeAuth({ ...cached, ...quick, appid: account.appid });
  auth.mobile = account.mobile || auth.mobile || cached.mobile || '';

  if (!auth.memberId && auth.mobile) {
    const member = await autoMember(account, auth.mobile);
    auth = normalizeAuth({ ...auth, ...member });
    auth.mobile = account.mobile || auth.mobile || cached.mobile || '';
  }

  const missing = ['token', 'accountId', 'sessionKey', 'openId', 'memberId'].filter((key) => !auth[key]);
  if (missing.length) throw new Error(`quickLogin 返回字段不完整：缺少 ${missing.join(', ')}；返回=${safeJson(quick)}`);

  cache[account.wxid] = {
    token: auth.token,
    accountId: auth.accountId,
    sessionKey: auth.sessionKey,
    openId: auth.openId,
    memberId: auth.memberId,
    mobile: account.mobile || auth.mobile || cached.mobile || '',
    remark: account.remark,
    updateTime: new Date().toISOString(),
  };
  saveCache(cache);

  log(`✅ quickLogin 成功：memberId=${auth.memberId} accountId=${mask(auth.accountId, 6, 6)} mobile=${maskPhone(auth.mobile) || '未解析到'}`);
  return auth;
}

async function refreshAuth(account, auth, cache, reason) {
  log(`🔄 ${reason || '登录态失效'}，清理缓存后重新尝试`);
  if (account.isManual) {
    log(`⚠️ 抓包账号凭证已失效，必须重新抓包更新 ljzfData 变量！`);
    throw new Error('抓包凭证已失效');
  }
  if (cache && account.wxid) {
    delete cache[account.wxid];
    saveCache(cache);
  }
  const fresh = await getAuth(account, cache || {});
  Object.assign(auth, fresh);
  return auth;
}

function isAuthExpiredError(error) {
  const message = String(error && error.message ? error.message : error || '');
  return /HTTP 401|登录已过期|token.*过期|unauthorized/i.test(message);
}

async function withAuthRetry(account, auth, cache, action, label) {
  try {
    return await action();
  } catch (error) {
    if (!isAuthExpiredError(error)) throw error;
    await refreshAuth(account, auth, cache, `${label || '请求'}遇到登录过期`);
    return action();
  }
}

// 微信 code 获取已统一走顶部的 getWxCode(getCode.js)，此处旧实现已废弃删除

async function quickLogin(account, jsCode) {
  const body = { appId: account.appid, jsCode, tenantId: DEFAULT_TENANT_ID, skipRequest: true };
  if (account.mobile) body.mobile = account.mobile;

  const data = await apiJson('/base/uniapp/uaa/member/mp/auth/quick', { method: 'POST', account, body });
  if (Number(data.code) !== 0) throw new Error(`quickLogin 失败：${data.message || safeJson(data)}`);
  return extractAuth(data);
}

async function autoMember(account, mobile) {
  const data = await apiJson('/mc/member/autoMember', {
    method: 'POST',
    account,
    body: { channel: 'CHARGE_PLATFORM', tenantId: DEFAULT_TENANT_ID, mobile: String(mobile), skipRequest: true },
  });
  if (Number(data.code) !== 0) throw new Error(`autoMember 失败：${data.message || safeJson(data)}`);
  if (typeof data.data === 'string') return { memberId: data.data, mobile };
  return extractAuth(data);
}

async function fetchTaskList(account, auth, cache) {
  const data = await withAuthRetry(account, auth, cache, () => apiJson('/mt/mini/task/list', {
    method: 'POST',
    account,
    auth,
    body: { memberId: auth.memberId, tenantId: DEFAULT_TENANT_ID },
  }), '获取任务列表');
  if (Number(data.code) !== 0) throw new Error(`获取任务列表失败：${data.message || safeJson(data)}`);
  return Array.isArray(data.data) ? data.data : [];
}

async function doAction(account, auth, cache, actionType, taskName, label) {
  const payload = {
    actionRecordCO: {
      actionType,
      actionUnit: '1',
      channel: 'LJZF',
      createdBy: auth.memberId,
      unitCount: '1',
    },
    tenantId: DEFAULT_TENANT_ID,
  };

  const data = await withAuthRetry(account, auth, cache, () => encryptedAction(account, auth, payload), label);
  if (Number(data.code) === 0) {
    const points = Number(data.data && data.data.pointCount ? data.data.pointCount : 0);
    stats.actionEarned += points;
    if (stats.currentAccount) stats.currentAccount.actionEarned += points;
    log(`✅ ${label} 成功，+${points}积分`);
    return { ok: true, reachedLimit: false };
  }

  const message = data.message || data.msg || '未知错误';
  log(`⚠️ ${label} 失败：${message}`);
  const reachedLimit = /已完成|达到上限|已达上限|超上限|重复/.test(message);
  if (!reachedLimit) addIssue(taskName, message);
  return { ok: false, reachedLimit };
}

async function encryptedAction(account, auth, payload) {
  const encrypted = encryptRequestData({ ...payload, appId: account.appid, sessionKey: auth.sessionKey, openId: auth.openId });
  return apiJson('/mt/web/action/add', {
    method: 'POST',
    account,
    auth,
    headers: { 'X-Nonce': encrypted.nonce, 'X-Timestamp': encrypted.timestamp, 'X-Client-Type': 'mini_program' },
    body: { encryptedKey: encrypted.encryptedKey, encryptedData: encrypted.encryptedData, iv: encrypted.iv },
  });
}

async function safeFetchPoint(account, auth, cache, label) {
  try {
    return await fetchPoint(account, auth, cache, label);
  } catch (error) {
    const message = `积分查询失败：${error.message}`;
    log(`⚠️ ${message}`);
    addIssue(label || '积分查询', message);
    return null;
  }
}

async function fetchPoint(account, auth, cache, label = '当前积分') {
  const mobile = account.mobile || auth.mobile || '';
  if (!mobile) {
    log('ℹ️ 无手机号，跳过积分查询');
    return null;
  }

  log(`💰 ${label}查询手机号：${maskPhone(mobile)}`);
  const url = `/mc/member/memberPoint?mobile=${encodeURIComponent(mobile)}&tenantId=${DEFAULT_TENANT_ID}`;
  const data = await withAuthRetry(account, auth, cache, () => apiJson(url, { method: 'GET', account, auth }), label);
  if (Number(data.code) !== 0) {
    log(`⚠️ 积分查询失败：${data.message || safeJson(data)}`);
    return null;
  }

  const points = Number(data.data && data.data.availablePoints ? data.data.availablePoints : 0);
  log(`💰 ${label}：${points}`);
  return points;
}

function addIssue(taskName, message) {
  const key = `${taskName}：${message}`;
  stats.issueCounts[key] = (stats.issueCounts[key] || 0) + 1;
  if (stats.currentAccount) stats.currentAccount.issues.push(key);
}

function buildNotifySummary() {
  const accountLines = stats.accountDetails.map((item, index) => {
    const before = formatPointValue(item.before);
    const after = formatPointValue(item.after);
    const source = item.deltaSource === 'action' ? '（任务接口累计）' : '';
    return `${index + 1}. ${item.remark}：${before} -> ${after}，增加${formatDelta(item.delta)}积分${source}`;
  });

  const issueLines = Object.entries(stats.issueCounts).map(([message, count]) => {
    return `- ${message}${count > 1 ? ` ×${count}` : ''}`;
  });

  const lines = [
    `${NOTIFY_TITLE}执行完成`,
    `账号：成功 ${stats.ok}/${stats.accounts}，失败 ${stats.fail}`,
    `本次跑完增加：${formatDelta(stats.earned)} 积分`,
    `账户总积分合计：${stats.totalPoints}`,
    '',
    '各账号积分：',
    ...(accountLines.length ? accountLines : ['暂无账号积分明细']),
  ];

  if (stats.lines.length) {
    lines.push('', '账号异常：', ...stats.lines.map((item) => `- ${item}`));
  }

  if (issueLines.length) {
    lines.push('', '任务异常汇总：', ...issueLines);
  }

  return lines.join('\n');
}

function formatPointValue(value) {
  return Number.isFinite(value) ? `${value}` : '未知';
}

function formatDelta(value) {
  if (!Number.isFinite(value)) return '未知';
  return value > 0 ? `+${value}` : `${value}`;
}

function apiJson(pathname, options = {}) {
  const account = options.account || {};
  const auth = options.auth || {};
  const url = new URL(pathname, API_BASE);
  const headers = { ...baseHeaders(account), ...(options.headers || {}) };
  if (auth.token) headers['X-Auth-Token'] = auth.token;
  if (auth.accountId) headers['X-Account-Id'] = auth.accountId;
  headers['X-Project-id'] = '';

  let body;
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  return requestJson(url, { method: options.method || (body ? 'POST' : 'GET'), headers, body });
}

function requestJson(urlInput, options = {}) {
  return requestRaw(urlInput, options).then((response) => {
    const text = response.body.toString('utf8');
    try {
      return text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`响应不是 JSON：${shortText(text)}`);
    }
  });
}

function requestRaw(urlInput, options = {}) {
  const url = urlInput instanceof URL ? urlInput : new URL(urlInput);
  const client = url.protocol === 'https:' ? https : http;
  const bodyBuffer = options.body === undefined ? null : Buffer.from(String(options.body), 'utf8');
  const headers = { ...(options.headers || {}) };
  if (bodyBuffer && !headers['Content-Length']) headers['Content-Length'] = bodyBuffer.length;

  return new Promise((resolve, reject) => {
    const req = client.request(
      url,
      { method: options.method || (bodyBuffer ? 'POST' : 'GET'), headers, timeout: CONFIG.timeout, rejectUnauthorized: false },
      (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => {
          try {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
              resolve(requestRaw(new URL(res.headers.location, url), options));
              return;
            }
            const body = decodeBody(Buffer.concat(chunks), res.headers['content-encoding']);
            if (res.statusCode < 200 || res.statusCode >= 300) {
              reject(new Error(`HTTP ${res.statusCode}：${shortText(body.toString('utf8'))}`));
              return;
            }
            resolve({ statusCode: res.statusCode, headers: res.headers, body });
          } catch (error) {
            reject(error);
          }
        });
      },
    );
    req.on('timeout', () => req.destroy(new Error(`请求超时：${CONFIG.timeout}ms`)));
    req.on('error', reject);
    if (bodyBuffer) req.write(bodyBuffer);
    req.end();
  });
}

function baseHeaders(account = {}) {
  return {
    Host: 'linjiucloud-api.ysservice.com.cn',
    xweb_xhr: '1',
    'X-Client-Id': DEFAULT_CLIENT_ID,
    'X-Tenant-Id': DEFAULT_TENANT_ID,
    'X-Client-Type': 'mini_program',
    Referer: `https://servicewechat.com/${account.appid || DEFAULT_APPID}/${DEFAULT_PAGE_FRAME}/page-frame.html`,
    Accept: '*/*',
    'Accept-Encoding': 'gzip, deflate, br',
    'User-Agent': account.ua || DEFAULT_UA,
    Connection: 'keep-alive',
    'Content-Type': 'application/json',
  };
}

function encryptRequestData(data) {
  const key = randomString(32);
  const iv = randomString(16);
  const keyBuffer = Buffer.from(key, 'utf8');
  const ivBuffer = Buffer.from(iv, 'utf8');
  const cipher = crypto.createCipheriv('aes-256-cbc', keyBuffer, ivBuffer);
  let encryptedData = cipher.update(JSON.stringify(data), 'utf8', 'base64');
  encryptedData += cipher.final('base64');
  const encryptedKey = crypto.publicEncrypt(
    { key: RSA_PUBLIC_KEY, padding: crypto.constants.RSA_PKCS1_PADDING },
    Buffer.from(keyBuffer.toString('base64'), 'utf8'),
  ).toString('base64');
  return { encryptedKey, encryptedData, iv: ivBuffer.toString('base64'), nonce: randomHex(32), timestamp: Date.now().toString() };
}

function parseAccounts(raw) {
  const isPhone = (value) => /^1\d{10}$/.test(String(value || ''));
  const isAppid = (value) => /^wx[a-z0-9]+$/i.test(String(value || ''));
  const isWxid = (value) => /^wxid_/i.test(String(value || ''));
  const isOpenid = (value) => /^o[wW][a-zA-Z0-9]/i.test(String(value || '')); // 应用宝 openid（如 owNAX...）
  const isUa = (value) => /MicroMessenger|Mozilla|MiniProgramEnv/i.test(String(value || ''));
  return String(raw || '')
    .split(/[\n&]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const parts = item.split('#').map((value) => value.trim()).filter(Boolean);
      // 标识符：wxid_ 开头走牛子，openid 格式走应用宝（yyb）
      const wxid = parts.find(isWxid) || parts.find(isOpenid) || '';
      if (!wxid) return null;

      const mobile = parts.find(isPhone) || '';
      const appid = parts.find(isAppid) || DEFAULT_APPID;
      const ua = parts.find(isUa) || '';
      const remark = parts.find((value) => value && !isPhone(value) && !isWxid(value) && !isOpenid(value) && !isAppid(value) && !isUa(value)) || mobile || wxid;

      return {
        mobile,
        wxid,
        appid,
        remark,
        ua,
      };
    })
    .filter(Boolean)
    .filter((item) => item.wxid);
}

function parseManualAccounts(rawData) {
  if (!rawData) return [];
  let parsedTokens = [];
  try {
    const parsed = JSON.parse(rawData);
    if (Array.isArray(parsed) && parsed.length > 0) {
      parsedTokens = parsed;
    }
  } catch (e) {
    let accounts = String(rawData).split(/[\n&@]+/);
    for (let acc of accounts) {
      if (!acc.trim()) continue;
      try {
        let singleJson = JSON.parse(acc);
        if (Array.isArray(singleJson)) parsedTokens.push(...singleJson);
        else if (typeof singleJson === 'object' && singleJson !== null) parsedTokens.push(singleJson);
      } catch (err) {
        let parts = acc.split('#');
        if (parts.length >= 7) {
          parsedTokens.push({
            remark: parts[0].trim(),
            mobile: parts[1].trim(),
            token: parts[2].trim(),
            accountId: parts[3].trim(),
            sessionKey: parts[4].trim(),
            openId: parts[5].trim(),
            memberId: parts[6].trim()
          });
        }
      }
    }
  }
  return parsedTokens.map((t, i) => ({
    remark: t.remark || '手动账号' + (i + 1),
    mobile: t.mobile || '',
    token: t.token,
    accountId: t.accountId,
    sessionKey: t.sessionKey,
    openId: t.openId,
    memberId: t.memberId,
    appid: t.appid || DEFAULT_APPID,
    isManual: true,
    wxid: `manual_${i}_${Date.now()}`
  })).filter(t => t.token && t.accountId);
}

function printTaskList(tasks) {
  log(`📋 任务列表：${tasks.length} 个`);
  tasks.forEach((task, index) => {
    const progress = getTaskProgress(task);
    const status = task.isCompleted ? '已完成' : `${progress.done}/${progress.max}`;
    const mode = task.issuedPoints === false ? '非直接积分' : '可领积分';
    const hidden = task.isShow === false ? '隐藏' : '展示';
    log(`  ${index + 1}. [${getTaskType(task)}] ${getTaskName(task)} | ${status} | ${task.pointCount || 0}积分+${task.pointLevelCount || 0}成长值 | ${hidden}/${mode}`);
  });
}

function getTaskType(task = {}) { return task.tmplType || task.actionType || ''; }
function getTaskName(task = {}) { return task.title || task.name || task.templateName || getTaskType(task) || '未知任务'; }
function getTaskProgress(task = {}) {
  if (getTaskType(task) === 'SIGN_IN') return { done: task.isCompleted ? 1 : 0, max: 1 };
  const records = Array.isArray(task.actionRecordList) ? task.actionRecordList.length : 0;
  const done = Math.max(0, toInt(task.participationCount ?? records, 0));
  const max = Math.max(1, toInt(task.maxDailyParticipationCount ?? task.unitCount, 1));
  return { done, max };
}

function extractWxCode(payload) {
  return getPath(payload, ['Data', 'code']) || getPath(payload, ['data', 'code']) || (typeof payload.Data === 'string' ? payload.Data : '') || (typeof payload.data === 'string' ? payload.data : '') || '';
}

function extractAuth(payload) {
  const from = payload && typeof payload.data === 'object' ? payload.data : payload || {};
  return {
    token: findDeep(from, ['token', 'authToken', 'accessToken']),
    accountId: findDeep(from, ['accountId', 'accountID', 'account_id']),
    sessionKey: findDeep(from, ['sessionKey', 'session_key']),
    openId: findDeep(from, ['openId', 'openid']),
    memberId: findDeep(from, ['memberId', 'member_id', 'id']),
    mobile: findDeep(from, ['mobile', 'phone', 'memberMobile']),
  };
}

function normalizeAuth(auth = {}) {
  return {
    token: auth.token || auth.authToken || auth.accessToken || '',
    accountId: auth.accountId || auth.accountID || auth.account_id || '',
    sessionKey: auth.sessionKey || auth.session_key || '',
    openId: auth.openId || auth.openid || '',
    memberId: auth.memberId || auth.member_id || auth.id || '',
    mobile: auth.mobile || auth.phone || auth.memberMobile || '',
    appid: auth.appid || DEFAULT_APPID,
  };
}

function findDeep(source, names) {
  const wanted = new Set(names.map((name) => name.toLowerCase()));
  const queue = [{ value: source, depth: 0 }];
  while (queue.length) {
    const { value, depth } = queue.shift();
    if (!value || typeof value !== 'object' || depth > 5) continue;
    for (const [key, child] of Object.entries(value)) {
      if (wanted.has(String(key).toLowerCase()) && child !== undefined && child !== null && child !== '') return String(child);
      if (child && typeof child === 'object') queue.push({ value: child, depth: depth + 1 });
    }
  }
  return '';
}

function getPath(source, keys) {
  let current = source;
  for (const key of keys) {
    if (!current || typeof current !== 'object' || !(key in current)) return '';
    current = current[key];
  }
  return current || '';
}

function decodeBody(buffer, encoding) {
  const value = String(encoding || '').toLowerCase();
  if (value.includes('br')) return zlib.brotliDecompressSync(buffer);
  if (value.includes('gzip')) return zlib.gunzipSync(buffer);
  if (value.includes('deflate')) return zlib.inflateSync(buffer);
  return buffer;
}

function loadCache() {
  try {
    if (!fs.existsSync(CACHE_FILE)) return {};
    const data = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
    return data && typeof data === 'object' ? data : {};
  } catch (error) {
    log(`⚠️ 读取缓存失败：${error.message}`);
    return {};
  }
}

function saveCache(cache) {
  try { fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2), 'utf8'); }
  catch (error) { log(`⚠️ 保存缓存失败：${error.message}`); }
}

async function sendNotifySafe(title, message) {
  if (!CONFIG.notify || !message) return;
  try {
    const notify = loadSendNotify();
    if (notify && typeof notify.sendNotify === 'function') await notify.sendNotify(title, message);
  } catch (error) {
    log(`⚠️ 通知失败：${error.message}`);
  }
}

function loadSendNotify() {
  const candidates = [
    './sendNotify',
    './sendNotify.js',
    '../sendNotify',
    '../sendNotify.js',
    '/ql/scripts/sendNotify',
    '/ql/scripts/sendNotify.js',
    '/ql/data/scripts/sendNotify',
    '/ql/data/scripts/sendNotify.js',
  ];
  let lastError = null;
  for (const item of candidates) {
    try {
      const notify = require(item);
      if (notify && typeof notify.sendNotify === 'function') return notify;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error('未找到 sendNotify.js');
}

function randomString(length) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let index = 0; index < length; index += 1) result += chars.charAt(Math.floor(Math.random() * chars.length));
  return result;
}

function randomHex(length) {
  const chars = '0123456789abcdef';
  let result = '';
  for (let index = 0; index < length; index += 1) result += chars.charAt(Math.floor(Math.random() * chars.length));
  return result;
}

function mask(value, start = 6, end = 4) {
  const text = String(value || '');
  if (!text) return '';
  if (text.length <= start + end) return `${text.slice(0, 2)}***`;
  return `${text.slice(0, start)}***${text.slice(-end)}`;
}

function maskPhone(value) {
  const text = String(value || '');
  if (!/^1\d{10}$/.test(text)) return text ? mask(text, 3, 2) : '';
  return `${text.slice(0, 3)}****${text.slice(-4)}`;
}

function safeJson(value) { try { return JSON.stringify(value); } catch { return String(value); } }
function shortText(value) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > 500 ? `${text.slice(0, 500)}...` : text;
}
function trimRightSlash(value) { return String(value || '').replace(/\/+$/, ''); }
function toInt(value, fallback) { const number = Number.parseInt(value, 10); return Number.isFinite(number) ? number : fallback; }
function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms))); }
function log(message) { console.log(message); }
