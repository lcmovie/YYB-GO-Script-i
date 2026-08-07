#!/usr/bin/env node
// name:创维小程序
/**
 * 创维小程序
 * cron: 39 9,16 * * *
 *
 * 流程：
 * wxid -> WECHAT_SERVER取code -> /v2/user/exchange -> ticket -> /v2/user/signin -> Authorization
 * -> 固定5个任务：/userScoreStatusInfo + /v1/complete-task/{taskCode}
 * -> 额外签到（兑吧连续签到）：index-nav(register) -> duiba-nologin -> autoLogin -> doSign
 *
 * 环境变量：
 * - WX_ID                   多账号，换行或&分隔；格式：wxid_xxx#备注（兼容旧变量 chuangw）
 * - WECHAT_SERVER           微信协议服务地址（可选，在 getCode.js 中配置）
 * - CHUANGW_APPID           默认 wxff438d3c60c63fb6
 * - CHUANGW_APP_PATH        默认 /pages/login/login
 * - CHUANGW_RUN_TASKS       默认1，0=只登录拿token
 */

'use strict';

const { getSingleCode } = require('./getCode');
const { sendNotify } = require('./sendNotify');
const crypto = require('crypto');
const vm = require('vm');

const ENV_NAME = 'chuangw';
const UC_API = 'https://uc-api.skyallhere.com/miniprogram/api';
const UC_ADMIN = 'https://uc-admin.skyallhere.com/api';

const APPID = process.env.CHUANGW_APPID || 'wxff438d3c60c63fb6';
const APP_VERSION = process.env.CHUANGW_APP_VERSION || '8.0.70';
const SDK_VERSION = process.env.CHUANGW_SDK_VERSION || '3.15.2';
const APP_PATH = process.env.CHUANGW_APP_PATH || '/pages/login/login';
const APP_SYSTEM = process.env.CHUANGW_APP_SYSTEM || 'iOS 26.1';
const APP_MODEL = process.env.CHUANGW_APP_MODEL || 'iPhone 15 pro max<iPhone16,2>';

const RUN_TASKS = (process.env.CHUANGW_RUN_TASKS || '1') !== '0';
// 固定任务：5个（不走环境变量）
const TASK_CODES = ['TS00016', 'TS00210', 'TS00203', 'TS00211', 'TS00213'];
const TASK_NAME_MAP = {
  TS00016: '每日签到',
  TS00210: '浏览商品详情',
  TS00201: '购买商品',
  TS00100: '添加产品',
  TS00202: '产品评价',
  TS00203: '分享商品',
  TS00211: '浏览商品详情(成长值)',
  TS00213: '浏览图片详情',
};

// 源码里硬编码私钥（calcSystemSignAndParam）
const TASK_SIGN_PRIVATE_KEY = `-----BEGIN RSA PRIVATE KEY-----
MIIBPAIBAAJBAMJrqTwwvDRo/NP3Pjq0wfeHtfAcwRu5vk5yTfdGmKAAqG9M9Bu8
COIBN/B0lGUcUx4HP4eIvK17HoIut8shun8CAwEAAQJAXVNWymjOfw4ChzFAsud/
0HVZlWgIHmn7+yYNXOyLaQnv8I7GTrVe85lnAvcmboSvpr5KFGzhY0KDpAnCcDsh
QQIhAPzyeP4ncY7cLkftHPUTSg7Mkve/gJUFZN7q2pW0KEGfAiEAxMRcDf8yqSXP
VfUmJpnzranrFRIAs9Eqi1jzbB4KmyECIQCu2hJHZg66uXuInuEQjKf5+PJzLj79
RIBJFEHLkIDvcwIhALvLwSQmvd5MVN9wU1IiOz0zYEfC3+K/LkDCy8kTvwGhAiEA
8OKljQOdOhQcWver4UsvF5jwGPC5CqkPq/not9YLtU4=
-----END RSA PRIVATE KEY-----`;

const fetchFn = globalThis.fetch || ((...args) => import('node-fetch').then(({ default: f }) => f(...args)));

function splitAccounts(raw) {
  return String(raw || '').split(/[\n@&\r]+/).map(s => {
    let x = s.trim();
    if (x.includes('=')) {
      x = x.split('=', 2)[1].trim();
    }
    return x;
  }).filter(Boolean);
}

const LOG_WIDTH = 74;

function hr(char = '─') {
  console.log(char.repeat(LOG_WIDTH));
}

function truncText(s, max = 96) {
  const str = String(s ?? '');
  if (str.length <= max) return str;
  return `${str.slice(0, max - 1)}…`;
}

function wrapText(s, max = 86) {
  const str = String(s ?? '').replace(/\n+/g, ' ').trim();
  if (!str) return [''];
  const lines = [];
  for (let i = 0; i < str.length; i += max) lines.push(str.slice(i, i + max));
  return lines;
}

function section(title) {
  console.log(`\n━━━ ${title} ━━━`);
}

function logWithIcon(icon, msg) {
  const lines = wrapText(msg);
  lines.forEach((line, idx) => {
    if (idx === 0) console.log(`${icon} ${line}`);
    else console.log(`   ${line}`);
  });
}

function logInfo(msg) {
  logWithIcon('ℹ️', msg);
}

function logOk(msg) {
  logWithIcon('✅', msg);
}

function logWarn(msg) {
  logWithIcon('⚠️', msg);
}

function logErr(msg) {
  logWithIcon('❌', msg);
}

function logSep(char = '─') {
  console.log(char.repeat(LOG_WIDTH));
}

function endSection() {
  console.log('');
}

function maskMiddle(s, left = 10, right = 8) {
  const str = String(s || '');
  if (!str) return '';
  if (str.length <= left + right + 3) return str;
  return `${str.slice(0, left)}...${str.slice(-right)}`;
}

function brief(v, max = 54) {
  if (v === undefined || v === null) return '';
  const s = typeof v === 'string' ? v : JSON.stringify(v);
  return truncText(s, max);
}

function taskName(code) {
  return TASK_NAME_MAP[code] || '任务';
}

function taskStateText(v) {
  return Number(v) === 1 ? '已完成' : '未完成';
}

function isWxidLike(s) {
  const x = String(s || '').trim();
  if (!x) return false;
  if (x.startsWith('wx:')) return true;
  if (x.startsWith('wxid_')) return true;
  return /^[a-zA-Z0-9_-]{4,64}$/.test(x) && !x.includes('.');
}

function decodeJwtPayload(token) {
  try {
    const p = String(token || '').split('.');
    if (p.length < 2) return null;
    const b64 = p[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    return JSON.parse(Buffer.from(padded, 'base64').toString('utf8'));
  } catch {
    return null;
  }
}

function fmtTs(ts) {
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return String(ts);
  return d.toLocaleString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' });
}

function printTokenInfo(token) {
  const p = decodeJwtPayload(token) || {};
  const iat = Number(p.iat || 0);
  const exp = Number(p.exp || 0);
  if (!iat || !exp) return;
  const validM = Math.floor((exp - iat) / 60);
  const leftM = Math.max(0, Math.floor((exp - Math.floor(Date.now() / 1000)) / 60));
  logInfo(`Token有效期≈${validM}分钟，剩余≈${leftM}分钟`);
  logInfo(`签发时间: ${fmtTs(iat)}`);
  logInfo(`过期时间: ${fmtTs(exp)}`);
}

function commonHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    'App-Version': APP_VERSION,
    'App-Sdkversion': SDK_VERSION,
    'App-System': APP_SYSTEM,
    'App-Model': APP_MODEL,
    'App-Path': APP_PATH,
    'User-Agent': 'Mozilla/5.0 MicroMessenger MiniProgram',
    ...extra,
  };
}

function miniH5UA() {
  return `Mozilla/5.0 (iPhone; CPU iPhone OS 26_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.70(0x1800463a) NetType/WIFI Language/zh_CN miniProgram/${APPID}`;
}

function safeJsonParse(text, fallback = null) {
  try { return JSON.parse(text); } catch { return fallback; }
}

function getSetCookieList(headers) {
  if (!headers) return [];
  if (typeof headers.getSetCookie === 'function') return headers.getSetCookie();
  if (typeof headers.raw === 'function') {
    const raw = headers.raw();
    if (raw && Array.isArray(raw['set-cookie'])) return raw['set-cookie'];
  }
  const single = headers.get ? headers.get('set-cookie') : '';
  if (!single) return [];
  return String(single).split(/,(?=[^;,]+=)/g).map(s => s.trim()).filter(Boolean);
}

function setCookieToJar(jar, setCookieLine) {
  const line = String(setCookieLine || '');
  const first = line.split(';')[0] || '';
  const idx = first.indexOf('=');
  if (idx <= 0) return;
  const k = first.slice(0, idx).trim();
  const v = first.slice(idx + 1).trim();
  if (!k) return;
  jar[k] = v;
}

function cookieHeaderFromJar(jar) {
  return Object.entries(jar || {}).map(([k, v]) => `${k}=${v}`).join('; ');
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function genNonce() {
  return crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

async function httpJson(url, { method = 'GET', headers = {}, body, timeout = 20000 } = {}) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(new Error('timeout')), timeout);
  try {
    const resp = await fetchFn(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: c.signal,
    });
    const text = await resp.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
    if (!resp.ok) throw new Error(`${method} ${url} -> ${resp.status} ${text.slice(0, 400)}`);
    return data;
  } finally {
    clearTimeout(t);
  }
}

async function httpText(url, { method = 'GET', headers = {}, body, timeout = 20000, jar = null, redirect = 'manual' } = {}) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(new Error('timeout')), timeout);
  try {
    const reqHeaders = { ...headers };
    if (jar && Object.keys(jar).length) {
      reqHeaders.Cookie = cookieHeaderFromJar(jar);
    }
    const resp = await fetchFn(url, {
      method,
      headers: reqHeaders,
      body,
      redirect,
      signal: c.signal,
    });

    if (jar) {
      const setCookies = getSetCookieList(resp.headers);
      for (const line of setCookies) setCookieToJar(jar, line);
    }

    const text = await resp.text();
    const isRedirect = resp.status >= 300 && resp.status < 400;
    if (!resp.ok && !isRedirect) {
      throw new Error(`${method} ${url} -> ${resp.status} ${text.slice(0, 400)}`);
    }
    return { status: resp.status, headers: resp.headers, text, finalUrl: resp.url };
  } finally {
    clearTimeout(t);
  }
}

async function getWxCode(wxid, appid = APPID) {
  try {
    return await getSingleCode(appid, wxid);
  } catch (e) {
    throw new Error(`wx.login失败: ${e.message || e}`);
  }
}

async function exchangeByCode(code) {
  const ret = await httpJson(`${UC_API}/v2/user/exchange`, {
    method: 'POST',
    headers: commonHeaders(),
    body: { code },
  });
  const ticket = ret?.data?.ticket || (typeof ret?.data === 'string' ? ret.data : '');
  if ((ret?.code === 0 || ret?.code === '0') && ticket) return ticket;
  throw new Error(`exchange失败: ${JSON.stringify(ret)}`);
}

async function signinByTicket(ticket) {
  const ret = await httpJson(`${UC_API}/v2/user/signin`, {
    method: 'POST',
    headers: commonHeaders(),
    body: { ticket },
  });
  const token = ret?.data?.token || '';
  if ((ret?.code === 0 || ret?.code === '0') && token) return token;
  throw new Error(`signin失败: ${JSON.stringify(ret)}`);
}

async function getUserByToken(token) {
  return httpJson(`${UC_API}/v1/get-user`, {
    method: 'GET',
    headers: commonHeaders({ Authorization: `Bearer ${token}` }),
  });
}

async function getWdStatus(token) {
  const ret = await httpJson(`${UC_ADMIN}/userEquityScoreLog/miniProgram/userScoreStatusInfo`, {
    method: 'GET',
    headers: commonHeaders({
      Authorization: `Bearer ${token}`,
      isNoToken: '1',
      'App-Path': '/pages-user/get-wd/get-wd',
    }),
  });
  const arr = Array.isArray(ret?.data) ? ret.data : [];
  const map = {};
  for (const x of arr) map[x.taskLabel] = Number(x.isComplete || 0);
  return { raw: ret, map };
}

async function getIndexNav(token) {
  return httpJson(`${UC_API}/v1/index-nav`, {
    method: 'GET',
    headers: commonHeaders({
      Authorization: `Bearer ${token}`,
      'App-Path': '/pages/user/user',
    }),
  });
}

async function getDuibaAutoLoginUrl(token) {
  const nav = await getIndexNav(token);
  const tokenUrl = nav?.data?.register || '';
  if (!tokenUrl) {
    throw new Error('index-nav未返回register签到入口');
  }
  const ret = await httpJson(tokenUrl, {
    method: 'GET',
    headers: commonHeaders({
      Authorization: `Bearer ${token}`,
      'App-Path': '/pages/user/user',
    }),
  });
  const autoLoginUrl = typeof ret?.data === 'string' ? ret.data : '';
  if (!autoLoginUrl) throw new Error(`duiba-nologin失败: ${JSON.stringify(ret)}`);
  return { tokenUrl, autoLoginUrl };
}

function extractScriptBlocks(html) {
  const out = [];
  const re = /<script[^>]*>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(String(html || '')))) {
    out.push(m[1] || '');
  }
  return out;
}

function decodeObfuscatedEvalScript(scriptCode, context = {}) {
  let generated = '';
  const sandbox = {
    window: {},
    location: { host: '74367-1-activity.m.dexfu.cn' },
    XMLHttpRequest: function () {},
    eval: (s) => {
      generated = String(s || '');
      return s;
    },
    ...context,
  };
  vm.createContext(sandbox);
  vm.runInContext(String(scriptCode || ''), sandbox, { timeout: 2500 });
  return generated;
}

function extractDuibaKeyFromPageHtml(pageHtml) {
  try {
    const scripts = extractScriptBlocks(pageHtml);
    const target = scripts.find(s => s.includes('获取token') || s.includes('/chw/ctoken/getToken'));
    if (!target) return 'e7a76d7t';
    const generated = decodeObfuscatedEvalScript(target);
    const m = generated.match(/var\s+key\s*=\s*['"]([^'"]+)['"]/);
    return m?.[1] || 'e7a76d7t';
  } catch {
    return 'e7a76d7t';
  }
}

function extractWindowAssignments(code) {
  const map = {};
  const re = /window\[['"]([^'"]+)['"]\]\s*=\s*['"]([^'"]*)['"]/g;
  let m;
  while ((m = re.exec(String(code || '')))) {
    map[m[1]] = m[2];
  }
  return map;
}

function resolveDuibaCtoken(tokenScript, keyHint = '') {
  let generated = '';
  try {
    generated = decodeObfuscatedEvalScript(String(tokenScript || ''), { window: {} });
  } catch {
    generated = '';
  }

  if (generated) {
    try {
      const sandbox = { window: {} };
      vm.createContext(sandbox);
      vm.runInContext(generated, sandbox, { timeout: 1500 });
      const win = sandbox.window || {};
      if (keyHint && typeof win[keyHint] === 'string') return win[keyHint];
      for (const v of Object.values(win)) {
        if (typeof v === 'string' && /^[a-zA-Z0-9]{4,24}$/.test(v)) return v;
      }
    } catch {
      // ignore
    }
  }

  const map = extractWindowAssignments(generated || tokenScript);
  if (keyHint && typeof map[keyHint] === 'string') return map[keyHint];
  for (const v of Object.values(map)) {
    if (typeof v === 'string' && /^[a-zA-Z0-9]{4,24}$/.test(v)) return v;
  }
  return '';
}

function getRedirectLocation(headers, baseUrl) {
  const loc = headers?.get ? headers.get('location') : '';
  if (!loc) return '';
  try { return new URL(loc, baseUrl).toString(); } catch { return loc; }
}

async function getDuibaIndexInfo(origin, signOperatingId, pageUrl, jar, ua) {
  const url = `${origin}/sign/component/index?${new URLSearchParams({
    signOperatingId: String(signOperatingId),
    preview: 'false',
    _: String(Date.now()),
  }).toString()}`;
  const resp = await httpText(url, {
    method: 'GET',
    jar,
    redirect: 'manual',
    headers: {
      Accept: 'application/json, text/plain, */*',
      Referer: pageUrl,
      'User-Agent': ua,
    },
  });
  return safeJsonParse(resp.text, {});
}

async function getDuibaCtoken(origin, pageUrl, jar, ua, keyHint) {
  const resp = await httpText(`${origin}/chw/ctoken/getToken`, {
    method: 'POST',
    jar,
    redirect: 'manual',
    headers: {
      Accept: '*/*',
      'Content-Type': 'application/x-www-form-urlencoded',
      Origin: origin,
      Referer: pageUrl,
      'User-Agent': ua,
    },
    body: `timestamp=${Date.now()}`,
  });
  const data = safeJsonParse(resp.text, {});
  if (!data?.success || !data?.token) {
    throw new Error(`ctoken接口失败: ${String(resp.text).slice(0, 200)}`);
  }
  const token = resolveDuibaCtoken(data.token, keyHint);
  if (!token) throw new Error('ctoken解析失败');
  return token;
}

async function doDuibaSign(origin, signOperatingId, signToken, pageUrl, jar, ua) {
  const resp = await httpText(`${origin}/sign/component/doSign?_=${Date.now()}`, {
    method: 'POST',
    jar,
    redirect: 'manual',
    headers: {
      Accept: 'application/json, text/plain, */*',
      'Content-Type': 'application/x-www-form-urlencoded',
      Origin: origin,
      Referer: pageUrl,
      'User-Agent': ua,
    },
    body: new URLSearchParams({
      signOperatingId: String(signOperatingId),
      token: String(signToken),
    }).toString(),
  });
  return safeJsonParse(resp.text, {});
}

async function getDuibaSignResult(origin, orderNum, pageUrl, jar, ua) {
  const url = `${origin}/sign/component/signResult?orderNum=${encodeURIComponent(String(orderNum))}&_=${Date.now()}`;
  const resp = await httpText(url, {
    method: 'GET',
    jar,
    redirect: 'manual',
    headers: {
      Accept: 'application/json, text/plain, */*',
      Referer: pageUrl,
      'User-Agent': ua,
    },
  });
  return safeJsonParse(resp.text, {});
}

function calcTaskSign(taskCode, nonce, timestamp, snCode = '') {
  const data = { taskCode, nonce, timestamp: String(timestamp) };
  if (snCode) data.snCode = snCode;

  const keys = Object.keys(data).sort((a, b) => (a > b ? 1 : -1));
  let preSign = '';
  for (const k of keys) {
    if (k !== 'taskCode' && k !== 'snCode') preSign += `${k}=${data[k]}&`;
  }

  const signer = crypto.createSign('RSA-SHA256');
  signer.update(preSign);
  signer.end();
  const sign = signer.sign(TASK_SIGN_PRIVATE_KEY, 'base64');

  return { preSign, sign };
}

async function completeTask(token, taskCode) {
  const nonce = genNonce();
  const timestamp = String(Date.now());
  const { preSign, sign } = calcTaskSign(taskCode, nonce, timestamp);

  const qs = new URLSearchParams({ taskCode, nonce, timestamp }).toString();
  const url = `${UC_API}/v1/complete-task/${taskCode}?${qs}`;

  const appPathMap = {
    TS00210: '/pages-cwshop/goods/detail/detail?wd=2',
    TS00016: '/pages/webview/webview?taskCode=TS00016',
    TS00203: '/pages-cwshop/goods/detail/detail?czz=1',
    TS00211: '/pages-cwshop/goods/detail/detail?czz=2',
    TS00213: '/pages-picture/picture/page-picture-detail',
  };

  const ret = await httpJson(url, {
    method: 'GET',
    headers: commonHeaders({
      Authorization: `Bearer ${token}`,
      nonce,
      timestamp,
      sign,
      'App-Path': appPathMap[taskCode] || APP_PATH,
    }),
  });

  return { ret, preSign };
}

async function runTasks(token) {
  section('任务中心');
  const before = await getWdStatus(token);
  logInfo(`固定任务(${TASK_CODES.length})：${TASK_CODES.map(c => `${c}(${taskName(c)})`).join('，')}`);
  logSep();

  let execCount = 0;
  let successCount = 0;

  for (let i = 0; i < TASK_CODES.length; i++) {
    const taskCode = TASK_CODES[i];
    const name = taskName(taskCode);
    const b = before.map[taskCode];
    if (Number(b) === 1) {
      logWarn(`[${i + 1}/${TASK_CODES.length}] ${taskCode} ${name}：已完成，跳过`);
      continue;
    }

    execCount++;
    logInfo(`[${i + 1}/${TASK_CODES.length}] 开始上报 ${taskCode} ${name}`);
    try {
      const { ret } = await completeTask(token, taskCode);
      const msg = brief(ret?.data || ret?.msg || ret);
      if (Number(ret?.code) === 0 || String(ret?.code) === '0') {
        successCount++;
        logOk(`${taskCode} ${name}：${msg || '成功'}`);
      } else {
        logWarn(`${taskCode} ${name}：${msg || '失败'}`);
      }
    } catch (e) {
      logErr(`${taskCode} ${name}：${e.message || e}`);
    }
    await sleep(800);
  }

  const after = await getWdStatus(token);
  logSep();
  logInfo('任务状态对比（执行前 -> 执行后）');
  for (const taskCode of TASK_CODES) {
    const name = taskName(taskCode);
    const b = taskStateText(before.map[taskCode]);
    const a = taskStateText(after.map[taskCode]);
    const icon = a === '已完成' ? '✅' : '▫️';
    logInfo(`${icon} ${taskCode} ${name}: ${b} -> ${a}`);
  }
  logSep();
  logOk(`任务执行结束：尝试 ${execCount} 个，成功 ${successCount} 个，跳过 ${TASK_CODES.length - execCount} 个`);
  endSection();
}

async function runDuibaExtraSign(token) {
  section('额外签到（兑吧连续签到）');
  try {
    const { autoLoginUrl } = await getDuibaAutoLoginUrl(token);
    logOk('签到入口获取成功');

    const jar = {};
    const ua = miniH5UA();

    const autoResp = await httpText(autoLoginUrl, {
      method: 'GET',
      jar,
      redirect: 'manual',
      headers: {
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'User-Agent': ua,
      },
    });

    const signPageUrl = getRedirectLocation(autoResp.headers, autoLoginUrl) || autoLoginUrl;
    const pageResp = await httpText(signPageUrl, {
      method: 'GET',
      jar,
      redirect: 'follow',
      headers: {
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        Referer: autoLoginUrl,
        'User-Agent': ua,
      },
    });

    const finalPageUrl = pageResp.finalUrl || signPageUrl;
    const u = new URL(finalPageUrl);
    const origin = `${u.protocol}//${u.host}`;
    const signOperatingId = u.searchParams.get('signOperatingId');
    if (!signOperatingId) throw new Error(`未找到signOperatingId: ${finalPageUrl}`);

    const keyHint = extractDuibaKeyFromPageHtml(pageResp.text);
    logInfo('已进入签到页');

    const before = await getDuibaIndexInfo(origin, signOperatingId, finalPageUrl, jar, ua);
    const bCon = Number(before?.data?.consecutiveCount || 0);
    const bTot = Number(before?.data?.totalCount || 0);
    const beforeSigned = Boolean(before?.data?.signResult);
    logInfo(`签到前：连签${bCon}天，总签到${bTot}天`);
    logInfo(`签到前状态：${beforeSigned ? '今日已签到' : '今日未签到'}`);

    const signToken = await getDuibaCtoken(origin, finalPageUrl, jar, ua, keyHint);
    logOk('ctoken解析成功');

    const signRet = await doDuibaSign(origin, signOperatingId, signToken, finalPageUrl, jar, ua);
    const signResult = Number(signRet?.data?.signResult ?? -1);
    const orderNum = signRet?.data?.orderNum || '';
    const signTextMap = {
      100: '签到请求已受理',
      2: '今日已签到',
      1: '签到成功',
    };
    logInfo(`doSign：${signTextMap[signResult] || `状态码 ${signResult}`}${orderNum ? `（单号${orderNum}）` : ''}`);

    let finalResult = null;
    if (orderNum) {
      for (let i = 0; i < 3; i++) {
        await sleep(350 + i * 350);
        finalResult = await getDuibaSignResult(origin, orderNum, finalPageUrl, jar, ua);
        if (Number(finalResult?.data?.signResult || 0) === 2) break;
      }
    }
    let finalSignCode = NaN;
    if (finalResult?.data) {
      const sr = Number(finalResult?.data?.signResult ?? -1);
      finalSignCode = sr;
      const credits = finalResult?.data?.credits;
      logInfo(`结果确认：状态码 ${sr}${credits !== null && credits !== undefined ? `，奖励 ${credits} 维豆` : ''}`);
    }

    const after = await getDuibaIndexInfo(origin, signOperatingId, finalPageUrl, jar, ua);
    const aCon = Number(after?.data?.consecutiveCount || 0);
    const aTot = Number(after?.data?.totalCount || 0);
    const afterSigned = Boolean(after?.data?.signResult);
    logSep();
    logInfo(`状态对比: 连签 ${bCon} -> ${aCon}，总签到 ${bTot} -> ${aTot}`);
    logInfo(`签到后状态：${afterSigned ? '今日已签到' : '今日未签到'}`);

    const progressChanged = aCon > bCon || aTot > bTot;
    const signedNow = !beforeSigned && afterSigned;
    const alreadySigned = beforeSigned && afterSigned && !progressChanged;

    if (progressChanged || signedNow || finalSignCode === 1) {
      logOk('兑吧连续签到成功');
    } else if (alreadySigned || signResult === 2 || finalSignCode === 2) {
      logInfo('今日已签到（可能是你手动签过）');
    } else {
      logWarn('签到状态未变化（可能已签/风控）');
    }
    logSep();
  } catch (e) {
    logErr(`兑吧签到失败: ${e.message || e}`);
  }
  endSection();
}

async function runOne(line, idx) {
  const [rawWxid, note = ''] = line.split('#').map(s => s.trim());
  const wxid = rawWxid?.startsWith('wx:') ? rawWxid.slice(3) : rawWxid;

  section(`账号${idx}${note ? ` (${note})` : ''}`);

  if (!isWxidLike(rawWxid)) {
    throw new Error('仅支持 wxid 协议模式；请填 wxid_xxx#备注');
  }

  const code = await getWxCode(wxid, APPID);
  logOk(`wx.login成功，code=${maskMiddle(String(code), 8, 4)}`);

  const ticket = await exchangeByCode(code);
  logOk(`exchange成功，ticket=${maskMiddle(ticket, 8, 6)}`);

  const token = await signinByTicket(ticket);
  logOk(`signin成功，Authorization=Bearer ${maskMiddle(token, 16, 12)}`);
  printTokenInfo(token);
  logSep();

  const profile = await getUserByToken(token);
  const user = {
    userId: profile?.data?.baseInfo?.userId,
    phone: profile?.data?.baseInfo?.phone,
    nickName: profile?.data?.baseInfo?.nickName,
  };
  logOk('/v1/get-user 成功');
  logInfo(`用户ID: ${user.userId || '-'}`);
  logInfo(`手机号: ${user.phone || '-'}`);
  logInfo(`昵称: ${user.nickName || '-'}`);
  logSep();

  if (RUN_TASKS) {
    await runTasks(token);
    await runDuibaExtraSign(token);
  } else {
    logWarn('CHUANGW_RUN_TASKS=0，已跳过全部任务（含兑吧签到）');
  }
  endSection();
}

(async () => {
  const raw = process.env.WX_ID || process.env[ENV_NAME] || '';
  if (!raw.trim()) {
    console.log(`未设置环境变量 WX_ID 或 ${ENV_NAME}`);
    process.exit(0);
  }

  const accounts = splitAccounts(raw);
  hr('═');
  console.log(`🚀 创维协议任务启动 | 共 ${accounts.length} 个账号`);
  hr('═');

  for (let i = 0; i < accounts.length; i++) {
    try {
      await runOne(accounts[i], i + 1);
    } catch (e) {
      logErr(`账号${i + 1}失败: ${e.message || e}`);
      endSection();
    }
  }
  hr('═');
  console.log('🎉 全部账号处理完成');
  hr('═');
  await sendNotify('创维小程序', `全部账号任务执行完成，共 ${accounts.length} 个账号`);
})();
