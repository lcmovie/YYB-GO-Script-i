// name:美孚
/*
小程序：美孚臻享俱乐部（微信协议版）
cron: 33 8,15 * * *
必填变量：
  WECHAT_SERVER  微信协议服务地址（getCode.js 读取，例如：http://127.0.0.1:8011）
  WX_ID          微信账号，多账号支持换行、&、@ 分隔
                 格式：wxid#备注（备注可选）

兼容变量：
  mftoken        旧版 X-access-token，多账号用 & 或换行分隔

可选变量：
  MF_FORCE_LOGIN  填 1 时忽略 mfwx.json 缓存，强制重新协议登录
  MF_TIMEOUT      请求超时时间，单位毫秒，默认 20000
  MF_SIGN_DELAY_MIN  签到前随机等待最小毫秒，默认 1500
  MF_SIGN_DELAY_MAX  签到前随机等待最大毫秒，默认 4500
  MF_X_USER_ID    特殊情况下手动指定 X-User-Id；默认不发送
  MF_OCR_SERVER   ddddocr 服务地址，默认：http://192.168.6.222:7777
  MF_CAPTCHA_RETRY  图形验证码识别重试次数，默认 3
*/

const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const zlib = require('zlib');
const { URL } = require('url');
const { getSingleCode } = require('./getCode.js'); // 共享微信小程序 code 获取模块（自动路由牛子/应用宝，读取 WX_ID）
const { sendNotify } = require('./sendNotify.js');

const APP_NAME = '美孚臻享俱乐部';
const WX_APPID = 'wx46f9572cac706c22';
const BASE_URL = 'https://www.rewards.mobil.com.cn';
const MALL_ID = '1';
const APP_VERSION = '4.8.9';
const CACHE_FILE = path.join(__dirname, 'mfwx.json');

const CONFIG = {
  wechatServer: trimRightSlash(process.env.WECHAT_SERVER || process.env.MF_WECHAT_SERVER || ''),
  wxAccountsRaw: process.env.WX_ID || '',
  tokenRaw: process.env.mftoken || process.env.MFTOKEN || '',
  timeout: toPositiveInt(process.env.MF_TIMEOUT, 20000),
  signDelayMin: toNonNegativeInt(process.env.MF_SIGN_DELAY_MIN, 1500),
  signDelayMax: toNonNegativeInt(process.env.MF_SIGN_DELAY_MAX, 4500),
  xUserId: process.env.MF_X_USER_ID || '',
  ocrServer: trimRightSlash(process.env.MF_OCR_SERVER || process.env.OCR_SERVER || 'http://192.168.6.222:7777'),
  captchaRetry: toPositiveInt(process.env.MF_CAPTCHA_RETRY, 3),
  forceLogin: ['1', 'true', 'yes'].includes(
    String(process.env.MF_FORCE_LOGIN || process.env.MFWX_FORCE_LOGIN || '').toLowerCase(),
  ),
};

const WX_UA =
  'Mozilla/5.0 (Linux; Android 10; MI 8 Build/QKQ1.190828.002; wv) ' +
  'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/126.0.6478.122 ' +
  'Mobile Safari/537.36 XWEB/1260059 MMWEBSDK/20240501 MMWEBID/3628 ' +
  'MicroMessenger/8.0.50.2701(0x28003252) WeChat/arm64 Weixin NetType/WIFI ' +
  'Language/zh_CN ABI/arm64 MiniProgramEnv/android';

const COMMON_HEADERS = {
  Host: 'www.rewards.mobil.com.cn',
  Connection: 'keep-alive',
  Accept: 'application/json, text/plain, */*',
  charset: 'utf-8',
  'User-Agent': WX_UA,
  'X-Form-Id-List': '[]',
  'X-App-Platform': 'wxapp',
  'X-Requested-With': 'XMLHttpRequest',
  'X-channel': 'WXapp',
  'X-App-Version': APP_VERSION,
  Referer: `https://servicewechat.com/${WX_APPID}/120/page-frame.html`,
};

main()
  .then(() => sendNotify(APP_NAME, '全部账号任务执行完成'))
  .catch(async (error) => {
    const message = error && error.stack ? error.stack : String(error);
    console.log(`[异常] ${message}`);
    await sendNotify(`${APP_NAME}异常`, message);
    process.exitCode = 1;
  });

async function main() {
  const wxAccounts = parseWxAccounts(CONFIG.wxAccountsRaw);
  const tokenAccounts = parseTokenAccounts(CONFIG.tokenRaw);

  if (wxAccounts.length) {
    console.log(`[开始] ${APP_NAME} 微信协议版，共 ${wxAccounts.length} 个账号`);
    const cache = loadCache();

    for (let index = 0; index < wxAccounts.length; index += 1) {
      const account = wxAccounts[index];
      console.log(`\n[账号 ${index + 1}] ${account.remark}`);

      try {
        await runProtocolAccount(account, cache);
      } catch (error) {
        console.log(`[失败] ${account.remark} 执行异常：${error.message}`);
      }
    }
    return;
  }

  if (tokenAccounts.length) {
    console.log(`[开始] ${APP_NAME} token 兼容模式，共 ${tokenAccounts.length} 个账号`);
    for (let index = 0; index < tokenAccounts.length; index += 1) {
      const account = tokenAccounts[index];
      console.log(`\n[账号 ${index + 1}] ${account.remark}`);
      try {
        const result = await signIn(account);
        logSignResult(account, result);
      } catch (error) {
        console.log(`[失败] ${account.remark} 执行异常：${error.message}`);
      }
    }
    return;
  }

  throw new Error('请配置 WX_ID（微信协议版）或 mftoken（旧版 token）环境变量');
}

async function runProtocolAccount(account, cache) {
  let credential = await getProtocolCredential(account, cache);
  credential.cookieJar = credential.cookieJar || {};
  const warmup = await warmupAccount(account, credential);
  if (warmup && warmup.alreadySigned) return;

  await sleep(randomInt(CONFIG.signDelayMin, CONFIG.signDelayMax));
  let result = await signIn(credential);

  if (isLoginExpired(result) && !credential.justLoggedIn) {
    console.log(`[重试] ${account.remark} token 失效，重新协议登录`);
    credential = await refreshProtocolCredential(account, cache[account.wxid] || {}, cache);
    await warmupAccount(account, credential);
    await sleep(randomInt(CONFIG.signDelayMin, CONFIG.signDelayMax));
    result = await signIn(credential);
  }

  if (needsCaptcha(result)) {
    const solved = await solveCaptcha(account, credential);
    if (solved) {
      await sleep(randomInt(CONFIG.signDelayMin, CONFIG.signDelayMax));
      result = await signIn(credential);
    }
  }

  logSignResult(account, result);
}

async function getProtocolCredential(account, cache) {
  const cached = normalizeCacheItem(cache[account.wxid]);
  cached.wxid = account.wxid;
  cached.remark = account.remark;

  if (cached.token && !CONFIG.forceLogin) {
    const valid = await validateToken(cached);
    if (valid.ok) {
      cache[account.wxid] = cached;
      saveCache(cache);
      console.log(`[缓存] ${account.remark} 使用 mfwx.json token`);
      return cached;
    }

    console.log(`[缓存] ${account.remark} token 失效：${valid.message}`);
  }

  return refreshProtocolCredential(account, cached, cache);
}

async function refreshProtocolCredential(account, oldItem, cache) {
  console.log(`[登录] ${account.remark} 获取微信 code`);
  const code = await getWxCode(account.wxid);

  console.log(`[登录] ${account.remark} 业务登录`);
  const result = await mobilApi('api/passport/login', {
    method: 'POST',
    body: { code },
    contentType: 'form',
    cookieJar: oldItem.cookieJar || {},
  });

  if (Number(result.code) !== 0) {
    throw new Error(`业务登录失败：${extractMessage(result) || JSON.stringify(result)}`);
  }

  const token = extractToken(result);
  if (!token) {
    throw new Error(`业务登录未返回 token：${JSON.stringify(result)}`);
  }

  const item = normalizeCacheItem({
    ...oldItem,
    wxid: account.wxid,
    remark: account.remark,
    token,
    xUserId: CONFIG.xUserId || oldItem.xUserId || '',
    updateTime: new Date().toISOString(),
  });

  cache[account.wxid] = item;
  saveCache(cache);
  item.justLoggedIn = true;
  item.cookieJar = oldItem.cookieJar || {};
  console.log(`[登录] ${account.remark} 协议登录成功，token=${maskToken(token)}`);
  return item;
}

async function validateToken(account) {
  try {
    const result = await mobilApi('api/kc/user/user-info', {
      method: 'GET',
      token: account.token,
      xUserId: account.xUserId,
      cookieJar: account.cookieJar,
    });

    if (Number(result.code) === 0) {
      return { ok: true };
    }

    return { ok: false, message: extractMessage(result) || JSON.stringify(result) };
  } catch (error) {
    return { ok: false, message: error.message };
  }
}

async function getWxCode(wxid) {
  try {
    return await getSingleCode(WX_APPID, wxid);
  } catch (e) {
    throw new Error(`获取微信 code 失败：${e.message}`);
  }
}

async function signIn(account) {
  return mobilApi('api/kc/user/sign-in', {
    method: 'POST',
    body: '',
    contentType: 'form',
    token: account.token,
    xUserId: account.xUserId,
    cookieJar: account.cookieJar,
  });
}

async function warmupAccount(account, credential) {
  const kcInfo = await safeMobilApi('api/kc/user/user-info', {
    method: 'GET',
    token: credential.token,
    xUserId: credential.xUserId,
    cookieJar: credential.cookieJar,
  });

  if (Number(kcInfo.code) === 0) {
    const info = kcInfo.data || {};
    const name = info.nickname || info.nick_name || info.mobile || '';
    const ulpUserId = info.ulp_user_id || info.ulpUserId || '';
    console.log(`[预热] ${account.remark} 会员信息正常${name ? `，${name}` : ''}${ulpUserId ? `，ulp=${ulpUserId}` : ''}`);
  } else {
    console.log(`[预热] ${account.remark} 会员信息异常：${extractMessage(kcInfo) || JSON.stringify(kcInfo)}`);
  }

  await safeMobilApi('api/kc/user/user-task', {
    method: 'GET',
    token: credential.token,
    xUserId: credential.xUserId,
    cookieJar: credential.cookieJar,
  });

  const signInfo = await safeMobilApi('api/kc/user/user-sign-info', {
    method: 'GET',
    token: credential.token,
    xUserId: credential.xUserId,
    cookieJar: credential.cookieJar,
  });

  if (Number(signInfo.code) === 0) {
    const data = signInfo.data || {};
    if (data.now_date_is_sign) {
      console.log(`[完成] ${account.remark} 今日已签到`);
      return { alreadySigned: true };
    }
    console.log(`[预热] ${account.remark} 签到信息正常`);
  } else {
    console.log(`[预热] ${account.remark} 签到信息异常：${extractMessage(signInfo) || JSON.stringify(signInfo)}`);
  }

  return { alreadySigned: false };
}

async function safeMobilApi(route, options) {
  try {
    return await mobilApi(route, options);
  } catch (error) {
    return { code: 500, msg: error.message };
  }
}

async function solveCaptcha(account, credential) {
  if (!CONFIG.ocrServer) {
    console.log(`[验证码] ${account.remark} 未配置 MF_OCR_SERVER，跳过自动识别`);
    return false;
  }

  credential.cookieJar = credential.cookieJar || {};

  for (let attempt = 1; attempt <= CONFIG.captchaRetry; attempt += 1) {
    try {
      const randomKey = randomAlphaNum(16);
      console.log(`[验证码] ${account.remark} 第 ${attempt}/${CONFIG.captchaRetry} 次获取图片`);

      const captchaInfo = await mobilApi('site/oil-helper-pic-captcha', {
        method: 'GET',
        query: {
          v: '63bcfda8626469.124631032',
          random_key: randomKey,
          refresh: 'true',
        },
        token: credential.token,
        xUserId: credential.xUserId,
        cookieJar: credential.cookieJar,
      });

      if (Number(captchaInfo.code) !== 0 || !captchaInfo.data || !captchaInfo.data.url) {
        throw new Error(extractMessage(captchaInfo) || JSON.stringify(captchaInfo));
      }

      const imageUrl = appendQuery(captchaInfo.data.url, { random_key: randomKey });
      const imageBuffer = await requestBuffer(imageUrl, {
        headers: {
          Accept: 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
          Referer: `https://servicewechat.com/${WX_APPID}/120/page-frame.html`,
          'User-Agent': WX_UA,
        },
        cookieJar: credential.cookieJar,
      });

      const captchaText = await ocrImage(imageBuffer);
      if (!captchaText) {
        throw new Error('OCR 未返回识别结果');
      }

      console.log(`[验证码] ${account.remark} OCR=${captchaText}`);
      const verify = await mobilApi('plugin/mobil_oil_helper/api/api-v2/verify-capthcha', {
        method: 'POST',
        body: { v_code: captchaText },
        contentType: 'form',
        token: credential.token,
        xUserId: credential.xUserId,
        cookieJar: credential.cookieJar,
      });

      if (Number(verify.code) === 0) {
        console.log(`[验证码] ${account.remark} 校验通过`);
        return true;
      }

      console.log(`[验证码] ${account.remark} 校验失败：${extractMessage(verify) || JSON.stringify(verify)}`);
    } catch (error) {
      console.log(`[验证码] ${account.remark} 处理失败：${error.message}`);
    }
  }

  return false;
}

async function ocrImage(buffer) {
  const result = await requestJson(`${CONFIG.ocrServer}/classification`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      image: buffer.toString('base64'),
    }),
  });

  const text =
    result.result ||
    result.data ||
    result.text ||
    result.code ||
    getByPath(result, ['Data', 'result']) ||
    getByPath(result, ['data', 'result']) ||
    '';

  return String(text).replace(/\s+/g, '').trim();
}

async function mobilApi(route, options = {}) {
  const url = new URL('/web/index.php', BASE_URL);
  url.searchParams.set('_mall_id', MALL_ID);
  url.searchParams.set('r', route);
  for (const [key, value] of Object.entries(options.query || {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }

  const headers = {
    ...COMMON_HEADERS,
    ...(options.headers || {}),
  };

  if (options.token) headers['X-Access-Token'] = options.token;
  if (options.xUserId || CONFIG.xUserId) headers['X-User-Id'] = String(options.xUserId || CONFIG.xUserId);

  let body = options.body;
  if (body !== undefined) {
    if (options.contentType === 'json') {
      headers['Content-Type'] = 'application/json';
      body = typeof body === 'string' ? body : JSON.stringify(body);
    } else {
      headers['Content-Type'] = 'application/x-www-form-urlencoded';
      body = typeof body === 'string' ? body : new URLSearchParams(body).toString();
    }
  }

  return requestJson(url, {
    method: options.method || (body === undefined ? 'GET' : 'POST'),
    headers,
    body,
    cookieJar: options.cookieJar,
  });
}

function requestJson(urlInput, options = {}) {
  return requestRaw(urlInput, options).then((response) => {
    const text = response.body.toString('utf8');
    try {
      return text ? JSON.parse(text) : {};
    } catch (error) {
      throw new Error(`响应不是合法 JSON：${shortText(text)}`);
    }
  });
}

function requestBuffer(urlInput, options = {}) {
  return requestRaw(urlInput, options).then((response) => response.body);
}

function requestRaw(urlInput, options = {}) {
  const url = urlInput instanceof URL ? urlInput : new URL(urlInput);
  const isHttps = url.protocol === 'https:';
  const client = isHttps ? https : http;
  const bodyBuffer =
    options.body === undefined || options.body === null
      ? null
      : Buffer.from(String(options.body), 'utf8');

  const headers = { ...(options.headers || {}) };
  const cookieHeader = cookieString(options.cookieJar);
  if (cookieHeader && !headers.Cookie && !headers.cookie) headers.Cookie = cookieHeader;

  if (bodyBuffer && !headers['Content-Length'] && !headers['content-length']) {
    headers['Content-Length'] = bodyBuffer.length;
  }

  return new Promise((resolve, reject) => {
    const req = client.request(
      url,
      {
        method: options.method || (bodyBuffer ? 'POST' : 'GET'),
        headers,
        timeout: CONFIG.timeout,
        rejectUnauthorized: false,
      },
      (res) => {
        const chunks = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => {
          try {
            updateCookieJar(options.cookieJar, res.headers['set-cookie']);

            if (
              res.statusCode >= 300 &&
              res.statusCode < 400 &&
              res.headers.location &&
              (options.redirects || 0) < 5
            ) {
              const redirectUrl = new URL(res.headers.location, url);
              resolve(requestRaw(redirectUrl, { ...options, redirects: (options.redirects || 0) + 1 }));
              return;
            }

            const raw = decodeResponse(Buffer.concat(chunks), res.headers['content-encoding']);

            if (res.statusCode < 200 || res.statusCode >= 300) {
              const text = raw.toString('utf8');
              reject(new Error(`HTTP ${res.statusCode}：${shortText(text)}`));
              return;
            }

            resolve({ body: raw, headers: res.headers, statusCode: res.statusCode });
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

function decodeResponse(buffer, encoding) {
  const value = String(encoding || '').toLowerCase();
  if (value.includes('br')) return zlib.brotliDecompressSync(buffer);
  if (value.includes('gzip')) return zlib.gunzipSync(buffer);
  if (value.includes('deflate')) return zlib.inflateSync(buffer);
  return buffer;
}

function updateCookieJar(jar, setCookie) {
  if (!jar || !setCookie) return;
  const values = Array.isArray(setCookie) ? setCookie : [setCookie];
  for (const item of values) {
    const pair = String(item).split(';')[0];
    const index = pair.indexOf('=');
    if (index <= 0) continue;
    const key = pair.slice(0, index).trim();
    const value = pair.slice(index + 1).trim();
    if (key) jar[key] = value;
  }
}

function cookieString(jar) {
  if (!jar || typeof jar !== 'object') return '';
  return Object.entries(jar)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key}=${value}`)
    .join('; ');
}

function appendQuery(urlValue, params) {
  const url = new URL(String(urlValue), BASE_URL);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

function logSignResult(account, result) {
  const code = Number(result && result.code);
  const data = (result && result.data) || {};

  if (code === 0) {
    const signed = data.now_date_is_sign;
    const days = data.sign_continue_text || data.sign_continue_day || data.sign_continue || '未知';
    const points = data.sign_once_point || data.point || '未知';

    if (signed) {
      console.log(`[成功] ${account.remark} 签到成功，已累计签到 ${days} 天，本次获得 ${points} 积分`);
    } else {
      console.log(`[完成] ${account.remark} 签到返回：${JSON.stringify(result)}`);
    }
    return;
  }

  if (needsCaptcha(result)) {
    console.log(`[风控] ${account.remark} 风险识别未通过，源码会在这里弹图形验证码；建议稍后重试或降低频率`);
    return;
  }

  console.log(`[失败] ${account.remark} 签到失败：${extractMessage(result) || JSON.stringify(result)}`);
}

function isLoginExpired(result) {
  if (!result) return false;
  if (Number(result.code) === -1) return true;
  return /请先登录|登录失效|token/i.test(extractMessage(result));
}

function needsCaptcha(result) {
  if (!result) return false;
  if (Number(result.code) === -11) return true;
  return /风险识别|验证码|校验码/i.test(extractMessage(result));
}

function parseWxAccounts(raw) {
  return splitEnv(raw).map((item) => {
    const [wxid, remark] = splitRemark(item);
    return { wxid, remark: remark || wxid };
  }).filter((item) => item.wxid);
}

function parseTokenAccounts(raw) {
  return splitEnv(raw).map((item, index) => {
    const [token, remark] = splitRemark(item);
    return {
      token,
      remark: remark || `token账号${index + 1}`,
    };
  }).filter((item) => item.token);
}

function splitEnv(raw) {
  return String(raw || '')
    .split(/[\n&@]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function splitRemark(value) {
  const index = value.indexOf('#');
  if (index === -1) return [value.trim(), ''];
  return [value.slice(0, index).trim(), value.slice(index + 1).trim()];
}

function loadCache() {
  try {
    if (!fs.existsSync(CACHE_FILE)) return {};
    const data = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
    return data && typeof data === 'object' ? data : {};
  } catch (error) {
    console.log(`[缓存] 读取 mfwx.json 失败：${error.message}`);
    return {};
  }
}

function saveCache(cache) {
  try {
    fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2), 'utf8');
  } catch (error) {
    console.log(`[缓存] 保存 mfwx.json 失败：${error.message}`);
  }
}

function normalizeCacheItem(item) {
  const value = item && typeof item === 'object' ? { ...item } : {};
  value.token = value.token || value.accessToken || value.access_token || '';
  value.xUserId = CONFIG.xUserId || value.xUserId || value.x_user_id || '';
  return value;
}

function extractToken(result) {
  const paths = [
    ['data', 'access_token'],
    ['data', 'accessToken'],
    ['data', 'token'],
    ['data', 'user', 'access_token'],
    ['data', 'user', 'accessToken'],
    ['data', 'user', 'token'],
    ['data', 'user_info', 'access_token'],
    ['data', 'user_info', 'accessToken'],
    ['data', 'user_info', 'token'],
    ['access_token'],
    ['accessToken'],
    ['token'],
  ];

  for (const item of paths) {
    const value = getByPath(result, item);
    if (isUsefulString(value)) return value;
  }

  return findKeyDeep(result, ['access_token', 'accessToken', 'token']);
}

function getByPath(source, keys) {
  let current = source;
  for (const key of keys) {
    if (!current || typeof current !== 'object' || !(key in current)) return undefined;
    current = current[key];
  }
  return current;
}

function findKeyDeep(source, names) {
  const wanted = new Set(names.map(normalizeName));
  const queue = [{ value: source, depth: 0 }];

  while (queue.length) {
    const { value, depth } = queue.shift();
    if (!value || typeof value !== 'object' || depth > 5) continue;

    for (const [key, child] of Object.entries(value)) {
      if (wanted.has(normalizeName(key)) && isUsefulString(child)) {
        return String(child);
      }
      if (child && typeof child === 'object') {
        queue.push({ value: child, depth: depth + 1 });
      }
    }
  }

  return '';
}

function normalizeName(value) {
  return String(value).toLowerCase().replace(/[-_]/g, '');
}

function isUsefulString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function extractMessage(result) {
  if (!result || typeof result !== 'object') return '';
  return String(result.msg || result.message || result.error || result.errmsg || '');
}

function maskToken(token) {
  const value = String(token || '');
  if (value.length <= 10) return value ? '***' : '';
  return `${value.slice(0, 4)}***${value.slice(-4)}`;
}

function shortText(text) {
  const value = String(text || '').replace(/\s+/g, ' ').trim();
  return value.length > 500 ? `${value.slice(0, 500)}...` : value;
}

function trimRightSlash(value) {
  return String(value || '').replace(/\/+$/, '');
}

function toPositiveInt(value, fallback) {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) && number > 0 ? number : fallback;
}

function toNonNegativeInt(value, fallback) {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) && number >= 0 ? number : fallback;
}

function randomInt(min, max) {
  const low = Math.min(min, max);
  const high = Math.max(min, max);
  if (high <= low) return low;
  return Math.floor(Math.random() * (high - low + 1)) + low;
}

function randomAlphaNum(length) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let result = '';
  for (let index = 0; index < length; index += 1) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
