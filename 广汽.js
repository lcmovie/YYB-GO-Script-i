// name:广汽
/**
 * 广汽丰田新能源 - 微信协议版（无babel依赖）
 * cron: 26 11,17 * * *
 * 变量：
 *   WX_ID=wxid#备注#deviceId#UA  (多号用换行或&，除了wxid其它皆选填，会自动生成一号一UA设备ID)
 *   WECHAT_SERVER/YYB_SERVER/SERVER_TYPE 在 getCode.js 中配置（微信协议地址）
 * 缓存：gqft.json
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { getSingleCode } = require('./getCode.js'); // 共享微信小程序 code 获取模块（自动路由牛子/应用宝，读取 WX_ID）
const { sendNotify } = require('./sendNotify.js');

const NAME = '广汽丰田新能源-微信协议版';
const APPID = 'wxd8a42d1c0c59c15d';
const API_VERSION = '1.4.0';
const WXGQFT = (process.env.WX_ID || '').trim();

const GW_BASE = 'https://gw.nevapp.gtmc.com.cn';
const XCX_BASE = 'https://xcx.nevapp.gtmc.com.cn/wxapp/nev-prod/bff-nev-wxapp';
const APP_ID = 'ecb4fdd3-da09-408a-913b-44d311d03105';
const APP_SIG_SECRET = '611ac848-be11-404e-b7a3-54f735d2eb3e';
const PUBLIC_KEY = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA49jxpFBAoEslNYrHb0wT8nCpGBn3hvjgToNkp7lFpsSeRS7WbHoFJEvmf1U83cHrbTzRFRowPft/FGBw6/6dZcmMjMgz1n0FWlqk0d7QjEDL+t9Dj9tH9e/qdGfJ3bzR0ZgpgQMpKpx5I5fcEgzMYnHWGLZBY+v+PlPTN/1mz0nnRtIIxb8YuZZFvadfGTC8jeD7tMERpd5zENml5cLbVujENsag9AIpvLdvR6fSewi3l9QmssWpty50UpcAWsvAs+ExRYyUe/s1lwfSdSciW6Lrj4sp4MMaWifdTQUbKKEeuRugEqJSDrxhxoybEbSbl2CYaTR8kifZ1n+lcAh6cQIDAQAB';
const PRIVATE_KEY = 'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCUEPwXFgsGTngqifX48k/5CRBNVA2/mLJhl+fP7Z0UHrSQmI31rtXcb9zN6PMG0jvNxk0oLvrUgf1K/lfgDp0noUQpCbHqkCk0CGQogSIVr/ktu5lhev0/P+9pkFfXrrZWKYhBk/z7r/XYvmsm4TVyFhge5WZqfY+HXhFmzJEu9lhq9VACXsfXJ6O778Dj3fF6hHsyNsai+qGNL31bdObxJG8EhWNcwK0ejCa8XzsscasbjZ/AhTwAQf9kxT9diCZv2vWvK5QtDhxMbqyQ6lFE8Ew9jaAHYnp2jxh3CwcAMp9B0+Ne4JOBaY7IjH9ENqMC29cYnhxNhj3ZGcbEu6lpAgMBAAECggEBAISKY66iu8GscmLZ1kY/Whk55M7jw97TaDJ2UTrOn8KH7ehVtxXKqIPH2qaztQBRJtl/fkfPLhcWOU9tN+pICqOT9zipBgtLeqaqMEYVuhYhzPMEMDuTZai9qakcXZWjPnMIgID7YQVHsNGROse15yq13mehv7jpppZtPTSBQCEBZAw+SFNS4KVfBDKNntlesEuLJHGWWXnqxWwK3YA4IdUAJjT5kDEiYQs7uy2FHqdcZnw7hV/Tt3OWDqrOB8zoZVhEg9dLvqpBaUi6yh9ihUYJBtFegmsFSY7MazHQjYnY8bcEcoma22c3AZbGeRwTwrNrlL0/UvF60L1njx4xhSUCgYEA0Xgh4mFSrp5E0UbMvy5TnpayH1hcaJNFjyGgQGdwgnE69gzR1Grqv+ihSjTbPvQHu9IGnuXb6Pdm/tuj2ml4xTJ9OnTe2/x/TzMIserNfRD1v6prxjNgZc+YDEebxHTWDBtCNpdbOEy27yO4fc9UvIoIbgG5eDTcMwCtiIt+98sCgYEAtPUPBqegfiDzyBP7l2hxhGwFgIrsFYIg3lJwwlyYpZEt8p/TMwPAMb2k+nfQPtyS6T2bBGr2PAKUAubD1SrwGE4ndXO4SDB814ll93ZrE7X18iyoGBwbgpjGMONK3nbS2z+2WrFEtQZaUuLiiZp+hnxk5uW7EQ5RnToOaUTPtRsCgYBNUOhA5Odd6LFCBb4BOxpGSR1KEJVbTDC6mhDKdOPEYgL/WtAAdc5cM4OFHmlmnTBVlTo4YGOBZAAyReP+9DtNnks2zniL/nEHTLEC6sYaSa5Lpp3NNJ16NtvKfIv0QaPYKB+Sgt96smY7cpXgaiy+wrxFzoEk623zrWZgJg0hbQKBgFMkEO5O0CeDPl6cB8lt/FIKS5Dew0+yhSWAnTw/zQatKH5EPoY+3+w6pPVLXUu0jm9JldK2zkGOMbEPk8R6QOv55JlLPM02MfXZtBa5usLIpKLLL8Q8Dcu4I79MfxatY33GzSLoNZgyvgc9JTZx3FYwCzAnNwbEHG1vwjVNn10nAoGASPxDtahASVh/IN6sjFR1soU8fuzEzThpnchfNVp3BeROR/8fXyfyBk3hKGmh6PY41XttKrGBwCaztCwA6zoTv7/SmzqNCzknq4uFbr9o455T0+0gtBKS6vFv1zCnvyMXjcmyCvB7gIRnhoq5W/z9l8VtAagNi9JOhZpjCl7Ep70=';
const CACHE_FILE = path.join(__dirname, 'gqft.json');

const pubPem = `-----BEGIN PUBLIC KEY-----\n${PUBLIC_KEY.match(/.{1,64}/g).join('\n')}\n-----END PUBLIC KEY-----`;
const priPem = `-----BEGIN PRIVATE KEY-----\n${PRIVATE_KEY.match(/.{1,64}/g).join('\n')}\n-----END PRIVATE KEY-----`;
const priJwk = crypto.createPrivateKey(priPem).export({ format: 'jwk' });
const priN = b64uToBigInt(priJwk.n);
const priD = b64uToBigInt(priJwk.d);
const priKlen = b64uToBuf(priJwk.n).length;

function b64uToBuf(s) {
  return Buffer.from(String(s).replace(/-/g, '+').replace(/_/g, '/'), 'base64');
}
function b64uToBigInt(s) {
  const h = b64uToBuf(s).toString('hex');
  return BigInt(`0x${h || '0'}`);
}
function modPow(base, exp, mod) {
  let b = base % mod, e = exp, r = 1n;
  while (e > 0n) {
    if (e & 1n) r = (r * b) % mod;
    e >>= 1n;
    b = (b * b) % mod;
  }
  return r;
}
function rsaEncryptPkcs1V15(plain) {
  return crypto.publicEncrypt({ key: pubPem, padding: crypto.constants.RSA_PKCS1_PADDING }, Buffer.from(String(plain))).toString('base64');
}
function rsaDecryptPkcs1V15(encB64) {
  const c = BigInt(`0x${Buffer.from(encB64, 'base64').toString('hex') || '0'}`);
  const m = modPow(c, priD, priN);
  let hex = m.toString(16);
  if (hex.length % 2) hex = `0${hex}`;
  let em = Buffer.from(hex, 'hex');
  if (em.length < priKlen) em = Buffer.concat([Buffer.alloc(priKlen - em.length, 0), em]);
  // PKCS#1 v1.5 block: 00 02 PS... 00 DATA
  if (em.length < 11 || em[0] !== 0x00 || em[1] !== 0x02) throw new Error('RSA解密填充头错误');
  let i = 2;
  while (i < em.length && em[i] !== 0x00) i++;
  if (i < 10 || i >= em.length) throw new Error('RSA解密填充分隔错误');
  return em.slice(i + 1).toString('utf8');
}

const log = console.log;
const rand = (n = 6) => { let s = ''; while (s.length < n) s += Math.random().toString(36).slice(2); return s.slice(0, n); };
const md5 = s => crypto.createHash('md5').update(s).digest('hex');

async function jreq(method, url, { headers = {}, data, timeout = 20000 } = {}) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), timeout);
  try {
    const opt = { method, headers, signal: c.signal };
    if (data !== undefined) opt.body = typeof data === 'string' ? data : JSON.stringify(data);
    const r = await fetch(url, opt);
    const txt = await r.text();
    if (!txt || !txt.trim()) throw new Error(`非JSON响应: 空响应 [${r.status}] ${method} ${url}`);
    let json;
    try { json = JSON.parse(txt); } catch { throw new Error(`非JSON响应: ${txt.slice(0, 120)} [${r.status}] ${method} ${url}`); }
    return { status: r.status, data: json };
  } finally { clearTimeout(t); }
}

function loadCache() { try { return JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8')) || {}; } catch { return {}; } }
function saveCache(c) { fs.writeFileSync(CACHE_FILE, JSON.stringify(c, null, 2)); }
function parseAccounts(raw) {
  return raw.split(/\n|&/).map(s => s.trim()).filter(Boolean).map(s => {
    const p = s.split('#');
    const wxid = p[0] ? p[0].trim() : '';
    const remark = p[1] ? p[1].trim() : wxid;
    const deviceId = p[2] ? p[2].trim() : md5(wxid).slice(0, 16);
    const hwHash = md5(wxid).slice(0, 8);
    const defaultUa = `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x${hwHash}) UnifiedPCWindowsWechat(0x${hwHash}) XWEB/19201`;
    const ua = p[3] ? p[3].trim() : defaultUa;
    return { wxid, remark, deviceId, ua };
  }).filter(x => x.wxid);
}
function parseJwt(token) {
  try {
    const raw = String(token || '').replace(/^Bearer\s+/i, '').trim();
    const [, p] = raw.split('.');
    return JSON.parse(Buffer.from(p.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8'));
  } catch { return {}; }
}
function fmt(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`; }
function decodeMaybeB64Phone(s) {
  const raw = String(s || '').trim();
  if (!raw) return '';
  if (/^1\d{10}$/.test(raw)) return raw;
  if (!/^[A-Za-z0-9+/=]+$/.test(raw)) return raw;
  try {
    const d = Buffer.from(raw, 'base64').toString('utf8').trim();
    return /^1\d{10}$/.test(d) ? d : raw;
  } catch { return raw; }
}

function aesEncrypt(obj) {
  const key = rand(16), iv = rand(16), keyiv = `${key}@DS@${iv}`;
  const cipher = crypto.createCipheriv('aes-128-cbc', Buffer.from(key), Buffer.from(iv));
  let enc = cipher.update(typeof obj === 'string' ? obj : JSON.stringify(obj), 'utf8', 'base64');
  enc += cipher.final('base64');
  return { encryptKey: rsaEncryptPkcs1V15(keyiv), encryptData: enc };
}
function aesDecrypt(encData, encKey) {
  const keyiv = rsaDecryptPkcs1V15(encKey);
  const [key, iv] = keyiv.split('@DS@');
  const dec = crypto.createDecipheriv('aes-128-cbc', Buffer.from(key), Buffer.from(iv));
  let out = dec.update(encData, 'base64', 'utf8');
  out += dec.final('utf8');
  return out;
}

async function getWxCode(wxid) {
  try {
    return await getSingleCode(APPID, wxid);
  } catch (e) {
    throw new Error(`微信协议取code失败: ${e.message}`);
  }
}
async function xcxLoginByCode(acc, code) {
  const url = `${XCX_BASE}/auth/login?code=${encodeURIComponent(code)}&clickUrl=${encodeURIComponent('/pages/index/index')}&clickId=`;
  const { data } = await jreq('POST', url, {
    data: { code, clickUrl: '/pages/index/index', clickId: '' },
    headers: { 'User-Agent': acc.ua, 'content-type': 'application/json', apiVersion: API_VERSION, Referer: `https://servicewechat.com/${APPID}/138/page-frame.html` },
  });
  if (data?.header?.code !== 10000000) throw new Error(`小程序登录失败: ${data?.header?.message || JSON.stringify(data)}`);
  if (!data?.body?.token) throw new Error('小程序登录返回无token');
  return data.body;
}
async function exchangeGwToken(acc, xcxToken) {
  const timestamp = Date.now();
  const nonce = rand(6);
  const sig = md5(`${timestamp}Basic bmV2YXBwOnNlY3JldA==${nonce}${APP_ID}${APP_SIG_SECRET}`);
  const body = aesEncrypt({ grant_type: 'password', username: '18825160040', password: xcxToken, auth_type: 'newminipg' });
  const { data } = await jreq('POST', `${GW_BASE}/ha/iam/api/sec/oauth/token`, {
    data: body,
    headers: {
      'User-Agent': acc.ua,
      'content-type': 'application/json',
      Authorization: 'Basic bmV2YXBwOnNlY3JldA==',
      appId: APP_ID,
      timestamp,
      xweb_xhr: '1',
      nonce,
      sig,
      deviceId: acc.deviceId,
      operateSystem: 'h5',
      appVersion: '',
      Referer: `https://servicewechat.com/${APPID}/138/page-frame.html`,
    },
  });
  const plain = JSON.parse(aesDecrypt(data.encryptData, data.encryptKey));
  if (plain?.header?.code !== 10000000 || !plain?.body?.accessToken) throw new Error(`换取GW token失败: ${JSON.stringify(plain)}`);
  return plain.body.accessToken;
}

class GwClient {
  constructor(token, anonymousId = '', appVersion = '3.22', acc = {}) { this.token = token; this.anonymousId = anonymousId; this.appVersion = appVersion; this.acc = acc; }
  sign(url, body) {
    const ts = Date.now();
    const nonce = rand(6);
    const raw = this.token.replace(/^Bearer\s+/i, '').trim();
    return { timestamp: ts, nonce, sig: md5(`${ts}${raw}${nonce}${APP_ID}${APP_SIG_SECRET}`) };
  }
  async req(method, path, query = {}, body = undefined) {
    const qs = Object.keys(query).length ? `?${new URLSearchParams(query).toString()}` : '';
    const { timestamp, nonce, sig } = this.sign(path + qs, body);
    const headers = {
      'content-type': 'application/json',
      appId: APP_ID,
      Authorization: this.token,
      timestamp: String(timestamp),
      xweb_xhr: '1',
      sig,
      nonce,
      appVersion: this.appVersion,
      operateSystem: 'h5',
    };
    if (this.acc?.deviceId) headers.deviceId = this.acc.deviceId;
    if (this.acc?.ua) headers['User-Agent'] = this.acc.ua;
    if (this.anonymousId) headers.AnonymousID = this.anonymousId;
    const send = method === 'GET' ? undefined : (Object.keys(body || {}).length ? aesEncrypt(body) : {});
    const { data } = await jreq(method, `${GW_BASE}${path}${qs}`, { headers, data: send });
    let d = data;
    if (d?.encryptData && d?.encryptKey) d = JSON.parse(aesDecrypt(d.encryptData, d.encryptKey));
    if (d?.header?.code !== 10000000) throw new Error(`GW接口失败 ${d?.header?.code} ${d?.header?.message || ''}`);
    return d.body;
  }
  queryScore() { return this.req('POST', '/main/api/sec/lgn/integral/my-total-num', { noLoad: 'true', noTip: 'true' }, { gtmcUid: '' }); }
  attendance(start, end) { return this.req('GET', '/main/api/marketing/lgn/sec/usersign/getAttendanceBook', { beginTime: start, endTime: end, noLoad: 'true' }); }
  signin() { return this.req('POST', '/main/api/marketing/lgn/task/sec/signinV2', { noLoad: 'true', noTip: 'true' }, { gtmcUid: '', fromApplication: '0' }); }
  receiveBlind(id) { return this.req('GET', '/main/api/sec/lgn/blindBox/addActivityTypeBlindBoxAward', { blindBoxId: id, noTip: 'true' }); }
}

class XcxClient {
  constructor(token, ua = '') { this.token = token; this.ua = ua; }
  async req(method, path, query = {}, body = undefined) {
    const qs = Object.keys(query).length ? `?${new URLSearchParams(query).toString()}` : '';
    const { data } = await jreq(method, `${XCX_BASE}${path}${qs}`, {
      data: body,
      headers: { Authorization: this.token, apiVersion: API_VERSION, 'content-type': 'application/json', 'User-Agent': this.ua || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36' },
    });
    if (data?.header?.code !== 10000000) {
      const hc = data?.header?.code;
      const rc = data?.code;
      const rm = data?.header?.message || data?.message || data?.msg || '';
      throw new Error(`XCX接口失败 [${method} ${path}] headerCode=${hc} code=${rc ?? ''} ${rm}`.trim());
    }
    return data.body;
  }
  currentUser() { return this.req('GET', '/user/current'); }
  pointList(pageNum = 1) { return this.req('GET', '/point/pointList', { pageNum, pageSize: 20, status: '0' }); }
  questionPage(pageNum = 1) { return this.req('POST', '/question/findAllQuestionPage', {}, { pageNum, pageSize: 10, clientType: 2, questionTypeId: null }); }
  answers(questionId) { return this.req('POST', '/questionAnswer/findLastQuestionAnswerPage', {}, { questionId: String(questionId), pageNum: 1, pageSize: 20 }); }
  saveAnswer(questionId, content) { return this.req('POST', '/questionAnswer/save', {}, { answerType: 1, content, questionAnswerFiles: [], questionAnswerId: null, questionId: String(questionId), type: 3 }); }
  infoPage(pageNum = 1) { return this.req('GET', '/information/pages', { pageNum, pageSize: 10 }); }
  postPage(pageNum = 1) { return this.req('POST', '/post/page', {}, { pageNum, pageSize: 10, displayFlag: true, shownIds: [] }); }
  comments(subjectId, subjectType = 'INFORMATION') { return this.req('GET', '/comment/page', { subjectId: String(subjectId), subjectType, pageNum: 1, pageSize: 20, essence: 'NOT_ESSENCE' }); }
  postComment(fromUid, subjectId, content, subjectType = 'INFORMATION') { return this.req('POST', '/comment', {}, { content, fromUid: String(fromUid), subjectId: String(subjectId), subjectType }); }
}

const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
const pick = arr => arr[Math.floor(Math.random() * arr.length)];
function mondayRange() {
  const n = new Date();
  const d = n.getDay() || 7;
  const s = new Date(n); s.setDate(n.getDate() - d + 1); s.setHours(0, 0, 0, 0);
  const e = new Date(s); e.setDate(s.getDate() + 6); e.setHours(23, 59, 59, 999);
  return [s, e];
}
function parseCn(s) {
  const m = String(s || '').match(/(\d{4})年(\d{2})月(\d{2})日\s+(\d{2}):(\d{2}):(\d{2})/);
  return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : null;
}
async function rewardedThisWeek(xcx, kws) {
  const [ws, we] = mondayRange();
  for (let p = 1; p <= 5; p++) {
    const b = await xcx.pointList(p);
    const list = b?.data || [];
    if (!list.length) return null;
    for (const it of list) {
      const t = parseCn(it.createTime);
      if (!t) continue;
      if (t < ws) return null;
      if (t > we) continue;
      const d = `${it.actionDesc || ''} ${it.remark || ''}`;
      if (kws.some(k => d.includes(k))) return it;
    }
    if (list.length < 20) return null;
  }
  return null;
}
async function weeklyAnswer(xcx, myUid) {
  for (let p = 1; p <= 3; p++) {
    const q = await xcx.questionPage(p);
    for (const item of (q?.data || []).sort(() => Math.random() - 0.5)) {
      const ans = await xcx.answers(item.id);
      const cands = (ans?.data || []).filter(x => String(x.createBy || '') !== String(myUid)).map(x => norm(x.content)).filter(x => x.length >= 4);
      if (!cands.length) continue;
      const content = pick(cands);
      await xcx.saveAnswer(item.id, content);
      return { questionId: item.id, content };
    }
  }
  return null;
}
async function weeklyComment(xcx, myUid) {
  let mode = 'INFORMATION';
  let pager = async p => xcx.infoPage(p);
  try {
    await pager(1);
  } catch {
    mode = 'POST';
    pager = async p => xcx.postPage(p);
  }

  for (let p = 1; p <= 3; p++) {
    const list = await pager(p);
    for (const art of (list?.data || []).sort(() => Math.random() - 0.5)) {
      const c = await xcx.comments(art.id, mode);
      const cands = (c?.data || []).filter(x => String(x.fromUid || '') !== String(myUid)).map(x => norm(x.content)).filter(x => x.length >= 2);
      if (!cands.length) continue;
      const content = pick(cands);
      await xcx.postComment(myUid, art.id, content, mode);
      return { subjectId: art.id, subjectType: mode, content };
    }
  }
  return null;
}
function weekStartEnd() {
  const n = new Date();
  const d = n.getDay();
  const s = new Date(n); s.setDate(n.getDate() - d);
  const e = new Date(s); e.setDate(s.getDate() + 6);
  const f = x => x.toISOString().slice(0, 10);
  return [f(s), f(e)];
}

async function ensureCred(acc, cache) {
  let c = cache[acc.wxid] || {};
  const exp = parseJwt(c.gwToken || '').exp || 0;
  if (c.gwToken && exp > Math.floor(Date.now() / 1000) + 60) {
    try {
      const gw = new GwClient(c.gwToken, c.anonymousId, c.appVersion || '3.22', acc);
      await gw.queryScore();
      if (c.xcxToken) {
        const xcx = new XcxClient(c.xcxToken, acc.ua);
        await xcx.currentUser();
      } else {
        throw new Error('缓存缺少xcxToken');
      }
      log(`✅ ${acc.remark} 使用缓存ck`);
      return c;
    } catch (e) {
      log(`⚠️ ${acc.remark} 缓存ck失效，刷新（${e.message}）`);
    }
  } else {
    log(`ℹ️ ${acc.remark} 无有效缓存ck，走微信协议`);
  }

  const code = await getWxCode(acc.wxid);
  const login = await xcxLoginByCode(acc, code);
  const xcxToken = login.token;
  log(`微信登录token长度: ${String(xcxToken || '').length}`);
  const gwToken = await exchangeGwToken(acc, xcxToken);
  c = { wxid: acc.wxid, xcxToken, gwToken, anonymousId: login.openId || '', appVersion: '3.22', updateTime: new Date().toISOString() };
  cache[acc.wxid] = c;
  saveCache(cache);
  return c;
}

async function main() {
  if (!WXGQFT) throw new Error('未设置变量 WX_ID');
  const accounts = parseAccounts(WXGQFT);
  if (!accounts.length) throw new Error('WX_ID 无账号');

  const cache = loadCache();
  log(`${NAME} 启动，共${accounts.length}个账号，缓存名:gqft`);

  for (let i = 0; i < accounts.length; i++) {
    const acc = accounts[i];
    log(`\n====== 账号${i + 1} ${acc.remark} ======`);
    try {
      const cred = await ensureCred(acc, cache);
      const gw = new GwClient(cred.gwToken, cred.anonymousId, cred.appVersion, acc);
      const xcx = new XcxClient(cred.xcxToken, acc.ua);
      const me = await xcx.currentUser();
      const showName = decodeMaybeB64Phone(me?.phone) || me?.nickname || acc.remark;

      const [s, e] = weekStartEnd();
      const book = await gw.attendance(s, e);
      if (!book.todayHasSigned) {
        const r = await gw.signin();
        log(`签到: +${r?.point || 0}`);
      } else {
        log('签到: 今日已签');
      }

      const book2 = await gw.attendance(s, e);
      const claim = (book2.signBlindBoxOutBoList || []).filter(x => Number(x.status) === 0);
      if (claim.length) {
        const cfg = book2.signUserBlindBoxConfigOutBoList || [];
        for (const b of claim) {
          const hit = cfg.find(x => Number(x.timeInterval) === Number(b.days));
          const id = hit?.id || b.days;
          try { await gw.receiveBlind(id); log(`盲盒: ${b.days}天已领`); } catch (e2) { log(`盲盒: ${b.days}天领取失败 ${e2.message}`); }
        }
      } else {
        log('盲盒: 暂无可领');
      }

      const score = await gw.queryScore();
      log(`查询: ${showName} 当前积分 ${score?.score ?? 0}`);

      try {
        const ansHit = await rewardedThisWeek(xcx, ['回答', '问答']);
        if (ansHit) {
          log(`回答问题: 本周已得分，跳过（${ansHit.actionDesc} ${ansHit.createTime}）`);
        } else {
          const ar = await weeklyAnswer(xcx, me.id);
          log(ar ? `回答问题: 已提交 questionId=${ar.questionId} content=${ar.content}` : '回答问题: 无可用题目/答案');
        }
      } catch (e1) {
        log(`回答问题: 执行异常，跳过（${e1.message}）`);
      }

      try {
        const cmtHit = await rewardedThisWeek(xcx, ['评论']);
        if (cmtHit) {
          log(`评论文章: 本周已得分，跳过（${cmtHit.actionDesc} ${cmtHit.createTime}）`);
        } else {
          const cr = await weeklyComment(xcx, me.id);
          log(cr ? `评论文章: 已提交 subjectType=${cr.subjectType} subjectId=${cr.subjectId} content=${cr.content}` : '评论文章: 无可用文章/评论');
        }
      } catch (e2) {
        log(`评论文章: 执行异常，跳过（${e2.message}）`);
      }

      const tokenExp = parseJwt(cred.gwToken).exp;
      if (tokenExp) log(`CK到期: ${fmt(new Date(tokenExp * 1000))}`);
    } catch (e) {
      log(`❌ ${acc.remark} 失败: ${e.message}`);
    }
  }
}

main()
  .then(() => sendNotify(NAME, '全部账号任务执行完成'))
  .catch(async e => {
    console.error(e.message || e);
    await sendNotify(`${NAME}异常`, e.stack || e.message || String(e));
    process.exitCode = 1;
  });
